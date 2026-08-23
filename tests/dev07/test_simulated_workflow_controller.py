import json
from datetime import UTC, datetime
from pathlib import Path

from acoustic_ladder.ui.controller import Confirmation, ExperimentWizardController, WizardState
from acoustic_ladder.ui.plans import load_wizard_plans
from acoustic_ladder.ui.simulated_workflow import (
    SimulatedMeasurementRunner,
    validate_simulated_repeat_evidence,
)

PROJECT_ROOT = Path(__file__).parents[2]


def _confirm(controller: ExperimentWizardController) -> None:
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)


def test_controller_runs_two_processed_repeats_before_advancing(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "controller-demo"
    runner = SimulatedMeasurementRunner(
        project_root=PROJECT_ROOT,
        session_root=session_root,
        now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    controller = ExperimentWizardController(
        plan=plan,
        runner=runner,
        session_id="controller-demo",
        session_root=session_root,
    )
    _confirm(controller)

    snapshot = controller.run_current_condition()

    assert snapshot.state is WizardState.WAITING_USER_ASSEMBLY
    assert snapshot.condition_index == 1
    for repeat in (1, 2):
        run_id = f"controller-demo-c001-r{repeat}-a001"
        receipt = (
            session_root
            / "processed"
            / f"run_{run_id}"
            / "processing_calibrated"
            / "processing_receipt.json"
        )
        assert receipt.is_file()


def test_three_condition_demo_records_six_unique_replayable_runs(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "six-sweeps"
    runner = SimulatedMeasurementRunner(
        project_root=PROJECT_ROOT,
        session_root=session_root,
        now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    controller = ExperimentWizardController(
        plan=plan,
        runner=runner,
        session_id="six-sweeps",
        session_root=session_root,
    )

    for _condition in plan.conditions:
        _confirm(controller)
        snapshot = controller.run_current_condition()

    assert snapshot.state is WizardState.ALL_COMPLETE
    state = json.loads((session_root / "session_state.json").read_bytes())
    successful = state["successful_runs"]
    assert len(successful) == 6
    assert len({entry["run_id"] for entry in successful}) == 6
    assert [(entry["condition_index"], entry["repeat_index"]) for entry in successful] == [
        (0, 1),
        (0, 2),
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
    ]
    for entry in successful:
        bundle = session_root / entry["bundle_relative_path"]
        processing = session_root / entry["processing_relative_path"]
        result = validate_simulated_repeat_evidence(
            bundle,
            processing,
            project_root=PROJECT_ROOT,
            expected_run_id=entry["run_id"],
        )
        assert (
            result.processing_receipt_path.relative_to(session_root).as_posix()
            == entry["processing_receipt_relative_path"]
        )
    assert state["last_failed_run_id"] is None
    assert state["needs_retry"] is False
