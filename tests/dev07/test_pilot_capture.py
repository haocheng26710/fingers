from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

import acoustic_ladder.audio.pilot_capture as pilot_module
from acoustic_ladder.audio.excitation_persistence import decode_ieee_float32_wav
from acoustic_ladder.audio.pilot_capture import (
    CancellationToken,
    CaptureState,
    PilotCaptureEngine,
    PilotCaptureError,
    PilotCaptureRequest,
)
from acoustic_ladder.audio.pilot_capture_backends import (
    DeviceBinding,
    FakeFullDuplexBackend,
    HardwareAuthorization,
    SoundDeviceFullDuplexBackend,
)


def _output() -> np.ndarray:
    return np.array([[0.0, 0.25, -0.5, 0.75, 0.5, 0.0]], dtype=np.float32)


def _request(*, output: np.ndarray | None = None) -> PilotCaptureRequest:
    return PilotCaptureRequest(
        run_id="pilot-001",
        output_samples=_output() if output is None else output,
        block_size_frames=2,
        started_at_utc=datetime(2026, 8, 23, 0, 0, tzinfo=UTC),
    )


def _binding(*, output_device_id: int = 22) -> DeviceBinding:
    return DeviceBinding(11, output_device_id, "authorized-host-api", 0, 0)


def _authorization(
    *, playback_authorized: bool = True, formal_experiment_enabled: bool = False
) -> HardwareAuthorization:
    return HardwareAuthorization(
        hardware_ready=True,
        operator_confirmed=True,
        playback_authorized=playback_authorized,
        run_mode="pilot",
        formal_experiment_enabled=formal_experiment_enabled,
        sample_rate_hz=48_000,
        input_channel_count=1,
        output_channel_count=1,
        playback_level_frozen=True,
        configuration_origin="pilot",
        authorized_binding=_binding(),
    )


def test_fake_backend_completes_and_publishes_minimal_bundle(tmp_path) -> None:
    output = np.array([[0.0, 0.25, -0.5, 0.75, 0.5, 0.0]], dtype=np.float32)
    request = PilotCaptureRequest(
        run_id="pilot-001",
        output_samples=output,
        block_size_frames=2,
        started_at_utc=datetime(2026, 8, 23, 0, 0, tzinfo=UTC),
    )

    result = PilotCaptureEngine().capture(
        request,
        tmp_path / "pilot-001",
        FakeFullDuplexBackend(fixed_delay_samples=1, linear_gain=0.5),
    )

    assert result.state is CaptureState.COMPLETED
    assert {path.name for path in result.bundle_path.iterdir()} == {
        "captured_input.wav",
        "output_reference.wav",
        "run.json",
        "qc.json",
    }


def test_output_reference_is_exact_submitted_sequence(tmp_path) -> None:
    output = _output()
    result = PilotCaptureEngine().capture(
        _request(output=output), tmp_path / "run", FakeFullDuplexBackend()
    )
    restored, rate = decode_ieee_float32_wav(
        (result.bundle_path / "output_reference.wav").read_bytes()
    )
    assert rate == 48_000
    assert np.array_equal(result.output_reference, output)
    assert np.array_equal(restored, output)


def test_fake_delay_gain_and_noise_are_deterministic(tmp_path) -> None:
    settings = {"fixed_delay_samples": 2, "linear_gain": 0.5, "noise_amplitude": 0.001}
    first = PilotCaptureEngine().capture(
        _request(), tmp_path / "first", FakeFullDuplexBackend(**settings)
    )
    second = PilotCaptureEngine().capture(
        _request(), tmp_path / "second", FakeFullDuplexBackend(**settings)
    )
    expected_signal = np.zeros_like(_output())
    expected_signal[:, 2:] = _output()[:, :-2] * np.float32(0.5)
    indices = np.arange(_output().shape[1], dtype=np.float32)
    expected = expected_signal + (
        np.sin(indices * np.float32(0.7548777)) * np.float32(0.001)
    ).reshape(1, -1)
    assert np.array_equal(first.captured_input, second.captured_input)
    assert np.array_equal(first.captured_input, expected)


