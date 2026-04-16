"""消息管理 API 路由"""
from __future__ import annotations

import json
import asyncio
import queue
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from config import load_config
from core.storage import build_blob_name, download_file_to_local, upload_file_to_storage
from db.auth_repository import resolve_user_from_authorization
from db.session_repository import (
    add_message,
    get_messages,
    get_session_by_id,
    add_session_file,
    get_session_files,
)
from core.agents.agent_d import run_agent_d_api
from service.agent_service import AgentService, get_selected_session_files_payload

router = APIRouter(prefix="/api/messages", tags=["消息管理"])


class SendMessageRequest(BaseModel):
    content: str = Field(..., description="消息内容")
    mode: Optional[str] = Field(
        default=None,
        description="工作模式；不传则使用会话在库中的 current_mode",
    )
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    files: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="随消息附带的数据文件（与 WebSocket 一致；不传则从会话已选文件读取）",
    )
    template_files: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="随消息附带的模板文件",
    )


class MessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: str


class SendMessageResponse(BaseModel):
    message_id: int
    content: str
    created_at: str


def _resolve_current_user(authorization: Optional[str], cfg):
    if not authorization:
        if cfg.auth.require_auth:
            raise HTTPException(status_code=401, detail="需要登录后访问")
        return None
    try:
        return resolve_user_from_authorization(authorization, cfg, required=True)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def _pick_table_filling_inputs(files: List[Dict[str, Any]], template_files: List[Dict[str, Any]]):
    """Pick one xlsx source and one template for direct table filling execution."""

    source_file = next((f for f in files if str(f.get("file_name", "")).lower().endswith(".xlsx")), None)
    template_file = next(
        (f for f in template_files if str(f.get("file_name", "")).lower().endswith((".docx", ".xlsx"))),
        None,
    )
    return source_file, template_file


def _resolve_file_reference(file_info: Dict[str, Any], cfg, session_id: str, kind: str) -> str:
    storage_key = str(file_info.get("storage_key") or "").strip()
    if not storage_key:
        return ""

    local_name = str(file_info.get("file_name") or storage_key).strip() or storage_key
    cache_path = Path(cfg.temp_dir) / "file_cache" / session_id / kind / local_name
    if cache_path.exists():
        return str(cache_path)

    if cfg.storage.enabled and cfg.storage.provider == "azure_blob":
        try:
            return str(download_file_to_local(storage_key, cache_path, config=cfg))
        except Exception:
            return storage_key

    return storage_key


def _flatten_table_filling_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Convert run_agent_d_api result into the legacy frontend-friendly shape."""

    data = response.get("data", {}) if isinstance(response, dict) else {}
    resolved_input = response.get("resolved_input", {}) if isinstance(response, dict) else {}
    return {
        "success": bool(response.get("success", False)) if isinstance(response, dict) else False,
        "message": response.get("message", "") if isinstance(response, dict) else "",
        "status": data.get("status") if isinstance(data, dict) else None,
        "excel_path": data.get("excel_path") if isinstance(data, dict) else None,
        "output_json": data.get("output_json") if isinstance(data, dict) else None,
        "total_rows": data.get("total_rows") if isinstance(data, dict) else 0,
        "matched_rows": data.get("matched_rows") if isinstance(data, dict) else 0,
        "used_plan": data.get("used_plan") if isinstance(data, dict) else None,
        "plan_source": data.get("plan_source") if isinstance(data, dict) else None,
        "template_filled": data.get("template_filled") if isinstance(data, dict) else False,
        "template_output": data.get("template_output") if isinstance(data, dict) else None,
        "template_mapping": data.get("template_mapping") if isinstance(data, dict) else {},
        "multi_table_results": data.get("multi_table_results") if isinstance(data, dict) else None,
        "resolved_input": resolved_input,
    }


def _normalize_entity_extraction_response(raw_response: str) -> str:
    """将实体提取的原始 JSON 响应转换为简短摘要。"""
    if not isinstance(raw_response, str) or not raw_response.strip():
        return "实体提取完成，共提取 0 条数据"

    try:
        parsed = json.loads(raw_response)
    except Exception:
        return "实体提取完成"

    if not isinstance(parsed, dict):
        return "实体提取完成"

    entities = parsed.get("entities")
    count = len(entities) if isinstance(entities, list) else 0
    return f"实体提取完成，共提取 {count} 条数据"


def _message_to_dict(m) -> Dict[str, Any]:
    return {
        "id": m.id,
        "session_id": str(m.session_id),
        "role": m.role,
        "content": m.content,
        "metadata": m.metadata,
        "created_at": m.created_at.isoformat() + "Z" if m.created_at else "",
    }


def _persist_generated_files(session_id: str, cfg, user_id: Optional[str], payload: Dict[str, Any]) -> None:
    candidate_paths = []
    for key in ("excel_path", "template_output", "output_json"):
        value = payload.get(key)
        if value:
            candidate_paths.append(str(value))
    for candidate in candidate_paths:
        try:
            path_obj = Path(candidate)
            if not path_obj.exists():
                continue
            storage_key = None
            try:
                storage_key = upload_file_to_storage(
                    path_obj,
                    config=cfg,
                    blob_name=build_blob_name(session_id, path_obj.name, prefix=cfg.storage.azure_blob_prefix),
                )
            except Exception:
                storage_key = None
            add_session_file(
                session_id=session_id,
                file_name=path_obj.name,
                file_type="generated",
                file_path=storage_key or "",
                file_size=path_obj.stat().st_size,
                config=cfg,
                user_id=user_id,
                source="generated",
                role="output",
                storage_key=storage_key,
            )
            try:
                path_obj.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            continue


def _collect_new_generated_files(session_id: str, cfg, user_id: Optional[str], before_ids: set[int]) -> List[Dict[str, Any]]:
    generated: List[Dict[str, Any]] = []
    try:
        rows = get_session_files(session_id, config=cfg, user_id=user_id)
    except Exception:
        return generated
    for f in rows:
        if f.id in before_ids:
            continue
        if getattr(f, "role", "") != "output":
            continue
        generated.append({"file_id": f.id, "file_name": f.file_name})
    return generated


@router.get("/{session_id}", response_model=List[MessageResponse])
async def get_messages_api(session_id: str, limit: int = 100, offset: int = 0, authorization: Optional[str] = Header(default=None)):
    """获取会话消息历史"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    messages = get_messages(session_id, limit=limit, offset=offset, config=cfg, user_id=current_user.id if current_user else None)
    return [_message_to_dict(m) for m in messages]


