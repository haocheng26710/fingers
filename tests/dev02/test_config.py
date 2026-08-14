from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from acoustic_ladder.config.bundle import (
    ConfigKind,
    ConfigValidationError,
    load_bundle,
    load_config,
    load_device_manifest,
)
from acoustic_ladder.config.models import AnalysisConfig, AudioConfig, ProtocolConfig
from acoustic_ladder.config.yaml_loader import ConfigYamlError, load_yaml_mapping
from tests.dev02.conftest import MANIFEST_PATH, REPO_ROOT, SIDECAR_PATH


def _read_yaml(path: Path) -> dict[str, Any]:
    return load_yaml_mapping(path)


def _write_yaml(path: Path, value: dict[str, Any]) -> Path:
    yaml = YAML(typ="safe", pure=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(value, handle)
    return path


def _load_temp(
    kind: ConfigKind, tmp_path: Path, data: dict[str, Any], manifest: dict[str, object]
) -> object:
    path = _write_yaml(tmp_path / f"{kind}.yaml", data)
    return load_config(kind, path, project_root=tmp_path, manifest=manifest).model


def test_safe_yaml_loads_plain_mapping(tmp_path: Path) -> None:
    path = tmp_path / "plain.yaml"
    path.write_text("alpha: 1\nbeta: null\n", encoding="utf-8")
    assert load_yaml_mapping(path) == {"alpha": 1, "beta": None}


def test_duplicate_yaml_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("alpha: 1\nalpha: 2\n", encoding="utf-8")
    with pytest.raises(ConfigYamlError, match="duplicate"):
        load_yaml_mapping(path)


def test_custom_yaml_tag_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tag.yaml"
    path.write_text("value: !python/object/apply:os.system ['unsafe']\n", encoding="utf-8")
    with pytest.raises(ConfigYamlError):
        load_yaml_mapping(path)


def test_unknown_config_field_is_rejected(tmp_path: Path, manifest: dict[str, object]) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml")
    data["invented"] = True
    with pytest.raises(ConfigValidationError, match="Extra inputs"):
        _load_temp("audio", tmp_path, data, manifest)


def test_audio_draft_is_valid(manifest: dict[str, object]) -> None:
    loaded = load_config(
        "audio",
        REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml",
        project_root=REPO_ROOT,
        manifest=manifest,
    )
    assert isinstance(loaded.model, AudioConfig)
    assert loaded.model.sample_rate_hz == 48000
    assert loaded.model.hardware_ready is False


def test_formal_audio_is_exactly_one_by_one(manifest: dict[str, object]) -> None:
    model = load_config(
        "audio",
        REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml",
        project_root=REPO_ROOT,
        manifest=manifest,
    ).model
    assert isinstance(model, AudioConfig)
    assert len(model.output_channels) == len(model.input_channels) == 1


def test_formal_multichannel_audio_is_rejected(tmp_path: Path, manifest: dict[str, object]) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml")
    data["output_channels"].append({"channel_index": None, "role": "diagnostic_reference"})
    with pytest.raises(ConfigValidationError, match="exactly one output"):
        _load_temp("audio", tmp_path, data, manifest)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [(10000.0, 300.0, "must be below"), (300.0, 24000.0, "Nyquist")],
)
def test_audio_frequency_contract(
    tmp_path: Path,
    manifest: dict[str, object],
    start: float,
    end: float,
    message: str,
) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml")
    data["ess_start_frequency_hz"] = start
    data["ess_end_frequency_hz"] = end
    with pytest.raises(ConfigValidationError, match=message):
        _load_temp("audio", tmp_path, data, manifest)


def test_hardware_unknowns_remain_null(manifest: dict[str, object]) -> None:
    model = load_config(
        "audio",
        REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml",
        project_root=REPO_ROOT,
        manifest=manifest,
    ).model
    assert isinstance(model, AudioConfig)
    assert model.audio_backend is None
    assert model.output_device.device_id is None
    assert model.output_channels[0].channel_index is None
    assert model.ess_duration_s is None
    assert model.output_gain_db is None


def test_hardware_ready_rejects_unknown_fields(tmp_path: Path, manifest: dict[str, object]) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml")
    data["hardware_ready"] = True
    with pytest.raises(ConfigValidationError, match="hardware field is null"):
        _load_temp("audio", tmp_path, data, manifest)


