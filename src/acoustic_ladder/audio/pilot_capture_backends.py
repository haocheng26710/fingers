"""Deterministic fake and safety-gated sounddevice pilot backends."""

from __future__ import annotations

import importlib
import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.pilot_capture import (
    SAMPLE_RATE_HZ,
    BackendCapture,
    BackendCaptureCancelled,
    BackendCaptureError,
    CancellationToken,
    PilotCaptureRequest,
)


@dataclass(frozen=True)
class DeviceBinding:
    """Explicit input/output identity authorized for one pilot run."""

    input_device_id: int
    output_device_id: int
    host_api: str
    input_channel: int
    output_channel: int

    def as_dict(self) -> dict[str, object]:
        return {
            "host_api": self.host_api,
            "input_channel": self.input_channel,
            "input_device_id": self.input_device_id,
            "output_channel": self.output_channel,
            "output_device_id": self.output_device_id,
        }


@dataclass(frozen=True)
class HardwareAuthorization:
    """Runtime-only booleans and frozen binding used by the real backend gate."""

    hardware_ready: bool
    operator_confirmed: bool
    playback_authorized: bool
    run_mode: str
    formal_experiment_enabled: bool
    sample_rate_hz: int
    input_channel_count: int
    output_channel_count: int
    playback_level_frozen: bool
    configuration_origin: str
    authorized_binding: DeviceBinding


class FakeFullDuplexBackend:
    """Block-wise deterministic backend; never imports or calls sounddevice."""

    def __init__(
        self,
        *,
        fixed_delay_samples: int = 0,
        linear_gain: float = 1.0,
        noise_amplitude: float = 0.0,
        cancel_at_block: int | None = None,
        fail_at_block: int | None = None,
        short_input_at_block: int | None = None,
        status_flags: tuple[str, ...] = (),
    ) -> None:
        if fixed_delay_samples < 0:
            raise ValueError("fixed_delay_samples cannot be negative")
        if not math.isfinite(linear_gain) or not math.isfinite(noise_amplitude):
            raise ValueError("fake backend gain and noise must be finite")
        if noise_amplitude < 0:
            raise ValueError("noise_amplitude cannot be negative")
        self.fixed_delay_samples = fixed_delay_samples
        self.linear_gain = linear_gain
        self.noise_amplitude = noise_amplitude
        self.cancel_at_block = cancel_at_block
        self.fail_at_block = fail_at_block
        self.short_input_at_block = short_input_at_block
        self.status_flags = status_flags

    def capture(
        self, request: PilotCaptureRequest, cancellation: CancellationToken
    ) -> BackendCapture:
        if cancellation.cancelled:
            raise BackendCaptureCancelled("capture cancelled before fake backend start")
        submitted = np.ascontiguousarray(request.output_samples.copy(), dtype=np.float32)
        sample_count = submitted.shape[1]
        captured = np.zeros_like(submitted)
        available = sample_count - self.fixed_delay_samples
        if available > 0:
            captured[:, self.fixed_delay_samples :] = submitted[:, :available] * np.float32(
                self.linear_gain
            )
        if self.noise_amplitude:
            indices = np.arange(sample_count, dtype=np.float32)
            captured += (
                np.sin(indices * np.float32(0.7548777)) * np.float32(self.noise_amplitude)
            ).reshape(1, -1)
        block_count = math.ceil(sample_count / request.block_size_frames)
        for block_index in range(block_count):
            if block_index == self.cancel_at_block:
                cancellation.cancel()
                raise BackendCaptureCancelled("capture cancelled during fake backend exchange")
            if block_index == self.fail_at_block:
                raise BackendCaptureError("injected fake backend failure")
            if block_index == self.short_input_at_block:
                captured = captured[:, :-1]
                break
        return BackendCapture(
            captured_input=np.ascontiguousarray(captured, dtype=np.float32),
            submitted_output=submitted,
            status_flags=self.status_flags,
            backend_type="fake_full_duplex",
        )


