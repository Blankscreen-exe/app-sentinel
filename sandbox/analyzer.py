"""APK static analysis inside the sandbox, using androguard.

Runs in the isolated sandbox container (no internet, no credentials). It reads the
APK from shared storage, extracts manifest facts, and returns a normalized dict.
It NEVER executes the application; it only parses the archive and its manifest.

Output is plain data (JSON-serializable). The orchestrator treats it as untrusted
and validates it before persisting.
"""

from __future__ import annotations

import hashlib
import zipfile
from typing import Any


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def analyze(path: str) -> dict[str, Any]:
    """Return normalized static facts for the APK at ``path``.

    Structural facts (zip contents) are always collected. Manifest facts are
    collected via androguard; if parsing fails, the error is recorded honestly and
    structural facts are still returned.
    """
    out: dict[str, Any] = {
        "schema_version": 1,
        "sha256": _sha256(path),
        "structure": _structure(path),
        "manifest": None,
        "manifest_error": None,
        "discoveries": [],
        "scan_error": None,
        "decompile": {"attempted": False, "ok": False, "error": None, "source_files": 0},
    }
    try:
        out["manifest"] = _manifest_facts(path)
    except Exception as exc:  # noqa: BLE001 - record, never crash the worker
        out["manifest_error"] = f"{type(exc).__name__}: {exc}"

    # Decompile the DEX bytecode to Java (JADX) so compiled apps yield code-level
    # discoveries, not just manifest + text-asset facts. Bounded by a timeout + mem cap;
    # on failure/timeout we still scan the APK's text entries (and any partial sources).
    decompiled_dir, dec_info = _decompile(path)
    out["decompile"].update(dec_info)
    try:
        from scanner import scan

        out["discoveries"] = scan(path, decompiled_dir=decompiled_dir)
    except Exception as exc:  # noqa: BLE001
        out["scan_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _decompile(path: str) -> tuple[str | None, dict[str, Any]]:
    """Run JADX into a temp dir. Returns (sources_dir_or_None, info). Never raises."""
    import os
    import shutil
    import subprocess
    import tempfile

    info: dict[str, Any] = {"attempted": False, "ok": False, "error": None, "source_files": 0}
    jadx = shutil.which("jadx")
    if jadx is None:
        info["error"] = "jadx not installed"
        return None, info

    info["attempted"] = True
    timeout = int(os.environ.get("JADX_TIMEOUT_SECONDS", "180"))
    outdir = tempfile.mkdtemp(prefix="jadx-")
    env = {**os.environ, "JAVA_OPTS": os.environ.get("JADX_JAVA_OPTS", "-Xmx1024m")}
    try:
        subprocess.run(
            [jadx, "-d", outdir, "--no-res", "--no-debug-info", "-j", "1", path],
            cwd=outdir, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        # Partial output may still have been written; scan whatever exists.
        info["error"] = f"jadx timed out after {timeout}s (scanning partial output)"
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
        return outdir, info

    # Count produced source files (jadx exits non-zero on partial decompiles, which is fine).
    srcs = 0
    for _d, _subdirs, files in os.walk(outdir):
        srcs += sum(1 for f in files if f.endswith((".java", ".smali", ".kt")))
    info["ok"] = srcs > 0
    info["source_files"] = srcs
    return outdir, info


def _structure(path: str) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    return {
        "entry_count": len(names),
        "has_manifest": "AndroidManifest.xml" in names,
        "dex_files": sorted(n for n in names if n.endswith(".dex")),
        "native_libs": sorted(n for n in names if n.startswith("lib/") and n.endswith(".so")),
        "asset_count": sum(1 for n in names if n.startswith("assets/")),
    }


def _manifest_facts(path: str) -> dict[str, Any]:
    from androguard.core.apk import APK  # imported lazily so structure works even if import fails

    apk = APK(path)
    return {
        "package": apk.get_package(),
        "version_name": apk.get_androidversion_name(),
        "version_code": apk.get_androidversion_code(),
        "min_sdk": apk.get_min_sdk_version(),
        "target_sdk": apk.get_target_sdk_version(),
        "permissions": sorted(apk.get_permissions() or []),
        "activities": sorted(apk.get_activities() or []),
        "services": sorted(apk.get_services() or []),
        "receivers": sorted(apk.get_receivers() or []),
        "providers": sorted(apk.get_providers() or []),
        "exported_activities": _exported(apk, "activity"),
        "debuggable": _bool_attr(apk, "debuggable"),
        "allow_backup": _bool_attr(apk, "allowBackup"),
        "uses_cleartext_traffic": _bool_attr(apk, "usesCleartextTraffic"),
    }


def _exported(apk: Any, kind: str) -> list[str]:
    exported: list[str] = []
    try:
        for item in apk.get_android_manifest_xml().findall(f".//{kind}"):
            name = item.get("{http://schemas.android.com/apk/res/android}name")
            exp = item.get("{http://schemas.android.com/apk/res/android}exported")
            if name and (exp or "").lower() == "true":
                exported.append(name)
    except Exception:  # noqa: BLE001
        pass
    return sorted(exported)


def _bool_attr(apk: Any, attr: str) -> bool | None:
    try:
        app = apk.get_android_manifest_xml().find(".//application")
        if app is None:
            return None
        val = app.get("{http://schemas.android.com/apk/res/android}" + attr)
        if val is None:
            return None
        return val.lower() == "true"
    except Exception:  # noqa: BLE001
        return None
