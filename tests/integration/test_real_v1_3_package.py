from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from acoustic_ladder.model_package.archive import EXPECTED_V1_3_SHA256, inspect_archive
from acoustic_ladder.model_package.models import JsonObject, JsonValue
from acoustic_ladder.model_package.normalize import (
    ManifestError,
    collect_null_pointers,
    generate_manifest,
    validate_manifest_file,
    verify_sidecar,
    write_manifest,
)
from tests.conftest import CALIBRATION_RECORD, MANIFEST_SCHEMA, REAL_PACKAGE


@pytest.fixture(scope="module")
def audit() -> JsonObject:
    calibration = json.loads(CALIBRATION_RECORD.read_text(encoding="utf-8"))
    return inspect_archive(
        REAL_PACKAGE,
        expected_sha256=EXPECTED_V1_3_SHA256,
        calibration_record=calibration,
        scanned_at="2026-08-14T00:00:00Z",
    )


@pytest.fixture(scope="module")
def manifest() -> JsonObject:
    return generate_manifest(REAL_PACKAGE, CALIBRATION_RECORD)


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def test_real_package_hash_and_inventory(audit: JsonObject) -> None:
    assert audit["package_sha256"] == EXPECTED_V1_3_SHA256
    assert hashlib.sha256(REAL_PACKAGE.read_bytes()).hexdigest() == EXPECTED_V1_3_SHA256
    assert audit["counts"] == {
        "formal_part_types": 22,
        "stl_files": 22,
        "step_files": 22,
        "assembly_files": 4,
        "batch_folders": 8,
        "calibration_files": 0,
    }
    assert audit["entry_count"] == 85


def test_real_package_validation_results(audit: JsonObject) -> None:
    results = _object(audit["package_results"])
    assert results["completeness"] == "PASS"
    assert results["printability"] == "PASS"
    assert results["mechanical_validation"] == {"pass": 254, "warning": 0, "fail": 0}
    required = _object(audit["required_files"])
    assert required["all_present"] is True
    assert len(_list(required["python_sources_read_without_execution"])) == 12


def test_real_geometry_and_stage_four(manifest: JsonObject) -> None:
    architecture = _object(manifest["architecture"])
    main_tube = _object(architecture["main_tube"])
    assert main_tube["lumen_shape"] == "round"
    assert _object(main_tube["inner_diameter"])["value"] == pytest.approx(5.0657870100038425)
    assert _object(main_tube["cross_sectional_area"])["value"] == pytest.approx(20.155043202071983)
    nodes = _list(architecture["nodes"])
    assert [_object(_object(node)["position"])["value"] for node in nodes] == [
        50.0,
        105.0,
        165.0,
        235.0,
        310.0,
        360.0,
    ]
    assert manifest["stage_four"] == {"recommended_nodes": ["N1", "N3", "N4", "N6"]}


def test_real_calibration_values(manifest: JsonObject) -> None:
    calibration = _object(manifest["calibration"])
    expected = {
        "module_diametral_offset": 0.0,
        "split_joint_diametral_offset": -0.14,
        "end_diametral_offset": -0.08,
        "acoustic_hole_compensation": 0.15,
        "slider_guide_clearance_per_side": 0.2,
    }
    for name, value in expected.items():
        assert _object(calibration[name])["value"] == pytest.approx(value)
    assert calibration["selected_wedge"] == "M"
    assert _object(calibration["selected_wedge_preload_offset"])["value"] == 0.0
    assert _object(calibration["d4_bridge_min_tip_wall"])["value"] == pytest.approx(
        0.8840909090909093
    )


def test_formal_bom_is_authoritative(manifest: JsonObject) -> None:
    bom = _object(manifest["bill_of_materials"])
    assert bom["authoritative_source"] == "reports/BOM_calibrated_v1_3.csv"
    quantities = _object(bom["quantities"])
    assert quantities["ALV1_slider_lock_wedge_M"] == 4
    assert quantities["ALV1_slider_lock_wedge_L"] == 0
    assert quantities["ALV1_slider_lock_wedge_H"] == 0


def test_current_status_is_not_locked_or_experiment_ready(manifest: JsonObject) -> None:
    assert manifest["status"] == {
        "model_status": "provisional",
        "physical_print_status": "actual_printed",
        "calibration_status": "applied",
        "release_role": "calibrated_printed_candidate",
        "geometry_locked": False,
        "experiment_ready": False,
    }


