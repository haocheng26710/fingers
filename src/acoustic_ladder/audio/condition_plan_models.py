"""Strict development-only protocol-condition plan models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.domain.models import NodeState
from acoustic_ladder.domain.paths import validate_relative_path

SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_-]+$"


class ConditionPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DevelopmentConditionDefinition(ConditionPlanModel):
    condition_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    condition_role: Literal["all_blk_reference", "single_bridge_candidate"]
    selected_node: str | None
    selected_module: str | None

    @model_validator(mode="after")
    def role_and_selection_match(self) -> DevelopmentConditionDefinition:
        if self.condition_id in {".", ".."}:
            raise ValueError("condition_id must not be a path token")
        selected = self.selected_node is not None and self.selected_module is not None
        if (self.selected_node is None) != (self.selected_module is None):
            raise ValueError("selected_node and selected_module must both be null or present")
        if self.condition_role == "all_blk_reference" and selected:
            raise ValueError("all-BLK reference cannot select a node or module")
        if self.condition_role == "single_bridge_candidate" and not selected:
            raise ValueError("single-bridge candidate requires one node and module")
        return self


class DevelopmentConditionPlan(ConditionPlanModel):
    schema_version: Literal["1.0.0"]
    condition_plan_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    usage_scope: Literal["development_fixture"]
    source_protocol_reference: str
    experiment_stage: Literal[1]
    protocol_execution_authorized: Literal[False]
    hardware_io_authorized: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    conditions: list[DevelopmentConditionDefinition] = Field(min_length=2)

    @field_validator("source_protocol_reference")
    @classmethod
    def source_protocol_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @model_validator(mode="after")
    def identities_and_baseline_are_unique(self) -> DevelopmentConditionPlan:
        if self.condition_plan_id in {".", ".."}:
            raise ValueError("condition_plan_id must not be a path token")
        identifiers = [condition.condition_id for condition in self.conditions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("condition IDs must be unique")
        selections = [
            (condition.selected_node, condition.selected_module)
            for condition in self.conditions
            if condition.selected_node is not None
        ]
        if len(selections) != len(set(selections)):
            raise ValueError("duplicate selected node/state")
        baselines = [
            condition
            for condition in self.conditions
            if condition.condition_role == "all_blk_reference"
        ]
        if len(baselines) != 1:
            raise ValueError("condition plan requires exactly one all-BLK reference")
        return self


class ResolvedConditionBinding(ConditionPlanModel):
    condition_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    condition_role: Literal["all_blk_reference", "single_bridge_candidate"]
    resolved_node_states: dict[str, NodeState]
    non_blk_node_count: int = Field(ge=0, le=1)

    @model_validator(mode="after")
    def resolved_role_is_consistent(self) -> ResolvedConditionBinding:
        actual = sum(state.module_id != "BLK" for state in self.resolved_node_states.values())
        if actual != self.non_blk_node_count:
            raise ValueError("non-BLK node count differs from resolved states")
        expected = 0 if self.condition_role == "all_blk_reference" else 1
        if actual != expected:
            raise ValueError("resolved states differ from the condition role")
        return self
