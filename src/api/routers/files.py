"""文件管理 API 路由"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from config import load_config
from core.storage import build_blob_name, delete_file_from_storage, download_file_to_local, upload_stream_to_storage
from db.auth_repository import resolve_user_from_authorization
from db.session_repository import (
    add_session_file,
    delete_session_file,
    get_session_by_id,
    get_session_files,
    update_file_selection,
)

router = APIRouter(prefix="/api/sessions/{session_id}/files", tags=["文件管理"])

# 文件存储目录
UPLOAD_DIR = Path("workspace/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class SessionFile(BaseModel):
    id: int
    file_name: str
    file_path: str
    file_type: str
    file_size: int
    is_selected: bool
    created_at: str
    storage_key: Optional[str] = None


class FileListResponse(BaseModel):
    data_files: List[SessionFile]
    template_files: List[SessionFile]


class FileSelectionRequest(BaseModel):
    file_id: int
    is_selected: bool


def _resolve_current_user(authorization: Optional[str], cfg):
    if not authorization:
        if cfg.auth.require_auth:
            raise HTTPException(status_code=401, detail="需要登录后访问")
        return None
    try:
        return resolve_user_from_authorization(authorization, cfg, required=True)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def _file_to_dict(f) -> Dict[str, Any]:
    return {
        "id": f.id,
        "file_name": f.file_name,
        "file_path": getattr(f, "storage_key", None) or f.file_path,
        "file_type": f.file_type,
        "file_size": f.file_size,
        "is_selected": f.is_selected,
        "created_at": f.created_at.isoformat() + "Z" if f.created_at else "",
        "storage_key": getattr(f, "storage_key", None),
    }


def _cleanup_blob_cache_file(path: Path, cache_root: Path) -> None:
    """仅清理 azure_blob_cache 下的临时下载文件。"""
    try:
        path = path.resolve()
        cache_root = cache_root.resolve()
    except Exception:
        return

    if cache_root not in path.parents:
        return

    try:
        if path.exists() and path.is_file():
            path.unlink()
    except Exception:
        return

    # 尝试向上清理空目录，最多到 cache_root
    current = path.parent
    while current != cache_root and cache_root in current.parents:
        try:
            current.rmdir()
            current = current.parent
        except OSError:
            break


@router.get("", response_model=FileListResponse)
async def list_files(session_id: str, authorization: Optional[str] = Header(default=None)):
    """获取会话的所有文件（按类型分组）"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    all_files = get_session_files(session_id, config=cfg, user_id=current_user.id if current_user else None)

    data_files = [_file_to_dict(f) for f in all_files if f.file_type == "data"]
    template_files = [_file_to_dict(f) for f in all_files if f.file_type == "template"]
    
    return FileListResponse(data_files=data_files, template_files=template_files)


@router.post("", response_model=SessionFile)
async def upload_file(
    session_id: str,
    file: UploadFile,
    file_type: str = Form(..., description="文件类型: data 或 template"),
    authorization: Optional[str] = Header(default=None),
):
    """
    上传文件到会话
    """
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 验证文件类型
    if file_type not in ("data", "template"):
        raise HTTPException(status_code=400, detail="file_type 必须是 'data' 或 'template'")
    
    # 保存文件
    file_name = file.filename or "unnamed"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{file_name}"
    file_size = 0
    storage_key = None
    if cfg.storage.enabled and cfg.storage.provider == "azure_blob":
        storage_key = upload_stream_to_storage(
            file.file,
            config=cfg,
            blob_name=build_blob_name(session_id, safe_name, prefix=cfg.storage.azure_blob_prefix),
            content_type=file.content_type,
        )
        if not storage_key:
            raise HTTPException(status_code=502, detail="Azure Blob 上传失败")
        try:
            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)
        except Exception:
            file_size = 0
    else:
        file_path = UPLOAD_DIR / session_id / safe_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(8192):
                buffer.write(chunk)
                file_size += len(chunk)
    
    # 保存到数据库
    session_file = add_session_file(
        session_id=session_id,
        file_name=file_name,
        file_type=file_type,
        file_path=storage_key or "",
        file_size=file_size,
        config=cfg,
        user_id=current_user.id if current_user else None,
        source="upload",
        role="source",
        storage_key=storage_key,
    )
    
    return _file_to_dict(session_file)


@router.patch("/selection")
async def update_file_selections(
    session_id: str,
    selections: List[FileSelectionRequest],
    authorization: Optional[str] = Header(default=None),
):
    """批量更新文件勾选状态"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    results = []
    for sel in selections:
        success = update_file_selection(sel.file_id, sel.is_selected, config=cfg, user_id=current_user.id if current_user else None)
        results.append({"file_id": sel.file_id, "success": success})
    
    return {"results": results}


@router.delete("/{file_id}")
async def delete_file(session_id: str, file_id: int, authorization: Optional[str] = Header(default=None)):
    """删除文件"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    
    # 检查会话是否存在
    session = get_session_by_id(session_id, config=cfg, user_id=current_user.id if current_user else None)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 获取文件信息（用于删除物理文件）
    files = get_session_files(session_id, config=cfg, user_id=current_user.id if current_user else None)
    file_info = next((f for f in files if f.id == file_id), None)
    
    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 删除 Blob 文件
    storage_key = getattr(file_info, "storage_key", None)
    if storage_key:
        delete_file_from_storage(storage_key, config=cfg)
    
    # 删除数据库记录
    success = delete_session_file(file_id, config=cfg, user_id=current_user.id if current_user else None)
    
    return {"success": success}


@router.get("/{file_id}/download")
async def download_file(session_id: str, file_id: int, authorization: Optional[str] = Header(default=None)):
    """下载文件"""
    cfg = load_config()
    current_user = _resolve_current_user(authorization, cfg)
    
    files = get_session_files(session_id, config=cfg, user_id=current_user.id if current_user else None)
    file_info = next((f for f in files if f.id == file_id), None)
    
    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    background_task = None
    storage_key = getattr(file_info, "storage_key", None)
    if storage_key and cfg.storage.enabled and cfg.storage.provider == "azure_blob":
        cache_path = Path(cfg.temp_dir) / "azure_blob_cache" / storage_key
        try:
            file_path = download_file_to_local(storage_key, cache_path, config=cfg)
            background_task = BackgroundTask(
                _cleanup_blob_cache_file,
                file_path,
                Path(cfg.temp_dir) / "azure_blob_cache",
            )
        except Exception:
            raise HTTPException(status_code=404, detail="文件不存在")
    else:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(file_path),
        filename=file_info.file_name,
        media_type="application/octet-stream",
        background=background_task,
    )


# ============ 通用路径下载（本地测试用）============
# 不依赖 session_id，用于下载 Agent 生成的 _filled.xlsx / _filtered_rows.json 等文件

download_router = APIRouter(prefix="/api/files", tags=["文件下载"])


@download_router.get("/download")
async def download_by_path(path: str):
    """根据本地绝对路径或 Blob key 下载（本地测试用）"""
    cfg = load_config()
    file_path = Path(path)
    if not file_path.exists() and cfg.storage.enabled and cfg.storage.provider == "azure_blob":
        try:
            cache_path = Path(cfg.temp_dir) / "azure_blob_cache" / path
            file_path = download_file_to_local(path, cache_path, config=cfg)
        except Exception:
            raise HTTPException(status_code=404, detail="文件不存在")
    elif not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )
