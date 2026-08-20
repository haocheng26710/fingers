"""Strict persisted contracts for synthetic measurement-matrix evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from acoustic_ladder.audio.baseline_difference import ProvisionalBaselineDifferenceMetrics
from acoustic_ladder.audio.provisional_qc_models import ProvisionalQcMetrics
from acoustic_ladder.domain.models import ConfigSnapshot

from .measurement_identity import MeasurementIdentity
from .split_plan import SplitPlan

SHA256_PATTERN = r"^[0-9a-f]{64}$"
SAFETY_MARKER: Literal["SYNTHETIC_MEASUREMENT_MATRIX_NOT_AN_EXPERIMENTAL_RESULT"] = (
    "SYNTHETIC_MEASUREMENT_MATRIX_NOT_AN_EXPERIMENTAL_RESULT"
)


class AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class SourceExecutionBinding(AnalysisModel):
    experiment_stage: Literal[1, 2, 3, 4]
    execution_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    execution_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_completion_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_completed_at_utc: AwareDatetime
    ordered_work_order_sha256: str = Field(pattern=SHA256_PATTERN)
    row_count: int = Field(gt=0)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    config_snapshots: dict[str, ConfigSnapshot]
    compiled_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_plan_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    schedule_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_reference: str
    scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_artifact_id: str
    source_ess_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)


class AnalysisSourceBinding(AnalysisModel):
    schema_version: Literal["1.1.0"]
    analysis_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    analysis_spec_reference: str
    analysis_spec_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_spec_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    ordered_source_aggregate_sha256: str = Field(pattern=SHA256_PATTERN)
    executions: tuple[SourceExecutionBinding, ...] = Field(min_length=4, max_length=4)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    source_execution_complete: Literal[True]
    source_execution_validated: Literal[True]


class MeasurementRow(MeasurementIdentity):
    schema_version: Literal["1.0.0"]
    matrix_row_ordinal: int = Field(gt=0)
    execution_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_completion_sha256: str = Field(pattern=SHA256_PATTERN)
    capture_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    run_record_sha256: str = Field(pattern=SHA256_PATTERN)
    ordered_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_reference_row_ids: tuple[str, ...] = Field(min_length=1)
    qc_metrics: ProvisionalQcMetrics
    baseline_difference_metrics: ProvisionalBaselineDifferenceMetrics
    qc_decision: Literal["not_evaluated"]
    thresholds_applied: Literal[False]
    development_synthetic_run: Literal[True]
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    hardware_io_performed: Literal[False]


class MeasurementRowIndex(AnalysisModel):
    schema_version: Literal["1.0.0"]
    row_count: int = Field(gt=0)
    rows: tuple[MeasurementRow, ...] = Field(min_length=1)


class FeatureColumn(AnalysisModel):
    ordinal: int = Field(gt=0)
    feature_id: str = Field(pattern=r"^[a-z0-9_]+$")
    unit: str
    definition: str
    source_arrays: tuple[str, ...] = Field(min_length=1)
    version: Literal["1.0.0"]


class FeatureColumnSchema(AnalysisModel):
    schema_version: Literal["1.0.0"]
    feature_count: Literal[16]
    scalar_dtype: Literal["float64"]
    columns: tuple[FeatureColumn, ...] = Field(min_length=16, max_length=16)
    pca_performed: Literal[False]
    feature_selection_performed: Literal[False]
    normalization_fitting_performed: Literal[False]


class AnalysisState(AnalysisModel):
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    analysis_status: Literal["provisional_measurement_matrix_only"]
    source_execution_complete: Literal[True]
    source_execution_validated: Literal[True]
    measurement_row_count: Literal[344]
    stage_1_row_count: Literal[152]
    stage_2_row_count: Literal[32]
    stage_3_row_count: Literal[32]
    stage_4_row_count: Literal[128]
    rows_excluded: Literal[0]
    silent_exclusion_performed: Literal[False]
    feature_extraction_performed: Literal[True]
    split_plan_generated: Literal[True]
    model_fit_performed: Literal[False]
    prediction_performed: Literal[False]
    classification_performed: Literal[False]
    interaction_analysis_performed: Literal[False]
    thresholds_applied: Literal[False]
    qc_decision: Literal["not_evaluated"]
    analysis_decision: Literal["not_evaluated"]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    hardware_enumeration_performed: Literal[False]
    hardware_io_performed: Literal[False]
    playback_performed: Literal[False]
    recording_performed: Literal[False]
    stream_opened: Literal[False]
    calibration_performed: Literal[False]
    absolute_spl_verified: Literal[False]
    day_group_status: Literal["trusted_day_identity_unavailable"]
    safety_marker: Literal["SYNTHETIC_MEASUREMENT_MATRIX_NOT_AN_EXPERIMENTAL_RESULT"]


class AnalysisReceipt(AnalysisState):
    schema_version: Literal["1.1.0"]
    algorithm_id: Literal["plan_bound_synthetic_measurement_matrix"]
    algorithm_version: Literal["1.1.0"]
    analysis_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    analysis_source_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    measurement_row_index_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_schema_sha256: str = Field(pattern=SHA256_PATTERN)
    split_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    measurement_matrix_npz_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_record_sha256: str = Field(pattern=SHA256_PATTERN)
    ordered_source_aggregate_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_evidence_time: AwareDatetime
    analysis_evidence_time_basis: Literal["latest_verified_execution_completion_utc"]
    analysis_evidence_time_derivation_version: Literal["1.0.0"]
    feature_count: Literal[16]
    split_fold_count: Literal[24]


class AnalysisMetadata(AnalysisState):
    schema_version: Literal["1.1.0"]
    analysis_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    analysis_evidence_time: AwareDatetime
    analysis_evidence_time_basis: Literal["latest_verified_execution_completion_utc"]
    ordered_source_aggregate_sha256: str = Field(pattern=SHA256_PATTERN)


class AnalysisRecord(AnalysisState):
    schema_version: Literal["1.1.0"]
    analysis_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    analysis_relative_path: str
    analysis_evidence_time: AwareDatetime
    analysis_evidence_time_basis: Literal["latest_verified_execution_completion_utc"]
    ordered_source_aggregate_sha256: str = Field(pattern=SHA256_PATTERN)
    immutable_status: Literal["complete"]


class PublishedSyntheticMeasurementMatrix(AnalysisModel):
    analysis_id: str
    analysis_path: str
    receipt: AnalysisReceipt
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)


def provisional_state() -> dict[str, object]:
    return {
        "data_origin": "synthetic",
        "run_mode": "development",
        "analysis_status": "provisional_measurement_matrix_only",
        "source_execution_complete": True,
        "source_execution_validated": True,
        "measurement_row_count": 344,
        "stage_1_row_count": 152,
        "stage_2_row_count": 32,
        "stage_3_row_count": 32,
        "stage_4_row_count": 128,
        "rows_excluded": 0,
        "silent_exclusion_performed": False,
        "feature_extraction_performed": True,
        "split_plan_generated": True,
        "model_fit_performed": False,
        "prediction_performed": False,
        "classification_performed": False,
        "interaction_analysis_performed": False,
        "thresholds_applied": False,
        "qc_decision": "not_evaluated",
        "analysis_decision": "not_evaluated",
        "formal_eligible": False,
        "experimental_result": False,
        "hardware_enumeration_performed": False,
        "hardware_io_performed": False,
        "playback_performed": False,
        "recording_performed": False,
        "stream_opened": False,
        "calibration_performed": False,
        "absolute_spl_verified": False,
        "day_group_status": "trusted_day_identity_unavailable",
        "safety_marker": SAFETY_MARKER,
    }


__all__ = [
    "SAFETY_MARKER",
    "AnalysisMetadata",
    "AnalysisReceipt",
    "AnalysisRecord",
    "AnalysisSourceBinding",
    "FeatureColumn",
    "FeatureColumnSchema",
    "MeasurementRow",
    "MeasurementRowIndex",
    "PublishedSyntheticMeasurementMatrix",
    "SourceExecutionBinding",
    "SplitPlan",
    "provisional_state",
]
