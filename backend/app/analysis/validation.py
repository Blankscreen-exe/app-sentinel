"""APK artifact validation.

Uploaded files are untrusted input. We validate by content, never by the file
extension, and we defend against malformed archives, zip bombs, and path-traversal
entries before anything downstream touches the file.

This runs in the orchestrator (not the sandbox) because it only inspects the ZIP
central directory and computes a hash; it does not decompress attacker-controlled
content to disk.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass, field

# ZIP local-file-header magic ("PK\x03\x04") and the empty/spanned variants.
_ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


@dataclass
class ValidationResult:
    ok: bool
    sha256: str
    file_size: int
    reasons: list[str] = field(default_factory=list)
    is_apk: bool = False
    entry_count: int = 0
    total_uncompressed: int = 0


def _looks_like_zip(path: str) -> bool:
    with open(path, "rb") as f:
        head = f.read(4)
    return any(head.startswith(m) for m in _ZIP_MAGICS)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _unsafe_entry_name(name: str) -> bool:
    # Absolute paths or parent-dir escapes must never be trusted.
    if name.startswith("/") or name.startswith("\\"):
        return True
    parts = name.replace("\\", "/").split("/")
    return ".." in parts


def validate_apk(
    path: str,
    *,
    max_file_bytes: int,
    max_uncompressed_bytes: int,
    max_entries: int,
) -> ValidationResult:
    """Validate a file on disk as a plausible, non-malicious APK.

    The caller is responsible for having enforced ``max_file_bytes`` during upload
    streaming; we re-check the size here as defence in depth.
    """
    size = _file_size(path)
    result = ValidationResult(ok=False, sha256=sha256_of(path), file_size=size)

    if size == 0:
        result.reasons.append("file is empty")
        return result
    if size > max_file_bytes:
        result.reasons.append(f"file exceeds size limit ({size} > {max_file_bytes})")
        return result

    if not _looks_like_zip(path):
        result.reasons.append("not a ZIP archive (APKs are ZIP files); extension is ignored")
        return result

    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            result.entry_count = len(infos)
            if result.entry_count > max_entries:
                result.reasons.append(
                    f"too many archive entries ({result.entry_count} > {max_entries})"
                )
            total_uncompressed = 0
            names = set()
            for info in infos:
                if _unsafe_entry_name(info.filename):
                    result.reasons.append(f"unsafe archive entry path: {info.filename!r}")
                total_uncompressed += info.file_size
                names.add(info.filename)
            result.total_uncompressed = total_uncompressed
            if total_uncompressed > max_uncompressed_bytes:
                result.reasons.append(
                    "archive expands beyond the decompression limit "
                    f"({total_uncompressed} > {max_uncompressed_bytes}) — possible zip bomb"
                )
            # APK marker: the manifest must be present. classes.dex may be absent in
            # split/multi-dex-less builds, so we do not require it.
            result.is_apk = "AndroidManifest.xml" in names
            if not result.is_apk:
                result.reasons.append("no AndroidManifest.xml — not a recognizable APK")
    except zipfile.BadZipFile:
        result.reasons.append("corrupt or malformed ZIP archive")
        return result

    result.ok = not result.reasons
    return result


def _file_size(path: str) -> int:
    import os

    return os.path.getsize(path)