def test_obvious_numeric_string_is_not_silently_coerced(
    tmp_path: Path, manifest: dict[str, object]
) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml")
    data["sample_rate_hz"] = "48000"
    with pytest.raises(ConfigValidationError):
        _load_temp("audio", tmp_path, data, manifest)


@pytest.mark.parametrize(
    "filename",
    [
        "stage1_single_bridge.yaml",
        "stage2_single_node_proxy_states.yaml",
        "stage3_two_node_interaction.yaml",
        "stage4_four_node_states.yaml",
    ],
)
def test_stage_drafts_load(filename: str, manifest: dict[str, object]) -> None:
    model = load_config(
        "protocol",
        REPO_ROOT / "config" / "protocols" / filename,
        project_root=REPO_ROOT,
        manifest=manifest,
    ).model
    assert isinstance(model, ProtocolConfig)
    assert model.execution_ready is False
    assert model.repeats is model.reassemblies is model.sessions is None


def test_unknown_protocol_node_is_rejected(tmp_path: Path, manifest: dict[str, object]) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "protocols" / "stage1_single_bridge.yaml")
    data["selected_nodes"] = ["N99"]
    with pytest.raises(ConfigValidationError, match="absent from manifest"):
        _load_temp("protocol", tmp_path, data, manifest)


def test_duplicate_protocol_nodes_are_rejected(tmp_path: Path, manifest: dict[str, object]) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "protocols" / "stage1_single_bridge.yaml")
    data["selected_nodes"] = ["N1", "N1"]
    with pytest.raises(ConfigValidationError, match="duplicates"):
        _load_temp("protocol", tmp_path, data, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [("device_manifest_reference", "../manifest.json"), ("device_manifest_sha256", "bad")],
)
def test_protocol_manifest_identity_fields_are_well_formed(
    tmp_path: Path,
    manifest: dict[str, object],
    field: str,
    value: str,
) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "protocols" / "stage1_single_bridge.yaml")
    data[field] = value
    with pytest.raises(ConfigValidationError):
        _load_temp("protocol", tmp_path, data, manifest)


def test_protocol_state_modules_must_be_allowed(
    tmp_path: Path, manifest: dict[str, object]
) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "protocols" / "stage1_single_bridge.yaml")
    data["state_definitions"][0]["module_id"] = "M"
    with pytest.raises(ConfigValidationError, match="outside allowed_modules"):
        _load_temp("protocol", tmp_path, data, manifest)


def test_stage_four_nodes_come_from_manifest(manifest: dict[str, object]) -> None:
    model = load_config(
        "protocol",
        REPO_ROOT / "config" / "protocols" / "stage4_four_node_states.yaml",
        project_root=REPO_ROOT,
        manifest=manifest,
    ).model
    assert isinstance(model, ProtocolConfig)
    assert model.selected_nodes == ["N1", "N3", "N4", "N6"]


def test_stage_four_follows_modified_manifest_recommendation(
    manifest: dict[str, object],
) -> None:
    changed = copy.deepcopy(manifest)
    stage_four = changed["stage_four"]
    assert isinstance(stage_four, dict)
    stage_four["recommended_nodes"] = ["N2", "N5"]
    model = load_config(
        "protocol",
        REPO_ROOT / "config" / "protocols" / "stage4_four_node_states.yaml",
        project_root=REPO_ROOT,
        manifest=changed,
    ).model
    assert isinstance(model, ProtocolConfig)
    assert model.selected_nodes == ["N2", "N5"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("tx_far", "open", "Input should be 'closed'"), ("unselected_nodes", "OPEN", "BLK")],
)
def test_protocol_frozen_boundaries_are_enforced(
    tmp_path: Path,
    manifest: dict[str, object],
    field: str,
    value: str,
    message: str,
) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "protocols" / "stage1_single_bridge.yaml")
    data["boundary_conditions"][field] = value
    with pytest.raises(ConfigValidationError, match=message):
        _load_temp("protocol", tmp_path, data, manifest)


def test_analysis_unknown_decisions_remain_null(manifest: dict[str, object]) -> None:
    model = load_config(
        "analysis",
        REPO_ROOT / "config" / "analysis" / "default.yaml",
        project_root=REPO_ROOT,
        manifest=manifest,
    ).model
    assert isinstance(model, AnalysisConfig)
    assert model.features is None
    assert model.normalization is None
    assert model.cross_validation_strategy is None
    assert all(value is None for value in model.decision_gates.model_dump().values())


