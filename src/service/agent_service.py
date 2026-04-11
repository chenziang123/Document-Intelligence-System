"""Agent 服务层 - 封装现有 Agent 供 API 调用"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from config import SystemConfig, get_config
from core.llm import get_llm_service
from core.orchestrator.coordinator import WorkflowCoordinator
from core.orchestrator.task_spec import TaskSpec, TaskType, FileInfo, FileType
from db.session_repository import get_messages, get_session_files
from langchain_openai import ChatOpenAI

# ============================================================================
# Session 级别的 Agent 实例缓存
# 设计原则：文件和对话历史都跟随消息，agent 被同一个 session 复用
# ============================================================================
_agent_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def _get_cached_agent(session_id: str, config: SystemConfig) -> Any:
    """
    获取或创建 session 对应的 DocumentAgent 实例。
    该实例在同一 session 的多次对话中被复用，对话历史累积。
    """
    with _cache_lock:
        if session_id not in _agent_cache:
            from core.agents.document_understand_agent import DocumentAgent
            _agent_cache[session_id] = DocumentAgent(config)
        return _agent_cache[session_id]


def clear_session_agent(session_id: str):
    """清除 session 对应的 agent 实例（当需要重置时调用）"""
    with _cache_lock:
        if session_id in _agent_cache:
            del _agent_cache[session_id]


def set_agent_files(agent: Any, files: List[Dict[str, Any]], config: SystemConfig, session_id: str = None):
    """
    将消息携带的文件设置到 agent。
    设计：每次消息的文件都追加/更新到 agent，不清除旧文件。
    这样用户可以问"基于刚才的文件"或"基于所有上传的文件"。
    
    重要：如果 files 为空列表（表示用户主动取消了所有文件勾选），
    则清除 agent 的文档内容，防止使用旧文档产生幻觉。
    """
    # ========== 核心修复：无文件时清除 agent 的文档内容 ==========
    if not files:
        # 用户没有勾选任何文件，清除 agent 的文档缓存
        agent._document_contents = {}
        agent._source_files = []
        return
    
    file_infos = []
    for f in files:
        is_selected = f.get('is_selected', True)
        if not is_selected:
            continue
        
        # 优先使用传入的 file_path，如果为空则从数据库查询
        file_path = f.get('file_path', '')
        if not file_path and session_id and f.get('file_id'):
            # 从数据库获取完整的文件信息
            db_files = get_session_files(session_id, config=config)
            for db_file in db_files:
                if db_file.id == f.get('file_id'):
                    file_path = db_file.file_path
                    break
        
        file_info = FileInfo(
            path=file_path,
            file_type=_get_file_type(f.get('file_name', '')),
        )
        file_infos.append(file_info)
    
    if file_infos:
        # 调用 agent 的 set_documents 方法加载文件
        agent.set_documents(file_infos, max_rows=100)


def _get_file_type(file_name: str) -> FileType:
    """根据文件名判断文件类型"""
    ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
    mapping = {
        'pdf': FileType.PDF,
        'doc': FileType.DOCX,
        'docx': FileType.DOCX,
        'xls': FileType.XLSX,
        'xlsx': FileType.XLSX,
        'txt': FileType.TXT,
        'md': FileType.MD,
    }
    return mapping.get(ext, FileType.TXT)


def get_selected_session_files_payload(
    session_id: str, config: SystemConfig
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    从会话存储读取已勾选的数据文件与模板，组装为 Agent 所需的字典列表。
    前端发消息时未带 file_path，须以库中勾选状态为准。
    """
    rows = get_session_files(session_id, config=config)
    data_files: List[Dict[str, Any]] = []
    template_files: List[Dict[str, Any]] = []
    for f in rows:
        if not getattr(f, "is_selected", False):
            continue
        entry = {
            "file_path": f.file_path,
            "file_name": f.file_name,
            "is_selected": True,
        }
        if f.file_type == "data":
            data_files.append(entry)
        elif f.file_type == "template":
            template_files.append(entry)
    return data_files, template_files


