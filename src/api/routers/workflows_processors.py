"""
工作流处理器模块 - 各种LLM处理函数
包括翻译、提取、分析、增强、转换、分割等功能
"""
from typing import Any, Dict, Optional
from config import SystemConfig
from utils.logger import get_logger

logger = get_logger(__name__)


def _get_llm_service():
    """获取 LLM 服务实例。"""
    from core.llm.llm_service import get_llm_service
    service = get_llm_service()
    if not hasattr(service, "is_available") or not service.is_available():
        logger.warning("LLM 服务不可用")
        return None
    return service


def _process_node(content: str, file_name: str, node, config: SystemConfig, state: Dict) -> Optional[str]:
    """根据节点类型分发处理。"""
    node_type = node.type
    node_title = node.title or ""
    config_values = node.configValues or {}
    
    # 先检查具体的node_title来精确判断处理类型（所有处理节点type都是'ai'）
    # 必须先检查具体的标题，再检查通用的type
    if "翻译" in node_title or "translate" in node_title.lower():
        return _translate_content(content, file_name, config, config_values)
    elif "内容提取" in node_title or ("extract" in node_title.lower() and "summary" in node_title.lower()):
        return _extract_summary_content(content, file_name, config_values)
    elif "数据抽取" in node_title or ("extract" in node_title.lower() and "data" in node_title.lower()):
        return _extract_data_content(content, file_name, config_values)
    elif "内容分析" in node_title or "分析" in node_title or "analyze" in node_title.lower():
        return _analyze_content(content, file_name, config_values)
    elif "文本增强" in node_title or "增强" in node_title or "enhance" in node_title.lower():
        return _enhance_text_content(content, file_name, config_values)
    elif "格式转换" in node_title or "转换" in node_title or "格式" in node_title or "convert" in node_title.lower():
        return _convert_format_content(content, file_name, config_values)
    elif "文档分割" in node_title or "分割" in node_title or "split" in node_title.lower():
        return _split_document_content(content, file_name, config_values)
    # 处理类型无法识别时，不进行默认翻译，避免误处理
    elif node_type == "ai":
        logger.warning(f"AI节点未能匹配具体处理类型: {node_title}，跳过处理")
        return content
    else:
        logger.warning(f"未知处理类型: {node_title}")
        return content


def _translate_content(content: str, file_name: str, config: SystemConfig, config_values: Dict = None) -> Optional[str]:
    """使用 LLM 翻译文档内容。"""
    service = _get_llm_service()
    if not service:
        return content

    config_values = config_values or {}
    text = content[:8000] if len(content) > 8000 else content
    
    # 优先使用自定义提示词
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        target_language = config_values.get("targetLanguage", "中文")
        prompt = (
            f"你是一个专业的文档翻译助手。请将以下文档翻译为{target_language}，保持原文的格式和结构。\n"
            "注意：\n"
            "1. 保持段落结构不变\n"
            "2. 保留标题层级\n"
            "3. 保留代码块、表格等特殊格式\n"
            "4. 不要添加或删除内容，只进行翻译\n"
            f"5. 如果源文已经是{target_language}，直接返回原文\n\n"
            f"文档内容：\n{text}"
        )

    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"LLM 翻译失败: {e}")
    return content


def _extract_summary_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """提取文档摘要和要点。"""
    service = _get_llm_service()
    if not service:
        return content
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        extract_type = config_values.get("extractType", "summary")
        summary_length = config_values.get("summaryLength", "medium")
        length_hint = {"short": "200字以内", "medium": "500字以内", "detailed": "1000字以内"}.get(summary_length, "500字以内")
        
        text = content[:8000] if len(content) > 8000 else content
        
        if extract_type == "summary":
            prompt = f"请为以下文档生成摘要（{length_hint}）：\n{text}"
        elif extract_type == "keypoints":
            prompt = f"请从以下文档中提取3-5个关键要点，用\n开头列出：\n{text}"
        else:  # both
            prompt = f"请为以下文档生成摘要（{length_hint}），然后在【要点】下列出3-5个关键要点：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"摘要提取失败: {e}")
    return content


def _extract_data_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """从文档中提取结构化数据。"""
    service = _get_llm_service()
    if not service:
        return content
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        data_format = config_values.get("dataFormat", "json")
        extract_fields = config_values.get("extractFields", "")
        text = content[:8000] if len(content) > 8000 else content
        
        prompt = f"请从以下文档中提取数据，格式为{data_format}\n"
        if extract_fields:
            prompt += f"需要提取的字段：{extract_fields}\n"
        prompt += f"文档内容：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"数据提取失败: {e}")
    return content


