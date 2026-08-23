import json
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


def test_completed_condition_progress_recovers_without_repeating_it(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    runner = FakeDemoCaptureRunner(np.ones((1, 8), dtype=np.float32))
    session_root = tmp_path / "development" / "demo" / "recover-demo"
    original = ExperimentWizardController(
        plan=plan,
        runner=runner,
        session_id="recover-demo",
        session_root=session_root,
    )
    for confirmation in Confirmation:
        original.set_confirmation(confirmation, True)
    assert original.run_current_condition().condition_index == 1

    recovered = ExperimentWizardController.recover(
        plan=plan,
        runner=runner,
        session_id="recover-demo",
        session_root=session_root,
    )

    snapshot = recovered.snapshot()
    assert snapshot.state is WizardState.WAITING_USER_ASSEMBLY
    assert snapshot.condition_index == 1
    assert snapshot.completed_repeat_count == 0
    assert not any(snapshot.confirmations.values())
    state = json.loads((session_root / "session_state.json").read_bytes())
    assert state["schema_version"] == "1.0.0"
    assert state["mode"] == "development_demo"
    assert state["completed_conditions"] == [plan.conditions[0].condition_id]
