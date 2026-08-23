import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.audio.pilot_capture import CancellationToken
from acoustic_ladder.audio.pilot_capture_backends import FakeFullDuplexBackend
from acoustic_ladder.ui.controller import Confirmation, ExperimentWizardController, WizardState
from acoustic_ladder.ui.plans import load_wizard_plans
from acoustic_ladder.ui.simulated_workflow import (
    SimulatedMeasurementRunner,
    SimulatedWorkflowError,
)

PROJECT_ROOT = Path(__file__).parents[2]


def test_processing_failure_stops_then_retry_uses_a_new_run_id(tmp_path: Path) -> None:
    calls = 0

    def backend_factory(_repeat_index: int, _condition: object) -> FakeFullDuplexBackend:
        nonlocal calls
        calls += 1
        return FakeFullDuplexBackend(
            fixed_delay_samples=1,
            linear_gain=0.0 if calls == 1 else 0.5,
        )

    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "retry-processing"
    controller = ExperimentWizardController(
        plan=plan,
        runner=SimulatedMeasurementRunner(
            project_root=PROJECT_ROOT,
            session_root=session_root,
            backend_factory=backend_factory,
            now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
        ),
        session_id="retry-processing",
        session_root=session_root,
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)

    failed = controller.run_current_condition()

    assert failed.state is WizardState.ERROR
    assert failed.completed_repeat_count == 0
    assert failed.capture_status == "完成"
    assert failed.bundle_validation_status == "通过"
    assert failed.processing_status == "失败"
    assert failed.structural_check_status == "需要重试"
    assert failed.needs_retry is True
    first_bundle = session_root / "captures" / "condition_001" / "repeat_1"
    assert first_bundle.is_dir()
    assert not (session_root / "captures" / "condition_001" / "repeat_2").exists()
    failed_bytes = {path.name: path.read_bytes() for path in first_bundle.iterdir()}
    failed_state = json.loads((session_root / "session_state.json").read_bytes())
    assert failed_state["last_failed_run_id"] == "retry-processing-c001-r1-a001"
    assert failed_state["needs_retry"] is True
    assert failed_state["successful_runs"] == []

    retried = controller.retry_current_repeat()

    assert retried.state is WizardState.WAITING_USER_ASSEMBLY
    assert retried.condition_index == 1
    assert {path.name: path.read_bytes() for path in first_bundle.iterdir()} == failed_bytes
    second_attempt = session_root / "captures" / "condition_001" / "repeat_1_attempt_002"
    assert second_attempt.is_dir()
    state = json.loads((session_root / "session_state.json").read_bytes())
    assert [entry["run_id"] for entry in state["successful_runs"]] == [
        "retry-processing-c001-r1-a002",
        "retry-processing-c001-r2-a001",
    ]
    assert state["last_failed_run_id"] == "retry-processing-c001-r1-a001"
    assert state["needs_retry"] is False


