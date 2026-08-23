import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.ui.controller import (
    Confirmation,
    ExperimentWizardController,
    WizardRecoveryError,
    WizardState,
)
from acoustic_ladder.ui.plans import load_wizard_plans
from acoustic_ladder.ui.simulated_workflow import SimulatedMeasurementRunner

PROJECT_ROOT = Path(__file__).parents[2]


def _runner(session_root: Path) -> SimulatedMeasurementRunner:
    return SimulatedMeasurementRunner(
        project_root=PROJECT_ROOT,
        session_root=session_root,
        now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )


def test_recovery_validates_processing_evidence_and_does_not_repeat_successes(
    tmp_path: Path,
) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "recover-processed"
    original = ExperimentWizardController(
        plan=plan,
        runner=_runner(session_root),
        session_id="recover-processed",
        session_root=session_root,
    )
    for confirmation in Confirmation:
        original.set_confirmation(confirmation, True)
    assert original.run_current_condition().condition_index == 1
    state_before = json.loads((session_root / "session_state.json").read_bytes())
    capture_paths_before = sorted(
        path.relative_to(session_root).as_posix()
        for path in (session_root / "captures").rglob("run.json")
    )

    recovered = ExperimentWizardController.recover(
        plan=plan,
        runner=_runner(session_root),
        session_id="recover-processed",
        session_root=session_root,
    )

    snapshot = recovered.snapshot()
    assert snapshot.state is WizardState.WAITING_USER_ASSEMBLY
    assert snapshot.condition_index == 1
    assert recovered.successful_run_ids == tuple(
        entry["run_id"] for entry in state_before["successful_runs"]
    )
    assert snapshot.capture_status == "完成"
    assert snapshot.structural_check_status == "通过"
    assert snapshot.formal_acoustic_decision is False
    assert snapshot.result_directory.endswith("processing_calibrated")
    assert (
        sorted(
            path.relative_to(session_root).as_posix()
            for path in (session_root / "captures").rglob("run.json")
        )
        == capture_paths_before
    )


def test_recovery_rejects_missing_processing_receipt_without_overwriting_state(
    tmp_path: Path,
) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "missing-receipt"
    original = ExperimentWizardController(
        plan=plan,
        runner=_runner(session_root),
        session_id="missing-receipt",
        session_root=session_root,
    )
    for confirmation in Confirmation:
        original.set_confirmation(confirmation, True)
    original.run_current_condition()
    state_path = session_root / "session_state.json"
    state_before = state_path.read_bytes()
    state = json.loads(state_before)
    receipt = session_root / state["successful_runs"][0]["processing_receipt_relative_path"]
    receipt.unlink()

    with pytest.raises(WizardRecoveryError, match="saved demo state was rejected"):
        ExperimentWizardController.recover(
            plan=plan,
            runner=_runner(session_root),
            session_id="missing-receipt",
            session_root=session_root,
        )


def test_recovery_marks_interrupted_attempt_for_retry_and_uses_fresh_identity(
    tmp_path: Path,
) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "interrupted"
    original = ExperimentWizardController(
        plan=plan,
        runner=_runner(session_root),
        session_id="interrupted",
        session_root=session_root,
    )
    for confirmation in Confirmation:
        original.set_confirmation(confirmation, True)
    state_path = session_root / "session_state.json"
    interrupted = json.loads(state_path.read_bytes())
    interrupted["attempt_counts"] = {"0:1": 1}
    state_path.write_text(json.dumps(interrupted), encoding="utf-8")

    recovered = ExperimentWizardController.recover(
        plan=plan,
        runner=_runner(session_root),
        session_id="interrupted",
        session_root=session_root,
    )

    pending = recovered.snapshot()
    assert pending.state is WizardState.READY
    assert pending.needs_retry is True
    assert pending.structural_check_status == "需要重试"
    assert "未完成" in pending.error_message

    completed = recovered.retry_current_repeat()

    assert completed.condition_index == 1
    assert recovered.successful_run_ids == (
        "interrupted-c001-r1-a002",
        "interrupted-c001-r2-a001",
    )
