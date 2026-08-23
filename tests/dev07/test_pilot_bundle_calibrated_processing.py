from datetime import UTC, datetime
from pathlib import Path

from acoustic_ladder.audio.ess import generate_ess, spec_from_audio_config
from acoustic_ladder.audio.microphone_calibration import (
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


def test_synthetic_pilot_bundle_produces_raw_and_calibrated_processing(tmp_path: Path) -> None:
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
                run_id="calibration-fixture",
                output_samples=generated.samples,
                block_size_frames=256,
                started_at_utc=datetime(2026, 8, 23, tzinfo=UTC),
            ),
            tmp_path / "capture",
            FakeFullDuplexBackend(fixed_delay_samples=1, linear_gain=0.5),
        )
        .bundle_path
    )
    before = {path.name: path.read_bytes() for path in bundle.iterdir()}
    timing = generated.timing
    calibration = load_dayton_calibration(CALIBRATION_PATH, expected_sha256=CALIBRATION_SHA256)

    result = process_pilot_capture_bundle(
        bundle,
        calibration,
        spec=PilotBundleProcessingSpec(
            sample_rate_hz=48_000,
            sweep_sample_count=timing.sweep_sample_count,
            pre_silence_sample_count=timing.pre_silence_sample_count,
            start_frequency_hz=excitation.start_frequency_hz,
            end_frequency_hz=excitation.end_frequency_hz,
            analysis_lower_hz=500.0,
            analysis_upper_hz=8_000.0,
        ),
    )

    assert "transfer_raw_real" in result.uncalibrated.arrays
    assert "transfer_raw_calibrated_real" in result.calibrated_arrays
    assert (
        result.receipt.microphone_calibration_applied,
        result.receipt.calibration_filename,
        result.receipt.calibration_sha256,
        result.receipt.calibration_point_count,
        result.receipt.calibration_frequency_min_hz,
        result.receipt.calibration_frequency_max_hz,
        result.receipt.calibration_interpolation,
        result.receipt.calibration_sign_convention,
        result.receipt.phase_calibrated,
        result.receipt.absolute_spl_calibrated,
    ) == (
        True,
        "CMM29939.txt",
        CALIBRATION_SHA256,
        256,
        20.0,
        20_000.0,
        "linear_in_log10_frequency",
        "add_correction_db_to_measured_magnitude_db",
        False,
        False,
    )
    assert {path.name: path.read_bytes() for path in bundle.iterdir()} == before
