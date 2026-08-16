"""Synthetic-only immutable publication and semantic validation for virtual capture."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import ValidationError

from acoustic_ladder import __version__
from acoustic_ladder.audio.ess import EssError, raw_float32_bytes
from acoustic_ladder.audio.excitation_persistence import (
    METADATA_NAME,
    WAV_NAME,
    EssArtifactError,
    decode_ieee_float32_wav,
    encode_ieee_float32_wav,
    validate_offline_ess_artifact,
)
from acoustic_ladder.audio.virtual_capture import VirtualCaptureEngine
from acoustic_ladder.audio.virtual_capture_models import (
    LoadedVirtualCaptureScenario,
    VirtualCaptureReceipt,
    VirtualCaptureResult,
    VirtualScenarioError,
    load_virtual_capture_scenario,
)
from acoustic_ladder.config.bundle import ConfigBundle, LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import ProtocolConfig, manifest_nodes
from acoustic_ladder.domain.models import (
    ArtifactRef,
    DataOrigin,
    LoadingDirection,
    MeasurementRunRecord,
    NodeState,
    RunMode,
)
from acoustic_ladder.storage.io import StorageError, safe_identifier, sha256_bytes
from acoustic_ladder.storage.store import ImmutableSessionStore

EXCITATION_METADATA = "excitation.metadata.json"
EXCITATION_METADATA_SIDECAR = "excitation.metadata.sha256"
OUTPUT_WAV = "output_reference.wav"
OUTPUT_WAV_SIDECAR = "output_reference.wav.sha256"
INPUT_WAV = "simulated_input.wav"
INPUT_WAV_SIDECAR = "simulated_input.wav.sha256"
RECEIPT_JSON = "capture_receipt.json"
RECEIPT_SIDECAR = "capture_receipt.sha256"
CAPTURE_PAYLOAD_NAMES = frozenset(
    {
        EXCITATION_METADATA,
        EXCITATION_METADATA_SIDECAR,
        OUTPUT_WAV,
        OUTPUT_WAV_SIDECAR,
        INPUT_WAV,
        INPUT_WAV_SIDECAR,
        RECEIPT_JSON,
        RECEIPT_SIDECAR,
    }
)
RUN_ENVELOPE_NAMES = frozenset({"synthetic_metadata.json", "run_record.json", "RUN_COMPLETE"})
SAFETY_MARKER: Literal["SYNTHETIC_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT"] = (
    "SYNTHETIC_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT"
)
RUN_NOTES = "Deterministic synthetic virtual capture; no hardware audio I/O."


class VirtualCapturePersistenceError(StorageError):
    """Capture publication/validation error with explicit publication state."""

    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(f"{message}; published={str(published).lower()}")
        self.published = published


@dataclass(frozen=True)
class PublishedVirtualCapture:
    run_path: Path
    receipt: VirtualCaptureReceipt
    receipt_sha256: str


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _synthetic_metadata(receipt_sha256: str) -> dict[str, object]:
    return {
        "capture_receipt_sha256": receipt_sha256,
        "data_origin": "synthetic",
        "hardware_io_performed": False,
        "safety_marker": SAFETY_MARKER,
    }


def _synthetic_metadata_bytes(receipt_sha256: str) -> bytes:
    return canonical_json_bytes(_synthetic_metadata(receipt_sha256))


def _verify_sidecar(root: Path, filename: str, sidecar_name: str) -> str:
    payload = (root / filename).read_bytes()
    digest = sha256_bytes(payload)
    try:
        words = (root / sidecar_name).read_text(encoding="ascii").split()
    except (OSError, UnicodeError) as exc:
        raise VirtualCapturePersistenceError(str(exc), published=True) from exc
    if words != [digest, filename]:
        raise VirtualCapturePersistenceError(
            f"invalid SHA256 sidecar for {filename}", published=True
        )
    return digest


def _validate_loaded_scenario(scenario: LoadedVirtualCaptureScenario, *, published: bool) -> None:
    try:
        current = load_virtual_capture_scenario(
            scenario.source_path, project_root=scenario.project_root
        )
    except VirtualScenarioError as exc:
        raise VirtualCapturePersistenceError(
            f"scenario source provenance cannot be reloaded: {exc}", published=published
        ) from exc
    if current != scenario:
        raise VirtualCapturePersistenceError(
            "scenario source provenance does not match the loaded scenario",
            published=published,
        )
    if hashlib.sha256(scenario.original_bytes).hexdigest() != scenario.original_sha256:
        raise VirtualCapturePersistenceError(
            "scenario raw SHA256 is inconsistent", published=published
        )
    normalized = canonical_json_bytes(scenario.model.model_dump(mode="json"))
    if normalized != scenario.normalized_bytes:
        raise VirtualCapturePersistenceError(
            "scenario normalized bytes are inconsistent", published=published
        )
    if hashlib.sha256(normalized).hexdigest() != scenario.normalized_sha256:
        raise VirtualCapturePersistenceError(
            "scenario normalized SHA256 is inconsistent", published=published
        )


def _blocked_states(bundle: LoadedBundle) -> dict[str, NodeState]:
    return {
        node_id: NodeState(
            node_id=node_id,
            state_id="virtual_capture_BLK",
            module_id="BLK",
            state_type="synthetic_discrete_module",
            discrete_label="BLK",
            continuous_value=None,
            unit=None,
            loading_direction=LoadingDirection.NOT_APPLICABLE,
            proxy_state=False,
            provenance="deterministic virtual capture fixture",
            notes="NOT_EXPERIMENTAL_RESULT",
        )
        for node_id in manifest_nodes(bundle.manifest)
    }


def _receipt(
    *,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_id: str,
    ess_metadata_sha256: str,
    ess_wav_sha256: str,
    ess_raw_sha256: str,
    ess_sample_count: int,
    session_id: str,
    reassembly_id: str,
    run_id: str,
    measurement_order: int,
    result: VirtualCaptureResult,
    output_wav: bytes,
    input_wav: bytes,
) -> VirtualCaptureReceipt:
    protocol = bundle.configs["protocol"].model
    if not isinstance(protocol, ProtocolConfig):
        raise VirtualCapturePersistenceError("bundle protocol model is invalid", published=False)
    return VirtualCaptureReceipt(
        schema_version="1.0.0",
        capture_id=run_id,
        run_id=run_id,
        session_id=session_id,
        reassembly_id=reassembly_id,
        measurement_order=measurement_order,
        data_origin="synthetic",
        run_mode="development",
        backend_id=scenario.model.backend_id,
        backend_version=scenario.model.backend_version,
        scenario_reference=scenario.original_relative_path,
        scenario_raw_sha256=scenario.original_sha256,
        scenario_normalized_sha256=scenario.normalized_sha256,
        bundle_content_sha256=bundle.receipt.bundle_content_sha256,
        device_manifest_sha256=bundle.receipt.device_manifest_sha256,
        config_snapshots=bundle.receipt.snapshots,
        protocol_id=protocol.protocol_id,
        protocol_execution_performed=False,
        source_ess_artifact_id=ess_artifact_id,
        source_ess_metadata_sha256=ess_metadata_sha256,
        source_ess_wav_sha256=ess_wav_sha256,
        source_ess_raw_float32_sha256=ess_raw_sha256,
        ess_sample_count=ess_sample_count,
        capture_tail_sample_count=scenario.model.capture_tail_samples,
        capture_sample_count=result.capture_sample_count,
        planned_output_sample_count=result.capture_sample_count,
        actual_output_sample_count=result.output_samples.shape[1],
        planned_input_sample_count=result.capture_sample_count,
        actual_input_sample_count=result.input_samples.shape[1],
        block_size_frames=scenario.model.block_size_frames,
        planned_block_count=result.planned_block_count,
        actual_block_count=result.actual_block_count,
        last_block_frame_count=result.last_block_frame_count,
        integer_latency_samples=scenario.model.integer_latency_samples,
        linear_gain=scenario.model.linear_gain,
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


def _artifact_refs(
    run_id: str, payloads: dict[str, bytes], receipt: VirtualCaptureReceipt
) -> list[ArtifactRef]:
    result: list[ArtifactRef] = []
    for name, payload in payloads.items():
        is_wav = name.endswith(".wav")
        shape = None
        if name == OUTPUT_WAV:
            shape = list(receipt.output_shape)
        elif name == INPUT_WAV:
            shape = list(receipt.input_shape)
        result.append(
            ArtifactRef(
                artifact_type="virtual_capture_audio" if is_wav else "virtual_capture_provenance",
                path=f"raw/run_{run_id}/{name}",
                sha256=sha256_bytes(payload),
                byte_size=len(payload),
                format="wav_ieee_float32"
                if is_wav
                else ("json" if name.endswith(".json") else "sha256"),
                shape=shape,
                dtype="float32" if is_wav else None,
                created_by="acoustic_ladder.virtual_capture",
                immutable=True,
            )
        )
    return result


def _payloads(
    *,
    receipt: VirtualCaptureReceipt,
    excitation_metadata: bytes,
    output_wav: bytes,
    input_wav: bytes,
) -> tuple[dict[str, bytes], str]:
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    digests = {
        EXCITATION_METADATA: sha256_bytes(excitation_metadata),
        OUTPUT_WAV: sha256_bytes(output_wav),
        INPUT_WAV: sha256_bytes(input_wav),
        RECEIPT_JSON: sha256_bytes(receipt_bytes),
    }
    return (
        {
            EXCITATION_METADATA: excitation_metadata,
            EXCITATION_METADATA_SIDECAR: _sidecar(
                digests[EXCITATION_METADATA], EXCITATION_METADATA
            ),
            OUTPUT_WAV: output_wav,
            OUTPUT_WAV_SIDECAR: _sidecar(digests[OUTPUT_WAV], OUTPUT_WAV),
            INPUT_WAV: input_wav,
            INPUT_WAV_SIDECAR: _sidecar(digests[INPUT_WAV], INPUT_WAV),
            RECEIPT_JSON: receipt_bytes,
            RECEIPT_SIDECAR: _sidecar(digests[RECEIPT_JSON], RECEIPT_JSON),
        },
        digests[RECEIPT_JSON],
    )


def publish_virtual_capture(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    reassembly_id: str,
    run_id: str,
    measurement_order: int,
    now: Callable[[], datetime],
) -> PublishedVirtualCapture:
    """Execute then create-only publish one synthetic virtual capture run."""

    safe_identifier(run_id, "run_id")
    if isinstance(measurement_order, bool) or not isinstance(measurement_order, int):
        raise VirtualCapturePersistenceError(
            "measurement_order must be a non-negative integer", published=False
        )
    if measurement_order < 0:
        raise VirtualCapturePersistenceError(
            "measurement_order must be non-negative", published=False
        )
    _validate_loaded_scenario(scenario, published=False)
    session = store.validate_session(DataOrigin.SYNTHETIC, session_id)
    _validate_stored_bundle(
        store.session_path(DataOrigin.SYNTHETIC, session_id), bundle, published=False
    )
    if reassembly_id not in session.reassembly_ids:
        raise VirtualCapturePersistenceError(
            "reassembly is not declared by session", published=False
        )
    audio = bundle.configs["audio"]
    try:
        ess = validate_offline_ess_artifact(ess_artifact_root, audio)
    except (EssArtifactError, EssError) as exc:
        raise VirtualCapturePersistenceError(str(exc), published=False) from exc
    excitation, sample_rate = decode_ieee_float32_wav((ess.artifact_root / WAV_NAME).read_bytes())
    result = VirtualCaptureEngine().execute(excitation, sample_rate, scenario.model)
    output_wav = encode_ieee_float32_wav(result.output_samples, sample_rate)
    input_wav = encode_ieee_float32_wav(result.input_samples, sample_rate)
    receipt = _receipt(
        bundle=bundle,
        scenario=scenario,
        ess_artifact_id=ess.artifact_id,
        ess_metadata_sha256=ess.metadata_sha256,
        ess_wav_sha256=ess.wav_sha256,
        ess_raw_sha256=ess.raw_float32_sha256,
        ess_sample_count=excitation.shape[1],
        session_id=session_id,
        reassembly_id=reassembly_id,
        run_id=run_id,
        measurement_order=measurement_order,
        result=result,
        output_wav=output_wav,
        input_wav=input_wav,
    )
    excitation_metadata = (ess.artifact_root / METADATA_NAME).read_bytes()
    payloads, receipt_digest = _payloads(
        receipt=receipt,
        excitation_metadata=excitation_metadata,
        output_wav=output_wav,
        input_wav=input_wav,
    )
    timestamp = now()
    protocol = bundle.configs["protocol"].model
    if not isinstance(protocol, ProtocolConfig):
        raise VirtualCapturePersistenceError("bundle protocol model is invalid", published=False)
    record = MeasurementRunRecord(
        run_id=run_id,
        session_id=session_id,
        reassembly_id=reassembly_id,
        protocol_id=protocol.protocol_id,
        measurement_order=measurement_order,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        formal_eligible=False,
        node_states=_blocked_states(bundle),
        created_at=timestamp,
        started_at=timestamp,
        completed_at=timestamp,
        config_hashes={
            **bundle.receipt.normalized_config_hashes,
            "bundle": bundle.receipt.bundle_content_sha256,
        },
        artifacts=_artifact_refs(run_id, payloads, receipt),
        backend="deterministic_virtual_duplex",
        software_version=__version__,
        status="complete",
        failure_reason=None,
        result_marker="NOT_EXPERIMENTAL_RESULT",
        notes=RUN_NOTES,
    )
    run_path = store.session_path(DataOrigin.SYNTHETIC, session_id) / "raw" / f"run_{run_id}"
    try:
        published_path = store.create_synthetic_run(
            record,
            payloads,
            _synthetic_metadata(receipt_digest),
        )
    except Exception as exc:
        published = (run_path / "RUN_COMPLETE").is_file()
        raise VirtualCapturePersistenceError(str(exc), published=published) from exc
    return PublishedVirtualCapture(published_path, receipt, receipt_digest)


def _validate_stored_bundle(session_root: Path, bundle: LoadedBundle, *, published: bool) -> None:
    manifest_path = session_root / "manifest/device_manifest.provisional.json"
    sidecar_path = session_root / "manifest/device_manifest.provisional.sha256"
    try:
        stored_manifest = manifest_path.read_bytes()
    except OSError as exc:
        raise VirtualCapturePersistenceError(
            f"stored manifest cannot be read: {exc}", published=published
        ) from exc
    if stored_manifest != bundle.manifest_bytes:
        raise VirtualCapturePersistenceError(
            "stored manifest differs from loaded bundle", published=published
        )
    try:
        stored_sidecar = sidecar_path.read_bytes()
    except OSError as exc:
        raise VirtualCapturePersistenceError(
            f"stored manifest sidecar cannot be read: {exc}", published=published
        ) from exc
    manifest_digest = sha256_bytes(stored_manifest)
    expected_sidecar = _sidecar(manifest_digest, "device_manifest.provisional.json")
    if (
        stored_sidecar != bundle.manifest_sidecar_bytes
        or stored_sidecar != expected_sidecar
        or manifest_digest != bundle.receipt.device_manifest_sha256
    ):
        raise VirtualCapturePersistenceError(
            "stored manifest sidecar differs from the exact digest contract",
            published=published,
        )
    for kind, loaded in bundle.configs.items():
        suffix = Path(loaded.snapshot.original_relative_path).suffix or ".yaml"
        if (
            session_root / f"protocol/config/{kind}.original{suffix}"
        ).read_bytes() != loaded.original_bytes:
            raise VirtualCapturePersistenceError(
                f"stored {kind} original config differs from loaded bundle", published=published
            )
        if (
            session_root / f"protocol/config/{kind}.normalized.json"
        ).read_bytes() != loaded.normalized_bytes:
            raise VirtualCapturePersistenceError(
                f"stored {kind} normalized config differs from loaded bundle", published=published
            )
    try:
        stored = ConfigBundle.model_validate_json(
            (session_root / "protocol/config_bundle.json").read_bytes()
        )
    except ValidationError as exc:
        raise VirtualCapturePersistenceError(
            "stored bundle receipt is invalid", published=published
        ) from exc
    if (
        stored.bundle_content_sha256 != bundle.receipt.bundle_content_sha256
        or stored.snapshots != bundle.receipt.snapshots
        or stored.normalized_config_hashes != bundle.receipt.normalized_config_hashes
    ):
        raise VirtualCapturePersistenceError(
            "stored bundle provenance differs", published=published
        )


def validate_virtual_capture(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    run_id: str,
) -> PublishedVirtualCapture:
    """Read-only byte and semantic replay validation of a completed capture run."""

    _validate_loaded_scenario(scenario, published=True)
    store.validate_session(DataOrigin.SYNTHETIC, session_id)
    run = store.validate_run(DataOrigin.SYNTHETIC, session_id, run_id)
    session_root = store.session_path(DataOrigin.SYNTHETIC, session_id)
    run_path = session_root / "raw" / f"run_{run_id}"
    if {entry.name for entry in run_path.iterdir()} != CAPTURE_PAYLOAD_NAMES | RUN_ENVELOPE_NAMES:
        raise VirtualCapturePersistenceError(
            "capture run does not contain exactly the required files", published=True
        )
    _validate_stored_bundle(session_root, bundle, published=True)
    metadata_digest = _verify_sidecar(run_path, EXCITATION_METADATA, EXCITATION_METADATA_SIDECAR)
    output_digest = _verify_sidecar(run_path, OUTPUT_WAV, OUTPUT_WAV_SIDECAR)
    input_digest = _verify_sidecar(run_path, INPUT_WAV, INPUT_WAV_SIDECAR)
    receipt_digest = _verify_sidecar(run_path, RECEIPT_JSON, RECEIPT_SIDECAR)
    if (run_path / "synthetic_metadata.json").read_bytes() != _synthetic_metadata_bytes(
        receipt_digest
    ):
        raise VirtualCapturePersistenceError(
            "synthetic metadata envelope differs from the canonical contract",
            published=True,
        )
    receipt_bytes = (run_path / RECEIPT_JSON).read_bytes()
    try:
        receipt = VirtualCaptureReceipt.model_validate_json(receipt_bytes)
    except ValidationError as exc:
        raise VirtualCapturePersistenceError("capture receipt is invalid", published=True) from exc
    if receipt_bytes != canonical_json_bytes(receipt.model_dump(mode="json")):
        raise VirtualCapturePersistenceError(
            "capture receipt is not canonical JSON", published=True
        )
    ess = validate_offline_ess_artifact(ess_artifact_root, bundle.configs["audio"])
    source_metadata = (ess.artifact_root / METADATA_NAME).read_bytes()
    if (run_path / EXCITATION_METADATA).read_bytes() != source_metadata:
        raise VirtualCapturePersistenceError(
            "copied ESS metadata differs from source", published=True
        )
    excitation, sample_rate = decode_ieee_float32_wav((ess.artifact_root / WAV_NAME).read_bytes())
    replayed = VirtualCaptureEngine().execute(excitation, sample_rate, scenario.model)
    expected_output_wav = encode_ieee_float32_wav(replayed.output_samples, sample_rate)
    expected_input_wav = encode_ieee_float32_wav(replayed.input_samples, sample_rate)
    output_samples, output_rate = decode_ieee_float32_wav((run_path / OUTPUT_WAV).read_bytes())
    input_samples, input_rate = decode_ieee_float32_wav((run_path / INPUT_WAV).read_bytes())
    if output_rate != sample_rate or input_rate != sample_rate:
        raise VirtualCapturePersistenceError("capture WAV sample rate mismatch", published=True)
    if not np.array_equal(output_samples, replayed.output_samples):
        raise VirtualCapturePersistenceError(
            "output samples differ from semantic replay", published=True
        )
    if not np.array_equal(input_samples, replayed.input_samples):
        raise VirtualCapturePersistenceError(
            "input samples differ from semantic replay", published=True
        )
    if (run_path / OUTPUT_WAV).read_bytes() != expected_output_wav:
        raise VirtualCapturePersistenceError("output WAV bytes are not canonical", published=True)
    if (run_path / INPUT_WAV).read_bytes() != expected_input_wav:
        raise VirtualCapturePersistenceError("input WAV bytes are not canonical", published=True)
    expected_receipt = _receipt(
        bundle=bundle,
        scenario=scenario,
        ess_artifact_id=ess.artifact_id,
        ess_metadata_sha256=ess.metadata_sha256,
        ess_wav_sha256=ess.wav_sha256,
        ess_raw_sha256=ess.raw_float32_sha256,
        ess_sample_count=excitation.shape[1],
        session_id=session_id,
        reassembly_id=receipt.reassembly_id,
        run_id=run_id,
        measurement_order=receipt.measurement_order,
        result=replayed,
        output_wav=expected_output_wav,
        input_wav=expected_input_wav,
    )
    if receipt != expected_receipt:
        raise VirtualCapturePersistenceError(
            "capture receipt differs from deterministic semantic replay", published=True
        )
    expected_payloads, expected_receipt_digest = _payloads(
        receipt=expected_receipt,
        excitation_metadata=source_metadata,
        output_wav=expected_output_wav,
        input_wav=expected_input_wav,
    )
    expected_artifacts = _artifact_refs(run_id, expected_payloads, expected_receipt)
    if (
        metadata_digest != ess.metadata_sha256
        or output_digest != receipt.output_wav_sha256
        or input_digest != receipt.input_wav_sha256
        or receipt_digest != expected_receipt_digest
    ):
        raise VirtualCapturePersistenceError("capture digest chain differs", published=True)
    if run.started_at != run.created_at or run.completed_at != run.created_at:
        raise VirtualCapturePersistenceError(
            "run record envelope violates the single capture timestamp contract",
            published=True,
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
        node_states=_blocked_states(bundle),
        created_at=run.created_at,
        started_at=run.created_at,
        completed_at=run.created_at,
        config_hashes={
            **bundle.receipt.normalized_config_hashes,
            "bundle": bundle.receipt.bundle_content_sha256,
        },
        artifacts=expected_artifacts,
        backend="deterministic_virtual_duplex",
        software_version=__version__,
        status="complete",
        failure_reason=None,
        result_marker="NOT_EXPERIMENTAL_RESULT",
        notes=RUN_NOTES,
    )
    if run != expected_run:
        raise VirtualCapturePersistenceError(
            "run record envelope differs from the canonical capture contract",
            published=True,
        )
    return PublishedVirtualCapture(run_path, receipt, receipt_digest)
