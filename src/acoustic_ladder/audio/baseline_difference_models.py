"""Strict provenance and state contracts for provisional baseline differences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.audio.baseline_difference import ProvisionalBaselineDifferenceMetrics
from acoustic_ladder.audio.repeatability_models import (
    RepeatabilityMemberIdentity,
    RepeatabilityMemberProvenance,
)
from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.domain.models import ConfigSnapshot, NodeState
from acoustic_ladder.domain.paths import validate_relative_path
from acoustic_ladder.storage.io import sha256_bytes

SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.-]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
BASELINE_DIFFERENCE_SAFETY_MARKER: Literal[
    "SYNTHETIC_PROVISIONAL_BASELINE_DIFFERENCE_METRICS_NOT_AN_EXPERIMENTAL_RESULT"
] = "SYNTHETIC_PROVISIONAL_BASELINE_DIFFERENCE_METRICS_NOT_AN_EXPERIMENTAL_RESULT"


class BaselineDifferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def identifiers_are_not_path_tokens(self) -> BaselineDifferenceModel:
        for name, value in self.__dict__.items():
            if name.endswith("_id") and value in {".", ".."}:
                raise ValueError(f"{name} must not be a path token")
        return self


class RepeatabilitySourceIdentity(BaselineDifferenceModel):
    repeat_set_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    members: list[RepeatabilityMemberIdentity] = Field(min_length=2)

    @model_validator(mode="after")
    def members_are_unique(self) -> RepeatabilitySourceIdentity:
        identities = [member.model_dump_json() for member in self.members]
        runs = [member.source_run_id for member in self.members]
        if len(set(identities)) != len(identities) or len(set(runs)) != len(runs):
            raise ValueError("repeatability source identities and runs must be unique")
        return self


class BaselineDifferenceStatePayload(TypedDict):
    evaluation_status: Literal["provisional_baseline_difference_metrics_only"]
    decision_status: Literal["not_evaluated"]
    baseline_comparison_decision: Literal["not_evaluated"]
    protocol_condition_binding_performed: Literal[True]
    protocol_execution_performed: Literal[False]
    baseline_assigned: Literal[True]
    baseline_role: Literal["all_blk_reference"]
    baseline_selection_status: Literal["selected_from_verified_all_blk_condition"]
    baseline_difference_computed: Literal[True]
    thresholds_applied: Literal[False]
    qc_threshold: None
    effect_threshold: None
    drift_threshold: None
    classification_pass_threshold: None
    drift_evaluated: Literal[False]
    drift_decision: Literal["not_evaluated"]
    smoothing_applied: Literal[False]
    feature_extraction_performed: Literal[False]
    classification_performed: Literal[False]
    cross_validation_performed: Literal[False]
    hardware_io_performed: Literal[False]
    playback_performed: Literal[False]
    recording_performed: Literal[False]
    hardware_ready: Literal[False]
    calibration_applied: Literal[False]
    absolute_spl_calibrated: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]


def baseline_difference_state() -> BaselineDifferenceStatePayload:
    return {
        "evaluation_status": "provisional_baseline_difference_metrics_only",
        "decision_status": "not_evaluated",
        "baseline_comparison_decision": "not_evaluated",
        "protocol_condition_binding_performed": True,
        "protocol_execution_performed": False,
        "baseline_assigned": True,
        "baseline_role": "all_blk_reference",
        "baseline_selection_status": "selected_from_verified_all_blk_condition",
        "baseline_difference_computed": True,
        "thresholds_applied": False,
        "qc_threshold": None,
        "effect_threshold": None,
        "drift_threshold": None,
        "classification_pass_threshold": None,
        "drift_evaluated": False,
        "drift_decision": "not_evaluated",
        "smoothing_applied": False,
        "feature_extraction_performed": False,
        "classification_performed": False,
        "cross_validation_performed": False,
        "hardware_io_performed": False,
        "playback_performed": False,
        "recording_performed": False,
        "hardware_ready": False,
        "calibration_applied": False,
        "absolute_spl_calibrated": False,
        "formal_eligible": False,
        "experimental_result": False,
    }


class BaselineDifferenceStateFields(BaselineDifferenceModel):
    evaluation_status: Literal["provisional_baseline_difference_metrics_only"]
    decision_status: Literal["not_evaluated"]
    baseline_comparison_decision: Literal["not_evaluated"]
    protocol_condition_binding_performed: Literal[True]
    protocol_execution_performed: Literal[False]
    baseline_assigned: Literal[True]
    baseline_role: Literal["all_blk_reference"]
    baseline_selection_status: Literal["selected_from_verified_all_blk_condition"]
    baseline_difference_computed: Literal[True]
    thresholds_applied: Literal[False]
    qc_threshold: None
    effect_threshold: None
    drift_threshold: None
    classification_pass_threshold: None
    drift_evaluated: Literal[False]
    drift_decision: Literal["not_evaluated"]
    smoothing_applied: Literal[False]
    feature_extraction_performed: Literal[False]
    classification_performed: Literal[False]
    cross_validation_performed: Literal[False]
    hardware_io_performed: Literal[False]
    playback_performed: Literal[False]
    recording_performed: Literal[False]
    hardware_ready: Literal[False]
    calibration_applied: Literal[False]
    absolute_spl_calibrated: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]


class BaselineDifferenceSourceProvenance(BaselineDifferenceModel):
    reassembly_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    repeat_set_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    condition_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    condition_role: Literal["all_blk_reference", "single_bridge_candidate"]
    resolved_node_states: dict[str, NodeState]
    resolved_node_states_sha256: str = Field(pattern=SHA256_PATTERN)
    non_blk_node_count: int = Field(ge=0, le=1)
    members: list[RepeatabilityMemberProvenance] = Field(min_length=2)
    normalized_member_list_sha256: str = Field(pattern=SHA256_PATTERN)
    repeatability_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    repeatability_receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def source_is_self_consistent(self) -> BaselineDifferenceSourceProvenance:
        state_digest = sha256_bytes(
            canonical_json_bytes(
                {
                    node_id: state.model_dump(mode="json")
                    for node_id, state in self.resolved_node_states.items()
                }
            )
        )
        if state_digest != self.resolved_node_states_sha256:
            raise ValueError("source resolved node-state digest differs")
        non_blk = sum(state.module_id != "BLK" for state in self.resolved_node_states.values())
        expected = 0 if self.condition_role == "all_blk_reference" else 1
        if non_blk != self.non_blk_node_count or non_blk != expected:
            raise ValueError("source condition role and non-BLK count differ")
        member_digest = sha256_bytes(
            canonical_json_bytes([member.model_dump(mode="json") for member in self.members])
        )
        if member_digest != self.normalized_member_list_sha256:
            raise ValueError("source normalized member-list digest differs")
        return self


class BaselineDifferenceConditionBinding(BaselineDifferenceModel):
    schema_version: Literal["1.0.0"]
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    comparison_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    condition_plan_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    condition_plan_reference: str
    condition_plan_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    condition_plan_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_protocol_reference: str
    source_protocol_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    source_protocol_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_source: BaselineDifferenceSourceProvenance
    candidate_source: BaselineDifferenceSourceProvenance
    protocol_condition_binding_performed: Literal[True]
    protocol_execution_performed: Literal[False]

    @field_validator("condition_plan_reference", "source_protocol_reference")
    @classmethod
    def references_are_relative(cls, value: str) -> str:
        return validate_relative_path(value)


class ProvisionalBaselineDifferenceReceipt(BaselineDifferenceStateFields):
    schema_version: Literal["1.0.0"]
    algorithm_id: Literal["provisional_all_blk_baseline_complex_difference"]
    algorithm_version: Literal["1.0.0"]
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    comparison_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    baseline_source: BaselineDifferenceSourceProvenance
    candidate_source: BaselineDifferenceSourceProvenance
    condition_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    condition_plan_reference: str
    condition_plan_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    condition_plan_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_protocol_reference: str
    source_protocol_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    source_protocol_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    config_snapshots: dict[str, ConfigSnapshot]
    scenario_reference: str
    scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_artifact_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    source_ess_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_rate_hz: int = Field(gt=0)
    transfer_fft_length: int = Field(gt=0)
    frequency_bin_count: int = Field(gt=0)
    ir_sample_count: int = Field(gt=0)
    analysis_band_bin_count: int = Field(gt=0)
    analysis_band_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    processing_algorithm_id: str
    processing_algorithm_version: str
    qc_algorithm_id: str
    qc_algorithm_version: str
    repeatability_algorithm_id: str
    repeatability_algorithm_version: str
    denominator_floor_formula_id: Literal[
        "max_baseline_magnitude_times_float64_epsilon_times_frequency_count_or_tiny"
    ]
    denominator_floor: float = Field(gt=0)
    ratio_valid_bin_count: dict[Literal["raw", "aligned"], int]
    ratio_invalid_bin_count: dict[Literal["raw", "aligned"], int]
    invalid_bin_output_policy: Literal["ratio_and_phase_zero_with_validity_masks"]
    phase_unwrap_rule: Literal["unwrap_each_contiguous_valid_segment_without_crossing_gaps"]
    arrays_sha256: str = Field(pattern=SHA256_PATTERN)
    metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    create_only: Literal[True]
    immutable: Literal[True]
    safety_marker: Literal[
        "SYNTHETIC_PROVISIONAL_BASELINE_DIFFERENCE_METRICS_NOT_AN_EXPERIMENTAL_RESULT"
    ]

    @field_validator("condition_plan_reference", "source_protocol_reference", "scenario_reference")
    @classmethod
    def receipt_references_are_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @model_validator(mode="after")
    def roles_and_dimensions_are_consistent(self) -> ProvisionalBaselineDifferenceReceipt:
        if self.baseline_source.condition_role != "all_blk_reference":
            raise ValueError("receipt baseline source is not all-BLK")
        if self.candidate_source.condition_role != "single_bridge_candidate":
            raise ValueError("receipt candidate source is not a single bridge")
        if self.baseline_source.reassembly_id == self.candidate_source.reassembly_id:
            raise ValueError("comparison sources must use different reassemblies")
        if self.frequency_bin_count != self.transfer_fft_length // 2 + 1:
            raise ValueError("frequency-bin count differs from transfer FFT length")
        if set(self.config_snapshots) != {
            "device_manifest",
            "audio_config",
            "protocol_config",
            "analysis_config",
            "synthetic_config",
        }:
            raise ValueError("comparison receipt must bind all five configuration snapshots")
        for representation in ("raw", "aligned"):
            if (
                self.ratio_valid_bin_count[representation]
                + self.ratio_invalid_bin_count[representation]
                != self.frequency_bin_count
            ):
                raise ValueError("ratio valid/invalid counts differ from frequency-bin count")
        baseline_runs = {member.identity.source_run_id for member in self.baseline_source.members}
        candidate_runs = {member.identity.source_run_id for member in self.candidate_source.members}
        if baseline_runs & candidate_runs:
            raise ValueError("comparison sources must not share runs")
        return self


class BaselineDifferenceRecord(BaselineDifferenceStateFields):
    schema_version: Literal["1.0.0"]
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    comparison_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    created_at: AwareDatetime
    status: Literal["complete"]
    condition_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    arrays_sha256: str = Field(pattern=SHA256_PATTERN)
    metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_member_list_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_member_list_sha256: str = Field(pattern=SHA256_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    safety_marker: Literal[
        "SYNTHETIC_PROVISIONAL_BASELINE_DIFFERENCE_METRICS_NOT_AN_EXPERIMENTAL_RESULT"
    ]


class BaselineDifferenceCreatedEvent(BaselineDifferenceModel):
    schema_version: Literal["1.0.0"]
    event: Literal["baseline_difference_created"]
    sequence: int = Field(gt=0)
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    data_origin: Literal["synthetic"]
    comparison_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    baseline_reassembly_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    baseline_repeat_set_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    candidate_reassembly_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    candidate_repeat_set_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    condition_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    arrays_sha256: str = Field(pattern=SHA256_PATTERN)
    metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    record_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_member_list_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_member_list_sha256: str = Field(pattern=SHA256_PATTERN)
    created_at: AwareDatetime


@dataclass(frozen=True)
class PublishedProvisionalBaselineDifference:
    comparison_path: Path
    metrics: ProvisionalBaselineDifferenceMetrics
    receipt: ProvisionalBaselineDifferenceReceipt
    condition_binding_sha256: str
    arrays_sha256: str
    metrics_sha256: str
    receipt_sha256: str
    record_created_at: datetime


__all__ = [
    "BASELINE_DIFFERENCE_SAFETY_MARKER",
    "BaselineDifferenceConditionBinding",
    "BaselineDifferenceCreatedEvent",
    "BaselineDifferenceRecord",
    "BaselineDifferenceSourceProvenance",
    "ProvisionalBaselineDifferenceReceipt",
    "PublishedProvisionalBaselineDifference",
    "RepeatabilitySourceIdentity",
    "baseline_difference_state",
]
