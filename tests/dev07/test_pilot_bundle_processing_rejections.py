import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import acoustic_ladder.audio.microphone_calibration as calibration_module
from acoustic_ladder.audio.ess import generate_ess, spec_from_audio_config
from acoustic_ladder.audio.microphone_calibration import (
    MicrophoneCalibration,
    MicrophoneCalibrationError,
    PilotBundleProcessingSpec,
    load_dayton_calibration,
    process_pilot_capture_bundle,
)
from acoustic_ladder.audio.pilot_capture import PilotCaptureEngine, PilotCaptureRequest
from acoustic_ladder.audio.pilot_capture_backends import FakeFullDuplexBackend
from acoustic_ladder.config.bundle import load_config
from acoustic_ladder.config.models import AudioConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = PROJECT_ROOT / "calibration" / "microphones" / "dayton_imm6c" / "CMM29939.txt"
CALIBRATION_SHA256 = "421070ec6d41c1b92cb69f0f5e4e290f9644847d92d52590994a80ea9e17a11e"


@pytest.fixture
def processing_fixture(
    tmp_path: Path,
) -> tuple[Path, MicrophoneCalibration, PilotBundleProcessingSpec]:
    loaded = load_config(
        "audio",
        PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        project_root=PROJECT_ROOT,
    )
    assert isinstance(loaded.model, AudioConfig)
    excitation = spec_from_audio_config(loaded.model)
    generated = generate_ess(excitation)
    bundle = (
        PilotCaptureEngine()
        .capture(
            PilotCaptureRequest(
                run_id="rejection-fixture",
                output_samples=generated.samples,
                block_size_frames=256,
                started_at_utc=datetime(2026, 8, 23, tzinfo=UTC),
            ),
            tmp_path / "capture",
            FakeFullDuplexBackend(),
        )
        .bundle_path
    )
    timing = generated.timing
    calibration = load_dayton_calibration(CALIBRATION_PATH, expected_sha256=CALIBRATION_SHA256)
    spec = PilotBundleProcessingSpec(
        sample_rate_hz=48_000,
        sweep_sample_count=timing.sweep_sample_count,
        pre_silence_sample_count=timing.pre_silence_sample_count,
        start_frequency_hz=excitation.start_frequency_hz,
        end_frequency_hz=excitation.end_frequency_hz,
        analysis_lower_hz=500.0,
        analysis_upper_hz=8_000.0,
    )
    return bundle, calibration, spec


@pytest.mark.parametrize(
    "filename",
    ["captured_input.wav", "output_reference.wav", "run.json", "qc.json"],
)
def test_each_required_bundle_file_is_required(
    processing_fixture: tuple[Path, MicrophoneCalibration, PilotBundleProcessingSpec],
    filename: str,
) -> None:
    bundle, calibration, spec = processing_fixture
    (bundle / filename).unlink()

    with pytest.raises(MicrophoneCalibrationError) as caught:
        process_pilot_capture_bundle(bundle, calibration, spec=spec)

    assert caught.value.code == "missing_bundle_file"


def test_bundle_wav_hash_mismatch_is_rejected(
    processing_fixture: tuple[Path, MicrophoneCalibration, PilotBundleProcessingSpec],
) -> None:
    bundle, calibration, spec = processing_fixture
    captured = bundle / "captured_input.wav"
    captured.write_bytes(captured.read_bytes() + b"tamper")

    with pytest.raises(MicrophoneCalibrationError) as caught:
        process_pilot_capture_bundle(bundle, calibration, spec=spec)

    assert caught.value.code == "wav_sha256_mismatch"


@pytest.mark.parametrize("state", ["cancelled", "failed"])
def test_noncompleted_bundle_is_rejected(
    processing_fixture: tuple[Path, MicrophoneCalibration, PilotBundleProcessingSpec],
    state: str,
) -> None:
    bundle, calibration, spec = processing_fixture
    run_path = bundle / "run.json"
    run = json.loads(run_path.read_bytes())
    run["final_state"] = state
    run_path.write_text(json.dumps(run), encoding="utf-8")

    with pytest.raises(MicrophoneCalibrationError) as caught:
        process_pilot_capture_bundle(bundle, calibration, spec=spec)

    assert caught.value.code == "capture_not_completed"


def test_calibration_processing_module_has_no_real_audio_operation() -> None:
    source = inspect.getsource(calibration_module)

    assert "sounddevice" not in source
    assert "query_devices" not in source
    assert ".Stream(" not in source
    assert "sd.play(" not in source
    assert "sd.rec(" not in source
