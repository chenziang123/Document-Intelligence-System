"""Tests for additional recognized actions and compatibility checks."""

from __future__ import annotations

from core.agents.agent_a import AgentA, build_action_plan_from_instruction, parse_instruction_rule_first
from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType


def test_replace_text_action_recognition_and_params_extraction():
    plan = build_action_plan_from_instruction('把"甲方"替换为"乙方"')
    action = plan.actions[0]
    assert action.action_type.value == "replace_text"
    assert action.params.get("find") == "甲方"
    assert action.params.get("replace") == "乙方"


def test_replace_text_in_compound_instruction_should_not_swallow_following_clauses():
    instruction = "标题加粗，把南京市替换为南京全市，插入目录，提取内容"
    plan = build_action_plan_from_instruction(instruction)
    replace_actions = [a for a in plan.actions if a.action_type.value == "replace_text"]
    assert replace_actions, "应识别到 replace_text 动作"

    action = replace_actions[0]
    assert action.params.get("find") == "南京市"
    assert action.params.get("replace") == "南京全市"


def test_insert_toc_action_recognition():
    plan = build_action_plan_from_instruction("请给文档插入目录")
    assert plan.actions[0].action_type.value == "insert_toc"


def test_auto_column_width_action_recognition_for_excel_scope():
    plan = build_action_plan_from_instruction("请把这个 excel 自动列宽")
    assert plan.actions[0].action_type.value == "auto_column_width"
    assert plan.file_scope == "xlsx"


def test_freeze_header_row_action_recognition():
    plan = build_action_plan_from_instruction("冻结首行作为表头")
    assert plan.actions[0].action_type.value == "freeze_header_row"


def test_remove_blank_lines_action_recognition():
    plan = build_action_plan_from_instruction("删除空行并清理文本")
    assert plan.actions[0].action_type.value == "remove_blank_lines"


def test_auto_column_width_on_docx_should_be_rejected_with_suggestion():
    agent = AgentA()
    task_spec = TaskSpec(
        task_type=TaskType.DOCUMENT_EDITING,
        instruction="请自动列宽",
        source_files=[FileInfo(path="dummy.docx", file_type=FileType.DOCX, name="dummy.docx")],
    )
    result = agent.execute(task_spec)

    assert result.success is False
    assert result.data["status"] == "precheck_failed"
    assert any("建议" in (s or "") or "改为" in (s or "") for s in result.data.get("suggestions", []))


def test_set_font_family_action_recognition():
    plan = build_action_plan_from_instruction("把正文字体改为宋体")
    assert plan.actions[0].action_type.value == "set_font_family"
    assert plan.actions[0].params.get("font_name") == "宋体"


def test_set_font_color_action_recognition():
    plan = build_action_plan_from_instruction("把标题字体颜色改为红色")
    assert plan.actions[0].action_type.value == "set_font_color"
    assert plan.actions[0].params.get("color") == "FF0000"


def test_set_font_size_action_recognition():
    plan = build_action_plan_from_instruction("把正文字号改成小四")
    assert plan.actions[0].action_type.value == "set_font_size"
    assert float(plan.actions[0].params.get("size_pt")) == 12.0


def test_set_alignment_action_recognition():
    plan = build_action_plan_from_instruction("正文设置为两端对齐")
    assert plan.actions[0].action_type.value == "set_paragraph_alignment"
    assert plan.actions[0].params.get("alignment") == "justify"


def test_set_line_spacing_action_recognition():
    plan = build_action_plan_from_instruction("正文行距设置为1.5倍")
    assert plan.actions[0].action_type.value == "set_line_spacing"
    assert float(plan.actions[0].params.get("line_spacing")) == 1.5


def test_bold_heading_should_cover_level1_and_level2_when_both_requested():
    plan = build_action_plan_from_instruction("将所有一级和二级标题加粗")
    heading_actions = [a for a in plan.actions if a.action_type.value == "bold_heading"]
    levels = sorted({int(a.target.get("level", 0)) for a in heading_actions})
    assert levels == [1, 2]


def test_colloquial_replace_and_extract_should_be_recognized_stably():
    instruction = "再把文里出现的南京市统一换成南京全市；最后把这几个数据单独捞出来做结构化结果给我：地区生产总值、常住人口、一般公共预算收入、进出口总额。"
    plan = build_action_plan_from_instruction(instruction)

    replace_actions = [a for a in plan.actions if a.action_type.value == "replace_text"]
    assert replace_actions
    assert replace_actions[0].params.get("find") == "南京市"
    assert replace_actions[0].params.get("replace") == "南京全市"

    extract_actions = [a for a in plan.actions if a.action_type.value == "extract_content"]
    assert extract_actions
    fields = extract_actions[0].params.get("fields", [])
    assert "地区生产总值" in fields
    assert "常住人口" in fields
    assert "一般公共预算收入" in fields
    assert "进出口总额" in fields


def test_body_style_actions_should_keep_body_scope():
    instruction = "将正文字号设为小四，正文设置为两端对齐，正文行距设置为1.5倍。"
    payload = parse_instruction_rule_first(instruction)

    body_style_actions = [
        a
        for a in payload.get("actions", [])
        if a.get("action_type") in {"set_font_size", "set_paragraph_alignment", "set_line_spacing"}
    ]
    assert body_style_actions, "应识别到正文字体/对齐/行距动作"
    assert all(str((a.get("target") or {}).get("scope", "")).lower() == "body" for a in body_style_actions)


def test_replace_pair_should_extract_precisely():
    instruction = "将南京市统一换成南京全市。"
    payload = parse_instruction_rule_first(instruction)
    replace_actions = [a for a in payload.get("actions", []) if a.get("action_type") == "replace_text"]
    assert replace_actions, "应识别到 replace_text 动作"

    action = replace_actions[0]
    assert (action.get("params") or {}).get("find") == "南京市"
    assert (action.get("params") or {}).get("replace") == "南京全市"


def test_parser_should_recognize_section_scoped_color_and_body_first_line_indent():
    instruction = "将这份文件中所有“综合”题目下的内容变为红色，并将所有正文段落进行首行缩进。"
    payload = parse_instruction_rule_first(instruction)

    color_actions = [a for a in payload.get("actions", []) if a.get("action_type") == "set_font_color"]
    assert color_actions, "应识别到 set_font_color 动作"
    color_target = color_actions[0].get("target", {})
    assert color_target.get("scope") == "section_content"
    assert color_target.get("section_title") == "综合"
    assert (color_actions[0].get("params") or {}).get("color") == "FF0000"

    indent_actions = [a for a in payload.get("actions", []) if a.get("action_type") == "set_first_line_indent"]
    assert indent_actions, "应识别到 set_first_line_indent 动作"
    assert (indent_actions[0].get("target") or {}).get("scope") == "body"
    assert float((indent_actions[0].get("params") or {}).get("indent_pt", 0)) == 24.0