class _SoundDeviceStream(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class _SoundDeviceModule(Protocol):
    CallbackStop: type[BaseException]

    def Stream(self, **settings: object) -> _SoundDeviceStream: ...


class SoundDeviceFullDuplexBackend:
    """Lazy adapter whose complete gate runs before module load or Stream open."""

    def __init__(
        self,
        *,
        current_binding: DeviceBinding,
        authorization: HardwareAuthorization,
        module_loader: Callable[[str], object] = importlib.import_module,
    ) -> None:
        self.current_binding = current_binding
        self.authorization = authorization
        self._module_loader = module_loader

    def capture(
        self, request: PilotCaptureRequest, cancellation: CancellationToken
    ) -> BackendCapture:
        checks = self._authorization_checks(request)
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise BackendCaptureError("real hardware safety gate rejected: " + ", ".join(failed))
        module = cast(_SoundDeviceModule, self._module_loader("sounddevice"))
        sample_count = request.output_samples.shape[1]
        captured = np.zeros_like(request.output_samples)
        submitted = np.zeros_like(request.output_samples)
        status_flags: set[str] = set()
        finished = threading.Event()
        callback_error: list[str] = []
        cursor = 0

        def callback(
            indata: NDArray[np.float32],
            outdata: NDArray[np.float32],
            frames: int,
            _time_info: object,
            status: object,
        ) -> None:
            nonlocal cursor
            outdata.fill(0.0)
            if cancellation.cancelled:
                finished.set()
                raise module.CallbackStop
            if bool(getattr(status, "input_overflow", False)):
                status_flags.add("overrun")
            if bool(getattr(status, "output_underflow", False)):
                status_flags.add("underrun")
            remaining = sample_count - cursor
            copied = min(frames, remaining)
            if copied <= 0:
                finished.set()
                raise module.CallbackStop
            try:
                if indata.ndim != 2 or indata.shape[0] < copied or indata.shape[1] != 1:
                    raise ValueError("sounddevice input callback returned an invalid shape")
                outdata[:copied, 0] = request.output_samples[0, cursor : cursor + copied]
                submitted[0, cursor : cursor + copied] = outdata[:copied, 0]
                captured[0, cursor : cursor + copied] = indata[:copied, 0]
            except Exception as exc:
                outdata.fill(0.0)
                callback_error.append(str(exc))
                finished.set()
                raise module.CallbackStop from exc
            cursor += copied
            if cursor == sample_count:
                finished.set()
                raise module.CallbackStop

        def finished_callback() -> None:
            finished.set()

        stream = module.Stream(
            samplerate=request.sample_rate_hz,
            blocksize=request.block_size_frames,
            dtype="float32",
            channels=(1, 1),
            device=(self.current_binding.input_device_id, self.current_binding.output_device_id),
            callback=callback,
            finished_callback=finished_callback,
        )
        try:
            stream.start()
            timeout_seconds = sample_count / request.sample_rate_hz + 5.0
            if not finished.wait(timeout_seconds):
                cancellation.cancel()
                raise BackendCaptureError("sounddevice stream did not finish before timeout")
        finally:
            stream.stop()
            stream.close()
        if cancellation.cancelled:
            raise BackendCaptureCancelled("sounddevice capture cancelled")
        if callback_error:
            raise BackendCaptureError(callback_error[0])
        if cursor != sample_count:
            raise BackendCaptureError("sounddevice capture returned an incomplete input buffer")
        return BackendCapture(
            captured_input=np.ascontiguousarray(captured),
            submitted_output=np.ascontiguousarray(submitted),
            status_flags=tuple(sorted(status_flags)),
            backend_type="sounddevice_full_duplex",
            device_binding=self.current_binding.as_dict(),
            authorization_checks=checks,
        )

    def _authorization_checks(self, request: PilotCaptureRequest) -> dict[str, bool]:
        authorization = self.authorization
        binding = self.current_binding
        return {
            "binding_matches_authorization": binding == authorization.authorized_binding,
            "configuration_origin_is_pilot": authorization.configuration_origin == "pilot",
            "formal_experiment_enabled_is_false": not authorization.formal_experiment_enabled,
            "hardware_ready": authorization.hardware_ready,
            "host_api_provided": bool(binding.host_api),
            "input_channel_count_is_mono": authorization.input_channel_count == 1,
            "input_channel_provided": binding.input_channel >= 0,
            "input_device_id_provided": binding.input_device_id >= 0,
            "operator_confirmed": authorization.operator_confirmed,
            "output_channel_count_is_mono": authorization.output_channel_count == 1,
            "output_channel_provided": binding.output_channel >= 0,
            "output_device_id_provided": binding.output_device_id >= 0,
            "playback_authorized": authorization.playback_authorized,
            "playback_level_frozen": authorization.playback_level_frozen,
            "run_mode_is_pilot": authorization.run_mode == "pilot",
            "sample_rate_is_48000": (
                authorization.sample_rate_hz == request.sample_rate_hz == SAMPLE_RATE_HZ
            ),
        }
