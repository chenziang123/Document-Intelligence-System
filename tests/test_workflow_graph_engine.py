"""工作流图引擎：多分支多输出节点。"""
from __future__ import annotations

from core.orchestrator.workflow_graph_engine import run_workflow_graph


def _emit_noop(*_args, **_kwargs):
    pass


def test_implicit_fork_reaches_both_output_nodes():
    """数据清洗后分两路，每路各自到达输出节点。"""
    nodes = [
        {"id": "in", "type": "input", "title": "输入"},
        {"id": "clean", "type": "process", "title": "清洗", "schemaKey": "schema-clean"},
        {"id": "agg", "type": "process", "title": "汇总", "schemaKey": "schema-agg"},
        {"id": "out_direct", "type": "output", "title": "直出"},
        {"id": "out_agg", "type": "output", "title": "汇总出"},
    ]
    edges = [
        {"from": "in", "to": "clean"},
        {"from": "clean", "to": "agg"},
        {"from": "clean", "to": "out_direct"},
        {"from": "agg", "to": "out_agg"},
    ]

    def run_process(node: dict, text: str) -> str:
        title = str(node.get("title") or "")
        if title == "清洗":
            return f"{text}|cleaned"
        if title == "汇总":
            return f"{text}|aggregated"
        return text

    outputs = run_workflow_graph(
        nodes,
        edges,
        "raw",
        "demo.txt",
        run_process=run_process,
        emit_progress=_emit_noop,
    )

    by_id = {node_id: content for node_id, content in outputs}
    assert set(by_id) == {"out_direct", "out_agg"}
    assert by_id["out_direct"] == "raw|cleaned"
    assert by_id["out_agg"] == "raw|cleaned|aggregated"
