import hashlib
from pathlib import Path

import pytest

from acoustic_ladder.audio.microphone_calibration import (
    MicrophoneCalibrationError,
    load_dayton_calibration,
)


@pytest.mark.parametrize(
    ("payload", "code", "line_number"),
    [
        (b"not-a-header\n20 0\n8000 0\n", "malformed_header", 1),
        (b"*1000Hz -36.2\n20 0 extra\n8000 0\n", "column_count", 2),
        (b"*1000Hz -36.2\n20 0\n20 0\n8000 0\n", "duplicate_frequency", 3),
        (b"*1000Hz -36.2\n20 0\n19 0\n8000 0\n", "non_increasing_frequency", 3),
        (b"*1000Hz -36.2\nnan 0\n8000 0\n", "non_finite", 2),
        (b"*1000Hz -36.2\n20 inf\n8000 0\n", "non_finite", 2),
        (b"*1000Hz -36.2\n0 0\n8000 0\n", "non_positive_frequency", 2),
        (b"*1000Hz -36.2\n", "missing_data", 1),
        (b"*1000Hz -36.2\n600 0\n8000 0\n", "analysis_band_not_covered", None),
        (b"*1000Hz nope\n20 0\n8000 0\n", "invalid_float", 1),
        (b"*1000Hz nan\n20 0\n8000 0\n", "non_finite", 1),
    ],
)
def test_malformed_calibration_is_rejected_with_location(
    tmp_path: Path, payload: bytes, code: str, line_number: int | None
) -> None:
    path = tmp_path / "malformed.txt"
    path.write_bytes(payload)

    with pytest.raises(MicrophoneCalibrationError) as caught:
        load_dayton_calibration(path, expected_sha256=hashlib.sha256(payload).hexdigest())

    assert caught.value.path == path
    assert caught.value.line_number == line_number
    assert caught.value.code == code


def test_calibration_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "hash-mismatch.txt"
    path.write_bytes(b"*1000Hz -36.2\n20 0\n8000 0\n")

    with pytest.raises(MicrophoneCalibrationError) as caught:
        load_dayton_calibration(path, expected_sha256="0" * 64)

    assert caught.value.code == "sha256_mismatch"
