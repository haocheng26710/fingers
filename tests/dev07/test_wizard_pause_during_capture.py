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


class _BlockingFakeBackend(FakeFullDuplexBackend):
    def __init__(self, started: Event, release: Event) -> None:
        super().__init__()
        self.started = started
        self.release = release

    def capture(
        self, request: PilotCaptureRequest, cancellation: CancellationToken
    ) -> BackendCapture:
        self.started.set()
        if not self.release.wait(5):
            raise RuntimeError("test fake backend release timed out")
        return super().capture(request, cancellation)


def test_pause_during_capture_is_deferred_until_between_repeats(tmp_path: Path) -> None:
    started = Event()
    release = Event()
    runner = FakeDemoCaptureRunner(
        np.ones((1, 8), dtype=np.float32),
        backend_factory=lambda repeat, _condition: (
            _BlockingFakeBackend(started, release) if repeat == 1 else FakeFullDuplexBackend()
        ),
    )
    controller = ExperimentWizardController(
        plan=load_wizard_plans(PROJECT_ROOT).demo_plan,
        runner=runner,
        session_id="deferred-pause",
        session_root=tmp_path / "development" / "demo" / "deferred-pause",
    )
    for confirmation in Confirmation:
        controller.set_confirmation(confirmation, True)
    results: list[WizardSnapshot] = []
    worker = Thread(target=lambda: results.append(controller.run_current_condition()))
    worker.start()
    assert started.wait(5)

    during = controller.request_pause()
    assert during.state is WizardState.RUNNING_REPEAT_1
    release.set()
    worker.join(5)

    assert not worker.is_alive()
    assert results[0].state is WizardState.PAUSED
    assert results[0].completed_repeat_count == 1
    assert not (controller.session_root / "captures" / "condition_001" / "repeat_2").exists()

    assert controller.resume().state is WizardState.BETWEEN_REPEATS
    completed = controller.run_current_condition()
    assert completed.state is WizardState.WAITING_USER_ASSEMBLY
    assert completed.condition_index == 1
