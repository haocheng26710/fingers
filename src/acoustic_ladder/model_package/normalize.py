"""Normalize audited V1.3 package facts into a deterministic provisional manifest."""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

from acoustic_ladder.model_package.archive import (
    EXPECTED_V1_3_SHA256,
    inspect_archive,
    read_csv,
    read_json,
)
from acoustic_ladder.model_package.calibration import canonical_json_bytes, load_calibration_record
from acoustic_ladder.model_package.models import JsonObject, JsonValue, SourceCandidate, measurement
from acoustic_ladder.model_package.provenance import ref, resolve_value

MANIFEST_SCHEMA_VERSION = "1.0.0"
DEVICE_ID = "acoustic-ladder-v1-3-calibrated-printed-candidate"
BRIDGE_MODULE_ALIASES = {
    "B40": ("ALV1_module_bridge_D4p0", "D4.0"),
    "B32": ("ALV1_module_bridge_D3p2", "D3.2"),
    "B28": ("ALV1_module_bridge_D2p8", "D2.8"),
}


class ManifestError(ValueError):
    """Raised when manifest generation or validation fails."""


def _object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ManifestError(f"Expected object at {label}")
    return value


def _list(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ManifestError(f"Expected array at {label}")
    return value


def _number(value: JsonValue, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ManifestError(f"Expected number at {label}")
    return float(value)


def _string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"Expected string at {label}")
    return value


def _numbers(value: JsonValue, label: str) -> list[float]:
    return [_number(item, f"{label}/{index}") for index, item in enumerate(_list(value, label))]


def _nested(record: JsonObject, *keys: str) -> JsonValue:
    current: JsonValue = record
    path = ""
    for key in keys:
        path += f"/{key}"
        current = _object(current, path)[key]
    return current


def collect_null_pointers(value: JsonValue, prefix: str = "") -> list[str]:
    """Return JSON Pointers for all explicitly null leaves."""

    if value is None:
        return [prefix or "/"]
    pointers: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            token = key.replace("~", "~0").replace("/", "~1")
            pointers.extend(collect_null_pointers(child, f"{prefix}/{token}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            pointers.extend(collect_null_pointers(child, f"{prefix}/{index}"))
    return pointers


def bridge_module(
    module_id: str,
    target_aperture_mm: float,
    cad_aperture_mm: float,
    measured_aperture_mm: float | None = None,
) -> JsonObject:
    """Build a bridge module while keeping target, CAD and measured apertures distinct."""

    try:
        cad_name, _derived_key = BRIDGE_MODULE_ALIASES[module_id]
    except KeyError as exc:
        raise ManifestError(f"Unknown bridge module alias: {module_id}") from exc
    return {
        "id": module_id,
        "cad_name": cad_name,
        "kind": "bridge",
        "target_aperture": measurement(target_aperture_mm, "mm"),
        "cad_compensated_aperture": measurement(cad_aperture_mm, "mm"),
        "measured_post_print_aperture": measurement(measured_aperture_mm, "mm"),
    }


def _package_ref(filename: str, locator: str, kind: str, unit: str | None) -> JsonObject:
    return ref("v1_3_print_package", filename, locator, kind, unit, "package_verified")


def _user_ref(locator: str, unit: str | None = None) -> JsonObject:
    return ref(
        "user_confirmed_measurement_record",
        "reference/calibration/V1_3_user_calibration_record.json",
        locator,
        "source",
        unit,
        "user_confirmed",
    )


def _frozen_ref(locator: str) -> JsonObject:
    return ref(
        "user_frozen_research_condition",
        "docs/prompts/DEV-01.01.md",
        locator,
        "source",
        None,
        "frozen",
    )


def _resolve_package_and_user(
    field: str,
    package_value: JsonValue,
    package_filename: str,
    package_locator: str,
    user_value: JsonValue,
    user_locator: str,
    unit: str | None,
) -> tuple[JsonValue, JsonObject | None]:
    return resolve_value(
        field,
        [
            SourceCandidate(
                package_value,
                1,
                "v1_3_print_package",
                package_filename,
                package_locator,
                "source",
                unit,
                "package_verified",
            ),
            SourceCandidate(
                user_value,
                2,
                "user_confirmed_measurement_record",
                "reference/calibration/V1_3_user_calibration_record.json",
                user_locator,
                "source",
                unit,
                "user_confirmed",
            ),
        ],
    )


def generate_manifest(
    archive_path: str | Path,
    calibration_path: str | Path,
    *,
    expected_sha256: str = EXPECTED_V1_3_SHA256,
) -> JsonObject:
    """Generate the active V1.3 provisional manifest solely from supplied inputs."""

    calibration_record = load_calibration_record(calibration_path)
    audit = inspect_archive(
        archive_path,
        expected_sha256=expected_sha256,
        calibration_record=calibration_record,
    )
    with zipfile.ZipFile(archive_path) as archive:
        params = read_json(archive, "reports/params_calibrated_v1_3.json")
        applied = read_json(archive, "reports/calibration_applied_v1_3.json")
        derived = read_json(archive, "reports/derived_acoustics_v1.json")
        dry_seal = read_json(archive, "reports/dry_seal_dimensions_v1.json")
        formal_bom_rows = read_csv(archive, "reports/BOM_calibrated_v1_3.csv")

    package_filename = "reports/params_calibrated_v1_3.json"
    fields: dict[str, JsonValue] = {}
    conflicts = list(_list(audit["conflicts"], "/audit/conflicts"))

    version = _string(params["VERSION"], "/VERSION")
    source_geometry = _string(applied["source_geometry"], "/source_geometry")
    total_length = _number(params["MAIN_TOTAL_ACOUSTIC_LENGTH"], "/MAIN_TOTAL_ACOUSTIC_LENGTH")
    segment_length = _number(params["SEGMENT_ACOUSTIC_LENGTH"], "/SEGMENT_ACOUSTIC_LENGTH")
    center_spacing = _number(params["MAIN_CENTER_SPACING"], "/MAIN_CENTER_SPACING")
    diameter = _number(params["ROUND_LUMEN_DIAMETER_MM"], "/ROUND_LUMEN_DIAMETER_MM")
    current_round_area = math.pi * (diameter / 2.0) ** 2
    node_positions = _numbers(params["NODE_X_GLOBAL"], "/NODE_X_GLOBAL")
    stage_four_positions = _numbers(
        params["STAGE_FOUR_INITIAL_NODE_X"], "/STAGE_FOUR_INITIAL_NODE_X"
    )
    node_ids = [f"N{index}" for index in range(1, len(node_positions) + 1)]
    position_to_id = dict(zip(node_positions, node_ids, strict=True))
    try:
        stage_four_nodes = [position_to_id[position] for position in stage_four_positions]
    except KeyError as exc:
        raise ManifestError(f"Stage-four position is not a declared node: {exc}") from exc

    fields.update(
        {
            "/device_version": _package_ref(package_filename, "/VERSION", "source", None),
            "/source_geometry_version": _package_ref(
                "reports/calibration_applied_v1_3.json", "/source_geometry", "source", None
            ),
            "/status/model_status": _frozen_ref("#2 model_status"),
            "/status/physical_print_status": _frozen_ref("#2 physical_print_status"),
            "/status/calibration_status": _frozen_ref("#2 calibration_status"),
            "/status/release_role": _frozen_ref("#2 release_role"),
            "/package/sha256": ref(
                "computed_archive_digest",
                Path(archive_path).name,
                "SHA256 of complete ZIP bytes",
                "derived",
                None,
                "computed_and_cross_checked",
            ),
            "/architecture/main_tube/lumen_shape": _package_ref(
                package_filename, "/VERSION and /ROUND_LUMEN_DIAMETER_MM", "source", None
            ),
            "/architecture/main_tube/total_acoustic_length": _package_ref(
                package_filename, "/MAIN_TOTAL_ACOUSTIC_LENGTH", "source", "mm"
            ),
            "/architecture/main_tube/segment_acoustic_length": _package_ref(
                package_filename, "/SEGMENT_ACOUSTIC_LENGTH", "source", "mm"
            ),
            "/architecture/main_tube/center_spacing": _package_ref(
                package_filename, "/MAIN_CENTER_SPACING", "source", "mm"
            ),
            "/architecture/main_tube/inner_diameter": _package_ref(
                package_filename, "/ROUND_LUMEN_DIAMETER_MM", "source", "mm"
            ),
            "/architecture/main_tube/cross_sectional_area": ref(
                "recomputed_from_v1_3_source_geometry",
                package_filename,
                "pi * (/ROUND_LUMEN_DIAMETER_MM / 2)^2",
                "derived",
                "mm^2",
                "computed",
            ),
            "/architecture/audio_channels": _frozen_ref("#2 formal audio channels"),
            "/architecture/end_roles": _frozen_ref("#2 TX/RX near/far roles"),
            "/boundary_conditions": _frozen_ref("#2 frozen boundary conditions"),
            "/stage_four/recommended_nodes": _package_ref(
                package_filename, "/STAGE_FOUR_INITIAL_NODE_X", "source", "mm"
            ),
        }
    )
    for index, _node_id in enumerate(node_ids):
        fields[f"/architecture/nodes/{index}/position"] = _package_ref(
            package_filename, f"/NODE_X_GLOBAL/{index}", "source", "mm"
        )

    bridge_specs = [
        (module_id, cad_name, derived_key, index)
        for index, (module_id, (cad_name, derived_key)) in enumerate(BRIDGE_MODULE_ALIASES.items())
    ]
    derived_bridges = _object(derived["bridges"], "/bridges")
    modules: list[JsonValue] = []
    missing_information: list[str] = []
    for index, (module_id, _cad_name, derived_key, target_index) in enumerate(bridge_specs):
        bridge = _object(derived_bridges[derived_key], f"/bridges/{derived_key}")
        target = _number(bridge["target_diameter_mm"], f"/bridges/{derived_key}/target_diameter_mm")
        cad = _number(bridge["cad_diameter_mm"], f"/bridges/{derived_key}/cad_diameter_mm")
        modules.append(bridge_module(module_id, target, cad))
        fields[f"/modules/{index}/target_aperture"] = _package_ref(
            "reports/derived_acoustics_v1.json",
            f"/bridges/{derived_key}/target_diameter_mm",
            "derived",
            "mm",
        )
        fields[f"/modules/{index}/cad_compensated_aperture"] = _package_ref(
            "reports/derived_acoustics_v1.json",
            f"/bridges/{derived_key}/cad_diameter_mm",
            "derived",
            "mm",
        )
        fields[f"/modules/{index}/measured_post_print_aperture"] = _user_ref(
            f"/calibration/acoustic_holes/measured_diameters_mm/{target_index}", "mm"
        )
        missing_information.append(f"/modules/{index}/measured_post_print_aperture/value")
    block_dead_length = _number(params["BLOCK_TIP_TO_MAIN_LUMEN"], "/BLOCK_TIP_TO_MAIN_LUMEN")
    modules.append(
        {
            "id": "BLK",
            "cad_name": "ALV1_module_block",
            "kind": "block",
            "meaning": "closed_node_not_open_end",
            "residual_dead_cavity_length": measurement(block_dead_length, "mm"),
        }
    )
    fields["/modules/3/residual_dead_cavity_length"] = _package_ref(
        package_filename, "/BLOCK_TIP_TO_MAIN_LUMEN", "source", "mm"
    )

    user_calibration = _object(calibration_record["calibration"], "/calibration")
    calibration_fields = (
        (
            "module_diametral_offset",
            applied["module_diametral_offset_mm"],
            "/module_diametral_offset_mm",
            _nested(user_calibration, "module_dry_seal", "applied_value_mm"),
            "/calibration/module_dry_seal/applied_value_mm",
        ),
        (
            "split_joint_diametral_offset",
            applied["split_joint_diametral_offset_mm"],
            "/split_joint_diametral_offset_mm",
            _nested(user_calibration, "split_joint_dry_seal", "applied_value_mm"),
            "/calibration/split_joint_dry_seal/applied_value_mm",
        ),
        (
            "end_diametral_offset",
            applied["end_diametral_offset_mm"],
            "/end_diametral_offset_mm",
            _nested(user_calibration, "end_dry_seal", "applied_value_mm"),
            "/calibration/end_dry_seal/applied_value_mm",
        ),
        (
            "acoustic_hole_compensation",
            applied["acoustic_hole_compensation_mm"],
            "/acoustic_hole_compensation_mm",
            _nested(user_calibration, "acoustic_holes", "applied_value_mm"),
            "/calibration/acoustic_holes/applied_value_mm",
        ),
        (
            "slider_guide_clearance_per_side",
            applied["slider_guide_clearance_per_side_mm"],
            "/slider_guide_clearance_per_side_mm",
            _nested(user_calibration, "slider_and_wedge", "guide_clearance_per_side_mm"),
            "/calibration/slider_and_wedge/guide_clearance_per_side_mm",
        ),
    )
    resolved_calibration: JsonObject = {}
    for field_name, package_value, package_locator, user_value, user_locator in calibration_fields:
        selected, conflict = _resolve_package_and_user(
            f"/calibration/{field_name}",
            package_value,
            "reports/calibration_applied_v1_3.json",
            package_locator,
            user_value,
            user_locator,
            "mm",
        )
        resolved_calibration[field_name] = measurement(cast(int | float | None, selected), "mm")
        fields[f"/calibration/{field_name}"] = _package_ref(
            "reports/calibration_applied_v1_3.json", package_locator, "source", "mm"
        )
        if conflict is not None:
            conflicts.append(conflict)

    selected_wedge, wedge_conflict = _resolve_package_and_user(
        "/calibration/selected_wedge",
        applied["selected_wedge"],
        "reports/calibration_applied_v1_3.json",
        "/selected_wedge",
        _nested(user_calibration, "slider_and_wedge", "selected_wedge"),
        "/calibration/slider_and_wedge/selected_wedge",
        None,
    )
    resolved_calibration["selected_wedge"] = selected_wedge
    resolved_calibration["selected_wedge_preload_offset"] = measurement(
        cast(
            int | float | None,
            _nested(user_calibration, "slider_and_wedge", "selected_wedge_preload_offset_mm"),
        ),
        "mm",
    )
    resolved_calibration["module_plug_base_tip"] = {
        "values": _numbers(applied["module_plug_base_tip_mm"], "/module_plug_base_tip_mm"),
        "unit": "mm",
    }
    resolved_calibration["split_joint_plug_base_tip"] = {
        "values": _numbers(
            applied["split_joint_plug_base_tip_mm"], "/split_joint_plug_base_tip_mm"
        ),
        "unit": "mm",
    }
    resolved_calibration["end_plug_base_tip"] = {
        "values": _numbers(applied["end_plug_base_tip_mm"], "/end_plug_base_tip_mm"),
        "unit": "mm",
    }
    resolved_calibration["split_joint_key_slot"] = {
        "width": measurement(
            _number(params["JOINT_KEY_SLOT_WIDTH"], "/JOINT_KEY_SLOT_WIDTH"), "mm"
        ),
        "radial_height": measurement(
            _number(params["JOINT_KEY_SLOT_RADIAL_HEIGHT"], "/JOINT_KEY_SLOT_RADIAL_HEIGHT"), "mm"
        ),
        "radial_center": measurement(
            _number(params["JOINT_KEY_SLOT_RADIAL_CENTER"], "/JOINT_KEY_SLOT_RADIAL_CENTER"), "mm"
        ),
        "male_key_width": measurement(_number(params["JOINT_KEY_WIDTH"], "/JOINT_KEY_WIDTH"), "mm"),
        "male_key_height": measurement(
            _number(params["JOINT_KEY_HEIGHT"], "/JOINT_KEY_HEIGHT"), "mm"
        ),
    }
    resolved_calibration["d4_bridge_min_tip_wall"] = measurement(
        _number(applied["D4_bridge_min_tip_wall_mm"], "/D4_bridge_min_tip_wall_mm"), "mm"
    )
    hole_targets = _numbers(
        _nested(user_calibration, "acoustic_holes", "target_diameters_mm"),
        "/calibration/acoustic_holes/target_diameters_mm",
    )
    hole_measurements = _list(
        _nested(user_calibration, "acoustic_holes", "measured_diameters_mm"),
        "/calibration/acoustic_holes/measured_diameters_mm",
    )
    if len(hole_targets) != len(hole_measurements):
        raise ManifestError("Acoustic-hole targets and measurements have different lengths")
    resolved_calibration["acoustic_hole_coupon_measurements"] = [
        {
            "target_diameter": measurement(target, "mm"),
            "measured_post_print_diameter": measurement(cast(int | float | None, measured), "mm"),
        }
        for target, measured in zip(hole_targets, hole_measurements, strict=True)
    ]
    resolved_calibration["dry_seal_dimensions"] = dry_seal
    resolved_calibration["user_record"] = {
        "source_type": calibration_record["source_type"],
        "confirmation_date": calibration_record["confirmation_date"],
        "confirmation_time": calibration_record["confirmation_time"],
    }
    fields["/calibration/selected_wedge"] = _package_ref(
        "reports/calibration_applied_v1_3.json", "/selected_wedge", "source", None
    )
    fields["/calibration/selected_wedge_preload_offset"] = _user_ref(
        "/calibration/slider_and_wedge/selected_wedge_preload_offset_mm", "mm"
    )
    fields["/calibration/acoustic_hole_coupon_measurements"] = _user_ref(
        "/calibration/acoustic_holes", "mm"
    )
    if wedge_conflict is not None:
        conflicts.append(wedge_conflict)

    actual_print = _object(calibration_record["actual_print_record"], "/actual_print_record")
    actual_print_settings = _object(actual_print["settings"], "/actual_print_record/settings")
    design_recommendation: JsonObject = {
        "nozzle_diameter": measurement(
            _number(params["NOZZLE_DIAMETER"], "/NOZZLE_DIAMETER"), "mm"
        ),
        "material": params["DEFAULT_MATERIAL"],
        "layer_height_range": {
            "values": _numbers(params["LAYER_HEIGHT_RANGE"], "/LAYER_HEIGHT_RANGE"),
            "unit": "mm",
        },
        "wall_count": params["MAIN_WALL_COUNT"],
    }
    fields["/manufacturing/design_recommendation"] = _package_ref(
        package_filename,
        "/NOZZLE_DIAMETER, /DEFAULT_MATERIAL, /LAYER_HEIGHT_RANGE, /MAIN_WALL_COUNT",
        "source",
        None,
    )
    fields["/manufacturing/actual_print_setting"] = _user_ref("/actual_print_record/settings")
    fields["/manufacturing/printer"] = _user_ref("/actual_print_record/printer")
    fields["/manufacturing/material"] = _user_ref("/actual_print_record/material")

    bom_quantities = {row["part_name"]: int(row["quantity"]) for row in formal_bom_rows}
    audit_counts = _object(audit["counts"], "/audit/counts")
    package_results = _object(audit["package_results"], "/audit/package_results")
    manifest: JsonObject = {
        "$schema": "../../schemas/device_manifest.schema.json",
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "device_id": DEVICE_ID,
        "device_version": version,
        "source_geometry_version": source_geometry,
        "status": {
            "model_status": "provisional",
            "physical_print_status": "actual_printed",
            "calibration_status": "applied",
            "release_role": "calibrated_printed_candidate",
            "geometry_locked": False,
            "experiment_ready": False,
        },
        "package": {
            "filename": Path(archive_path).name,
            "sha256": audit["package_sha256"],
            "file_size_bytes": audit["file_size_bytes"],
        },
        "architecture": {
            "research_object": (
                "single-speaker single-microphone reconfigurable internal acoustic graph network"
            ),
            "audio_channels": {"output": 1, "input": 1},
            "main_tube": {
                "lumen_shape": "round",
                "total_acoustic_length": measurement(total_length, "mm"),
                "segment_acoustic_length": measurement(segment_length, "mm"),
                "center_spacing": measurement(center_spacing, "mm"),
                "inner_diameter": measurement(diameter, "mm"),
                "cross_sectional_area": measurement(current_round_area, "mm^2"),
            },
            "segments": [
                {
                    "id": f"{tube}_{section}",
                    "tube": tube,
                    "start": measurement(start, "mm"),
                    "end": measurement(end, "mm"),
                }
                for tube in ("TX", "RX")
                for section, start, end in (
                    ("front", 0.0, segment_length),
                    ("rear", segment_length, total_length),
                )
            ],
            "end_roles": {
                "TX_near": "speaker",
                "RX_near": "microphone",
                "TX_far": "closed",
                "RX_far": "closed",
            },
            "nodes": [
                {"id": node_id, "position": measurement(position, "mm")}
                for node_id, position in zip(node_ids, node_positions, strict=True)
            ],
        },
        "modules": modules,
        "boundary_conditions": {
            "unpopulated_node_requirement": "BLK_required",
            "BLK_interpretation": "closed_not_open",
            "formal_speaker_count": 1,
            "formal_microphone_count": 1,
        },
        "stage_four": {"recommended_nodes": stage_four_nodes},
        "calibration": resolved_calibration,
        "manufacturing": {
            "physical_print_confirmed": True,
            "printer": actual_print["printer"],
            "build_plate": actual_print["build_plate"],
            "slicer": actual_print["slicer"],
            "material": actual_print["material"],
            "actual_print_setting": actual_print_settings,
            "operator": actual_print["operator"],
            "print_date": actual_print["print_date"],
            "calibration_test_date": actual_print["calibration_test_date"],
            "environment": actual_print["environment"],
            "fit_cycle_counts": actual_print["fit_cycle_counts"],
            "verification": actual_print["verification"],
            "measurement": actual_print["measurement"],
            "post_processing": actual_print["post_processing"],
            "design_recommendation": design_recommendation,
        },
        "bill_of_materials": {
            "authoritative_source": "reports/BOM_calibrated_v1_3.csv",
            "quantities": bom_quantities,
        },
        "validation": {
            "formal_part_types": audit_counts["formal_part_types"],
            "stl_files": audit_counts["stl_files"],
            "step_files": audit_counts["step_files"],
            "assembly_files": audit_counts["assembly_files"],
            "print_batches": audit_counts["batch_folders"],
            "calibration_files": audit_counts["calibration_files"],
            "completeness": package_results["completeness"],
            "printability": package_results["printability"],
            "mechanical_validation": package_results["mechanical_validation"],
        },
        "provenance": {
            "priority_order": [
                "V1.3 package explicit source geometry",
                "user-confirmed actual print and calibration record",
                "V1.3 package explicitly derived acoustics",
                "derived values recomputed from V1.3 source geometry",
                "general engineering knowledge",
            ],
            "fields": fields,
            "conflicts": conflicts,
        },
        "warnings": audit["warnings"],
        "missing_information": missing_information,
    }
    manufacturing = _object(manifest["manufacturing"], "/manufacturing")
    missing_information.extend(collect_null_pointers(manufacturing, "/manufacturing"))
    manifest_calibration = _object(manifest["calibration"], "/calibration")
    missing_information.extend(collect_null_pointers(manifest_calibration, "/calibration"))
    manifest["missing_information"] = sorted(set(missing_information))
    return manifest


def write_manifest(manifest: JsonObject, output_path: str | Path, sidecar_path: str | Path) -> str:
    """Write canonical manifest bytes and its stable SHA256 sidecar."""

    output = Path(output_path)
    data = canonical_json_bytes(manifest)
    output.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    Path(sidecar_path).write_text(f"{digest}  {output.name}\n", encoding="ascii", newline="\n")
    return digest


def verify_sidecar(manifest_path: str | Path, sidecar_path: str | Path) -> str:
    """Verify and return the digest recorded for an existing manifest."""

    manifest = Path(manifest_path)
    tokens = Path(sidecar_path).read_text(encoding="ascii").strip().split()
    if len(tokens) != 2 or tokens[1] != manifest.name:
        raise ManifestError("Malformed manifest SHA256 sidecar")
    actual = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if tokens[0].lower() != actual:
        raise ManifestError(f"Manifest sidecar mismatch: expected {tokens[0]}, calculated {actual}")
    return actual


def recompute_sidecar(manifest_path: str | Path, sidecar_path: str | Path) -> str:
    """Recompute a manifest sidecar from its current bytes."""

    manifest = Path(manifest_path)
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    Path(sidecar_path).write_text(f"{digest}  {manifest.name}\n", encoding="ascii", newline="\n")
    return digest


def validate_manifest_file(manifest_path: str | Path, schema_path: str | Path) -> None:
    """Validate a manifest against the committed Draft 2020-12 schema."""

    try:
        manifest: Any = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        schema: Any = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read manifest or schema: {exc}") from exc
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        messages = [
            f"/{'/'.join(str(part) for part in error.path)}: {error.message}" for error in errors
        ]
        raise ManifestError("Manifest schema validation failed:\n" + "\n".join(messages))
