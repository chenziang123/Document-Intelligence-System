"""
Markdown / Plain Text → PDF 生成器（基于 reportlab）。
支持中文、多级标题、代码块、表格。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 字体路径（Windows 常用中文字体，优先使用系统自带）
FONT_DIR = Path("C:/WINDOWS/Fonts")
CHINESE_FONT_CANDIDATES = [
    ("msyh.ttc", "Microsoft YaHei"),
    ("msyhbd.ttc", "Microsoft YaHei Bold"),
    ("simhei.ttf", "SimHei"),
    ("simsun.ttc", "SimSun"),
    ("NotoSansSC-VF.ttf", "NotoSansSC"),
]

# 全局注册字体别名（模块级别只注册一次）
_font_normal: str = "Helvetica"
_font_bold: str = "Helvetica-Bold"
_font_registered: bool = False
_HIGHLIGHT_BG = "#FFF176"


def _register_chinese_font() -> None:
    """注册中文字体到 reportlab，全局只执行一次。"""
    global _font_normal, _font_bold, _font_registered
    if _font_registered:
        return
    _font_registered = True

    registered: dict[str, str] = {}
    for font_file, alias in [
        ("msyh.ttc", "ChineseFont"),
        ("simhei.ttf", "ChineseFont"),
        ("simsun.ttc", "ChineseFont"),
        ("NotoSansSC-VF.ttf", "ChineseFont"),
        ("msyhbd.ttc", "ChineseFontBold"),
        ("simhei.ttf", "ChineseFontBold"),
    ]:
        p = FONT_DIR / font_file
        if not p.exists() or alias in registered:
            continue
        try:
            pdfmetrics.registerFont(TTFont(alias, str(p)))
            registered[alias] = str(p)
        except Exception:
            continue

    if "ChineseFont" in registered:
        _font_normal = "ChineseFont"
    if "ChineseFontBold" in registered:
        _font_bold = "ChineseFontBold"
    elif "ChineseFont" in registered:
        _font_bold = "ChineseFont"


def _get_fonts() -> tuple:
    _register_chinese_font()
    return _font_normal, _font_bold


def prepare_text_for_pdf(text: str) -> str:
    """为 PDF 渲染预处理文本，保留关键词高亮结构并便于着色。"""
    raw = (text or "").strip()
    if not raw:
        return raw
    if "【高亮结果】" not in raw:
        return raw

    kw_part = ""
    if "【关键词】" in raw:
        kw_start = raw.find("【关键词】")
        hl_start = raw.find("【高亮结果】")
        if kw_start < hl_start:
            kw_part = raw[kw_start:hl_start].strip()

    body = raw.split("【高亮结果】", 1)[1].strip()
    parts: List[str] = []
    if kw_part:
        parts.append(kw_part)
    parts.append("【高亮结果】")
    parts.append(body)
    return "\n\n".join(parts)


def _is_keyword_highlight_document(text: str) -> bool:
    """是否为关键词高亮节点的结构化输出。"""
    return "【高亮结果】" in (text or "")


def text_to_pdf(
    text: str,
    output_path: str | Path,
    title: str = "",
    font_size: int = 11,
    line_spacing: float = 1.5,
) -> Path:
    """
    将 markdown 或纯文本内容渲染为 PDF 文件。

    - markdown 标题 (# ## ###) → 加大加粗
    - 代码块 (``` ```) → 等宽灰色背景
    - 表格 (| ... |) → 表格样式
    - 空行 → Spacer
    - 其余 → 正文
    - 仅关键词高亮节点输出（含【高亮结果】段）中的 **词** 才渲染黄色底纹
    """
    path = Path(output_path)
    text = prepare_text_for_pdf(text)
    keyword_highlight_doc = _is_keyword_highlight_document(text)
    in_highlight_section = False
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title or path.stem,
    )

    fn_normal, fn_bold = _get_fonts()

    def sty(name: str, **kwargs) -> ParagraphStyle:
        return ParagraphStyle(name, **kwargs)

    def sty_copy(base: ParagraphStyle, **kwargs) -> ParagraphStyle:
        """基于已有样式复制，只取 style 相关的属性。"""
        base_dict = {k: v for k, v in base.__dict__.items()
                     if k not in ('_name', 'parent', 'name')}
        base_dict.update(kwargs)
        return ParagraphStyle("_copied", **base_dict)

    s_title = sty("MyTitle", fontName=fn_bold, fontSize=22, leading=28,
                  alignment=TA_CENTER, spaceAfter=12, textColor=colors.HexColor("#1a1a2e"))
    s_h1 = sty("MyH1", fontName=fn_bold, fontSize=18, leading=24,
               spaceBefore=18, spaceAfter=8, textColor=colors.HexColor("#16213e"))
    s_h2 = sty("MyH2", fontName=fn_bold, fontSize=15, leading=20,
               spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#0f3460"))
    s_section = sty("MySection", fontName=fn_bold, fontSize=14, leading=20,
                  spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#0f3460"))
    s_h3 = sty("MyH3", fontName=fn_bold, fontSize=13, leading=18,
               spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1a1a2e"))
    s_body = sty("MyBody", fontName=fn_normal, fontSize=font_size,
                 leading=font_size * line_spacing, spaceAfter=4,
                 textColor=colors.HexColor("#333333"))
    s_code = sty("MyCode", fontName="Courier", fontSize=9, leading=13,
                 spaceBefore=4, spaceAfter=4, leftIndent=16,
                 textColor=colors.HexColor("#2d2d2d"))
    s_th = sty("MyTh", fontName=fn_bold, fontSize=font_size - 1, leading=14,
               alignment=TA_CENTER, textColor=colors.white)
    s_td = sty("MyTd", fontName=fn_normal, fontSize=font_size - 1, leading=14,
               textColor=colors.HexColor("#333333"))
    s_quote = sty("MyQuote", fontName=fn_normal, fontSize=font_size,
                  leading=font_size * line_spacing, leftIndent=20, rightIndent=20,
                  spaceAfter=4, textColor=colors.HexColor("#555555"))

    story: List = []

    if title:
        story.append(Paragraph(title, s_title))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 12))

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        use_highlight = keyword_highlight_doc and in_highlight_section

        # 关键词高亮分段标题
        if stripped == "【关键词】":
            in_highlight_section = False
            use_highlight = False
            story.append(Paragraph(_esc(stripped), s_section))
        elif stripped == "【高亮结果】":
            in_highlight_section = True
            use_highlight = True
            story.append(Paragraph(_esc(stripped), s_section))
        # 标题
        elif stripped.startswith("### "):
            story.append(Paragraph(_render(stripped[4:], s_h3, highlight=use_highlight), s_h3))
        elif stripped.startswith("## "):
            story.append(Paragraph(_render(stripped[3:], s_h2, highlight=use_highlight), s_h2))
        elif stripped.startswith("# "):
            story.append(Paragraph(_render(stripped[2:], s_h1, highlight=use_highlight), s_h1))
        # 代码块
        elif stripped.startswith("```"):
            code_lines: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(_esc(lines[i]))
                i += 1
            story.append(Paragraph("<br/>".join(code_lines), s_code))
            story.append(Spacer(1, 6))
        # 表格
        elif stripped.startswith("|") and stripped.endswith("|"):
            rows, i = _parse_table(lines, i)
            if rows:
                ncols = len(rows[0])
                col_w = (A4[0] - 4 * cm) / max(ncols, 1)
                tbl_data = []
                for ri, row in enumerate(rows):
                    p_row = []
                    for ci in range(ncols):
                        cell = row[ci] if ci < len(row) else ""
                        p_row.append(
                            Paragraph(
                                _render(cell, s_th if ri == 0 else s_td, highlight=False),
                                s_th if ri == 0 else s_td,
                            )
                        )
                    tbl_data.append(p_row)
                tbl = Table(tbl_data, colWidths=[col_w] * ncols, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3460")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), fn_bold),
                    ("FONTSIZE", (0, 0), (-1, -1), font_size - 1),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f9f9f9")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 10))
        # 引用
        elif stripped.startswith("> "):
            story.append(Paragraph(_render(stripped[2:], s_body, highlight=use_highlight), s_quote))
        # 列表
        elif re.match(r"^(\s*)[-*+]\s+", stripped) or re.match(r"^(\s*)\d+\.\s+", stripped):
            m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)", stripped)
            if m:
                indent, bullet, rest = m.groups()
                lvl = len(indent) // 2
                story.append(
                    Paragraph(
                        _render(f"{'  ' * lvl}{bullet} {rest}", s_body, highlight=use_highlight),
                        sty_copy(s_body, leftIndent=16 + lvl * 16),
                    )
                )
        # 空行
        elif not stripped:
            story.append(Spacer(1, 6))
        # 正文
        else:
            story.append(Paragraph(_render(stripped, s_body, highlight=use_highlight), s_body))

        i += 1

    doc.build(story)
    return path


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render(text: str, base_style: ParagraphStyle, *, highlight: bool = False) -> str:
    """将 markdown 行内样式转为 reportlab XML 标记（先保护行内代码，避免标签嵌套错误）。"""
    result = _esc(text)
    fn_bold, _ = _get_fonts()
    code_spans: List[str] = []

    def _stash_code(match: re.Match) -> str:
        code_spans.append(match.group(1))
        return f"@@CODE{len(code_spans) - 1}@@"

    # 先抽出 `code`，避免其中的 _ * 被误当成强调语法
    result = re.sub(r"`([^`]+)`", _stash_code, result)

    if highlight:
        result = re.sub(
            r"\*\*(.+?)\*\*",
            rf'<span backColor="{_HIGHLIGHT_BG}"><font face="{fn_bold}">\1</font></span>',
            result,
        )
        result = re.sub(
            r"__(.+?)__",
            rf'<span backColor="{_HIGHLIGHT_BG}"><font face="{fn_bold}">\1</font></span>',
            result,
        )
        # 高亮模式下不做 * / _ 斜体解析，避免 138******** 等掩码手机号破坏 markup
    else:
        result = re.sub(r"\*\*(.+?)\*\*", rf'<font face="{fn_bold}"><b>\1</b></font>', result)
        result = re.sub(r"__(.+?)__", rf'<font face="{fn_bold}"><b>\1</b></font>', result)
        # *斜体*（排除 **）
        result = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", result)
        # _斜体_（排除 snake_case 如 protocol_type、fetch_kddcup99）
        result = re.sub(r"(?<![\w])_([^_]+)_(?![\w])", r"<i>\1</i>", result)

    for idx, code in enumerate(code_spans):
        result = result.replace(
            f"@@CODE{idx}@@",
            f"<font face='Courier' color='#c7254e'>{code}</font>",
        )
    return result


def _normalize_table_rows(rows: List[List[str]]) -> List[List[str]]:
    """将表格各行补齐为相同列数，避免渲染时越界。"""
    if not rows:
        return []
    ncols = max(len(row) for row in rows)
    if ncols <= 0:
        return []
    normalized: List[List[str]] = []
    for row in rows:
        cells = [str(c).strip() for c in row]
        if len(cells) < ncols:
            cells.extend([""] * (ncols - len(cells)))
        elif len(cells) > ncols:
            cells = cells[:ncols]
        normalized.append(cells)
    return normalized


def _parse_table(lines: List[str], start: int) -> tuple:
    """解析 markdown 表格，返回 (rows, next_idx)。"""
    rows: List[List[str]] = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|") or not line.endswith("|"):
            break
        row = [c.strip() for c in line.strip("|").split("|")]
        # 跳过对齐行
        if row and all(re.match(r"^[\s:|-]+$", c) for c in row if c):
            i += 1
            continue
        if not any(cell for cell in row):
            i += 1
            continue
        rows.append(row)
        i += 1
        if len(rows) > 30:
            break
    return _normalize_table_rows(rows), i

