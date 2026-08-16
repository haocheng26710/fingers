from __future__ import annotations

import ast
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder import cli
from acoustic_ladder.audio import preflight as preflight_module
from acoustic_ladder.audio.backend import FakeInventoryBackend
from acoustic_ladder.audio.inventory import collect_inventory
from acoustic_ladder.audio.models import (
    AudioInventoryCaptureContext,
    AudioInventorySnapshot,
    ContextualAudioPreflightReport,
    HardwareSetupRecord,
)
from acoustic_ladder.audio.persistence import (
    load_audio_artifact,
    persist_audio_artifact,
    persist_bytes_with_sidecar,
    verify_bytes_sidecar,
)
from acoustic_ladder.audio.preflight import build_contextual_preflight_report
from acoustic_ladder.audio.summary import render_inventory_summary
from acoustic_ladder.config.schema import GENERATED_SCHEMA_MODELS, check_schemas
from tests.conftest import REPO_ROOT

INVENTORY = REPO_ROOT / "reference/audio/inventory/DEV-03.01_audio_inventory.json"
INVENTORY_SIDECAR = REPO_ROOT / "reference/audio/inventory/DEV-03.01_audio_inventory.sha256"
HARDWARE = REPO_ROOT / "reference/audio/hardware_setup.provisional.json"
REPORT = REPO_ROOT / "docs/reports/DEV-03.01.md"
CONTEXT = REPO_ROOT / "reference/audio/inventory/DEV-03.02_inventory_capture_context.json"
CONTEXT_SIDECAR = REPO_ROOT / (
    "reference/audio/inventory/DEV-03.02_inventory_capture_context.sha256"
)
INVENTORY_SHA256 = "8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2"
NOW = datetime(2026, 8, 16, 18, 30, tzinfo=UTC)


def _snapshot() -> AudioInventorySnapshot:
    snapshot, digest = load_audio_artifact(INVENTORY, INVENTORY_SIDECAR, AudioInventorySnapshot)
    assert digest == INVENTORY_SHA256
    return snapshot


def _context() -> AudioInventoryCaptureContext:
    return AudioInventoryCaptureContext(
        schema_version="1.0.0",
        context_id="DEV-03.02-inventory-capture-context",
        inventory_reference="reference/audio/inventory/DEV-03.01_audio_inventory.json",
        inventory_sha256=INVENTORY_SHA256,
        context_recorded_at=NOW,
        context_source="operator_fact_correction_after_DEV-03.01",
        experimental_input_hardware_connected=False,
        experimental_output_hardware_connected=False,
        experimental_fixture_connected=False,
        inventory_role="development_host_baseline_without_experimental_hardware",
        candidate_binding_status="deferred_until_hardware_connection",
        existing_endpoint_interpretation="not_experimental_hardware",
        hardware_ready=False,
        full_duplex_verified=False,
        shared_clock_verified=False,
        channel_mapping_verified=False,
        calibration_file_verified=False,
        absolute_spl_calibrated=False,
        notes=["Operator fact correction recorded after DEV-03.01."],
    )


def _contextual_report(
    fake_backend: FakeInventoryBackend | None = None,
) -> ContextualAudioPreflightReport:
    snapshot = collect_inventory(fake_backend, now=NOW) if fake_backend else _snapshot()
    hardware = HardwareSetupRecord.model_validate_json(HARDWARE.read_bytes())
    return build_contextual_preflight_report(
        snapshot,
        hardware,
        _context(),
        inventory_reference="reference/audio/inventory/DEV-03.01_audio_inventory.json",
        inventory_sha256=INVENTORY_SHA256,
        capture_context_reference=(
            "reference/audio/inventory/DEV-03.02_inventory_capture_context.json"
        ),
        capture_context_sha256="2" * 64,
        hardware_setup_reference="reference/audio/hardware_setup.provisional.json",
        hardware_setup_sha256=hashlib.sha256(HARDWARE.read_bytes()).hexdigest(),
        now=NOW,
    )


def test_authoritative_inventory_has_no_replacement_character() -> None:
    assert "\ufffd" not in INVENTORY.read_text(encoding="utf-8")
    assert all("\ufffd" not in device.name for device in _snapshot().devices)


def test_authoritative_inventory_preserves_known_chinese_names() -> None:
    names = {device.name for device in _snapshot().devices}
    assert "Microsoft 声音映射器 - Input" in names
    assert "阵列麦克风 (AMD Audio Device)" in names
    assert "耳机 (Senary Audio)" in names
    assert "扬声器 (Senary Audio)" in names
    assert "麦克风 (Senary Audio capture)" in names


def test_summary_is_rendered_from_inventory_model() -> None:
    rendered = render_inventory_summary(
        _snapshot(),
        inventory_reference="reference/audio/inventory/DEV-03.01_audio_inventory.json",
        inventory_sha256=INVENTORY_SHA256,
    ).decode("utf-8")
    assert "Device names below come directly from the verified inventory model." in rendered


