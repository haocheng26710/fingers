"""Strict models for deterministic development protocol plans."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.domain.models import NodeState
from acoustic_ladder.domain.paths import validate_relative_path

SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_-]+$"
PLAN_SAFETY_MARKER: Literal["DEVELOPMENT_PROTOCOL_PLAN_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"] = (
    "DEVELOPMENT_PROTOCOL_PLAN_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"
)


class ProtocolPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DevelopmentProtocolPlanSpec(ProtocolPlanModel):
    schema_version: Literal["1.0.0"]
    plan_spec_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    usage_scope: Literal["development_fixture"]
    source_protocol_reference: str
    session_count: int = Field(gt=0)
    reassemblies_per_session: int = Field(gt=0)
    continuous_repeats_per_condition: int = Field(gt=0)
    randomization_enabled: bool
    random_seed: Annotated[str, Field(pattern=SAFE_IDENTIFIER_PATTERN)] | None
    selected_nodes: list[str] | None
    max_planned_measurements: int = Field(gt=0)
    operator_confirmation_required: Literal[True]
    protocol_execution_authorized: Literal[False]
    hardware_io_authorized: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]

    @field_validator("source_protocol_reference")
    @classmethod
    def source_protocol_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @field_validator("selected_nodes")
    @classmethod
    def selected_nodes_are_unique(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("selected_nodes cannot contain duplicates")
        if value is not None and any(
            re.fullmatch(SAFE_IDENTIFIER_PATTERN, node_id) is None or node_id in {".", ".."}
            for node_id in value
        ):
            raise ValueError("selected_nodes must contain safe ASCII identifiers")
        return value

    @model_validator(mode="after")
    def randomization_seed_matches_mode(self) -> DevelopmentProtocolPlanSpec:
        if self.plan_spec_id in {".", ".."}:
            raise ValueError("plan_spec_id cannot be a path token")
        if self.randomization_enabled and self.random_seed is None:
            raise ValueError("randomization requires an explicit seed")
        if not self.randomization_enabled and self.random_seed is not None:
            raise ValueError("disabled randomization requires a null seed")
        return self


class CompiledProtocolCondition(ProtocolPlanModel):
    condition_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    experiment_stage: Literal[1, 2, 3, 4]
    condition_role: str
    condition_label: str
    selected_nodes: list[str]
    selected_modules: list[str]
    node_states: dict[str, NodeState]
    node_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_node_count: int = Field(ge=0)
    proxy_experiment: bool
    proxy_state: bool
    source_protocol_reference: str
    source_state_ids: list[str]
    operator_confirmation_requirements: list[str] = Field(min_length=1)
    operator_confirmation_required: Literal[True]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    hardware_io_performed: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]

    @model_validator(mode="after")
    def node_states_match_identity_and_digest(self) -> CompiledProtocolCondition:
        if not self.node_states:
            raise ValueError("condition node_states cannot be empty")
        if any(key != state.node_id for key, state in self.node_states.items()):
            raise ValueError("condition node-state key differs from node_id")
        actual_active = sum(state.module_id != "BLK" for state in self.node_states.values())
        if actual_active != self.active_node_count:
            raise ValueError("condition active_node_count differs from node_states")
        payload = canonical_json_bytes(
            {node_id: state.model_dump(mode="json") for node_id, state in self.node_states.items()}
        )
        if hashlib.sha256(payload).hexdigest() != self.node_state_sha256:
            raise ValueError("condition node_state_sha256 differs from node_states")
        return self


class PlannedMeasurement(ProtocolPlanModel):
    global_planned_ordinal: int = Field(gt=0)
    session_local_measurement_order: int = Field(gt=0)
    session_index: int = Field(gt=0)
    reassembly_index: int = Field(gt=0)
    condition_block_order: int = Field(gt=0)
    continuous_repeat_index: int = Field(gt=0)
    condition_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    node_states: dict[str, NodeState]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    hardware_io_performed: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]


class ProtocolConditionBlock(ProtocolPlanModel):
    condition_block_order: int = Field(gt=0)
    canonical_condition_index: int = Field(gt=0)
    condition_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    measurements: list[PlannedMeasurement] = Field(min_length=1)


class ProtocolReassemblySlot(ProtocolPlanModel):
    reassembly_index: int = Field(gt=0)
    condition_blocks: list[ProtocolConditionBlock] = Field(min_length=1)


class ProtocolSessionSlot(ProtocolPlanModel):
    session_index: int = Field(gt=0)
    reassembly_slots: list[ProtocolReassemblySlot] = Field(min_length=1)


class CompiledDevelopmentProtocolPlan(ProtocolPlanModel):
    schema_version: Literal["1.0.0"]
    compiler_algorithm_id: Literal["development_protocol_matrix_compiler"]
    compiler_algorithm_version: Literal["1.0.0"]
    plan_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    plan_spec_id: str
    plan_spec_reference: str
    plan_spec_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_spec_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_reference: str
    protocol_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_id: str
    protocol_version: str
    experiment_stage: Literal[1, 2, 3, 4]
    manifest_reference: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    condition_count: int = Field(gt=0)
    condition_matrix: list[CompiledProtocolCondition]
    condition_matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planned_measurement_count: int = Field(gt=0)
    session_count: int = Field(gt=0)
    reassemblies_per_session: int = Field(gt=0)
    continuous_repeats_per_condition: int = Field(gt=0)
    randomization_enabled: bool
    randomization_algorithm_id: Literal["sha256_ranked_condition_blocks"]
    randomization_algorithm_version: Literal["1.0.0"]
    random_seed: str | None
    session_slots: list[ProtocolSessionSlot] = Field(min_length=1)
    schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    all_node_states_complete: Literal[True]
    operator_confirmation_required: Literal[True]
    operator_confirmation_status: Literal["pending"]
    development_fixture: Literal[True]
    protocol_execution_performed: Literal[False]
    hardware_io_performed: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_PLAN_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]

    @model_validator(mode="after")
    def condition_count_matches(self) -> CompiledDevelopmentProtocolPlan:
        if self.condition_count != len(self.condition_matrix):
            raise ValueError("condition_count does not match condition_matrix")
        identifiers = [condition.condition_id for condition in self.condition_matrix]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("condition IDs must be unique")
        matrix_bytes = canonical_json_bytes(
            [condition.model_dump(mode="json") for condition in self.condition_matrix]
        )
        if hashlib.sha256(matrix_bytes).hexdigest() != self.condition_matrix_sha256:
            raise ValueError("condition_matrix_sha256 differs from condition_matrix")
        node_sets = [set(condition.node_states) for condition in self.condition_matrix]
        if not node_sets or any(nodes != node_sets[0] for nodes in node_sets[1:]):
            raise ValueError("condition matrix node-state maps are not complete and identical")
        if self.session_count != len(self.session_slots):
            raise ValueError("session_count does not match session_slots")
        if self.randomization_enabled != (self.random_seed is not None):
            raise ValueError("randomization mode and seed are inconsistent")
        by_condition = {condition.condition_id: condition for condition in self.condition_matrix}
        global_ordinals: list[int] = []
        actual = sum(
            len(block.measurements)
            for session in self.session_slots
            for reassembly in session.reassembly_slots
            for block in reassembly.condition_blocks
        )
        if actual != self.planned_measurement_count:
            raise ValueError("planned_measurement_count does not match schedule")
        for expected_session, session in enumerate(self.session_slots, start=1):
            if session.session_index != expected_session:
                raise ValueError("session indices are not continuous")
            if len(session.reassembly_slots) != self.reassemblies_per_session:
                raise ValueError("reassembly count differs from plan")
            local_orders: list[int] = []
            for expected_reassembly, reassembly in enumerate(session.reassembly_slots, start=1):
                if reassembly.reassembly_index != expected_reassembly:
                    raise ValueError("reassembly indices are not continuous")
                if {block.condition_id for block in reassembly.condition_blocks} != set(
                    by_condition
                ):
                    raise ValueError("reassembly condition multiset is incomplete")
                for expected_block, block in enumerate(reassembly.condition_blocks, start=1):
                    if block.condition_block_order != expected_block:
                        raise ValueError("condition block order is not continuous")
                    if len(block.measurements) != self.continuous_repeats_per_condition:
                        raise ValueError("continuous repeat count differs from plan")
                    condition = by_condition[block.condition_id]
                    for expected_repeat, measurement in enumerate(block.measurements, start=1):
                        if (
                            measurement.continuous_repeat_index != expected_repeat
                            or measurement.condition_id != block.condition_id
                            or measurement.node_states != condition.node_states
                        ):
                            raise ValueError("planned measurement differs from condition block")
                        global_ordinals.append(measurement.global_planned_ordinal)
                        local_orders.append(measurement.session_local_measurement_order)
            if local_orders != list(range(1, len(local_orders) + 1)):
                raise ValueError("session-local measurement order is not continuous")
        if global_ordinals != list(range(1, len(global_ordinals) + 1)):
            raise ValueError("global planned ordinals are not continuous")
        schedule_bytes = canonical_json_bytes(
            [session.model_dump(mode="json") for session in self.session_slots]
        )
        if hashlib.sha256(schedule_bytes).hexdigest() != self.schedule_sha256:
            raise ValueError("schedule_sha256 differs from session_slots")
        return self


class ProtocolPlanReceipt(ProtocolPlanModel):
    schema_version: Literal["1.0.0"]
    compiler_algorithm_id: Literal["development_protocol_matrix_compiler"]
    compiler_algorithm_version: Literal["1.0.0"]
    plan_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    plan_spec_id: str
    plan_spec_reference: str
    plan_spec_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_spec_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_reference: str
    protocol_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_id: str
    protocol_version: str
    experiment_stage: Literal[1, 2, 3, 4]
    manifest_reference: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    condition_count: int = Field(gt=0)
    planned_measurement_count: int = Field(gt=0)
    session_count: int = Field(gt=0)
    reassemblies_per_session: int = Field(gt=0)
    continuous_repeats_per_condition: int = Field(gt=0)
    randomization_enabled: bool
    randomization_algorithm_id: Literal["sha256_ranked_condition_blocks"]
    randomization_algorithm_version: Literal["1.0.0"]
    random_seed: str | None
    condition_matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiled_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    all_node_states_complete: Literal[True]
    operator_confirmation_required: Literal[True]
    operator_confirmation_status: Literal["pending"]
    development_fixture: Literal[True]
    protocol_execution_performed: Literal[False]
    hardware_io_performed: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_PLAN_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]


class ProtocolPlanRecord(ProtocolPlanModel):
    schema_version: Literal["1.0.0"]
    plan_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    plan_relative_path: str
    created_at: AwareDatetime
    compiled_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    immutable_status: Literal["immutable"]
    operator_confirmation_status: Literal["pending"]
    protocol_execution_performed: Literal[False]
    hardware_io_performed: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["DEVELOPMENT_PROTOCOL_PLAN_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT"]

    @field_validator("plan_relative_path")
    @classmethod
    def plan_path_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)


@dataclass(frozen=True)
class PublishedDevelopmentProtocolPlan:
    plan_path: Path
    plan: CompiledDevelopmentProtocolPlan
    receipt: ProtocolPlanReceipt
    record: ProtocolPlanRecord
    plan_sha256: str
    receipt_sha256: str
