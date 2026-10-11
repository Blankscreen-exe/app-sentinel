"""Validate the sandbox's raw output and turn it into persisted discoveries.

The sandbox output is UNTRUSTED (it was produced by code that parsed a hostile file).
We validate its shape with a Pydantic model before trusting any field, then derive
`Discovery` rows with provenance. Discoveries are observations, never confirmed
vulnerabilities.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import Discovery, StaticAnalysis


class _Structure(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entry_count: int = 0
    has_manifest: bool = False
    dex_files: list[str] = []
    native_libs: list[str] = []
    asset_count: int = 0


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    package: str | None = None
    version_name: str | None = None
    version_code: str | None = None
    min_sdk: str | None = None
    target_sdk: str | None = None
    permissions: list[str] = []
    exported_activities: list[str] = []
    debuggable: bool | None = None
    allow_backup: bool | None = None
    uses_cleartext_traffic: bool | None = None


class SandboxPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_version: int
    sha256: str
    structure: _Structure
    manifest: _Manifest | None = None
    manifest_error: str | None = None


def ingest(analysis: StaticAnalysis, raw_payload: dict[str, Any]) -> None:
    """Populate ``analysis`` (manifest_json + discoveries) from validated raw output.

    Mutates ``analysis`` in place; the caller commits.
    """
    payload = SandboxPayload.model_validate(raw_payload)  # raises if shape is wrong

    manifest = payload.manifest
    analysis.manifest_json = json.dumps(
        manifest.model_dump() if manifest else {"error": payload.manifest_error}
    )
    analysis.status = "analyzed"
    analysis.completed_at = dt.datetime.now(dt.UTC)

    if manifest is None:
        return

    pkg = manifest.package or "unknown"

    # Dangerous permissions are observations with a neutral severity hint.
    for perm in manifest.permissions:
        analysis.discoveries.append(
            Discovery(
                kind="permission",
                name=perm,
                location="AndroidManifest.xml",
                detection_method="androguard",
                confidence="high",
            )
        )

    for comp in manifest.exported_activities:
        analysis.discoveries.append(
            Discovery(
                kind="exported_component",
                name=comp,
                detail="activity exported=true",
                location="AndroidManifest.xml",
                detection_method="androguard",
                confidence="high",
                severity_hint="low",
            )
        )

    for attr, hint in (
        ("debuggable", "medium"),
        ("uses_cleartext_traffic", "medium"),
        ("allow_backup", "low"),
    ):
        if getattr(manifest, attr) is True:
            analysis.discoveries.append(
                Discovery(
                    kind="manifest_flag",
                    name=f"android:{attr}=true",
                    detail=f"package {pkg}",
                    location="AndroidManifest.xml",
                    detection_method="androguard",
                    confidence="high",
                    severity_hint=hint,
                )
            )