def test_summary_has_no_replacement_character() -> None:
    rendered = render_inventory_summary(
        _snapshot(),
        inventory_reference="reference/audio/inventory/DEV-03.01_audio_inventory.json",
        inventory_sha256=INVENTORY_SHA256,
    ).decode("utf-8")
    assert "\ufffd" not in rendered


def test_summary_contains_every_inventory_index_and_name() -> None:
    snapshot = _snapshot()
    rendered = render_inventory_summary(
        snapshot,
        inventory_reference="reference/audio/inventory/DEV-03.01_audio_inventory.json",
        inventory_sha256=INVENTORY_SHA256,
    ).decode("utf-8")
    for device in snapshot.devices:
        assert f"| {device.snapshot_device_index} |" in rendered
        escaped_name = (
            device.name.replace("\\", "\\\\")
            .replace("|", "\\|")
            .replace("\r\n", "<br>")
            .replace("\r", "<br>")
            .replace("\n", "<br>")
        )
        assert escaped_name in rendered


def test_markdown_device_name_is_safely_escaped() -> None:
    snapshot = _snapshot()
    changed_device = snapshot.devices[0].model_copy(update={"name": "a|b\\c\r\nd"})
    changed = snapshot.model_copy(update={"devices": [changed_device, *snapshot.devices[1:]]})
    rendered = render_inventory_summary(
        changed,
        inventory_reference="reference/audio/inventory/test.json",
        inventory_sha256="1" * 64,
    ).decode("utf-8")
    assert "a\\|b\\\\c<br>d" in rendered


def test_ascii_audio_list_output_is_ascii_only_and_marked(
    fake_backend: FakeInventoryBackend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_audio_backend", lambda: fake_backend)
    cli.main(["audio-list"])
    output = capsys.readouterr().out
    output.encode("ascii")
    assert "DEVICE_NAME_ENCODING=JSON_ASCII_ESCAPED" in output
    assert "NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED" in output


def test_ascii_audio_list_name_is_json_reversible(
    fake_backend: FakeInventoryBackend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_audio_backend", lambda: fake_backend)
    expected = collect_inventory(fake_backend, now=NOW).devices[0].name
    cli.main(["audio-list"])
    line = next(
        line for line in capsys.readouterr().out.splitlines() if line.startswith("DEVICE 0:")
    )
    encoded_name = line.split(": ", 1)[1].rsplit(" [host_api=", 1)[0]
    assert json.loads(encoded_name) == expected


def test_production_code_does_not_use_lossy_replace_decoding() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "src/acoustic_ladder").rglob("*.py")
    )
    assert 'errors="replace"' not in source
    assert "errors='replace'" not in source


def test_disconnected_context_has_three_false_connection_flags() -> None:
    context = _context()
    assert context.experimental_input_hardware_connected is False
    assert context.experimental_output_hardware_connected is False
    assert context.experimental_fixture_connected is False


