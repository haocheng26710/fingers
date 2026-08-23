import hashlib
from pathlib import Path

import pytest

from acoustic_ladder.audio.microphone_calibration import (
    MicrophoneCalibrationError,
    load_dayton_calibration,
)


def test_invalid_utf8_reports_the_actual_source_line(tmp_path: Path) -> None:
    path = tmp_path / "invalid-encoding.txt"
    payload = b"*1000Hz\t-36.2\n20.0\t\xff\n8000.0\t0.0\n"
    path.write_bytes(payload)

    with pytest.raises(MicrophoneCalibrationError) as caught:
        load_dayton_calibration(path, expected_sha256=hashlib.sha256(payload).hexdigest())

    assert caught.value.path == path
    assert caught.value.line_number == 2
    assert caught.value.code == "encoding"
