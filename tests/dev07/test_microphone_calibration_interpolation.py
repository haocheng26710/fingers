from pathlib import Path

import numpy as np

from acoustic_ladder.audio.microphone_calibration import (
    interpolate_calibration,
    load_dayton_calibration,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = PROJECT_ROOT / "calibration" / "microphones" / "dayton_imm6c" / "CMM29939.txt"
CALIBRATION_SHA256 = "421070ec6d41c1b92cb69f0f5e4e290f9644847d92d52590994a80ea9e17a11e"


def test_log_frequency_interpolation_is_exact_and_does_not_extrapolate() -> None:
    calibration = load_dayton_calibration(CALIBRATION_PATH, expected_sha256=CALIBRATION_SHA256)
    lower_index = 100
    midpoint = float(
        np.sqrt(calibration.frequency_hz[lower_index] * calibration.frequency_hz[lower_index + 1])
    )
    targets = np.array(
        [
            calibration.frequency_hz[lower_index],
            midpoint,
            calibration.frequency_min_hz - 0.01,
            calibration.frequency_max_hz + 0.01,
        ]
    )

    correction, valid = interpolate_calibration(calibration, targets)

    np.testing.assert_allclose(
        correction[:2],
        [
            calibration.correction_db[lower_index],
            (calibration.correction_db[lower_index] + calibration.correction_db[lower_index + 1])
            / 2,
        ],
        rtol=0.0,
        atol=1e-12,
    )
    assert np.array_equal(valid, [True, True, False, False])
    assert np.array_equal(correction[2:], [0.0, 0.0])
