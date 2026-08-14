"""Read and audit model ZIP files without importing or executing their source code."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import posixpath
import re
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from acoustic_ladder import __version__
from acoustic_ladder.model_package.models import JsonObject, JsonValue
from acoustic_ladder.model_package.provenance import json_compatible

EXPECTED_V1_3_SHA256 = "1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b"

REQUIRED_PATHS = (
    "README_V1_3_校准后正式打印说明.md",
    "reports/params_calibrated_v1_3.json",
    "reports/calibration_applied_v1_3.json",
    "reports/校准数据应用说明_V1_3.md",
    "reports/V1_3_修改与保留清单.md",
    "reports/BOM_calibrated_v1_3.csv",
    "reports/BOM.csv",
    "reports/打印批次清单_V1_3.csv",
    "reports/package_completeness_v1_3.json",
    "reports/printability_audit_v1_3.json",
    "reports/printability_audit_v1_3.txt",
    "reports/validation_report_v1_3.txt",
    "reports/validation_report_v1.txt",
    "reports/derived_acoustics_v1.json",
    "reports/dry_seal_dimensions_v1.json",
    "reports/dry_seal_dimensions_v1.txt",
    "reports/acoustic_design_report_v1.md",
    "source/v1_params.py",
    "source/build_v1_3_calibrated_package.py",
    "source/bom.py",
    "source/parts/main_tubes.py",
    "source/parts/modules.py",
    "source/parts/end_adapters.py",
)

JSON_REPORTS = (
    "reports/params_calibrated_v1_3.json",
    "reports/calibration_applied_v1_3.json",
    "reports/package_completeness_v1_3.json",
    "reports/printability_audit_v1_3.json",
    "reports/derived_acoustics_v1.json",
    "reports/dry_seal_dimensions_v1.json",
)

CSV_REPORTS = (
    "reports/BOM_calibrated_v1_3.csv",
    "reports/BOM.csv",
    "reports/打印批次清单_V1_3.csv",
)


class ModelPackageError(RuntimeError):
    """Base class for model-package validation failures."""


class ArchiveSafetyError(ModelPackageError):
    """Raised when a ZIP contains an unsafe path or duplicate normalized path."""


class MissingRequiredEntryError(ModelPackageError):
    """Raised when a required package entry is absent."""


class PackageParseError(ModelPackageError):
    """Raised when a required structured report cannot be parsed."""


class PackageConflictError(ModelPackageError):
    """Raised when the archive contradicts its own completeness claims."""


class HashMismatchError(ModelPackageError):
    """Raised when a caller-supplied archive digest does not match."""


def sha256_file(path: str | Path) -> str:
    """Return a streaming SHA256 digest for a file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_text(data: bytes) -> str:
    """Decode package text using UTF-8 while accepting an optional BOM."""

    return data.decode("utf-8-sig")


def classify_entry(path: str) -> str:
    """Classify an archive entry using only its path."""

    normalized = path.replace("\\", "/").lower()
    if normalized.endswith("/"):
        return "directory"
    if "/assemblies/" in normalized and normalized.endswith(".step"):
        return "assembly_step"
    if "/step/" in normalized and normalized.endswith(".step"):
        return "part_step"
    if normalized.endswith(".stl"):
        return "stl"
    if normalized.endswith(".py"):
        return "python_source"
    if normalized.endswith(".json"):
        return "json_report"
    if normalized.endswith(".csv"):
        return "csv_report"
    if normalized.endswith(".md"):
        return "markdown"
    if normalized.endswith(".txt"):
        return "text_report"
    return "other"


def _canonical_path(name: str) -> str:
    return posixpath.normpath(name.replace("\\", "/")).casefold()


def _path_flags(name: str) -> tuple[bool, bool]:
    portable = name.replace("\\", "/")
    parts = PurePosixPath(portable).parts
    is_absolute = (
        portable.startswith("/")
        or name.startswith("\\")
        or PureWindowsPath(name).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", name))
    )
    has_traversal = ".." in parts
    return is_absolute, has_traversal


def _relative_path(name: str) -> str:
    portable = name.replace("\\", "/")
    return portable.split("/", 1)[1] if "/" in portable else portable


def _find_info(archive: zipfile.ZipFile, relative_path: str) -> zipfile.ZipInfo:
    matches = [
        info for info in archive.infolist() if _relative_path(info.filename) == relative_path
    ]
    if len(matches) != 1:
        raise MissingRequiredEntryError(
            f"Expected exactly one entry ending in {relative_path!r}; found {len(matches)}"
        )
    return matches[0]


def read_entry(archive: zipfile.ZipFile, relative_path: str) -> bytes:
    """Read one entry selected by its path relative to the package root."""

    return archive.read(_find_info(archive, relative_path))


