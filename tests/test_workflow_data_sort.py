"""数据处理排序单元测试。"""
from __future__ import annotations

from api.routers.workflows_processors import _data_process_sort_table


def test_sort_table_mixed_numeric_and_text_in_same_column():
    content = "名称\t金额\n苹果\t10\n香蕉\t2\n合计\t-\n"
    result = _data_process_sort_table(
        content,
        {"sortColumn": "金额", "sortOrder": "asc"},
    )
    assert result is not None
    lines = result.splitlines()
    assert lines[0] == "名称\t金额"
    # 数字升序在前，非数字与空值不应触发 str/float 比较异常
    assert "香蕉\t2" in lines
    assert "苹果\t10" in lines
    assert "合计\t-" in lines


def test_sort_table_numeric_desc():
    content = "名称\t金额\n苹果\t10\n香蕉\t2\n"
    result = _data_process_sort_table(
        content,
        {"sortColumn": "金额", "sortOrder": "desc"},
    )
    assert result is not None
    rows = result.splitlines()[1:]
    assert rows[0].endswith("10")
    assert rows[1].endswith("2")


def test_sort_table_treats_null_as_zero_when_prompt_says_so():
    content = "名称\t销售额\n苹果\t10\n香蕉\tnull\n橙子\t2\n"
    result = _data_process_sort_table(
        content,
        {"sortColumn": "销售额", "sortOrder": "asc", "prompt": "空值为null，按照0处理"},
    )
    assert result is not None
    rows = result.splitlines()[1:]
    assert rows[0].startswith("香蕉")
    assert rows[0].endswith("null")


def test_sort_table_mixed_numeric_text_no_type_error():
    content = "名称\t销售额\nA\t100\nB\tpending\nC\t50\n"
    result = _data_process_sort_table(
        content,
        {"sortColumn": "销售额", "sortOrder": "asc"},
    )
    assert result is not None
    assert len(result.splitlines()) == 4


def test_fill_null_table_replaces_empty_cells():
    from api.routers.workflows_processors import _data_process_fill_null_table

    content = "name\tamount\napple\t\nbanana\t2\n"
    result = _data_process_fill_null_table(
        content,
        {"fillColumns": "amount", "fillValue": "null"},
    )
    assert result is not None
    assert "apple\tnull" in result
    assert "banana\t2" in result
