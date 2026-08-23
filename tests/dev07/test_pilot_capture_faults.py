from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from acoustic_ladder.audio.pilot_capture import (
    CaptureState,
    PilotCaptureEngine,
    PilotCaptureError,
    PilotCaptureRequest,
)
from acoustic_ladder.audio.pilot_capture_backends import FakeFullDuplexBackend


def test_fake_input_shortage_is_failed_and_never_published(tmp_path: Path) -> None:
    request = PilotCaptureRequest(
        run_id="short-input",
        output_samples=np.ones((1, 6), dtype=np.float32),
        block_size_frames=2,
        started_at_utc=datetime(2026, 8, 23, tzinfo=UTC),
    )
    engine = PilotCaptureEngine()

    with pytest.raises(PilotCaptureError, match="exact length") as caught:
        engine.capture(
            request,
            tmp_path / "short-input",
            FakeFullDuplexBackend(short_input_at_block=1),
        )

    assert caught.value.state is CaptureState.FAILED
    assert engine.state is CaptureState.FAILED
    assert not (tmp_path / "short-input").exists()
