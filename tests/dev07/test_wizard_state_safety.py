import json
from pathlib import Path

import numpy as np
import pytest

from acoustic_ladder.ui.controller import (
    Confirmation,
    ExperimentWizardController,
    FakeDemoCaptureRunner,
    WizardError,
    WizardRecoveryError,
)
from acoustic_ladder.ui.plans import load_wizard_plans

PROJECT_ROOT = Path(__file__).parents[2]


def _runner() -> FakeDemoCaptureRunner:
    return FakeDemoCaptureRunner(np.ones((1, 8), dtype=np.float32))


def test_corrupted_recovery_state_is_rejected_without_overwrite(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "corrupt-demo"
    ExperimentWizardController(
        plan=plan,
        runner=_runner(),
        session_id="corrupt-demo",
        session_root=session_root,
    )
    state_path = session_root / "session_state.json"
    state_path.write_bytes(b"{not-json\n")
    original = state_path.read_bytes()

    with pytest.raises(WizardRecoveryError, match="rejected"):
        ExperimentWizardController.recover(
            plan=plan,
            runner=_runner(),
            session_id="corrupt-demo",
            session_root=session_root,
        )

    assert state_path.read_bytes() == original


def test_missing_recovery_field_is_rejected_without_overwrite(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "missing-field"
    ExperimentWizardController(
        plan=plan,
        runner=_runner(),
        session_id="missing-field",
        session_root=session_root,
    )
    state_path = session_root / "session_state.json"
    payload = json.loads(state_path.read_bytes())
    del payload["plan_sha256"]
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    original = state_path.read_bytes()

    with pytest.raises(WizardRecoveryError, match="missing fields"):
        ExperimentWizardController.recover(
            plan=plan,
            runner=_runner(),
            session_id="missing-field",
            session_root=session_root,
        )

    assert state_path.read_bytes() == original


def test_formal_or_arbitrary_roots_are_rejected_without_files(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    forbidden = tmp_path / "data" / "real" / "not-demo"

    with pytest.raises(WizardError, match="development/demo"):
        ExperimentWizardController(
            plan=plan,
            runner=_runner(),
            session_id="not-demo",
            session_root=forbidden,
        )

    assert not forbidden.exists()


def test_unsafe_session_identifier_is_rejected_without_files(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    forbidden = tmp_path / "development" / "demo" / "unsafe"

    with pytest.raises(WizardError, match="safe and identical"):
        ExperimentWizardController(
            plan=plan,
            runner=_runner(),
            session_id="../unsafe",
            session_root=forbidden,
        )

    assert not forbidden.exists()


def test_existing_demo_directory_requires_explicit_recovery(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    existing = tmp_path / "development" / "demo" / "existing-demo"
    existing.mkdir(parents=True)
    marker = existing / "operator-note.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(WizardError, match="recover it explicitly"):
        ExperimentWizardController(
            plan=plan,
            runner=_runner(),
            session_id="existing-demo",
            session_root=existing,
        )

    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not (existing / "session_state.json").exists()


def test_confirmation_state_is_persisted_at_safe_boundary(tmp_path: Path) -> None:
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    session_root = tmp_path / "development" / "demo" / "confirmed"
    controller = ExperimentWizardController(
        plan=plan,
        runner=_runner(),
        session_id="confirmed",
        session_root=session_root,
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)

    recovered = ExperimentWizardController.recover(
        plan=plan,
        runner=_runner(),
        session_id="confirmed",
        session_root=session_root,
    )

    assert recovered.snapshot().can_start