def _analyze_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """分析文档内容（关键词、实体、情感等）。"""
    service = _get_llm_service()
    if not service:
        return content

    def _normalize_list(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            return [x.strip() for x in v.split(',') if x.strip()]
        return []

    def _to_int(v, default):
        try:
            n = int(v)
            return n if n > 0 else default
        except Exception:
            return default
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    analysis_type = config_values.get("analysisType", "keywords")
    entity_types = _normalize_list(config_values.get("entityTypes", []))
    entity_map = {
        "person": "人名",
        "location": "地名",
        "org": "机构",
        "date": "日期",
    }
    selected_entity_labels = [entity_map.get(x, x) for x in entity_types] if entity_types else ["人名", "地名", "机构", "日期"]
    selected_entity_desc = "、".join(selected_entity_labels)

    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
        if analysis_type == "entities":
            prompt += (
                "\n\n附加硬约束（必须遵守）：\n"
                f"- 只允许抽取这些实体类型：{selected_entity_desc}\n"
                "- 严禁输出未在允许列表中的任何实体类型\n"
                "- 若无命中，返回空数组\n"
            )
    else:
        top_k = _to_int(config_values.get("topK", 10), 10)
        text = content[:8000] if len(content) > 8000 else content
        
        if analysis_type == "keywords":
            prompt = f"请提取以下文档的{top_k}个关键词，仅输出关键词列表（逗号分隔，不要解释）：\n{text}"
        elif analysis_type == "entities":
            prompt = (
                "请执行实体抽取，并严格遵循以下规则：\n"
                f"1. 只允许抽取这些实体类型：{selected_entity_desc}\n"
                "2. 严禁输出未在允许列表中的任何实体类型\n"
                "3. 若某一允许类型没有命中，返回空数组\n"
                "4. 输出必须是 JSON 对象，不要附加解释文字\n"
                f"5. JSON 的键只能来自：{selected_entity_desc}\n"
                f"文档内容：\n{text}"
            )
        else:  # all
            prompt = (
                "请对以下文档进行全面分析，输出结构为：关键词、实体、主题、情感。\n"
                f"其中关键词数量为 {top_k} 个；实体部分只允许这些类型：{selected_entity_desc}。\n"
                "实体部分若无命中可返回空数组，不要新增其他实体类型。\n"
                f"文档内容：\n{text}"
            )
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"内容分析失败: {e}")
    return content


def _enhance_text_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """文本增强：语法检查、润色、改写等。"""
    service = _get_llm_service()
    if not service:
        return content
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        enhance_type = config_values.get("enhanceType", "grammar")
        style = config_values.get("style", "concise")
        text = content[:8000] if len(content) > 8000 else content
        
        style_desc = {
            "concise": "简洁风格",
            "formal": "学术风格",
            "casual": "口语风格",
            "professional": "专业风格"
        }.get(style, "简洁风格")
        
        if enhance_type == "grammar":
            prompt = f"请检查并修正以下文本的语法错误，只返回修正后的文本：\n{text}"
        elif enhance_type == "polish":
            prompt = f"请润色以下文本为{style_desc}，提高表达质量，保持原意：\n{text}"
        elif enhance_type == "rephrase":
            prompt = f"请改写以下文本为{style_desc}，保持原意但使用不同的措辞：\n{text}"
        else:  # all
            prompt = f"请对以下文本进行全面优化：1. 检查语法 2. 润色表达 3. 调整为{style_desc}。返回优化后的文本：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"文本增强失败: {e}")
    return content


def _convert_format_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """格式转换。"""
    service = _get_llm_service()
    if not service:
        return content
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        text = content[:8000] if len(content) > 8000 else content
        prompt = custom_prompt.replace("{content}", text) if "{content}" in custom_prompt else f"{custom_prompt}\n{text}"
    else:
        target_format = config_values.get("targetFormat", "markdown")
        preserve_structure = config_values.get("preserveStructure", True)
        text = content[:8000] if len(content) > 8000 else content
        
        format_names = {"markdown": "Markdown", "html": "HTML", "plaintext": "纯文本", "json": "JSON"}
        target_name = format_names.get(target_format, target_format)
        
        prompt = f"请将以下文本转换为{target_name}格式"
        if preserve_structure:
            prompt += "，保持原有的结构和层级"
        prompt += f"：\n{text}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"格式转换失败: {e}")
    return content


def _split_document_content(content: str, file_name: str, config_values: Dict) -> Optional[str]:
    """文档分割（按章节、段落或大小）。"""
    service = _get_llm_service()
    if not service:
        return content
    
    # 如果用户提供了自定义提示词，优先使用
    custom_prompt = config_values.get("prompt", "").strip()
    if custom_prompt:
        prompt = custom_prompt.replace("{content}", content[:8000]) if "{content}" in custom_prompt else f"{custom_prompt}\n{content[:8000]}"
    else:
        split_method = config_values.get("splitMethod", "paragraph")
        
        if split_method == "section":
            prompt = f"请按章节/段落分割以下文档，为每个部分添加标题标记（# 或 ##）。保留原文内容：\n{content[:8000]}"
        elif split_method == "paragraph":
            prompt = f"请将以下文档按段落分割，每段加上序号，保留原文内容：\n{content[:8000]}"
        elif split_method == "size":
            prompt = f"请将以下文档分成多个部分，每个部分约500字，用【分割】标记分割点，保留原文：\n{content[:8000]}"
        else:  # page
            prompt = f"请将以下文档按逻辑页面分割，用【新页面】标记，保留原文：\n{content[:8000]}"
    
    try:
        response = service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            strip_markdown_output=False,
        )
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"文档分割失败: {e}")
    return content
