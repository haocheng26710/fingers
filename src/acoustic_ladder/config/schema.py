"""Deterministic JSON Schema export directly from active Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from acoustic_ladder.audio.models import (
    AudioInventoryCaptureContext,
    AudioInventorySnapshot,
    AudioPreflightReport,
    ContextualAudioPreflightReport,
    HardwareSetupRecord,
)
from acoustic_ladder.config.models import (
    AnalysisConfig,
    AudioConfig,
    ProtocolConfig,
    SyntheticConfig,
)
from acoustic_ladder.domain.models import (
    ArtifactRef,
    MeasurementRunRecord,
    ReassemblyRecord,
    SessionRecord,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "audio_config.schema.json": AudioConfig,
    "protocol_config.schema.json": ProtocolConfig,
    "analysis_config.schema.json": AnalysisConfig,
    "synthetic_config.schema.json": SyntheticConfig,
    "session_record.schema.json": SessionRecord,
    "reassembly_record.schema.json": ReassemblyRecord,
    "measurement_run_record.schema.json": MeasurementRunRecord,
    "artifact_ref.schema.json": ArtifactRef,
}
AUDIO_ARTIFACT_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "audio_inventory_snapshot.schema.json": AudioInventorySnapshot,
    "hardware_setup_record.schema.json": HardwareSetupRecord,
    "audio_preflight_report.schema.json": AudioPreflightReport,
}
ALL_SCHEMA_MODELS = SCHEMA_MODELS | AUDIO_ARTIFACT_SCHEMA_MODELS
CONTEXT_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "audio_inventory_capture_context.schema.json": AudioInventoryCaptureContext,
    "contextual_audio_preflight_report.schema.json": ContextualAudioPreflightReport,
}
GENERATED_SCHEMA_MODELS = ALL_SCHEMA_MODELS | CONTEXT_SCHEMA_MODELS


class SchemaDriftError(ValueError):
    """Raised when committed schemas differ from active model exports."""


def schema_bytes(model: type[BaseModel]) -> bytes:
    schema = model.model_json_schema(mode="validation")
    return (
        json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def export_schemas(output_dir: str | Path) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, model in GENERATED_SCHEMA_MODELS.items():
        path = output / filename
        path.write_bytes(schema_bytes(model))
        paths.append(path)
    return paths


def check_schemas(output_dir: str | Path) -> None:
    output = Path(output_dir)
    drift = [
        filename
        for filename, model in GENERATED_SCHEMA_MODELS.items()
        if not (output / filename).is_file()
        or (output / filename).read_bytes() != schema_bytes(model)
    ]
    if drift:
        raise SchemaDriftError(f"committed schemas are missing or stale: {drift}")
