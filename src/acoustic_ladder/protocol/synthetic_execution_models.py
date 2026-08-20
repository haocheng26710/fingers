"""Strict contracts for development-only synthetic protocol execution."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from acoustic_ladder.audio.virtual_capture_models import (
    BlockTraceRecord,
    CaptureFaultCounters,
    StateTransitionRecord,
)
from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.domain.models import NodeState

SHA256_PATTERN = r"^[0-9a-f]{64}$"
SAFE_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
EXECUTION_SAFETY_MARKER: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"] = (
    "SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"
)
ZERO_EVENT_SHA256 = "0" * 64


class SyntheticExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class SyntheticProtocolWorkOrder(SyntheticExecutionModel):
    schema_version: Literal["1.0.0"]
    execution_id: str = Field(pattern=SAFE_ID_PATTERN, max_length=32)
    plan_id: str = Field(pattern=SAFE_ID_PATTERN)
    compiled_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_plan_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    schedule_sha256: str = Field(pattern=SHA256_PATTERN)
    experiment_stage: Literal[1, 2, 3, 4]
    global_planned_ordinal: int = Field(gt=0)
    session_local_measurement_order: int = Field(gt=0)
    session_index: int = Field(gt=0)
    reassembly_index: int = Field(gt=0)
    condition_block_order: int = Field(gt=0)
    canonical_condition_index: int = Field(gt=0)
    continuous_repeat_index: int = Field(gt=0)
    condition_id: str = Field(pattern=SAFE_ID_PATTERN)
    condition_role: str
    condition_label: str
    condition_node_state_sha256: str = Field(pattern=SHA256_PATTERN)
    node_states: dict[str, NodeState]
    selected_nodes: list[str]
    selected_modules: list[str]
    operator_confirmation_requirements: list[str] = Field(min_length=1)
    session_id: str = Field(pattern=SAFE_ID_PATTERN)
    reassembly_id: str = Field(pattern=SAFE_ID_PATTERN)
    run_id: str = Field(pattern=SAFE_ID_PATTERN)
    capture_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_confirmation_status: Literal["pending"]
    development_synthetic_run: Literal[True]
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    physical_operator_confirmation_performed: Literal[False]
    formal_protocol_execution_performed: Literal[False]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
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
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"]
    work_order_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def identities_and_digest_are_derived(self) -> SyntheticProtocolWorkOrder:
        prefix = f"sx_{self.execution_id}"
        if self.session_id != f"{prefix}_s{self.session_index:02d}":
            raise ValueError("session_id is not derived from execution coordinates")
        if self.reassembly_id != (
            f"{prefix}_s{self.session_index:02d}_r{self.reassembly_index:02d}"
        ):
            raise ValueError("reassembly_id is not derived from execution coordinates")
        expected_run = f"{prefix}_w{self.global_planned_ordinal:06d}"
        if self.run_id != expected_run or self.capture_id != expected_run:
            raise ValueError("run/capture identity is not derived from execution coordinates")
        state_bytes = canonical_json_bytes(
            {key: value.model_dump(mode="json") for key, value in self.node_states.items()}
        )
        if hashlib.sha256(state_bytes).hexdigest() != self.condition_node_state_sha256:
            raise ValueError("work-order NodeState digest differs from condition identity")
        core = self.model_dump(mode="json", exclude={"work_order_sha256"})
        if hashlib.sha256(canonical_json_bytes(core)).hexdigest() != self.work_order_sha256:
            raise ValueError("work_order_sha256 differs from canonical work-order core")
        return self


class SyntheticProtocolExecutionManifest(SyntheticExecutionModel):
    schema_version: Literal["1.0.0"]
    execution_id: str = Field(pattern=SAFE_ID_PATTERN, max_length=32)
    plan_id: str = Field(pattern=SAFE_ID_PATTERN)
    plan_spec_id: str
    experiment_stage: Literal[1, 2, 3, 4]
    compiled_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_plan_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    schedule_sha256: str = Field(pattern=SHA256_PATTERN)
    condition_matrix_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_reference: str
    scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_artifact_id: str
    source_ess_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    synthetic_config_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_work_order_count: int = Field(gt=0)
    ordered_work_order_sha256: str = Field(pattern=SHA256_PATTERN)
    development_synthetic_run: Literal[True]
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    formal_protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
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
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"]


class SyntheticProtocolExecutionRecord(SyntheticExecutionModel):
    schema_version: Literal["1.0.0"]
    execution_id: str = Field(pattern=SAFE_ID_PATTERN, max_length=32)
    execution_relative_path: str
    created_at: AwareDatetime
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    immutable_status: Literal["initialized"]
    development_synthetic_run: Literal[True]
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    formal_protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
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
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"]


class SyntheticProtocolExecutionConcurrencyToken(SyntheticExecutionModel):
    execution_id: str = Field(pattern=SAFE_ID_PATTERN, max_length=32)
    event_sequence: int = Field(ge=0)
    head_event_sha256: str = Field(pattern=SHA256_PATTERN)
    current_work_order_sha256: str = Field(pattern=SHA256_PATTERN)
    cursor: int = Field(ge=0)
    recovery_run_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)


class SyntheticProtocolExecutionStatus(SyntheticExecutionModel):
    execution_id: str
    execution_state: Literal[
        "active", "paused", "failed", "recovery_required", "aborted", "complete"
    ]
    current_work_order: SyntheticProtocolWorkOrder | None
    cursor: int = Field(ge=0)
    total_work_order_count: int = Field(gt=0)
    successful_work_order_count: int = Field(ge=0)
    concurrency_token: SyntheticProtocolExecutionConcurrencyToken
    recovery_kind: Literal["capture", "completion"] | None
    synthetic_capture_performed: bool
    development_synthetic_run: Literal[True]
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    formal_protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
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
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"]


class PlanBoundSyntheticCaptureReceipt(SyntheticExecutionModel):
    schema_version: Literal["1.0.0"]
    execution_id: str = Field(pattern=SAFE_ID_PATTERN, max_length=32)
    plan_id: str = Field(pattern=SAFE_ID_PATTERN)
    compiled_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_plan_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    schedule_sha256: str = Field(pattern=SHA256_PATTERN)
    work_order_sha256: str = Field(pattern=SHA256_PATTERN)
    experiment_stage: Literal[1, 2, 3, 4]
    global_planned_ordinal: int = Field(gt=0)
    session_index: int = Field(gt=0)
    reassembly_index: int = Field(gt=0)
    condition_block_order: int = Field(gt=0)
    continuous_repeat_index: int = Field(gt=0)
    condition_id: str = Field(pattern=SAFE_ID_PATTERN)
    condition_role: str
    condition_node_state_sha256: str = Field(pattern=SHA256_PATTERN)
    node_states: dict[str, NodeState]
    selected_nodes: list[str]
    selected_modules: list[str]
    session_id: str = Field(pattern=SAFE_ID_PATTERN)
    reassembly_id: str = Field(pattern=SAFE_ID_PATTERN)
    run_id: str = Field(pattern=SAFE_ID_PATTERN)
    capture_id: str = Field(pattern=SAFE_ID_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    backend_id: Literal["deterministic_plan_bound_virtual_duplex"]
    backend_version: Literal["1.0.0"]
    scenario_reference: str
    scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_id: str
    protocol_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    synthetic_config_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    synthetic_config_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
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
    capture_receipt_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    block_trace: list[BlockTraceRecord]
    state_transition_trace: list[StateTransitionRecord]
    fault_counters: CaptureFaultCounters
    final_state: Literal["completed"]
    all_finite: Literal[True]
    create_only: Literal[True]
    immutable: Literal[True]
    synthetic_capture_performed: Literal[True]
    virtual_duplex_scheduler_exercised: Literal[True]
    development_synthetic_run: Literal[True]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    formal_protocol_execution_performed: Literal[False]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
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
    safety_marker: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"]

    @model_validator(mode="after")
    def capture_identity_and_shapes_match(self) -> PlanBoundSyntheticCaptureReceipt:
        if self.run_id != self.capture_id:
            raise ValueError("capture_id must equal deterministic run_id")
        if self.output_shape != self.input_shape:
            raise ValueError("plan-bound capture input/output shapes differ")
        if self.output_shape[1] != self.capture_sample_count:
            raise ValueError("capture shape differs from sample count")
        if self.ess_sample_count + self.capture_tail_sample_count != self.capture_sample_count:
            raise ValueError("ESS and tail do not form capture sample count")
        if self.actual_block_count != self.planned_block_count:
            raise ValueError("plan-bound capture did not execute every block")
        if set(self.node_states) != set(self.manifest_node_delay_samples) or set(
            self.node_states
        ) != set(self.manifest_module_node_weights):
            raise ValueError("capture NodeState/delay/weight node sets differ")
        state_bytes = canonical_json_bytes(
            {key: value.model_dump(mode="json") for key, value in self.node_states.items()}
        )
        if hashlib.sha256(state_bytes).hexdigest() != self.condition_node_state_sha256:
            raise ValueError("capture NodeState digest differs from work order")
        return self


class SyntheticProtocolExecutionControl(SyntheticExecutionModel):
    action: Literal["pause", "resume", "retry", "abort"]
    actor_id: str = Field(pattern=SAFE_ID_PATTERN)
    expected_event_sequence: int = Field(ge=0)
    expected_head_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_current_work_order_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_cursor: int = Field(ge=0)
    reason_code: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)

    @model_validator(mode="after")
    def abort_requires_reason(self) -> SyntheticProtocolExecutionControl:
        if (self.action == "abort") != (self.reason_code is not None):
            raise ValueError("reason_code is required only for abort")
        return self


class SyntheticProtocolExecutionEvent(SyntheticExecutionModel):
    schema_version: Literal["1.0.0"]
    execution_id: str = Field(pattern=SAFE_ID_PATTERN, max_length=32)
    event_sequence: int = Field(gt=0)
    event_type: Literal[
        "work_order_succeeded",
        "work_order_failed",
        "work_order_retry_requested",
        "execution_paused",
        "execution_resumed",
        "execution_aborted",
    ]
    previous_event_sha256: str = Field(pattern=SHA256_PATTERN)
    plan_id: str
    compiled_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_plan_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    work_order_sha256: str = Field(pattern=SHA256_PATTERN)
    actor_id: str = Field(pattern=SAFE_ID_PATTERN)
    before_state: Literal["active", "paused", "failed", "aborted", "complete"]
    after_state: Literal["active", "paused", "failed", "aborted", "complete"]
    cursor_before: int = Field(ge=0)
    cursor_after: int = Field(ge=0)
    session_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    reassembly_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    run_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    capture_receipt_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    run_record_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    ordered_artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reason_code: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    recorded_at: AwareDatetime
    synthetic_capture_performed: bool
    development_synthetic_run: Literal[True]
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    formal_protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
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
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"]


class SyntheticProtocolExecutionCompletion(SyntheticExecutionModel):
    schema_version: Literal["1.0.0"]
    execution_id: str = Field(pattern=SAFE_ID_PATTERN, max_length=32)
    plan_id: str
    compiled_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_plan_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    schedule_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_work_order_count: int = Field(gt=0)
    completed_work_order_count: int = Field(gt=0)
    final_event_sequence: int = Field(gt=0)
    final_event_sha256: str = Field(pattern=SHA256_PATTERN)
    ordered_successful_run_sha256: str = Field(pattern=SHA256_PATTERN)
    ordered_event_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_at: AwareDatetime
    completion_state: Literal["complete"]
    synthetic_capture_performed: Literal[True]
    development_synthetic_run: Literal[True]
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    formal_protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
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
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT"]
