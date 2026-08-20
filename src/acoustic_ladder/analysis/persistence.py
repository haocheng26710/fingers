"""Immutable publication and full replay validation for synthetic analysis matrices."""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.storage.io import StorageError, sha256_bytes
from acoustic_ladder.storage.npz import deterministic_npz_bytes

from .measurement_matrix import ComputedMeasurementMatrix, compute_measurement_matrix
from .models import (
    AnalysisMetadata,
    AnalysisReceipt,
    AnalysisRecord,
    AnalysisSourceBinding,
    FeatureColumn,
    FeatureColumnSchema,
    MeasurementRow,
    MeasurementRowIndex,
    PublishedSyntheticMeasurementMatrix,
    SourceExecutionBinding,
    provisional_state,
)
from .source_validation import (
    AnalysisExecutionSource,
    AnalysisSourceError,
    validate_synthetic_analysis_sources,
)
from .spec import LoadedDevelopmentAnalysisMatrixSpec
from .split_plan import build_grouped_split_plan

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
COMPLETE_NAME = "ANALYSIS_COMPLETE"
ENVELOPE_NAMES = frozenset(
    {
        "analysis_source_binding.json",
        "analysis_source_binding.sha256",
        "measurement_row_index.json",
        "measurement_row_index.sha256",
        "feature_schema.json",
        "feature_schema.sha256",
        "split_plan.json",
        "split_plan.sha256",
        "measurement_matrix.npz",
        "measurement_matrix.npz.sha256",
        "analysis_receipt.json",
        "analysis_receipt.sha256",
        "analysis_metadata.json",
        "analysis_record.json",
        COMPLETE_NAME,
    }
)
COMPLETE_BYTES = b"complete\n"


@dataclass(frozen=True)
class _Payloads:
    files: dict[str, bytes]
    receipt: AnalysisReceipt
    receipt_sha256: str


class AnalysisPersistenceError(StorageError):
    """Fail-closed analysis publication error with durable publication state."""

    def __init__(self, message: str, *, published: bool = False) -> None:
        super().__init__(f"{message}; published={str(published).lower()}")
        self.published = published


class SyntheticMeasurementMatrixStore:
    """Confine analysis envelopes beneath one injected synthetic data root."""

    def __init__(self, synthetic_root: str | Path) -> None:
        supplied = Path(synthetic_root)
        if supplied.exists() and _is_reparse_point(supplied):
            raise AnalysisPersistenceError("synthetic root cannot be a symlink or reparse point")
        self.synthetic_root = supplied.resolve()
        self.analyses_root = self.synthetic_root / "analyses"

    def analysis_path(self, analysis_id: str) -> Path:
        _identifier(analysis_id)
        target = (self.analyses_root / f"analysis_{analysis_id}").resolve()
        if not target.is_relative_to(self.synthetic_root):
            raise AnalysisPersistenceError("analysis path escapes synthetic root")
        return target


