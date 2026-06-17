"""
任务执行器
负责调用Agent执行具体任务
文档解析由各Agent自行处理（使用外部库如python-docx, pdfplumber等）
"""
from typing import Optional, List, Any, Dict
import csv
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

from config import SystemConfig, get_config
from core.storage import build_blob_name, upload_file_to_storage, oss_storage_enabled
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

    def parse_documents(self, source_files: List[FileInfo], *, for_workflow: bool = False) -> Dict[str, str]:
        """解析源文档，返回 file_path -> text 映射。"""
        from utils.document_reader import read_document

        parsed_content: Dict[str, str] = {}
        for file_info in source_files:
            if file_info.path in self._file_cache:
                parsed_content[file_info.path] = self._file_cache[file_info.path]
                continue

            path_lower = str(file_info.path).lower()
            if for_workflow and path_lower.endswith((".xlsx", ".xls")):
                content = read_document(
                    file_info.path,
                    max_rows=10000,
                    compute_stats=False,
                    workflow_table=True,
                )
            else:
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
        payload = getattr(data, "data", {}) if data is not None else {}
        if not isinstance(payload, dict):
            return ""
        entities = payload.get("entities")
        if not isinstance(entities, list) or not entities:
            self.logger.warning("跳过模板填充：缺少 entities 数据")
            return ""

        try:
            from core.agents.agent_d import run_agent_d_fill_from_entities

            fill_result = run_agent_d_fill_from_entities(
                entities=entities,
                template=template.path,
            )
            if not isinstance(fill_result, dict) or not fill_result.get("success"):
                self.logger.warning(f"模板填充失败: {fill_result}")
                return ""
            result_data = fill_result.get("data", {})
            if isinstance(result_data, dict):
                return str(result_data.get("template_output") or "")
            return ""
        except Exception as exc:
            self.logger.error(f"模板填充异常: {exc}")
            return ""

    def execute_workflow_pipeline(self, task_spec: TaskSpec, progress_callback=None) -> Dict[str, Any]:
        """
        统一工作流节点流水线执行（由 coordinator 调用）。
        parameters:
            - workflow_nodes: List[dict]
            - output_config: Dict[str, Any]
            - execution_id: str (optional, for blob prefix)
        """
        source = task_spec.source_files[0] if task_spec.source_files else None
        if not source:
            return {"success": False, "message": "缺少源文件"}

        output_config = task_spec.parameters.get("output_config", {}) or {}
        workflow_nodes = task_spec.parameters.get("workflow_nodes", []) or []
        input_config = task_spec.parameters.get("input_config", {}) or {}
        execution_id = str(task_spec.parameters.get("execution_id") or "workflow")

        from utils.workflow_paths import resolve_workflow_output_path

        out_path, out_name = resolve_workflow_output_path(
            source.name,
            source.path,
            output_config,
            str(self.config.output_dir),
        )

        skip_existing = bool(input_config.get("skipExisting", False))
        if skip_existing and out_path.exists():
            return {
                "success": True,
                "skipped": True,
                "message": "跳过已存在输出（skipExisting=true）",
                "output_file": str(out_path),
                "output": {
                    "name": out_path.name,
                    "path": str(out_path),
                    "blob_name": None,
                    "size": out_path.stat().st_size,
                    "source": source.name,
                },
            }

        parsed = self.parse_documents([source], for_workflow=True)
        content = parsed.get(source.path, "")
        if not content:
            return {"success": False, "message": f"无法读取文件内容: {source.name}"}

        total_nodes = max(len(workflow_nodes), 1)
        result_content = content
        out_path_written: Optional[Path] = None
        out_name_written = out_name
        mime_type = "application/octet-stream"
        wrote_output = False
        written_outputs: List[Dict[str, Any]] = []

        from api.routers.workflows_processors import _process_node
        from core.orchestrator.workflow_control import (
            collect_controlled_node_ids,
            run_loop_body,
        )

        node_map = {str(n.get("id", "")): n for n in workflow_nodes if n.get("id")}
        controlled_ids = collect_controlled_node_ids(workflow_nodes)
        node_index_map = {
            str(n.get("id", "")): idx for idx, n in enumerate(workflow_nodes, 1) if n.get("id")
        }

        def _emit_node_progress(node_dict: dict, status: str, message: str, *, progress_pct: int) -> None:
            if not progress_callback:
                return
            nid = str(node_dict.get("id", ""))
            ntitle = str(node_dict.get("title", "") or node_dict.get("type", ""))
            nindex = node_index_map.get(nid, 1)
            progress_callback(
                nindex,
                total_nodes,
                message,
                node_id=nid,
                node_title=ntitle,
                node_index=nindex,
                node_status=status,
                node_progress=progress_pct,
            )

        def _run_process_dict(node_dict: dict, text: str) -> str:
            proc = SimpleNamespace(
                type=node_dict.get("type", ""),
                title=node_dict.get("title", ""),
                schemaKey=node_dict.get("schemaKey", ""),
                configValues=node_dict.get("configValues", {}) or {},
            )
            out = _process_node(text, source.name, proc, self.config, {})
            if not out:
                raise RuntimeError(f"节点处理结果为空: {proc.title or proc.type}")
            return out

        def _write_output_for_node(
            node_dict: dict,
            original_index: int,
            *,
            branch_content: Optional[str] = None,
        ) -> Optional[Dict[str, Any]]:
            nonlocal out_path_written, out_name_written, mime_type, wrote_output
            node_id = str(node_dict.get("id", ""))
            node_title = str(node_dict.get("title", "") or node_dict.get("type", ""))
            eff_output = self._merge_node_output_config(output_config, node_dict)
            node_out_path, node_out_name = resolve_workflow_output_path(
                source.name,
                source.path,
                eff_output,
                str(self.config.output_dir),
            )
            node_out_path.parent.mkdir(parents=True, exist_ok=True)
            text_to_write = branch_content if branch_content is not None else result_content
            if progress_callback:
                progress_callback(
                    original_index,
                    total_nodes,
                    f"输出节点开始: {node_title}",
                    node_id=node_id,
                    node_title=node_title,
                    node_index=original_index,
                    node_status="running",
                    node_progress=30,
                )
            try:
                mime_type = self._write_workflow_output_file(
                    text_to_write, node_out_path, eff_output, node_out_name
                )
            except Exception as exc:
                if progress_callback:
                    progress_callback(
                        original_index,
                        total_nodes,
                        f"输出节点失败: {node_title}（{exc}）",
                        node_id=node_id,
                        node_title=node_title,
                        node_index=original_index,
                        node_status="failed",
                        node_progress=100,
                    )
                return {"success": False, "message": f"输出文件写入失败: {exc}"}
            out_path_written = node_out_path
            out_name_written = node_out_name
            wrote_output = True
            output_item = {
                "name": node_out_path.name,
                "path": str(node_out_path),
                "blob_name": None,
                "size": node_out_path.stat().st_size,
                "source": source.name,
                "output_node_id": node_id,
            }
            written_outputs.append(output_item)
            if progress_callback:
                progress_callback(
                    original_index,
                    total_nodes,
                    f"输出节点完成: {node_title}",
                    node_id=node_id,
                    node_title=node_title,
                    node_index=original_index,
                    node_status="completed",
                    node_progress=100,
                )
            return None

        workflow_edges = task_spec.parameters.get("workflow_edges") or []
        from core.orchestrator.workflow_graph_engine import (
            run_workflow_graph,
            should_use_graph_engine,
        )

        if should_use_graph_engine(workflow_edges, workflow_nodes):
            try:
                branch_outputs = run_workflow_graph(
                    workflow_nodes,
                    workflow_edges or None,
                    content,
                    source.name,
                    run_process=_run_process_dict,
                    emit_progress=lambda nd, st, msg, progress_pct: _emit_node_progress(
                        nd, st, msg, progress_pct=progress_pct
                    ),
                )
            except Exception as exc:
                return {"success": False, "message": f"图执行失败: {exc}"}
            if not branch_outputs:
                return {"success": False, "message": "工作流执行未到达任何输出节点"}
            for output_node_id, branch_content in branch_outputs:
                node_dict = node_map.get(str(output_node_id))
                if not node_dict:
                    continue
                original_index = node_index_map.get(str(output_node_id), 1)
                err = _write_output_for_node(
                    node_dict, original_index, branch_content=branch_content
                )
                if err:
                    return err
        if not should_use_graph_engine(workflow_edges, workflow_nodes):
            for original_index, node_dict in enumerate(workflow_nodes, 1):
                node_type = str(node_dict.get("type", "")).lower()
                node_id = str(node_dict.get("id", ""))
                node_title = str(node_dict.get("title", "") or node_dict.get("type", ""))
                schema_key = str(node_dict.get("schemaKey", "") or "").strip().lower()
                config_values = node_dict.get("configValues", {}) or {}

                if node_type == "input":
                    if progress_callback:
                        progress_callback(
                            original_index,
                            total_nodes,
                            f"输入节点完成: {node_title}",
                            node_id=node_id,
                            node_title=node_title,
                            node_index=original_index,
                            node_status="completed",
                            node_progress=100,
                        )
                    continue

                if node_type == "output":
                    eff_output = self._merge_node_output_config(output_config, node_dict)
                    node_out_path, node_out_name = resolve_workflow_output_path(
                        source.name,
                        source.path,
                        eff_output,
                        str(self.config.output_dir),
                    )
                    node_out_path.parent.mkdir(parents=True, exist_ok=True)
                    if progress_callback:
                        progress_callback(
                            original_index,
                            total_nodes,
                            f"输出节点开始: {node_title}",
                            node_id=node_id,
                            node_title=node_title,
                            node_index=original_index,
                            node_status="running",
                            node_progress=30,
                        )
                    try:
                        mime_type = self._write_workflow_output_file(
                            result_content, node_out_path, eff_output, node_out_name
                        )
                    except Exception as exc:
                        if progress_callback:
                            progress_callback(
                                original_index,
                                total_nodes,
                                f"输出节点失败: {node_title}（{exc}）",
                                node_id=node_id,
                                node_title=node_title,
                                node_index=original_index,
                                node_status="failed",
                                node_progress=100,
                            )
                        return {"success": False, "message": f"输出文件写入失败: {exc}"}
                    out_path_written = node_out_path
                    out_name_written = node_out_name
                    wrote_output = True
                    written_outputs.append({
                        "name": node_out_path.name,
                        "path": str(node_out_path),
                        "blob_name": None,
                        "size": node_out_path.stat().st_size,
                        "source": source.name,
                        "output_node_id": node_id,
                    })
                    if progress_callback:
                        progress_callback(
                            original_index,
                            total_nodes,
                            f"输出节点完成: {node_title}",
                            node_id=node_id,
                            node_title=node_title,
                            node_index=original_index,
                            node_status="completed",
                            node_progress=100,
                        )
                    continue

                if node_id in controlled_ids:
                    _emit_node_progress(
                        node_dict,
                        "completed",
                        f"已由流程控制执行: {node_title}",
                        progress_pct=100,
                    )
                    continue

                if node_type == "control" and schema_key == "schema-loop":
                    body_ids = config_values.get("bodyNodeIds") or []
                    max_iter = int(config_values.get("maxIterations") or 5)
                    exit_condition = config_values.get("exitCondition") or "unchanged"
                    exit_text = config_values.get("exitContainsText") or ""
                    if progress_callback:
                        progress_callback(
                            original_index,
                            total_nodes,
                            f"循环开始: {node_title}（最多 {max_iter} 次）",
                            node_id=node_id,
                            node_title=node_title,
                            node_index=original_index,
                            node_status="running",
                            node_progress=20,
                        )
                    try:
                        def _run_loop_step(nd: dict, txt: str) -> str:
                            _emit_node_progress(nd, "running", f"循环执行: {nd.get('title', '')}", progress_pct=40)
                            try:
                                out = _run_process_dict(nd, txt)
                            except Exception:
                                _emit_node_progress(nd, "failed", f"循环失败: {nd.get('title', '')}", progress_pct=100)
                                raise
                            _emit_node_progress(nd, "completed", f"循环步骤完成: {nd.get('title', '')}", progress_pct=100)
                            return out

                        result_content = run_loop_body(
                            body_ids,
                            node_map,
                            result_content,
                            _run_loop_step,
                            max_iterations=max_iter,
                            exit_condition=exit_condition,
                            exit_contains_text=exit_text,
                        )
                    except Exception as exc:
                        if progress_callback:
                            progress_callback(
                                original_index,
                                total_nodes,
                                f"循环失败: {node_title}（{exc}）",
                                node_id=node_id,
                                node_title=node_title,
                                node_index=original_index,
                                node_status="failed",
                                node_progress=100,
                            )
                        return {"success": False, "message": f"循环处理失败: {exc}"}
                    if progress_callback:
                        progress_callback(
                            original_index,
                            total_nodes,
                            f"循环完成: {node_title}",
                            node_id=node_id,
                            node_title=node_title,
                            node_index=original_index,
                            node_status="completed",
                            node_progress=100,
                        )
                    continue

                node = SimpleNamespace(
                    type=node_dict.get("type", ""),
                    title=node_dict.get("title", ""),
                    schemaKey=node_dict.get("schemaKey", ""),
                    configValues=config_values,
                )
                if progress_callback:
                    progress_callback(
                        original_index,
                        total_nodes,
                        f"处理节点开始: {node.title or node.type}",
                        node_id=node_id,
                        node_title=str(node.title or node.type),
                        node_index=original_index,
                        node_status="running",
                        node_progress=30,
                    )
                try:
                    result_content = _process_node(result_content, source.name, node, self.config, {})
                except Exception as exc:
                    if progress_callback:
                        progress_callback(
                            original_index,
                            total_nodes,
                            f"处理节点失败: {node.title or node.type}（{exc}）",
                            node_id=node_id,
                            node_title=str(node.title or node.type),
                            node_index=original_index,
                            node_status="failed",
                            node_progress=100,
                        )
                    return {"success": False, "message": f"节点处理失败: {node.title or node.type}（{exc}）"}
                if not result_content:
                    if progress_callback:
                        progress_callback(
                            original_index,
                            total_nodes,
                            f"处理节点失败: {node.title or node.type}",
                            node_id=node_id,
                            node_title=str(node.title or node.type),
                            node_index=original_index,
                            node_status="failed",
                            node_progress=100,
                        )
                    return {"success": False, "message": f"节点处理结果为空: {node.title or node.type}"}
                if progress_callback:
                    progress_callback(
                        original_index,
                        total_nodes,
                        f"处理节点完成: {node.title or node.type}",
                        node_id=node_id,
                        node_title=str(node.title or node.type),
                        node_index=original_index,
                        node_status="completed",
                        node_progress=100,
                    )

        if not wrote_output or not out_path_written:
            return {"success": False, "message": "工作流中缺少输出节点"}

        out_path = out_path_written
        out_name = out_name_written

        blob_name = None
        if oss_storage_enabled(self.config):
            for item in written_outputs:
                item_path = Path(str(item.get("path") or ""))
                if not item_path.exists():
                    continue
                try:
                    item_blob = upload_file_to_storage(
                        item_path,
                        config=self.config,
                        blob_name=build_blob_name(
                            execution_id,
                            item_path.name,
                            prefix=self.config.storage.object_key_prefix or "workflows",
                        ),
                        content_type=mime_type,
                    )
                    item["blob_name"] = item_blob
                    if blob_name is None:
                        blob_name = item_blob
                except Exception as exc:
                    self.logger.warning(f"上传工作流产物到 OSS 失败: {exc}")

        primary_output = written_outputs[0] if written_outputs else {
            "name": out_path.name,
            "path": str(out_path),
            "blob_name": blob_name,
            "size": out_path.stat().st_size,
            "source": source.name,
        }

        return {
            "success": True,
            "message": "工作流处理完成",
            "output_file": str(out_path),
            "output": primary_output,
            "outputs": written_outputs,
        }

    @staticmethod
    def _merge_node_output_config(base: Dict[str, Any], node_dict: Dict[str, Any]) -> Dict[str, Any]:
        """将输出节点上的 configValues 合并进全局 output_config。"""
        cv = dict(node_dict.get("configValues") or {})
        schema_key = str(node_dict.get("schemaKey") or "")
        merged = dict(base or {})
        if cv.get("outputFormat"):
            merged["outputFormat"] = cv["outputFormat"]
        elif schema_key == "schema-save-excel":
            merged["outputFormat"] = "xlsx"
        elif schema_key == "schema-save-text":
            merged["outputFormat"] = "txt"
        for key in (
            "namingRule", "savePath", "sheetName", "outputEncoding", "lineEnding",
            "outputMode", "targetSpaceId", "targetLanguage",
        ):
            if cv.get(key) not in (None, ""):
                merged[key] = cv[key]
        return merged

    def _write_workflow_output_file(
        self,
        result_content: str,
        out_path: Path,
        output_config: Dict[str, Any],
        out_name: str,
    ) -> str:
        """按配置将流水线结果写入磁盘，返回 MIME 类型。"""
        output_format = str(output_config.get("outputFormat") or "md").lower()
        if output_format in ("excel", "xls"):
            output_format = "xlsx"
        if output_format not in ("md", "txt", "pdf", "xlsx"):
            output_format = "md"

        if output_format == "pdf":
            from utils.pdf_generator import text_to_pdf
            text_to_pdf(result_content, str(out_path), title=out_name)
            return "application/pdf"
        if output_format == "xlsx":
            self._write_xlsx_output(
                result_content, out_path, str(output_config.get("sheetName") or "Sheet1")
            )
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        encoding = str(output_config.get("outputEncoding") or "utf-8").lower()
        if encoding not in {"utf-8", "gbk"}:
            encoding = "utf-8"
        line_ending = "\r\n" if str(output_config.get("lineEnding") or "").lower() == "crlf" else "\n"
        text_output = result_content.replace("\r\n", "\n").replace("\r", "\n")
        if line_ending != "\n":
            text_output = text_output.replace("\n", line_ending)
        out_path.write_text(text_output, encoding=encoding)
        if output_format == "md":
            return "text/markdown; charset=utf-8"
        return "text/plain; charset=utf-8"

    def _write_xlsx_output(self, content: str, out_path: Path, sheet_name: str = "Sheet1") -> None:
        """将文本、Markdown表格、JSON数组等轻量转换为Excel。"""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        safe_sheet_name = "".join(ch for ch in (sheet_name or "Sheet1") if ch not in r'[]:*?/\\')[:31] or "Sheet1"
        ws.title = safe_sheet_name

        rows = self._content_to_rows(content)
        if not rows:
            rows = [["内容"], [content]]
        for row in rows:
            ws.append([self._to_excel_cell(cell) for cell in row])

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)

    @staticmethod
    def _to_excel_cell(value: Any) -> Any:
        """将 Python 值转为可写入 Excel 单元格的形式。"""
        if isinstance(value, list):
            if not value:
                return ""
            return value[0]
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return "" if value is None else value

    def _content_to_rows(self, content: str) -> List[List[Any]]:
        text = (content or "").strip()
        if not text:
            return []

        # 工作流排序等输出的纯 TSV
        tsv_lines = [ln for ln in text.splitlines() if ln.strip() and "\t" in ln and not ln.strip().startswith("【")]
        if len(tsv_lines) >= 2:
            return [[cell for cell in ln.split("\t")] for ln in tsv_lines]

        try:
            payload = json.loads(text)
            rows = self._json_to_rows(payload)
            if rows:
                return rows
        except Exception:
            pass

        markdown_rows: List[List[str]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not (line.startswith("|") and line.endswith("|")):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and all(c and set(c) <= {"-", ":"} for c in cells):
                continue
            markdown_rows.append(cells)
        if markdown_rows:
            return markdown_rows

        try:
            dialect = csv.Sniffer().sniff(text[:2048], delimiters=",\t;")
            reader = csv.reader(text.splitlines(), dialect)
            rows = [row for row in reader if row]
            if rows and any(len(row) > 1 for row in rows):
                return rows
        except Exception:
            pass

        return [["内容"], *[[line] for line in text.splitlines()]]

    def _json_to_rows(self, payload: Any) -> List[List[Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("entities"), list):
            payload = payload.get("entities")
        if isinstance(payload, dict):
            return [["字段", "值"], *[[key, value] for key, value in payload.items()]]
        if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
            headers: List[str] = []
            for item in payload:
                for key in item.keys():
                    if key not in headers:
                        headers.append(str(key))
            return [headers, *[[item.get(header, "") for header in headers] for item in payload]]
        if isinstance(payload, list):
            return [["值"], *[[item] for item in payload]]
        return []

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
