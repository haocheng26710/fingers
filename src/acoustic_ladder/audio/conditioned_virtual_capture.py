"""Condition-aware synthetic capture publication and deterministic replay."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError

from acoustic_ladder import __version__
from acoustic_ladder.audio.condition_plan import (
    ConditionPlanError,
    LoadedDevelopmentConditionPlan,
    load_development_condition_plan,
)
from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    ConditionedCaptureError,
    ConditionedVirtualCaptureReceipt,
    LoadedConditionedVirtualCaptureScenario,
    PublishedConditionedVirtualCapture,
    load_conditioned_virtual_capture_scenario,
)
from acoustic_ladder.audio.ess import raw_float32_bytes
from acoustic_ladder.audio.excitation_persistence import (
    METADATA_NAME,
    WAV_NAME,
    decode_ieee_float32_wav,
    encode_ieee_float32_wav,
    validate_offline_ess_artifact,
)
from acoustic_ladder.audio.virtual_capture import VirtualCaptureEngine
from acoustic_ladder.audio.virtual_capture_backend import BackendBlockResult
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
from acoustic_ladder.storage.io import safe_identifier, sha256_bytes
from acoustic_ladder.storage.store import ImmutableSessionStore
from acoustic_ladder.synthetic.generator import generate_synthetic_arrays

SAFETY_MARKER: Literal["SYNTHETIC_CONDITION_BOUND_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT"] = (
    "SYNTHETIC_CONDITION_BOUND_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT"
)


class ConditionedVirtualCapturePersistenceError(ConditionedCaptureError):
    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(f"{message}; published={str(published).lower()}")
        self.published = published


class ConditionedFirBackend:
    """Causal block-wise float32 FIR with state carried across block boundaries."""

    def __init__(self, impulse_response: NDArray[np.float32]) -> None:
        if (
            impulse_response.ndim != 1
            or impulse_response.size < 1
            or impulse_response.dtype != np.float32
            or not np.isfinite(impulse_response).all()
        ):
            raise ConditionedCaptureError("conditioned FIR must be finite one-dimensional float32")
        self._ir = impulse_response.astype(np.float64)
        self._history = np.zeros(max(0, impulse_response.size - 1), dtype=np.float64)
        self._prepared = False
        self._armed = False
        self._closed = False

    def prepare(self, *, sample_rate_hz: int, total_frame_count: int) -> None:
        if sample_rate_hz <= 0 or total_frame_count <= 0 or self._prepared:
            raise ConditionedCaptureError("invalid conditioned backend preparation")
        self._prepared = True

    def arm(self) -> None:
        if not self._prepared or self._armed or self._closed:
            raise ConditionedCaptureError("conditioned backend cannot be armed")
        self._armed = True

    def exchange_block(
        self, output_block: NDArray[np.float32], *, frame_count: int, block_index: int
    ) -> BackendBlockResult:
        del block_index
        if not self._armed or self._closed or output_block.shape != (1, frame_count):
            raise ConditionedCaptureError("invalid conditioned output block")
        samples = output_block[0].astype(np.float64)
        combined = np.concatenate((self._history, samples))
        convolved = np.convolve(combined, self._ir, mode="full")
        start = self._history.size
        result = np.ascontiguousarray(convolved[start : start + frame_count], dtype=np.float32)
        if self._history.size:
            self._history = combined[-self._history.size :]
        return BackendBlockResult(result.reshape(1, -1))

    def close(self) -> None:
        self._closed = True

    def abort(self) -> None:
        self._closed = True


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _validate_scenario(
    scenario: LoadedConditionedVirtualCaptureScenario, *, published: bool
) -> None:
    try:
        current = load_conditioned_virtual_capture_scenario(
            scenario.source_path, project_root=scenario.project_root
        )
    except ConditionedCaptureError as exc:
        raise ConditionedVirtualCapturePersistenceError(str(exc), published=published) from exc
    if current != scenario:
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned scenario differs from its loaded provenance", published=published
        )


def _validate_plan(
    plan: LoadedDevelopmentConditionPlan, bundle: LoadedBundle, *, published: bool
) -> None:
    try:
        current = load_development_condition_plan(
            plan.source_path,
            project_root=plan.project_root,
            bundle=bundle,
        )
    except ConditionPlanError as exc:
        raise ConditionedVirtualCapturePersistenceError(str(exc), published=published) from exc
    if current != plan:
        raise ConditionedVirtualCapturePersistenceError(
            "condition plan differs from its loaded provenance", published=published
        )
    protocol = bundle.configs.get("protocol")
    protocol_path = plan.project_root / plan.source_protocol_reference
    try:
        protocol_bytes = protocol_path.read_bytes()
    except OSError as exc:
        raise ConditionedVirtualCapturePersistenceError(
            f"source protocol provenance cannot be reloaded: {exc}", published=published
        ) from exc
    if (
        protocol is None
        or protocol_bytes != protocol.original_bytes
        or sha256_bytes(protocol_bytes) != plan.source_protocol_raw_sha256
        or protocol.snapshot.normalized_sha256 != plan.source_protocol_normalized_sha256
    ):
        raise ConditionedVirtualCapturePersistenceError(
            "source protocol differs from condition-plan provenance", published=published
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


def _synthetic_ir(
    bundle: LoadedBundle,
    plan: LoadedDevelopmentConditionPlan,
    condition_id: str,
    sample_rate_hz: int,
) -> tuple[NDArray[np.float32], dict[str, int], dict[str, float]]:
    loaded = bundle.configs.get("synthetic")
    if loaded is None or not isinstance(loaded.model, SyntheticConfig):
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned capture requires SyntheticConfig", published=False
        )
    config = loaded.model
    if (
        config.sample_rate_hz != sample_rate_hz
        or config.noise_level != 0
        or config.session_drift != 0
        or config.reassembly_drift != 0
        or config.output_channel_count != 1
        or config.input_channel_count != 1
        or config.output_dtype != "float32"
    ):
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned SyntheticConfig must be mono float32 with matching rate "
            "and zero noise/drift",
            published=False,
        )
    binding = plan.binding(condition_id)
    generated = generate_synthetic_arrays(bundle.manifest, config, binding.resolved_node_states)
    impulse = np.ascontiguousarray(generated.synthetic_ir[0, 0], dtype=np.float32)
    delays = generated.metadata["node_delay_samples"]
    weights = generated.metadata["node_weights"]
    if not isinstance(delays, dict) or not isinstance(weights, dict):
        raise ConditionedVirtualCapturePersistenceError(
            "synthetic generator omitted node provenance", published=False
        )
    return (
        impulse,
        {str(key): int(value) for key, value in delays.items()},
        {str(key): float(value) for key, value in weights.items()},
    )


def _artifacts(
    run_id: str,
    payloads: dict[str, bytes],
    receipt: ConditionedVirtualCaptureReceipt,
) -> list[ArtifactRef]:
    artifacts: list[ArtifactRef] = []
    for name, payload in payloads.items():
        is_wav = name.endswith(".wav")
        shape = list(receipt.output_shape) if name == OUTPUT_WAV else None
        if name == INPUT_WAV:
            shape = list(receipt.input_shape)
        artifacts.append(
            ArtifactRef(
                artifact_type="conditioned_virtual_capture_audio"
                if is_wav
                else "conditioned_virtual_capture_provenance",
                path=f"raw/run_{run_id}/{name}",
                sha256=sha256_bytes(payload),
                byte_size=len(payload),
                format="wav_ieee_float32"
                if is_wav
                else ("json" if name.endswith(".json") else "sha256"),
                shape=shape,
                dtype="float32" if is_wav else None,
                created_by="acoustic_ladder.conditioned_virtual_capture",
                immutable=True,
            )
        )
    return artifacts


def _receipt(
    *,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    plan: LoadedDevelopmentConditionPlan,
    condition_id: str,
    ess: object,
    session_id: str,
    reassembly_id: str,
    run_id: str,
    measurement_order: int,
    result: object,
    impulse: NDArray[np.float32],
    delays: dict[str, int],
    weights: dict[str, float],
    output_wav: bytes,
    input_wav: bytes,
) -> ConditionedVirtualCaptureReceipt:
    from acoustic_ladder.audio.excitation_persistence import EssArtifactReceipt
    from acoustic_ladder.audio.virtual_capture_models import VirtualCaptureResult

    if not isinstance(ess, EssArtifactReceipt) or not isinstance(result, VirtualCaptureResult):
        raise TypeError("invalid conditioned receipt inputs")
    protocol = bundle.configs["protocol"].model
    if not isinstance(protocol, ProtocolConfig):
        raise ConditionedVirtualCapturePersistenceError(
            "bundle protocol is invalid", published=False
        )
    binding = plan.binding(condition_id)
    state_bytes = canonical_json_bytes(
        {key: value.model_dump(mode="json") for key, value in binding.resolved_node_states.items()}
    )
    return ConditionedVirtualCaptureReceipt(
        schema_version="1.0.0",
        capture_id=run_id,
        run_id=run_id,
        session_id=session_id,
        reassembly_id=reassembly_id,
        measurement_order=measurement_order,
        data_origin="synthetic",
        run_mode="development",
        backend_id="deterministic_conditioned_virtual_duplex",
        backend_version="1.0.0",
        scenario_reference=scenario.original_relative_path,
        scenario_raw_sha256=scenario.original_sha256,
        scenario_normalized_sha256=scenario.normalized_sha256,
        bundle_content_sha256=bundle.receipt.bundle_content_sha256,
        device_manifest_sha256=bundle.receipt.device_manifest_sha256,
        config_snapshots=bundle.receipt.snapshots,
        protocol_id=protocol.protocol_id,
        protocol_execution_performed=False,
        condition_plan_id=plan.model.condition_plan_id,
        condition_plan_reference=plan.original_relative_path,
        condition_plan_raw_sha256=plan.original_sha256,
        condition_plan_normalized_sha256=plan.normalized_sha256,
        source_protocol_reference=plan.source_protocol_reference,
        source_protocol_raw_sha256=plan.source_protocol_raw_sha256,
        source_protocol_normalized_sha256=plan.source_protocol_normalized_sha256,
        condition_id=binding.condition_id,
        condition_role=binding.condition_role,
        resolved_node_states=binding.resolved_node_states,
        resolved_node_states_sha256=hashlib.sha256(state_bytes).hexdigest(),
        condition_binding_performed=True,
        protocol_condition_binding_performed=True,
        synthetic_response_formula_id=(
            "transparent_round_trip_delay_and_relative_aperture_coupling"
        ),
        synthetic_response_formula_version="1.0.0",
        synthetic_ir_raw_sha256=sha256_bytes(impulse.tobytes(order="C")),
        manifest_node_delay_samples=delays,
        manifest_module_node_weights=weights,
        source_ess_artifact_id=ess.artifact_id,
        source_ess_metadata_sha256=ess.metadata_sha256,
        source_ess_wav_sha256=ess.wav_sha256,
        source_ess_raw_float32_sha256=ess.raw_float32_sha256,
        ess_sample_count=ess.metadata.timing.total_sample_count,
        capture_tail_sample_count=scenario.model.capture_tail_samples,
        capture_sample_count=result.capture_sample_count,
        block_size_frames=scenario.model.block_size_frames,
        planned_block_count=result.planned_block_count,
        actual_block_count=result.actual_block_count,
        last_block_frame_count=result.last_block_frame_count,
        output_shape=result.output_samples.shape,
        input_shape=result.input_samples.shape,
        output_dtype="float32",
        input_dtype="float32",
        output_raw_float32_sha256=sha256_bytes(raw_float32_bytes(result.output_samples)),
        input_raw_float32_sha256=sha256_bytes(raw_float32_bytes(result.input_samples)),
        output_wav_sha256=sha256_bytes(output_wav),
        input_wav_sha256=sha256_bytes(input_wav),
        block_trace=list(result.block_trace),
        state_transition_trace=list(result.transitions),
        fault_counters=result.fault_counters,
        final_state="completed",
        all_finite=True,
        create_only=True,
        immutable=True,
        virtual_duplex_scheduler_exercised=True,
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
        safety_marker=SAFETY_MARKER,
    )


def _execute(
    *,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    plan: LoadedDevelopmentConditionPlan,
    condition_id: str,
    ess_artifact_root: str | Path,
) -> tuple[object, object, NDArray[np.float32], dict[str, int], dict[str, float], int]:
    ess = validate_offline_ess_artifact(ess_artifact_root, bundle.configs["audio"])
    excitation, sample_rate = decode_ieee_float32_wav((ess.artifact_root / WAV_NAME).read_bytes())
    impulse, delays, weights = _synthetic_ir(bundle, plan, condition_id, sample_rate)
    if scenario.model.capture_tail_samples < impulse.size - 1:
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned capture tail does not cover manifest-derived IR", published=False
        )
    backend = ConditionedFirBackend(impulse)
    result = VirtualCaptureEngine().execute(
        excitation,
        sample_rate,
        _schedule(scenario),
        backend=backend,
    )
    return ess, result, impulse, delays, weights, sample_rate


def publish_conditioned_virtual_capture(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    condition_plan: LoadedDevelopmentConditionPlan,
    condition_id: str,
    ess_artifact_root: str | Path,
    session_id: str,
    reassembly_id: str,
    run_id: str,
    measurement_order: int,
    now: Callable[[], datetime],
) -> PublishedConditionedVirtualCapture:
    safe_identifier(run_id, "run_id")
    if isinstance(measurement_order, bool) or not isinstance(measurement_order, int):
        raise ConditionedVirtualCapturePersistenceError(
            "measurement_order must be an integer", published=False
        )
    _validate_scenario(scenario, published=False)
    _validate_plan(condition_plan, bundle, published=False)
    session = store.validate_session(DataOrigin.SYNTHETIC, session_id)
    _validate_stored_bundle(
        store.session_path(DataOrigin.SYNTHETIC, session_id), bundle, published=False
    )
    if reassembly_id not in session.reassembly_ids:
        raise ConditionedVirtualCapturePersistenceError(
            "reassembly is not declared by session", published=False
        )
    ess, result, impulse, delays, weights, sample_rate = _execute(
        bundle=bundle,
        scenario=scenario,
        plan=condition_plan,
        condition_id=condition_id,
        ess_artifact_root=ess_artifact_root,
    )
    from acoustic_ladder.audio.excitation_persistence import EssArtifactReceipt
    from acoustic_ladder.audio.virtual_capture_models import VirtualCaptureResult

    assert isinstance(ess, EssArtifactReceipt)
    assert isinstance(result, VirtualCaptureResult)
    output_wav = encode_ieee_float32_wav(result.output_samples, sample_rate)
    input_wav = encode_ieee_float32_wav(result.input_samples, sample_rate)
    receipt = _receipt(
        bundle=bundle,
        scenario=scenario,
        plan=condition_plan,
        condition_id=condition_id,
        ess=ess,
        session_id=session_id,
        reassembly_id=reassembly_id,
        run_id=run_id,
        measurement_order=measurement_order,
        result=result,
        impulse=impulse,
        delays=delays,
        weights=weights,
        output_wav=output_wav,
        input_wav=input_wav,
    )
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    source_metadata = (ess.artifact_root / METADATA_NAME).read_bytes()
    payloads = {
        EXCITATION_METADATA: source_metadata,
        EXCITATION_METADATA_SIDECAR: _sidecar(sha256_bytes(source_metadata), EXCITATION_METADATA),
        OUTPUT_WAV: output_wav,
        OUTPUT_WAV_SIDECAR: _sidecar(sha256_bytes(output_wav), OUTPUT_WAV),
        INPUT_WAV: input_wav,
        INPUT_WAV_SIDECAR: _sidecar(sha256_bytes(input_wav), INPUT_WAV),
        RECEIPT_JSON: receipt_bytes,
        RECEIPT_SIDECAR: _sidecar(sha256_bytes(receipt_bytes), RECEIPT_JSON),
    }
    timestamp = now()
    binding = condition_plan.binding(condition_id)
    record = MeasurementRunRecord(
        run_id=run_id,
        session_id=session_id,
        reassembly_id=reassembly_id,
        protocol_id=receipt.protocol_id,
        measurement_order=measurement_order,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        formal_eligible=False,
        node_states=binding.resolved_node_states,
        created_at=timestamp,
        started_at=timestamp,
        completed_at=timestamp,
        config_hashes={
            **bundle.receipt.normalized_config_hashes,
            "bundle": bundle.receipt.bundle_content_sha256,
            "condition_plan": condition_plan.normalized_sha256,
        },
        artifacts=_artifacts(run_id, payloads, receipt),
        backend="deterministic_conditioned_virtual_duplex",
        software_version=__version__,
        status="complete",
        failure_reason=None,
        result_marker="NOT_EXPERIMENTAL_RESULT",
        notes="Synthetic protocol-condition binding only; not an experimental result.",
    )
    target = store.session_path(DataOrigin.SYNTHETIC, session_id) / "raw" / f"run_{run_id}"
    try:
        path = store.create_synthetic_run(
            record,
            payloads,
            {
                "condition_binding_performed": True,
                "condition_id": condition_id,
                "data_origin": "synthetic",
                "experimental_result": False,
                "formal_eligible": False,
                "hardware_io_performed": False,
                "receipt_sha256": sha256_bytes(receipt_bytes),
                "safety_marker": SAFETY_MARKER,
            },
        )
    except Exception as exc:
        raise ConditionedVirtualCapturePersistenceError(
            str(exc), published=(target / "RUN_COMPLETE").is_file()
        ) from exc
    return PublishedConditionedVirtualCapture(path, receipt, sha256_bytes(receipt_bytes))


def _verify_payloads(root: Path, name: str, sidecar: str) -> str:
    payload = (root / name).read_bytes()
    digest = sha256_bytes(payload)
    if (root / sidecar).read_bytes() != _sidecar(digest, name):
        raise ConditionedVirtualCapturePersistenceError(
            f"invalid conditioned sidecar for {name}", published=True
        )
    return digest


def validate_conditioned_virtual_capture(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    run_id: str,
) -> PublishedConditionedVirtualCapture:
    _validate_scenario(scenario, published=True)
    store.validate_session(DataOrigin.SYNTHETIC, session_id)
    run = store.validate_run(DataOrigin.SYNTHETIC, session_id, run_id)
    session_root = store.session_path(DataOrigin.SYNTHETIC, session_id)
    root = session_root / "raw" / f"run_{run_id}"
    if {entry.name for entry in root.iterdir()} != CAPTURE_PAYLOAD_NAMES | RUN_ENVELOPE_NAMES:
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned capture file set is not exact", published=True
        )
    _validate_stored_bundle(session_root, bundle, published=True)
    for name, sidecar in (
        (EXCITATION_METADATA, EXCITATION_METADATA_SIDECAR),
        (OUTPUT_WAV, OUTPUT_WAV_SIDECAR),
        (INPUT_WAV, INPUT_WAV_SIDECAR),
        (RECEIPT_JSON, RECEIPT_SIDECAR),
    ):
        _verify_payloads(root, name, sidecar)
    receipt_bytes = (root / RECEIPT_JSON).read_bytes()
    try:
        receipt = ConditionedVirtualCaptureReceipt.model_validate_json(receipt_bytes)
    except ValidationError as exc:
        raise ConditionedVirtualCapturePersistenceError(
            f"conditioned capture receipt is invalid: {exc}", published=True
        ) from exc
    if receipt_bytes != canonical_json_bytes(receipt.model_dump(mode="json")):
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned capture receipt is not canonical", published=True
        )
    plan = load_development_condition_plan(
        scenario.project_root / receipt.condition_plan_reference,
        project_root=scenario.project_root,
        bundle=bundle,
    )
    _validate_plan(plan, bundle, published=True)
    if (
        plan.original_sha256 != receipt.condition_plan_raw_sha256
        or plan.normalized_sha256 != receipt.condition_plan_normalized_sha256
    ):
        raise ConditionedVirtualCapturePersistenceError(
            "condition plan digest differs from conditioned receipt", published=True
        )
    ess, result, impulse, delays, weights, sample_rate = _execute(
        bundle=bundle,
        scenario=scenario,
        plan=plan,
        condition_id=receipt.condition_id,
        ess_artifact_root=ess_artifact_root,
    )
    from acoustic_ladder.audio.excitation_persistence import EssArtifactReceipt
    from acoustic_ladder.audio.virtual_capture_models import VirtualCaptureResult

    assert isinstance(ess, EssArtifactReceipt)
    assert isinstance(result, VirtualCaptureResult)
    output_wav = encode_ieee_float32_wav(result.output_samples, sample_rate)
    input_wav = encode_ieee_float32_wav(result.input_samples, sample_rate)
    expected = _receipt(
        bundle=bundle,
        scenario=scenario,
        plan=plan,
        condition_id=receipt.condition_id,
        ess=ess,
        session_id=session_id,
        reassembly_id=receipt.reassembly_id,
        run_id=run_id,
        measurement_order=receipt.measurement_order,
        result=result,
        impulse=impulse,
        delays=delays,
        weights=weights,
        output_wav=output_wav,
        input_wav=input_wav,
    )
    source_metadata = (ess.artifact_root / METADATA_NAME).read_bytes()
    expected_payloads = {
        EXCITATION_METADATA: source_metadata,
        EXCITATION_METADATA_SIDECAR: _sidecar(sha256_bytes(source_metadata), EXCITATION_METADATA),
        OUTPUT_WAV: output_wav,
        OUTPUT_WAV_SIDECAR: _sidecar(sha256_bytes(output_wav), OUTPUT_WAV),
        INPUT_WAV: input_wav,
        INPUT_WAV_SIDECAR: _sidecar(sha256_bytes(input_wav), INPUT_WAV),
        RECEIPT_JSON: canonical_json_bytes(expected.model_dump(mode="json")),
    }
    expected_payloads[RECEIPT_SIDECAR] = _sidecar(
        sha256_bytes(expected_payloads[RECEIPT_JSON]), RECEIPT_JSON
    )
    if receipt != expected:
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned receipt differs from semantic replay", published=True
        )
    if any((root / name).read_bytes() != payload for name, payload in expected_payloads.items()):
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned capture payload differs from replay", published=True
        )
    expected_run = MeasurementRunRecord(
        run_id=run_id,
        session_id=session_id,
        reassembly_id=receipt.reassembly_id,
        protocol_id=receipt.protocol_id,
        measurement_order=receipt.measurement_order,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        formal_eligible=False,
        node_states=receipt.resolved_node_states,
        created_at=run.created_at,
        started_at=run.created_at,
        completed_at=run.created_at,
        config_hashes={
            **bundle.receipt.normalized_config_hashes,
            "bundle": bundle.receipt.bundle_content_sha256,
            "condition_plan": plan.normalized_sha256,
        },
        artifacts=_artifacts(run_id, expected_payloads, expected),
        backend="deterministic_conditioned_virtual_duplex",
        software_version=__version__,
        status="complete",
        failure_reason=None,
        result_marker="NOT_EXPERIMENTAL_RESULT",
        notes="Synthetic protocol-condition binding only; not an experimental result.",
    )
    if run != expected_run:
        raise ConditionedVirtualCapturePersistenceError(
            "conditioned run record differs from replay", published=True
        )
    return PublishedConditionedVirtualCapture(root, receipt, sha256_bytes(receipt_bytes))


__all__ = [
    "ConditionedVirtualCapturePersistenceError",
    "load_conditioned_virtual_capture_scenario",
    "publish_conditioned_virtual_capture",
    "validate_conditioned_virtual_capture",
]