def _identifier(analysis_id: str) -> None:
    if _SAFE_ID.fullmatch(analysis_id) is None or analysis_id in {".", ".."}:
        raise AnalysisPersistenceError(f"unsafe analysis_id: {analysis_id!r}")


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _feature_schema() -> FeatureColumnSchema:
    definitions = (
        (
            "raw_complex_additive_symmetric_relative_l2",
            "1",
            "Symmetric relative L2 of raw complex additive difference",
            ("raw_complex_additive_difference_real", "raw_complex_additive_difference_imag"),
        ),
        (
            "aligned_complex_additive_symmetric_relative_l2",
            "1",
            "Symmetric relative L2 of aligned complex additive difference",
            (
                "aligned_complex_additive_difference_real",
                "aligned_complex_additive_difference_imag",
            ),
        ),
        (
            "raw_magnitude_difference_rms_db",
            "dB",
            "RMS raw magnitude difference in the analysis band",
            ("raw_magnitude_difference_db",),
        ),
        (
            "aligned_magnitude_difference_rms_db",
            "dB",
            "RMS aligned magnitude difference in the analysis band",
            ("aligned_magnitude_difference_db",),
        ),
        (
            "raw_magnitude_difference_maximum_absolute_db",
            "dB",
            "Maximum absolute raw magnitude difference",
            ("raw_magnitude_difference_db",),
        ),
        (
            "aligned_magnitude_difference_maximum_absolute_db",
            "dB",
            "Maximum absolute aligned magnitude difference",
            ("aligned_magnitude_difference_db",),
        ),
        (
            "raw_phase_difference_rms_rad",
            "rad",
            "RMS raw unwrapped phase difference over valid analysis bins",
            ("raw_unwrapped_phase_difference_rad",),
        ),
        (
            "aligned_phase_difference_rms_rad",
            "rad",
            "RMS aligned unwrapped phase difference over valid analysis bins",
            ("aligned_unwrapped_phase_difference_rad",),
        ),
        (
            "raw_phase_difference_maximum_absolute_rad",
            "rad",
            "Maximum absolute raw unwrapped phase difference",
            ("raw_unwrapped_phase_difference_rad",),
        ),
        (
            "aligned_phase_difference_maximum_absolute_rad",
            "rad",
            "Maximum absolute aligned unwrapped phase difference",
            ("aligned_unwrapped_phase_difference_rad",),
        ),
        (
            "raw_ir_difference_symmetric_nrmse",
            "1",
            "Symmetric normalized raw IR difference",
            ("raw_ir_difference",),
        ),
        (
            "aligned_ir_difference_symmetric_nrmse",
            "1",
            "Symmetric normalized aligned IR difference",
            ("aligned_ir_difference",),
        ),
        (
            "raw_ir_difference_absolute_peak",
            "amplitude",
            "Absolute peak of raw IR difference",
            ("raw_ir_difference",),
        ),
        (
            "aligned_ir_difference_absolute_peak",
            "amplitude",
            "Absolute peak of aligned IR difference",
            ("aligned_ir_difference",),
        ),
        (
            "raw_ir_difference_peak_index",
            "sample",
            "Flattened sample index of raw IR difference peak",
            ("raw_ir_difference",),
        ),
        (
            "aligned_ir_difference_peak_index",
            "sample",
            "Flattened sample index of aligned IR difference peak",
            ("aligned_ir_difference",),
        ),
    )
    return FeatureColumnSchema(
        schema_version="1.0.0",
        feature_count=16,
        scalar_dtype="float64",
        columns=tuple(
            FeatureColumn(
                ordinal=index,
                feature_id=feature_id,
                unit=unit,
                definition=definition,
                source_arrays=sources,
                version="1.0.0",
            )
            for index, (feature_id, unit, definition, sources) in enumerate(definitions, start=1)
        ),
        pca_performed=False,
        feature_selection_performed=False,
        normalization_fitting_performed=False,
    )


def _source_binding(computed: ComputedMeasurementMatrix, analysis_id: str) -> AnalysisSourceBinding:
    spec = computed.sources.analysis_spec
    bindings: list[SourceExecutionBinding] = []
    for execution in computed.sources.executions:
        first = execution.rows[0]
        receipt = first.capture.receipt
        bindings.append(
            SourceExecutionBinding(
                experiment_stage=cast(Literal[1, 2, 3, 4], execution.stage),
                execution_id=execution.source.execution_id,
                execution_manifest_sha256=execution.execution_manifest_sha256,
                execution_completion_sha256=execution.execution_completion_sha256,
                ordered_work_order_sha256=sha256_bytes(
                    canonical_json_bytes(
                        [row.work_order.work_order_sha256 for row in execution.rows]
                    )
                ),
                row_count=len(execution.rows),
                bundle_content_sha256=receipt.bundle_content_sha256,
                device_manifest_sha256=receipt.device_manifest_sha256,
                config_snapshots=execution.source.bundle.receipt.snapshots,
                compiled_plan_sha256=first.work_order.compiled_plan_sha256,
                protocol_plan_receipt_sha256=first.work_order.protocol_plan_receipt_sha256,
                schedule_sha256=first.work_order.schedule_sha256,
                scenario_reference=receipt.scenario_reference,
                scenario_raw_sha256=receipt.scenario_raw_sha256,
                scenario_normalized_sha256=receipt.scenario_normalized_sha256,
                source_ess_artifact_id=receipt.source_ess_artifact_id,
                source_ess_metadata_sha256=receipt.source_ess_metadata_sha256,
                source_ess_wav_sha256=receipt.source_ess_wav_sha256,
                source_ess_raw_float32_sha256=receipt.source_ess_raw_float32_sha256,
            )
        )
    reference = spec.source_path.relative_to(spec.project_root).as_posix()
    return AnalysisSourceBinding(
        schema_version="1.0.0",
        analysis_id=analysis_id,
        analysis_spec_reference=reference,
        analysis_spec_raw_sha256=spec.raw_sha256,
        analysis_spec_normalized_sha256=spec.normalized_sha256,
        ordered_source_aggregate_sha256=computed.sources.ordered_source_aggregate_sha256,
        executions=tuple(bindings),
        data_origin="synthetic",
        run_mode="development",
        source_execution_complete=True,
        source_execution_validated=True,
    )


