"""Strict models for development-only offline protocol rehearsal."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.domain.models import NodeState

REHEARSAL_SAFETY_MARKER: Literal[
    "DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"
] = "DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"
ZERO_EVENT_SHA256 = "0" * 64


class ProtocolRehearsalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ProtocolRehearsalWorkOrder(ProtocolRehearsalModel):
    work_order_schema_version: Literal["1.0.0"]
    plan_id: str
    compiled_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_plan_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_stage: Literal[1, 2, 3, 4]
    global_planned_ordinal: int = Field(gt=0)
    session_local_measurement_order: int = Field(gt=0)
    session_index: int = Field(gt=0)
    reassembly_index: int = Field(gt=0)
    condition_block_order: int = Field(gt=0)
    canonical_condition_index: int = Field(gt=0)
    continuous_repeat_index: int = Field(gt=0)
    condition_id: str
    condition_role: str
    condition_label: str
    condition_node_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    node_states: dict[str, NodeState]
    selected_nodes: list[str]
    selected_modules: list[str]
    operator_confirmation_requirements: list[str] = Field(min_length=1)
    operator_confirmation_status: Literal["pending"]
    development_rehearsal: Literal[True]
    requirements_presented_for_rehearsal: Literal[False]
    physical_operator_confirmation_performed: Literal[False]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
    hardware_io_performed: Literal[False]
    hardware_ready: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]
    work_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity_matches_core_bytes(self) -> ProtocolRehearsalWorkOrder:
        core = self.model_dump(mode="json", exclude={"work_order_sha256"})
        if hashlib.sha256(canonical_json_bytes(core)).hexdigest() != self.work_order_sha256:
            raise ValueError("work_order_sha256 differs from canonical work-order core")
        return self


class ProtocolRehearsalManifest(ProtocolRehearsalModel):
    schema_version: Literal["1.0.0"]
    rehearsal_id: str
    plan_id: str
    plan_spec_id: str
    plan_spec_reference: str
    plan_spec_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_spec_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_id: str
    protocol_version: str
    protocol_reference: str
    protocol_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_stage: Literal[1, 2, 3, 4]
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiled_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_plan_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    condition_matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    condition_count: int = Field(gt=0)
    planned_measurement_count: int = Field(gt=0)
    session_count: int = Field(gt=0)
    reassemblies_per_session: int = Field(gt=0)
    continuous_repeats_per_condition: int = Field(gt=0)
    randomization_enabled: bool
    randomization_algorithm_id: str
    randomization_algorithm_version: str
    random_seed: str | None
    ordered_work_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_rehearsal: Literal[True]
    requirements_presented_for_rehearsal: Literal[False]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
    hardware_io_performed: Literal[False]
    hardware_ready: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]


class ProtocolRehearsalRecord(ProtocolRehearsalModel):
    schema_version: Literal["1.0.0"]
    rehearsal_id: str
    rehearsal_relative_path: str
    created_at: AwareDatetime
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    immutable_status: Literal["initialized"]
    development_rehearsal: Literal[True]
    requirements_presented_for_rehearsal: Literal[False]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
    hardware_io_performed: Literal[False]
    hardware_ready: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]


class ProtocolRehearsalConcurrencyToken(ProtocolRehearsalModel):
    rehearsal_id: str
    event_sequence: int = Field(ge=0)
    head_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_work_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProtocolRehearsalStatus(ProtocolRehearsalModel):
    rehearsal_id: str
    rehearsal_state: Literal["active", "paused", "failed", "aborted", "complete"]
    current_work_order_phase: (
        Literal["awaiting_requirements_presentation", "requirements_presented", "claimed", "failed"]
        | None
    )
    current_work_order: ProtocolRehearsalWorkOrder | None
    cursor: int = Field(ge=0)
    total_work_order_count: int = Field(gt=0)
    rehearsed_work_order_count: int = Field(ge=0)
    concurrency_token: ProtocolRehearsalConcurrencyToken
    development_rehearsal: Literal[True]
    requirements_presented_for_rehearsal: bool
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
    hardware_io_performed: Literal[False]
    hardware_ready: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]


class ProtocolRehearsalTransitionCommand(ProtocolRehearsalModel):
    action: Literal[
        "present-requirements",
        "claim",
        "mark-rehearsed",
        "mark-failed",
        "retry",
        "pause",
        "resume",
        "abort",
    ]
    rehearsal_actor_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    expected_event_sequence: int = Field(ge=0)
    expected_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_current_work_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    detail: str | None = Field(default=None, max_length=512)

    @field_validator("detail")
    @classmethod
    def detail_has_no_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(
            ord(character) < 32 and character not in "\t" for character in value
        ):
            raise ValueError("detail cannot contain control characters")
        return value

    @model_validator(mode="after")
    def reason_matches_action(self) -> ProtocolRehearsalTransitionCommand:
        requires_reason = self.action in {"mark-failed", "abort"}
        if requires_reason != (self.reason_code is not None):
            raise ValueError("reason_code is required only for fail or abort")
        if not requires_reason and self.detail is not None:
            raise ValueError("detail is allowed only for fail or abort")
        return self


class ProtocolRehearsalEvent(ProtocolRehearsalModel):
    schema_version: Literal["1.0.0"]
    rehearsal_id: str
    event_sequence: int = Field(gt=0)
    event_type: Literal[
        "requirements_presented",
        "work_order_claimed",
        "work_order_rehearsed",
        "work_order_failed",
        "work_order_retry_requested",
        "rehearsal_paused",
        "rehearsal_resumed",
        "rehearsal_aborted",
    ]
    previous_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_id: str
    compiled_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_work_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rehearsal_actor_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    before_rehearsal_state: Literal["active", "paused", "failed", "aborted", "complete"]
    after_rehearsal_state: Literal["active", "paused", "failed", "aborted", "complete"]
    before_work_order_phase: (
        Literal["awaiting_requirements_presentation", "requirements_presented", "claimed", "failed"]
        | None
    )
    after_work_order_phase: (
        Literal["awaiting_requirements_presentation", "requirements_presented", "claimed", "failed"]
        | None
    )
    derived_cursor_before: int = Field(ge=0)
    derived_cursor_after: int = Field(ge=0)
    reason_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    detail: str | None = Field(default=None, max_length=512)
    recorded_at: AwareDatetime
    development_rehearsal: Literal[True]
    requirements_presented_for_rehearsal: bool
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
    hardware_io_performed: Literal[False]
    hardware_ready: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]


class ProtocolRehearsalCompletion(ProtocolRehearsalModel):
    schema_version: Literal["1.0.0"]
    rehearsal_id: str
    plan_id: str
    compiled_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_plan_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_work_order_count: int = Field(gt=0)
    rehearsed_work_order_count: int = Field(gt=0)
    final_event_sequence: int = Field(gt=0)
    final_event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_event_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completion_state: Literal["complete"]
    development_rehearsal: Literal[True]
    requirements_presented_for_rehearsal: Literal[False]
    physical_operator_confirmation_performed: Literal[False]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    measurement_performed: Literal[False]
    hardware_io_performed: Literal[False]
    hardware_ready: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_REHEARSAL_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]
