"""Fake-only capture, calibrated processing, and immutable demo evidence."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from acoustic_ladder.audio.ess import GeneratedEss, generate_ess, spec_from_audio_config
from acoustic_ladder.audio.microphone_calibration import (
    MicrophoneCalibration,
    MicrophoneCalibrationError,
    PilotBundleProcessingResult,
    PilotBundleProcessingSpec,
    load_dayton_calibration,
    process_pilot_capture_bundle,
)
from acoustic_ladder.audio.pilot_capture import (
    CancellationToken,
    PilotCaptureEngine,
    PilotCaptureRequest,
)
from acoustic_ladder.audio.pilot_capture_backends import FakeFullDuplexBackend
from acoustic_ladder.config.bundle import canonical_json_bytes, load_config
from acoustic_ladder.config.models import AudioConfig
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes, sha256_bytes
from acoustic_ladder.storage.npz import deterministic_npz_bytes, load_deterministic_npz
from acoustic_ladder.ui.plans import DemoCondition

CALIBRATION_SHA256 = "421070ec6d41c1b92cb69f0f5e4e290f9644847d92d52590994a80ea9e17a11e"
CALIBRATION_RELATIVE_PATH = Path("calibration/microphones/dayton_imm6c/CMM29939.txt")
PROCESSING_FILE_NAMES = frozenset(
    {
        "processing_arrays.npz",
        "processing_arrays.npz.sha256",
        "processing_receipt.json",
        "processing_receipt.sha256",
        "processing_metadata.json",
        "processing_record.json",
        "PROCESSING_COMPLETE",
    }
)


class SimulatedWorkflowError(RuntimeError):
    """A repeat failure carrying its stage and retry-safe publication facts."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        phase: str,
        run_id: str,
        bundle_path: Path,
        processing_published: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.run_id = run_id
        self.bundle_path = bundle_path
        self.capture_published = bundle_path.is_dir()
        self.processing_published = processing_published


@dataclass(frozen=True)
class SimulatedRepeatResult:
    run_id: str
    bundle_path: Path
    processing_directory: Path
    processing_receipt_path: Path
    capture_status: str = "completed"
    bundle_status: str = "passed"
    processing_status: str = "passed"
    calibration_status: str = "applied"
    calibration_band_valid: bool = True
    structural_status: str = "passed"


@dataclass(frozen=True)
class _WorkflowResources:
    generated: GeneratedEss
    processing_spec: PilotBundleProcessingSpec


BackendFactory = Callable[[int, DemoCondition], FakeFullDuplexBackend]


def _json_object(path: Path) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return value


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _bundle_hashes(bundle: Path) -> dict[str, str]:
    return {
        name: sha256_bytes((bundle / name).read_bytes())
        for name in sorted(("captured_input.wav", "output_reference.wav", "run.json", "qc.json"))
    }


def _load_resources(project_root: Path) -> _WorkflowResources:
    loaded = load_config(
        "audio",
        project_root / "tests/fixtures/audio/ess_offline_development.yaml",
        project_root=project_root,
    )
    if not isinstance(loaded.model, AudioConfig):
        raise SimulatedWorkflowError(
            "development audio fixture did not load as AudioConfig",
            code="invalid_audio_config",
            phase="setup",
            run_id="unassigned",
            bundle_path=project_root / "development" / "demo",
        )
    excitation = spec_from_audio_config(loaded.model)
    generated = generate_ess(excitation)
    timing = generated.timing
    processing_spec = PilotBundleProcessingSpec(
        sample_rate_hz=excitation.sample_rate_hz,
        sweep_sample_count=timing.sweep_sample_count,
        pre_silence_sample_count=timing.pre_silence_sample_count,
        start_frequency_hz=excitation.start_frequency_hz,
        end_frequency_hz=excitation.end_frequency_hz,
        analysis_lower_hz=500.0,
        analysis_upper_hz=8_000.0,
    )
    return _WorkflowResources(generated, processing_spec)


def _load_calibration(project_root: Path) -> MicrophoneCalibration:
    return load_dayton_calibration(
        project_root / CALIBRATION_RELATIVE_PATH,
        expected_sha256=CALIBRATION_SHA256,
    )


