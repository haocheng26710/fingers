"""Guarded mono pilot full-duplex capture with create-only publication."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.excitation_persistence import encode_ieee_float32_wav
from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.storage.io import sha256_bytes

SAMPLE_RATE_HZ = 48_000


class CaptureState(StrEnum):
    DISARMED = "disarmed"
    ARMED = "armed"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PilotCaptureError(RuntimeError):
    """Domain error carrying the non-success terminal state."""

    def __init__(self, message: str, *, state: CaptureState, code: str) -> None:
        super().__init__(message)
        self.state = state
        self.code = code


class BackendCaptureError(RuntimeError):
    """Backend failure translated by the capture engine."""


class BackendCaptureCancelled(RuntimeError):
    """Backend stopped after a cancellation request."""


class CancellationToken:
    """Thread-safe cancellation signal shared with a running backend."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class PilotCaptureRequest:
    run_id: str
    output_samples: NDArray[np.float32]
    block_size_frames: int
    started_at_utc: datetime
    sample_rate_hz: int = SAMPLE_RATE_HZ


@dataclass(frozen=True)
class BackendCapture:
    captured_input: NDArray[np.float32]
    submitted_output: NDArray[np.float32]
    status_flags: tuple[str, ...]
    backend_type: str
    device_binding: dict[str, object] | None = None
    authorization_checks: dict[str, bool] | None = None


class FullDuplexBackend(Protocol):
    def capture(
        self, request: PilotCaptureRequest, cancellation: CancellationToken
    ) -> BackendCapture: ...


@dataclass(frozen=True)
class PilotCaptureResult:
    state: CaptureState
    bundle_path: Path
    captured_input: NDArray[np.float32]
    output_reference: NDArray[np.float32]
    status_flags: tuple[str, ...]


