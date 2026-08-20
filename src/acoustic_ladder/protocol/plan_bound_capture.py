"""Plan-bound deterministic synthetic capture; never a hardware or formal path."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from acoustic_ladder import __version__
from acoustic_ladder.audio.conditioned_virtual_capture import ConditionedFirBackend
from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    LoadedConditionedVirtualCaptureScenario,
    load_conditioned_virtual_capture_scenario,
)
from acoustic_ladder.audio.ess import raw_float32_bytes
from acoustic_ladder.audio.excitation_persistence import (
    METADATA_NAME,
    WAV_NAME,
    EssArtifactReceipt,
    decode_ieee_float32_wav,
    encode_ieee_float32_wav,
    validate_offline_ess_artifact,
)
from acoustic_ladder.audio.virtual_capture import VirtualCaptureEngine
from acoustic_ladder.audio.virtual_capture_models import FaultMode, VirtualCaptureScenario
from acoustic_ladder.audio.virtual_capture_persistence import (
    CAPTURE_PAYLOAD_NAMES,
    EXCITATION_METADATA,
    EXCITATION_METADATA_SIDECAR,
    INPUT_WAV,
    INPUT_WAV_SIDECAR,
    OUTPUT_WAV,
    OUTPUT_WAV_SIDECAR,
    RECEIPT_JSON,
    RECEIPT_SIDECAR,
    RUN_ENVELOPE_NAMES,
    _validate_stored_bundle,
)
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import ProtocolConfig, SyntheticConfig
from acoustic_ladder.domain.models import ArtifactRef, DataOrigin, MeasurementRunRecord, RunMode
from acoustic_ladder.protocol.synthetic_execution_models import (
    EXECUTION_SAFETY_MARKER,
    PlanBoundSyntheticCaptureReceipt,
    SyntheticProtocolWorkOrder,
)
from acoustic_ladder.storage.io import StorageError, sha256_bytes
from acoustic_ladder.storage.store import ImmutableSessionStore
from acoustic_ladder.synthetic.generator import generate_synthetic_arrays


class PlanBoundSyntheticCaptureError(StorageError):
    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(message)
        self.published = published


@dataclass(frozen=True)
class PublishedPlanBoundSyntheticCapture:
    run_path: Path
    receipt: PlanBoundSyntheticCaptureReceipt
    receipt_sha256: str
    run_record_sha256: str
    ordered_artifact_sha256: str


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _validate_scenario(scenario: LoadedConditionedVirtualCaptureScenario) -> None:
    current = load_conditioned_virtual_capture_scenario(
        scenario.source_path, project_root=scenario.project_root
    )
    if current != scenario:
        raise PlanBoundSyntheticCaptureError(
            "synthetic scenario differs from its loaded provenance", published=False
        )


def _schedule(scenario: LoadedConditionedVirtualCaptureScenario) -> VirtualCaptureScenario:
    return VirtualCaptureScenario(
        schema_version="1.0.0",
        scenario_id=scenario.model.scenario_id,
        usage_scope="development_fixture",
        backend_id="deterministic_virtual_duplex",
        backend_version="1.0.0",
        block_size_frames=scenario.model.block_size_frames,
        integer_latency_samples=0,
        capture_tail_samples=scenario.model.capture_tail_samples,
        linear_gain=1.0,
        fault_mode=FaultMode.NONE,
        fault_block_index=None,
        hardware_io_authorized=False,
        formal_eligible=False,
        experimental_result=False,
    )


def _execute(
    *,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    work_order: SyntheticProtocolWorkOrder,
) -> tuple[EssArtifactReceipt, object, np.ndarray, dict[str, int], dict[str, float], int]:
    _validate_scenario(scenario)
    loaded = bundle.configs.get("synthetic")
    if loaded is None or not isinstance(loaded.model, SyntheticConfig):
        raise PlanBoundSyntheticCaptureError("SyntheticConfig is required", published=False)
    config = loaded.model
    ess = validate_offline_ess_artifact(ess_artifact_root, bundle.configs["audio"])
    excitation, sample_rate = decode_ieee_float32_wav((ess.artifact_root / WAV_NAME).read_bytes())
    if (
        config.sample_rate_hz != sample_rate
        or config.output_channel_count != 1
        or config.input_channel_count != 1
        or config.output_dtype != "float32"
    ):
        raise PlanBoundSyntheticCaptureError(
            "plan-bound SyntheticConfig must be mono float32 at the ESS sample rate",
            published=False,
        )
    generated = generate_synthetic_arrays(
        bundle.manifest,
        config,
        work_order.node_states,
        session_index=work_order.session_index,
        reassembly_index=work_order.reassembly_index,
    )
    impulse = np.ascontiguousarray(generated.synthetic_ir[0, 0], dtype=np.float32)
    if scenario.model.capture_tail_samples < impulse.size - 1:
        raise PlanBoundSyntheticCaptureError(
            "synthetic capture tail does not cover manifest-derived IR", published=False
        )
    delays = generated.metadata.get("node_delay_samples")
    weights = generated.metadata.get("node_weights")
    if not isinstance(delays, dict) or not isinstance(weights, dict):
        raise PlanBoundSyntheticCaptureError(
            "synthetic generator omitted node provenance", published=False
        )
    result = VirtualCaptureEngine().execute(
        excitation,
        sample_rate,
        _schedule(scenario),
        backend=ConditionedFirBackend(impulse),
    )
    return (
        ess,
        result,
        impulse,
        {str(key): int(value) for key, value in delays.items()},
        {str(key): float(value) for key, value in weights.items()},
        sample_rate,
    )


def _receipt(
    *,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    work_order: SyntheticProtocolWorkOrder,
    ess: EssArtifactReceipt,
    result: object,
    impulse: np.ndarray,
    delays: dict[str, int],
    weights: dict[str, float],
    output_wav: bytes,
    input_wav: bytes,
) -> PlanBoundSyntheticCaptureReceipt:
    from acoustic_ladder.audio.virtual_capture_models import VirtualCaptureResult

    if not isinstance(result, VirtualCaptureResult):
        raise TypeError("invalid virtual capture result")
    protocol = bundle.configs["protocol"].model
    if not isinstance(protocol, ProtocolConfig):
        raise PlanBoundSyntheticCaptureError("ProtocolConfig is required", published=False)
    synthetic_snapshot = bundle.receipt.snapshots["synthetic_config"]
    return PlanBoundSyntheticCaptureReceipt.model_validate(
        {
            "schema_version": "1.0.0",
            "execution_id": work_order.execution_id,
            "plan_id": work_order.plan_id,
            "compiled_plan_sha256": work_order.compiled_plan_sha256,
            "protocol_plan_receipt_sha256": work_order.protocol_plan_receipt_sha256,
            "schedule_sha256": work_order.schedule_sha256,
            "work_order_sha256": work_order.work_order_sha256,
            "experiment_stage": work_order.experiment_stage,
            "global_planned_ordinal": work_order.global_planned_ordinal,
            "session_index": work_order.session_index,
            "reassembly_index": work_order.reassembly_index,
            "condition_block_order": work_order.condition_block_order,
            "continuous_repeat_index": work_order.continuous_repeat_index,
            "condition_id": work_order.condition_id,
            "condition_role": work_order.condition_role,
            "condition_node_state_sha256": work_order.condition_node_state_sha256,
            "node_states": work_order.node_states,
            "selected_nodes": work_order.selected_nodes,
            "selected_modules": work_order.selected_modules,
            "session_id": work_order.session_id,
            "reassembly_id": work_order.reassembly_id,
            "run_id": work_order.run_id,
            "capture_id": work_order.capture_id,
            "data_origin": "synthetic",
            "run_mode": "development",
            "backend_id": "deterministic_plan_bound_virtual_duplex",
            "backend_version": "1.0.0",
            "scenario_reference": scenario.original_relative_path,
            "scenario_raw_sha256": scenario.original_sha256,
            "scenario_normalized_sha256": scenario.normalized_sha256,
            "bundle_content_sha256": bundle.receipt.bundle_content_sha256,
            "device_manifest_sha256": bundle.receipt.device_manifest_sha256,
            "protocol_id": protocol.protocol_id,
            "protocol_raw_sha256": bundle.receipt.snapshots["protocol_config"].original_sha256,
            "synthetic_config_raw_sha256": synthetic_snapshot.original_sha256,
            "synthetic_config_normalized_sha256": synthetic_snapshot.normalized_sha256,
            "synthetic_response_formula_id": (
                "transparent_round_trip_delay_and_relative_aperture_coupling"
            ),
            "synthetic_response_formula_version": "1.0.0",
            "synthetic_ir_raw_sha256": sha256_bytes(impulse.tobytes(order="C")),
            "manifest_node_delay_samples": delays,
            "manifest_module_node_weights": weights,
            "source_ess_artifact_id": ess.artifact_id,
            "source_ess_metadata_sha256": ess.metadata_sha256,
            "source_ess_wav_sha256": ess.wav_sha256,
            "source_ess_raw_float32_sha256": ess.raw_float32_sha256,
            "ess_sample_count": ess.metadata.timing.total_sample_count,
            "capture_tail_sample_count": scenario.model.capture_tail_samples,
            "capture_sample_count": result.capture_sample_count,
            "block_size_frames": scenario.model.block_size_frames,
            "planned_block_count": result.planned_block_count,
            "actual_block_count": result.actual_block_count,
            "last_block_frame_count": result.last_block_frame_count,
            "output_shape": result.output_samples.shape,
            "input_shape": result.input_samples.shape,
            "output_dtype": "float32",
            "input_dtype": "float32",
            "output_raw_float32_sha256": sha256_bytes(raw_float32_bytes(result.output_samples)),
            "input_raw_float32_sha256": sha256_bytes(raw_float32_bytes(result.input_samples)),
            "output_wav_sha256": sha256_bytes(output_wav),
            "input_wav_sha256": sha256_bytes(input_wav),
            "capture_receipt_sha256": None,
            "block_trace": list(result.block_trace),
            "state_transition_trace": list(result.transitions),
            "fault_counters": result.fault_counters,
            "final_state": "completed",
            "all_finite": True,
            "create_only": True,
            "immutable": True,
            "synthetic_capture_performed": True,
            "virtual_duplex_scheduler_exercised": True,
            "development_synthetic_run": True,
            "physical_operator_confirmation_performed": False,
            "operator_confirmation_status": "pending",
            "formal_protocol_execution_performed": False,
            "protocol_execution_performed": False,
            "measurement_performed": False,
            "hardware_io_performed": False,
            "playback_performed": False,
            "recording_performed": False,
            "hardware_ready": False,
            "full_duplex_verified": False,
            "shared_clock_verified": False,
            "channel_mapping_verified": False,
            "calibration_file_verified": False,
            "calibration_applied": False,
            "absolute_spl_calibrated": False,
            "electrical_loopback_available": False,
            "formal_eligible": False,
            "experimental_result": False,
            "safety_marker": EXECUTION_SAFETY_MARKER,
        }
    )


def _payloads(
    *,
    receipt: PlanBoundSyntheticCaptureReceipt,
    excitation_metadata: bytes,
    output_wav: bytes,
    input_wav: bytes,
) -> tuple[dict[str, bytes], str]:
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    values = {
        EXCITATION_METADATA: excitation_metadata,
        OUTPUT_WAV: output_wav,
        INPUT_WAV: input_wav,
        RECEIPT_JSON: receipt_bytes,
    }
    payloads = dict(values)
    for filename, sidecar in (
        (EXCITATION_METADATA, EXCITATION_METADATA_SIDECAR),
        (OUTPUT_WAV, OUTPUT_WAV_SIDECAR),
        (INPUT_WAV, INPUT_WAV_SIDECAR),
        (RECEIPT_JSON, RECEIPT_SIDECAR),
    ):
        payloads[sidecar] = _sidecar(sha256_bytes(values[filename]), filename)
    return payloads, sha256_bytes(receipt_bytes)


def _artifacts(
    run_id: str, payloads: dict[str, bytes], receipt: PlanBoundSyntheticCaptureReceipt
) -> list[ArtifactRef]:
    result: list[ArtifactRef] = []
    for name, payload in payloads.items():
        is_wav = name.endswith(".wav")
        shape = list(receipt.output_shape) if name == OUTPUT_WAV else None
        if name == INPUT_WAV:
            shape = list(receipt.input_shape)
        result.append(
            ArtifactRef(
                artifact_type=(
                    "plan_bound_synthetic_capture_audio"
                    if is_wav
                    else "plan_bound_synthetic_capture_provenance"
                ),
                path=f"raw/run_{run_id}/{name}",
                sha256=sha256_bytes(payload),
                byte_size=len(payload),
                format=(
                    "wav_ieee_float32"
                    if is_wav
                    else ("json" if name.endswith(".json") else "sha256")
                ),
                shape=shape,
                dtype="float32" if is_wav else None,
                created_by="acoustic_ladder.plan_bound_capture",
                immutable=True,
            )
        )
    return result


def _record(
    *,
    bundle: LoadedBundle,
    work_order: SyntheticProtocolWorkOrder,
    receipt: PlanBoundSyntheticCaptureReceipt,
    payloads: dict[str, bytes],
    timestamp: datetime,
) -> MeasurementRunRecord:
    return MeasurementRunRecord(
        run_id=work_order.run_id,
        session_id=work_order.session_id,
        reassembly_id=work_order.reassembly_id,
        protocol_id=receipt.protocol_id,
        measurement_order=work_order.session_local_measurement_order,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        formal_eligible=False,
        node_states=work_order.node_states,
        created_at=timestamp,
        started_at=timestamp,
        completed_at=timestamp,
        config_hashes={
            **bundle.receipt.normalized_config_hashes,
            "bundle": bundle.receipt.bundle_content_sha256,
            "compiled_plan": work_order.compiled_plan_sha256,
            "protocol_plan_receipt": work_order.protocol_plan_receipt_sha256,
            "schedule": work_order.schedule_sha256,
            "work_order": work_order.work_order_sha256,
            "scenario": receipt.scenario_normalized_sha256,
        },
        artifacts=_artifacts(work_order.run_id, payloads, receipt),
        backend="deterministic_plan_bound_virtual_duplex",
        software_version=__version__,
        status="complete",
        failure_reason=None,
        result_marker="NOT_EXPERIMENTAL_RESULT",
        notes="Development synthetic plan-bound capture; not an experimental result.",
    )


def _publication_result(
    path: Path, receipt: PlanBoundSyntheticCaptureReceipt, record: MeasurementRunRecord
) -> PublishedPlanBoundSyntheticCapture:
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    record_bytes = canonical_json_bytes(record.model_dump(mode="json"))
    artifact_digest = hashlib.sha256(
        canonical_json_bytes([item.sha256 for item in record.artifacts])
    ).hexdigest()
    return PublishedPlanBoundSyntheticCapture(
        path,
        receipt,
        sha256_bytes(receipt_bytes),
        sha256_bytes(record_bytes),
        artifact_digest,
    )


def publish_plan_bound_synthetic_capture(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    work_order: SyntheticProtocolWorkOrder,
    now: Callable[[], datetime],
) -> PublishedPlanBoundSyntheticCapture:
    session = store.validate_session(DataOrigin.SYNTHETIC, work_order.session_id)
    if work_order.reassembly_id not in session.reassembly_ids:
        raise PlanBoundSyntheticCaptureError(
            "work-order reassembly is not declared by session", published=False
        )
    _validate_stored_bundle(
        store.session_path(DataOrigin.SYNTHETIC, work_order.session_id),
        bundle,
        published=False,
    )
    ess, result, impulse, delays, weights, sample_rate = _execute(
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        work_order=work_order,
    )
    from acoustic_ladder.audio.virtual_capture_models import VirtualCaptureResult

    if not isinstance(result, VirtualCaptureResult):
        raise TypeError("invalid virtual capture result")
    output_wav = encode_ieee_float32_wav(result.output_samples, sample_rate)
    input_wav = encode_ieee_float32_wav(result.input_samples, sample_rate)
    receipt = _receipt(
        bundle=bundle,
        scenario=scenario,
        work_order=work_order,
        ess=ess,
        result=result,
        impulse=impulse,
        delays=delays,
        weights=weights,
        output_wav=output_wav,
        input_wav=input_wav,
    )
    payloads, receipt_digest = _payloads(
        receipt=receipt,
        excitation_metadata=(ess.artifact_root / METADATA_NAME).read_bytes(),
        output_wav=output_wav,
        input_wav=input_wav,
    )
    record = _record(
        bundle=bundle,
        work_order=work_order,
        receipt=receipt,
        payloads=payloads,
        timestamp=now(),
    )
    target = (
        store.session_path(DataOrigin.SYNTHETIC, work_order.session_id)
        / "raw"
        / f"run_{work_order.run_id}"
    )
    try:
        path = store.create_synthetic_run(
            record,
            payloads,
            {
                "capture_receipt_sha256": receipt_digest,
                "data_origin": "synthetic",
                "execution_id": work_order.execution_id,
                "formal_protocol_execution_performed": False,
                "hardware_io_performed": False,
                "work_order_sha256": work_order.work_order_sha256,
                "safety_marker": EXECUTION_SAFETY_MARKER,
            },
        )
    except Exception as exc:
        raise PlanBoundSyntheticCaptureError(
            str(exc), published=(target / "RUN_COMPLETE").is_file()
        ) from exc
    return _publication_result(path, receipt, record)


def validate_plan_bound_synthetic_capture(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    work_order: SyntheticProtocolWorkOrder,
) -> PublishedPlanBoundSyntheticCapture:
    run = store.validate_run(DataOrigin.SYNTHETIC, work_order.session_id, work_order.run_id)
    root = (
        store.session_path(DataOrigin.SYNTHETIC, work_order.session_id)
        / "raw"
        / f"run_{work_order.run_id}"
    )
    if {entry.name for entry in root.iterdir()} != CAPTURE_PAYLOAD_NAMES | RUN_ENVELOPE_NAMES:
        raise PlanBoundSyntheticCaptureError("plan-bound run file set is not exact", published=True)
    for filename, sidecar in (
        (EXCITATION_METADATA, EXCITATION_METADATA_SIDECAR),
        (OUTPUT_WAV, OUTPUT_WAV_SIDECAR),
        (INPUT_WAV, INPUT_WAV_SIDECAR),
        (RECEIPT_JSON, RECEIPT_SIDECAR),
    ):
        payload = (root / filename).read_bytes()
        if (root / sidecar).read_bytes() != _sidecar(sha256_bytes(payload), filename):
            raise PlanBoundSyntheticCaptureError(
                f"invalid plan-bound sidecar for {filename}", published=True
            )
    try:
        stored_receipt = PlanBoundSyntheticCaptureReceipt.model_validate_json(
            (root / RECEIPT_JSON).read_bytes()
        )
    except ValidationError as exc:
        raise PlanBoundSyntheticCaptureError(str(exc), published=True) from exc
    ess, result, impulse, delays, weights, sample_rate = _execute(
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        work_order=work_order,
    )
    from acoustic_ladder.audio.virtual_capture_models import VirtualCaptureResult

    if not isinstance(result, VirtualCaptureResult):
        raise TypeError("invalid virtual capture result")
    output_wav = encode_ieee_float32_wav(result.output_samples, sample_rate)
    input_wav = encode_ieee_float32_wav(result.input_samples, sample_rate)
    expected_receipt = _receipt(
        bundle=bundle,
        scenario=scenario,
        work_order=work_order,
        ess=ess,
        result=result,
        impulse=impulse,
        delays=delays,
        weights=weights,
        output_wav=output_wav,
        input_wav=input_wav,
    )
    expected_payloads, _ = _payloads(
        receipt=expected_receipt,
        excitation_metadata=(ess.artifact_root / METADATA_NAME).read_bytes(),
        output_wav=output_wav,
        input_wav=input_wav,
    )
    if stored_receipt != expected_receipt or any(
        (root / name).read_bytes() != payload for name, payload in expected_payloads.items()
    ):
        raise PlanBoundSyntheticCaptureError(
            "plan-bound capture differs from semantic replay", published=True
        )
    expected_record = _record(
        bundle=bundle,
        work_order=work_order,
        receipt=expected_receipt,
        payloads=expected_payloads,
        timestamp=run.created_at,
    )
    if run != expected_record:
        raise PlanBoundSyntheticCaptureError(
            "plan-bound run record differs from replay", published=True
        )
    return _publication_result(root, expected_receipt, expected_record)


def validate_plan_bound_synthetic_capture_binding(
    *,
    store: ImmutableSessionStore,
    work_order: SyntheticProtocolWorkOrder,
) -> PublishedPlanBoundSyntheticCapture:
    """Validate immutable run/artifact hashes and exact plan identity without DSP replay."""

    run = store.validate_run(DataOrigin.SYNTHETIC, work_order.session_id, work_order.run_id)
    root = (
        store.session_path(DataOrigin.SYNTHETIC, work_order.session_id)
        / "raw"
        / f"run_{work_order.run_id}"
    )
    if {entry.name for entry in root.iterdir()} != CAPTURE_PAYLOAD_NAMES | RUN_ENVELOPE_NAMES:
        raise PlanBoundSyntheticCaptureError("plan-bound run file set is not exact", published=True)
    for filename, sidecar in (
        (EXCITATION_METADATA, EXCITATION_METADATA_SIDECAR),
        (OUTPUT_WAV, OUTPUT_WAV_SIDECAR),
        (INPUT_WAV, INPUT_WAV_SIDECAR),
        (RECEIPT_JSON, RECEIPT_SIDECAR),
    ):
        payload = (root / filename).read_bytes()
        if (root / sidecar).read_bytes() != _sidecar(sha256_bytes(payload), filename):
            raise PlanBoundSyntheticCaptureError(
                f"invalid plan-bound sidecar for {filename}", published=True
            )
    try:
        receipt_bytes = (root / RECEIPT_JSON).read_bytes()
        receipt = PlanBoundSyntheticCaptureReceipt.model_validate_json(receipt_bytes)
    except ValidationError as exc:
        raise PlanBoundSyntheticCaptureError(str(exc), published=True) from exc
    if receipt_bytes != canonical_json_bytes(receipt.model_dump(mode="json")):
        raise PlanBoundSyntheticCaptureError("capture receipt is not canonical", published=True)
    expected_identity = {
        "execution_id": work_order.execution_id,
        "plan_id": work_order.plan_id,
        "compiled_plan_sha256": work_order.compiled_plan_sha256,
        "protocol_plan_receipt_sha256": work_order.protocol_plan_receipt_sha256,
        "schedule_sha256": work_order.schedule_sha256,
        "work_order_sha256": work_order.work_order_sha256,
        "experiment_stage": work_order.experiment_stage,
        "global_planned_ordinal": work_order.global_planned_ordinal,
        "session_index": work_order.session_index,
        "reassembly_index": work_order.reassembly_index,
        "condition_block_order": work_order.condition_block_order,
        "continuous_repeat_index": work_order.continuous_repeat_index,
        "condition_id": work_order.condition_id,
        "condition_role": work_order.condition_role,
        "condition_node_state_sha256": work_order.condition_node_state_sha256,
        "node_states": work_order.node_states,
        "selected_nodes": work_order.selected_nodes,
        "selected_modules": work_order.selected_modules,
        "session_id": work_order.session_id,
        "reassembly_id": work_order.reassembly_id,
        "run_id": work_order.run_id,
        "capture_id": work_order.capture_id,
    }
    for field, expected in expected_identity.items():
        if getattr(receipt, field) != expected:
            raise PlanBoundSyntheticCaptureError(
                f"capture identity differs from work order: {field}", published=True
            )
    if (
        run.node_states != work_order.node_states
        or run.session_id != work_order.session_id
        or run.reassembly_id != work_order.reassembly_id
        or run.measurement_order != work_order.session_local_measurement_order
        or run.config_hashes.get("work_order") != work_order.work_order_sha256
        or run.config_hashes.get("compiled_plan") != work_order.compiled_plan_sha256
    ):
        raise PlanBoundSyntheticCaptureError(
            "run record differs from plan-derived work order", published=True
        )
    return _publication_result(root, receipt, run)


__all__ = [
    "PlanBoundSyntheticCaptureError",
    "PublishedPlanBoundSyntheticCapture",
    "publish_plan_bound_synthetic_capture",
    "validate_plan_bound_synthetic_capture",
    "validate_plan_bound_synthetic_capture_binding",
]
