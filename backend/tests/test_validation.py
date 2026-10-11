"""APK validation must reject hostile and malformed inputs by content."""

from __future__ import annotations

import io
import os
import tempfile
import zipfile

from app.analysis.validation import validate_apk

LIMITS = dict(max_file_bytes=10_000_000, max_uncompressed_bytes=50_000_000, max_entries=1000)


def _write(tmp: str, data: bytes) -> str:
    path = os.path.join(tmp, "f.bin")
    with open(path, "wb") as f:
        f.write(data)
    return path


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_rejects_non_zip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, b"this is not a zip file at all")
        r = validate_apk(path, **LIMITS)
        assert not r.ok
        assert any("ZIP" in reason for reason in r.reasons)


def test_rejects_zip_without_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, _zip_bytes({"hello.txt": b"hi"}))
        r = validate_apk(path, **LIMITS)
        assert not r.ok
        assert not r.is_apk
        assert any("AndroidManifest" in reason for reason in r.reasons)


def test_accepts_minimal_apk_shaped_zip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, _zip_bytes({"AndroidManifest.xml": b"<manifest/>", "classes.dex": b"x"}))
        r = validate_apk(path, **LIMITS)
        assert r.ok, r.reasons
        assert r.is_apk
        assert len(r.sha256) == 64


def test_rejects_path_traversal_entry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, _zip_bytes({"AndroidManifest.xml": b"x", "../../etc/evil": b"x"}))
        r = validate_apk(path, **LIMITS)
        assert not r.ok
        assert any("unsafe archive entry" in reason for reason in r.reasons)


def test_rejects_zip_bomb_by_uncompressed_size() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # Highly compressible 5 MB entry; cap uncompressed at 1 MB.
        path = _write(tmp, _zip_bytes({"AndroidManifest.xml": b"x", "big": b"\0" * (5 * 1024 * 1024)}))
        r = validate_apk(path, max_file_bytes=10_000_000, max_uncompressed_bytes=1_000_000, max_entries=1000)
        assert not r.ok
        assert any("zip bomb" in reason for reason in r.reasons)


def test_rejects_empty_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(tmp, b"")
        r = validate_apk(path, **LIMITS)
        assert not r.ok
