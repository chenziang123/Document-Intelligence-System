"""
任务执行器
负责调用Agent执行具体任务
文档解析由各Agent自行处理（使用外部库如python-docx, pdfplumber等）
"""
from typing import Optional, List, Any, Dict
import importlib

from config import SystemConfig, get_config
from utils.logger import get_logger
from core.orchestrator.task_spec import FileInfo, TaskSpec


class TaskExecutor:
    """
    任务执行器
    封装Agent的调用逻辑
    注意：文档解析由各Agent自行处理，不使用统一的解析器
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.logger = get_logger(__name__)
        self._agents = {}
        self._file_cache: Dict[str, Any] = {}  # 缓存已解析的文件内容

    def get_file_content(self, file_info: FileInfo) -> Any:
        """
        获取文件内容
        由各Agent自行实现具体解析逻辑
        """
        if file_info.path in self._file_cache:
            return self._file_cache[file_info.path]

        self.logger.info(f"读取文件: {file_info.name}")
        # 具体解析逻辑由Agent实现，这里只返回文件路径
        return file_info.path

    def cache_file_content(self, file_path: str, content: Any):
        """缓存文件解析结果"""
        self._file_cache[file_path] = content

    def clear_cache(self):
        """清除文件缓存"""
        self._file_cache.clear()

    def parse_documents(self, source_files: List[FileInfo]) -> Dict[str, str]:
        """解析源文档，返回 file_path -> text 映射。"""
        from utils.document_reader import read_document

        parsed_content: Dict[str, str] = {}
        for file_info in source_files:
            if file_info.path in self._file_cache:
                parsed_content[file_info.path] = self._file_cache[file_info.path]
                continue

            content = read_document(file_info.path)
            parsed_content[file_info.path] = content
            self._file_cache[file_info.path] = content

        return parsed_content

    def execute_agent(
        self,
        agent_name: str,
        task_spec: TaskSpec,
        **kwargs
    ) -> Any:
        """
        执行Agent
        agent_name: agent_a, agent_b, agent_c, agent_d, conversation
        """
        agent = self._get_agent(agent_name)
        if not agent:
            self.logger.error(f"Agent不存在: {agent_name}")
            return None

        try:
            return agent.execute(task_spec, **kwargs)
        except Exception as e:
            self.logger.error(f"Agent执行失败 {agent_name}: {str(e)}")
            return None

    def fill_template(
        self,
        data: Any,
        template: FileInfo
    ) -> str:
        """
        填充模板
        将数据填入指定模板
        """
        self.logger.info(f"填充模板: {template.name}")
        # TODO: 实现模板填充逻辑
        return ""

    def _get_parser(self, file_type: str):
        """
        获取对应的解析器
        注意：此方法已废弃，解析逻辑由各Agent自行处理
        """
        self.logger.warning(f"解析器已废弃，请使用各Agent自带的解析功能")
        return None

    def _get_agent(self, agent_name: str):
        """获取对应的Agent"""
        if agent_name in self._agents:
            return self._agents[agent_name]

        agent_map = {
            "agent_a": "core.agents.agent_a.AgentA",
            "agent_b": "core.agents.agent_b.AgentB",
            "agent_c": "core.agents.agent_c.AgentC",
            "agent_d": "core.agents.agent_d.AgentD",
            "conversation": "core.agents.conversation_agent.ConversationAgent",
            "document_understanding": "core.agents.document_understand_agent.DocumentAgent",
        }

        agent_config = agent_map.get(agent_name)
        if not agent_config:
            return None

        try:
            # 分离模块路径和类名
            module_path, class_name = agent_config.rsplit(".", 1)
            if agent_name == "conversation":
                class_name = "ConversationAgent"
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            agent = agent_class(self.config)
            self._agents[agent_name] = agent
            return agent
        except Exception as e:
            self.logger.error(f"加载Agent失败 {agent_name}: {str(e)}")
            return None
