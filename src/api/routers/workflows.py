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
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field

from config import SystemConfig, get_config
from utils.workflow_paths import resolve_workflow_output_path
from core.orchestrator.coordinator import WorkflowCoordinator
from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType
from core.storage import build_blob_name, upload_file_to_storage, oss_storage_enabled
from db.auth_repository import resolve_user_from_authorization
from db.connection import is_database_configured
from db.workflow_repository import db_load_execution_states, db_save_execution_states, is_db_enabled
from db.session_repository import add_session_file, get_session_by_id
from utils.logger import get_logger
from workflow_storage import delete_workflow, get_workflow, list_workflows, save_workflow

router = APIRouter(prefix="/api/workflows", tags=["工作流编排"])
logger = get_logger(__name__)

# ==================== 执行状态存储（进程内内存） ====================
# key: execution_id, value: state dict
_EXECUTION_STATES: Dict[str, dict] = {}


def _execution_states_file(config: Optional[SystemConfig] = None) -> Path:
    cfg = config or get_config()
    state_dir = Path(cfg.work_dir) / "workflows"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "execution_states.json"


def _load_execution_states(config: Optional[SystemConfig] = None) -> Dict[str, dict]:
    cfg = config or get_config()
    if is_db_enabled(cfg):
        loaded = db_load_execution_states(cfg)
        if loaded:
            return loaded

    path = _execution_states_file(config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning(f"加载工作流执行状态失败: {exc}")
    return {}


def _persist_execution_states(config: Optional[SystemConfig] = None) -> None:
    cfg = config or get_config()
    if is_db_enabled(cfg):
        if db_save_execution_states(_EXECUTION_STATES, cfg):
            return

    path = _execution_states_file(config)
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps(_EXECUTION_STATES, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception as exc:
        logger.warning(f"持久化工作流执行状态失败: {exc}")
        if tmp_path.exists():
            tmp_path.unlink()


_EXECUTION_STATES.update(_load_execution_states())

# ==================== Request / Response 模型 ====================


class WorkflowNode(BaseModel):
    id: str
    type: str
    title: str
    schemaKey: Optional[str] = None
    configValues: Dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    workflowId: str = Field(..., description="工作流 ID")
    nodes: List[WorkflowNode] = Field(default_factory=list, description="工作流节点配置")
    docs: List[str] = Field(default_factory=list, description="文档库文档 ID 列表")
    localFiles: List[Dict[str, Any]] = Field(
        default_factory=list, description="本地上传文件 [{name, size, content(base64)}]"
    )
    sessionId: Optional[str] = Field(None, description="会话 ID（可选）")
    runSettings: Dict[str, Any] = Field(
        default_factory=dict,
        description="运行设置：concurrentLimit、continueOnError、notifyOnError",
    )
    workflowEdges: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="画布连线 [{id, from, to, label}]，空则按节点顺序链式执行",
    )


class ExecutionResponse(BaseModel):
    execution_id: str
    status: str
    progress: int = 0
    current_file_index: int = 0
    total_files: int = 0
    current_file_name: str = ""
    current_node_id: str = ""
    current_node_name: str = ""
    current_node_index: int = 0
    total_nodes: int = 0
    node_progress: List[Dict[str, Any]] = Field(default_factory=list)
    logs: List[Dict[str, str]] = Field(default_factory=list)
    output_files: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    nodes: List[Dict[str, Any]]


# ==================== 辅助函数 ====================


def _get_output_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取输出节点配置。优先「输出文件/文档库」节点，否则用第一个输出节点。"""
    first_output: Dict[str, Any] = {}
    for node in nodes:
        if node.type != "output":
            continue
        cv = dict(node.configValues or {})
        cv["_schemaKey"] = node.schemaKey
        if node.schemaKey == "schema-save-excel":
            cv.setdefault("outputFormat", "xlsx")
        elif node.schemaKey == "schema-save-text":
            cv.setdefault("outputFormat", "txt")
        if not first_output:
            first_output = cv
        # 画布上可能存在多个输出型节点时的歧义处理
        if node.schemaKey == "schema-library-output":
            return cv
        if node.schemaKey in {"schema-save-excel", "schema-save-text"}:
            return cv
    return first_output


def _get_input_config(nodes: List[WorkflowNode]) -> Dict[str, Any]:
    """从节点列表中提取输入节点配置。"""
    for node in nodes:
        if node.type == "input":
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


def _build_node_progress(nodes: List[WorkflowNode]) -> List[Dict[str, Any]]:
    progress_items: List[Dict[str, Any]] = []
    for idx, node in enumerate(nodes, start=1):
        progress_items.append(
            {
                "id": node.id,
                "title": node.title,
                "type": node.type,
                "schemaKey": node.schemaKey,
                "index": idx,
                "status": "pending",
                "progress": 0,
                "message": "",
            }
        )
    return progress_items


# 节点配置字段中文名（校验报错展示用）
_CONFIG_FIELD_LABELS = {
    "processKind": "处理类型",
    "sortColumn": "排序列",
    "sortOrder": "升降序",
    "filterExpr": "筛选条件",
    "aggregateColumn": "汇总列",
    "aggregateOp": "汇总方式",
    "fillColumns": "填充列",
    "computedColumnName": "新列名",
    "computedFormula": "计算表达式",
    "mergeSourceColumns": "待合并列",
    "mergeTargetColumn": "目标列名",
    "splitSourceColumn": "待拆分列",
    "splitIntoColumns": "拆成列名",
    "cleanRules": "清洗规则",
    "tableStrategy": "提取策略",
    "tableIndex": "表格序号",
    "sheetName": "工作表名",
    "outputEncoding": "输出编码",
    "lineEnding": "换行符",
}


def _label_config_fields(keys: List[str]) -> str:
    return "、".join(_CONFIG_FIELD_LABELS.get(k, k) for k in keys)


def _validate_execute_request(request: ExecuteRequest) -> List[str]:
    errors: List[str] = []
    for idx, node in enumerate(request.nodes, start=1):
        schema_key = str(node.schemaKey or "").strip()
        cv = node.configValues or {}
        title = node.title or schema_key or f"第{idx}个节点"

        if schema_key == "schema-data-process":
            process_kind = str(cv.get("processKind") or "").strip()
            if process_kind not in {"sort", "filter", "aggregate", "dedupe", "fill_null", "computed_column", "merge_columns", "split_column"}:
                errors.append(f"{title}：处理类型配置无效")
            required_by_kind = {
                "sort": ["sortColumn"],
                "filter": ["filterExpr"],
                "aggregate": ["aggregateColumn", "aggregateOp"],
                "fill_null": ["fillColumns"],
                "computed_column": ["computedColumnName", "computedFormula"],
                "merge_columns": ["mergeSourceColumns", "mergeTargetColumn"],
                "split_column": ["splitSourceColumn", "splitIntoColumns"],
            }
            missing = [key for key in required_by_kind.get(process_kind, []) if not str(cv.get(key) or "").strip()]
            if missing:
                errors.append(f"{title}：缺少配置 {_label_config_fields(missing)}")
        elif schema_key == "schema-data-clean":
            rules = cv.get("cleanRules")
            if not rules:
                errors.append(f"{title}：清洗规则不能为空")
        elif schema_key == "schema-table-extract":
            strategy = str(cv.get("tableStrategy") or "first").strip()
            if strategy not in {"first", "all", "by_index"}:
                errors.append(f"{title}：提取策略配置无效")
            if strategy == "by_index":
                try:
                    if int(cv.get("tableIndex")) <= 0:
                        raise ValueError()
                except Exception:
                    errors.append(f"{title}：表格序号必须是从 1 开始的正整数")
        elif schema_key == "schema-save-excel":
            sheet_name = str(cv.get("sheetName") or "Sheet1")
            if len(sheet_name) > 31:
                errors.append(f"{title}：工作表名不能超过 31 个字符")
            if any(ch in sheet_name for ch in '[]:*?/\\'):
                errors.append(f"{title}：工作表名不能包含 []:*?/\\")
        elif schema_key == "schema-save-text":
            encoding = str(cv.get("outputEncoding") or "utf-8").lower()
            if encoding not in {"utf-8", "gbk"}:
                errors.append(f"{title}：输出编码仅支持 utf-8 或 gbk")
            line_ending = str(cv.get("lineEnding") or "lf").lower()
            if line_ending not in {"lf", "crlf"}:
                errors.append(f"{title}：换行符仅支持 lf 或 crlf")

    return errors


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
    from utils.storage_paths import resolve_local_storage_path

    # 文档库文档
    doc = get_library_doc_by_id(doc_id, config=config, user_id=None)
    if doc and doc.storage_key:
        resolved = resolve_local_storage_path(doc.storage_key, config=config)
        if resolved:
            return str(resolved)
        if doc.blob_url and doc.blob_url != doc.storage_key:
            resolved = resolve_local_storage_path(doc.blob_url, config=config)
            if resolved:
                return str(resolved)

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


@dataclass
class _FileJobResult:
    idx: int
    name: str
    status: str  # processed | skipped | failed | missing | cancelled
    output_item: Optional[Dict[str, Any]] = None
    output_items: Optional[List[Dict[str, Any]]] = None
    error_message: Optional[str] = None


def _parse_bool_setting(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).lower() in ("true", "1", "yes", "on")


def _parse_run_settings(run_settings: Optional[Dict[str, Any]]) -> Tuple[int, bool, bool]:
    rs = run_settings or {}
    raw_limit = rs.get("concurrentLimit", 1)
    try:
        concurrent_limit = int(raw_limit)
    except (TypeError, ValueError):
        concurrent_limit = 1
    concurrent_limit = max(1, min(10, concurrent_limit))
    continue_on_error = _parse_bool_setting(rs.get("continueOnError"), True)
    notify_on_error = _parse_bool_setting(rs.get("notifyOnError"), True)
    return concurrent_limit, continue_on_error, notify_on_error


def _with_state_lock(state_lock: Optional[threading.Lock], fn):
    if state_lock:
        with state_lock:
            return fn()
    return fn()


def _append_execution_log(
    state: Dict[str, Any],
    log_type: str,
    message: str,
    *,
    config: SystemConfig,
    state_lock: Optional[threading.Lock] = None,
) -> None:
    def _apply():
        state["logs"].append({"type": log_type, "message": message})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)

    _with_state_lock(state_lock, _apply)


def _make_progress_callback(
    execution_id: str,
    *,
    state_lock: Optional[threading.Lock] = None,
    file_index: int = 1,
    total_files: int = 1,
):
    """生成一个向执行状态写入进度日志的回调。"""

    def callback(progress: int, total: int, message: str, **kwargs):
        if execution_id not in _EXECUTION_STATES:
            return

        def _apply():
            state = _EXECUTION_STATES[execution_id]
            node_ratio = max(0.0, min(float(progress) / max(total, 1), 1.0))
            overall = int(((file_index - 1) + node_ratio) / max(total_files, 1) * 100)
            state["progress"] = max(0, min(overall, 99 if state.get("status") == "running" else 100))

            node_id = str(kwargs.get("node_id") or "")
            node_title = str(kwargs.get("node_title") or "")
            node_index = int(kwargs.get("node_index") or progress or 0)
            node_status = str(kwargs.get("node_status") or "running")
            node_item_progress = int(
                kwargs.get("node_progress")
                if kwargs.get("node_progress") is not None
                else (100 if node_status == "completed" else 50)
            )

            if node_id or node_title:
                state["current_node_id"] = node_id
                state["current_node_name"] = node_title
                state["current_node_index"] = node_index
                state["total_nodes"] = max(int(state.get("total_nodes") or total or 0), int(total or 0))
                for item in state.get("node_progress", []):
                    if (node_id and item.get("id") == node_id) or (not node_id and item.get("title") == node_title):
                        item["status"] = node_status
                        item["progress"] = max(0, min(node_item_progress, 100))
                        item["message"] = message
                        break
            state["logs"].append({"type": "info", "message": message})
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states()

        _with_state_lock(state_lock, _apply)

    return callback


def _process_single_file(
    *,
    idx: int,
    file_info: FileInfo,
    total_files: int,
    execution_id: str,
    params: ExecuteRequest,
    config: SystemConfig,
    skip_existing: bool,
    output_config_for_path: Dict[str, Any],
    output_mode: str,
    output_format: str,
    target_space_id: Optional[str],
    naming_rule: str,
    input_config: Dict[str, Any],
    target_language: str,
    output_config: Dict[str, Any],
    notify_on_error: bool,
    state_lock: Optional[threading.Lock],
) -> _FileJobResult:
    state = _EXECUTION_STATES.get(execution_id)
    if not state:
        return _FileJobResult(idx, file_info.name, "cancelled")

    prefix = f"[{idx + 1}/{total_files}]"
    name = file_info.name

    if not file_info.path or not Path(file_info.path).exists():
        _append_execution_log(
            state,
            "warn",
            f"{prefix} 跳过（文件不存在）: {name}",
            config=config,
            state_lock=state_lock,
        )
        return _FileJobResult(idx, name, "missing")

    out_path, out_name = resolve_workflow_output_path(
        file_info.name,
        file_info.path,
        output_config_for_path,
        str(config.output_dir),
    )

    if skip_existing and out_path.exists():
        skip_item = {
            "name": out_name,
            "path": str(out_path),
            "blob_name": None,
            "size": out_path.stat().st_size,
            "source": file_info.name,
            "skipped": True,
        }
        _append_execution_log(
            state,
            "warn",
            f"{prefix} 跳过已处理: {file_info.name}（输出已存在: {out_name}）",
            config=config,
            state_lock=state_lock,
        )
        return _FileJobResult(idx, name, "skipped", output_item=skip_item)

    def _mark_running():
        state["current_file_index"] = idx + 1
        state["current_file_name"] = name
        state["current_node_id"] = ""
        state["current_node_name"] = ""
        state["current_node_index"] = 0
        state["total_nodes"] = len(params.nodes)
        state["node_progress"] = _build_node_progress(params.nodes)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)

    _with_state_lock(state_lock, _mark_running)
    _append_execution_log(
        state,
        "info",
        f"{prefix} 正在处理: {name}",
        config=config,
        state_lock=state_lock,
    )

    task_spec = TaskSpec(
        task_type=TaskType.WORKFLOW_PIPELINE,
        instruction=f"workflow:{params.workflowId}",
        source_files=[file_info],
        session_id=params.sessionId,
        parameters={
            "workflow_nodes": [n.model_dump() for n in params.nodes],
            "output_config": {
                "outputMode": output_mode,
                "outputFormat": output_format,
                "targetSpaceId": target_space_id,
                "namingRule": naming_rule,
                "targetLanguage": target_language,
                "savePath": output_config.get("savePath"),
                "sheetName": output_config.get("sheetName"),
                "outputEncoding": output_config.get("outputEncoding"),
                "lineEnding": output_config.get("lineEnding"),
                "notifyOnComplete": output_config.get("notifyOnComplete"),
            },
            "input_config": input_config,
            "execution_id": execution_id,
            "workflow_edges": params.workflowEdges or [],
        },
    )

    coordinator = WorkflowCoordinator(config)
    wf_result = coordinator.execute(
        task_spec,
        progress_callback=_make_progress_callback(
            execution_id,
            state_lock=state_lock,
            file_index=idx + 1,
            total_files=total_files,
        ),
    )
    if not wf_result.success:
        err = str(wf_result.message)
        msg = f"{prefix} 执行失败: {err}"
        if notify_on_error:
            msg = f"【出错通知】{msg}"
        _append_execution_log(state, "error", msg, config=config, state_lock=state_lock)
        return _FileJobResult(idx, name, "failed", error_message=err)

    out_items: List[Dict[str, Any]] = []
    if isinstance(wf_result.data, dict):
        raw_outputs = wf_result.data.get("outputs")
        if isinstance(raw_outputs, list) and raw_outputs:
            out_items = [item for item in raw_outputs if isinstance(item, dict) and item]
        else:
            single = wf_result.data.get("output", {}) or {}
            if single:
                out_items = [single]
    if not out_items:
        _append_execution_log(
            state,
            "warn",
            f"{prefix} 无输出产物: {file_info.name}",
            config=config,
            state_lock=state_lock,
        )
        return _FileJobResult(idx, name, "failed", error_message="无输出产物")

    for out_item in out_items:
        out_path = out_item.get("path")
        out_name = out_item.get("name", file_info.name)
        _append_execution_log(
            state,
            "done",
            f"{prefix} 已保存: {out_name}",
            config=config,
            state_lock=state_lock,
        )

        if str(output_mode).lower() == "library" and out_path and target_space_id:
            ok_lib, lib_msg = _save_output_to_library(str(out_path), str(target_space_id), config)
            if ok_lib:
                _append_execution_log(
                    state,
                    "done",
                    f"{prefix} 已保存到文档库: {out_name}",
                    config=config,
                    state_lock=state_lock,
                )
            else:
                lib_msg_text = f"{prefix} 文档库入库失败: {lib_msg}"
                if notify_on_error:
                    lib_msg_text = f"【出错通知】{lib_msg_text}"
                _append_execution_log(state, "error", lib_msg_text, config=config, state_lock=state_lock)

    return _FileJobResult(idx, name, "processed", output_items=out_items)


def _apply_file_job_result(
    result: _FileJobResult,
    *,
    state: Dict[str, Any],
    all_output_files: List[Dict[str, Any]],
    counters: Dict[str, int],
    failure_messages: List[str],
    total_files: int,
    config: SystemConfig,
    state_lock: Optional[threading.Lock],
) -> None:
    if result.status in ("processed", "skipped"):
        items = result.output_items or ([result.output_item] if result.output_item else [])
        for item in items:
            if item:
                all_output_files.append(item)
    if result.status == "processed":
        counters["processed"] += 1
    elif result.status == "skipped":
        counters["skipped"] += 1
    elif result.status == "failed":
        counters["failed"] += 1
        if result.error_message:
            failure_messages.append(result.error_message)
    elif result.status == "missing":
        counters["missing"] += 1

    done_count = counters["processed"] + counters["skipped"] + counters["failed"] + counters["missing"]

    def _update_progress():
        state["progress"] = int(done_count / max(total_files, 1) * 100)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)

    _with_state_lock(state_lock, _update_progress)


async def _run_execution(execution_id: str, params: ExecuteRequest):
    """
    后台执行任务：支持多文件串行或并行处理（由 runSettings.concurrentLimit 控制）。
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
        input_config = _get_input_config(params.nodes)

        translation_config = _get_translation_config(params.nodes)
        target_language = _normalize_lang(translation_config.get("targetLanguage", "中文"))

        if str(output_mode).lower() == "library" and not target_space_id:
            state["logs"].append(
                {
                    "type": "warn",
                    "message": "输出模式为「保存到文档库」，但未选择目标文档库；文件只会生成在工作流输出目录，不会出现在文档库列表。请在输出节点选择目标库后重试。",
                }
            )
        elif str(output_mode).lower() == "library" and not (
            config.database.enabled and is_database_configured(config)
        ):
            state["logs"].append(
                {
                    "type": "warn",
                    "message": "文档库入库需要 MySQL：请在 .env 中启用 DB_ENABLED 并配置 DATABASE_URL（或其它 DB_*）。当前数据库未就绪，仅能下载/查看本地输出路径。",
                }
            )

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

        # 从文档库（命名规则用 doc.file_name，不用带 hash 的磁盘文件名）
        from db.library_repository import get_library_doc_by_id

        for doc_id in params.docs:
            doc = get_library_doc_by_id(doc_id, config=config, user_id=None)
            path = _resolve_doc_path(doc_id, config)
            if path:
                display_name = doc.file_name if doc and doc.file_name else Path(path).name
                ft = _detect_file_type(display_name)
                source_files.append(FileInfo(path=path, file_type=ft, name=display_name))
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
            state["error_code"] = "VALIDATION_ERROR"
            state["logs"].append({"type": "error", "message": "没有可处理的文件"})
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_execution_states(config)
            return

        concurrent_limit, continue_on_error, notify_on_error = _parse_run_settings(params.runSettings)
        total_files = len(source_files)
        state["total_files"] = total_files
        if concurrent_limit <= 1:
            start_msg = f"共 {total_files} 个文件，开始逐个处理..."
        else:
            start_msg = f"共 {total_files} 个文件，并发数量 {concurrent_limit}，开始并行处理..."
        state["logs"].append({"type": "info", "message": start_msg})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)

        # ===== 文件处理（支持串行 / 并行） =====
        all_output_files: List[Dict[str, Any]] = []
        failure_messages: List[str] = []
        counters = {"processed": 0, "skipped": 0, "failed": 0, "missing": 0}
        skip_existing = bool(input_config.get("skipExisting", False))
        output_config_for_path = {
            "outputFormat": output_format,
            "namingRule": naming_rule,
            "savePath": output_config.get("savePath"),
        }
        state_lock = threading.Lock() if concurrent_limit > 1 else None
        stop_processing = threading.Event()

        def _job_kwargs():
            return {
                "total_files": total_files,
                "execution_id": execution_id,
                "params": params,
                "config": config,
                "skip_existing": skip_existing,
                "output_config_for_path": output_config_for_path,
                "output_mode": output_mode,
                "output_format": output_format,
                "target_space_id": target_space_id,
                "naming_rule": naming_rule,
                "input_config": input_config,
                "target_language": target_language,
                "output_config": output_config,
                "notify_on_error": notify_on_error,
                "state_lock": state_lock,
            }

        def _run_job(idx: int, file_info: FileInfo) -> _FileJobResult:
            if stop_processing.is_set():
                return _FileJobResult(idx, file_info.name, "cancelled")
            return _process_single_file(idx=idx, file_info=file_info, **_job_kwargs())

        for batch_start in range(0, total_files, concurrent_limit):
            if stop_processing.is_set():
                remaining = total_files - batch_start
                if remaining > 0:
                    _append_execution_log(
                        state,
                        "warn",
                        f"已停止后续处理：出错时继续已关闭，剩余 {remaining} 个文件未处理",
                        config=config,
                        state_lock=state_lock,
                    )
                break

            batch = source_files[batch_start: batch_start + concurrent_limit]
            batch_jobs = list(enumerate(batch, start=batch_start))

            if concurrent_limit <= 1:
                for idx, file_info in batch_jobs:
                    result = _run_job(idx, file_info)
                    _apply_file_job_result(
                        result,
                        state=state,
                        all_output_files=all_output_files,
                        counters=counters,
                        failure_messages=failure_messages,
                        total_files=total_files,
                        config=config,
                        state_lock=state_lock,
                    )
                    if result.status == "failed" and not continue_on_error:
                        stop_processing.set()
                        break
            else:
                with ThreadPoolExecutor(max_workers=min(concurrent_limit, len(batch_jobs))) as executor:
                    futures = {executor.submit(_run_job, idx, file_info): (idx, file_info) for idx, file_info in batch_jobs}
                    batch_failed = False
                    for future in as_completed(futures):
                        result = future.result()
                        _apply_file_job_result(
                            result,
                            state=state,
                            all_output_files=all_output_files,
                            counters=counters,
                            failure_messages=failure_messages,
                            total_files=total_files,
                            config=config,
                            state_lock=state_lock,
                        )
                        if result.status == "failed":
                            batch_failed = True
                    if batch_failed and not continue_on_error:
                        stop_processing.set()

        processed_count = counters["processed"]
        skipped_count = counters["skipped"]
        failed_count = counters["failed"]

        # ===== 完成 =====
        state["progress"] = 100
        state["output_files"] = all_output_files
        if all_output_files:
            state["status"] = "completed"
            state["error"] = None
            state["error_code"] = None
            if skipped_count and processed_count:
                summary = f"全部完成：新处理 {processed_count} 个，跳过 {skipped_count} 个"
            elif skipped_count:
                summary = f"全部完成：跳过 {skipped_count} 个（输出均已存在）"
            else:
                summary = f"全部完成，已处理 {processed_count} 个输出文件"
            state["logs"].append({"type": "done", "message": summary})
            if failed_count > 0:
                state["logs"].append({"type": "warn", "message": f"其中 {failed_count} 个文件处理失败"})
        else:
            state["status"] = "failed"
            state["error_code"] = "WORKFLOW_FAILED"
            merged = "；".join(failure_messages[-3:]) if failure_messages else "全部文件处理失败"
            state["error"] = merged
            state["logs"].append({"type": "error", "message": f"执行失败: {merged}"})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)

    except Exception as e:
        logger.error(f"执行任务异常: {e}")
        state["status"] = "failed"
        state["error"] = str(e)
        state["error_code"] = "INTERNAL_ERROR"
        state["logs"].append({"type": "error", "message": f"执行异常: {e}"})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_execution_states(config)


