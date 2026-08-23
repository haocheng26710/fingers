from pathlib import Path

import numpy as np

from acoustic_ladder.ui.controller import (
    Confirmation,
    ExperimentWizardController,
    FakeDemoCaptureRunner,
    WizardState,
)
from acoustic_ladder.ui.plans import load_wizard_plans

PROJECT_ROOT = Path(__file__).parents[2]


def _ready_controller(tmp_path: Path) -> ExperimentWizardController:
    controller = ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=FakeDemoCaptureRunner(np.ones((1, 8), dtype=np.float32)),
        session_id="demo-session",
        session_root=tmp_path / "development" / "demo" / "demo-session",
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)
    return controller


def test_condition_runs_two_fake_captures_then_advances_and_resets_confirmations(
    tmp_path: Path,
) -> None:
    controller = _ready_controller(tmp_path)
    first_condition = controller.snapshot().condition.condition_id

    result = controller.run_current_condition()

    assert result.state is WizardState.WAITING_USER_ASSEMBLY
    assert result.condition_index == 1
    assert result.condition.condition_id != first_condition
    assert result.completed_repeat_count == 0
    assert not any(result.confirmations.values())
    assert result.can_start is False
    for repeat in (1, 2):
        bundle = controller.session_root / "captures" / "condition_001" / f"repeat_{repeat}"
        assert {path.name for path in bundle.iterdir()} == {
            "captured_input.wav",
            "output_reference.wav",
            "run.json",
            "qc.json",
        }