@router.post("/{session_id}", response_model=SendMessageResponse)
async def send_message(session_id: str, request: SendMessageRequest, authorization: Optional[str] = Header(default=None)):
    """
    发送消息并获取 AI 回复（非流式版本）
    用于简单场景或调试
    """
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    effective_mode = (request.mode or session.current_mode or "default_conversation").strip()

    user_meta: Dict[str, Any] = {**(request.metadata or {}), "mode": effective_mode}
    if request.files:
        user_meta["files"] = request.files
    if request.template_files:
        user_meta["template_files"] = request.template_files

    # 保存用户消息（含附件元数据，供前端展示「文件 + 文字」为一条消息）
    user_msg = add_message(
        session_id,
        "user",
        request.content,
        user_meta,
        config=cfg,
        user_id=current_user.id if current_user else None,
    )

    if request.files is not None or request.template_files is not None:
        db_data_files = list(request.files or [])
        db_template_files = list(request.template_files or [])
    else:
        db_data_files, db_template_files = get_selected_session_files_payload(session_id, cfg)

    # 表格填表走直达执行核，避免聊天/会话链路与 tests/test_d/run.py 的逻辑偏离。
    if effective_mode == "table_filling":
        source_file, template_file = _pick_table_filling_inputs(db_data_files, db_template_files)
        if source_file and template_file:
            response = run_agent_d_api(
                src=_resolve_file_reference(source_file, cfg, session_id, "source"),
                prompt=request.content,
                template=_resolve_file_reference(template_file, cfg, session_id, "template"),
                output_json="",
                output_template="",
                allow_rule_fallback=True,
            )
            table_filling_data = _flatten_table_filling_response(response)
            ai_msg = add_message(
                session_id,
                "assistant",
                table_filling_data.get("message", ""),
                {"mode": effective_mode, "tableFillingData": table_filling_data},
                config=cfg,
                user_id=current_user.id if current_user else None,
            )
            _persist_generated_files(session_id, cfg, current_user.id if current_user else None, table_filling_data)
            return SendMessageResponse(
                message_id=ai_msg.id,
                content=ai_msg.content,
                created_at=ai_msg.created_at.isoformat() + "Z",
            )

    before_file_ids = {
        f.id for f in get_session_files(session_id, config=cfg, user_id=current_user.id if current_user else None)
    }

    # 调用 Agent 服务获取回复（必须与前端所选模式一致，否则恒走默认对话）
    agent_service = AgentService()
    response = await agent_service.chat(
        session_id,
        request.content,
        mode=effective_mode,
        files=db_data_files,
        template_files=db_template_files,
    )

    assistant_content = response
    assistant_meta: Dict[str, Any] = {"mode": effective_mode}
    if effective_mode == "entity_extraction":
        assistant_content = _normalize_entity_extraction_response(response)

    generated_files = _collect_new_generated_files(
        session_id,
        cfg,
        current_user.id if current_user else None,
        before_file_ids,
    )
    if generated_files:
        assistant_meta["generated_files"] = generated_files
    
    # 保存 AI 回复
    ai_msg = add_message(
        session_id,
        "assistant",
        assistant_content,
        assistant_meta,
        config=cfg,
        user_id=current_user.id if current_user else None,
    )
    
    return SendMessageResponse(
        message_id=ai_msg.id,
        content=ai_msg.content,
        created_at=ai_msg.created_at.isoformat() + "Z",
    )


