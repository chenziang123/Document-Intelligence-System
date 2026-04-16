from __future__ import annotations

from pathlib import Path

from config import StorageConfig, SystemConfig
from core.storage.azure_blob_storage import AzureBlobStorage, build_blob_name


class _FakeDownloadStream:
    def __init__(self, payload: bytes):
        self._payload = payload

    def readall(self) -> bytes:
        return self._payload


class _FakeBlobClient:
    def __init__(self, storage: dict[str, bytes], name: str):
        self._storage = storage
        self._name = name

    def download_blob(self):
        return _FakeDownloadStream(self._storage[self._name])


class _FakeContainerClient:
    def __init__(self):
        self.storage: dict[str, bytes] = {}

    def create_container(self):
        return None

    def upload_blob(self, name, data, overwrite=False, content_settings=None):
        self.storage[name] = data.read()

    def get_blob_client(self, name):
        return _FakeBlobClient(self.storage, name)

    def delete_blob(self, name):
        from core.storage import azure_blob_storage as storage_module

        if name not in self.storage:
            raise storage_module.ResourceNotFoundError(name)
        self.storage.pop(name, None)


class _FakeServiceClient:
    def __init__(self):
        self.container_client = _FakeContainerClient()

    @classmethod
    def from_connection_string(cls, connection_string):
        return cls()

    def get_container_client(self, container_name):
        return self.container_client


def test_build_blob_name_uses_session_prefix():
    assert build_blob_name("abc123", "../report.xlsx", prefix="document") == "document/abc123/report.xlsx"


def test_upload_download_delete_round_trip(tmp_path: Path, monkeypatch):
    from core.storage import azure_blob_storage as storage_module

    monkeypatch.setattr(storage_module, "BlobServiceClient", _FakeServiceClient)

    cfg = SystemConfig(
        storage=StorageConfig(
            enabled=True,
            provider="azure_blob",
            azure_connection_string="UseDevelopmentStorage=true",
            azure_container_name="document",
            azure_blob_prefix="sessions",
        )
    )
    backend = AzureBlobStorage(cfg)

    source = tmp_path / "demo.txt"
    source.write_text("hello azure", encoding="utf-8")

    blob_name = build_blob_name("sess-1", source.name, prefix=cfg.storage.azure_blob_prefix)
    assert backend.upload_file(source, blob_name) == blob_name

    restored = tmp_path / "restored.txt"
    backend.download_to_path(blob_name, restored)
    assert restored.read_text(encoding="utf-8") == "hello azure"

    assert backend.delete_file(blob_name) is True
    assert backend.delete_file(blob_name) is False
