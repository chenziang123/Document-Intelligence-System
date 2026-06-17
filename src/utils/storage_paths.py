"""本地存储路径解析（兼容后端从 src/ 或项目根目录启动）。"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from config import SystemConfig, get_config


def _candidate_roots(config: SystemConfig) -> List[Path]:
    cwd = Path.cwd().resolve()
    roots: List[Path] = [cwd, cwd.parent]

    work_dir = Path(config.work_dir)
    if work_dir.is_absolute():
        roots.append(work_dir)
        if work_dir.name == "workspace":
            roots.append(work_dir.parent)
    else:
        roots.extend([cwd / work_dir, cwd.parent / work_dir])

    seen: set[str] = set()
    ordered: List[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            ordered.append(resolved)
    return ordered


def resolve_local_storage_path(
    storage_key: str,
    config: Optional[SystemConfig] = None,
) -> Optional[Path]:
    """把数据库中的 storage_key 解析为本地可读文件路径。"""
    key = str(storage_key or "").strip()
    if not key:
        return None

    cfg = config or get_config()
    direct = Path(key)
    if direct.is_absolute():
        try:
            if direct.is_file():
                return direct.resolve()
        except OSError:
            pass

    try:
        if direct.is_file():
            return direct.resolve()
    except OSError:
        pass

    normalized = Path(key.replace("\\", "/"))
    parts = normalized.parts

    for root in _candidate_roots(cfg):
        candidates = [root / key, root / normalized]
        if parts and parts[0] == "workspace" and len(parts) > 1:
            candidates.append(root / Path(*parts[1:]))
            candidates.append(root / cfg.work_dir / Path(*parts[1:]))
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate.resolve()
            except OSError:
                continue
    return None


def library_upload_dir(config: Optional[SystemConfig] = None) -> Path:
    """文档库本地上传目录（优先使用项目根下的 workspace/library）。"""
    cfg = config or get_config()
    cwd = Path.cwd().resolve()

    candidates: List[Path] = []
    if cwd.name.lower() == "src":
        candidates.append(cwd.parent / "workspace" / "library")
    for root in _candidate_roots(cfg):
        candidates.append(root / "workspace" / "library")

    seen: set[str] = set()
    for target in candidates:
        key = str(target)
        if key in seen:
            continue
        seen.add(key)
        if target.is_dir():
            return target.resolve()

    default_root = cwd.parent if cwd.name.lower() == "src" else cwd
    fallback = default_root / "workspace" / "library"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback.resolve()
