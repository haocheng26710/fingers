from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from acoustic_ladder import cli
from acoustic_ladder.audio.backend import FakeInventoryBackend
from acoustic_ladder.audio.errors import AudioPersistenceError
from acoustic_ladder.audio.inventory import collect_inventory
from acoustic_ladder.audio.models import AudioPreflightReport, HardwareSetupRecord
from acoustic_ladder.audio.persistence import (
    load_audio_artifact,
    persist_audio_artifact,
)
from acoustic_ladder.audio.preflight import build_preflight_report
from acoustic_ladder.config.bundle import load_config
from acoustic_ladder.config.models import AudioConfig
from acoustic_ladder.config.schema import ALL_SCHEMA_MODELS, check_schemas, schema_bytes
from tests.conftest import REPO_ROOT
from tests.dev03.audio_api_guard import assert_production_audio_api_guard

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
HARDWARE_PATH = REPO_ROOT / "reference/audio/hardware_setup.provisional.json"


def _hardware() -> HardwareSetupRecord:
    return HardwareSetupRecord.model_validate_json(HARDWARE_PATH.read_bytes())


def _preflight(fake_backend: FakeInventoryBackend) -> AudioPreflightReport:
    snapshot = collect_inventory(fake_backend, now=NOW)
    return build_preflight_report(
        snapshot,
        _hardware(),
        inventory_reference="reference/audio/inventory/test.json",
        inventory_sha256="1" * 64,
        hardware_setup_reference="reference/audio/hardware_setup.provisional.json",
        hardware_setup_sha256=hashlib.sha256(HARDWARE_PATH.read_bytes()).hexdigest(),
        now=NOW,
    )


def test_hardware_setup_preserves_confirmed_and_unknown_facts() -> None:
    hardware = _hardware()
    assert hardware.interface_model == "Dayton Audio iMM-6C"
    assert hardware.operator_reported_shared_interface is True
    assert hardware.microphone_calibration_file_available is True
    assert hardware.microphone_calibration_reference is None
    assert hardware.microphone_calibration_sha256 is None
    assert hardware.electrical_loopback_available is False


def test_absolute_spl_requires_calibrator() -> None:
    data = _hardware().model_dump()
    data["absolute_spl_calibrated"] = True
    with pytest.raises(ValidationError, match="acoustic calibrator"):
        HardwareSetupRecord.model_validate(data)


def test_applied_calibration_requires_referenced_file() -> None:
    data = _hardware().model_dump()
    data["microphone_calibration_applied"] = True
    with pytest.raises(ValidationError, match="referenced, hashed"):
        HardwareSetupRecord.model_validate(data)


def test_name_match_remains_unconfirmed(fake_backend: FakeInventoryBackend) -> None:
    report = _preflight(fake_backend)
    assert report.input_candidate_device_indices == [0]
    assert report.operator_confirmation_status == "needs_operator_confirmation"


def test_one_way_checks_do_not_prove_duplex(fake_backend: FakeInventoryBackend) -> None:
    report = _preflight(fake_backend)
    assert report.separate_input_format_check
    assert report.separate_output_format_check
    assert report.full_duplex_verified is False
    assert report.shared_clock_verified is False


def test_preflight_is_never_hardware_ready(fake_backend: FakeInventoryBackend) -> None:
    report = _preflight(fake_backend)
    assert report.hardware_ready is False
    assert report.channel_mapping_verified is False
    assert report.calibration_file_verified is False


def test_canonical_json_and_sidecar_round_trip(
    tmp_path: Path, fake_backend: FakeInventoryBackend
) -> None:
    from acoustic_ladder.audio.models import AudioInventorySnapshot

    snapshot = collect_inventory(fake_backend, now=NOW)
    output = tmp_path / "inventory.json"
    sidecar = tmp_path / "inventory.sha256"
    digest = persist_audio_artifact(output, sidecar, snapshot)
    loaded, verified = load_audio_artifact(output, sidecar, AudioInventorySnapshot)
    assert loaded == snapshot
    assert verified == digest == hashlib.sha256(output.read_bytes()).hexdigest()
    assert sidecar.read_text(encoding="ascii").startswith(digest)


