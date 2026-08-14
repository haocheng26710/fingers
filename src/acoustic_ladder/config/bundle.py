"""Layered configuration loading, normalization, provenance and content hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from acoustic_ladder.config.models import (
    AnalysisConfig,
    AudioConfig,
    ConfigModel,
    ProtocolConfig,
    SyntheticConfig,
    resolve_protocol_against_manifest,
)
from acoustic_ladder.config.yaml_loader import load_yaml_mapping
from acoustic_ladder.domain.models import ConfigLayer, ConfigSnapshot
from acoustic_ladder.domain.paths import validate_relative_path
from acoustic_ladder.model_package.archive import sha256_file
from acoustic_ladder.model_package.normalize import verify_sidecar

ConfigKind = Literal["audio", "protocol", "analysis", "synthetic"]


class ConfigValidationError(ValueError):
    """Configuration error with the Pydantic field path preserved."""


class ConfigBundle(BaseModel):
    """Runtime receipt; loaded_at is recorded but excluded from the content digest."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str
    device_manifest_sha256: str
    snapshots: dict[str, ConfigSnapshot]
    normalized_config_hashes: dict[str, str]
    bundle_content_sha256: str
    loaded_at: AwareDatetime
    validation_status: Literal["valid"]


@dataclass(frozen=True)
class LoadedConfig:
    kind: ConfigKind
    model: ConfigModel
    snapshot: ConfigSnapshot
    original_bytes: bytes
    normalized_bytes: bytes


@dataclass(frozen=True)
class LoadedBundle:
    receipt: ConfigBundle
    manifest: dict[str, object]
    manifest_bytes: bytes
    manifest_sidecar_bytes: bytes
    configs: dict[ConfigKind, LoadedConfig]


MODEL_BY_KIND: dict[ConfigKind, type[ConfigModel]] = {
    "audio": AudioConfig,
    "protocol": ProtocolConfig,
    "analysis": AnalysisConfig,
    "synthetic": SyntheticConfig,
}
LAYER_BY_KIND: dict[ConfigKind, ConfigLayer] = {
    "audio": "audio_config",
    "protocol": "protocol_config",
    "analysis": "analysis_config",
    "synthetic": "synthetic_config",
}


