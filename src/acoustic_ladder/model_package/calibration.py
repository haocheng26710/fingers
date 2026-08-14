"""Validation and normalization for the user-confirmed V1.3 calibration record."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acoustic_ladder.model_package.models import JsonObject, JsonValue
from acoustic_ladder.model_package.provenance import json_compatible

REQUIRED_NULL_POINTERS = (
    "/confirmation_time",
    "/actual_print_record/printer/model",
    "/actual_print_record/printer/firmware_version",
    "/actual_print_record/material/type",
    "/actual_print_record/material/brand",
    "/actual_print_record/material/model",
    "/actual_print_record/material/color",
    "/actual_print_record/material/batch",
    "/actual_print_record/material/dried",
    "/actual_print_record/material/drying_temperature_c",
    "/actual_print_record/material/drying_duration_h",
    "/actual_print_record/slicer/version",
    "/actual_print_record/settings/nozzle_diameter_mm",
    "/actual_print_record/settings/layer_height_mm",
    "/actual_print_record/settings/line_width_mm",
    "/actual_print_record/settings/wall_count",
    "/actual_print_record/settings/top_layers",
    "/actual_print_record/settings/bottom_layers",
    "/actual_print_record/settings/infill_percent",
    "/actual_print_record/settings/infill_pattern",
    "/actual_print_record/settings/nozzle_temperature_c",
    "/actual_print_record/settings/bed_temperature_c",
    "/actual_print_record/settings/print_speed_mm_s",
    "/actual_print_record/settings/first_layer_speed_mm_s",
    "/actual_print_record/settings/flow_ratio",
    "/actual_print_record/settings/pressure_advance_or_flow_dynamics",
    "/actual_print_record/settings/elephant_foot_compensation_mm",
    "/actual_print_record/settings/support_settings",
    "/actual_print_record/settings/brim_width_mm",
    "/actual_print_record/settings/seam_position",
    "/actual_print_record/settings/automatic_orientation_enabled",
    "/actual_print_record/settings/other_slicer_settings",
    "/actual_print_record/operator",
    "/actual_print_record/print_date",
    "/actual_print_record/calibration_test_date",
    "/actual_print_record/environment/temperature_c",
    "/actual_print_record/environment/humidity_percent",
    "/actual_print_record/fit_cycle_counts/module_interface",
    "/actual_print_record/fit_cycle_counts/end_interface",
    "/actual_print_record/fit_cycle_counts/split_joint_interface",
    "/actual_print_record/verification/low_pressure_leak_test/performed",
    "/actual_print_record/verification/low_pressure_leak_test/method",
    "/actual_print_record/verification/low_pressure_leak_test/result",
    "/actual_print_record/verification/spectral_repeatability_test/performed",
    "/actual_print_record/verification/spectral_repeatability_test/method",
    "/actual_print_record/verification/spectral_repeatability_test/result",
    "/actual_print_record/measurement/tool",
    "/actual_print_record/measurement/tool_accuracy",
    "/actual_print_record/post_processing/deburring_tool",
    "/actual_print_record/post_processing/sandpaper_specification",
    "/actual_print_record/post_processing/actual_material_removed",
)


class CalibrationRecordError(ValueError):
    """Raised when the user calibration record is incomplete or altered."""


def _pointer_get(document: JsonValue, pointer: str) -> JsonValue:
    current = document
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise CalibrationRecordError(f"Missing required calibration field {pointer}")
        current = current[token]
    return current


def load_calibration_record(path: str | Path) -> JsonObject:
    """Load and validate the normalized user record."""

    try:
        parsed: Any = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibrationRecordError(f"Cannot read calibration record: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CalibrationRecordError("Calibration record must be a JSON object")
    record = {str(key): json_compatible(value) for key, value in parsed.items()}
    validate_calibration_record(record)
    return record


def validate_calibration_record(record: JsonObject) -> None:
    """Enforce source identity and preserve every explicitly unknown value as null."""

    if record.get("source_type") != "user_confirmed_measurement_record":
        raise CalibrationRecordError("Unexpected calibration source_type")
    if record.get("confirmation_date") != "2026-08-14":
        raise CalibrationRecordError("Unexpected calibration confirmation_date")
    for pointer in REQUIRED_NULL_POINTERS:
        if _pointer_get(record, pointer) is not None:
            raise CalibrationRecordError(f"Unknown field must remain null: {pointer}")
    holes = _pointer_get(record, "/calibration/acoustic_holes/measured_diameters_mm")
    if holes != [None, None, None, None, None]:
        raise CalibrationRecordError("Acoustic-hole measured diameters must remain explicit nulls")


def canonical_json_bytes(document: JsonObject) -> bytes:
    """Serialize JSON deterministically as UTF-8 with LF newlines."""

    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def render_calibration_markdown(record: JsonObject) -> str:
    """Render the normalized record as a faithful human-readable account."""

    calibration = record["calibration"]
    assert isinstance(calibration, dict)
    actual = record["actual_print_record"]
    assert isinstance(actual, dict)
    lines = [
        "# V1.3 User-Confirmed Calibration Record",
        "",
        f"- Source type: `{record['source_type']}`",
        f"- Confirmation date: `{record['confirmation_date']}`",
        "- Confirmation time: `null` (not provided)",
        "- Rule: user-confirmed facts only; every unknown remains explicit `null`.",
    ]
    section_names = (
        ("Module dry-seal interface", "module_dry_seal"),
        ("End dry-seal interface", "end_dry_seal"),
        ("Split-joint dry-seal interface", "split_joint_dry_seal"),
        ("Bridge and acoustic-hole compensation", "acoustic_holes"),
        ("Slider and wedge", "slider_and_wedge"),
    )
    for heading, key in section_names:
        lines.extend(
            [
                "",
                f"## {heading}",
                "",
                "```json",
                json.dumps(calibration[key], ensure_ascii=False, sort_keys=True, indent=2),
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "## Actual print record",
            "",
            "This is distinct from the package design recommendation below.",
            "",
            "```json",
            json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
            "",
            "## Design recommendation (not an actual print setting)",
            "",
            "```json",
            json.dumps(
                record["design_recommendation"], ensure_ascii=False, sort_keys=True, indent=2
            ),
            "```",
            "",
            "## Required unknown fields",
            "",
        ]
    )
    lines.extend(f"- `{pointer}`" for pointer in REQUIRED_NULL_POINTERS)
    lines.extend(
        [
            "",
            "Low-pressure leak and spectral-repeatability testing were not performed or recorded.",
            "No result is inferred.",
            "",
        ]
    )
    return "\n".join(lines)


def normalize_calibration_record(
    input_path: str | Path,
    output_json_path: str | Path,
    output_markdown_path: str | Path,
) -> JsonObject:
    """Validate then write canonical machine- and human-readable records."""

    record = load_calibration_record(input_path)
    Path(output_json_path).write_bytes(canonical_json_bytes(record))
    Path(output_markdown_path).write_text(
        render_calibration_markdown(record), encoding="utf-8", newline="\n"
    )
    return record
