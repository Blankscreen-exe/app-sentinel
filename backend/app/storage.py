"""Artifact/evidence storage behind a small interface (ADR-004c).

Files are addressed by an opaque internal key, never by their original filename.
The local-disk backend writes under ``DATA_DIR``. An S3/MinIO backend can be added
later by implementing the same ``Storage`` protocol without touching callers.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from app.config import get_settings


class Storage(Protocol):
    def put_stream(self, key: str, src: BinaryIO) -> int: ...
    def path(self, key: str) -> str: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    """Local-disk backend. Keys are relative paths under the root; traversal is refused."""

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        target = (self._root / key).resolve()
        # Refuse keys that escape the storage root.
        if not str(target).startswith(str(self._root) + "/") and target != self._root:
            raise ValueError(f"invalid storage key: {key!r}")
        return target

    def put_stream(self, key: str, src: BinaryIO) -> int:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with open(target, "wb") as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
                written += len(chunk)
        return written

    def path(self, key: str) -> str:
        return str(self._resolve(key))

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)


def get_storage() -> Storage:
    return LocalStorage(get_settings().data_dir)


def move_into(storage: Storage, key: str, local_file: str) -> None:
    """Move an already-written local file into storage under ``key``."""
    dst = storage.path(key)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(local_file, dst)
