"""storage_paths 单元测试。"""
from __future__ import annotations

from pathlib import Path

from config import get_config
from utils.storage_paths import library_upload_dir, resolve_local_storage_path


def test_resolve_library_storage_key_from_src_cwd(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    lib_dir = project_root / "workspace" / "library" / "space-1"
    lib_dir.mkdir(parents=True)
    file_path = lib_dir / "abc_sample.txt"
    file_path.write_text("hello", encoding="utf-8")

    src_dir = project_root / "src"
    src_dir.mkdir()
    monkeypatch.chdir(src_dir)

    cfg = get_config()
    storage_key = r"workspace\library\space-1\abc_sample.txt"
    resolved = resolve_local_storage_path(storage_key, config=cfg)
    assert resolved is not None
    assert resolved.resolve() == file_path.resolve()


def test_library_upload_dir_points_to_project_workspace(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    src_dir = project_root / "src"
    src_dir.mkdir()
    monkeypatch.chdir(src_dir)

    upload_dir = library_upload_dir(get_config())
    assert upload_dir == (project_root / "workspace" / "library").resolve()
