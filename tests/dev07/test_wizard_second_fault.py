from pathlib import Path

import numpy as np

from acoustic_ladder.audio.pilot_capture_backends import FakeFullDuplexBackend
from acoustic_ladder.ui.controller import (
    Confirmation,
    ExperimentWizardController,
    FakeDemoCaptureRunner,
    WizardState,
)
from acoustic_ladder.ui.plans import load_wizard_plans

PROJECT_ROOT = Path(__file__).parents[2]


def test_second_repeat_failure_keeps_first_success_and_does_not_advance(
    tmp_path: Path,
) -> None:
    runner = FakeDemoCaptureRunner(
        np.ones((1, 8), dtype=np.float32),
        backend_factory=lambda repeat, _condition: FakeFullDuplexBackend(
            fail_at_block=0 if repeat == 2 else None
        ),
    )
    controller = ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=runner,
        session_id="second-fault",
        session_root=tmp_path / "development" / "demo" / "second-fault",
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)

    result = controller.run_current_condition()

    assert result.state is WizardState.ERROR
    assert result.completed_repeat_count == 1
    assert result.condition_index == 0
    first = controller.session_root / "captures" / "condition_001" / "repeat_1"
    second = controller.session_root / "captures" / "condition_001" / "repeat_2"
    assert first.is_dir()
    assert not second.exists()