def test_calibration_hash_failure_keeps_capture_and_publishes_no_processing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "isolated-project"
    audio_target = project / "tests" / "fixtures" / "audio"
    calibration_target = project / "calibration" / "microphones" / "dayton_imm6c"
    audio_target.mkdir(parents=True)
    calibration_target.mkdir(parents=True)
    shutil.copyfile(
        PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        audio_target / "ess_offline_development.yaml",
    )
    shutil.copyfile(
        PROJECT_ROOT / "calibration/microphones/dayton_imm6c/CMM29939.txt",
        calibration_target / "CMM29939.txt",
    )
    session_root = tmp_path / "development" / "demo" / "bad-calibration"
    runner = SimulatedMeasurementRunner(
        project_root=project,
        session_root=session_root,
        now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    (calibration_target / "CMM29939.txt").write_bytes(b"tampered calibration\n")
    target = session_root / "captures" / "condition_001" / "repeat_1"

    with pytest.raises(SimulatedWorkflowError) as raised:
        runner.run_repeat(
            condition=load_wizard_plans(PROJECT_ROOT).demo_plan.conditions[0],
            repeat_index=1,
            target=target,
            run_id="bad-calibration-c001-r1-a001",
            cancellation=CancellationToken(),
        )

    assert raised.value.phase == "calibration"
    assert raised.value.code == "calibration_failed"
    assert target.is_dir()
    assert not (session_root / "processed").exists()


@pytest.mark.parametrize(
    ("backend", "message"),
    [
        (FakeFullDuplexBackend(linear_gain=20.0), "clipping"),
        (FakeFullDuplexBackend(status_flags=("underrun",)), "underrun"),
        (FakeFullDuplexBackend(status_flags=("overrun",)), "overrun"),
    ],
)
def test_structural_capture_fault_requires_retry_without_processing(
    tmp_path: Path,
    backend: FakeFullDuplexBackend,
    message: str,
) -> None:
    session_root = tmp_path / "development" / "demo" / f"structural-{message}"
    runner = SimulatedMeasurementRunner(
        project_root=PROJECT_ROOT,
        session_root=session_root,
        backend_factory=lambda _repeat, _condition: backend,
        now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    target = session_root / "captures" / "condition_001" / "repeat_1"

    with pytest.raises(SimulatedWorkflowError, match=message) as raised:
        runner.run_repeat(
            condition=load_wizard_plans(PROJECT_ROOT).demo_plan.conditions[0],
            repeat_index=1,
            target=target,
            run_id=f"structural-{message}-c001-r1-a001",
            cancellation=CancellationToken(),
        )

    assert raised.value.phase == "capture"
    assert target.is_dir()
    assert not (session_root / "processed").exists()


@pytest.mark.parametrize(
    ("cancel", "expected_state"),
    [(False, WizardState.ERROR), (True, WizardState.CANCELLED)],
)
def test_first_capture_terminal_failure_never_starts_second_repeat(
    tmp_path: Path,
    cancel: bool,
    expected_state: WizardState,
) -> None:
    session_id = "cancel-first" if cancel else "fail-first"
    session_root = tmp_path / "development" / "demo" / session_id
    backend = (
        FakeFullDuplexBackend(cancel_at_block=0)
        if cancel
        else FakeFullDuplexBackend(fail_at_block=0)
    )
    controller = ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=SimulatedMeasurementRunner(
            project_root=PROJECT_ROOT,
            session_root=session_root,
            backend_factory=lambda _repeat, _condition: backend,
            now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
        ),
        session_id=session_id,
        session_root=session_root,
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)

    snapshot = controller.run_current_condition()

    assert snapshot.state is expected_state
    assert snapshot.completed_repeat_count == 0
    assert snapshot.capture_status == ("取消" if cancel else "失败")
    assert snapshot.bundle_validation_status == "失败"
    assert snapshot.structural_check_status == "需要重试"
    assert snapshot.needs_retry is True
    assert not (session_root / "captures" / "condition_001" / "repeat_2").exists()
    state = json.loads((session_root / "session_state.json").read_bytes())
    assert state["successful_runs"] == []
    assert state["needs_retry"] is True


def test_second_capture_failure_keeps_first_processing_and_does_not_advance(
    tmp_path: Path,
) -> None:
    calls = 0

    def backend_factory(_repeat: int, _condition: object) -> FakeFullDuplexBackend:
        nonlocal calls
        calls += 1
        return FakeFullDuplexBackend(fail_at_block=0 if calls == 2 else None)

    session_root = tmp_path / "development" / "demo" / "fail-second"
    controller = ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=SimulatedMeasurementRunner(
            project_root=PROJECT_ROOT,
            session_root=session_root,
            backend_factory=backend_factory,
            now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
        ),
        session_id="fail-second",
        session_root=session_root,
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)

    snapshot = controller.run_current_condition()

    assert snapshot.state is WizardState.ERROR
    assert snapshot.condition_index == 0
    assert snapshot.completed_repeat_count == 1
    state = json.loads((session_root / "session_state.json").read_bytes())
    assert [entry["run_id"] for entry in state["successful_runs"]] == ["fail-second-c001-r1-a001"]
    assert state["last_failed_run_id"] == "fail-second-c001-r2-a001"


def test_processing_persistence_collision_does_not_complete_repeat(tmp_path: Path) -> None:
    session_root = tmp_path / "development" / "demo" / "persistence-failure"
    controller = ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=SimulatedMeasurementRunner(
            project_root=PROJECT_ROOT,
            session_root=session_root,
            now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
        ),
        session_id="persistence-failure",
        session_root=session_root,
    )
    collision = (
        session_root
        / "processed"
        / "run_persistence-failure-c001-r1-a001"
        / "processing_calibrated"
    )
    collision.mkdir(parents=True)
    marker = collision / "preserve.txt"
    marker.write_text("existing", encoding="utf-8")
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)

    snapshot = controller.run_current_condition()

    assert snapshot.state is WizardState.ERROR
    assert snapshot.completed_repeat_count == 0
    assert "persistence" in snapshot.error_message
    assert marker.read_text(encoding="utf-8") == "existing"
    state = json.loads((session_root / "session_state.json").read_bytes())
    assert state["successful_runs"] == []
    assert state["needs_retry"] is True