def _save_output_to_library(file_path: str, space_id: str, config: SystemConfig) -> Tuple[bool, str]:
    """将输出文件保存到文档库（写存储 + PostgreSQL 登记）。返回 (是否成功, 错误说明)。"""
    if not (config.database.enabled and is_database_configured(config)):
        return False, "数据库未启用或未配置，无法写入 library_documents"

    try:
        from db.library_repository import add_library_doc, get_library_space_by_id
        import hashlib

        p = Path(file_path)
        if not p.is_file():
            return False, f"输出文件不存在: {file_path}"

        # 与手动上传一致：登记为空间所属用户，否则已登录用户列表会带 user_id 条件，看不到 user_id 为空的记录
        space_row = get_library_space_by_id(space_id, config=config, user_id=None)
        owner_user_id = space_row.user_id if space_row else None

        with open(p, "rb") as f:
            content_bytes = f.read()
        file_size = len(content_bytes)
        file_hash = hashlib.md5(content_bytes).hexdigest()
        safe_name = f"{file_hash}_{p.name}"

        storage_key: Optional[str] = None
        if oss_storage_enabled(config):
            from core.storage import build_blob_name, upload_stream_to_storage
            from io import BytesIO

            blob_name = build_blob_name(space_id, safe_name, prefix=config.storage.object_key_prefix or "workflows")
            storage_key = upload_stream_to_storage(
                BytesIO(content_bytes),
                config=config,
                blob_name=blob_name,
                content_type="application/octet-stream",
            )
        else:
            upload_dir = Path(config.work_dir) / "library" / space_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            storage_key = str(upload_dir / safe_name)
            Path(storage_key).write_bytes(content_bytes)

        add_library_doc(
            space_id=space_id,
            file_name=p.name,
            file_size=file_size,
            config=config,
            user_id=owner_user_id,
            mime_type="application/octet-stream",
            storage_key=storage_key,
            blob_url=storage_key,
        )
        return True, ""
    except Exception as e:
        logger.warning(f"保存到文档库失败: {e}")
        return False, str(e)