def _validate_structural_bundle(bundle: Path, run_id: str) -> None:
    run = _json_object(bundle / "run.json")
    qc = _json_object(bundle / "qc.json")
    if run.get("run_id") != run_id or run.get("final_state") != "completed":
        raise ValueError("capture identity or completed state differs")
    flags = run.get("backend_status_flags")
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise ValueError("backend status flags are invalid")
    if "underrun" in flags or qc.get("underrun") is True:
        raise ValueError("backend underrun requires retry")
    if "overrun" in flags or qc.get("overrun") is True:
        raise ValueError("backend overrun requires retry")
    clipping = qc.get("clipping_sample_count")
    if isinstance(clipping, bool) or not isinstance(clipping, int) or clipping != 0:
        raise ValueError("clipping samples require retry")
    if qc.get("complete_capture") is not True:
        raise ValueError("capture bundle is incomplete")


def _validate_processing_result(result: PilotBundleProcessingResult) -> None:
    frequency = np.asarray(result.uncalibrated.arrays["frequency_hz"], dtype=np.float64)
    analysis = np.asarray(result.uncalibrated.arrays["analysis_band_mask"], dtype=np.bool_)
    calibration_valid = np.asarray(result.calibrated_arrays["calibration_valid"], dtype=np.bool_)
    required = (frequency >= 500.0) & (frequency <= 8_000.0)
    if not bool(analysis.any()) or not bool(required.any()):
        raise ValueError("analysis band contains no frequency bins")
    if not bool(calibration_valid[required].all()):
        raise ValueError("iMM-6C calibration is invalid within 500-8000 Hz")
    for variant in ("raw", "aligned"):
        raw_phase = result.uncalibrated.arrays[f"phase_{variant}_rad"]
        calibrated_phase = result.calibrated_arrays[f"phase_{variant}_calibrated_rad"]
        if not np.array_equal(raw_phase, calibrated_phase):
            raise ValueError("amplitude calibration changed phase")


def _receipt_payload(
    *,
    result: PilotBundleProcessingResult,
    run_id: str,
    bundle_relative_path: str,
    bundle_hashes: dict[str, str],
    arrays_sha256: str,
    created_at: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "source_run_id": run_id,
        "source_bundle_relative_path": bundle_relative_path,
        "source_bundle_sha256": bundle_hashes,
        "processing_arrays_npz_sha256": arrays_sha256,
        "analysis_band_lower_hz": 500.0,
        "analysis_band_upper_hz": 8_000.0,
        "microphone_calibration": asdict(result.receipt),
        "phase_calibrated": False,
        "absolute_spl_calibrated": False,
        "synthetic": True,
        "development": True,
        "provisional": True,
        "experimental_result": False,
        "formal_acoustic_decision": "not_evaluated",
        "created_at": created_at,
    }


def _publish_processing(
    *,
    session_root: Path,
    bundle: Path,
    run_id: str,
    result: PilotBundleProcessingResult,
    created_at: datetime,
) -> Path:
    processing_parent = (session_root / "processed" / f"run_{run_id}").resolve()
    if not processing_parent.is_relative_to(session_root.resolve()):
        raise StorageError("processing path escapes the development demo session")
    processing_parent.mkdir(parents=True, exist_ok=True)
    target = (processing_parent / "processing_calibrated").resolve()
    if target.exists():
        raise StorageError(f"processing already exists for run: {run_id}")
    arrays = dict(result.uncalibrated.arrays)
    arrays.update(result.calibrated_arrays)
    arrays_bytes = deterministic_npz_bytes(arrays)
    arrays_digest = sha256_bytes(arrays_bytes)
    bundle_relative = bundle.relative_to(session_root).as_posix()
    timestamp = created_at.astimezone(UTC).isoformat()
    receipt = _receipt_payload(
        result=result,
        run_id=run_id,
        bundle_relative_path=bundle_relative,
        bundle_hashes=_bundle_hashes(bundle),
        arrays_sha256=arrays_digest,
        created_at=timestamp,
    )
    receipt_bytes = canonical_json_bytes(receipt)
    receipt_digest = sha256_bytes(receipt_bytes)
    metadata = {
        "data_origin": "development_demo",
        "fake_backend": True,
        "hardware_io_performed": False,
        "playback_performed": False,
        "recording_performed": False,
        "formal_eligible": False,
        "experimental_result": False,
        "processing_receipt_sha256": receipt_digest,
    }
    record = {
        "schema_version": "1.0.0",
        "processing_id": "calibrated",
        "source_run_id": run_id,
        "status": "complete",
        "processing_receipt_sha256": receipt_digest,
        "created_at": timestamp,
        "structural_result": "passed",
        "formal_acoustic_decision": "not_evaluated",
    }
    staging = Path(tempfile.mkdtemp(prefix=".calibrated.staging-", dir=processing_parent))
    published = False
    try:
        atomic_write_bytes(staging / "processing_arrays.npz", arrays_bytes)
        atomic_write_bytes(
            staging / "processing_arrays.npz.sha256",
            _sidecar(arrays_digest, "processing_arrays.npz"),
        )
        atomic_write_bytes(staging / "processing_receipt.json", receipt_bytes)
        atomic_write_bytes(
            staging / "processing_receipt.sha256",
            _sidecar(receipt_digest, "processing_receipt.json"),
        )
        atomic_write_bytes(staging / "processing_metadata.json", canonical_json_bytes(metadata))
        atomic_write_bytes(staging / "processing_record.json", canonical_json_bytes(record))
        atomic_write_bytes(staging / "PROCESSING_COMPLETE", b"complete\n")
        if target.exists():
            raise StorageError(f"processing already exists for run: {run_id}")
        os.rename(staging, target)
        published = True
        return target
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


