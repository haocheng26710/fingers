import importlib
from pathlib import Path

import pytest

from acoustic_ladder.ui.controller import WizardState
from acoustic_ladder.ui.tk_app import (
    FAKE_MODE_WARNING,
    MODULE_DESCRIPTIONS,
    STATE_TEXT,
    create_demo_controller,
)

PROJECT_ROOT = Path(__file__).parents[2]


def test_ui_factory_builds_only_a_fake_demo_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_import = importlib.import_module
    imported: list[str] = []

    def guarded_import(name: str, package: str | None = None) -> object:
        imported.append(name)
        if name == "sounddevice":
            raise AssertionError("UI must not import a real audio backend")
        return original_import(name, package)

    monkeypatch.setattr(importlib, "import_module", guarded_import)
    plans, controller = create_demo_controller(
        PROJECT_ROOT,
        "factory-demo",
        recover=False,
        demo_data_root=tmp_path / "development" / "demo",
    )

    assert plans.demo_plan.mode == "development_demo"
    assert controller.runner.backend_type == "fake_full_duplex"
    assert controller.session_root == (tmp_path / "development" / "demo" / "factory-demo").resolve()
    assert "sounddevice" not in imported


def test_visible_ui_copy_distinguishes_user_and_program_roles() -> None:
    source = (PROJECT_ROOT / "src/acoustic_ladder/ui/tk_app.py").read_text(encoding="utf-8")

    assert FAKE_MODE_WARNING == "当前未连接真实硬件\uff0c不会播放或录音"
    assert "[用户操作]" in source
    assert "[程序执行]" in source
    assert set(MODULE_DESCRIPTIONS) == {"BLK", "B28", "B32", "B40"}
    assert set(STATE_TEXT) == set(WizardState)


def test_ui_source_has_no_real_audio_backend_operation() -> None:
    source = (PROJECT_ROOT / "src/acoustic_ladder/ui/tk_app.py").read_text(encoding="utf-8")

    assert "SoundDeviceFullDuplexBackend" not in source
    assert "query_devices" not in source
    assert ".Stream(" not in source
    assert "sd.play(" not in source
    assert "sd.rec(" not in source


def test_module_entry_delegates_to_tk_app() -> None:
    source = (PROJECT_ROOT / "src/acoustic_ladder/ui/__main__.py").read_text(encoding="utf-8")

    assert "from acoustic_ladder.ui.tk_app import main" in source
    assert "SystemExit(main())" in source
