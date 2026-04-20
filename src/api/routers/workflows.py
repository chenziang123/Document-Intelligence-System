"""
Workflow API 路由
支持前端工作流节点的执行调度，逐文件处理。

端点：
  POST /api/workflows/execute        启动执行，返回 execution_id
  GET  /api/workflows/executions/{id}  查询执行状态
  GET  /api/workflows/templates       获取工作流模板列表
  GET  /api/workflows/templates/{id}  获取指定模板
  GET  /api/workflows                获取用户工作流列表
  POST /api/workflows                保存工作流（新建或更新）
  DELETE /api/workflows/{id}         删除工作流
  GET  /api/workflows/{id}           获取单个工作流完整配置
  GET  /api/workflows/models         获取可用 LLM 模型
  GET  /api/workflows/languages      获取支持的目标语言
  GET  /api/workflows/output-formats  获取支持的输出格式
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from config import SystemConfig, get_config
from core.orchestrator.coordinator import WorkflowCoordinator
from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType
from core.storage import build_blob_name, upload_file_to_storage
from db.auth_repository import resolve_user_from_authorization
from db.session_repository import add_session_file, get_session_by_id
from utils.logger import get_logger
from workflow_storage import delete_workflow, get_workflow, list_workflows, save_workflow
from .workflows_processors import _process_node

router = APIRouter(prefix="/api/workflows", tags=["工作流编排"])
logger = get_logger(__name__)

# ==================== 执行状态存储（进程内内存） ====================
# key: execution_id, value: state dict
_EXECUTION_STATES: Dict[str, dict] = {}

# ==================== Request / Response 模型 ====================


class WorkflowNode(BaseModel):
    id: str
    type: str
    title: str
    configValues: Dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    workflowId: str = Field(..., description="工作流 ID")
    nodes: List[WorkflowNode] = Field(default_factory=list, description="工作流节点配置")
    docs: List[str] = Field(default_factory=list, description="文档库文档 ID 列表")
    localFiles: List[Dict[str, Any]] = Field(
        default_factory=list, description="本地上传文件 [{name, size, content(base64)}]"
    )
    sessionId: Optional[str] = Field(None, description="会话 ID（可选）")


class ExecutionResponse(BaseModel):
    execution_id: str
    status: str
    progress: int = 0
    current_file_index: int = 0
    total_files: int = 0
    current_file_name: str = ""
    logs: List[Dict[str, str]] = Field(default_factory=list)
    output_files: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    nodes: List[Dict[str, Any]]


# ==================== 辅助函数 ====================


def _get_output_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取输出节点配置。"""
    for node in nodes:
        if node.type == "output":
            return node.configValues or {}
    return {}


