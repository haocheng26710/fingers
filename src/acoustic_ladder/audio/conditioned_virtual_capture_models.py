"""Strict contracts for condition-aware development-only virtual capture."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from acoustic_ladder.audio.virtual_capture_models import (
    BlockTraceRecord,
    CaptureFaultCounters,
    StateTransitionRecord,
)
from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.config.yaml_loader import load_yaml_mapping
from acoustic_ladder.domain.models import ConfigSnapshot, NodeState
from acoustic_ladder.domain.paths import validate_relative_path

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ConditionedCaptureError(RuntimeError):
    """Condition-aware capture input or replay failure."""


class ConditionedCaptureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ConditionedVirtualCaptureScenario(ConditionedCaptureModel):
    schema_version: Literal["1.0.0"]
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    usage_scope: Literal["development_fixture"]
    backend_id: Literal["deterministic_conditioned_virtual_duplex"]
    backend_version: Literal["1.0.0"]
    block_size_frames: int = Field(gt=0)
    capture_tail_samples: int = Field(ge=0)
    fault_mode: Literal["none"]
    fault_block_index: None
    hardware_io_authorized: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]


@dataclass(frozen=True)
class LoadedConditionedVirtualCaptureScenario:
    model: ConditionedVirtualCaptureScenario
    source_path: Path
    project_root: Path
    original_relative_path: str
    original_bytes: bytes
    normalized_bytes: bytes
    original_sha256: str
    normalized_sha256: str


class ConditionedVirtualCaptureReceipt(ConditionedCaptureModel):
    schema_version: Literal["1.0.0"]
    capture_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    reassembly_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    measurement_order: int = Field(ge=0)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    backend_id: Literal["deterministic_conditioned_virtual_duplex"]
    backend_version: Literal["1.0.0"]
    scenario_reference: str
    scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    config_snapshots: dict[str, ConfigSnapshot]
    protocol_id: str
    protocol_execution_performed: Literal[False]
    condition_plan_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    condition_plan_reference: str
    condition_plan_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    condition_plan_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_protocol_reference: str
    source_protocol_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    source_protocol_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    condition_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    condition_role: Literal["all_blk_reference", "single_bridge_candidate"]
    resolved_node_states: dict[str, NodeState]
    resolved_node_states_sha256: str = Field(pattern=SHA256_PATTERN)
    condition_binding_performed: Literal[True]
    protocol_condition_binding_performed: Literal[True]
    synthetic_response_formula_id: Literal[
        "transparent_round_trip_delay_and_relative_aperture_coupling"
    ]
    synthetic_response_formula_version: Literal["1.0.0"]
    synthetic_ir_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    manifest_node_delay_samples: dict[str, int]
    manifest_module_node_weights: dict[str, float]
    source_ess_artifact_id: str
    source_ess_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    ess_sample_count: int = Field(gt=0)
    capture_tail_sample_count: int = Field(ge=0)
    capture_sample_count: int = Field(gt=0)
    block_size_frames: int = Field(gt=0)
    planned_block_count: int = Field(gt=0)
    actual_block_count: int = Field(gt=0)
    last_block_frame_count: int = Field(gt=0)
    output_shape: tuple[Literal[1], int]
    input_shape: tuple[Literal[1], int]
    output_dtype: Literal["float32"]
    input_dtype: Literal["float32"]
    output_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    input_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    output_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    input_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    block_trace: list[BlockTraceRecord]
    state_transition_trace: list[StateTransitionRecord]
    fault_counters: CaptureFaultCounters
    final_state: Literal["completed"]
    all_finite: Literal[True]
    create_only: Literal[True]
    immutable: Literal[True]
    virtual_duplex_scheduler_exercised: Literal[True]
    hardware_io_performed: Literal[False]
    playback_performed: Literal[False]
    recording_performed: Literal[False]
    hardware_ready: Literal[False]
    full_duplex_verified: Literal[False]
    shared_clock_verified: Literal[False]
    channel_mapping_verified: Literal[False]
    calibration_file_verified: Literal[False]
    calibration_applied: Literal[False]
    absolute_spl_calibrated: Literal[False]
    electrical_loopback_available: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_CONDITION_BOUND_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT"]

    @model_validator(mode="after")
    def provenance_and_shapes_are_consistent(self) -> ConditionedVirtualCaptureReceipt:
        for reference in (
            self.scenario_reference,
            self.condition_plan_reference,
            self.source_protocol_reference,
        ):
            validate_relative_path(reference)
        expected_snapshots = {
            "device_manifest",
            "audio_config",
            "protocol_config",
            "analysis_config",
            "synthetic_config",
        }
        if set(self.config_snapshots) != expected_snapshots:
            raise ValueError("conditioned receipt must bind all five config snapshots")
        if (
            self.output_shape != self.input_shape
            or self.output_shape[1] != self.capture_sample_count
        ):
            raise ValueError("conditioned capture shapes and sample count differ")
        if self.ess_sample_count + self.capture_tail_sample_count != self.capture_sample_count:
            raise ValueError("ESS and tail counts do not form conditioned capture count")
        if self.actual_block_count != self.planned_block_count:
            raise ValueError("conditioned capture did not execute every block")
        if set(self.resolved_node_states) != set(self.manifest_node_delay_samples) or set(
            self.resolved_node_states
        ) != set(self.manifest_module_node_weights):
            raise ValueError("conditioned node-state, delay and weight keys differ")
        canonical_states = canonical_json_bytes(
            {key: value.model_dump(mode="json") for key, value in self.resolved_node_states.items()}
        )
        if hashlib.sha256(canonical_states).hexdigest() != self.resolved_node_states_sha256:
            raise ValueError("resolved node-state digest differs")
        actual_non_blk = sum(
            state.module_id != "BLK" for state in self.resolved_node_states.values()
        )
        expected_non_blk = 0 if self.condition_role == "all_blk_reference" else 1
        if actual_non_blk != expected_non_blk:
            raise ValueError("resolved node states differ from conditioned role")
        if any(delay < 0 for delay in self.manifest_node_delay_samples.values()):
            raise ValueError("manifest-derived delays cannot be negative")
        return self


@dataclass(frozen=True)
class PublishedConditionedVirtualCapture:
    run_path: Path
    receipt: ConditionedVirtualCaptureReceipt
    receipt_sha256: str


def load_conditioned_virtual_capture_scenario(
    path: str | Path, *, project_root: str | Path
) -> LoadedConditionedVirtualCaptureScenario:
    scenario_path = Path(path).resolve()
    root = Path(project_root).resolve()
    if not scenario_path.is_relative_to(root):
        raise ConditionedCaptureError("conditioned scenario must be inside project root")
    relative = validate_relative_path(scenario_path.relative_to(root).as_posix())
    try:
        original = scenario_path.read_bytes()
        mapping = load_yaml_mapping(scenario_path)
        model = ConditionedVirtualCaptureScenario.model_validate_json(
            json.dumps(mapping, ensure_ascii=False, allow_nan=False)
        )
    except (OSError, ValueError) as exc:
        raise ConditionedCaptureError(f"invalid conditioned scenario {relative}: {exc}") from exc
    normalized = canonical_json_bytes(model.model_dump(mode="json"))
    return LoadedConditionedVirtualCaptureScenario(
        model=model,
        source_path=scenario_path,
        project_root=root,
        original_relative_path=relative,
        original_bytes=original,
        normalized_bytes=normalized,
        original_sha256=hashlib.sha256(original).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
    )