def test_disconnected_context_skips_candidate_name_matching(
    fake_backend: FakeInventoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_match(*values: object, **keywords: object) -> list[int]:
        del values, keywords
        raise AssertionError("candidate matching must not run")

    monkeypatch.setattr(preflight_module, "_candidate_indices", forbidden_match)
    _contextual_report(fake_backend)


def test_contextual_preflight_has_no_candidates() -> None:
    report = _contextual_report()
    assert report.input_candidate_device_indices == []
    assert report.output_candidate_device_indices == []


def test_contextual_candidate_status_is_not_applicable() -> None:
    report = _contextual_report()
    assert report.input_candidate_status == "not_applicable_hardware_disconnected"
    assert report.output_candidate_status == "not_applicable_hardware_disconnected"


def test_contextual_binding_and_confirmation_are_deferred() -> None:
    report = _contextual_report()
    assert report.device_binding_status == "deferred_until_hardware_connection"
    assert report.operator_confirmation_status == "deferred_until_hardware_connection"


def test_contextual_readiness_fields_are_all_false() -> None:
    report = _contextual_report()
    assert report.hardware_ready is False
    assert report.full_duplex_verified is False
    assert report.shared_clock_verified is False
    assert report.channel_mapping_verified is False
    assert report.calibration_file_verified is False
    assert report.absolute_spl_calibrated is False


def test_context_and_summary_sidecars_verify(tmp_path: Path) -> None:
    context_path = tmp_path / "context.json"
    context_sidecar = tmp_path / "context.sha256"
    summary_path = tmp_path / "summary.md"
    summary_sidecar = tmp_path / "summary.sha256"
    context_digest = persist_audio_artifact(context_path, context_sidecar, _context())
    loaded, verified = load_audio_artifact(
        context_path, context_sidecar, AudioInventoryCaptureContext
    )
    rendered = render_inventory_summary(
        _snapshot(),
        inventory_reference=loaded.inventory_reference,
        inventory_sha256=loaded.inventory_sha256,
        context=loaded,
        context_reference="reference/audio/inventory/context.json",
        context_sha256=context_digest,
    )
    summary_digest = persist_bytes_with_sidecar(summary_path, summary_sidecar, rendered)
    assert verified == context_digest
    assert verify_bytes_sidecar(summary_path, summary_sidecar) == summary_digest


def test_original_inventory_and_sidecar_bytes_are_unchanged() -> None:
    assert hashlib.sha256(INVENTORY.read_bytes()).hexdigest() == INVENTORY_SHA256
    assert (
        hashlib.sha256(INVENTORY_SIDECAR.read_bytes()).hexdigest()
        == "78594f861f7ddb93c8868339737cd84718908c25fb0f3c019df53b391f33e78d"
    )


def test_corrected_dev0301_report_has_no_replacement_character() -> None:
    assert "\ufffd" not in REPORT.read_text(encoding="utf-8")


def test_corrected_dev0301_report_does_not_blame_sounddevice() -> None:
    report = REPORT.read_text(encoding="utf-8")
    assert "Replacement characters are preserved exactly as returned" not in report
    assert "sounddevice returned replacement characters" not in report.casefold()


def test_production_audio_code_calls_no_forbidden_api_after_context_change() -> None:
    forbidden = {
        "play",
        "rec",
        "playrec",
        "wait",
        "Stream",
        "RawStream",
        "InputStream",
        "OutputStream",
        "RawInputStream",
        "RawOutputStream",
    }
    called: set[str] = set()
    for source_path in (REPO_ROOT / "src/acoustic_ladder/audio").glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
    assert called.isdisjoint(forbidden)


def test_context_schemas_are_generated_from_models() -> None:
    check_schemas(REPO_ROOT / "schemas")
    assert len(GENERATED_SCHEMA_MODELS) == 13


def test_contextual_preflight_rejects_wrong_inventory_identity() -> None:
    hardware = HardwareSetupRecord.model_validate_json(HARDWARE.read_bytes())
    with pytest.raises(ValueError, match="SHA256 does not match"):
        build_contextual_preflight_report(
            _snapshot(),
            hardware,
            _context(),
            inventory_reference="reference/audio/inventory/DEV-03.01_audio_inventory.json",
            inventory_sha256="0" * 64,
            capture_context_reference="reference/audio/inventory/context.json",
            capture_context_sha256="1" * 64,
            hardware_setup_reference="reference/audio/hardware_setup.provisional.json",
            hardware_setup_sha256=hashlib.sha256(HARDWARE.read_bytes()).hexdigest(),
            now=NOW,
        )


def test_summary_uses_lf_line_endings_only() -> None:
    rendered = render_inventory_summary(
        _snapshot(),
        inventory_reference="reference/audio/inventory/DEV-03.01_audio_inventory.json",
        inventory_sha256=INVENTORY_SHA256,
        context=_context(),
        context_reference="reference/audio/inventory/context.json",
        context_sha256="1" * 64,
    )
    assert b"\r" not in rendered


def test_context_cli_workflow_does_not_invoke_inventory_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_backend() -> object:
        raise AssertionError("production inventory backend must not be invoked")

    monkeypatch.setattr(cli, "_audio_backend", forbidden_backend)
    contextual = tmp_path / "contextual.json"
    contextual_sidecar = tmp_path / "contextual.sha256"
    summary = tmp_path / "summary.md"
    summary_sidecar = tmp_path / "summary.sha256"
    cli.main(
        [
            "audio-contextual-preflight",
            "--inventory",
            str(INVENTORY),
            "--inventory-sidecar",
            str(INVENTORY_SIDECAR),
            "--context",
            str(CONTEXT),
            "--context-sidecar",
            str(CONTEXT_SIDECAR),
            "--hardware-setup",
            str(HARDWARE),
            "--output",
            str(contextual),
            "--output-sidecar",
            str(contextual_sidecar),
        ]
    )
    cli.main(
        [
            "audio-inventory-summary",
            "--inventory",
            str(INVENTORY),
            "--inventory-sidecar",
            str(INVENTORY_SIDECAR),
            "--context",
            str(CONTEXT),
            "--context-sidecar",
            str(CONTEXT_SIDECAR),
            "--output",
            str(summary),
            "--output-sidecar",
            str(summary_sidecar),
        ]
    )
    cli.main(
        [
            "audio-context-validate",
            "--inventory",
            str(INVENTORY),
            "--inventory-sidecar",
            str(INVENTORY_SIDECAR),
            "--context",
            str(CONTEXT),
            "--context-sidecar",
            str(CONTEXT_SIDECAR),
            "--summary",
            str(summary),
            "--summary-sidecar",
            str(summary_sidecar),
            "--contextual-preflight",
            str(contextual),
            "--contextual-preflight-sidecar",
            str(contextual_sidecar),
        ]
    )
    assert capsys.readouterr().out.count("NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED") == 3
