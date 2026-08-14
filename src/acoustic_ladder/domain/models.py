"""Pydantic v2 domain records for sessions, runs, states and artifacts."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.domain.paths import validate_relative_path

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RelativePath = Annotated[str, Field(min_length=1)]
type ConfigLayer = Literal[
    "device_manifest", "audio_config", "protocol_config", "analysis_config", "synthetic_config"
]


class StrictModel(BaseModel):
    """Reject unknown fields and implicit string-to-number coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)


class DataOrigin(StrEnum):
    SYNTHETIC = "synthetic"
    REAL = "real"


class RunMode(StrEnum):
    FORMAL = "formal"
    DIAGNOSTIC = "diagnostic"
    DEVELOPMENT = "development"


class LoadingDirection(StrEnum):
    LOADING = "loading"
    UNLOADING = "unloading"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class NodeState(StrictModel):
    node_id: str
    state_id: str
    module_id: str
    state_type: str
    discrete_label: str | None
    continuous_value: float | None
    unit: str | None
    loading_direction: LoadingDirection
    proxy_state: bool
    provenance: str | None
    notes: str | None

    @model_validator(mode="after")
    def continuous_value_has_unit(self) -> NodeState:
        if (self.continuous_value is None) != (self.unit is None):
            raise ValueError(
                "continuous_value and unit must either both be present or both be null"
            )
        return self


class ConfigSnapshot(StrictModel):
    layer: ConfigLayer
    original_relative_path: RelativePath
    original_sha256: str
    normalized_sha256: str
    validation_status: Literal["valid"]

    @field_validator("original_relative_path")
    @classmethod
    def path_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @field_validator("original_sha256", "normalized_sha256")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("expected a lowercase SHA256 digest")
        return value


class ArtifactRef(StrictModel):
    artifact_type: str
    path: RelativePath
    sha256: str
    byte_size: int = Field(ge=0)
    format: str
    shape: list[int] | None
    dtype: str | None
    created_by: str
    immutable: Literal[True] = True

    @field_validator("path")
    @classmethod
    def path_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @field_validator("sha256")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("expected a lowercase SHA256 digest")
        return value

    @field_validator("shape")
    @classmethod
    def shape_is_positive(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(item < 0 for item in value):
            raise ValueError("artifact shape dimensions cannot be negative")
        return value


class SessionRecord(StrictModel):
    session_id: str
    session_schema_version: str
    created_at: AwareDatetime
    data_origin: DataOrigin
    run_mode: RunMode
    operator: str | None
    device_manifest_reference: RelativePath
    config_bundle_reference: RelativePath
    reassembly_ids: list[str]
    run_ids: list[str]
    immutable_status: Literal["immutable"]
    notes: str | None

    @field_validator("device_manifest_reference", "config_bundle_reference")
    @classmethod
    def paths_are_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @field_validator("reassembly_ids", "run_ids")
    @classmethod
    def identifiers_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("record identifiers must be unique")
        return value


class ReassemblyRecord(StrictModel):
    reassembly_id: str
    session_id: str
    sequence_index: int = Field(ge=0)
    created_at: AwareDatetime
    assembly_description: str
    operator_confirmation: bool
    related_run_ids: list[str]

    @field_validator("related_run_ids")
    @classmethod
    def run_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("related run IDs must be unique")
        return value


class MeasurementRunRecord(StrictModel):
    run_id: str
    session_id: str
    reassembly_id: str
    protocol_id: str
    measurement_order: int = Field(ge=0)
    data_origin: DataOrigin
    run_mode: RunMode
    formal_eligible: bool
    node_states: dict[str, NodeState]
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    config_hashes: dict[str, str]
    artifacts: list[ArtifactRef]
    backend: str
    software_version: str
    status: Literal["planned", "generated", "complete", "failed"]
    failure_reason: str | None
    result_marker: str | None
    notes: str | None

    @field_validator("config_hashes")
    @classmethod
    def config_hashes_are_sha256(cls, value: dict[str, str]) -> dict[str, str]:
        invalid = [
            name for name, digest in value.items() if SHA256_PATTERN.fullmatch(digest) is None
        ]
        if invalid:
            raise ValueError(f"invalid config SHA256 values: {invalid}")
        return value

    @model_validator(mode="after")
    def enforce_origin_and_state_invariants(self) -> MeasurementRunRecord:
        for key, state in self.node_states.items():
            if key != state.node_id:
                raise ValueError(f"node-state key {key!r} does not match node_id {state.node_id!r}")
        if self.data_origin is DataOrigin.SYNTHETIC:
            if self.run_mode is not RunMode.DEVELOPMENT:
                raise ValueError("synthetic runs must use development run_mode")
            if self.formal_eligible:
                raise ValueError("synthetic runs can never be formal eligible")
            if self.result_marker != "NOT_EXPERIMENTAL_RESULT":
                raise ValueError("synthetic runs require NOT_EXPERIMENTAL_RESULT")
        if self.status == "failed" and self.failure_reason is None:
            raise ValueError("failed runs require a failure_reason")
        if self.status != "failed" and self.failure_reason is not None:
            raise ValueError("failure_reason is only valid for failed runs")
        if self.status == "complete" and self.completed_at is None:
            raise ValueError("complete runs require completed_at")
        return self


def utc_now() -> datetime:
    """Production default; callers may inject a deterministic provider."""

    return datetime.now().astimezone()