def _get_translation_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取翻译/AI节点配置。"""
    for node in nodes:
        if node.type in ("translate", "ai"):
            return node.configValues or {}
    return {"targetLanguage": "中文"}


def _get_processing_nodes(nodes: List[WorkflowNode]) -> List[WorkflowNode]:
    """从节点列表中提取所有处理节点（排除输入/输出节点）。"""
    processing = []
    for node in nodes:
        if node.type not in ("input", "output"):
            processing.append(node)
    return processing


# 语言 code → 人类可读名称映射
_LANG_MAP = {
    "en": "英语", "zh": "中文", "ja": "日语", "ko": "韩语",
    "fr": "法语", "de": "德语", "es": "西班牙语", "ru": "俄语",
    "ar": "阿拉伯语", "pt": "葡萄牙语", "it": "意大利语",
    "zh-CN": "简体中文", "zh-TW": "繁体中文",
}


def _normalize_lang(code_or_label: str) -> str:
    """把语言 code 或 label 统一转为 label。"""
    if code_or_label in _LANG_MAP.values():
        return code_or_label
    return _LANG_MAP.get(code_or_label, code_or_label)


def _resolve_doc_path(doc_id: str, config: SystemConfig) -> Optional[str]:
    """根据文档 ID 解析磁盘路径，支持 session 文件和文档库文件。"""
    from db.library_repository import get_library_doc_by_id

    # 文档库文档
    doc = get_library_doc_by_id(doc_id, config=config, user_id=None)
    if doc and doc.storage_key:
        p = Path(doc.storage_key)
        if p.exists():
            return str(p)

    # session 文件
    parts = doc_id.split(":", 1)
    if len(parts) == 2 and parts[0] == "session":
        session_id, file_id = parts[1].split("/", 1)
        try:
            session = get_session_by_id(session_id, config=config)
            if session:
                for row in getattr(session, "files", []):
                    if str(row.id) == file_id:
                        p = Path(row.file_path)
                        if p.exists():
                            return str(p)
        except Exception:
            pass

    # 尝试 workspace 目录
    workspace_root = Path(config.work_dir)
    candidates = [
        workspace_root / doc_id,
        workspace_root / "uploads" / doc_id,
        workspace_root / "documents" / doc_id,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return str(p)
    return None


def _detect_file_type(name: str) -> FileType:
    """根据文件名推断 FileType。"""
    ext = Path(name).suffix.lower().lstrip(".")
    mapping = {
        "docx": FileType.DOCX,
        "pdf": FileType.PDF,
        "txt": FileType.TXT,
        "md": FileType.MD,
        "markdown": FileType.MD,
        "xlsx": FileType.XLSX,
        "xls": FileType.XLS,
        "csv": FileType.CSV,
        "doc": FileType.DOC,
    }
    return mapping.get(ext, FileType.TXT)


def _make_progress_callback(execution_id: str):
    """生成一个向执行状态写入进度日志的回调。"""

    def callback(progress: int, total: int, message: str):
        if execution_id not in _EXECUTION_STATES:
            return
        state = _EXECUTION_STATES[execution_id]
        state["progress"] = max(state["progress"], int(progress / max(total, 1) * 100))
        state["logs"].append({"type": "info", "message": message})

    return callback


async def _run_execution(execution_id: str, params: ExecuteRequest):
    """
    后台执行任务：逐文件处理，支持本地文件和文档库文件。
    在 asyncio.to_thread 中运行，不阻塞事件循环。
    """
    config = get_config()
    state = _EXECUTION_STATES.get(execution_id)
    if not state:
        return

    try:
        output_config = _get_output_config(params.nodes)
        output_mode = output_config.get("outputMode", "download")
        output_format = output_config.get("outputFormat", "md")
        target_space_id = output_config.get("targetSpaceId")
        naming_rule = output_config.get("namingRule", "{original_name}_out")

        translation_config = _get_translation_config(params.nodes)
        target_language = _normalize_lang(translation_config.get("targetLanguage", "中文"))

        # ===== 保存本地文件到磁盘 =====
        saved_local_files: List[Dict[str, Any]] = []  # [{path, name, size}]
        if params.localFiles:
            state["logs"].append({"type": "info", "message": f"正在上传 {len(params.localFiles)} 个本地文件..."})
            for lf in params.localFiles:
                name = lf.get("name", "unknown")
                content_bytes = lf.get("content") or lf.get("data")
                if not content_bytes:
                    state["logs"].append({"type": "warn", "message": f"  文件内容为空: {name}"})
                    continue
                if isinstance(content_bytes, str):
                    import base64 as _b64
                    try:
                        content_bytes = _b64.b64decode(content_bytes)
                    except Exception:
                        # 不是 base64，当作普通文本
                        content_bytes = content_bytes.encode("utf-8")
                upload_dir = Path(config.temp_dir) / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                safe_name = Path(name).name
                file_path = upload_dir / safe_name
                file_path.write_bytes(content_bytes)
                saved_local_files.append({
                    "path": str(file_path),
                    "name": name,
                    "size": len(content_bytes),
                })
                state["logs"].append({"type": "done", "message": f"  已保存: {name}"})

        # ===== 收集源文件列表 =====
        source_files: List[FileInfo] = []

        # 从文档库
        for doc_id in params.docs:
            path = _resolve_doc_path(doc_id, config)
            if path:
                ft = _detect_file_type(Path(path).name)
                source_files.append(FileInfo(path=path, file_type=ft, name=Path(path).name))
            else:
                state["logs"].append({"type": "warn", "message": f"文档路径未找到: {doc_id}"})

        # 从本地文件（已保存到磁盘）
        for lf in saved_local_files:
            ft = _detect_file_type(lf["name"])
            source_files.append(
                FileInfo(path=lf["path"], file_type=ft, name=lf["name"], metadata={"local": True, "size": lf["size"]})
            )

        # 也处理未上传的本地占位（跳过）
        for lf in params.localFiles:
            name = lf.get("name", "unknown")
            if not any(sf.name == name for sf in source_files):
                state["logs"].append({"type": "warn", "message": f"本地文件未上传，跳过: {name}"})

        if not source_files:
            state["status"] = "failed"
            state["error"] = "没有可处理的文件"
            state["logs"].append({"type": "error", "message": "没有可处理的文件"})
            return

        state["total_files"] = len(source_files)
        state["logs"].append({"type": "info", "message": f"共 {len(source_files)} 个文件，开始逐个处理..."})

        # ===== 逐文件处理 =====
        all_output_files: List[Dict[str, Any]] = []
        ext = output_format or "md"

        for idx, file_info in enumerate(source_files):
            state["current_file_index"] = idx + 1
            state["current_file_name"] = file_info.name
            state["progress"] = int(idx / len(source_files) * 100)
            state["logs"].append(
                {"type": "info", "message": f"[{idx + 1}/{len(source_files)}] 正在处理: {file_info.name}"}
            )

            if not file_info.path or not Path(file_info.path).exists():
                state["logs"].append({"type": "warn", "message": f"  跳过（文件不存在）: {file_info.name}"})
                continue

            # 构建输出路径
            out_name = naming_rule.replace("{original_name}", Path(file_info.path).stem)
            if not out_name.endswith(f".{ext}"):
                out_name += f".{ext}"
            out_path = Path(config.output_dir) / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # 读取源文件内容
            state["logs"].append({"type": "info", "message": f"  读取文件..."})
            try:
                from utils.document_reader import read_document
                content = read_document(file_info.path)
            except Exception as e:
                logger.warning(f"文档解析失败 {file_info.path}: {e}")
                content = None

            if not content:
                state["logs"].append({"type": "warn", "message": f"  无法读取文件内容，跳过: {file_info.name}"})
                continue

            # ===== 处理流水线（支持多个处理节点） =====
            processing_nodes = _get_processing_nodes(params.nodes)
            result_content = content
            
            for proc_node in processing_nodes:
                node_name = proc_node.title or proc_node.type
                state["logs"].append({"type": "info", "message": f"  {node_name} 处理中..."})
                try:
                    result_content = _process_node(result_content, file_info.name, proc_node, config, state)
                except Exception as e:
                    logger.error(f"处理失败 {file_info.name} ({node_name}): {e}")
                    state["logs"].append({"type": "error", "message": f"  {node_name} 失败: {e}"})
                    result_content = None
                    break
                
                if not result_content:
                    state["logs"].append({"type": "error", "message": f"  {node_name} 结果为空，跳过: {file_info.name}"})
                    break
            
            if not result_content:
                state["logs"].append({"type": "error", "message": f"  处理流水线完成但无有效结果，跳过: {file_info.name}"})
                continue
            
            translated = result_content

            # 保存输出文件
            try:
                # 推导正确的文件后缀和 MIME 类型
                fmt_ext = output_format  # md | txt | pdf
                if fmt_ext not in ("md", "txt", "pdf"):
                    fmt_ext = "md"
                ext = f".{fmt_ext}"
                mime_map = {"pdf": "application/pdf", "md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8"}
                mime_type = mime_map.get(fmt_ext, "text/plain; charset=utf-8")

                # 文件名（按 naming_rule，但保持对应后缀）
                out_name = naming_rule.replace("{original_name}", Path(file_info.path).stem)
                if not out_name.endswith(ext):
                    out_name = out_name + ext
                out_path = Path(config.output_dir) / out_name
                out_path.parent.mkdir(parents=True, exist_ok=True)

                # 生成文件内容
                if fmt_ext == "pdf":
                    from utils.pdf_generator import text_to_pdf
                    state["logs"].append({"type": "info", "message": f"  生成 PDF..."})
                    text_to_pdf(translated, str(out_path), title=out_name)
                else:
                    out_path.write_text(translated, encoding="utf-8")

                file_size = out_path.stat().st_size

                # 上传到 Blob Storage（无论哪种输出模式都上传）
                blob_name = None
                if config.storage.enabled and config.storage.provider == "azure_blob":
                    from core.storage import upload_file_to_storage, build_blob_name
                    try:
                        blob_name = upload_file_to_storage(
                            out_path,
                            config=config,
                            blob_name=build_blob_name(
                                execution_id,
                                out_path.name,
                                prefix=config.storage.azure_blob_prefix or "workflows",
                            ),
                            content_type=mime_type,
                        )
                        logger.info(f"已上传到 Blob: {blob_name}")
                    except Exception as blob_err:
                        logger.warning(f"Blob 上传失败: {blob_err}")

                all_output_files.append({
                    "name": out_path.name,
                    "path": str(out_path),
                    "blob_name": blob_name,
                    "size": file_size,
                    "source": file_info.name,
                })
                state["logs"].append({"type": "done", "message": f"  已保存: {out_path.name} ({fmt_ext.upper()})"})

                # 保存到文档库
                if output_mode == "library" and target_space_id:
                    _save_output_to_library(str(out_path), target_space_id, config)
                    state["logs"].append({"type": "done", "message": f"  已保存到文档库: {out_path.name}"})
            except Exception as e:
                logger.error(f"保存文件失败 {out_path}: {e}")
                state["logs"].append({"type": "error", "message": f"  保存失败: {e}"})

        # ===== 完成 =====
        state["status"] = "completed"
        state["progress"] = 100
        state["output_files"] = all_output_files
        state["logs"].append({"type": "done", "message": f"全部完成，已处理 {len(all_output_files)} 个输出文件"})

    except Exception as e:
        logger.error(f"执行任务异常: {e}")
        state["status"] = "failed"
        state["error"] = str(e)
        state["logs"].append({"type": "error", "message": f"执行异常: {e}"})


def _save_output_to_library(file_path: str, space_id: str, config: SystemConfig):
    """将输出文件保存到文档库。"""
    try:
        from db.library_repository import add_library_doc
        from pathlib import Path
        import hashlib

        p = Path(file_path)
        with open(p, "rb") as f:
            content_bytes = f.read()
        file_size = len(content_bytes)
        file_hash = hashlib.md5(content_bytes).hexdigest()
        safe_name = f"{file_hash}_{p.name}"

        storage_key = None
        if config.storage.enabled and config.storage.provider == "azure_blob":
            from core.storage import build_blob_name, upload_stream_to_storage
            from io import BytesIO
            blob_name = build_blob_name(space_id, safe_name, prefix=config.storage.azure_blob_prefix)
            storage_key = upload_stream_to_storage(
                BytesIO(content_bytes), config=config, blob_name=blob_name,
                content_type="application/octet-stream",
            )
        else:
            upload_dir = Path("workspace/library") / space_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            storage_key = str(upload_dir / safe_name)
            with open(storage_key, "wb") as f:
                f.write(content_bytes)

        add_library_doc(
            space_id=space_id,
            file_name=p.name,
            file_size=file_size,
            config=config,
            user_id=None,
            mime_type="application/octet-stream",
            storage_key=storage_key,
            blob_url=storage_key,
        )
    except Exception as e:
        logger.warning(f"保存到文档库失败: {e}")


# ==================== API 端点 ====================

# ⚠️ 路由顺序很重要：精确路径必须在动态路径 {workflow_id} 之前注册


@router.post("/execute", response_model=Dict[str, str])
async def execute_workflow(request: ExecuteRequest, background_tasks: BackgroundTasks):
    """
    启动工作流执行（逐文件处理）。
    立即返回 execution_id，前端通过 GET /executions/{id} 轮询进度。
    """
    execution_id = uuid.uuid4().hex

    _EXECUTION_STATES[execution_id] = {
        "status": "running",
        "progress": 0,
        "current_file_index": 0,
        "total_files": 0,
        "current_file_name": "",
        "logs": [{"type": "info", "message": "任务已启动，正在初始化..."}],
        "output_files": [],
        "error": None,
    }

    # 后台运行，不阻塞 HTTP 响应
    background_tasks.add_task(_run_execution, execution_id, request)

    return {"execution_id": execution_id}


# -------- 精确路径端点（必须在 /{workflow_id} 之前） --------


@router.get("/templates")
async def list_templates():
    """返回内置工作流模板列表（节点含 schemaKey + configValues 默认值）。"""
    return {"templates": [
        {
            "id": "translate-pdf",
            "name": "PDF 翻译",
            "description": "将 PDF 文件翻译为目标语言",
            "nodes": [
                {
                    "id": "n_pdf_input",
                    "type": "input",
                    "title": "PDF 输入",
                    "icon": "📕",
                    "body": "导入 PDF 文件",
                    "schemaKey": "schema-pdf-input",
                    "configValues": {
                        "inputSource": "library",
                        "spaceId": None,
                        "skipExisting": False,
                    }
                },
                {
                    "id": "n_ai_translate",
                    "type": "ai",
                    "title": "AI 翻译",
                    "icon": "🌍",
                    "body": "使用大模型进行智能翻译处理",
                    "schemaKey": "schema-translate",
                    "configValues": {
                        "targetLanguage": "en",
                        "prompt": "请将此文档翻译为指定语言，保持原文格式和专业术语的准确性。",
                    }
                },
                {
                    "id": "n_output",
                    "type": "output",
                    "title": "输出文件",
                    "icon": "📁",
                    "body": "保存结果到文档库或直接下载",
                    "schemaKey": "schema-library-output",
                    "configValues": {
                        "outputMode": "download",
                        "targetSpaceId": None,
                        "namingRule": "{original_name}_translated",
                        "outputFormat": "pdf",
                        "notifyOnComplete": True,
                    }
                },
            ],
        },
        {
            "id": "translate-docx",
            "name": "Word 翻译",
            "description": "将 Word 文档翻译为目标语言",
            "nodes": [
                {
                    "id": "n_docx_input",
                    "type": "input",
                    "title": "DOCX 输入",
                    "icon": "📘",
                    "body": "导入 Word 文档",
                    "schemaKey": "schema-docx-input",
                    "configValues": {
                        "inputSource": "library",
                        "spaceId": None,
                        "skipExisting": False,
                    }
                },
                {
                    "id": "n_ai_translate",
                    "type": "ai",
                    "title": "AI 翻译",
                    "icon": "🌍",
                    "body": "使用大模型进行智能翻译处理",
                    "schemaKey": "schema-translate",
                    "configValues": {
                        "targetLanguage": "en",
                        "prompt": "请将此文档翻译为指定语言，保持原文格式和专业术语的准确性。",
                    }
                },
                {
                    "id": "n_output",
                    "type": "output",
                    "title": "输出文件",
                    "icon": "📁",
                    "body": "保存结果到文档库或直接下载",
                    "schemaKey": "schema-library-output",
                    "configValues": {
                        "outputMode": "download",
                        "targetSpaceId": None,
                        "namingRule": "{original_name}_translated",
                        "outputFormat": "docx",
                        "notifyOnComplete": True,
                    }
                },
            ],
        },
    ]}


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str):
    """获取指定模板的完整配置。"""
    templates = await list_templates()
    for t in templates:
        if t["id"] == template_id:
            return t
    raise HTTPException(status_code=404, detail="模板不存在")


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution_status(execution_id: str):
    """查询工作流执行状态。"""
    state = _EXECUTION_STATES.get(execution_id)
    if not state:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return ExecutionResponse(
        execution_id=execution_id,
        status=state["status"],
        progress=state["progress"],
        current_file_index=state["current_file_index"],
        total_files=state["total_files"],
        current_file_name=state["current_file_name"],
        logs=state["logs"],
        output_files=state["output_files"],
        error=state["error"],
    )


@router.get("/models", response_model=List[Dict[str, str]])
async def list_models():
    """返回可用 LLM 模型列表。"""
    return [
        {"id": "deepseek-chat", "name": "DeepSeek Chat"},
        {"id": "gpt-4o", "name": "GPT-4o"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "claude-3-5-sonnet", "name": "Claude 3.5 Sonnet"},
    ]


@router.get("/languages", response_model=List[Dict[str, str]])
async def list_languages():
    """返回支持的目标语言列表。"""
    return [
        {"code": "zh", "name": "中文"},
        {"code": "en", "name": "English"},
        {"code": "ja", "name": "日本語"},
        {"code": "ko", "name": "한국어"},
        {"code": "fr", "name": "Français"},
        {"code": "de", "name": "Deutsch"},
        {"code": "es", "name": "Español"},
        {"code": "ru", "name": "Русский"},
        {"code": "ar", "name": "العربية"},
        {"code": "pt", "name": "Português"},
    ]


@router.get("/output-formats", response_model=List[Dict[str, str]])
async def list_output_formats():
    """返回支持的输出格式列表。"""
    return [
        {"code": "pdf", "name": "PDF"},
        {"code": "md", "name": "Markdown"},
        {"code": "txt", "name": "纯文本"},
    ]


# -------- 用户工作流 CRUD（/{workflow_id} 必须在最后） --------


class SaveWorkflowRequest(BaseModel):
    id: str = Field(..., description="工作流 ID（唯一标识，新建时由前端生成）")
    name: str = Field(..., description="工作流名称")
    icon: str = Field("🔧", description="图标 emoji")
    type: str = Field("custom", description="类型（custom/template）")
    nodes: List[Dict[str, Any]] = Field(
        default_factory=list, description="节点列表（含 configValues 等完整配置）"
    )
    config: Dict[str, Any] = Field(default_factory=dict, description="全局配置")


@router.get("", response_model=Dict[str, Any])
async def list_user_workflows():
    """返回用户自定义工作流列表（不含模板）。"""
    return {"workflows": list_workflows()}


@router.post("", response_model=Dict[str, Any])
async def save_user_workflow(request: SaveWorkflowRequest):
    """保存（新建或更新）用户工作流。"""
    if request.type == "template":
        raise HTTPException(status_code=400, detail="模板工作流不可通过此接口保存")
    wf = save_workflow(
        workflow_id=request.id,
        name=request.name,
        icon=request.icon,
        nodes=request.nodes,
        config_data=request.config,
    )
    return wf


@router.get("/{workflow_id}", response_model=Dict[str, Any])
async def get_single_workflow(workflow_id: str):
    """获取指定工作流的完整配置（含节点和 config）。"""
    wf = get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf


@router.delete("/{workflow_id}", response_model=Dict[str, bool])
async def delete_user_workflow(workflow_id: str):
    """删除指定用户工作流。"""
    success = delete_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="工作流不存在或为模板工作流")
    return True
