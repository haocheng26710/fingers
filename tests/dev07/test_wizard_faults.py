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


def _ready_with_fault(tmp_path: Path, *, failed_repeat: int) -> ExperimentWizardController:
    runner = FakeDemoCaptureRunner(
        np.ones((1, 8), dtype=np.float32),
        backend_factory=lambda repeat, _condition: FakeFullDuplexBackend(
            fail_at_block=0 if repeat == failed_repeat else None
        ),
    )
    controller = ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=runner,
        session_id="fault-demo",
        session_root=tmp_path / "development" / "demo" / "fault-demo",
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)
    return controller


def test_first_repeat_failure_stops_condition_without_second_capture(tmp_path: Path) -> None:
    controller = _ready_with_fault(tmp_path, failed_repeat=1)

    result = controller.run_current_condition()

    assert result.state is WizardState.ERROR
    assert result.completed_repeat_count == 0
    assert result.condition_index == 0
    assert "injected fake backend failure" in result.error_message
    assert not (controller.session_root / "captures" / "condition_001" / "repeat_2").exists()
