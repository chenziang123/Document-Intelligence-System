"""TXT 适配器独立动作测试（10用例）。"""

from __future__ import annotations

from pathlib import Path

from core.agents.agent_a.txt_adapter import TxtAdapter


def _write_txt(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "sample.txt"
    p.write_text(content, encoding="utf-8")
    return p


def test_txt_case_01_split_paragraphs_blocks_count(tmp_path: Path):
    p = _write_txt(tmp_path, "第一段\n\n第二段\n\n第三段\n")
    a = TxtAdapter(str(p))
    result = a.apply_action({"action_type": "split_paragraphs", "params": {}, "target": {}})
    assert result.details.get("count") == 3


def test_txt_case_02_split_paragraphs_non_target_not_mutated(tmp_path: Path):
    p = _write_txt(tmp_path, "A\n\nB\n")
    a = TxtAdapter(str(p))
    before = a.content
    a.apply_action({"action_type": "split_paragraphs", "params": {}, "target": {}})
    assert a.content == before


def test_txt_case_03_reorder_paragraphs_changes_order(tmp_path: Path):
    p = _write_txt(tmp_path, "A\n\nB\n\nC\n")
    a = TxtAdapter(str(p))
    a.apply_action({"action_type": "reorder_paragraphs", "params": {"from": 1, "to": 3}, "target": {}})
    assert a.content.startswith("B")
    assert a.content.strip().endswith("A")


def test_txt_case_04_reorder_invalid_no_change(tmp_path: Path):
    p = _write_txt(tmp_path, "A\n\nB\n")
    a = TxtAdapter(str(p))
    before = a.content
    result = a.apply_action({"action_type": "reorder_paragraphs", "params": {"from": 9, "to": 1}, "target": {}})
    assert result.details.get("moved") is False
    assert a.content == before


def test_txt_case_05_replace_text_target_changes(tmp_path: Path):
    p = _write_txt(tmp_path, "南京 统计 公报\n")
    a = TxtAdapter(str(p))
    a.apply_action({"action_type": "replace_text", "params": {"find": "统计", "replace": "数据"}, "target": {}})
    assert "数据" in a.content
    assert "统计" not in a.content


def test_txt_case_06_replace_text_non_target_not_changed(tmp_path: Path):
    p = _write_txt(tmp_path, "南京\n")
    a = TxtAdapter(str(p))
    before = a.content
    a.apply_action({"action_type": "replace_text", "params": {"find": "上海", "replace": "北京"}, "target": {}})
    assert a.content == before


def test_txt_case_07_extract_content_fields(tmp_path: Path):
    p = _write_txt(tmp_path, "姓名: 李四\n年龄: 20\n\n备注: 正常\n")
    a = TxtAdapter(str(p))
    result = a.apply_action({"action_type": "extract_content", "params": {"fields": ["姓名", "年龄"]}, "target": {}})
    fields = result.details.get("fields", {})
    assert fields.get("姓名") == "李四"
    assert fields.get("年龄") == "20"


def test_txt_case_08_extract_content_non_target_not_mutated(tmp_path: Path):
    p = _write_txt(tmp_path, "A\n\nB\n")
    a = TxtAdapter(str(p))
    before = a.content
    a.apply_action({"action_type": "extract_content", "params": {"fields": ["姓名"]}, "target": {}})
    assert a.content == before


def test_txt_case_09_remove_blank_lines_changes_only_spacing(tmp_path: Path):
    p = _write_txt(tmp_path, "A\n\n\n\nB\n")
    a = TxtAdapter(str(p))
    a.apply_action({"action_type": "remove_blank_lines", "params": {}, "target": {}})
    assert "\n\n\n" not in a.content
    assert "A" in a.content and "B" in a.content


def test_txt_case_10_unify_style_preserves_text_content(tmp_path: Path):
    p = _write_txt(tmp_path, "A   B\n\n\nC\n")
    a = TxtAdapter(str(p))
    a.apply_action({"action_type": "unify_style", "params": {}, "target": {}})
    assert "A B" in a.content
    assert "C" in a.content


def test_txt_case_11_reorder_fallback_split_by_line(tmp_path: Path):
    p = _write_txt(tmp_path, "第一行\n第二行\n第三行\n")
    a = TxtAdapter(str(p))
    result = a.apply_action({"action_type": "reorder_paragraphs", "params": {"from": 3, "to": 1}, "target": {}})
    assert result.details.get("moved") is True
    assert a.content.startswith("第三行")


def test_txt_case_12_reorder_should_not_move_heading_units(tmp_path: Path):
    p = _write_txt(tmp_path, "总标题\n一、发展概况\n（一）行业规模\n正文A\n正文B\n正文C\n")
    a = TxtAdapter(str(p))
    result = a.apply_action({"action_type": "reorder_paragraphs", "params": {"from": 3, "to": 1}, "target": {}})
    assert result.details.get("moved") is True
    lines = [ln for ln in a.content.splitlines() if ln.strip()]
    # 标题行保持在原位置，不参与正文重排
    assert lines[0] == "总标题"
    assert lines[1] == "一、发展概况"
    assert lines[2] == "（一）行业规模"
    assert result.details.get("locked_prefix_units", 0) >= 1