# ============ WebSocket 流式聊天 ============

class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
    
    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
    
    async def send_text(self, session_id: str, text: str):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_text(text)
    
    async def send_json(self, session_id: str, data: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(data)


manager = ConnectionManager()


@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """
    WebSocket 流式聊天（长连接模式）
    前端连接后可持续发送消息，后端保持连接循环处理。
    每次前端发送 JSON：{"content": "...", "mode": "...", "files": [...], "template_files": [...]}
    后端流式返回：{"type": "chunk", "content": "..."} 或 {"type": "done", "content": "..."}
    """
    cfg = load_config()
    current_user = None
    authorization = websocket.headers.get("authorization") or websocket.query_params.get("token")
    if authorization:
        try:
            current_user = resolve_user_from_authorization(authorization, cfg, required=True, allow_raw_token=True)
        except PermissionError as exc:
            await websocket.close(code=4401, reason=str(exc))
            return
    elif cfg.auth.require_auth:
        await websocket.close(code=4401, reason="需要登录后访问")
        return
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        await websocket.close(code=4004, reason="会话不存在")
        return
    
    await manager.connect(websocket, session_id)
    
    try:
        # 保持连接循环，持续处理消息
        while True:
            try:
                # 等待接收消息（会阻塞在这里直到收到消息或连接关闭）
                data = await websocket.receive_json()
            except Exception:
                # 连接已关闭或出错，退出循环
                break
            
            user_content = data.get("content", "")
            # 显式 null/空串时回退到会话记录的模式，避免误走默认对话
            raw_mode = data.get("mode")
            mode = (raw_mode or session.current_mode or "default_conversation")
            if isinstance(mode, str):
                mode = mode.strip() or "default_conversation"
            
            # 优先使用前端传来的文件（和消息一起发送）
            # 这样用户可以随时切换勾选，文件跟随消息
            client_files = data.get("files") or []
            client_templates = data.get("template_files") or []

            # 实体提取模式
            if mode == "entity_extraction":
                db_data_files, db_template_files = get_selected_session_files_payload(session_id, cfg)
                db_path_map = {f.get('file_name'): f for f in db_data_files}
                db_tpl_path_map = {f.get('file_name'): f for f in db_template_files}
                if client_files:
                    files = []
                    for cf in client_files:
                        matched = db_path_map.get(cf.get('file_name'))
                        if matched:
                            files.append(matched)
                        elif cf.get('storage_key'):
                            # 前端直接传了 storage_key（混合模式串行处理，清除选中状态后用）
                            files.append(cf)
                else:
                    files = db_data_files
                if client_templates:
                    template_files = []
                    for ct in client_templates:
                        matched = db_tpl_path_map.get(ct.get('file_name'))
                        if matched:
                            template_files.append(matched)
                        elif ct.get('storage_key'):
                            template_files.append(ct)
                else:
                    template_files = db_template_files
            elif mode == "table_filling":
                # 表格填表模式走直达执行核，保证与 tests/test_d/run.py 同构。
                db_data_files, db_template_files = get_selected_session_files_payload(session_id, cfg)
                db_path_map = {f.get('file_name'): f for f in db_data_files}
                db_tpl_path_map = {f.get('file_name'): f for f in db_template_files}
                if client_files:
                    files = []
                    for cf in client_files:
                        matched = db_path_map.get(cf.get('file_name'))
                        if matched:
                            files.append(matched)
                        elif cf.get('storage_key'):
                            files.append(cf)
                else:
                    files = db_data_files
                if client_templates:
                    template_files = []
                    for ct in client_templates:
                        matched = db_tpl_path_map.get(ct.get('file_name'))
                        if matched:
                            template_files.append(matched)
                        elif ct.get('storage_key'):
                            template_files.append(ct)
                else:
                    template_files = db_template_files

                source_file, template_file = _pick_table_filling_inputs(files, template_files)
                if source_file and template_file:
                    user_meta: Dict[str, Any] = {"mode": mode}
                    if files:
                        user_meta["files"] = files
                    if template_files:
                        user_meta["template_files"] = template_files
                    add_message(session_id, "user", user_content, user_meta, config=cfg, user_id=current_user.id if current_user else None)
                    await manager.send_json(session_id, {"type": "start", "mode": mode})
                    response = await asyncio.to_thread(
                        run_agent_d_api,
                        src=_resolve_file_reference(source_file, cfg, session_id, "source"),
                        prompt=user_content,
                        template=_resolve_file_reference(template_file, cfg, session_id, "template"),
                        output_json="",
                        output_template="",
                        allow_rule_fallback=True,
                    )
                    table_filling_data = _flatten_table_filling_response(response)
                    full_response = json.dumps(table_filling_data, ensure_ascii=False)
                    await manager.send_json(session_id, {"type": "chunk", "content": full_response, "result_type": "table_filling"})
                    add_message(session_id, "assistant", table_filling_data.get("message", ""), {"mode": mode, "tableFillingData": table_filling_data}, config=cfg, user_id=current_user.id if current_user else None)
                    _persist_generated_files(session_id, cfg, current_user.id if current_user else None, table_filling_data)
                    await manager.send_json(session_id, {"type": "done"})
                    continue
            elif client_files or client_templates:
                files = client_files
                template_files = client_templates
            else:
                files, template_files = get_selected_session_files_payload(session_id, cfg)

            user_meta: Dict[str, Any] = {"mode": mode}
            if files:
                user_meta["files"] = files
            if template_files:
                user_meta["template_files"] = template_files

            # 保存用户消息（含附件元数据）
            add_message(session_id, "user", user_content, user_meta, config=cfg, user_id=current_user.id if current_user else None)
            
            # 发送开始信号
            await manager.send_json(session_id, {"type": "start", "mode": mode})

            before_file_ids = {
                f.id for f in get_session_files(session_id, config=cfg, user_id=current_user.id if current_user else None)
            }

            # 进度队列：线程安全信令，规避 run_coroutine_threadsafe 在主 loop 阻塞时无法执行的问题
            progress_queue: queue.Queue = queue.Queue()

            def progress_callback(completed: int, total: int, message: str):
                percent = int(completed / total * 100) if total > 0 else 0
                progress_queue.put_nowait({
                    "type": "progress",
                    "progress": percent,
                    "message": message,
                })

            # 在后台线程跑提取，主 loop 保持空闲以处理 WebSocket
            agent_service = AgentService()
            full_response = ""

            async def drain_queue():
                """每 50ms 把队列中的进度消息发往 WebSocket"""
                while not progress_queue.empty():
                    try:
                        msg = progress_queue.get_nowait()
                        # _done 标记仅用于退出循环，不发往 WebSocket
                        if msg.get("_done"):
                            continue
                        await manager.send_json(session_id, msg)
                    except queue.Empty:
                        break

            async def extraction_task():
                nonlocal full_response
                try:
                    async for chunk in agent_service.chat_stream(
                        session_id,
                        user_content,
                        mode,
                        files=files,
                        template_files=template_files,
                        progress_callback=progress_callback if mode in ("entity_extraction", "table_filling") else None,
                    ):
                        full_response += chunk
                        if mode == "entity_extraction":
                            await manager.send_json(session_id, {"type": "chunk", "content": chunk, "result_type": "entity_extraction"})
                        elif mode == "table_filling":
                            await manager.send_json(session_id, {"type": "chunk", "content": chunk, "result_type": "table_filling"})
                        else:
                            await manager.send_json(session_id, {"type": "chunk", "content": chunk})
                finally:
                    progress_queue.put_nowait({"_done": True})

            # 并发：提取跑后台 + 主 loop 轮询进度队列
            ext_task = asyncio.create_task(extraction_task())
            while not ext_task.done():
                await drain_queue()
                await asyncio.sleep(0.05)
            await drain_queue()

            assistant_content = full_response
            assistant_meta: Dict[str, Any] = {"mode": mode}
            if mode == "entity_extraction":
                assistant_content = _normalize_entity_extraction_response(full_response)

            generated_files = _collect_new_generated_files(
                session_id,
                cfg,
                current_user.id if current_user else None,
                before_file_ids,
            )
            if generated_files:
                assistant_meta["generated_files"] = generated_files

            add_message(
                session_id,
                "assistant",
                assistant_content,
                assistant_meta,
                config=cfg,
                user_id=current_user.id if current_user else None,
            )
            await manager.send_json(session_id, {"type": "done"})
            
    except WebSocketDisconnect:
        pass  # 正常断开
    except Exception as e:
        await manager.send_json(session_id, {"type": "error", "message": str(e)})
    finally:
        manager.disconnect(session_id)
