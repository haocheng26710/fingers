from pathlib import Path
from threading import Event, Thread

import numpy as np

from acoustic_ladder.audio.pilot_capture import (
    BackendCapture,
    CancellationToken,
    PilotCaptureRequest,
)
from acoustic_ladder.audio.pilot_capture_backends import FakeFullDuplexBackend
from acoustic_ladder.ui.controller import (
    Confirmation,
    ExperimentWizardController,
    FakeDemoCaptureRunner,
    WizardSnapshot,
    WizardState,
)
from acoustic_ladder.ui.plans import load_wizard_plans

PROJECT_ROOT = Path(__file__).parents[2]


class _CancellationAwareFakeBackend(FakeFullDuplexBackend):
    def __init__(self, started: Event, release: Event, observed: Event) -> None:
        super().__init__()
        self.started = started
        self.release = release
        self.observed = observed

    def capture(
        self, request: PilotCaptureRequest, cancellation: CancellationToken
    ) -> BackendCapture:
        self.started.set()
        if not self.release.wait(5):
            raise RuntimeError("test fake backend release timed out")
        if cancellation.cancelled:
            self.observed.set()
        return super().capture(request, cancellation)


def test_emergency_stop_cancels_active_fake_capture_without_success(tmp_path: Path) -> None:
    started = Event()
    release = Event()
    observed = Event()
    backend = _CancellationAwareFakeBackend(started, release, observed)
    plan = load_wizard_plans(PROJECT_ROOT).demo_plan
    controller = ExperimentWizardController(
        plan=plan,
        runner=FakeDemoCaptureRunner(
            np.ones((1, 8), dtype=np.float32),
            backend_factory=lambda _repeat, _condition: backend,
        ),
        session_id="cancel-demo",
        session_root=tmp_path / "development" / "demo" / "cancel-demo",
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)
    results: list[WizardSnapshot] = []
    worker = Thread(target=lambda: results.append(controller.run_current_condition()))
    worker.start()
    assert started.wait(5)

    during = controller.emergency_stop()
    assert during.state is WizardState.RUNNING_REPEAT_1
    release.set()
    worker.join(5)

    assert observed.is_set()
    assert results[0].state is WizardState.CANCELLED
    assert results[0].completed_repeat_count == 0
    assert not (controller.session_root / "captures" / "condition_001" / "repeat_1").exists()

    recovered = ExperimentWizardController.recover(
        plan=plan,
        runner=FakeDemoCaptureRunner(np.ones((1, 8), dtype=np.float32)),
        session_id="cancel-demo",
        session_root=controller.session_root,
    )

    assert recovered.snapshot().state is WizardState.READY
    assert recovered.snapshot().can_start