def test_sidecar_tampering_is_rejected(tmp_path: Path, fake_backend: FakeInventoryBackend) -> None:
    from acoustic_ladder.audio.models import AudioInventorySnapshot

    output = tmp_path / "inventory.json"
    sidecar = tmp_path / "inventory.sha256"
    persist_audio_artifact(output, sidecar, collect_inventory(fake_backend, now=NOW))
    sidecar.write_text("0" * 64 + "  inventory.json\n", encoding="ascii")
    with pytest.raises(AudioPersistenceError, match="mismatch"):
        load_audio_artifact(output, sidecar, AudioInventorySnapshot)


def test_inventory_persistence_is_create_only(
    tmp_path: Path, fake_backend: FakeInventoryBackend
) -> None:
    output = tmp_path / "inventory.json"
    sidecar = tmp_path / "inventory.sha256"
    snapshot = collect_inventory(fake_backend, now=NOW)
    persist_audio_artifact(output, sidecar, snapshot)
    original = output.read_bytes()
    with pytest.raises(AudioPersistenceError, match="already exists"):
        persist_audio_artifact(output, sidecar, snapshot)
    assert output.read_bytes() == original


def test_audio_config_remains_draft_one_by_one() -> None:
    model = load_config(
        "audio",
        REPO_ROOT / "config/audio/default_1x1_ess.yaml",
        project_root=REPO_ROOT,
    ).model
    assert isinstance(model, AudioConfig)
    assert model.config_status == "draft"
    assert model.hardware_ready is False
    assert len(model.input_channels) == len(model.output_channels) == 1
    assert model.input_channels[0].channel_index is None
    assert model.output_channels[0].channel_index is None
    assert model.operator_confirmation_status == "needs_operator_confirmation"


def test_all_committed_schemas_match_models() -> None:
    check_schemas(REPO_ROOT / "schemas")
    assert len(ALL_SCHEMA_MODELS) == 11
    for filename, model in ALL_SCHEMA_MODELS.items():
        assert (REPO_ROOT / "schemas" / filename).read_bytes() == schema_bytes(model)


def test_cli_inventory_and_preflight_include_safety_marker(
    tmp_path: Path,
    fake_backend: FakeInventoryBackend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_audio_backend", lambda: fake_backend)
    inventory = tmp_path / "inventory.json"
    sidecar = tmp_path / "inventory.sha256"
    preflight = tmp_path / "preflight.json"
    cli.main(["audio-inventory", "--output", str(inventory), "--sidecar", str(sidecar)])
    cli.main(
        [
            "audio-preflight",
            "--inventory",
            str(inventory),
            "--inventory-sidecar",
            str(sidecar),
            "--hardware-setup",
            str(HARDWARE_PATH),
            "--output",
            str(preflight),
        ]
    )
    cli.main(
        [
            "audio-validate",
            "--inventory",
            str(inventory),
            "--inventory-sidecar",
            str(sidecar),
            "--preflight",
            str(preflight),
        ]
    )
    assert capsys.readouterr().out.count("NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED") == 3
    assert json.loads(preflight.read_text(encoding="utf-8"))["hardware_ready"] is False


def test_audio_list_cli_has_safety_marker(
    fake_backend: FakeInventoryBackend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_audio_backend", lambda: fake_backend)
    cli.main(["audio-list"])
    output = capsys.readouterr().out
    assert "HOST_API 0" in output
    assert "DEVICE 0" in output
    assert "NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED" in output


def test_production_audio_code_calls_no_forbidden_api() -> None:
    sources = {
        str(source_path): source_path.read_text(encoding="utf-8")
        for source_path in (REPO_ROOT / "src/acoustic_ladder/audio").glob("*.py")
    }
    assert_production_audio_api_guard(sources)
