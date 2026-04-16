"""会话和消息的内存存储（数据库未启用时使用）"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from .models import FileRow, MessageRow, SessionListItem, SessionRow, SessionWithMessages


class MemoryStore:
    """内存存储"""

    def __init__(self):
        self._sessions: Dict[int, SessionRow] = {}
        self._sessions_by_uuid: Dict[str, SessionRow] = {}
        self._messages: Dict[int, List[MessageRow]] = {}
        self._session_files: Dict[int, List[FileRow]] = {}
        self._next_id = 1

    def _gen_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid


# 全局内存存储实例
_store = MemoryStore()


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _gen_session_id() -> str:
    return str(uuid.uuid4())


# ============ 会话操作 ============

def create_session(
    title: str = "新会话",
    current_mode: str = "default_conversation",
    config=None,
    user_id: Optional[str] = None,
) -> SessionRow:
    """创建新会话"""
    sid = _store._gen_id()
    session_id = _gen_session_id()
    now = datetime.utcnow()

    session = SessionRow(
        id=sid,
        session_id=session_id,
        title=title,
        current_mode=current_mode,
        created_at=now,
        updated_at=now,
        user_id=user_id,
    )
    _store._sessions[sid] = session
    _store._sessions_by_uuid[session_id] = session
    _store._messages[sid] = []
    _store._session_files[sid] = []
    return session


def get_session_by_id(
    session_id: str,
    config=None,
) -> Optional[SessionRow]:
    """根据 session_id 获取会话"""
    return _store._sessions_by_uuid.get(session_id)


def list_sessions(
    limit: int = 50,
    offset: int = 0,
    config=None,
) -> tuple:
    """获取会话列表"""
    sessions = sorted(
        _store._sessions.values(),
        key=lambda s: s.updated_at,
        reverse=True,
    )
    total = len(sessions)
    items = [
        SessionListItem(
            session_id=s.session_id,
            title=s.title,
            current_mode=s.current_mode,
            message_count=len(_store._messages.get(s.id, [])),
            updated_at=s.updated_at.isoformat() + "Z" if s.updated_at else "",
        )
        for s in sessions[offset:offset + limit]
    ]
    return items, total


def update_session(
    session_id: str,
    title: Optional[str] = None,
    current_mode: Optional[str] = None,
    config=None,
) -> Optional[SessionRow]:
    """更新会话"""
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return None

    if title is not None:
        session.title = title
    if current_mode is not None:
        session.current_mode = current_mode
    session.updated_at = datetime.utcnow()
    return session


def delete_session(
    session_id: str,
    config=None,
) -> bool:
    """删除会话"""
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return False

    sid = session.id
    del _store._sessions_by_uuid[session_id]
    del _store._sessions[sid]
    _store._messages.pop(sid, None)
    _store._session_files.pop(sid, None)
    return True


# ============ 消息操作 ============

def add_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
    config=None,
    user_id: Optional[str] = None,
) -> MessageRow:
    """添加消息"""
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    now = datetime.utcnow()
    msg = MessageRow(
        id=_store._gen_id(),
        session_id=session.id,
        role=role,
        content=content,
        metadata=metadata,
        created_at=now,
        user_id=user_id or session.user_id,
    )
    _store._messages[session.id].append(msg)

    # 更新会话时间
    session.updated_at = now
    return msg


def get_messages(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    config=None,
) -> List[MessageRow]:
    """获取会话消息"""
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return []
    msgs = _store._messages.get(session.id, [])
    return msgs[offset:offset + limit]


def get_session_with_messages(
    session_id: str,
    config=None,
) -> Optional[SessionWithMessages]:
    """获取会话及其所有消息"""
    session = get_session_by_id(session_id, config)
    if not session:
        return None
    messages = get_messages(session_id, config=config)
    return SessionWithMessages(session=session, messages=messages)


# ============ 文件操作 ============

def add_session_file(
    session_id: str,
    file_name: str,
    file_type: str,
    file_path: str,
    file_size: int,
    config=None,
    user_id: Optional[str] = None,
    source: str = "upload",
    role: str = "source",
    task_uuid: Optional[str] = None,
    origin_file_id: Optional[int] = None,
    storage_key: Optional[str] = None,
    mime_type: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> FileRow:
    """添加会话文件"""
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        raise ValueError(f"会话不存在: {session_id}")

    now = datetime.utcnow()
    frow = FileRow(
        id=_store._gen_id(),
        session_id=session.id,
        file_name=file_name,
        file_type=file_type,
        file_path=file_path,
        file_size=file_size,
        is_selected=False,
        created_at=now,
        user_id=user_id or session.user_id,
        source=source,
        role=role,
        task_uuid=task_uuid,
        origin_file_id=origin_file_id,
        storage_key=storage_key,
        mime_type=mime_type,
        file_hash=file_hash,
    )
    _store._session_files[session.id].append(frow)
    return frow


def get_session_files(
    session_id: str,
    file_type: Optional[str] = None,
    config=None,
) -> List[FileRow]:
    """获取会话文件列表"""
    session = _store._sessions_by_uuid.get(session_id)
    if not session:
        return []
    files = _store._session_files.get(session.id, [])
    if file_type:
        return [f for f in files if f.file_type == file_type]
    return files


def update_file_selection(
    file_id: int,
    is_selected: bool,
    config=None,
) -> bool:
    """更新文件勾选状态"""
    for files in _store._session_files.values():
        for f in files:
            if f.id == file_id:
                f.is_selected = is_selected
                return True
    return False


def delete_session_file(
    file_id: int,
    config=None,
) -> bool:
    """删除会话文件"""
    for files in _store._session_files.values():
        for i, f in enumerate(files):
            if f.id == file_id:
                files.pop(i)
                return True
    return False
