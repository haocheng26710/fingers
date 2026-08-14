from __future__ import annotations

import json
from pathlib import Path

import pytest

from acoustic_ladder.model_package.calibration import (
    CalibrationRecordError,
    canonical_json_bytes,
    load_calibration_record,
    validate_calibration_record,
)
from acoustic_ladder.model_package.normalize import (
    BRIDGE_MODULE_ALIASES,
    ManifestError,
    bridge_module,
    recompute_sidecar,
    verify_sidecar,
    write_manifest,
)
from tests.conftest import CALIBRATION_RECORD


def test_bridge_alias_mapping() -> None:
    assert BRIDGE_MODULE_ALIASES == {
        "B40": ("ALV1_module_bridge_D4p0", "D4.0"),
        "B32": ("ALV1_module_bridge_D3p2", "D3.2"),
        "B28": ("ALV1_module_bridge_D2p8", "D2.8"),
    }


def test_target_cad_and_measured_apertures_are_separate() -> None:
    module = bridge_module("B40", 4.0, 4.15)
    assert module["target_aperture"] == {"value": 4.0, "unit": "mm"}
    assert module["cad_compensated_aperture"] == {"value": 4.15, "unit": "mm"}
    assert module["measured_post_print_aperture"] == {"value": None, "unit": "mm"}


def test_unknown_bridge_alias_fails() -> None:
    with pytest.raises(ManifestError):
        bridge_module("B99", 9.9, 10.0)


def test_unknown_calibration_values_remain_null() -> None:
    record = load_calibration_record(CALIBRATION_RECORD)
    actual = record["actual_print_record"]
    assert isinstance(actual, dict)
    settings = actual["settings"]
    assert isinstance(settings, dict)
    assert settings["nozzle_diameter_mm"] is None
    material = actual["material"]
    assert isinstance(material, dict)
    assert material["type"] is None


def test_design_recommendation_does_not_fill_actual_settings() -> None:
    record = load_calibration_record(CALIBRATION_RECORD)
    design = record["design_recommendation"]
    actual = record["actual_print_record"]
    assert isinstance(design, dict)
    assert isinstance(actual, dict)
    settings = actual["settings"]
    assert isinstance(settings, dict)
    assert design["nozzle_diameter_mm"] == 0.4
    assert settings["nozzle_diameter_mm"] is None


def test_non_null_unknown_is_rejected() -> None:
    record = json.loads(CALIBRATION_RECORD.read_text(encoding="utf-8"))
    record["actual_print_record"]["settings"]["nozzle_diameter_mm"] = 0.4
    with pytest.raises(CalibrationRecordError):
        validate_calibration_record(record)


def test_canonical_manifest_bytes_are_deterministic() -> None:
    first = canonical_json_bytes({"z": 1, "a": {"b": 2}})
    second = canonical_json_bytes({"a": {"b": 2}, "z": 1})
    assert first == second
    assert first.endswith(b"\n")


def test_manifest_sidecar_round_trip(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    sidecar = tmp_path / "manifest.sha256"
    digest = write_manifest({"schema_version": "test"}, manifest, sidecar)
    assert verify_sidecar(manifest, sidecar) == digest
    assert recompute_sidecar(manifest, sidecar) == digest


def test_manifest_sidecar_detects_tampering(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    sidecar = tmp_path / "manifest.sha256"
    write_manifest({"schema_version": "test"}, manifest, sidecar)
    manifest.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        verify_sidecar(manifest, sidecar)
