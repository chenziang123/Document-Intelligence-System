"""MD 适配器独立动作测试（10用例）。"""

from __future__ import annotations

from pathlib import Path

from core.agents.agent_a.md_adapter import MdAdapter


def _write_md(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "sample.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_md_case_01_bold_heading_target_changes(tmp_path: Path):
    p = _write_md(tmp_path, "# 标题A\n\n正文B\n")
    a = MdAdapter(str(p))
    before = a.content
    a.apply_action({"action_type": "bold_heading", "target": {"level": 1}, "params": {}})
    assert "# **标题A**" in a.content
    assert "正文B" in a.content
    assert before != a.content


def test_md_case_02_bold_heading_non_target_not_changed(tmp_path: Path):
    p = _write_md(tmp_path, "## 二级标题\n\n普通段\n")
    a = MdAdapter(str(p))
    before = a.content
    a.apply_action({"action_type": "bold_heading", "target": {"level": 1}, "params": {}})
    assert a.content == before


def test_md_case_03_reorder_paragraphs_changes_order(tmp_path: Path):
    p = _write_md(tmp_path, "A段\n\nB段\n\nC段\n")
    a = MdAdapter(str(p))
    a.apply_action({"action_type": "reorder_paragraphs", "params": {"from": 3, "to": 1}, "target": {}})
    assert a.content.startswith("C段")
    assert "A段" in a.content and "B段" in a.content


def test_md_case_04_reorder_out_of_range_no_change(tmp_path: Path):
    p = _write_md(tmp_path, "A\n\nB\n")
    a = MdAdapter(str(p))
    before = a.content
    result = a.apply_action({"action_type": "reorder_paragraphs", "params": {"from": 5, "to": 1}, "target": {}})
    assert result.details.get("moved") is False
    assert a.content == before


def test_md_case_05_unify_style_list_marker(tmp_path: Path):
    p = _write_md(tmp_path, "* 项目1\n+ 项目2\n")
    a = MdAdapter(str(p))
    a.apply_action({"action_type": "unify_style", "target": {}, "params": {}})
    assert "- 项目1" in a.content
    assert "- 项目2" in a.content


def test_md_case_06_unify_style_heading_blank_line_rule(tmp_path: Path):
    p = _write_md(tmp_path, "# 标题\n正文\n")
    a = MdAdapter(str(p))
    a.apply_action({"action_type": "unify_style", "target": {}, "params": {}})
    assert "# 标题\n\n正文" in a.content


def test_md_case_07_replace_text_target_only(tmp_path: Path):
    p = _write_md(tmp_path, "苹果 和 香蕉\n")
    a = MdAdapter(str(p))
    a.apply_action({"action_type": "replace_text", "params": {"find": "苹果", "replace": "橙子"}, "target": {}})
    assert "橙子" in a.content
    assert "香蕉" in a.content
    assert "苹果" not in a.content


def test_md_case_08_replace_text_miss_non_target_unchanged(tmp_path: Path):
    p = _write_md(tmp_path, "苹果\n")
    a = MdAdapter(str(p))
    before = a.content
    a.apply_action({"action_type": "replace_text", "params": {"find": "不存在", "replace": "X"}, "target": {}})
    assert a.content == before


def test_md_case_09_extract_content_fields(tmp_path: Path):
    p = _write_md(tmp_path, "# 标题\n\n姓名: 张三\n年龄: 18\n")
    a = MdAdapter(str(p))
    result = a.apply_action({"action_type": "extract_content", "params": {"fields": ["姓名", "年龄"]}, "target": {}})
    fields = result.details.get("fields", {})
    assert fields.get("姓名") == "张三"
    assert fields.get("年龄") == "18"


def test_md_case_10_remove_blank_lines_target_change_non_target_keep(tmp_path: Path):
    p = _write_md(tmp_path, "A\n\n\n\nB\n")
    a = MdAdapter(str(p))
    a.apply_action({"action_type": "remove_blank_lines", "params": {}, "target": {}})
    assert "\n\n\n" not in a.content
    assert "A" in a.content and "B" in a.content


def test_md_case_11_reorder_never_before_main_title(tmp_path: Path):
    p = _write_md(tmp_path, "# 总标题\n\n发布单位\n发布时间：2024-01-01\n\n第一段\n\n第二段\n\n第三段\n")
    a = MdAdapter(str(p))
    result = a.apply_action({"action_type": "reorder_paragraphs", "params": {"from": 3, "to": 1}, "target": {}})
    assert result.details.get("moved") is True
    assert a.content.startswith("# 总标题")
    assert "第三段\n\n第一段\n\n第二段" in a.content