# ==================== API 端点 ====================

# ⚠️ 路由顺序很重要：精确路径必须在动态路径 {workflow_id} 之前注册


@router.post("/execute", response_model=Dict[str, str])
async def execute_workflow(request: ExecuteRequest, background_tasks: BackgroundTasks):
    """
    启动工作流执行（支持多文件串行/并行）。
    立即返回 execution_id，前端通过 GET /executions/{id} 轮询进度。
    """
    validation_errors = _validate_execute_request(request)
    if validation_errors:
        raise HTTPException(status_code=400, detail="；".join(validation_errors))

    execution_id = uuid.uuid4().hex

    _EXECUTION_STATES[execution_id] = {
        "status": "running",
        "progress": 0,
        "current_file_index": 0,
        "total_files": 0,
        "current_file_name": "",
        "current_node_id": "",
        "current_node_name": "",
        "current_node_index": 0,
        "total_nodes": len(request.nodes),
        "node_progress": _build_node_progress(request.nodes),
        "logs": [{"type": "info", "message": "任务已启动，正在初始化..."}],
        "output_files": [],
        "error": None,
        "error_code": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _persist_execution_states()

    # 后台运行，不阻塞 HTTP 响应
    background_tasks.add_task(_run_execution, execution_id, request)

    return {"execution_id": execution_id}


# -------- 精确路径端点（必须在 /{workflow_id} 之前） --------


@router.get("/templates")
async def list_templates():
    """返回内置工作流模板列表。预设模板由前端维护（文档翻译流）。"""
    return {"templates": []}


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str):
    """获取指定模板的完整配置。"""
    templates_resp = await list_templates()
    templates = templates_resp.get("templates", []) if isinstance(templates_resp, dict) else []
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
    error_code = state.get("error_code")
    if not error_code and state.get("status") == "failed":
        error_text = str(state.get("error") or "")
        if "没有可处理的文件" in error_text or "缺少" in error_text:
            error_code = "VALIDATION_ERROR"
        else:
            error_code = "WORKFLOW_FAILED"
    return ExecutionResponse(
        execution_id=execution_id,
        status=state["status"],
        progress=state["progress"],
        current_file_index=state["current_file_index"],
        total_files=state["total_files"],
        current_file_name=state["current_file_name"],
        current_node_id=state.get("current_node_id", ""),
        current_node_name=state.get("current_node_name", ""),
        current_node_index=state.get("current_node_index", 0),
        total_nodes=state.get("total_nodes", 0),
        node_progress=state.get("node_progress", []),
        logs=state["logs"],
        output_files=state["output_files"],
        error=state["error"],
        error_code=error_code,
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
        {"code": "xlsx", "name": "Excel"},
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
    return {"success": True}