class SimulatedMeasurementRunner:
    """One deep fake-only entry for capture, processing, calibration, and publication."""

    backend_type = "fake_full_duplex"
    workflow_kind = "calibrated_processing"
    requires_processing_receipt = True

    def __init__(
        self,
        *,
        project_root: Path,
        session_root: Path,
        backend_factory: BackendFactory | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.session_root = session_root.resolve()
        self._backend_factory = backend_factory or (
            lambda _repeat, _condition: FakeFullDuplexBackend(
                fixed_delay_samples=1, linear_gain=0.5
            )
        )
        self._now = now or (lambda: datetime.now(UTC))
        self._resources = _load_resources(self.project_root)

    def run_repeat(
        self,
        *,
        condition: DemoCondition,
        repeat_index: int,
        target: Path,
        run_id: str,
        cancellation: CancellationToken,
    ) -> SimulatedRepeatResult:
        bundle = target.resolve()
        capture_root = (self.session_root / "captures").resolve()
        if not bundle.is_relative_to(capture_root):
            raise SimulatedWorkflowError(
                "capture target escapes the development demo root",
                code="capture_path_escape",
                phase="capture",
                run_id=run_id,
                bundle_path=bundle,
            )
        request = PilotCaptureRequest(
            run_id=run_id,
            output_samples=self._resources.generated.samples,
            block_size_frames=256,
            started_at_utc=self._now(),
        )
        PilotCaptureEngine().capture(
            request,
            bundle,
            self._backend_factory(repeat_index, condition),
            cancellation=cancellation,
        )
        bundle_before = {path.name: path.read_bytes() for path in bundle.iterdir()}
        try:
            _validate_structural_bundle(bundle, run_id)
        except (OSError, ValueError) as exc:
            raise SimulatedWorkflowError(
                str(exc),
                code="structural_capture_failed",
                phase="capture",
                run_id=run_id,
                bundle_path=bundle,
            ) from exc
        try:
            calibration = _load_calibration(self.project_root)
        except MicrophoneCalibrationError as exc:
            raise SimulatedWorkflowError(
                f"iMM-6C calibration failed: {exc}",
                code="calibration_failed",
                phase="calibration",
                run_id=run_id,
                bundle_path=bundle,
            ) from exc
        try:
            processed = process_pilot_capture_bundle(
                bundle,
                calibration,
                spec=self._resources.processing_spec,
            )
        except Exception as exc:
            raise SimulatedWorkflowError(
                f"ESS processing failed: {exc}",
                code="processing_failed",
                phase="processing",
                run_id=run_id,
                bundle_path=bundle,
            ) from exc
        try:
            _validate_processing_result(processed)
        except ValueError as exc:
            raise SimulatedWorkflowError(
                str(exc),
                code="calibration_failed",
                phase="calibration",
                run_id=run_id,
                bundle_path=bundle,
            ) from exc
        try:
            processing = _publish_processing(
                session_root=self.session_root,
                bundle=bundle,
                run_id=run_id,
                result=processed,
                created_at=self._now(),
            )
        except Exception as exc:
            raise SimulatedWorkflowError(
                f"processing persistence failed: {exc}",
                code="persistence_failed",
                phase="persistence",
                run_id=run_id,
                bundle_path=bundle,
                processing_published=False,
            ) from exc
        bundle_after = {path.name: path.read_bytes() for path in bundle.iterdir()}
        if bundle_after != bundle_before:
            raise SimulatedWorkflowError(
                "processing modified the immutable capture bundle",
                code="source_bundle_modified",
                phase="persistence",
                run_id=run_id,
                bundle_path=bundle,
                processing_published=True,
            )
        return SimulatedRepeatResult(
            run_id=run_id,
            bundle_path=bundle,
            processing_directory=processing,
            processing_receipt_path=processing / "processing_receipt.json",
        )


def validate_simulated_repeat_evidence(
    bundle_path: str | Path,
    processing_directory: str | Path,
    *,
    project_root: str | Path,
    expected_run_id: str,
) -> SimulatedRepeatResult:
    """Replay one successful fake repeat without writing or invoking hardware APIs."""

    bundle = Path(bundle_path).resolve()
    processing = Path(processing_directory).resolve()
    if (
        not processing.is_dir()
        or {path.name for path in processing.iterdir()} != PROCESSING_FILE_NAMES
    ):
        raise SimulatedWorkflowError(
            "processing evidence does not contain the exact required files",
            code="invalid_processing_envelope",
            phase="recovery",
            run_id=expected_run_id,
            bundle_path=bundle,
        )
    try:
        _validate_structural_bundle(bundle, expected_run_id)
        resources = _load_resources(Path(project_root).resolve())
        calibration = _load_calibration(Path(project_root).resolve())
        recomputed = process_pilot_capture_bundle(
            bundle, calibration, spec=resources.processing_spec
        )
        _validate_processing_result(recomputed)
        arrays = dict(recomputed.uncalibrated.arrays)
        arrays.update(recomputed.calibrated_arrays)
        expected_arrays = deterministic_npz_bytes(arrays)
        stored_arrays = (processing / "processing_arrays.npz").read_bytes()
        if stored_arrays != expected_arrays:
            raise ValueError("processing arrays differ from replay")
        load_deterministic_npz(stored_arrays)
        arrays_digest = sha256_bytes(stored_arrays)
        if (processing / "processing_arrays.npz.sha256").read_bytes() != _sidecar(
            arrays_digest, "processing_arrays.npz"
        ):
            raise ValueError("processing arrays sidecar differs")
        receipt_path = processing / "processing_receipt.json"
        receipt = _json_object(receipt_path)
        record = _json_object(processing / "processing_record.json")
        created_at = record.get("created_at")
        if not isinstance(created_at, str):
            raise ValueError("processing record timestamp is invalid")
        expected_receipt = _receipt_payload(
            result=recomputed,
            run_id=expected_run_id,
            bundle_relative_path=str(receipt.get("source_bundle_relative_path")),
            bundle_hashes=_bundle_hashes(bundle),
            arrays_sha256=arrays_digest,
            created_at=created_at,
        )
        receipt_bytes = canonical_json_bytes(expected_receipt)
        if receipt_path.read_bytes() != receipt_bytes:
            raise ValueError("processing receipt differs from replay")
        receipt_digest = sha256_bytes(receipt_bytes)
        if (processing / "processing_receipt.sha256").read_bytes() != _sidecar(
            receipt_digest, "processing_receipt.json"
        ):
            raise ValueError("processing receipt sidecar differs")
        metadata = _json_object(processing / "processing_metadata.json")
        if metadata.get("processing_receipt_sha256") != receipt_digest:
            raise ValueError("processing metadata receipt binding differs")
        if (
            record.get("source_run_id") != expected_run_id
            or record.get("status") != "complete"
            or record.get("processing_receipt_sha256") != receipt_digest
        ):
            raise ValueError("processing record binding differs")
        if (processing / "PROCESSING_COMPLETE").read_bytes() != b"complete\n":
            raise ValueError("processing completion marker differs")
    except (OSError, ValueError, MicrophoneCalibrationError) as exc:
        raise SimulatedWorkflowError(
            f"saved repeat evidence was rejected: {exc}",
            code="invalid_saved_evidence",
            phase="recovery",
            run_id=expected_run_id,
            bundle_path=bundle,
            processing_published=processing.is_dir(),
        ) from exc
    return SimulatedRepeatResult(
        run_id=expected_run_id,
        bundle_path=bundle,
        processing_directory=processing,
        processing_receipt_path=processing / "processing_receipt.json",
    )
