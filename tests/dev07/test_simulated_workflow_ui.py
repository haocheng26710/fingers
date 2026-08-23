import queue
import threading
from pathlib import Path

from acoustic_ladder.ui.simulated_workflow import SimulatedMeasurementRunner
from acoustic_ladder.ui.tk_app import (
    STRUCTURAL_DISCLAIMER,
    ExperimentWizardWindow,
    create_demo_controller,
)

PROJECT_ROOT = Path(__file__).parents[2]


def test_default_ui_controller_uses_complete_fake_workflow_and_status_contract(
    tmp_path: Path,
) -> None:
    plans, controller = create_demo_controller(
        PROJECT_ROOT,
        "ui-complete",
        recover=False,
        demo_data_root=tmp_path / "development" / "demo",
    )

    snapshot = controller.snapshot()
    assert plans.demo_plan.mode == "development_demo"
    assert isinstance(controller.runner, SimulatedMeasurementRunner)
    assert snapshot.capture_status == "等待"
    assert snapshot.bundle_validation_status == "等待"
    assert snapshot.processing_status == "等待"
    assert snapshot.calibration_status == "等待"
    assert snapshot.calibration_band_status == "等待"
    assert snapshot.structural_check_status == "等待"
    assert snapshot.result_directory == "尚无结果目录"
    assert snapshot.formal_acoustic_decision is False


def test_tk_source_keeps_fake_only_disclaimer_and_has_no_real_backend_entry() -> None:
    source = (PROJECT_ROOT / "src/acoustic_ladder/ui/tk_app.py").read_text(encoding="utf-8")

    for marker in (
        "模拟演练",
        "FAKE BACKEND",
        "不会播放或录音",
        "不构成正式实验结论",
    ):
        assert marker in source
    assert "SoundDeviceFullDuplexBackend" not in source
    assert "query_devices" not in source
    assert "sounddevice" not in source


def test_background_worker_only_publishes_to_main_thread_queue() -> None:
    assert STRUCTURAL_DISCLAIMER == "当前结果仅为模拟链路结构检查\uff0c不代表正式声学 PASS/FAIL。"
    window = ExperimentWizardWindow.__new__(ExperimentWizardWindow)
    window._messages = queue.Queue()
    worker_ident: list[int] = []
    marker = object()

    def action() -> object:
        worker_ident.append(threading.get_ident())
        return marker

    worker = threading.Thread(target=window._capture_worker, args=(action,))
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert worker_ident != [threading.get_ident()]
    assert window._messages.get_nowait() == ("snapshot", marker)
    assert window._messages.empty()
