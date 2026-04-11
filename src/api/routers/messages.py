"""消息管理 API 路由"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from config import load_config
from db.session_repository import (
    add_message,
    get_messages,
    get_session_by_id,
)
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


def _message_to_dict(m) -> Dict[str, Any]:
    return {
        "id": m.id,
        "session_id": str(m.session_id),
        "role": m.role,
        "content": m.content,
        "metadata": m.metadata,
        "created_at": m.created_at.isoformat() + "Z" if m.created_at else "",
    }


@router.get("/{session_id}", response_model=List[MessageResponse])
async def get_messages_api(session_id: str, limit: int = 100, offset: int = 0):
    """获取会话消息历史"""
    cfg = load_config()
    messages = get_messages(session_id, limit=limit, offset=offset, config=cfg)
    return [_message_to_dict(m) for m in messages]


@router.post("/{session_id}", response_model=SendMessageResponse)
async def send_message(session_id: str, request: SendMessageRequest):
    """
    发送消息并获取 AI 回复（非流式版本）
    用于简单场景或调试
    """
    cfg = load_config()
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg)
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
    )

    if request.files is not None or request.template_files is not None:
        db_data_files = list(request.files or [])
        db_template_files = list(request.template_files or [])
    else:
        db_data_files, db_template_files = get_selected_session_files_payload(session_id, cfg)

    # 调用 Agent 服务获取回复（必须与前端所选模式一致，否则恒走默认对话）
    agent_service = AgentService()
    response = await agent_service.chat(
        session_id,
        request.content,
        mode=effective_mode,
        files=db_data_files,
        template_files=db_template_files,
    )
    
    # 保存 AI 回复
    ai_msg = add_message(session_id, "assistant", response, config=cfg)
    
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
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg)
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

            # 实体提取模式：必须使用数据库中的真实 file_path
            # 因为前端发送的文件可能没有 file_path
            if mode == "entity_extraction":
                db_data_files, db_template_files = get_selected_session_files_payload(session_id, cfg)
                # 合并：使用前端传来的勾选状态，用数据库中的 file_path
                if client_files:
                    # 构建 file_name -> file_path 映射
                    db_path_map = {f.get('file_name'): f.get('file_path') for f in db_data_files}
                    for cf in client_files:
                        if not cf.get('file_path') and cf.get('file_name') in db_path_map:
                            cf['file_path'] = db_path_map[cf['file_name']]
                if client_templates:
                    db_tpl_path_map = {f.get('file_name'): f.get('file_path') for f in db_template_files}
                    for ct in client_templates:
                        if not ct.get('file_path') and ct.get('file_name') in db_tpl_path_map:
                            ct['file_path'] = db_tpl_path_map[ct['file_name']]
                # 始终以数据库路径为准（最可靠）
                files = db_data_files if db_data_files else client_files
                template_files = db_template_files if db_template_files else client_templates
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
            add_message(session_id, "user", user_content, user_meta, config=cfg)
            
            # 发送开始信号
            await manager.send_json(session_id, {"type": "start"})

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
                        progress_callback=progress_callback if mode == "entity_extraction" else None,
                    ):
                        full_response += chunk
                        if mode == "entity_extraction":
                            await manager.send_json(session_id, {"type": "chunk", "content": chunk, "result_type": "entity_extraction"})
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

            add_message(session_id, "assistant", full_response, {"mode": mode}, config=cfg)
            await manager.send_json(session_id, {"type": "done"})
            
    except WebSocketDisconnect:
        pass  # 正常断开
    except Exception as e:
        await manager.send_json(session_id, {"type": "error", "message": str(e)})
    finally:
        manager.disconnect(session_id)