class PilotCaptureEngine:
    """Execute one pilot capture and publish only a complete four-file bundle."""

    def __init__(self) -> None:
        self.state = CaptureState.DISARMED

    def capture(
        self,
        request: PilotCaptureRequest,
        output_directory: str | Path,
        backend: FullDuplexBackend,
        *,
        cancellation: CancellationToken | None = None,
    ) -> PilotCaptureResult:
        self._validate_request(request)
        target = Path(output_directory).resolve()
        if target.exists():
            raise PilotCaptureError(
                f"immutable capture directory already exists: {target}",
                state=CaptureState.DISARMED,
                code="target_exists",
            )
        token = cancellation or CancellationToken()
        self.state = CaptureState.ARMED
        if token.cancelled:
            self.state = CaptureState.CANCELLED
            raise PilotCaptureError(
                "capture cancelled before start",
                state=self.state,
                code="cancelled",
            )
        self.state = CaptureState.RUNNING
        try:
            backend_result = backend.capture(request, token)
        except BackendCaptureCancelled as exc:
            self.state = CaptureState.CANCELLED
            raise PilotCaptureError(str(exc), state=self.state, code="cancelled") from exc
        except Exception as exc:
            self.state = CaptureState.FAILED
            raise PilotCaptureError(
                f"full-duplex backend failed: {exc}",
                state=self.state,
                code="backend_error",
            ) from exc
        try:
            self._validate_backend_result(request, backend_result)
            self.state = CaptureState.COMPLETED
            self._publish(target, request, backend_result)
        except PilotCaptureError:
            self.state = CaptureState.FAILED
            raise
        except Exception as exc:
            self.state = CaptureState.FAILED
            raise PilotCaptureError(
                f"capture bundle publication failed: {exc}",
                state=self.state,
                code="publication_error",
            ) from exc
        return PilotCaptureResult(
            state=self.state,
            bundle_path=target,
            captured_input=backend_result.captured_input,
            output_reference=backend_result.submitted_output,
            status_flags=backend_result.status_flags,
        )

    @staticmethod
    def _validate_request(request: PilotCaptureRequest) -> None:
        samples = request.output_samples
        if (
            samples.ndim != 2
            or samples.shape[0] != 1
            or samples.shape[1] <= 0
            or samples.dtype != np.float32
            or not samples.flags.c_contiguous
            or not bool(np.isfinite(samples).all())
        ):
            raise PilotCaptureError(
                "output samples must be finite C-contiguous [1,n] float32",
                state=CaptureState.DISARMED,
                code="invalid_output",
            )
        if request.sample_rate_hz != SAMPLE_RATE_HZ:
            raise PilotCaptureError(
                "pilot capture sample rate must be 48000 Hz",
                state=CaptureState.DISARMED,
                code="invalid_sample_rate",
            )
        if request.block_size_frames <= 0:
            raise PilotCaptureError(
                "block_size_frames must be positive",
                state=CaptureState.DISARMED,
                code="invalid_block_size",
            )
        if not request.run_id or any(
            not (character.isascii() and (character.isalnum() or character in "-_"))
            for character in request.run_id
        ):
            raise PilotCaptureError(
                "run_id must use ASCII letters, digits, hyphens, or underscores",
                state=CaptureState.DISARMED,
                code="invalid_run_id",
            )
        if request.started_at_utc.tzinfo is None:
            raise PilotCaptureError(
                "started_at_utc must be timezone-aware",
                state=CaptureState.DISARMED,
                code="invalid_timestamp",
            )

    @staticmethod
    def _validate_backend_result(request: PilotCaptureRequest, result: BackendCapture) -> None:
        expected_shape = request.output_samples.shape
        for label, samples in (
            ("captured input", result.captured_input),
            ("submitted output", result.submitted_output),
        ):
            if (
                samples.shape != expected_shape
                or samples.dtype != np.float32
                or not samples.flags.c_contiguous
                or not bool(np.isfinite(samples).all())
            ):
                raise PilotCaptureError(
                    f"{label} must be finite C-contiguous [1,n] float32 with exact length",
                    state=CaptureState.FAILED,
                    code="invalid_backend_result",
                )
        if not np.array_equal(result.submitted_output, request.output_samples):
            raise PilotCaptureError(
                "backend submitted output differs from the requested sequence",
                state=CaptureState.FAILED,
                code="output_reference_mismatch",
            )

    @staticmethod
    def _publish(target: Path, request: PilotCaptureRequest, result: BackendCapture) -> None:
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise PilotCaptureError(
                f"immutable capture directory already exists: {target}",
                state=CaptureState.FAILED,
                code="target_exists",
            )
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=parent))
        published = False
        try:
            output_wav = encode_ieee_float32_wav(result.submitted_output, request.sample_rate_hz)
            input_wav = encode_ieee_float32_wav(result.captured_input, request.sample_rate_hz)
            run_payload = {
                "authorization_checks": result.authorization_checks
                or {"real_hardware_authorized": False},
                "backend_status_flags": list(result.status_flags),
                "backend_type": result.backend_type,
                "channel_count_input": 1,
                "channel_count_output": 1,
                "captured_input_wav_sha256": sha256_bytes(input_wav),
                "device_binding": result.device_binding,
                "final_state": CaptureState.COMPLETED.value,
                "mode": "pilot",
                "output_reference_wav_sha256": sha256_bytes(output_wav),
                "run_id": request.run_id,
                "sample_count": request.output_samples.shape[1],
                "sample_rate_hz": request.sample_rate_hz,
                "started_at_utc": request.started_at_utc.astimezone(UTC).isoformat(),
            }
            qc_payload = _structural_qc(result)
            _write_staged_file(staging / "captured_input.wav", input_wav)
            _write_staged_file(staging / "output_reference.wav", output_wav)
            _write_staged_file(staging / "run.json", canonical_json_bytes(run_payload))
            _write_staged_file(staging / "qc.json", canonical_json_bytes(qc_payload))
            if target.exists():
                raise PilotCaptureError(
                    f"immutable capture directory already exists: {target}",
                    state=CaptureState.FAILED,
                    code="target_exists",
                )
            staging.rename(target)
            published = True
        finally:
            if not published and staging.exists():
                shutil.rmtree(staging)


def _structural_qc(result: BackendCapture) -> dict[str, object]:
    captured = result.captured_input
    output = result.submitted_output
    return {
        "captured_input_finite": bool(np.isfinite(captured).all()),
        "captured_input_peak": float(np.max(np.abs(captured))),
        "captured_input_rms": float(np.sqrt(np.mean(np.square(captured)))),
        "captured_input_sample_count": captured.shape[1],
        "clipping_sample_count": int(np.count_nonzero(np.abs(captured) > 1.0)),
        "complete_capture": captured.shape == output.shape,
        "evaluation_status": "pilot_structural_metrics_only",
        "output_reference_finite": bool(np.isfinite(output).all()),
        "output_reference_peak": float(np.max(np.abs(output))),
        "output_reference_rms": float(np.sqrt(np.mean(np.square(output)))),
        "output_reference_sample_count": output.shape[1],
        "overrun": "overrun" in result.status_flags,
        "qc_decision": "not_evaluated",
        "thresholds_applied": False,
        "underrun": "underrun" in result.status_flags,
    }


def _write_staged_file(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
