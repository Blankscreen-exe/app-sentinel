"""Content scanner: finds backend clues inside the APK's text files.

Runs in the sandbox. Scans textual entries (resources, assets, bundled JS) for URLs,
client keys, SDK references, and table/bucket references, each with provenance
(entry path + line number).

Secret classification and redaction happen HERE, inside the sandbox, so sensitive
values never leave it. A public client key (e.g. `sb_publishable_...`) is labelled as
public and kept; a secret-looking value (`sb_secret_...`, service-role JWT) is redacted
to a prefix + hash before it is returned.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from typing import Any

# Entries we treat as text worth scanning.
_TEXT_SUFFIXES = (".js", ".json", ".xml", ".txt", ".html", ".properties", ".ts", ".map", ".cfg")
_TEXT_PREFIXES = ("assets/", "res/raw/", "res/values")

_MAX_BYTES_PER_ENTRY = 5 * 1024 * 1024  # skip huge blobs
_MAX_FINDINGS = 2000

_SUPABASE_URL = re.compile(r"https://[a-z0-9-]+\.supabase\.(?:co|in)", re.I)
_URL = re.compile(r"https?://[^\s\"'<>()]+", re.I)
_SB_PUBLISHABLE = re.compile(r"sb_publishable_[A-Za-z0-9]{8,}")
_SB_SECRET = re.compile(r"sb_secret_[A-Za-z0-9]{8,}")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_TABLE = re.compile(r"\.from\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\)")
_BUCKET = re.compile(r"storage\s*\.\s*from\(\s*[\"']([A-Za-z_][A-Za-z0-9_-]*)[\"']\s*\)")
_SDK_MARKERS = {
    "@supabase/supabase-js": "supabase",
    "supabase": "supabase",
    "firebase": "firebase",
    "amazonaws.com": "aws",
    "googleapis.com": "google",
}

# XML-namespace / toolchain URLs that are not real backend endpoints.
_URL_IGNORE = ("schemas.android.com", "www.w3.org", "apache.org", "xmlpull.org", "java.sun.com")


def _redact(value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{value[:10]}…[REDACTED sha256:{digest}]"


def _jwt_role(token: str) -> str | None:
    """Best-effort decode of a JWT payload's `role` claim (no signature check)."""
    import base64
    import json as _json

    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        role = payload.get("role")
        return str(role) if role is not None else None
    except Exception:  # noqa: BLE001
        return None


def _finding(kind: str, name: str, entry: str, lineno: int, **extra: Any) -> dict[str, Any]:
    f = {"kind": kind, "name": name, "location": f"{entry}:{lineno}", "detection_method": "content-scan"}
    f.update(extra)
    return f


def scan(path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()  # dedup by (kind, name) to limit noise

    def add(f: dict[str, Any]) -> None:
        key = (f["kind"], f["name"])
        if key in seen or len(findings) >= _MAX_FINDINGS:
            return
        seen.add(key)
        findings.append(f)

    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            if info.file_size > _MAX_BYTES_PER_ENTRY:
                continue
            if not (name.endswith(_TEXT_SUFFIXES) or name.startswith(_TEXT_PREFIXES)):
                continue
            try:
                raw = zf.read(name)
            except Exception:  # noqa: BLE001
                continue
            # Skip compiled/binary resources (e.g. binary AXML, resources.arsc): a NUL
            # byte early in the file means it is not plain text.
            if b"\x00" in raw[:4096]:
                continue
            _scan_text(name, raw.decode("utf-8", errors="ignore"), add)

    return findings


def _scan_text(entry: str, text: str, add: Any) -> None:
    sdks_found: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _SUPABASE_URL.finditer(line):
            add(_finding("endpoint", m.group(0), entry, lineno,
                         detail="Supabase project URL", confidence="high",
                         needs_runtime_validation=True))
        for m in _URL.finditer(line):
            url = m.group(0).rstrip('",;)')
            if _SUPABASE_URL.match(url):
                continue
            if any(ig in url for ig in _URL_IGNORE):
                continue
            if url.lower().startswith("http://"):
                add(_finding("insecure_endpoint", url, entry, lineno,
                             detail="cleartext HTTP endpoint", confidence="high",
                             severity_hint="medium"))
            else:
                add(_finding("endpoint", url, entry, lineno, confidence="medium"))
        for m in _SB_PUBLISHABLE.finditer(line):
            # Publishable keys are public by design — kept unredacted (needed to test the
            # backend's authorization), and explicitly labelled as not-a-secret.
            add(_finding("client_key", m.group(0), entry, lineno,
                         detail="Supabase publishable (public client) key — not a secret",
                         confidence="high", classification="public_client_key",
                         needs_runtime_validation=True))
        for m in _SB_SECRET.finditer(line):
            add(_finding("secret", _redact(m.group(0)), entry, lineno,
                         detail="Supabase SECRET key — should never ship in a client",
                         confidence="high", classification="sensitive_secret",
                         severity_hint="high"))
        for m in _JWT.finditer(line):
            token = m.group(0)
            role = _jwt_role(token)
            if role in ("anon", "authenticated"):
                # A public client JWT (anon/authenticated) — kept, needed for testing.
                add(_finding("client_key", token, entry, lineno,
                             detail=f"Supabase {role} JWT (public client key) — not a secret",
                             confidence="high", classification="public_client_key",
                             needs_runtime_validation=True))
            else:
                # service_role or undetermined → treat as sensitive and redact.
                add(_finding("secret", _redact(token), entry, lineno,
                             detail=f"JWT token (role={role or 'unknown'}) — treat as sensitive",
                             confidence="medium", classification="sensitive_secret",
                             severity_hint="high"))
        for m in _TABLE.finditer(line):
            add(_finding("table_ref", m.group(1), entry, lineno,
                         detail="referenced database table/view", confidence="medium"))
        for m in _BUCKET.finditer(line):
            add(_finding("bucket_ref", m.group(1), entry, lineno,
                         detail="referenced storage bucket", confidence="medium"))
        low = line.lower()
        for marker, sdk in _SDK_MARKERS.items():
            if marker in low and sdk not in sdks_found:
                sdks_found.add(sdk)
                add(_finding("sdk", sdk, entry, lineno,
                             detail=f"SDK marker: {marker}", confidence="medium"))