def test_normalized_hash_ignores_yaml_order_and_comments(
    tmp_path: Path, manifest: dict[str, object]
) -> None:
    source = _read_yaml(REPO_ROOT / "config" / "analysis" / "default.yaml")
    first = _write_yaml(tmp_path / "first.yaml", source)
    reversed_mapping = dict(reversed(list(source.items())))
    second = _write_yaml(tmp_path / "second.yaml", reversed_mapping)
    second.write_text(
        "# formatting-only comment\n" + second.read_text(encoding="utf-8"), encoding="utf-8"
    )
    one = load_config("analysis", first, project_root=tmp_path, manifest=manifest)
    two = load_config("analysis", second, project_root=tmp_path, manifest=manifest)
    assert one.snapshot.original_sha256 != two.snapshot.original_sha256
    assert one.snapshot.normalized_sha256 == two.snapshot.normalized_sha256


def test_bundle_hash_excludes_loading_time() -> None:
    common = {
        "project_root": REPO_ROOT,
        "manifest_path": MANIFEST_PATH,
        "manifest_sidecar_path": SIDECAR_PATH,
        "audio_path": REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml",
        "protocol_path": REPO_ROOT / "config" / "protocols" / "stage1_single_bridge.yaml",
        "analysis_path": REPO_ROOT / "config" / "analysis" / "default.yaml",
        "synthetic_path": REPO_ROOT / "config" / "synthetic" / "default.yaml",
    }
    first = load_bundle(**common, now=lambda: datetime(2026, 8, 14, tzinfo=UTC))
    second = load_bundle(**common, now=lambda: datetime(2026, 8, 15, tzinfo=UTC))
    assert first.receipt.loaded_at != second.receipt.loaded_at
    assert first.receipt.bundle_content_sha256 == second.receipt.bundle_content_sha256


@pytest.mark.parametrize("field", ["device_manifest_reference", "device_manifest_sha256"])
def test_bundle_rejects_protocol_manifest_identity_mismatch(tmp_path: Path, field: str) -> None:
    data = _read_yaml(REPO_ROOT / "config" / "protocols" / "stage1_single_bridge.yaml")
    data[field] = "0" * 64 if field.endswith("sha256") else "wrong/manifest.json"
    paths = {
        "manifest_path": tmp_path / "config/devices/device_manifest.provisional.json",
        "manifest_sidecar_path": tmp_path / "config/devices/device_manifest.provisional.sha256",
        "audio_path": tmp_path / "config/audio/default_1x1_ess.yaml",
        "protocol_path": tmp_path / "config/protocols/protocol.yaml",
        "analysis_path": tmp_path / "config/analysis/default.yaml",
        "synthetic_path": tmp_path / "config/synthetic/default.yaml",
    }
    sources = {
        "manifest_path": MANIFEST_PATH,
        "manifest_sidecar_path": SIDECAR_PATH,
        "audio_path": REPO_ROOT / "config/audio/default_1x1_ess.yaml",
        "analysis_path": REPO_ROOT / "config/analysis/default.yaml",
        "synthetic_path": REPO_ROOT / "config/synthetic/default.yaml",
    }
    for name, source in sources.items():
        target = paths[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    paths["protocol_path"].parent.mkdir(parents=True, exist_ok=True)
    _write_yaml(paths["protocol_path"], data)
    with pytest.raises(ConfigValidationError, match=field):
        load_bundle(
            project_root=tmp_path,
            manifest_path=paths["manifest_path"],
            manifest_sidecar_path=paths["manifest_sidecar_path"],
            audio_path=paths["audio_path"],
            protocol_path=paths["protocol_path"],
            analysis_path=paths["analysis_path"],
            synthetic_path=paths["synthetic_path"],
            now=lambda: datetime(2026, 8, 14, tzinfo=UTC),
        )


def test_manifest_sidecar_is_required_and_verified(tmp_path: Path) -> None:
    manifest_copy = tmp_path / "manifest.json"
    sidecar = tmp_path / "manifest.sha256"
    manifest_copy.write_bytes(MANIFEST_PATH.read_bytes())
    sidecar.write_text("0" * 64 + "  manifest.json\n", encoding="ascii")
    with pytest.raises(ValueError, match="mismatch"):
        load_device_manifest(manifest_copy, sidecar, project_root=tmp_path)