def test_capture_arrays_are_channel_first_float32(tmp_path) -> None:
    result = PilotCaptureEngine().capture(_request(), tmp_path / "run", FakeFullDuplexBackend())
    assert result.captured_input.shape == (1, _output().shape[1])
    assert result.output_reference.shape == (1, _output().shape[1])
    assert result.captured_input.dtype == np.float32
    assert result.output_reference.dtype == np.float32
    assert result.captured_input.flags.c_contiguous


class _ForbiddenModuleLoader:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, name: str) -> object:
        self.calls += 1
        raise AssertionError(f"module loader must not be called: {name}")


def test_missing_real_authorization_is_rejected_before_stream_open(tmp_path) -> None:
    loader = _ForbiddenModuleLoader()
    backend = SoundDeviceFullDuplexBackend(
        current_binding=_binding(),
        authorization=_authorization(playback_authorized=False),
        module_loader=loader,
    )
    with pytest.raises(PilotCaptureError, match="playback_authorized") as caught:
        PilotCaptureEngine().capture(_request(), tmp_path / "run", backend)
    assert caught.value.state is CaptureState.FAILED
    assert loader.calls == 0
    assert not (tmp_path / "run").exists()


def test_changed_device_binding_is_rejected_before_stream_open(tmp_path) -> None:
    loader = _ForbiddenModuleLoader()
    backend = SoundDeviceFullDuplexBackend(
        current_binding=_binding(output_device_id=99),
        authorization=_authorization(),
        module_loader=loader,
    )
    with pytest.raises(PilotCaptureError, match="binding"):
        PilotCaptureEngine().capture(_request(), tmp_path / "run", backend)
    assert loader.calls == 0


def test_formal_experiment_mode_is_rejected_before_stream_open(tmp_path) -> None:
    loader = _ForbiddenModuleLoader()
    backend = SoundDeviceFullDuplexBackend(
        current_binding=_binding(),
        authorization=_authorization(formal_experiment_enabled=True),
        module_loader=loader,
    )
    with pytest.raises(PilotCaptureError, match="formal_experiment_enabled"):
        PilotCaptureEngine().capture(_request(), tmp_path / "run", backend)
    assert loader.calls == 0


def test_cancellation_marks_cancelled_and_does_not_publish(tmp_path) -> None:
    control = CancellationToken()
    engine = PilotCaptureEngine()
    with pytest.raises(PilotCaptureError) as caught:
        engine.capture(
            _request(),
            tmp_path / "run",
            FakeFullDuplexBackend(cancel_at_block=1),
            cancellation=control,
        )
    assert control.cancelled
    assert engine.state is CaptureState.CANCELLED
    assert caught.value.state is CaptureState.CANCELLED
    assert not (tmp_path / "run").exists()


def test_backend_exception_marks_failed_and_does_not_publish(tmp_path) -> None:
    engine = PilotCaptureEngine()
    with pytest.raises(PilotCaptureError, match="injected fake backend failure") as caught:
        engine.capture(_request(), tmp_path / "run", FakeFullDuplexBackend(fail_at_block=1))
    assert caught.value.state is CaptureState.FAILED
    assert engine.state is CaptureState.FAILED
    assert not (tmp_path / "run").exists()


def test_underrun_and_overrun_are_recorded_in_run_and_qc(tmp_path) -> None:
    result = PilotCaptureEngine().capture(
        _request(),
        tmp_path / "run",
        FakeFullDuplexBackend(status_flags=("underrun", "overrun")),
    )
    run = json.loads((result.bundle_path / "run.json").read_bytes())
    qc = json.loads((result.bundle_path / "qc.json").read_bytes())
    assert run["backend_status_flags"] == ["underrun", "overrun"]
    assert qc["underrun"] is True
    assert qc["overrun"] is True
    assert qc["evaluation_status"] == "pilot_structural_metrics_only"
    assert qc["qc_decision"] == "not_evaluated"
    assert qc["thresholds_applied"] is False