def _row_index(computed: ComputedMeasurementMatrix) -> MeasurementRowIndex:
    processed = {row.work_order.work_order_sha256: row for row in computed.processed_rows}
    execution_by_stage = {item.stage: item for item in computed.sources.executions}
    rows: list[MeasurementRow] = []
    for ordinal, identity in enumerate(computed.identities, start=1):
        source = processed[identity.work_order_sha256]
        execution = execution_by_stage[identity.experiment_stage]
        result = computed.assembled.row_results[identity.row_id]
        rows.append(
            MeasurementRow.model_validate(
                {
                    **identity.model_dump(mode="python"),
                    "schema_version": "1.0.0",
                    "matrix_row_ordinal": ordinal,
                    "execution_manifest_sha256": execution.execution_manifest_sha256,
                    "execution_completion_sha256": execution.execution_completion_sha256,
                    "capture_receipt_sha256": source.capture.receipt_sha256,
                    "run_record_sha256": source.capture.run_record_sha256,
                    "ordered_artifact_sha256": source.capture.ordered_artifact_sha256,
                    "baseline_reference_row_ids": computed.assembled.baseline_reference_row_ids[
                        identity.row_id
                    ],
                    "qc_metrics": source.qc,
                    "baseline_difference_metrics": result.metrics,
                    "qc_decision": "not_evaluated",
                    "thresholds_applied": False,
                    "development_synthetic_run": True,
                    "data_origin": "synthetic",
                    "run_mode": "development",
                    "formal_eligible": False,
                    "experimental_result": False,
                    "hardware_io_performed": False,
                }
            )
        )
    return MeasurementRowIndex(schema_version="1.0.0", row_count=len(rows), rows=tuple(rows))


