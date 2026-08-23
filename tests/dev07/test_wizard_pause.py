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


def _controller(tmp_path: Path) -> ExperimentWizardController:
    return ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=FakeDemoCaptureRunner(np.ones((1, 8), dtype=np.float32)),
        session_id="pause-demo",
        session_root=tmp_path / "development" / "demo" / "pause-demo",
    )


def test_pause_and_resume_restore_only_an_allowed_condition_boundary(tmp_path: Path) -> None:
    controller = _controller(tmp_path)

    assert controller.request_pause().state is WizardState.PAUSED
    assert controller.resume().state is WizardState.WAITING_USER_ASSEMBLY

    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)
    assert controller.request_pause().state is WizardState.PAUSED
    resumed = controller.resume()
    assert resumed.state is WizardState.READY
    assert resumed.can_start is True
