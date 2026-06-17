"""工作流控制流：分叉合并、循环退出条件。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Set


def collect_controlled_node_ids(workflow_nodes: List[dict]) -> Set[str]:
    """由循环节点托管的处理节点，线性遍历时跳过。"""
    controlled: Set[str] = set()
    for node_dict in workflow_nodes:
        node_type = str(node_dict.get("type", "")).lower()
        if node_type != "control":
            continue
        schema_key = str(node_dict.get("schemaKey", "") or "").strip().lower()
        cv = node_dict.get("configValues") or {}
        if schema_key == "schema-loop":
            for nid in cv.get("bodyNodeIds") or []:
                if nid:
                    controlled.add(str(nid))
    return controlled


def merge_parallel_results(results: List[str], strategy: str) -> str:
    """合并分叉多路输出。"""
    cleaned = [str(r).strip() for r in results if r is not None and str(r).strip()]
    if not cleaned:
        return ""
    strategy = str(strategy or "concat").lower()
    if strategy == "first":
        return cleaned[0]
    if strategy == "last":
        return cleaned[-1]
    if strategy == "longest":
        return max(cleaned, key=len)
    return "\n\n---\n\n".join(cleaned)


def should_exit_loop(
    *,
    iteration: int,
    max_iterations: int,
    before: str,
    after: str,
    exit_condition: str,
    exit_contains_text: str = "",
) -> bool:
    """判断是否退出循环。"""
    condition = str(exit_condition or "unchanged").lower()
    if iteration >= max(1, int(max_iterations or 1)):
        return True
    if condition == "max_only":
        return False
    if condition == "empty":
        return not str(after or "").strip()
    if condition == "unchanged":
        return str(before or "") == str(after or "")
    if condition == "contains":
        needle = str(exit_contains_text or "").strip()
        if needle:
            return needle in str(after or "")
    return False


def run_nodes_in_parallel(
    node_ids: List[str],
    node_map: Dict[str, dict],
    content: str,
    source_name: str,
    run_one: Callable[[dict, str], str],
    *,
    max_workers: int = 4,
) -> List[str]:
    """对多个节点并行执行同一输入内容。"""
    ids = [str(i) for i in node_ids if i and str(i) in node_map]
    if not ids:
        return []

    if len(ids) == 1:
        return [run_one(node_map[ids[0]], content)]

    workers = max(1, min(max_workers, len(ids)))
    results: Dict[str, str] = {}

    def _job(nid: str) -> tuple[str, str]:
        return nid, run_one(node_map[nid], content)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_job, nid): nid for nid in ids}
        for fut in as_completed(futures):
            nid, out = fut.result()
            results[nid] = out

    return [results.get(nid, "") for nid in ids]


def run_loop_body(
    body_node_ids: List[str],
    node_map: Dict[str, dict],
    content: str,
    run_one: Callable[[dict, str], str],
    *,
    max_iterations: int,
    exit_condition: str,
    exit_contains_text: str = "",
) -> str:
    """按顺序重复执行循环体，直到满足退出条件或达到上限。"""
    ids = [str(i) for i in body_node_ids if i and str(i) in node_map]
    if not ids:
        return content

    current = content
    cap = max(1, min(50, int(max_iterations or 5)))
    for iteration in range(1, cap + 1):
        before = current
        for nid in ids:
            current = run_one(node_map[nid], current)
        if should_exit_loop(
            iteration=iteration,
            max_iterations=cap,
            before=before,
            after=current,
            exit_condition=exit_condition,
            exit_contains_text=exit_contains_text,
        ):
            break
    return current
