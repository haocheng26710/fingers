from pathlib import Path

from acoustic_ladder.audio.microphone_calibration import load_dayton_calibration

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = PROJECT_ROOT / "calibration" / "microphones" / "dayton_imm6c" / "CMM29939.txt"
CALIBRATION_SHA256 = "421070ec6d41c1b92cb69f0f5e4e290f9644847d92d52590994a80ea9e17a11e"


def test_archived_imm6c_calibration_has_verified_metadata_and_range() -> None:
    calibration = load_dayton_calibration(CALIBRATION_PATH, expected_sha256=CALIBRATION_SHA256)

    assert (
        CALIBRATION_PATH.stat().st_size,
        calibration.original_filename,
        calibration.sha256,
        calibration.sensitivity_1khz_db,
        calibration.point_count,
        calibration.frequency_min_hz,
        calibration.frequency_max_hz,
        float(calibration.correction_db.min()),
        float(calibration.correction_db.max()),
        calibration.interpolation,
        calibration.sign_convention,
    ) == (
        3205,
        "CMM29939.txt",
        CALIBRATION_SHA256,
        -36.2,
        256,
        20.0,
        20_000.0,
        -0.5,
        2.2,
        "linear_in_log10_frequency",
        "add_correction_db_to_measured_magnitude_db",
    )
