"""Artifact intake: stream upload safely, validate, store, record.

Size is enforced *while streaming* so an oversized upload never fills the disk.
The file is quarantined in a temp dir, validated, and only moved into permanent
storage under an internal key (the sha256) if it passes.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.analysis.validation import ValidationResult, validate_apk
from app.config import get_settings
from app.models import ApplicationArtifact, Project
from app.storage import get_storage, move_into

logger = logging.getLogger("artifacts")


class UploadTooLarge(Exception):
    pass


@dataclass
class IntakeOutcome:
    artifact: ApplicationArtifact
    validation: ValidationResult


def _stream_to_temp(src: BinaryIO, tmp_dir: str, max_bytes: int) -> str:
    os.makedirs(tmp_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=tmp_dir, suffix=".upload")
    written = 0
    try:
        with os.fdopen(fd, "wb") as dst:
            while chunk := src.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLarge(f"upload exceeds {max_bytes} bytes")
                dst.write(chunk)
    except BaseException:
        # Never leave a partial/oversized file lying around.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return tmp_path


def intake_apk(
    session: Session,
    *,
    project_name: str,
    filename: str,
    src: BinaryIO,
) -> IntakeOutcome:
    settings = get_settings()
    storage = get_storage()
    tmp_dir = os.path.join(settings.data_dir, "tmp")

    tmp_path = _stream_to_temp(src, tmp_dir, settings.max_upload_bytes)
    try:
        result = validate_apk(
            tmp_path,
            max_file_bytes=settings.max_upload_bytes,
            max_uncompressed_bytes=settings.max_uncompressed_bytes,
            max_entries=settings.max_zip_entries,
        )

        project = _get_or_create_project(session, project_name)

        if not result.ok:
            # Record the rejection honestly; do not keep the file.
            os.unlink(tmp_path)
            artifact = ApplicationArtifact(
                project_id=project.id,
                filename=filename,
                sha256=result.sha256,
                file_size=result.file_size,
                upload_status="rejected",
            )
            session.add(artifact)
            session.commit()
            logger.info(
                "artifact rejected",
                extra={"extra": {"artifact_id": artifact.id, "reasons": result.reasons}},
            )
            return IntakeOutcome(artifact=artifact, validation=result)

        # Internal key is content-addressed; original filename stays in the DB only.
        key = f"artifacts/{result.sha256}.apk"
        if not storage.exists(key):
            move_into(storage, key, tmp_path)
        else:
            os.unlink(tmp_path)  # identical bytes already stored (dedup)

        artifact = ApplicationArtifact(
            project_id=project.id,
            filename=filename,
            internal_storage_key=key,
            sha256=result.sha256,
            file_size=result.file_size,
            upload_status="uploaded",
        )
        session.add(artifact)
        session.commit()
        logger.info(
            "artifact stored",
            extra={"extra": {"artifact_id": artifact.id, "sha256": result.sha256}},
        )
        return IntakeOutcome(artifact=artifact, validation=result)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _get_or_create_project(session: Session, name: str) -> Project:
    name = (name or "").strip() or f"project-{uuid.uuid4().hex[:8]}"
    existing = session.query(Project).filter(Project.name == name).one_or_none()
    if existing:
        return existing
    project = Project(name=name)
    session.add(project)
    session.flush()
    return project
