"""工作流输出路径与命名规则解析。"""
from pathlib import Path
from typing import Any, Dict, Tuple


def apply_naming_rule(naming_rule: str, source_name: str, source_path: str = "") -> str:
    """将命名规则中的占位符替换为源文件相关片段。"""
    ref = source_name or source_path or "output"
    path = Path(ref)
    stem = path.stem
    basename = path.name
    # 不含扩展名的「完整文件名」；多段扩展名如 archive.tar.gz 仅去掉最后一段
    file_stem = stem
    slug = basename.replace(".", "_") if basename else stem
    rule = str(naming_rule or "{original_name}_out")
    return (
        rule.replace("{original_file}", file_stem)
        .replace("{original_slug}", slug)
        .replace("{original_name}", stem)
    )


def resolve_workflow_output_path(
    source_name: str,
    source_path: str,
    output_config: Dict[str, Any],
    output_dir: str,
) -> Tuple[Path, str]:
    """
    根据输出节点配置解析单个源文件对应的输出路径。
    返回 (绝对路径, 输出文件名)。
    """
    output_format = str(output_config.get("outputFormat") or "md").lower()
    if output_format in ("excel", "xls"):
        output_format = "xlsx"
    if output_format not in ("md", "txt", "pdf", "xlsx"):
        output_format = "md"

    naming_rule = str(output_config.get("namingRule") or "{original_name}_out")
    save_path = str(output_config.get("savePath") or "").strip()
    out_name = apply_naming_rule(naming_rule, source_name, source_path)
    ext = f".{output_format}"

    if save_path:
        resolved_save = Path(save_path)
        if not resolved_save.is_absolute():
            resolved_save = Path(output_dir) / resolved_save
        if resolved_save.suffix:
            out_path = resolved_save
            out_name = out_path.name
        else:
            if not out_name.endswith(ext):
                out_name += ext
            out_path = resolved_save / out_name
    else:
        if not out_name.endswith(ext):
            out_name += ext
        out_path = Path(output_dir) / out_name

    return out_path, out_name
