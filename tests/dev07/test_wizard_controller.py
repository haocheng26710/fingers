from pathlib import Path

import numpy as np
import pytest

from acoustic_ladder.ui.controller import (
    Confirmation,
    ExperimentWizardController,
    FakeDemoCaptureRunner,
    WizardError,
    WizardState,
)
from acoustic_ladder.ui.plans import load_wizard_plans

PROJECT_ROOT = Path(__file__).parents[2]


def _controller(tmp_path: Path) -> ExperimentWizardController:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    runner = FakeDemoCaptureRunner(np.ones((1, 8), dtype=np.float32))
    return ExperimentWizardController(
        plan=plan,
        runner=runner,
        session_id="demo-session",
        session_root=tmp_path / "development" / "demo" / "demo-session",
    )


def test_three_confirmations_are_required_before_condition_can_start(tmp_path: Path) -> None:
    controller = _controller(tmp_path)

    initial = controller.snapshot()
    assert initial.state is WizardState.WAITING_USER_ASSEMBLY
    assert initial.confirmations == {
        Confirmation.ASSEMBLY_COMPLETE: False,
        Confirmation.HEADPHONES_OFF: False,
        Confirmation.PLACEMENT_CORRECT: False,
    }
    assert initial.can_start is False
    with pytest.raises(WizardError, match="not ready"):
        controller.run_current_condition()

    controller.set_confirmation(Confirmation.ASSEMBLY_COMPLETE, True)
    controller.set_confirmation(Confirmation.HEADPHONES_OFF, True)
    assert controller.snapshot().can_start is False

    controller.set_confirmation(Confirmation.PLACEMENT_CORRECT, True)
    ready = controller.snapshot()
    assert ready.state is WizardState.READY
    assert ready.can_start is True
