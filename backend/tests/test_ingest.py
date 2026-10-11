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
    }


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
    # every discovery carries detection provenance
    assert all(d.detection_method == "androguard" and d.location for d in analysis.discoveries)


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