def _payloads(
    *,
    sources: tuple[AnalysisExecutionSource, ...] | list[AnalysisExecutionSource],
    analysis_spec: LoadedDevelopmentAnalysisMatrixSpec,
    analysis_id: str,
    created_at: datetime,
) -> _Payloads:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise AnalysisPersistenceError("analysis created_at must be timezone-aware")
    try:
        validated = validate_synthetic_analysis_sources(
            sources=sources, analysis_spec=analysis_spec
        )
        computed = compute_measurement_matrix(validated)
        counts = Counter(row.experiment_stage for row in computed.identities)
        if len(computed.identities) != 344 or counts != {1: 152, 2: 32, 3: 32, 4: 128}:
            raise ValueError(f"measurement row counts differ from the fixture contract: {counts}")
        binding = _source_binding(computed, analysis_id)
        row_index = _row_index(computed)
        feature_schema = _feature_schema()
        split_plan = build_grouped_split_plan(computed.identities)
        core = {
            "analysis_source_binding.json": canonical_json_bytes(binding.model_dump(mode="json")),
            "measurement_row_index.json": canonical_json_bytes(row_index.model_dump(mode="json")),
            "feature_schema.json": canonical_json_bytes(feature_schema.model_dump(mode="json")),
            "split_plan.json": canonical_json_bytes(split_plan.model_dump(mode="json")),
            "measurement_matrix.npz": deterministic_npz_bytes(computed.assembled.arrays),
        }
        digests = {name: sha256_bytes(payload) for name, payload in core.items()}
        state = provisional_state()
        receipt = AnalysisReceipt.model_validate(
            {
                **state,
                "schema_version": "1.0.0",
                "algorithm_id": "plan_bound_synthetic_measurement_matrix",
                "algorithm_version": "1.0.0",
                "analysis_id": analysis_id,
                "analysis_source_binding_sha256": digests["analysis_source_binding.json"],
                "measurement_row_index_sha256": digests["measurement_row_index.json"],
                "feature_schema_sha256": digests["feature_schema.json"],
                "split_plan_sha256": digests["split_plan.json"],
                "measurement_matrix_npz_sha256": digests["measurement_matrix.npz"],
                "ordered_source_aggregate_sha256": validated.ordered_source_aggregate_sha256,
                "feature_count": 16,
                "split_fold_count": 24,
            }
        )
        receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
        receipt_digest = sha256_bytes(receipt_bytes)
        metadata = AnalysisMetadata.model_validate(
            {
                **state,
                "schema_version": "1.0.0",
                "analysis_id": analysis_id,
                "created_at": created_at,
                "receipt_sha256": receipt_digest,
            }
        )
        record = AnalysisRecord.model_validate(
            {
                **state,
                "schema_version": "1.0.0",
                "analysis_id": analysis_id,
                "analysis_relative_path": f"analyses/analysis_{analysis_id}",
                "created_at": created_at,
                "receipt_sha256": receipt_digest,
                "immutable_status": "complete",
            }
        )
    except AnalysisPersistenceError:
        raise
    except (AnalysisSourceError, OSError, ValueError, ValidationError) as exc:
        raise AnalysisPersistenceError(f"analysis computation failed: {exc}") from exc
    files = dict(core)
    for filename, digest in digests.items():
        sidecar = filename.removesuffix(".json").removesuffix(".npz") + (
            ".npz.sha256" if filename.endswith(".npz") else ".sha256"
        )
        files[sidecar] = _sidecar(digest, filename)
    files["analysis_receipt.json"] = receipt_bytes
    files["analysis_receipt.sha256"] = _sidecar(receipt_digest, "analysis_receipt.json")
    files["analysis_metadata.json"] = canonical_json_bytes(metadata.model_dump(mode="json"))
    files["analysis_record.json"] = canonical_json_bytes(record.model_dump(mode="json"))
    files[COMPLETE_NAME] = COMPLETE_BYTES
    if set(files) != ENVELOPE_NAMES:
        raise AnalysisPersistenceError("internal analysis envelope schema differs from 15 files")
    return _Payloads(dict(sorted(files.items())), receipt, receipt_digest)


def _published(
    store: SyntheticMeasurementMatrixStore, analysis_id: str, payloads: _Payloads
) -> PublishedSyntheticMeasurementMatrix:
    return PublishedSyntheticMeasurementMatrix(
        analysis_id=analysis_id,
        analysis_path=str(store.analysis_path(analysis_id)),
        receipt=payloads.receipt,
        receipt_sha256=payloads.receipt_sha256,
    )


def _prepare_parent(store: SyntheticMeasurementMatrixStore) -> None:
    if store.synthetic_root.exists() and _is_reparse_point(store.synthetic_root):
        raise AnalysisPersistenceError("synthetic root cannot be a symlink or reparse point")
    store.synthetic_root.mkdir(parents=True, exist_ok=True)
    if store.analyses_root.exists() and _is_reparse_point(store.analyses_root):
        raise AnalysisPersistenceError("analyses root cannot be a symlink or reparse point")
    store.analyses_root.mkdir(exist_ok=True)


def _cleanup(path: Path | None, lock_fd: int | None, lock: Path) -> list[str]:
    failures: list[str] = []
    if path is not None and path.exists():
        try:
            shutil.rmtree(path)
        except Exception as exc:
            failures.append(f"staging cleanup failed: {type(exc).__name__}: {exc}")
    if lock_fd is not None:
        try:
            os.close(lock_fd)
        except Exception as exc:
            failures.append(f"lock close failed: {type(exc).__name__}: {exc}")
    if lock.exists():
        try:
            lock.unlink()
        except Exception as exc:
            failures.append(f"lock unlink failed: {type(exc).__name__}: {exc}")
    return failures


