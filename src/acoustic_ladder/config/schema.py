"""Deterministic JSON Schema export directly from active Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from acoustic_ladder.audio.baseline_difference import ProvisionalBaselineDifferenceMetrics
from acoustic_ladder.audio.baseline_difference_models import ProvisionalBaselineDifferenceReceipt
from acoustic_ladder.audio.condition_plan_models import DevelopmentConditionPlan
from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    ConditionedVirtualCaptureReceipt,
)
from acoustic_ladder.audio.ess_processing_models import EssProcessingReceipt
from acoustic_ladder.audio.excitation_models import EssArtifactMetadata, EssSignalSpec
from acoustic_ladder.audio.models import (
    AudioInventoryCaptureContext,
    AudioInventorySnapshot,
    AudioPreflightReport,
    ContextualAudioPreflightReport,
    HardwareSetupRecord,
)
from acoustic_ladder.audio.provisional_qc_models import (
    ProvisionalQcMetrics,
    ProvisionalQcReceipt,
)
from acoustic_ladder.audio.repeatability_models import (
    ConditionedProvisionalRepeatabilityReceipt,
    ProvisionalRepeatabilityMetrics,
    ProvisionalRepeatabilityReceipt,
)
from acoustic_ladder.audio.virtual_capture_models import (
    VirtualCaptureReceipt,
    VirtualCaptureScenario,
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
from acoustic_ladder.protocol.planning_models import (
    CompiledDevelopmentProtocolPlan,
    DevelopmentProtocolPlanSpec,
    ProtocolPlanReceipt,
    ProtocolPlanRecord,
)
from acoustic_ladder.protocol.rehearsal_models import (
    ProtocolRehearsalCompletion,
    ProtocolRehearsalEvent,
    ProtocolRehearsalManifest,
    ProtocolRehearsalRecord,
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
ESS_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "ess_signal_spec.schema.json": EssSignalSpec,
    "ess_artifact_metadata.schema.json": EssArtifactMetadata,
}
VIRTUAL_CAPTURE_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "virtual_capture_scenario.schema.json": VirtualCaptureScenario,
    "virtual_capture_receipt.schema.json": VirtualCaptureReceipt,
}
ESS_PROCESSING_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "ess_processing_receipt.schema.json": EssProcessingReceipt,
}
PROVISIONAL_QC_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "provisional_qc_metrics.schema.json": ProvisionalQcMetrics,
    "provisional_qc_receipt.schema.json": ProvisionalQcReceipt,
}
REPEATABILITY_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "provisional_repeatability_metrics.schema.json": ProvisionalRepeatabilityMetrics,
    "provisional_repeatability_receipt.schema.json": ProvisionalRepeatabilityReceipt,
}
CONDITION_BASELINE_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "development_condition_plan.schema.json": DevelopmentConditionPlan,
    "conditioned_virtual_capture_receipt.schema.json": ConditionedVirtualCaptureReceipt,
    "conditioned_provisional_repeatability_receipt.schema.json": (
        ConditionedProvisionalRepeatabilityReceipt
    ),
    "provisional_baseline_difference_metrics.schema.json": (ProvisionalBaselineDifferenceMetrics),
    "provisional_baseline_difference_receipt.schema.json": (ProvisionalBaselineDifferenceReceipt),
}
PROTOCOL_PLAN_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "development_protocol_plan_spec.schema.json": DevelopmentProtocolPlanSpec,
    "compiled_protocol_plan.schema.json": CompiledDevelopmentProtocolPlan,
    "protocol_plan_receipt.schema.json": ProtocolPlanReceipt,
    "protocol_plan_record.schema.json": ProtocolPlanRecord,
}
PROTOCOL_REHEARSAL_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "protocol_rehearsal_manifest.schema.json": ProtocolRehearsalManifest,
    "protocol_rehearsal_record.schema.json": ProtocolRehearsalRecord,
    "protocol_rehearsal_event.schema.json": ProtocolRehearsalEvent,
    "protocol_rehearsal_completion.schema.json": ProtocolRehearsalCompletion,
}
ALL_GENERATED_SCHEMA_MODELS = (
    GENERATED_SCHEMA_MODELS
    | ESS_SCHEMA_MODELS
    | VIRTUAL_CAPTURE_SCHEMA_MODELS
    | ESS_PROCESSING_SCHEMA_MODELS
    | PROVISIONAL_QC_SCHEMA_MODELS
    | REPEATABILITY_SCHEMA_MODELS
    | CONDITION_BASELINE_SCHEMA_MODELS
    | PROTOCOL_PLAN_SCHEMA_MODELS
    | PROTOCOL_REHEARSAL_SCHEMA_MODELS
)


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
    for filename, model in ALL_GENERATED_SCHEMA_MODELS.items():
        path = output / filename
        path.write_bytes(schema_bytes(model))
        paths.append(path)
    return paths


def check_schemas(output_dir: str | Path) -> None:
    output = Path(output_dir)
    drift = [
        filename
        for filename, model in ALL_GENERATED_SCHEMA_MODELS.items()
        if not (output / filename).is_file()
        or (output / filename).read_bytes() != schema_bytes(model)
    ]
    if drift:
        raise SchemaDriftError(f"committed schemas are missing or stale: {drift}")
