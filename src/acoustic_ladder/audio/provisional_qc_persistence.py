"""Immutable publication and read-only replay validation for provisional synthetic QC."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder.audio.ess_processing_models import PublishedEssProcessing
from acoustic_ladder.audio.ess_processing_persistence import (
    ARRAYS_NAME,
    EssProcessingPersistenceError,
    validate_ess_processing,
)
from acoustic_ladder.audio.excitation_persistence import decode_ieee_float32_wav
from acoustic_ladder.audio.provisional_qc import (
    ProvisionalQcError,
    QcProcessingEvidence,
    compute_provisional_qc_metrics,
)
from acoustic_ladder.audio.provisional_qc_models import (
    QC_SAFETY_MARKER,
    ProvisionalQcMetrics,
    ProvisionalQcReceipt,
    PublishedProvisionalQc,
    QcCreatedEvent,
    QcRecord,
)
from acoustic_ladder.audio.virtual_capture_models import LoadedVirtualCaptureScenario
from acoustic_ladder.audio.virtual_capture_persistence import INPUT_WAV, OUTPUT_WAV
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.storage.io import StorageError, safe_identifier, sha256_bytes
from acoustic_ladder.storage.npz import load_deterministic_npz
from acoustic_ladder.storage.store import ImmutableSessionStore

METRICS_NAME = "qc_metrics.json"
METRICS_SIDECAR = "qc_metrics.sha256"
RECEIPT_NAME = "qc_receipt.json"
RECEIPT_SIDECAR = "qc_receipt.sha256"
METADATA_NAME = "qc_metadata.json"
RECORD_NAME = "qc_record.json"
COMPLETE_NAME = "QC_COMPLETE"
QC_COMPLETE_BYTES = b"complete\n"
QC_EVENT_NAME = "qc_created"
QC_FILE_NAMES = frozenset(
    {
        METRICS_NAME,
        METRICS_SIDECAR,
        RECEIPT_NAME,
        RECEIPT_SIDECAR,
        METADATA_NAME,
        RECORD_NAME,
        COMPLETE_NAME,
    }
)
_ASCII_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]+$")


class ProvisionalQcPersistenceError(StorageError):
    """QC publication/validation error carrying whether the envelope was published."""

    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(f"{message}; published={str(published).lower()}")
        self.published = published


def _identifier(value: str, label: str) -> None:
    if _ASCII_IDENTIFIER.fullmatch(value) is None or value in {".", ".."}:
        raise ProvisionalQcPersistenceError(f"unsafe {label}: {value!r}", published=False)
    safe_identifier(value, label)


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _analysis(bundle: LoadedBundle) -> AnalysisConfig:
    loaded = bundle.configs.get("analysis")
    if loaded is None or not isinstance(loaded.model, AnalysisConfig):
        raise ProvisionalQcPersistenceError(
            "QC requires a loaded analysis configuration", published=False
        )
    if loaded.model.decision_gates.qc_threshold is not None:
        raise ProvisionalQcPersistenceError(
            "provisional QC refuses a non-null qc_threshold", published=False
        )
    return loaded.model


def _evidence(processing: PublishedEssProcessing) -> QcProcessingEvidence:
    receipt = processing.receipt
    return QcProcessingEvidence(
        sample_rate_hz=receipt.sample_rate_hz,
        sweep_sample_count=receipt.sweep_sample_count,
        pre_silence_sample_count=receipt.pre_silence_sample_count,
        transfer_fft_length=receipt.transfer_fft_length,
        estimated_latency_samples=receipt.estimated_latency_samples,
        estimated_latency_seconds=receipt.estimated_latency_seconds,
        matched_correlation_signed=receipt.matched_correlation_signed,
        matched_correlation_absolute=receipt.matched_correlation_absolute,
        ir_dominant_peak_index=receipt.ir_dominant_peak_index,
        ir_dominant_peak_value=receipt.ir_dominant_peak_value,
        reference_peak_index=receipt.reference_peak_index,
    )


def _compute(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    source_run_id: str,
    processing_id: str,
) -> tuple[ProvisionalQcMetrics, PublishedEssProcessing]:
    try:
        processing = validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            session_id=session_id,
            source_run_id=source_run_id,
            processing_id=processing_id,
        )
    except EssProcessingPersistenceError as exc:
        raise ProvisionalQcPersistenceError(str(exc), published=False) from exc
    _analysis(bundle)
    run_path = store.session_path(DataOrigin.SYNTHETIC, session_id) / "raw" / f"run_{source_run_id}"
    try:
        output, output_rate = decode_ieee_float32_wav((run_path / OUTPUT_WAV).read_bytes())
        captured, input_rate = decode_ieee_float32_wav((run_path / INPUT_WAV).read_bytes())
        arrays = load_deterministic_npz((processing.processing_path / ARRAYS_NAME).read_bytes())
        if output_rate != processing.receipt.sample_rate_hz or input_rate != output_rate:
            raise ProvisionalQcError("QC source sample rates disagree with processing receipt")
        metrics = compute_provisional_qc_metrics(output, captured, arrays, _evidence(processing))
    except (OSError, ValueError, ProvisionalQcError) as exc:
        raise ProvisionalQcPersistenceError(str(exc), published=False) from exc
    return metrics, processing


def _receipt(
    *,
    session_id: str,
    source_run_id: str,
    processing_id: str,
    qc_id: str,
    processing: PublishedEssProcessing,
    metrics_sha256: str,
) -> ProvisionalQcReceipt:
    source = processing.receipt
    return ProvisionalQcReceipt(
        schema_version="1.0.0",
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
        qc_id=qc_id,
        data_origin="synthetic",
        run_mode="development",
        source_capture_receipt_sha256=source.source_capture_receipt_sha256,
        source_processing_receipt_sha256=processing.receipt_sha256,
        source_processing_arrays_sha256=processing.arrays_sha256,
        source_processing_schema_version=source.schema_version,
        source_processing_algorithm_id=source.algorithm_id,
        source_processing_algorithm_version=source.algorithm_version,
        bundle_content_sha256=source.bundle_content_sha256,
        device_manifest_sha256=source.device_manifest_sha256,
        analysis_config_reference=source.analysis_config_reference,
        analysis_config_raw_sha256=source.analysis_config_raw_sha256,
        analysis_config_normalized_sha256=source.analysis_config_normalized_sha256,
        qc_metrics_sha256=metrics_sha256,
        qc_algorithm_id="provisional_offline_qc_metrics",
        qc_algorithm_version="1.0.0",
        waveform_metric_formula_id="float64_peak_rms_active_pre_and_abs_ge_one_clip",
        snr_proxy_formula_id="20_log10_input_active_rms_over_pre_silence_rms",
        latency_evidence_source="validated_processing_receipt",
        ir_concentration_formula_id="dominant_abs_over_second_largest_abs",
        reference_residual_formula_id="reference_peak_abs_over_off_peak_rms",
        spectral_coverage_formula_id=(
            "rfft_reference_above_max_abs_times_float64_epsilon_times_reference_count"
        ),
        metric_computation_status="complete",
        evaluation_status="provisional_metrics_only",
        decision_status="not_evaluated",
        thresholds_applied=False,
        qc_threshold=None,
        threshold_source=None,
        create_only=True,
        immutable=True,
        hardware_io_performed=False,
        playback_performed=False,
        recording_performed=False,
        hardware_ready=False,
        full_duplex_verified=False,
        shared_clock_verified=False,
        channel_mapping_verified=False,
        calibration_file_verified=False,
        calibration_applied=False,
        absolute_spl_calibrated=False,
        electrical_loopback_available=False,
        formal_eligible=False,
        experimental_result=False,
        safety_marker=QC_SAFETY_MARKER,
    )


def _metadata(metrics_sha256: str, receipt_sha256: str) -> dict[str, object]:
    return {
        "data_origin": "synthetic",
        "decision_status": "not_evaluated",
        "evaluation_status": "provisional_metrics_only",
        "experimental_result": False,
        "formal_eligible": False,
        "hardware_io_performed": False,
        "hardware_ready": False,
        "metric_computation_status": "complete",
        "qc_metrics_sha256": metrics_sha256,
        "qc_receipt_sha256": receipt_sha256,
        "run_mode": "development",
        "safety_marker": QC_SAFETY_MARKER,
        "thresholds_applied": False,
    }


def publish_provisional_qc(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    source_run_id: str,
    processing_id: str,
    qc_id: str,
    now: Callable[[], datetime],
) -> PublishedProvisionalQc:
    """Replay processing, compute threshold-free metrics, and create-only publish QC."""

    metrics, processing = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
    )
    _identifier(qc_id, "qc_id")
    metrics_bytes = canonical_json_bytes(metrics.model_dump(mode="json"))
    metrics_digest = sha256_bytes(metrics_bytes)
    receipt = _receipt(
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
        qc_id=qc_id,
        processing=processing,
        metrics_sha256=metrics_digest,
    )
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    receipt_digest = sha256_bytes(receipt_bytes)
    timestamp = now()
    record = QcRecord(
        schema_version="1.0.0",
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
        qc_id=qc_id,
        created_at=timestamp,
        status="complete",
        qc_metrics_sha256=metrics_digest,
        qc_receipt_sha256=receipt_digest,
        data_origin="synthetic",
        run_mode="development",
        evaluation_status="provisional_metrics_only",
        decision_status="not_evaluated",
        formal_eligible=False,
        experimental_result=False,
        result_marker="NOT_AN_EXPERIMENTAL_RESULT",
    )
    record_bytes = canonical_json_bytes(record.model_dump(mode="json"))
    target = (
        store.session_path(DataOrigin.SYNTHETIC, session_id)
        / "qc"
        / f"run_{source_run_id}"
        / f"processing_{processing_id}"
        / f"qc_{qc_id}"
    )
    try:
        path = store.create_synthetic_qc(
            session_id=session_id,
            source_run_id=source_run_id,
            processing_id=processing_id,
            qc_id=qc_id,
            artifact_payloads={
                METRICS_NAME: metrics_bytes,
                METRICS_SIDECAR: _sidecar(metrics_digest, METRICS_NAME),
                RECEIPT_NAME: receipt_bytes,
                RECEIPT_SIDECAR: _sidecar(receipt_digest, RECEIPT_NAME),
            },
            metadata=_metadata(metrics_digest, receipt_digest),
            record=record,
        )
        store.append_event(
            DataOrigin.SYNTHETIC,
            session_id,
            QC_EVENT_NAME,
            {
                "schema_version": "1.0.0",
                "source_run_id": source_run_id,
                "processing_id": processing_id,
                "qc_id": qc_id,
                "created_at": record.model_dump(mode="json")["created_at"],
                "qc_record_sha256": sha256_bytes(record_bytes),
                "qc_metrics_sha256": metrics_digest,
                "qc_receipt_sha256": receipt_digest,
            },
        )
    except Exception as exc:
        published = (target / COMPLETE_NAME).is_file()
        raise ProvisionalQcPersistenceError(str(exc), published=published) from exc
    return PublishedProvisionalQc(path, metrics, receipt, metrics_digest, receipt_digest, timestamp)


def _verify_sidecar(root: Path, filename: str, sidecar: str) -> str:
    try:
        payload = (root / filename).read_bytes()
        actual = (root / sidecar).read_bytes()
    except OSError as exc:
        raise ProvisionalQcPersistenceError(str(exc), published=True) from exc
    digest = sha256_bytes(payload)
    if actual != _sidecar(digest, filename):
        raise ProvisionalQcPersistenceError(
            f"invalid SHA256 sidecar for {filename}", published=True
        )
    return digest


def _validated_event(
    *,
    store: ImmutableSessionStore,
    session_id: str,
    source_run_id: str,
    processing_id: str,
    qc_id: str,
    record: QcRecord,
    record_bytes: bytes,
    metrics_sha256: str,
    receipt_sha256: str,
) -> QcCreatedEvent:
    events_root = store.session_path(DataOrigin.SYNTHETIC, session_id) / "events"
    matching: list[QcCreatedEvent] = []
    for path in sorted(events_root.glob(f"*_{QC_EVENT_NAME}.json")):
        try:
            raw = path.read_bytes()
            event = QcCreatedEvent.model_validate_json(raw)
        except (OSError, ValidationError) as exc:
            raise ProvisionalQcPersistenceError(
                f"invalid {QC_EVENT_NAME} event: {exc}", published=True
            ) from exc
        if raw != canonical_json_bytes(event.model_dump(mode="json")):
            raise ProvisionalQcPersistenceError(
                f"noncanonical {QC_EVENT_NAME} event", published=True
            )
        if path.name != f"{event.sequence:06d}_{QC_EVENT_NAME}.json":
            raise ProvisionalQcPersistenceError(
                f"invalid {QC_EVENT_NAME} event filename sequence", published=True
            )
        if (
            event.source_run_id == source_run_id
            and event.processing_id == processing_id
            and event.qc_id == qc_id
        ):
            matching.append(event)
    if len(matching) != 1:
        raise ProvisionalQcPersistenceError(
            f"expected exactly one matching {QC_EVENT_NAME} event", published=True
        )
    event = matching[0]
    if (
        event.session_id != session_id
        or event.data_origin != "synthetic"
        or event.created_at != record.created_at
        or event.qc_record_sha256 != sha256_bytes(record_bytes)
        or event.qc_metrics_sha256 != metrics_sha256
        or event.qc_receipt_sha256 != receipt_sha256
    ):
        raise ProvisionalQcPersistenceError(
            f"{QC_EVENT_NAME} event binding differs", published=True
        )
    return event


def validate_provisional_qc(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    source_run_id: str,
    processing_id: str,
    qc_id: str,
) -> PublishedProvisionalQc:
    """Read-only byte and semantic replay validation of a completed QC envelope."""

    metrics, processing = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
    )
    _identifier(qc_id, "qc_id")
    root = (
        store.session_path(DataOrigin.SYNTHETIC, session_id)
        / "qc"
        / f"run_{source_run_id}"
        / f"processing_{processing_id}"
        / f"qc_{qc_id}"
    )
    if not root.is_dir() or {entry.name for entry in root.iterdir()} != QC_FILE_NAMES:
        raise ProvisionalQcPersistenceError(
            "QC directory does not contain exactly the required files", published=True
        )
    metrics_digest = _verify_sidecar(root, METRICS_NAME, METRICS_SIDECAR)
    receipt_digest = _verify_sidecar(root, RECEIPT_NAME, RECEIPT_SIDECAR)
    metrics_bytes = (root / METRICS_NAME).read_bytes()
    receipt_bytes = (root / RECEIPT_NAME).read_bytes()
    record_bytes = (root / RECORD_NAME).read_bytes()
    try:
        stored_metrics = ProvisionalQcMetrics.model_validate_json(metrics_bytes)
        stored_receipt = ProvisionalQcReceipt.model_validate_json(receipt_bytes)
        record = QcRecord.model_validate_json(record_bytes)
    except ValidationError as exc:
        raise ProvisionalQcPersistenceError(str(exc), published=True) from exc
    for label, raw, model in (
        ("metrics", metrics_bytes, stored_metrics),
        ("receipt", receipt_bytes, stored_receipt),
        ("record", record_bytes, record),
    ):
        if raw != canonical_json_bytes(model.model_dump(mode="json")):
            raise ProvisionalQcPersistenceError(f"QC {label} is not canonical", published=True)
    event = _validated_event(
        store=store,
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
        qc_id=qc_id,
        record=record,
        record_bytes=record_bytes,
        metrics_sha256=metrics_digest,
        receipt_sha256=receipt_digest,
    )
    expected_metrics_bytes = canonical_json_bytes(metrics.model_dump(mode="json"))
    expected_metrics_digest = sha256_bytes(expected_metrics_bytes)
    expected_receipt = _receipt(
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
        qc_id=qc_id,
        processing=processing,
        metrics_sha256=expected_metrics_digest,
    )
    expected_receipt_bytes = canonical_json_bytes(expected_receipt.model_dump(mode="json"))
    expected_receipt_digest = sha256_bytes(expected_receipt_bytes)
    if stored_metrics != metrics or metrics_bytes != expected_metrics_bytes:
        raise ProvisionalQcPersistenceError("QC metrics differ from replay", published=True)
    if stored_receipt != expected_receipt or receipt_bytes != expected_receipt_bytes:
        raise ProvisionalQcPersistenceError("QC receipt differs from replay", published=True)
    expected_record = QcRecord(
        schema_version="1.0.0",
        session_id=session_id,
        source_run_id=source_run_id,
        processing_id=processing_id,
        qc_id=qc_id,
        created_at=event.created_at,
        status="complete",
        qc_metrics_sha256=expected_metrics_digest,
        qc_receipt_sha256=expected_receipt_digest,
        data_origin="synthetic",
        run_mode="development",
        evaluation_status="provisional_metrics_only",
        decision_status="not_evaluated",
        formal_eligible=False,
        experimental_result=False,
        result_marker="NOT_AN_EXPERIMENTAL_RESULT",
    )
    if record != expected_record:
        raise ProvisionalQcPersistenceError("QC record differs from replay", published=True)
    if (root / METADATA_NAME).read_bytes() != canonical_json_bytes(
        _metadata(expected_metrics_digest, expected_receipt_digest)
    ):
        raise ProvisionalQcPersistenceError("QC metadata differs", published=True)
    if (
        metrics_digest != expected_metrics_digest
        or receipt_digest != expected_receipt_digest
        or (root / COMPLETE_NAME).read_bytes() != QC_COMPLETE_BYTES
    ):
        raise ProvisionalQcPersistenceError("QC digest or completion differs", published=True)
    return PublishedProvisionalQc(
        root,
        stored_metrics,
        stored_receipt,
        metrics_digest,
        receipt_digest,
        record.created_at,
    )