def test_create_only_rejects_existing_run_without_changing_bytes(tmp_path) -> None:
    target = tmp_path / "run"
    target.mkdir()
    sentinel = target / "sentinel.bin"
    sentinel.write_bytes(b"unchanged")
    with pytest.raises(PilotCaptureError, match="already exists"):
        PilotCaptureEngine().capture(_request(), target, FakeFullDuplexBackend())
    assert sentinel.read_bytes() == b"unchanged"
    assert list(target.iterdir()) == [sentinel]


def test_staging_write_failure_leaves_no_final_or_owned_staging(tmp_path, monkeypatch) -> None:
    writes = 0
    original = pilot_module._write_staged_file

    def fail_second_write(path: Path, payload: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("injected staging write failure")
        original(path, payload)

    monkeypatch.setattr(pilot_module, "_write_staged_file", fail_second_write)
    with pytest.raises(PilotCaptureError, match="injected staging write failure"):
        PilotCaptureEngine().capture(_request(), tmp_path / "run", FakeFullDuplexBackend())
    assert not (tmp_path / "run").exists()
    assert not list(tmp_path.glob(".run.staging-*"))


class _CallbackStop(Exception):
    pass


class _FakeStatus:
    input_overflow = True
    output_underflow = True

    def __bool__(self) -> bool:
        return True


class _FakeStream:
    def __init__(
        self,
        owner: _FakeSoundDevice,
        callback: Callable[..., None],
        finished_callback: Callable[[], None],
        blocksize: int,
        **settings: object,
    ) -> None:
        self.owner = owner
        self.callback = callback
        self.finished_callback = finished_callback
        self.blocksize = blocksize
        self.settings = settings

    def start(self) -> None:
        self.owner.stream_started += 1
        remaining = _output().shape[1]
        while remaining:
            frames = min(self.blocksize, remaining)
            indata = np.full((frames, 1), 0.125, dtype=np.float32)
            outdata = np.empty((frames, 1), dtype=np.float32)
            try:
                self.callback(indata, outdata, frames, None, _FakeStatus())
            except _CallbackStop:
                self.owner.submitted.append(outdata.copy())
                break
            self.owner.submitted.append(outdata.copy())
            remaining -= frames
        self.finished_callback()

    def stop(self) -> None:
        self.owner.stream_stopped += 1

    def close(self) -> None:
        self.owner.stream_closed += 1


class _FakeSoundDevice:
    CallbackStop = _CallbackStop

    def __init__(self) -> None:
        self.stream_constructed = 0
        self.stream_started = 0
        self.stream_stopped = 0
        self.stream_closed = 0
        self.query_calls = 0
        self.submitted: list[np.ndarray] = []
        self.stream_settings: dict[str, object] = {}

    def Stream(self, **settings: object) -> _FakeStream:
        self.stream_constructed += 1
        self.stream_settings = settings
        return _FakeStream(self, **settings)

    def query_devices(self) -> None:
        self.query_calls += 1
        raise AssertionError("device enumeration is forbidden")


def test_injected_sounddevice_adapter_runs_callback_without_device_query(tmp_path) -> None:
    module = _FakeSoundDevice()
    backend = SoundDeviceFullDuplexBackend(
        current_binding=_binding(),
        authorization=_authorization(),
        module_loader=lambda _name: module,
    )
    result = PilotCaptureEngine().capture(_request(), tmp_path / "run", backend)
    assert result.state is CaptureState.COMPLETED
    assert np.array_equal(np.vstack(module.submitted).T, _output())
    assert np.all(result.captured_input == np.float32(0.125))
    assert module.stream_constructed == 1
    assert module.stream_started == module.stream_stopped == module.stream_closed == 1
    assert module.query_calls == 0


def test_tests_use_only_injected_sounddevice_and_never_real_hardware(tmp_path) -> None:
    module = _FakeSoundDevice()
    backend = SoundDeviceFullDuplexBackend(
        current_binding=_binding(),
        authorization=_authorization(),
        module_loader=lambda _name: module,
    )
    PilotCaptureEngine().capture(_request(), tmp_path / "run", backend)
    assert module.query_calls == 0
    assert module.stream_settings["device"] == (11, 22)
    assert module.stream_settings["channels"] == (1, 1)
    assert module.stream_settings["samplerate"] == 48_000
