"""工作流图结构执行引擎（第二阶段：连线、条件分支、分叉汇合）。"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.orchestrator.workflow_control import merge_parallel_results, run_nodes_in_parallel


def edges_from_linear_order(workflow_nodes: List[dict]) -> List[dict]:
    """无连线时按节点列表顺序生成链式边。"""
    edges: List[dict] = []
    ids = [str(n.get("id")) for n in workflow_nodes if n.get("id")]
    for i in range(len(ids) - 1):
        edges.append({"from": ids[i], "to": ids[i + 1], "label": ""})
    return edges


def normalize_edges(raw_edges: Optional[List[dict]], workflow_nodes: List[dict]) -> List[dict]:
    if raw_edges:
        out = []
        for e in raw_edges:
            f = str(e.get("from") or "")
            t = str(e.get("to") or "")
            if f and t:
                out.append({"from": f, "to": t, "label": str(e.get("label") or "")})
        if out:
            return out
    return edges_from_linear_order(workflow_nodes)


def build_adjacency(edges: List[dict]) -> Tuple[Dict[str, List[dict]], Dict[str, List[dict]]]:
    outgoing: Dict[str, List[dict]] = defaultdict(list)
    incoming: Dict[str, List[dict]] = defaultdict(list)
    for e in edges:
        outgoing[e["from"]].append(e)
        incoming[e["to"]].append(e)
    return outgoing, incoming


def find_start_node_id(workflow_nodes: List[dict], incoming: Dict[str, List[dict]]) -> Optional[str]:
    for n in workflow_nodes:
        if str(n.get("type", "")).lower() == "input":
            nid = str(n.get("id", ""))
            if nid and not incoming.get(nid):
                return nid
    for n in workflow_nodes:
        nid = str(n.get("id", ""))
        if nid and not incoming.get(nid):
            return nid
    if workflow_nodes:
        return str(workflow_nodes[0].get("id", ""))
    return None


def evaluate_condition(content: str, config: dict) -> bool:
    ctype = str(config.get("conditionType") or "contains").lower()
    match_text = str(config.get("matchText") or "")
    try:
        min_len = int(config.get("minLength") or 0)
    except (TypeError, ValueError):
        min_len = 0
    text = str(content or "")
    if ctype == "contains":
        return match_text in text
    if ctype == "not_contains":
        return match_text not in text
    if ctype == "empty":
        return not text.strip()
    if ctype == "not_empty":
        return bool(text.strip())
    if ctype == "length_gt":
        return len(text) > min_len
    if ctype == "length_lt":
        return len(text) < min_len
    return True


def pick_edge_by_label(edges: List[dict], label: str) -> Optional[dict]:
    label = str(label or "")
    for e in edges:
        if str(e.get("label") or "") == label:
            return e
    for e in edges:
        if not str(e.get("label") or ""):
            return e
    return edges[0] if edges else None


def pick_single_next(outgoing: Dict[str, List[dict]], node_id: str) -> Optional[str]:
    outs = outgoing.get(node_id) or []
    if not outs:
        return None
    e = pick_edge_by_label(outs, "")
    return str(e["to"]) if e else None


def collect_controlled_from_graph(workflow_nodes: List[dict]) -> Set[str]:
    controlled: Set[str] = set()
    for n in workflow_nodes:
        t = str(n.get("type", "")).lower()
        sk = str(n.get("schemaKey", "") or "").strip().lower()
        cv = n.get("configValues") or {}
        if t == "control" and sk == "schema-loop":
            for nid in cv.get("bodyNodeIds") or []:
                if nid:
                    controlled.add(str(nid))
    return controlled


class GraphExecutionContext:
    """图执行上下文，供 executor 注入回调。"""

    def __init__(
        self,
        *,
        node_map: Dict[str, dict],
        outgoing: Dict[str, List[dict]],
        node_index_map: Dict[str, int],
        total_nodes: int,
        source_name: str,
        run_process: Callable[[dict, str], str],
        emit_progress: Callable[..., None],
        controlled_ids: Set[str],
    ):
        self.node_map = node_map
        self.outgoing = outgoing
        self.node_index_map = node_index_map
        self.total_nodes = total_nodes
        self.source_name = source_name
        self.run_process = run_process
        self.emit_progress = emit_progress
        self.controlled_ids = controlled_ids
        self.branch_outputs: List[Tuple[str, str]] = []
        self._branch_lock = threading.Lock()


def _fan_out_from_node(
    ctx: GraphExecutionContext,
    node_id: str,
    content: str,
    *,
    stop_ids: Optional[Set[str]] = None,
) -> bool:
    """节点有多条出边时并行执行各路分支。返回 True 表示已分叉（调用方应结束当前路径）。"""
    outs = ctx.outgoing.get(node_id) or []
    if len(outs) <= 1:
        return False

    target_ids = [str(e["to"]) for e in outs if e.get("to")]
    if not target_ids:
        return False

    stops = stop_ids or set()

    def _run_implicit_branch(nd: dict, text: str) -> str:
        tid = str(nd.get("id", ""))
        if not tid:
            return text
        return execute_from_node(ctx, tid, text, stop_ids=stops)

    run_nodes_in_parallel(
        target_ids,
        ctx.node_map,
        content,
        ctx.source_name,
        _run_implicit_branch,
    )
    return True


def execute_from_node(
    ctx: GraphExecutionContext,
    node_id: str,
    content: str,
    *,
    stop_ids: Optional[Set[str]] = None,
) -> str:
    """从指定节点开始沿图执行，直到输出节点、汇合停止点或无路可走。"""
    current_id: Optional[str] = node_id
    result_content = content
    visited_steps = 0
    max_steps = max(len(ctx.node_map) * 20, 50)
    stops = stop_ids or set()

    while current_id and visited_steps < max_steps:
        if current_id in stops:
            return result_content
        visited_steps += 1
        node_dict = ctx.node_map.get(current_id)
        if not node_dict:
            break

        node_type = str(node_dict.get("type", "")).lower()
        schema_key = str(node_dict.get("schemaKey", "") or "").strip().lower()
        config_values = node_dict.get("configValues", {}) or {}
        node_title = str(node_dict.get("title", "") or node_dict.get("type", ""))
        nindex = ctx.node_index_map.get(current_id, 1)

        if current_id in ctx.controlled_ids and schema_key not in {
            "schema-loop",
            "schema-condition",
            "schema-fork",
            "schema-join",
        }:
            current_id = pick_single_next(ctx.outgoing, current_id)
            continue

        if node_type == "input":
            ctx.emit_progress(
                node_dict, "completed", f"输入节点完成: {node_title}", progress_pct=100
            )
            if _fan_out_from_node(ctx, current_id, result_content, stop_ids=stops):
                return result_content
            current_id = pick_single_next(ctx.outgoing, current_id)
            continue

        if node_type == "output":
            ctx.emit_progress(node_dict, "running", f"输出节点开始: {node_title}", progress_pct=30)
            ctx.emit_progress(node_dict, "completed", f"输出节点完成: {node_title}", progress_pct=100)
            with ctx._branch_lock:
                ctx.branch_outputs.append((current_id, result_content))
            return result_content

        if node_type == "control" and schema_key == "schema-condition":
            ok = evaluate_condition(result_content, config_values)
            branch_label = "true" if ok else "false"
            ctx.emit_progress(
                node_dict,
                "completed",
                f"条件判断: {node_title} → {branch_label}",
                progress_pct=100,
            )
            outs = ctx.outgoing.get(current_id) or []
            nxt = pick_edge_by_label(outs, branch_label)
            current_id = str(nxt["to"]) if nxt else None
            continue

        if node_type == "control" and schema_key == "schema-fork":
            outs = ctx.outgoing.get(current_id) or []
            branch_ids = [str(e["to"]) for e in outs]
            merge_strategy = config_values.get("mergeStrategy") or "concat"
            join_id = str(config_values.get("joinNodeId") or "").strip()
            ctx.emit_progress(
                node_dict,
                "running",
                f"分叉开始: {node_title}（{len(branch_ids)} 路）",
                progress_pct=20,
            )

            branch_stop_ids = {join_id} if join_id else set()

            def _run_branch_target(nd: dict, text: str) -> str:
                tid = str(nd.get("id", ""))
                if not tid:
                    return text
                if branch_stop_ids:
                    return execute_from_node(ctx, tid, text, stop_ids=branch_stop_ids)
                ctx.emit_progress(nd, "running", f"分支执行: {nd.get('title', '')}", progress_pct=30)
                out = ctx.run_process(nd, text)
                ctx.emit_progress(nd, "completed", f"分支完成: {nd.get('title', '')}", progress_pct=100)
                return out

            branch_outputs = run_nodes_in_parallel(
                branch_ids,
                ctx.node_map,
                result_content,
                ctx.source_name,
                _run_branch_target,
            )
            result_content = merge_parallel_results(branch_outputs, merge_strategy)
            ctx.emit_progress(node_dict, "completed", f"分叉完成: {node_title}", progress_pct=100)
            if join_id and join_id in ctx.node_map:
                # 先进入汇合节点，以便上报「汇合」进度（不可直接跳到汇合之后）
                current_id = join_id
            elif branch_ids:
                current_id = pick_single_next(ctx.outgoing, branch_ids[0])
            else:
                current_id = None
            continue

        if node_type == "control" and schema_key == "schema-join":
            ctx.emit_progress(node_dict, "running", f"汇合中: {node_title}", progress_pct=50)
            ctx.emit_progress(node_dict, "completed", f"汇合: {node_title}", progress_pct=100)
            if _fan_out_from_node(ctx, current_id, result_content, stop_ids=stops):
                return result_content
            current_id = pick_single_next(ctx.outgoing, current_id)
            continue

        if node_type == "control" and schema_key == "schema-loop":
            from core.orchestrator.workflow_control import run_loop_body

            body_ids = config_values.get("bodyNodeIds") or []
            max_iter = int(config_values.get("maxIterations") or 5)
            exit_condition = config_values.get("exitCondition") or "unchanged"
            exit_text = config_values.get("exitContainsText") or ""
            ctx.emit_progress(node_dict, "running", f"循环开始: {node_title}", progress_pct=20)

            def _run_loop(nd: dict, txt: str) -> str:
                ctx.emit_progress(nd, "running", f"循环执行: {nd.get('title', '')}", progress_pct=40)
                out = ctx.run_process(nd, txt)
                ctx.emit_progress(nd, "completed", f"循环步骤完成: {nd.get('title', '')}", progress_pct=100)
                return out

            result_content = run_loop_body(
                body_ids,
                ctx.node_map,
                result_content,
                _run_loop,
                max_iterations=max_iter,
                exit_condition=exit_condition,
                exit_contains_text=exit_text,
            )
            ctx.emit_progress(node_dict, "completed", f"循环完成: {node_title}", progress_pct=100)
            if _fan_out_from_node(ctx, current_id, result_content, stop_ids=stops):
                return result_content
            current_id = pick_single_next(ctx.outgoing, current_id)
            continue

        # 普通处理节点
        ctx.emit_progress(
            node_dict, "running", f"处理节点开始: {node_title}", progress_pct=30
        )
        result_content = ctx.run_process(node_dict, result_content)
        ctx.emit_progress(
            node_dict, "completed", f"处理节点完成: {node_title}", progress_pct=100
        )
        if _fan_out_from_node(ctx, current_id, result_content, stop_ids=stops):
            return result_content
        current_id = pick_single_next(ctx.outgoing, current_id)

    return result_content


_GRAPH_CONTROL_SCHEMAS = frozenset({"schema-condition", "schema-fork", "schema-join"})


def should_use_graph_engine(
    workflow_edges: Optional[List[dict]],
    workflow_nodes: Optional[List[dict]] = None,
) -> bool:
    """存在自定义连线或图结构控制节点时使用图执行。"""
    if workflow_edges:
        return True
    if workflow_nodes:
        for n in workflow_nodes:
            sk = str(n.get("schemaKey") or "").strip().lower()
            if sk in _GRAPH_CONTROL_SCHEMAS:
                return True
    return False


def run_workflow_graph(
    workflow_nodes: List[dict],
    workflow_edges: Optional[List[dict]],
    initial_content: str,
    source_name: str,
    *,
    run_process: Callable[[dict, str], str],
    emit_progress: Callable[[dict, str, str, int], None],
) -> List[Tuple[str, str]]:
    """执行工作流图，返回各输出节点 (node_id, content) 列表。"""
    edges = normalize_edges(workflow_edges, workflow_nodes)
    node_map = {str(n.get("id", "")): n for n in workflow_nodes if n.get("id")}
    outgoing, incoming = build_adjacency(edges)
    controlled = collect_controlled_from_graph(workflow_nodes)
    node_index_map = {
        str(n.get("id", "")): idx for idx, n in enumerate(workflow_nodes, 1) if n.get("id")
    }
    start_id = find_start_node_id(workflow_nodes, incoming)
    if not start_id:
        raise RuntimeError("工作流图中找不到起始节点")

    ctx = GraphExecutionContext(
        node_map=node_map,
        outgoing=outgoing,
        node_index_map=node_index_map,
        total_nodes=max(len(workflow_nodes), 1),
        source_name=source_name,
        run_process=run_process,
        emit_progress=lambda nd, st, msg, progress_pct=50: emit_progress(nd, st, msg, progress_pct),
        controlled_ids=controlled,
    )
    execute_from_node(ctx, start_id, initial_content)
    return list(ctx.branch_outputs)
