"""Ingest must validate untrusted sandbox output and derive provenance-tagged discoveries."""

from __future__ import annotations

import pytest

from app.analysis.ingest import ingest
from app.models import StaticAnalysis


def _valid_payload() -> dict:
    return {
        "schema_version": 1,
        "sha256": "a" * 64,
        "structure": {"entry_count": 3, "has_manifest": True, "dex_files": ["classes.dex"]},
        "manifest": {
            "package": "com.example.lab",
            "permissions": ["android.permission.INTERNET"],
            "exported_activities": ["com.example.lab.MainActivity"],
            "debuggable": True,
            "uses_cleartext_traffic": None,
            "allow_backup": False,
        },
        "manifest_error": None,
        "discoveries": [
            {
                "kind": "client_key",
                "name": "sb_publishable_AbCdEf0123456789xyzTESTvalue",
                "location": "assets/config.js:4",
                "detection_method": "content-scan",
                "detail": "Supabase publishable (public client) key — not a secret",
                "confidence": "high",
                "classification": "public_client_key",
                "needs_runtime_validation": True,
            },
            {
                "kind": "endpoint",
                "name": "https://abcd1234test.supabase.co",
                "location": "assets/config.js:3",
                "detection_method": "content-scan",
                "confidence": "high",
            },
        ],
        "scan_error": None,
    }


def test_ingest_persists_scan_findings_with_classification() -> None:
    analysis = StaticAnalysis(artifact_id="x", status="analyzing")
    ingest(analysis, _valid_payload())
    key = next(d for d in analysis.discoveries if d.kind == "client_key")
    # A public client key is KEPT (needed to test the backend) and labelled as public.
    assert key.name.startswith("sb_publishable_")
    assert "public_client_key" in (key.detail or "")
    assert key.needs_runtime_validation is True
    endpoint = next(d for d in analysis.discoveries if d.kind == "endpoint")
    assert endpoint.location == "assets/config.js:3"


def test_ingest_builds_discoveries_with_provenance() -> None:
    analysis = StaticAnalysis(artifact_id="x", status="analyzing")
    ingest(analysis, _valid_payload())
    assert analysis.status == "analyzed"
    kinds = {(d.kind, d.name) for d in analysis.discoveries}
    assert ("permission", "android.permission.INTERNET") in kinds
    assert ("exported_component", "com.example.lab.MainActivity") in kinds
    assert ("manifest_flag", "android:debuggable=true") in kinds
    # allow_backup is False -> must NOT be reported
    assert not any(d.name.startswith("android:allowBackup") for d in analysis.discoveries)
    # every discovery carries a location + detection method (provenance)
    assert all(d.detection_method and d.location for d in analysis.discoveries)
    # manifest-derived discoveries are attributed to androguard
    manifest_kinds = {"permission", "exported_component", "manifest_flag"}
    assert all(
        d.detection_method == "androguard"
        for d in analysis.discoveries
        if d.kind in manifest_kinds
    )


def test_ingest_rejects_malformed_payload() -> None:
    analysis = StaticAnalysis(artifact_id="x", status="analyzing")
    with pytest.raises(Exception):
        ingest(analysis, {"not": "the expected shape"})


def test_ingest_handles_missing_manifest() -> None:
    analysis = StaticAnalysis(artifact_id="x", status="analyzing")
    payload = {
        "schema_version": 1,
        "sha256": "b" * 64,
        "structure": {"has_manifest": False},
        "manifest": None,
        "manifest_error": "parse failed",
    }
    ingest(analysis, payload)
    assert analysis.status == "analyzed"
    assert analysis.discoveries == []