class AgentService:
    """Agent 服务封装 - 接入现有 Agent"""

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.coordinator = WorkflowCoordinator(self.config)

    async def _stream_sync_generator(self, gen: Generator) -> AsyncGenerator[str, None]:
        """
        将同步生成器包装为异步生成器，逐项 yield。
        用于在异步上下文中使用 DocumentAgent 的 stream_chat()。
        """
        for item in gen:
            yield item

    async def _get_document_agent(
        self,
        session_id: str,
        content: str,
        files: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        获取缓存的 DocumentAgent 实例，并将消息携带的文件设置到 agent。
        设计：agent 被 session 复用，对话历史累积；文件跟随消息追加到 agent。
        """
        # 获取或创建缓存的 agent 实例
        agent = _get_cached_agent(session_id, self.config)
        
        # 将消息携带的文件设置到 agent（传入 session_id 以便从数据库查询 file_path）
        if files:
            set_agent_files(agent, files, self.config, session_id)
        
        return agent

    async def chat_stream(
        self,
        session_id: str,
        content: str,
        mode: str = "default_conversation",
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
        progress_callback=None,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天响应。
        每次对话都基于当前勾选的文件，支持多轮对话上下文。
        """
        if not mode or not str(mode).strip():
            mode = "default_conversation"
        else:
            mode = str(mode).strip()

        # 默认对话：直连 LLM 流式
        if mode == "default_conversation":
            async for part in self._stream_default_conversation(session_id):
                yield part
            return

        # 文档理解模式：每次都基于当前勾选的文件回答
        if mode == "document_understanding":
            agent = await self._get_document_agent(session_id, content, files)
            async for part in self._stream_sync_generator(agent.stream_chat(content)):
                yield part
            return

        # 实体提取模式：返回完整 JSON（非流式），支持进度回调
        if mode == "entity_extraction":
            import json
            task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)

            # 在后台线程跑阻塞的 coordinator.execute，主 event loop 的轮询负责处理进度
            result = await asyncio.to_thread(
                self.coordinator.execute,
                task_spec,
                progress_callback=progress_callback,
            )
            await asyncio.sleep(0)

            # result.data 是 WorkflowResult，.data 是 AgentResponse，.data.data 才是字典
            agent_response = result.data if result.data else None
            inner_data = agent_response.data if agent_response else {}
            response_data = {
                "success": result.success,
                "message": result.message,
                "entities": inner_data.get("entities") if isinstance(inner_data, dict) else [],
                "schema": inner_data.get("schema") if isinstance(inner_data, dict) else {},
                "chunk_count": inner_data.get("chunk_count") if isinstance(inner_data, dict) else 0,
                "total_extractions": inner_data.get("total_extractions") if isinstance(inner_data, dict) else 0,
            }
            yield json.dumps(response_data, ensure_ascii=False)
            return

        # 其他模式：模拟流式输出
        task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
        result = self.coordinator.execute(task_spec)

        for char in result.message:
            yield char
            await asyncio.sleep(0.005)

    async def chat(
        self,
        session_id: str,
        content: str,
        mode: str = "default_conversation",
        files: Optional[List[Dict[str, Any]]] = None,
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        非流式聊天响应
        """
        if not mode or not str(mode).strip():
            mode = "default_conversation"
        else:
            mode = str(mode).strip()

        # 默认对话
        if mode == "default_conversation":
            return await self._get_conversation_response(session_id)

        # 文档理解模式：每次都基于当前勾选的文件回答
        if mode == "document_understanding":
            agent = await self._get_document_agent(session_id, content, files)
            return agent.chat(content)

        # 其他模式
        task_spec = self._build_task_spec(session_id, mode, content, files or [], template_files)
        result = self.coordinator.execute(task_spec)
        return result.message

    async def _get_conversation_response(self, session_id: str) -> str:
        """获取默认对话的完整回复（非流式）"""
        llm = get_llm_service()
        if not llm.is_available():
            return "LLM 服务不可用，请检查 API Key 配置。"

        # 直接传字典列表，llm.chat 内部会进行转换
        messages = self._build_conversation_llm_messages(session_id)
        return llm.chat(messages=messages)

    def _get_task_type(self, mode: str) -> TaskType:
        """将前端模式转换为 TaskType"""
        mapping = {
            "default_conversation": TaskType.DEFAULT_CONVERSATION,
            "document_understanding": TaskType.DOCUMENT_UNDERSTANDING,
            "document_editing": TaskType.DOCUMENT_EDITING,
            "entity_extraction": TaskType.ENTITY_EXTRACTION,
            "table_filling": TaskType.TABLE_FILLING,
        }
        return mapping.get(mode, TaskType.DEFAULT_CONVERSATION)

    def _get_file_type(self, file_name: str) -> FileType:
        """根据文件名判断文件类型"""
        ext = file_name.lower().split('.')[-1]
        mapping = {
            'pdf': FileType.PDF,
            'doc': FileType.DOCX,
            'docx': FileType.DOCX,
            'xls': FileType.XLSX,
            'xlsx': FileType.XLSX,
            'txt': FileType.TXT,
            'md': FileType.MD,
        }
        return mapping.get(ext, FileType.TXT)

    def _build_file_info(self, file_dict: Dict[str, Any]) -> FileInfo:
        """将文件字典转换为 FileInfo"""
        return FileInfo(
            path=file_dict.get('file_path', ''),
            file_type=self._get_file_type(file_dict.get('file_name', '')),
        )

    def _build_task_spec(
        self,
        session_id: str,
        mode: str,
        content: str,
        files: List[Dict[str, Any]],
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskSpec:
        """构建任务规格"""
        # 获取数据文件
        source_files = [self._build_file_info(f) for f in files if f.get('is_selected', True)]

        # 获取模板文件
        template_file = None
        if template_files:
            selected_templates = [f for f in template_files if f.get('is_selected', True)]
            if selected_templates:
                template_file = self._build_file_info(selected_templates[0])

        return TaskSpec(
            task_type=self._get_task_type(mode),
            instruction=content,
            source_files=source_files,
            template_file=template_file,
            session_id=session_id,
        )

    def _build_conversation_llm_messages(self, session_id: str) -> List[Dict[str, str]]:
        """默认对话：从会话历史构造发给 LLM 的消息列表（含刚写入的用户消息）。"""
        system_prompt = get_config().agent.get_prompt("conversation")
        rows = get_messages(session_id, limit=50, config=self.config)
        msgs: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for r in rows:
            if r.role in ("user", "assistant"):
                msgs.append({"role": r.role, "content": r.content})
        return msgs

    async def _stream_default_conversation(self, session_id: str) -> AsyncGenerator[str, None]:
        """默认对话：真实 LLM 流式输出，保留 Markdown 原文。"""
        llm = get_llm_service()
        if not llm.is_available():
            yield "LLM 服务不可用，请检查 API Key 配置。"
            return

        lc_messages = llm._convert_messages(self._build_conversation_llm_messages(session_id))
        client = ChatOpenAI(
            api_key=llm._get_api_key(),
            base_url=llm._get_base_url(),
            model=llm.config.model,
            temperature=llm.config.temperature,
            max_tokens=llm.config.max_tokens,
            streaming=True,
        )
        def _chunk_to_text(chunk) -> str:
            raw = getattr(chunk, "content", None) or ""
            if isinstance(raw, str):
                return raw
            if isinstance(raw, list):
                parts = []
                for block in raw:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                return "".join(parts)
            return str(raw)

        stream_iter = client.stream(lc_messages)
        while True:
            chunk = await asyncio.to_thread(next, stream_iter, None)
            if chunk is None:
                break
            text = _chunk_to_text(chunk)
            if text:
                yield text

    def execute_task(
        self,
        session_id: str,
        mode: str,
        content: str,
        files: List[Dict[str, Any]],
        template_files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        执行 Agent 任务（非流式）
        """
        task_spec = self._build_task_spec(session_id, mode, content, files, template_files)
        result = self.coordinator.execute(task_spec)

        return {
            "success": result.success,
            "message": result.message,
            "data": result.data,
            "output_file": result.output_file,
        }