def read_json(archive: zipfile.ZipFile, relative_path: str) -> JsonObject:
    """Parse one required JSON object without evaluating any package code."""

    try:
        parsed: Any = json.loads(decode_text(read_entry(archive, relative_path)))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, OSError) as exc:
        raise PackageParseError(f"Invalid JSON in {relative_path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PackageParseError(f"Expected a JSON object in {relative_path}")
    return {str(key): json_compatible(value) for key, value in parsed.items()}


def read_csv(archive: zipfile.ZipFile, relative_path: str) -> list[dict[str, str]]:
    """Parse a UTF-8/UTF-8-SIG CSV report with strict quote handling."""

    try:
        text = decode_text(read_entry(archive, relative_path))
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if reader.fieldnames is None or any(not name for name in reader.fieldnames):
            raise csv.Error("missing or empty header")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error, KeyError, OSError) as exc:
        raise PackageParseError(f"Invalid CSV in {relative_path}: {exc}") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise PackageParseError(f"Inconsistent column count in {relative_path}")
    return [{str(key): str(value) for key, value in row.items()} for row in rows]


def _null_pointers(value: JsonValue, prefix: str = "") -> list[str]:
    pointers: list[str] = []
    if value is None:
        return [prefix or "/"]
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            pointers.extend(_null_pointers(child, f"{prefix}/{escaped}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            pointers.extend(_null_pointers(child, f"{prefix}/{index}"))
    return pointers


def _warning(code: str, message: str, evidence: list[str]) -> JsonObject:
    return {"code": code, "severity": "warning", "message": message, "evidence": evidence}


def _known_warnings(
    names: set[str],
    texts: dict[str, str],
    calibration_record: JsonObject | None,
    bom_mismatch: bool,
) -> list[JsonObject]:
    warnings: list[JsonObject] = []
    derived = json.loads(texts["reports/derived_acoustics_v1.json"])
    if "main_teardrop" in derived:
        warnings.append(
            _warning(
                "DERIVED_FIELD_NAME_MAIN_TEARDROP",
                (
                    "derived_acoustics_v1.json retains the historical main_teardrop field "
                    "name; the active V1.3 lumen is round."
                ),
                [
                    "reports/derived_acoustics_v1.json#/main_teardrop",
                    "reports/params_calibrated_v1_3.json#/VERSION",
                ],
            )
        )
    warnings.append(
        _warning(
            "LEGACY_REPORT_TITLES",
            "The acoustic design Markdown and dry-seal TXT retain V1.0-era titles.",
            ["reports/acoustic_design_report_v1.md", "reports/dry_seal_dimensions_v1.txt"],
        )
    )
    if bom_mismatch:
        warnings.append(
            _warning(
                "SOURCE_BOM_WEDGE_QUANTITY_MISMATCH",
                (
                    "source/bom.py retains L/H wedge quantities that differ from the formal "
                    "calibrated BOM."
                ),
                ["reports/BOM_calibrated_v1_3.csv", "source/bom.py"],
            )
        )
    build_text = texts["source/build_v1_3_calibrated_package.py"]
    for module, code in (
        ("acoustic_calcs.py", "MISSING_ACOUSTIC_CALCS_SOURCE"),
        ("build_v1.py", "MISSING_BUILD_V1_SOURCE"),
    ):
        if module.removesuffix(".py") in build_text and not any(
            name.endswith(f"source/{module}") for name in names
        ):
            warnings.append(
                _warning(
                    code,
                    (
                        f"The packaged build script references {module}, but that source file "
                        "is not packaged."
                    ),
                    ["source/build_v1_3_calibrated_package.py"],
                )
            )
    if not any(
        name.endswith(("pyproject.toml", "requirements.txt", "requirements.lock", "uv.lock"))
        for name in names
    ):
        warnings.append(
            _warning(
                "CAD_REBUILD_ENVIRONMENT_NOT_LOCKED",
                "The package does not contain a complete version-locked CAD rebuild environment.",
                ["source/"],
            )
        )
    warnings.append(
        _warning(
            "RAW_CALIBRATION_MEASUREMENTS_MISSING",
            "The package contains applied calibration reports but no raw coupon measurement table.",
            ["reports/calibration_applied_v1_3.json"],
        )
    )
    if calibration_record is None or _null_pointers(calibration_record):
        warnings.append(
            _warning(
                "ACTUAL_PRINT_FIELDS_INCOMPLETE",
                (
                    "User-confirmed actual printing and test information intentionally "
                    "contains explicit null fields."
                ),
                ["reference/calibration/V1_3_user_calibration_record.json"],
            )
        )
    warnings.append(
        _warning(
            "LEAK_AND_SPECTRAL_TESTS_UNRECORDED",
            (
                "Low-pressure leak testing and spectral repeatability testing were not "
                "performed or not recorded."
            ),
            ["reference/calibration/V1_3_user_calibration_record.json#/verification"],
        )
    )
    return warnings


def _bom_quantities(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    try:
        return {row["part_name"]: int(row["quantity"]) for row in rows}
    except (KeyError, ValueError) as exc:
        raise PackageParseError(f"Invalid formal BOM quantity: {exc}") from exc


def _source_wedge_quantities(source_text: str) -> dict[str, int]:
    matches = re.findall(r'\("ALV1_slider_lock_wedge_([LMH])",\s*(\d+)', source_text)
    return {f"ALV1_slider_lock_wedge_{label}": int(quantity) for label, quantity in matches}


def _scan_entries(archive: zipfile.ZipFile) -> tuple[list[JsonObject], set[str]]:
    entries: list[JsonObject] = []
    names: set[str] = set()
    normalized_seen: dict[str, str] = {}
    unsafe: list[str] = []
    for info in archive.infolist():
        name = info.filename
        is_absolute, has_traversal = _path_flags(name)
        canonical = _canonical_path(name)
        duplicate = canonical in normalized_seen
        if is_absolute or has_traversal or duplicate:
            unsafe.append(name)
        normalized_seen.setdefault(canonical, name)
        try:
            data = archive.read(info)
            read_success = True
            read_error: str | None = None
            entry_hash: str | None = hashlib.sha256(data).hexdigest()
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            read_success = False
            read_error = str(exc)
            entry_hash = None
            data = b""
        relative = _relative_path(name)
        names.add(relative)
        entries.append(
            {
                "path": name,
                "relative_path": relative,
                "uncompressed_size_bytes": info.file_size,
                "compressed_size_bytes": info.compress_size,
                "sha256": entry_hash,
                "category": classify_entry(name),
                "required": relative in REQUIRED_PATHS,
                "read_success": read_success,
                "read_error": read_error,
                "is_absolute_path": is_absolute,
                "has_parent_traversal": has_traversal,
                "duplicate_normalized_path": duplicate,
            }
        )
    if unsafe:
        raise ArchiveSafetyError(f"Unsafe ZIP entry paths: {unsafe}")
    unreadable = [entry["path"] for entry in entries if not entry["read_success"]]
    if unreadable:
        raise ModelPackageError(f"Unreadable ZIP entries: {unreadable}")
    return entries, names


def inspect_archive(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    calibration_record: JsonObject | None = None,
    scanned_at: str | None = None,
) -> JsonObject:
    """Return a complete, non-executing audit of a V1.3 model package."""

    archive_path = Path(path)
    actual_hash = sha256_file(archive_path)
    if expected_sha256 is not None and actual_hash != expected_sha256.lower():
        raise HashMismatchError(
            f"Archive SHA256 {actual_hash} does not match expected {expected_sha256.lower()}"
        )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries, names = _scan_entries(archive)
            missing = sorted(set(REQUIRED_PATHS) - names)
            python_entries = sorted(name for name in names if name.endswith(".py"))
            if missing:
                raise MissingRequiredEntryError(f"Missing required entries: {missing}")
            parsed_json = {name: read_json(archive, name) for name in JSON_REPORTS}
            parsed_csv = {name: read_csv(archive, name) for name in CSV_REPORTS}
            text_paths = (
                "reports/derived_acoustics_v1.json",
                "source/build_v1_3_calibrated_package.py",
                "source/bom.py",
            )
            texts = {name: decode_text(read_entry(archive, name)) for name in text_paths}
            validation_text = decode_text(read_entry(archive, "reports/validation_report_v1_3.txt"))
    except zipfile.BadZipFile as exc:
        raise ModelPackageError(f"Invalid ZIP archive: {exc}") from exc

    counts = {
        "stl_files": sum(entry["category"] == "stl" for entry in entries),
        "step_files": sum(entry["category"] == "part_step" for entry in entries),
        "assembly_files": sum(entry["category"] == "assembly_step" for entry in entries),
        "batch_folders": len(
            {
                str(entry["relative_path"]).split("/")[1]
                for entry in entries
                if str(entry["relative_path"]).startswith("stl/")
                and len(str(entry["relative_path"]).split("/")) > 2
            }
        ),
        "calibration_files": sum(
            "coupon" in str(entry["relative_path"]).lower() for entry in entries
        ),
    }
    completeness = parsed_json["reports/package_completeness_v1_3.json"]
    expected_counts = {
        "stl_files": completeness.get("stl_files"),
        "step_files": completeness.get("step_files"),
        "assembly_files": completeness.get("assembly_files"),
        "batch_folders": completeness.get("batch_folders"),
        "calibration_files": completeness.get("calibration_files"),
    }
    if counts != expected_counts:
        raise PackageConflictError(
            f"Archive counts {counts} disagree with package completeness report {expected_counts}"
        )
    validation_match = re.search(r"PASS=(\d+)\s+WARNING=(\d+)\s+FAIL=(\d+)", validation_text)
    if validation_match is None:
        raise PackageParseError("Mechanical validation summary was not found")
    validation_summary = {
        "pass": int(validation_match.group(1)),
        "warning": int(validation_match.group(2)),
        "fail": int(validation_match.group(3)),
    }
    official_bom = _bom_quantities(parsed_csv["reports/BOM_calibrated_v1_3.csv"])
    source_bom = _source_wedge_quantities(texts["source/bom.py"])
    wedge_names = [f"ALV1_slider_lock_wedge_{label}" for label in "LMH"]
    mismatch = any(official_bom.get(name) != source_bom.get(name) for name in wedge_names)
    conflicts: list[JsonValue] = []
    if mismatch:
        conflicts.append(
            {
                "code": "BOM_WEDGE_QUANTITY_CONFLICT",
                "field": "/bill_of_materials/wedge_quantities",
                "selected_source": "reports/BOM_calibrated_v1_3.csv",
                "selected_value": {name: official_bom.get(name) for name in wedge_names},
                "alternative_source": "source/bom.py",
                "alternative_value": {name: source_bom.get(name) for name in wedge_names},
                "resolution": "BOM_calibrated_v1_3.csv has higher declared priority",
            }
        )
    derived = parsed_json["reports/derived_acoustics_v1.json"]
    if "main_teardrop" in derived:
        conflicts.append(
            {
                "code": "ACTIVE_LUMEN_LABEL_CONFLICT",
                "field": "/architecture/main_tube/lumen_shape",
                "selected_source": "reports/params_calibrated_v1_3.json",
                "selected_value": "round",
                "alternative_source": "reports/derived_acoustics_v1.json#/main_teardrop",
                "alternative_value": "historical_field_label_main_teardrop",
                "resolution": (
                    "V1.3 source geometry and explicit special rule take priority; the "
                    "derived field is historical only"
                ),
            }
        )

    nulls = _null_pointers(calibration_record) if calibration_record is not None else []
    missing_information: list[JsonValue] = [
        "source/acoustic_calcs.py",
        "source/build_v1.py",
        "raw calibration coupon measurement table",
        *[f"user_calibration_record{pointer}" for pointer in nulls],
    ]
    parsed_results: list[JsonValue] = [
        {
            "path": name,
            "format": "json",
            "result": "PASS",
            "top_level_keys": sorted(parsed_json[name]),
        }
        for name in JSON_REPORTS
    ] + [
        {
            "path": name,
            "format": "csv",
            "result": "PASS",
            "row_count": len(parsed_csv[name]),
            "columns": list(parsed_csv[name][0]) if parsed_csv[name] else [],
        }
        for name in CSV_REPORTS
    ]
    params = parsed_json["reports/params_calibrated_v1_3.json"]
    calibration = parsed_json["reports/calibration_applied_v1_3.json"]
    printability = parsed_json["reports/printability_audit_v1_3.json"]
    return {
        "package_filename": archive_path.name,
        "package_sha256": actual_hash,
        "file_size_bytes": archive_path.stat().st_size,
        "scanned_at": scanned_at
        or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "entry_count": len(entries),
        "entries": entries,
        "safety": {
            "absolute_paths_found": False,
            "parent_traversal_found": False,
            "duplicate_normalized_paths_found": False,
            "all_entries_readable": True,
        },
        "required_files": {
            "required_count": len(REQUIRED_PATHS),
            "all_present": True,
            "missing": [],
            "python_sources_read_without_execution": python_entries,
        },
        "counts": {"formal_part_types": completeness["formal_part_types"], **counts},
        "parsed_files": parsed_results,
        "package_results": {
            "completeness": completeness["result"],
            "printability": printability["result"],
            "mechanical_validation": validation_summary,
        },
        "version_relationships": {
            "active_version": params["VERSION"],
            "source_geometry": calibration["source_geometry"],
            "derived_acoustics_version": derived["version"],
            "active_lumen_shape": "round",
        },
        "formal_bom_quantities": official_bom,
        "conflicts": conflicts,
        "warnings": _known_warnings(names, texts, calibration_record, mismatch),
        "missing_information": missing_information,
        "review_program_version": __version__,
    }
