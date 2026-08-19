"""Immutable publication and read-only replay for synthetic repeatability evidence."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

import numpy as np
from pydantic import ValidationError

from acoustic_ladder.audio.conditioned_virtual_capture import (
    ConditionedVirtualCapturePersistenceError,
    validate_conditioned_virtual_capture,
)
from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    LoadedConditionedVirtualCaptureScenario,
    PublishedConditionedVirtualCapture,
)
from acoustic_ladder.audio.ess_processing_models import PublishedEssProcessing
from acoustic_ladder.audio.ess_processing_persistence import (
    ARRAYS_NAME,
    CaptureScenario,
    EssProcessingPersistenceError,
    validate_ess_processing,
)
from acoustic_ladder.audio.excitation_persistence import decode_ieee_float32_wav
from acoustic_ladder.audio.provisional_qc_models import PublishedProvisionalQc
from acoustic_ladder.audio.provisional_qc_persistence import (
    ProvisionalQcPersistenceError,
    validate_provisional_qc,
)
from acoustic_ladder.audio.repeatability import (
    RepeatabilityError,
    RepeatabilityKernelMember,
    compute_provisional_repeatability_metrics,
)
from acoustic_ladder.audio.repeatability_models import (
    REPEATABILITY_SAFETY_MARKER,
    ConditionedProvisionalRepeatabilityReceipt,
    ProvisionalRepeatabilityMetrics,
    ProvisionalRepeatabilityReceipt,
    PublishedProvisionalRepeatability,
    RepeatabilityCreatedEvent,
    RepeatabilityMemberIdentity,
    RepeatabilityMemberProvenance,
    RepeatabilityRecord,
)
from acoustic_ladder.audio.virtual_capture_persistence import (
    INPUT_WAV,
    PublishedVirtualCapture,
    VirtualCapturePersistenceError,
    validate_virtual_capture,
)
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.storage.io import StorageError, safe_identifier, sha256_bytes
from acoustic_ladder.storage.npz import load_deterministic_npz
from acoustic_ladder.storage.store import ImmutableSessionStore

METRICS_NAME = "repeatability_metrics.json"
METRICS_SIDECAR = "repeatability_metrics.sha256"
RECEIPT_NAME = "repeatability_receipt.json"
RECEIPT_SIDECAR = "repeatability_receipt.sha256"
METADATA_NAME = "repeatability_metadata.json"
RECORD_NAME = "repeatability_record.json"
COMPLETE_NAME = "REPEATABILITY_COMPLETE"
REPEATABILITY_COMPLETE_BYTES = b"complete\n"
REPEATABILITY_EVENT_NAME = "repeatability_created"
REPEATABILITY_FILE_NAMES = frozenset(
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


class RepeatabilityPersistenceError(StorageError):
    """Repeatability error carrying whether the immutable directory exists."""

    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(f"{message}; published={str(published).lower()}")
        self.published = published


@dataclass(frozen=True)
class _LoadedMember:
    capture: PublishedVirtualCapture | PublishedConditionedVirtualCapture
    processing: PublishedEssProcessing
    qc: PublishedProvisionalQc
    provenance: RepeatabilityMemberProvenance
    kernel: RepeatabilityKernelMember
    compatibility_key: tuple[object, ...]


def _identifier(value: str, label: str) -> None:
    if _ASCII_IDENTIFIER.fullmatch(value) is None or value in {".", ".."}:
        raise RepeatabilityPersistenceError(f"unsafe {label}: {value!r}", published=False)
    safe_identifier(value, label)


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


class _StatePayload(TypedDict):
    decision_status: Literal["not_evaluated"]
    repeatability_decision: Literal["not_evaluated"]
    thresholds_applied: Literal[False]
    repeatability_threshold: None
    threshold_source: None
    baseline_assigned: Literal[False]
    baseline_role: Literal["not_assigned"]
    baseline_selection_status: Literal["deferred_until_protocol_binding"]
    baseline_difference_computed: Literal[False]
    protocol_condition_binding_performed: Literal[False]
    drift_evaluated: Literal[False]
    drift_decision: Literal["not_evaluated"]


def _state() -> _StatePayload:
    return {
        "decision_status": "not_evaluated",
        "repeatability_decision": "not_evaluated",
        "thresholds_applied": False,
        "repeatability_threshold": None,
        "threshold_source": None,
        "baseline_assigned": False,
        "baseline_role": "not_assigned",
        "baseline_selection_status": "deferred_until_protocol_binding",
        "baseline_difference_computed": False,
        "protocol_condition_binding_performed": False,
        "drift_evaluated": False,
        "drift_decision": "not_evaluated",
    }


def _analysis_gate(bundle: LoadedBundle) -> AnalysisConfig:
    loaded = bundle.configs.get("analysis")
    if loaded is None or not isinstance(loaded.model, AnalysisConfig):
        raise RepeatabilityPersistenceError(
            "repeatability requires an active AnalysisConfig", published=False
        )
    analysis = loaded.model
    configured = {
        "baseline_selection_rule": analysis.baseline_selection_rule,
        "qc_threshold": analysis.decision_gates.qc_threshold,
        "effect_threshold": analysis.decision_gates.effect_threshold,
        "drift_threshold": analysis.decision_gates.drift_threshold,
        "classification_pass_threshold": (analysis.decision_gates.classification_pass_threshold),
    }
    non_null = [name for name, value in configured.items() if value is not None]
    if non_null:
        raise RepeatabilityPersistenceError(
            f"repeatability requires null AnalysisConfig fields: {non_null}",
            published=False,
        )
    normalized = canonical_json_bytes(analysis.model_dump(mode="json"))
    if (
        normalized != loaded.normalized_bytes
        or sha256_bytes(normalized) != loaded.snapshot.normalized_sha256
    ):
        raise RepeatabilityPersistenceError(
            "active AnalysisConfig differs from its normalized provenance",
            published=False,
        )
    return analysis


def _member_list_bytes(members: Sequence[RepeatabilityMemberProvenance]) -> bytes:
    return canonical_json_bytes([member.model_dump(mode="json") for member in members])


def _load_member(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: CaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    identity: RepeatabilityMemberIdentity,
) -> _LoadedMember:
    for label, value in (
        ("source_run_id", identity.source_run_id),
        ("processing_id", identity.processing_id),
        ("qc_id", identity.qc_id),
    ):
        _identifier(value, label)
    try:
        capture: PublishedVirtualCapture | PublishedConditionedVirtualCapture
        if isinstance(scenario, LoadedConditionedVirtualCaptureScenario):
            capture = validate_conditioned_virtual_capture(
                store=store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess_artifact_root,
                session_id=session_id,
                run_id=identity.source_run_id,
            )
        else:
            capture = validate_virtual_capture(
                store=store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess_artifact_root,
                session_id=session_id,
                run_id=identity.source_run_id,
            )
        processing = validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            session_id=session_id,
            source_run_id=identity.source_run_id,
            processing_id=identity.processing_id,
        )
        qc = validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            session_id=session_id,
            source_run_id=identity.source_run_id,
            processing_id=identity.processing_id,
            qc_id=identity.qc_id,
        )
    except (
        OSError,
        ValueError,
        VirtualCapturePersistenceError,
        ConditionedVirtualCapturePersistenceError,
        EssProcessingPersistenceError,
        ProvisionalQcPersistenceError,
    ) as exc:
        raise RepeatabilityPersistenceError(str(exc), published=False) from exc

    capture_receipt = capture.receipt
    processing_receipt = processing.receipt
    qc_receipt = qc.receipt
    if (
        processing_receipt.source_capture_receipt_sha256 != capture.receipt_sha256
        or qc_receipt.source_capture_receipt_sha256 != capture.receipt_sha256
        or qc_receipt.source_processing_receipt_sha256 != processing.receipt_sha256
        or qc_receipt.source_processing_arrays_sha256 != processing.arrays_sha256
    ):
        raise RepeatabilityPersistenceError(
            "member evidence digest chains disagree", published=False
        )
    try:
        captured, sample_rate = decode_ieee_float32_wav((capture.run_path / INPUT_WAV).read_bytes())
        arrays = load_deterministic_npz((processing.processing_path / ARRAYS_NAME).read_bytes())
        mask = arrays["analysis_band_mask"]
        if sample_rate != processing_receipt.sample_rate_hz:
            raise RepeatabilityError("captured input sample rate differs from processing")
        kernel = RepeatabilityKernelMember(
            identity=identity,
            measurement_order=capture_receipt.measurement_order,
            latency_samples=processing_receipt.estimated_latency_samples,
            pre_silence_sample_count=processing_receipt.pre_silence_sample_count,
            captured_input=captured,
            ir_aligned=arrays["ir_aligned"],
            transfer_aligned_real=arrays["transfer_aligned_real"],
            transfer_aligned_imag=arrays["transfer_aligned_imag"],
            analysis_band_mask=mask,
        )
    except (OSError, KeyError, ValueError, RepeatabilityError) as exc:
        raise RepeatabilityPersistenceError(str(exc), published=False) from exc

    provenance = RepeatabilityMemberProvenance(
        identity=identity,
        measurement_order=capture_receipt.measurement_order,
        estimated_latency_samples=processing_receipt.estimated_latency_samples,
        capture_receipt_sha256=capture.receipt_sha256,
        captured_input_wav_sha256=capture_receipt.input_wav_sha256,
        processing_receipt_sha256=processing.receipt_sha256,
        processing_arrays_sha256=processing.arrays_sha256,
        qc_metrics_sha256=qc.metrics_sha256,
        qc_receipt_sha256=qc.receipt_sha256,
    )
    audio_snapshot = capture_receipt.config_snapshots["audio_config"]
    analysis_snapshot = capture_receipt.config_snapshots["analysis_config"]
    mask_bytes = np.ascontiguousarray(mask, dtype=np.bool_).tobytes(order="C")
    compatibility_key: tuple[object, ...] = (
        capture_receipt.reassembly_id,
        capture_receipt.bundle_content_sha256,
        capture_receipt.device_manifest_sha256,
        canonical_json_bytes(audio_snapshot.model_dump(mode="json")),
        canonical_json_bytes(analysis_snapshot.model_dump(mode="json")),
        capture_receipt.scenario_reference,
        capture_receipt.scenario_raw_sha256,
        capture_receipt.scenario_normalized_sha256,
        capture_receipt.source_ess_artifact_id,
        capture_receipt.source_ess_metadata_sha256,
        capture_receipt.source_ess_wav_sha256,
        capture_receipt.source_ess_raw_float32_sha256,
        processing_receipt.schema_version,
        processing_receipt.algorithm_id,
        processing_receipt.algorithm_version,
        qc_receipt.schema_version,
        qc_receipt.qc_algorithm_id,
        qc_receipt.qc_algorithm_version,
        processing_receipt.sample_rate_hz,
        processing_receipt.sweep_sample_count,
        processing_receipt.pre_silence_sample_count,
        processing_receipt.post_silence_sample_count,
        processing_receipt.transfer_fft_length,
        processing_receipt.frequency_bin_count,
        processing_receipt.ir_sample_count,
        int(np.count_nonzero(mask)),
        sha256_bytes(mask_bytes),
    )
    if isinstance(capture, PublishedConditionedVirtualCapture):
        conditioned = capture.receipt
        compatibility_key += (
            conditioned.protocol_id,
            conditioned.condition_plan_reference,
            conditioned.condition_plan_raw_sha256,
            conditioned.condition_plan_normalized_sha256,
            conditioned.source_protocol_reference,
            conditioned.source_protocol_raw_sha256,
            conditioned.source_protocol_normalized_sha256,
            conditioned.condition_id,
            conditioned.condition_role,
            conditioned.resolved_node_states_sha256,
        )
    return _LoadedMember(capture, processing, qc, provenance, kernel, compatibility_key)


def _compute(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: CaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    members: Sequence[RepeatabilityMemberIdentity],
) -> tuple[ProvisionalRepeatabilityMetrics, list[_LoadedMember]]:
    _analysis_gate(bundle)
    _identifier(session_id, "session_id")
    if len(members) < 2:
        raise RepeatabilityPersistenceError(
            "repeatability requires at least two members", published=False
        )
    loaded = [
        _load_member(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            session_id=session_id,
            identity=member,
        )
        for member in members
    ]
    if any(member.compatibility_key != loaded[0].compatibility_key for member in loaded[1:]):
        raise RepeatabilityPersistenceError(
            "repeatability members do not share one compatible provenance context",
            published=False,
        )
    loaded.sort(key=lambda member: member.provenance.measurement_order)
    try:
        metrics = compute_provisional_repeatability_metrics([member.kernel for member in loaded])
    except (RepeatabilityError, ValidationError) as exc:
        raise RepeatabilityPersistenceError(str(exc), published=False) from exc
    return metrics, loaded


def _receipt(
    *,
    session_id: str,
    repeat_set_id: str,
    loaded: Sequence[_LoadedMember],
    metrics_sha256: str,
) -> ProvisionalRepeatabilityReceipt | ConditionedProvisionalRepeatabilityReceipt:
    first = loaded[0]
    capture = first.capture.receipt
    processing = first.processing.receipt
    qc = first.qc.receipt
    members = [member.provenance for member in loaded]
    audio = capture.config_snapshots["audio_config"]
    analysis = capture.config_snapshots["analysis_config"]
    mask = first.kernel.analysis_band_mask
    mask_bytes = np.ascontiguousarray(mask, dtype=np.bool_).tobytes(order="C")
    common: dict[str, object] = dict(
        schema_version="1.1.0",
        session_id=session_id,
        reassembly_id=capture.reassembly_id,
        repeat_set_id=repeat_set_id,
        data_origin="synthetic",
        run_mode="development",
        members=members,
        normalized_member_list_sha256=sha256_bytes(_member_list_bytes(members)),
        bundle_content_sha256=capture.bundle_content_sha256,
        device_manifest_sha256=capture.device_manifest_sha256,
        audio_config_reference=audio.original_relative_path,
        audio_config_raw_sha256=audio.original_sha256,
        audio_config_normalized_sha256=audio.normalized_sha256,
        analysis_config_reference=analysis.original_relative_path,
        analysis_config_raw_sha256=analysis.original_sha256,
        analysis_config_normalized_sha256=analysis.normalized_sha256,
        virtual_scenario_reference=capture.scenario_reference,
        virtual_scenario_raw_sha256=capture.scenario_raw_sha256,
        virtual_scenario_normalized_sha256=capture.scenario_normalized_sha256,
        source_ess_artifact_id=capture.source_ess_artifact_id,
        source_ess_metadata_sha256=capture.source_ess_metadata_sha256,
        source_ess_wav_sha256=capture.source_ess_wav_sha256,
        source_ess_raw_float32_sha256=capture.source_ess_raw_float32_sha256,
        processing_schema_version=processing.schema_version,
        processing_algorithm_id=processing.algorithm_id,
        processing_algorithm_version=processing.algorithm_version,
        qc_schema_version=qc.schema_version,
        qc_algorithm_id=qc.qc_algorithm_id,
        qc_algorithm_version=qc.qc_algorithm_version,
        sample_rate_hz=processing.sample_rate_hz,
        sweep_sample_count=processing.sweep_sample_count,
        pre_silence_sample_count=processing.pre_silence_sample_count,
        post_silence_sample_count=processing.post_silence_sample_count,
        transfer_fft_length=processing.transfer_fft_length,
        frequency_bin_count=processing.frequency_bin_count,
        ir_sample_count=processing.ir_sample_count,
        analysis_band_bin_count=int(np.count_nonzero(mask)),
        analysis_band_mask_sha256=sha256_bytes(mask_bytes),
        repeatability_metrics_sha256=metrics_sha256,
        repeatability_algorithm_id="provisional_continuous_repeatability_metrics",
        repeatability_algorithm_version="1.1.0",
        pair_enumeration_formula_id="all_unique_unordered_pairs_in_measurement_order",
        captured_input_correlation_formula_id=("normalized_dot_after_pre_silence_without_epsilon"),
        latency_delta_formula_id="validated_processing_latency_j_minus_i",
        ir_correlation_formula_id="normalized_dot_aligned_ir_without_epsilon",
        ir_symmetric_nrmse_formula_id="symmetric_l2_over_root_mean_square_norm",
        complex_transfer_relative_l2_formula_id=(
            "analysis_band_symmetric_complex_l2_over_root_mean_square_norm"
        ),
        magnitude_rmse_formula_id="float64_tiny_floor_20_log10_magnitude_rmse_db",
        phase_rms_formula_id=("joint_nonzero_angle_h_i_times_conjugate_h_j_rms_without_unwrap"),
        metric_computation_status="complete",
        evaluation_status="provisional_repeatability_metrics_only",
        **_state(),
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
        safety_marker=REPEATABILITY_SAFETY_MARKER,
    )
    if isinstance(first.capture, PublishedConditionedVirtualCapture):
        conditioned = first.capture.receipt
        common.update(
            schema_version="1.2.0",
            protocol_id=conditioned.protocol_id,
            condition_plan_id=conditioned.condition_plan_id,
            condition_plan_reference=conditioned.condition_plan_reference,
            condition_plan_raw_sha256=conditioned.condition_plan_raw_sha256,
            condition_plan_normalized_sha256=conditioned.condition_plan_normalized_sha256,
            source_protocol_reference=conditioned.source_protocol_reference,
            source_protocol_raw_sha256=conditioned.source_protocol_raw_sha256,
            source_protocol_normalized_sha256=conditioned.source_protocol_normalized_sha256,
            condition_id=conditioned.condition_id,
            condition_role=conditioned.condition_role,
            resolved_node_states=conditioned.resolved_node_states,
            resolved_node_states_sha256=conditioned.resolved_node_states_sha256,
            non_blk_node_count=sum(
                state.module_id != "BLK" for state in conditioned.resolved_node_states.values()
            ),
            protocol_condition_binding_performed=True,
            protocol_execution_performed=False,
        )
        return ConditionedProvisionalRepeatabilityReceipt.model_validate(common)
    return ProvisionalRepeatabilityReceipt.model_validate(common)


def _metadata(
    receipt: ProvisionalRepeatabilityReceipt | ConditionedProvisionalRepeatabilityReceipt,
    receipt_sha256: str,
) -> dict[str, object]:
    return {
        **_state(),
        "data_origin": "synthetic",
        "evaluation_status": "provisional_repeatability_metrics_only",
        "experimental_result": False,
        "formal_eligible": False,
        "hardware_io_performed": False,
        "metric_computation_status": "complete",
        "normalized_member_list_sha256": receipt.normalized_member_list_sha256,
        "reassembly_id": receipt.reassembly_id,
        "repeat_set_id": receipt.repeat_set_id,
        "repeatability_metrics_sha256": receipt.repeatability_metrics_sha256,
        "repeatability_receipt_sha256": receipt_sha256,
        "run_mode": "development",
        "safety_marker": REPEATABILITY_SAFETY_MARKER,
    }


def _target(
    store: ImmutableSessionStore, session_id: str, reassembly_id: str, repeat_set_id: str
) -> Path:
    return (
        store.session_path(DataOrigin.SYNTHETIC, session_id)
        / "qc"
        / "repeat_sets"
        / f"reassembly_{reassembly_id}"
        / f"repeat_set_{repeat_set_id}"
    )


def publish_provisional_repeatability(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: CaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    repeat_set_id: str,
    members: Sequence[RepeatabilityMemberIdentity],
    now: Callable[[], datetime],
) -> PublishedProvisionalRepeatability:
    """Replay member evidence and create-only publish threshold-free repeatability."""

    _identifier(repeat_set_id, "repeat_set_id")
    metrics, loaded = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        members=members,
    )
    metrics_bytes = canonical_json_bytes(metrics.model_dump(mode="json"))
    metrics_digest = sha256_bytes(metrics_bytes)
    receipt = _receipt(
        session_id=session_id,
        repeat_set_id=repeat_set_id,
        loaded=loaded,
        metrics_sha256=metrics_digest,
    )
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    receipt_digest = sha256_bytes(receipt_bytes)
    timestamp = now()
    record = RepeatabilityRecord(
        schema_version="1.1.0",
        session_id=session_id,
        reassembly_id=receipt.reassembly_id,
        repeat_set_id=repeat_set_id,
        created_at=timestamp,
        status="complete",
        repeatability_metrics_sha256=metrics_digest,
        repeatability_receipt_sha256=receipt_digest,
        normalized_member_list_sha256=receipt.normalized_member_list_sha256,
        data_origin="synthetic",
        run_mode="development",
        evaluation_status="provisional_repeatability_metrics_only",
        **_state(),
        formal_eligible=False,
        experimental_result=False,
        result_marker="NOT_AN_EXPERIMENTAL_RESULT",
    )
    record_bytes = canonical_json_bytes(record.model_dump(mode="json"))
    target = _target(store, session_id, receipt.reassembly_id, repeat_set_id)
    try:
        path = store.create_synthetic_repeatability(
            session_id=session_id,
            reassembly_id=receipt.reassembly_id,
            repeat_set_id=repeat_set_id,
            artifact_payloads={
                METRICS_NAME: metrics_bytes,
                METRICS_SIDECAR: _sidecar(metrics_digest, METRICS_NAME),
                RECEIPT_NAME: receipt_bytes,
                RECEIPT_SIDECAR: _sidecar(receipt_digest, RECEIPT_NAME),
            },
            metadata=_metadata(receipt, receipt_digest),
            record=record,
        )
        store.append_event(
            DataOrigin.SYNTHETIC,
            session_id,
            REPEATABILITY_EVENT_NAME,
            {
                "schema_version": "1.0.0",
                "reassembly_id": receipt.reassembly_id,
                "repeat_set_id": repeat_set_id,
                "created_at": record.model_dump(mode="json")["created_at"],
                "repeatability_record_sha256": sha256_bytes(record_bytes),
                "repeatability_metrics_sha256": metrics_digest,
                "repeatability_receipt_sha256": receipt_digest,
                "normalized_member_list_sha256": receipt.normalized_member_list_sha256,
            },
        )
    except Exception as exc:
        published = (target / COMPLETE_NAME).is_file()
        raise RepeatabilityPersistenceError(str(exc), published=published) from exc
    return PublishedProvisionalRepeatability(
        path, metrics, receipt, metrics_digest, receipt_digest, timestamp
    )


def _verify_sidecar(root: Path, filename: str, sidecar: str) -> str:
    try:
        payload = (root / filename).read_bytes()
        actual = (root / sidecar).read_bytes()
    except OSError as exc:
        raise RepeatabilityPersistenceError(str(exc), published=True) from exc
    digest = sha256_bytes(payload)
    if actual != _sidecar(digest, filename):
        raise RepeatabilityPersistenceError(
            f"invalid SHA256 sidecar for {filename}", published=True
        )
    return digest


def _validated_event(
    *,
    store: ImmutableSessionStore,
    session_id: str,
    reassembly_id: str,
    repeat_set_id: str,
    record: RepeatabilityRecord,
    record_bytes: bytes,
    metrics_sha256: str,
    receipt_sha256: str,
    member_list_sha256: str,
) -> RepeatabilityCreatedEvent:
    events_root = store.session_path(DataOrigin.SYNTHETIC, session_id) / "events"
    matching: list[RepeatabilityCreatedEvent] = []
    for path in sorted(events_root.glob(f"*_{REPEATABILITY_EVENT_NAME}.json")):
        try:
            raw = path.read_bytes()
            event = RepeatabilityCreatedEvent.model_validate_json(raw)
        except (OSError, ValidationError) as exc:
            raise RepeatabilityPersistenceError(
                f"invalid {REPEATABILITY_EVENT_NAME} event: {exc}", published=True
            ) from exc
        if raw != canonical_json_bytes(event.model_dump(mode="json")):
            raise RepeatabilityPersistenceError(
                f"noncanonical {REPEATABILITY_EVENT_NAME} event", published=True
            )
        if path.name != f"{event.sequence:06d}_{REPEATABILITY_EVENT_NAME}.json":
            raise RepeatabilityPersistenceError(
                f"invalid {REPEATABILITY_EVENT_NAME} event filename sequence", published=True
            )
        if event.reassembly_id == reassembly_id and event.repeat_set_id == repeat_set_id:
            matching.append(event)
    if len(matching) != 1:
        raise RepeatabilityPersistenceError(
            f"expected exactly one matching {REPEATABILITY_EVENT_NAME} event", published=True
        )
    event = matching[0]
    if (
        event.session_id != session_id
        or event.data_origin != "synthetic"
        or event.created_at != record.created_at
        or event.repeatability_record_sha256 != sha256_bytes(record_bytes)
        or event.repeatability_metrics_sha256 != metrics_sha256
        or event.repeatability_receipt_sha256 != receipt_sha256
        or event.normalized_member_list_sha256 != member_list_sha256
    ):
        raise RepeatabilityPersistenceError(
            f"{REPEATABILITY_EVENT_NAME} event binding differs", published=True
        )
    return event


def validate_provisional_repeatability(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: CaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    repeat_set_id: str,
    members: Sequence[RepeatabilityMemberIdentity],
) -> PublishedProvisionalRepeatability:
    """Read-only semantic and byte replay of one completed repeatability envelope."""

    _identifier(repeat_set_id, "repeat_set_id")
    metrics, loaded = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        members=members,
    )
    reassembly_id = loaded[0].capture.receipt.reassembly_id
    root = _target(store, session_id, reassembly_id, repeat_set_id)
    if not root.is_dir() or {entry.name for entry in root.iterdir()} != REPEATABILITY_FILE_NAMES:
        raise RepeatabilityPersistenceError(
            "repeatability directory does not contain exactly the required files",
            published=True,
        )
    metrics_digest = _verify_sidecar(root, METRICS_NAME, METRICS_SIDECAR)
    receipt_digest = _verify_sidecar(root, RECEIPT_NAME, RECEIPT_SIDECAR)
    metrics_bytes = (root / METRICS_NAME).read_bytes()
    receipt_bytes = (root / RECEIPT_NAME).read_bytes()
    record_bytes = (root / RECORD_NAME).read_bytes()
    try:
        stored_metrics = ProvisionalRepeatabilityMetrics.model_validate_json(metrics_bytes)
        stored_receipt: ProvisionalRepeatabilityReceipt | ConditionedProvisionalRepeatabilityReceipt
        if isinstance(scenario, LoadedConditionedVirtualCaptureScenario):
            stored_receipt = ConditionedProvisionalRepeatabilityReceipt.model_validate_json(
                receipt_bytes
            )
        else:
            stored_receipt = ProvisionalRepeatabilityReceipt.model_validate_json(receipt_bytes)
        record = RepeatabilityRecord.model_validate_json(record_bytes)
    except ValidationError as exc:
        raise RepeatabilityPersistenceError(str(exc), published=True) from exc
    for label, raw, model in (
        ("metrics", metrics_bytes, stored_metrics),
        ("receipt", receipt_bytes, stored_receipt),
        ("record", record_bytes, record),
    ):
        if raw != canonical_json_bytes(model.model_dump(mode="json")):
            raise RepeatabilityPersistenceError(
                f"repeatability {label} is not canonical", published=True
            )
    event = _validated_event(
        store=store,
        session_id=session_id,
        reassembly_id=reassembly_id,
        repeat_set_id=repeat_set_id,
        record=record,
        record_bytes=record_bytes,
        metrics_sha256=metrics_digest,
        receipt_sha256=receipt_digest,
        member_list_sha256=stored_receipt.normalized_member_list_sha256,
    )
    expected_metrics_bytes = canonical_json_bytes(metrics.model_dump(mode="json"))
    expected_metrics_digest = sha256_bytes(expected_metrics_bytes)
    expected_receipt = _receipt(
        session_id=session_id,
        repeat_set_id=repeat_set_id,
        loaded=loaded,
        metrics_sha256=expected_metrics_digest,
    )
    expected_receipt_bytes = canonical_json_bytes(expected_receipt.model_dump(mode="json"))
    expected_receipt_digest = sha256_bytes(expected_receipt_bytes)
    if stored_metrics != metrics or metrics_bytes != expected_metrics_bytes:
        raise RepeatabilityPersistenceError(
            "repeatability metrics differ from replay", published=True
        )
    if stored_receipt != expected_receipt or receipt_bytes != expected_receipt_bytes:
        raise RepeatabilityPersistenceError(
            "repeatability receipt differs from replay", published=True
        )
    expected_record = RepeatabilityRecord(
        schema_version="1.1.0",
        session_id=session_id,
        reassembly_id=reassembly_id,
        repeat_set_id=repeat_set_id,
        created_at=event.created_at,
        status="complete",
        repeatability_metrics_sha256=expected_metrics_digest,
        repeatability_receipt_sha256=expected_receipt_digest,
        normalized_member_list_sha256=expected_receipt.normalized_member_list_sha256,
        data_origin="synthetic",
        run_mode="development",
        evaluation_status="provisional_repeatability_metrics_only",
        **_state(),
        formal_eligible=False,
        experimental_result=False,
        result_marker="NOT_AN_EXPERIMENTAL_RESULT",
    )
    if record != expected_record:
        raise RepeatabilityPersistenceError(
            "repeatability record differs from replay", published=True
        )
    if (root / METADATA_NAME).read_bytes() != canonical_json_bytes(
        _metadata(expected_receipt, expected_receipt_digest)
    ):
        raise RepeatabilityPersistenceError("repeatability metadata differs", published=True)
    if (
        metrics_digest != expected_metrics_digest
        or receipt_digest != expected_receipt_digest
        or (root / COMPLETE_NAME).read_bytes() != REPEATABILITY_COMPLETE_BYTES
    ):
        raise RepeatabilityPersistenceError(
            "repeatability digest or completion contract differs", published=True
        )
    return PublishedProvisionalRepeatability(
        root,
        stored_metrics,
        stored_receipt,
        metrics_digest,
        receipt_digest,
        event.created_at,
    )
