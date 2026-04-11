"""
工作流协调器
核心编排模块，根据任务类型选择并执行对应工作流
"""
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
import json
from datetime import datetime
from pathlib import Path

from .task_spec import TaskSpec, TaskType, FileInfo
from .executor import TaskExecutor
from config import SystemConfig, get_config
from db.workflow_persistence import (
    persist_workflow_execute_begin,
    persist_workflow_execute_end,
)
from output.result_handler import ResultHandler
from utils.logger import get_logger


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    success: bool
    message: str
    data: Optional[Any] = None
    output_file: Optional[str] = None
    # 交互式 Agent 实例（用于文档理解模式）
    interactive_agent: Optional[Any] = None
    # 源文件列表
    source_files: Optional[List[Any]] = None


class WorkflowCoordinator:
    """
    工作流协调器
    负责路由和管理不同类型任务的执行流程
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.logger = get_logger(__name__)
        self.executor = TaskExecutor(self.config)
        self.result_handler = ResultHandler(self.config.output_dir)
        self._workflow_handlers: Dict[TaskType, Callable] = {}
        self._register_workflows()
        # 保存 DocumentAgent 实例供交互式对话使用
        self._document_agent_instance = None

    def _register_workflows(self):
        """注册所有工作流处理器"""
        self._workflow_handlers = {
            TaskType.DEFAULT_CONVERSATION: self._default_conversation_flow,
            TaskType.DOCUMENT_UNDERSTANDING: self._document_understanding_flow,
            TaskType.DOCUMENT_EDITING: self._document_editing_flow,
            TaskType.ENTITY_EXTRACTION: self._entity_extraction_flow,
            TaskType.TABLE_FILLING: self._table_filling_flow,
        }

    def execute(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        执行工作流
        根据任务规格选择对应的工作流并执行
        """
        self.logger.info(f"开始执行任务: {task_spec.task_type.value}")

        # 验证任务规格
        is_valid, error_msg = task_spec.validate()
        if not is_valid:
            self.logger.error(f"任务规格验证失败: {error_msg}")
            return WorkflowResult(success=False, message=error_msg)

        persist_workflow_execute_begin(task_spec, self.config)

        handler = self._workflow_handlers.get(task_spec.task_type)
        if not handler:
            msg = f"不支持的任务类型: {task_spec.task_type.value}"
            persist_workflow_execute_end(task_spec, False, msg, self.config)
            return WorkflowResult(success=False, message=msg)

        try:
            result = handler(task_spec, progress_callback=progress_callback)
            persist_workflow_execute_end(
                task_spec, result.success, result.message, self.config
            )
            return result
        except Exception as e:
            self.logger.error(f"工作流执行失败: {str(e)}")
            persist_workflow_execute_end(task_spec, False, str(e), self.config)
            return WorkflowResult(success=False, message=f"执行失败: {str(e)}")

    def _default_conversation_flow(self, task_spec: TaskSpec) -> WorkflowResult:
        """
        默认对话模式
        直接与LLM交流，查询系统信息
        """
        self.logger.info("进入默认对话模式")

        result = self.executor.execute_agent(
            agent_name="conversation",
            task_spec=task_spec
        )

        return WorkflowResult(
            success=True,
            message=result.message,
            data=result
        )

    def _document_understanding_flow(self, task_spec: TaskSpec) -> WorkflowResult:
        """
        文档理解模式
        1. 初始化 DocumentAgent
        2. 设置文档（如果有）
        3. 返回可交互的 Agent 实例供 CLI 使用
        """
        self.logger.info("进入文档理解模式")

        # 获取 DocumentAgent 实例
        agent = self.executor._get_agent("document_understanding")
        if not agent:
            return WorkflowResult(
                success=False,
                message="DocumentAgent 初始化失败"
            )

        # 设置文档（如果有）
        if task_spec.source_files:
            agent.set_documents(task_spec.source_files)
            file_names = [f.name for f in task_spec.source_files]
        else:
            file_names = []

        # 保存实例供交互式对话使用
        self._document_agent_instance = agent

        return WorkflowResult(
            success=True,
            message="文档理解 Agent 已就绪，可以开始对话",
            data={"status": "ready", "files": file_names},
            interactive_agent=agent,
            source_files=task_spec.source_files or []
        )

    def _document_editing_flow(self, task_spec: TaskSpec) -> WorkflowResult:
        """
        文档编辑模式
        1. 解析文档
        2. Agent_A 按要求编辑文档
        """
        self.logger.info("进入文档编辑模式")

        # 1. 解析文档
        parsed_content = self.executor.parse_documents(task_spec.source_files)

        # 2. Agent_A 编辑文档
        task_spec.parameters["parsed_content"] = parsed_content
        result = self.executor.execute_agent(
            agent_name="agent_a",
            task_spec=task_spec,
            mode="editing"
        )

        return WorkflowResult(
            success=True,
            message="文档编辑完成",
            data=result,
            output_file=task_spec.output_file
        )

    def _entity_extraction_flow(self, task_spec: TaskSpec, progress_callback=None) -> WorkflowResult:
        """
        实体提取模式
        1. 解析文档
        2. Agent_B 提取实体数据为JSON
        3. 将数据填入模板
        4. 可选存入数据库
        """
        self.logger.info("进入实体提取模式")

        # 文档解析完毕后立即通知前端，让用户知道任务已启动
        if progress_callback:
            progress_callback(0, 1, "文档解析完成，开始提取...")

        # 1. 解析非结构化文档
        parsed_content = self.executor.parse_documents(task_spec.source_files)

        # 2. Agent_B 提取实体（带进度回调）
        task_spec.parameters["parsed_content"] = parsed_content
        extracted_data = self.executor.execute_agent(
            agent_name="agent_b",
            task_spec=task_spec,
            progress_callback=progress_callback,
        )

        if not extracted_data or not getattr(extracted_data, "success", False):
            err_msg = getattr(extracted_data, "message", "实体提取失败")
            return WorkflowResult(success=False, message=err_msg, data=extracted_data)

        output_filename = (
            Path(task_spec.output_file).name
            if task_spec.output_file
            else f"entity_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        saved_path = self.result_handler.save_json(
            data=getattr(extracted_data, "data", {}),
            filename=output_filename,
        )
        if saved_path:
            extracted_data.metadata = extracted_data.metadata or {}
            extracted_data.metadata["saved_path"] = saved_path
            extracted_data.message = f"{extracted_data.message}，结果已保存到: {saved_path}"

        # 3. 填入模板
        if task_spec.template_file:
            filled_template = self.executor.fill_template(
                data=extracted_data,
                template=task_spec.template_file
            )

            return WorkflowResult(
                success=True,
                message="实体提取完成",
                data=extracted_data,
                output_file=saved_path or task_spec.output_file
            )

        return WorkflowResult(
            success=True,
            message="实体提取完成",
            data=extracted_data,
            output_file=saved_path or task_spec.output_file,
        )

    def _table_filling_flow(self, task_spec: TaskSpec) -> WorkflowResult:
        """
        表格填表模式
        1. Agent_D 筛选Excel数据
        2. 填入表格模板
        """
        self.logger.info("进入表格填表模式")

        # Agent_D 处理表格
        result = self.executor.execute_agent(
            agent_name="agent_d",
            task_spec=task_spec
        )

        return WorkflowResult(
            success=True,
            message="表格填表完成",
            data=result,
            output_file=task_spec.output_file
        )

    def get_available_workflows(self) -> Dict[str, str]:
        """获取所有可用的工作流"""
        return {
            TaskType.DEFAULT_CONVERSATION.value: "默认对话模式 - 与AI自由交流",
            TaskType.DOCUMENT_UNDERSTANDING.value: "文档理解模式 - 解析并理解文档内容",
            TaskType.DOCUMENT_EDITING.value: "文档编辑模式 - 按要求编辑Word文档",
            TaskType.ENTITY_EXTRACTION.value: "实体提取模式 - 从文档中提取数据填入模板",
            TaskType.TABLE_FILLING.value: "表格填表模式 - 从Excel筛选数据填入表格",
        }