def canonical_json_bytes(value: object) -> bytes:
    """Stable UTF-8 JSON used for all configuration content hashes."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _relative_to_project(path: Path, project_root: Path) -> str:
    resolved_path = path.resolve()
    resolved_root = project_root.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ConfigValidationError(f"configuration path is outside project root: {path}")
    return validate_relative_path(resolved_path.relative_to(resolved_root).as_posix())


def _format_validation_error(path: Path, error: ValidationError) -> ConfigValidationError:
    details = []
    for item in error.errors(include_url=False):
        location = "/" + "/".join(str(part) for part in item["loc"])
        details.append(f"{location}: {item['msg']}")
    return ConfigValidationError(f"invalid {path}:\n" + "\n".join(details))


def load_config(
    kind: ConfigKind,
    path: str | Path,
    *,
    project_root: str | Path,
    manifest: dict[str, object] | None = None,
) -> LoadedConfig:
    """Safely load, strictly validate and normalize one YAML layer."""

    config_path = Path(path)
    raw = config_path.read_bytes()
    data = load_yaml_mapping(config_path)
    try:
        model = MODEL_BY_KIND[kind].model_validate_json(
            json.dumps(data, ensure_ascii=False, allow_nan=False)
        )
    except ValidationError as exc:
        raise _format_validation_error(config_path, exc) from exc
    if kind == "protocol":
        if manifest is None:
            raise ConfigValidationError("protocol validation requires a device manifest")
        assert isinstance(model, ProtocolConfig)
        try:
            model = resolve_protocol_against_manifest(model, manifest)
        except ValueError as exc:
            raise ConfigValidationError(f"invalid {config_path}: {exc}") from exc
    normalized = canonical_json_bytes(model.model_dump(mode="json"))
    snapshot = ConfigSnapshot(
        layer=LAYER_BY_KIND[kind],
        original_relative_path=_relative_to_project(config_path, Path(project_root)),
        original_sha256=hashlib.sha256(raw).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        validation_status="valid",
    )
    return LoadedConfig(kind, model, snapshot, raw, normalized)


def load_device_manifest(
    manifest_path: str | Path,
    sidecar_path: str | Path,
    *,
    project_root: str | Path,
) -> tuple[dict[str, object], bytes, bytes, ConfigSnapshot]:
    """Verify the committed sidecar before accepting a manifest into a bundle."""

    manifest_file = Path(manifest_path)
    sidecar_file = Path(sidecar_path)
    verified = verify_sidecar(manifest_file, sidecar_file)
    raw = manifest_file.read_bytes()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(f"invalid device manifest JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigValidationError("device manifest must be a JSON object")
    normalized = canonical_json_bytes(parsed)
    snapshot = ConfigSnapshot(
        layer="device_manifest",
        original_relative_path=_relative_to_project(manifest_file, Path(project_root)),
        original_sha256=verified,
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        validation_status="valid",
    )
    return parsed, raw, sidecar_file.read_bytes(), snapshot


def load_bundle(
    *,
    project_root: str | Path,
    manifest_path: str | Path,
    manifest_sidecar_path: str | Path,
    audio_path: str | Path,
    protocol_path: str | Path,
    analysis_path: str | Path,
    synthetic_path: str | Path | None,
    now: Callable[[], datetime],
) -> LoadedBundle:
    """Load all four required layers plus an optional independent synthetic layer."""

    root = Path(project_root)
    manifest, manifest_bytes, sidecar_bytes, manifest_snapshot = load_device_manifest(
        manifest_path, manifest_sidecar_path, project_root=root
    )
    paths: dict[ConfigKind, str | Path] = {
        "audio": audio_path,
        "protocol": protocol_path,
        "analysis": analysis_path,
    }
    if synthetic_path is not None:
        paths["synthetic"] = synthetic_path
    loaded = {
        kind: load_config(kind, path, project_root=root, manifest=manifest)
        for kind, path in paths.items()
    }
    protocol = loaded["protocol"].model
    assert isinstance(protocol, ProtocolConfig)
    actual_manifest_sha256 = sha256_file(manifest_path)
    expected_manifest_reference = _relative_to_project(Path(manifest_path), root)
    if protocol.device_manifest_reference != expected_manifest_reference:
        raise ConfigValidationError(
            "protocol device_manifest_reference does not match the loaded manifest: "
            f"{protocol.device_manifest_reference!r} != {expected_manifest_reference!r}"
        )
    if protocol.device_manifest_sha256 != actual_manifest_sha256:
        raise ConfigValidationError(
            "protocol device_manifest_sha256 does not match the verified manifest: "
            f"{protocol.device_manifest_sha256!r} != {actual_manifest_sha256!r}"
        )
    snapshots = {"device_manifest": manifest_snapshot}
    snapshots.update({f"{kind}_config": item.snapshot for kind, item in loaded.items()})
    hashes = {name: snapshot.normalized_sha256 for name, snapshot in snapshots.items()}
    digest_payload = {
        "schema_version": "1.0.0",
        "device_manifest_sha256": actual_manifest_sha256,
        "normalized_config_hashes": hashes,
    }
    loaded_at = now()
    if loaded_at.tzinfo is None or loaded_at.utcoffset() is None:
        raise ConfigValidationError("bundle loading time must be timezone-aware")
    receipt = ConfigBundle(
        schema_version="1.0.0",
        device_manifest_sha256=actual_manifest_sha256,
        snapshots=snapshots,
        normalized_config_hashes=hashes,
        bundle_content_sha256=content_sha256(digest_payload),
        loaded_at=loaded_at,
        validation_status="valid",
    )
    return LoadedBundle(receipt, manifest, manifest_bytes, sidecar_bytes, loaded)