def test_v1_2_is_historical_not_an_active_parameter_source(manifest: JsonObject) -> None:
    assert manifest["source_geometry_version"] == "V1.2 equal-area round main tube"
    assert manifest["device_version"] == "Acoustic Ladder V1.3 Calibrated Round Main Tube"
    provenance = _object(manifest["provenance"])
    fields = _object(provenance["fields"])
    source_filenames = [_object(value)["source_filename"] for value in fields.values()]
    assert not any("v1_2" in str(filename).lower() for filename in source_filenames)


def test_unknowns_remain_null_and_design_does_not_fill_actual(manifest: JsonObject) -> None:
    manufacturing = _object(manifest["manufacturing"])
    settings = _object(manufacturing["actual_print_setting"])
    design = _object(manufacturing["design_recommendation"])
    assert settings["nozzle_diameter_mm"] is None
    assert _object(design["nozzle_diameter"])["value"] == 0.4
    material = _object(manufacturing["material"])
    assert material["type"] is None
    measurement_record = _object(manufacturing["measurement"])
    assert measurement_record["tool"] is None
    assert measurement_record["tool_accuracy"] is None
    modules = _list(manifest["modules"])
    for module in modules[:3]:
        measured = _object(_object(module)["measured_post_print_aperture"])
        assert measured["value"] is None
    nulls = collect_null_pointers(manufacturing, "/manufacturing")
    missing = _list(manifest["missing_information"])
    assert set(nulls).issubset(set(missing))
    calibration = _object(manifest["calibration"])
    coupon_measurements = _list(calibration["acoustic_hole_coupon_measurements"])
    assert len(coupon_measurements) == 5
    assert all(
        _object(_object(item)["measured_post_print_diameter"])["value"] is None
        for item in coupon_measurements
    )


def test_known_warnings_and_conflicts_are_explicit(manifest: JsonObject) -> None:
    warning_codes = {_object(item)["code"] for item in _list(manifest["warnings"])}
    assert warning_codes == {
        "DERIVED_FIELD_NAME_MAIN_TEARDROP",
        "LEGACY_REPORT_TITLES",
        "SOURCE_BOM_WEDGE_QUANTITY_MISMATCH",
        "MISSING_ACOUSTIC_CALCS_SOURCE",
        "MISSING_BUILD_V1_SOURCE",
        "CAD_REBUILD_ENVIRONMENT_NOT_LOCKED",
        "RAW_CALIBRATION_MEASUREMENTS_MISSING",
        "ACTUAL_PRINT_FIELDS_INCOMPLETE",
        "LEAK_AND_SPECTRAL_TESTS_UNRECORDED",
    }
    provenance = _object(manifest["provenance"])
    conflict_codes = {_object(item)["code"] for item in _list(provenance["conflicts"])}
    assert conflict_codes == {"BOM_WEDGE_QUANTITY_CONFLICT", "ACTIVE_LUMEN_LABEL_CONFLICT"}


def test_manifest_generation_is_byte_deterministic(tmp_path: Path) -> None:
    first = generate_manifest(REAL_PACKAGE, CALIBRATION_RECORD)
    second = generate_manifest(REAL_PACKAGE, CALIBRATION_RECORD)
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_sidecar = tmp_path / "first.sha256"
    second_sidecar = tmp_path / "second.sha256"
    first_digest = write_manifest(first, first_path, first_sidecar)
    second_digest = write_manifest(second, second_path, second_sidecar)
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_digest == second_digest


def test_generated_manifest_schema_and_sidecar(tmp_path: Path, manifest: JsonObject) -> None:
    manifest_path = tmp_path / "device_manifest.provisional.json"
    sidecar_path = tmp_path / "device_manifest.provisional.sha256"
    digest = write_manifest(manifest, manifest_path, sidecar_path)
    validate_manifest_file(manifest_path, MANIFEST_SCHEMA)
    assert verify_sidecar(manifest_path, sidecar_path) == digest


def test_schema_distinguishes_null_from_missing(tmp_path: Path, manifest: JsonObject) -> None:
    invalid = deepcopy(manifest)
    modules = _list(invalid["modules"])
    first_module = _object(modules[0])
    measured = _object(first_module["measured_post_print_aperture"])
    del measured["value"]
    invalid_path = tmp_path / "missing-null.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ManifestError):
        validate_manifest_file(invalid_path, MANIFEST_SCHEMA)


def test_schema_distinguishes_provisional_from_locked(tmp_path: Path, manifest: JsonObject) -> None:
    invalid = deepcopy(manifest)
    status = _object(invalid["status"])
    status["model_status"] = "locked"
    status["geometry_locked"] = False
    invalid_path = tmp_path / "invalid-locked-state.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ManifestError):
        validate_manifest_file(invalid_path, MANIFEST_SCHEMA)
