"""Append-only session/run storage with strict synthetic/real root separation."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import manifest_nodes
from acoustic_ladder.domain.models import (
    ArtifactRef,
    DataOrigin,
    MeasurementRunRecord,
    ReassemblyRecord,
    SessionRecord,
)
from acoustic_ladder.storage.io import (
    StorageError,
    atomic_write_bytes,
    atomic_write_json,
    confined_path,
    safe_identifier,
    sha256_bytes,
)

if TYPE_CHECKING:
    from acoustic_ladder.audio.ess_processing_models import ProcessingRecord
    from acoustic_ladder.audio.provisional_qc_models import QcRecord

SESSION_DIRECTORIES = (
    "manifest",
    "protocol",
    "raw",
    "processed",
    "qc",
    "features",
    "models",
    "reports",
    "events",
)
EVENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
EVENT_RESERVED_FIELDS = frozenset({"event", "sequence", "session_id", "data_origin"})


@dataclass(frozen=True)
class DataRoots:
    synthetic: Path
    real: Path

    def __post_init__(self) -> None:
        synthetic = self.synthetic.resolve()
        real = self.real.resolve()
        if synthetic == real or synthetic.is_relative_to(real) or real.is_relative_to(synthetic):
            raise StorageError("synthetic and real roots must be distinct and non-overlapping")

    def for_origin(self, origin: DataOrigin) -> Path:
        return self.synthetic if origin is DataOrigin.SYNTHETIC else self.real


def verify_artifact(session_root: str | Path, artifact: ArtifactRef) -> Path:
    """Verify confinement, size and digest for one immutable artifact."""

    target = confined_path(session_root, artifact.path)
    if not target.is_file():
        raise StorageError(f"artifact is missing: {artifact.path}")
    data = target.read_bytes()
    if len(data) != artifact.byte_size:
        raise StorageError(f"artifact byte size mismatch: {artifact.path}")
    if sha256_bytes(data) != artifact.sha256:
        raise StorageError(f"artifact SHA256 mismatch: {artifact.path}")
    return target


class ImmutableSessionStore:
    """Create-only file store; existing sessions, runs, events and artifacts are never replaced."""

    def __init__(self, roots: DataRoots) -> None:
        self.roots = roots

    def session_path(self, origin: DataOrigin, session_id: str) -> Path:
        safe_identifier(session_id, "session_id")
        root = self.roots.for_origin(origin).resolve()
        session = (root / f"session_{session_id}").resolve()
        if not session.is_relative_to(root):
            raise StorageError("resolved session path escapes its configured data root")
        return session

    def create_session(
        self,
        record: SessionRecord,
        reassemblies: list[ReassemblyRecord],
        bundle: LoadedBundle,
    ) -> Path:
        """Publish a complete session directory using a staging-directory rename."""

        if record.data_origin is DataOrigin.SYNTHETIC and record.run_mode.value != "development":
            raise StorageError("synthetic sessions must use development mode")
        expected_reassemblies = [item.reassembly_id for item in reassemblies]
        if record.reassembly_ids != expected_reassemblies:
            raise StorageError("session reassembly_ids do not match supplied reassembly records")
        if any(item.session_id != record.session_id for item in reassemblies):
            raise StorageError("reassembly record belongs to a different session")
        root = self.roots.for_origin(record.data_origin).resolve()
        root.mkdir(parents=True, exist_ok=True)
        final = self.session_path(record.data_origin, record.session_id)
        if final.exists():
            raise StorageError(f"session already exists: {record.session_id}")
        staging = Path(tempfile.mkdtemp(prefix=f".session_{record.session_id}.", dir=root))
        try:
            for directory in SESSION_DIRECTORIES:
                (staging / directory).mkdir()
            self._write_bundle(staging, bundle)
            atomic_write_json(staging / "session_record.json", record.model_dump(mode="json"))
            atomic_write_json(
                staging / "events" / "000001_session_created.json",
                {
                    "event": "session_created",
                    "session_id": record.session_id,
                    "created_at": record.created_at.isoformat(),
                },
            )
            for sequence, reassembly in enumerate(reassemblies, start=2):
                atomic_write_json(
                    staging / "events" / f"{sequence:06d}_reassembly_created.json",
                    reassembly.model_dump(mode="json"),
                )
            atomic_write_bytes(staging / "SESSION_COMPLETE", b"complete\n")
            if final.exists():
                raise StorageError(f"session already exists: {record.session_id}")
            os.rename(staging, final)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        return final

    def create_synthetic_session(
        self,
        record: SessionRecord,
        reassemblies: list[ReassemblyRecord],
        bundle: LoadedBundle,
    ) -> Path:
        """Synthetic-only entry point that can never select the real root."""

        if record.data_origin is not DataOrigin.SYNTHETIC:
            raise StorageError("synthetic writer refuses non-synthetic session records")
        return self.create_session(record, reassemblies, bundle)

    def _write_bundle(self, staging: Path, bundle: LoadedBundle) -> None:
        atomic_write_bytes(
            staging / "manifest" / "device_manifest.provisional.json", bundle.manifest_bytes
        )
        atomic_write_bytes(
            staging / "manifest" / "device_manifest.provisional.sha256",
            bundle.manifest_sidecar_bytes,
        )
        atomic_write_json(
            staging / "protocol" / "config_bundle.json",
            bundle.receipt.model_dump(mode="json"),
        )
        for kind, loaded in bundle.configs.items():
            suffix = Path(loaded.snapshot.original_relative_path).suffix or ".yaml"
            atomic_write_bytes(
                staging / "protocol" / "config" / f"{kind}.original{suffix}",
                loaded.original_bytes,
            )
            atomic_write_bytes(
                staging / "protocol" / "config" / f"{kind}.normalized.json",
                loaded.normalized_bytes,
            )

    def create_run(
        self,
        record: MeasurementRunRecord,
        artifact_payloads: dict[str, bytes],
        metadata: dict[str, object],
    ) -> Path:
        """Atomically publish a complete run and append a never-overwritten event."""

        session = self.session_path(record.data_origin, record.session_id)
        if not (session / "SESSION_COMPLETE").is_file():
            raise StorageError(f"session is missing or incomplete: {record.session_id}")
        session_record = SessionRecord.model_validate_json(
            (session / "session_record.json").read_text(encoding="utf-8")
        )
        if session_record.data_origin is not record.data_origin:
            raise StorageError("run data_origin does not match session root")
        self._validate_run_relationships(session, session_record, record)
        safe_identifier(record.run_id, "run_id")
        final = session / "raw" / f"run_{record.run_id}"
        if final.exists():
            raise StorageError(f"run already exists: {record.run_id}")
        staging = Path(tempfile.mkdtemp(prefix=f".run_{record.run_id}.", dir=session / "raw"))
        try:
            for relative, payload in artifact_payloads.items():
                target = confined_path(staging, relative)
                atomic_write_bytes(target, payload)
            atomic_write_json(staging / "synthetic_metadata.json", metadata)
            atomic_write_json(staging / "run_record.json", record.model_dump(mode="json"))
            for artifact in record.artifacts:
                local_relative = artifact.path.removeprefix(f"raw/run_{record.run_id}/")
                local = artifact.model_copy(update={"path": local_relative})
                verify_artifact(staging, local)
            atomic_write_bytes(staging / "RUN_COMPLETE", b"complete\n")
            if final.exists():
                raise StorageError(f"run already exists: {record.run_id}")
            os.rename(staging, final)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        self.append_event(
            record.data_origin,
            record.session_id,
            "run_created",
            {"run_id": record.run_id, "created_at": record.created_at.isoformat()},
        )
        return final

    def create_synthetic_run(
        self,
        record: MeasurementRunRecord,
        artifact_payloads: dict[str, bytes],
        metadata: dict[str, object],
    ) -> Path:
        """Synthetic-only run entry point that can never select the real root."""

        if record.data_origin is not DataOrigin.SYNTHETIC:
            raise StorageError("synthetic writer refuses non-synthetic run records")
        return self.create_run(record, artifact_payloads, metadata)

    def create_synthetic_processing(
        self,
        *,
        session_id: str,
        source_run_id: str,
        processing_id: str,
        artifact_payloads: dict[str, bytes],
        metadata: dict[str, object],
        record: ProcessingRecord,
    ) -> Path:
        """Create-only publish one processing child under a verified synthetic run."""

        safe_identifier(processing_id, "processing_id")
        self.validate_run(DataOrigin.SYNTHETIC, session_id, source_run_id)
        if (
            record.session_id != session_id
            or record.source_run_id != source_run_id
            or record.processing_id != processing_id
        ):
            raise StorageError("processing record identity does not match selected path")
        session = self.session_path(DataOrigin.SYNTHETIC, session_id)
        processed_root = (session / "processed").resolve()
        if not processed_root.is_relative_to(session.resolve()):
            raise StorageError("processed root escapes the synthetic session")
        parent = processed_root / f"run_{source_run_id}"
        parent.mkdir(exist_ok=True)
        final = (parent / f"processing_{processing_id}").resolve()
        if final.parent != parent.resolve() or not final.is_relative_to(processed_root):
            raise StorageError("processing path escapes the synthetic session")
        if final.exists():
            raise StorageError(f"processing already exists: {processing_id}")
        lock = parent / f".{processing_id}.publish.lock"
        descriptor: int | None = None
        staging: Path | None = None
        published = False
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if final.exists():
                raise StorageError(f"processing already exists: {processing_id}")
            staging = Path(tempfile.mkdtemp(prefix=f".{processing_id}.staging-", dir=parent))
            for relative, payload in artifact_payloads.items():
                atomic_write_bytes(confined_path(staging, relative), payload)
            atomic_write_json(staging / "processing_metadata.json", metadata)
            atomic_write_json(staging / "processing_record.json", record.model_dump(mode="json"))
            atomic_write_bytes(staging / "PROCESSING_COMPLETE", b"complete\n")
            os.rename(staging, final)
            published = True
            return final
        except FileExistsError as exc:
            raise StorageError(
                f"processing publication is already in progress: {processing_id}"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)
            if not published and staging is not None and staging.exists():
                shutil.rmtree(staging)

    def append_event(
        self,
        origin: DataOrigin,
        session_id: str,
        event: str,
        payload: dict[str, object],
    ) -> Path:
        """Append an event only to a verified session derived from configured roots."""

        if EVENT_NAME_PATTERN.fullmatch(event) is None:
            raise StorageError(
                "event name must be non-empty ASCII letters, digits, hyphens or underscores"
            )
        reserved = sorted(EVENT_RESERVED_FIELDS.intersection(payload))
        if reserved:
            raise StorageError(f"event payload contains reserved fields: {reserved}")
        session = self._validated_completed_session(origin, session_id)
        root = self.roots.for_origin(origin).resolve()
        events = (session / "events").resolve()
        if not events.is_dir():
            raise StorageError(f"session events directory is missing: {session_id}")
        if not events.is_relative_to(session) or not events.is_relative_to(root):
            raise StorageError("resolved events path escapes the verified session data root")
        existing = sorted(events.glob("[0-9][0-9][0-9][0-9][0-9][0-9]_*.json"))
        sequence = int(existing[-1].name[:6]) + 1 if existing else 1
        path = events / f"{sequence:06d}_{event}.json"
        atomic_write_json(
            path,
            {
                "event": event,
                "sequence": sequence,
                "session_id": session_id,
                "data_origin": origin.value,
                **payload,
            },
        )
        return path

    def create_synthetic_qc(
        self,
        *,
        session_id: str,
        source_run_id: str,
        processing_id: str,
        qc_id: str,
        artifact_payloads: dict[str, bytes],
        metadata: dict[str, object],
        record: QcRecord,
    ) -> Path:
        """Create-only publish one QC child under a verified synthetic processing."""

        safe_identifier(source_run_id, "source_run_id")
        safe_identifier(processing_id, "processing_id")
        safe_identifier(qc_id, "qc_id")
        self.validate_run(DataOrigin.SYNTHETIC, session_id, source_run_id)
        if (
            record.session_id != session_id
            or record.source_run_id != source_run_id
            or record.processing_id != processing_id
            or record.qc_id != qc_id
        ):
            raise StorageError("QC record identity does not match selected path")
        session = self.session_path(DataOrigin.SYNTHETIC, session_id)
        processing = (
            session / "processed" / f"run_{source_run_id}" / f"processing_{processing_id}"
        ).resolve()
        if (
            not processing.is_relative_to(session.resolve())
            or not (processing / "PROCESSING_COMPLETE").is_file()
        ):
            raise StorageError("source processing is missing or incomplete")
        qc_root = (session / "qc").resolve()
        if not qc_root.is_relative_to(session.resolve()):
            raise StorageError("QC root escapes the synthetic session")
        parent = (qc_root / f"run_{source_run_id}" / f"processing_{processing_id}").resolve()
        if not parent.is_relative_to(qc_root):
            raise StorageError("QC parent escapes the synthetic session")
        parent.mkdir(parents=True, exist_ok=True)
        final = (parent / f"qc_{qc_id}").resolve()
        if final.parent != parent or not final.is_relative_to(qc_root):
            raise StorageError("QC path escapes the synthetic session")
        if final.exists():
            raise StorageError(f"QC already exists: {qc_id}")
        lock = parent / f".{qc_id}.publish.lock"
        descriptor: int | None = None
        staging: Path | None = None
        published = False
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if final.exists():
                raise StorageError(f"QC already exists: {qc_id}")
            staging = Path(tempfile.mkdtemp(prefix=f".{qc_id}.staging-", dir=parent))
            for relative, payload in artifact_payloads.items():
                atomic_write_bytes(confined_path(staging, relative), payload)
            atomic_write_json(staging / "qc_metadata.json", metadata)
            atomic_write_json(staging / "qc_record.json", record.model_dump(mode="json"))
            atomic_write_bytes(staging / "QC_COMPLETE", b"complete\n")
            os.rename(staging, final)
            published = True
            return final
        except FileExistsError as exc:
            raise StorageError(f"QC publication is already in progress: {qc_id}") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)
            if not published and staging is not None and staging.exists():
                shutil.rmtree(staging)

    def _validated_completed_session(self, origin: DataOrigin, session_id: str) -> Path:
        session = self.session_path(origin, session_id)
        root = self.roots.for_origin(origin).resolve()
        if not session.is_relative_to(root):
            raise StorageError("session path escapes the selected data root")
        if not session.is_dir() or not (session / "SESSION_COMPLETE").is_file():
            raise StorageError(f"session is missing or incomplete: {session_id}")
        try:
            record = SessionRecord.model_validate_json(
                (session / "session_record.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise StorageError(f"invalid session record: {exc}") from exc
        if record.session_id != session_id:
            raise StorageError("session record session_id does not match selected session")
        if record.data_origin is not origin:
            raise StorageError("session record origin does not match selected data root")
        return session

    def validate_session(self, origin: DataOrigin, session_id: str) -> SessionRecord:
        session = self.session_path(origin, session_id)
        if not session.is_dir() or not (session / "SESSION_COMPLETE").is_file():
            raise StorageError(f"session is missing or incomplete: {session_id}")
        missing_directories = [
            name for name in SESSION_DIRECTORIES if not (session / name).is_dir()
        ]
        if missing_directories:
            raise StorageError(f"session directories are missing: {missing_directories}")
        try:
            record = SessionRecord.model_validate_json(
                (session / "session_record.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise StorageError(f"invalid session record: {exc}") from exc
        if record.data_origin is not origin:
            raise StorageError("session record origin does not match selected root")
        for run_directory in sorted((session / "raw").glob("run_*")):
            self.validate_run(origin, session_id, run_directory.name.removeprefix("run_"))
        return record

    def validate_run(
        self, origin: DataOrigin, session_id: str, run_id: str
    ) -> MeasurementRunRecord:
        """Validate one completed run record and every referenced artifact."""

        safe_identifier(run_id, "run_id")
        session = self.session_path(origin, session_id)
        run_directory = session / "raw" / f"run_{run_id}"
        if not (run_directory / "RUN_COMPLETE").is_file():
            raise StorageError(f"run is missing or incomplete: {run_id}")
        try:
            run = MeasurementRunRecord.model_validate_json(
                (run_directory / "run_record.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise StorageError(f"invalid run record in {run_directory.name}: {exc}") from exc
        if run.run_id != run_id or run.session_id != session_id or run.data_origin is not origin:
            raise StorageError("run record identity does not match selected storage path")
        try:
            session_record = SessionRecord.model_validate_json(
                (session / "session_record.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise StorageError(f"invalid session record: {exc}") from exc
        self._validate_run_relationships(session, session_record, run)
        for artifact in run.artifacts:
            verify_artifact(session, artifact)
        return run

    @staticmethod
    def _validate_run_relationships(
        session: Path, session_record: SessionRecord, run: MeasurementRunRecord
    ) -> None:
        if run.reassembly_id not in session_record.reassembly_ids:
            raise StorageError("run reassembly_id is not declared by the session")
        try:
            manifest = json.loads(
                (session / "manifest" / "device_manifest.provisional.json").read_text(
                    encoding="utf-8"
                )
            )
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
            expected_nodes = set(manifest_nodes(manifest))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise StorageError(f"cannot validate stored manifest nodes: {exc}") from exc
        actual_nodes = set(run.node_states)
        if actual_nodes != expected_nodes:
            raise StorageError(
                "run node-state map is incomplete or contains unknown nodes: "
                f"missing={sorted(expected_nodes - actual_nodes)}, "
                f"extra={sorted(actual_nodes - expected_nodes)}"
            )


def read_json_object(path: str | Path) -> dict[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StorageError(f"expected JSON object: {path}")
    return value


def record_bytes(record: SessionRecord | ReassemblyRecord | MeasurementRunRecord) -> bytes:
    return canonical_json_bytes(record.model_dump(mode="json"))
