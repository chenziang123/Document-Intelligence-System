"""Agent 编排 API 路由"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from config import load_config
from core.storage import build_blob_name, upload_file_to_storage
from db.auth_repository import resolve_user_from_authorization
from db.session_repository import add_session_file, get_session_by_id

router = APIRouter(prefix="/api/agents", tags=["Agent编排"])

# ============ Agent 能力定义 ============

MODES = [
    {
        "id": "default_conversation",
        "name": "默认对话",
        "description": "自由对话，通用问答",
        "requires_data": False,
        "requires_template": False,
    },
    {
        "id": "document_understanding",
        "name": "文档理解",
        "description": "上传文档后可交互式提问",
        "requires_data": True,
        "requires_template": False,
    },
    {
        "id": "document_editing",
        "name": "文档编辑",
        "description": "自然语言编辑Word/Excel/文本",
        "requires_data": True,
        "requires_template": False,
    },
    {
        "id": "entity_extraction",
        "name": "实体提取",
        "description": "从文档提取结构化数据",
        "requires_data": True,
        "requires_template": None,  # 可选
    },
    {
        "id": "table_filling",
        "name": "表格填表",
        "description": "条件筛选并填入模板",
        "requires_data": True,
        "requires_template": True,
    },
]


class TaskSpec(BaseModel):
    mode: str = Field(..., description="模式: default_conversation, document_understanding, etc.")
    content: str = Field(..., description="任务内容")
    session_id: str = Field(..., description="会话ID")
    files: List[Dict[str, Any]] = Field(default_factory=list, description="关联文件列表")


class AgentCapabilitiesResponse(BaseModel):
    modes: List[Dict[str, Any]]


class MixedFillRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    entities: List[Dict[str, Any]] = Field(default_factory=list, description="合并后的结构化实体")
    template_file: str = Field(..., description="模板文件绝对路径")
    output_json: str = Field(default="", description="输出JSON路径（可选）")
    output_template: str = Field(default="", description="输出模板路径（可选）")
    template_sheet_name: str = Field(default="", description="模板sheet（可选）")
    template_header_row: int | None = Field(default=None, description="模板表头行（可选）")
    template_start_row: int | None = Field(default=None, description="模板起始行（可选）")
    template_table_index: int | None = Field(default=None, description="docx模板表索引（可选）")


@router.get("/capabilities", response_model=AgentCapabilitiesResponse)
async def get_capabilities():
    """获取所有 Agent 能力"""
    return AgentCapabilitiesResponse(modes=MODES)


@router.post("/execute")
async def execute_task(task: TaskSpec):
    """
    直接执行 Agent 任务
    此端点用于前端直接调用 Agent，不走 WebSocket
    """
    from service.agent_service import AgentService
    
    agent_service = AgentService()
    result = await agent_service.execute_task(
        session_id=task.session_id,
        mode=task.mode,
        content=task.content,
        files=task.files,
    )
    return result


@router.post("/mixed-fill")
async def mixed_fill(request: MixedFillRequest, authorization: str | None = Header(default=None)):
    """统一填表：将mixed模式合并实体写入一个模板（xlsx/docx）。"""
    from core.agents.agent_d import run_agent_d_fill_from_entities

    cfg = load_config()
    current_user = None
    if authorization:
        try:
            current_user = resolve_user_from_authorization(authorization, cfg, required=True)
        except PermissionError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail=str(exc))
    elif cfg.auth.require_auth:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="需要登录后访问")

    result = run_agent_d_fill_from_entities(
        entities=request.entities,
        template=request.template_file,
        output_json=request.output_json,
        output_template=request.output_template,
        template_sheet_name=request.template_sheet_name,
        template_header_row=request.template_header_row,
        template_start_row=request.template_start_row,
        template_table_index=request.template_table_index,
    )
    output_path = result.get("data", {}).get("output_template") if isinstance(result, dict) else None
    if output_path:
        try:
            from pathlib import Path

            path_obj = Path(str(output_path))
            if path_obj.exists():
                storage_key = None
                try:
                    storage_key = upload_file_to_storage(
                        path_obj,
                        config=cfg,
                        blob_name=build_blob_name(session_id, path_obj.name, prefix=cfg.storage.azure_blob_prefix),
                    )
                except Exception:
                    storage_key = None
                session = get_session_by_id(request.session_id, config=cfg, user_id=current_user.id if current_user else None)
                if session:
                    add_session_file(
                        session_id=request.session_id,
                        file_name=path_obj.name,
                        file_type=path_obj.suffix.lower().lstrip(".") or "output",
                        file_path=str(path_obj),
                        file_size=path_obj.stat().st_size,
                        config=cfg,
                        user_id=current_user.id if current_user else None,
                        source="generated",
                        role="output",
                        storage_key=storage_key,
                    )
        except Exception:
            pass
    return result