def compute_synthetic_measurement_matrix(
    *,
    store: SyntheticMeasurementMatrixStore,
    sources: tuple[AnalysisExecutionSource, ...] | list[AnalysisExecutionSource],
    analysis_spec: LoadedDevelopmentAnalysisMatrixSpec,
    analysis_id: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> PublishedSyntheticMeasurementMatrix:
    """Compute and immutably publish one plan-bound synthetic measurement matrix."""

    _identifier(analysis_id)
    target = store.analysis_path(analysis_id)
    lock = store.analyses_root / f".analysis_{analysis_id}.lock"
    if target.exists():
        if target.is_dir() and {path.name for path in target.iterdir()} == ENVELOPE_NAMES:
            raise AnalysisPersistenceError("completed analysis target already exists")
        raise AnalysisPersistenceError("partial analysis target already exists")
    if lock.exists():
        raise AnalysisPersistenceError("analysis publication is already in progress")
    payloads = _payloads(
        sources=sources,
        analysis_spec=analysis_spec,
        analysis_id=analysis_id,
        created_at=now(),
    )
    _prepare_parent(store)
    lock_fd: int | None = None
    staging: Path | None = None
    body_error: BaseException | None = None
    try:
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise AnalysisPersistenceError("analysis publication is already in progress") from exc
        if target.exists():
            raise AnalysisPersistenceError("analysis target appeared during publication")
        staging = Path(
            tempfile.mkdtemp(prefix=f".analysis_{analysis_id}.staging-", dir=store.analyses_root)
        )
        for name, payload in payloads.files.items():
            if name == COMPLETE_NAME:
                continue
            with (staging / name).open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        with (staging / COMPLETE_NAME).open("xb") as handle:
            handle.write(COMPLETE_BYTES)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(staging, target)
        staging = None
    except BaseException as exc:
        body_error = exc
    cleanup_failures = _cleanup(staging, lock_fd, lock)
    if body_error is not None:
        if cleanup_failures:
            body_error.add_note("; ".join(cleanup_failures))
        if not isinstance(body_error, Exception):
            raise body_error.with_traceback(body_error.__traceback__)
        published = target.is_dir() and {path.name for path in target.iterdir()} == ENVELOPE_NAMES
        if isinstance(body_error, AnalysisPersistenceError) and not cleanup_failures:
            raise body_error.with_traceback(body_error.__traceback__)
        detail = f"analysis publication failed: {type(body_error).__name__}: {body_error}"
        if cleanup_failures:
            detail += "; " + "; ".join(cleanup_failures)
        raise AnalysisPersistenceError(detail, published=published) from body_error
    if cleanup_failures:
        published = target.is_dir() and {path.name for path in target.iterdir()} == ENVELOPE_NAMES
        raise AnalysisPersistenceError(
            "analysis publication cleanup failed: " + "; ".join(cleanup_failures),
            published=published,
        )
    return _published(store, analysis_id, payloads)


def validate_synthetic_measurement_matrix(
    *,
    store: SyntheticMeasurementMatrixStore,
    sources: tuple[AnalysisExecutionSource, ...] | list[AnalysisExecutionSource],
    analysis_spec: LoadedDevelopmentAnalysisMatrixSpec,
    analysis_id: str,
) -> PublishedSyntheticMeasurementMatrix:
    """Read and replay a complete analysis envelope without writing or cleanup."""

    target = store.analysis_path(analysis_id)
    if (
        not target.is_dir()
        or _is_reparse_point(target)
        or {path.name for path in target.iterdir()} != ENVELOPE_NAMES
    ):
        raise AnalysisPersistenceError("incomplete analysis envelope")
    try:
        metadata_bytes = (target / "analysis_metadata.json").read_bytes()
        metadata = AnalysisMetadata.model_validate_json(metadata_bytes)
        if canonical_json_bytes(metadata.model_dump(mode="json")) != metadata_bytes:
            raise ValueError("analysis metadata bytes are not canonical")
        payloads = _payloads(
            sources=sources,
            analysis_spec=analysis_spec,
            analysis_id=analysis_id,
            created_at=metadata.created_at,
        )
        for name, expected in payloads.files.items():
            path = target / name
            if _is_reparse_point(path) or not path.is_file() or path.read_bytes() != expected:
                raise ValueError(f"analysis payload differs from full replay: {name}")
    except AnalysisPersistenceError:
        raise
    except (OSError, ValueError, ValidationError) as exc:
        raise AnalysisPersistenceError(f"analysis validation failed: {exc}") from exc
    return _published(store, analysis_id, payloads)


__all__ = [
    "AnalysisPersistenceError",
    "SyntheticMeasurementMatrixStore",
    "compute_synthetic_measurement_matrix",
    "validate_synthetic_measurement_matrix",
]
