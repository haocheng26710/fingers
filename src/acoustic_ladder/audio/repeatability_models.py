"""Strict contracts for provisional synthetic repeatability evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from statistics import fmean
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.domain.paths import validate_relative_path
from acoustic_ladder.storage.io import sha256_bytes

SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.-]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
REPEATABILITY_SAFETY_MARKER: Literal[
    "SYNTHETIC_PROVISIONAL_REPEATABILITY_METRICS_NOT_AN_EXPERIMENTAL_RESULT"
] = "SYNTHETIC_PROVISIONAL_REPEATABILITY_METRICS_NOT_AN_EXPERIMENTAL_RESULT"


class RepeatabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def identifiers_are_not_path_tokens(self) -> RepeatabilityModel:
        for name, value in self.__dict__.items():
            if name.endswith("_id") and value in {".", ".."}:
                raise ValueError(f"{name} must not be a path token")
        return self


class RepeatabilityMemberIdentity(RepeatabilityModel):
    source_run_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    processing_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    qc_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)


class RepeatabilityMemberEvidence(RepeatabilityModel):
    identity: RepeatabilityMemberIdentity
    measurement_order: int = Field(ge=0)
    latency_samples: int = Field(ge=0)


class RepeatabilityPairMetrics(RepeatabilityModel):
    left_member: RepeatabilityMemberIdentity
    right_member: RepeatabilityMemberIdentity
    left_measurement_order: int = Field(ge=0)
    right_measurement_order: int = Field(ge=0)
    captured_input_correlation: float | None = Field(default=None, ge=-1, le=1)
    captured_input_correlation_status: Literal[
        "computed", "zero_left_norm", "zero_right_norm", "zero_both_norm"
    ]
    latency_delta_samples: int
    latency_absolute_delta_samples: int = Field(ge=0)
    ir_correlation: float | None = Field(default=None, ge=-1, le=1)
    ir_correlation_status: Literal[
        "computed", "zero_left_norm", "zero_right_norm", "zero_both_norm"
    ]
    ir_symmetric_nrmse: float | None = Field(default=None, ge=0)
    ir_symmetric_nrmse_status: Literal["computed", "zero_symmetric_norm"]
    complex_transfer_relative_l2: float | None = Field(default=None, ge=0)
    complex_transfer_relative_l2_status: Literal["computed", "zero_symmetric_norm"]
    magnitude_rmse_db: float = Field(ge=0)
    analysis_band_bin_count: int = Field(gt=0)
    joint_phase_valid_bin_count: int = Field(ge=0)
    joint_phase_valid_fraction: float = Field(ge=0, le=1)
    phase_rms_rad: float | None = Field(default=None, ge=0)
    phase_rms_status: Literal["computed", "no_joint_phase_valid_bins"]

    @model_validator(mode="after")
    def pair_semantics_are_consistent(self) -> RepeatabilityPairMetrics:
        if self.left_measurement_order >= self.right_measurement_order:
            raise ValueError("pair members must follow measurement order")
        if self.latency_absolute_delta_samples != abs(self.latency_delta_samples):
            raise ValueError("absolute latency delta differs from signed delta")
        nullable_statuses = (
            (self.captured_input_correlation, self.captured_input_correlation_status),
            (self.ir_correlation, self.ir_correlation_status),
            (self.ir_symmetric_nrmse, self.ir_symmetric_nrmse_status),
            (
                self.complex_transfer_relative_l2,
                self.complex_transfer_relative_l2_status,
            ),
            (self.phase_rms_rad, self.phase_rms_status),
        )
        if any(
            (value is not None) != (status == "computed") for value, status in nullable_statuses
        ):
            raise ValueError("pair metric nullability differs from its status")
        if (self.joint_phase_valid_bin_count == 0) != (
            self.phase_rms_status == "no_joint_phase_valid_bins"
        ):
            raise ValueError("phase status differs from its valid-bin count")
        if self.joint_phase_valid_bin_count > self.analysis_band_bin_count:
            raise ValueError("joint phase-valid count exceeds the analysis band")
        if self.joint_phase_valid_fraction != (
            self.joint_phase_valid_bin_count / self.analysis_band_bin_count
        ):
            raise ValueError("joint phase-valid fraction differs from its count")
        return self


class ProvisionalRepeatabilityMetrics(RepeatabilityModel):
    schema_version: Literal["1.0.0"]
    members: list[RepeatabilityMemberEvidence]
    pairs: list[RepeatabilityPairMetrics]
    member_count: int = Field(ge=2)
    pair_count: int = Field(gt=0)
    measurement_order_min: int = Field(ge=0)
    measurement_order_max: int = Field(ge=0)
    latency_min_samples: int = Field(ge=0)
    latency_max_samples: int = Field(ge=0)
    latency_span_samples: int = Field(ge=0)
    pairwise_maximum_absolute_latency_delta_samples: int = Field(ge=0)
    captured_input_correlation_defined_count: int = Field(ge=0)
    captured_input_correlation_min: float | None = Field(default=None, ge=-1, le=1)
    captured_input_correlation_mean: float | None = Field(default=None, ge=-1, le=1)
    ir_correlation_defined_count: int = Field(ge=0)
    ir_correlation_min: float | None = Field(default=None, ge=-1, le=1)
    ir_correlation_mean: float | None = Field(default=None, ge=-1, le=1)
    ir_symmetric_nrmse_defined_count: int = Field(ge=0)
    ir_symmetric_nrmse_mean: float | None = Field(default=None, ge=0)
    ir_symmetric_nrmse_max: float | None = Field(default=None, ge=0)
    complex_transfer_relative_l2_defined_count: int = Field(ge=0)
    complex_transfer_relative_l2_mean: float | None = Field(default=None, ge=0)
    complex_transfer_relative_l2_max: float | None = Field(default=None, ge=0)
    magnitude_rmse_db_defined_count: int = Field(ge=0)
    magnitude_rmse_db_mean: float = Field(ge=0)
    magnitude_rmse_db_max: float = Field(ge=0)
    phase_rms_rad_defined_count: int = Field(ge=0)
    phase_rms_rad_mean: float | None = Field(default=None, ge=0)
    phase_rms_rad_max: float | None = Field(default=None, ge=0)
    phase_valid_fraction_min: float = Field(ge=0, le=1)
    phase_valid_fraction_mean: float = Field(ge=0, le=1)
    all_required_numeric_values_finite: Literal[True]

    @model_validator(mode="after")
    def collection_shape_is_consistent(self) -> ProvisionalRepeatabilityMetrics:
        if self.member_count != len(self.members):
            raise ValueError("member count differs from member evidence")
        expected_pairs = self.member_count * (self.member_count - 1) // 2
        if self.pair_count != expected_pairs or self.pair_count != len(self.pairs):
            raise ValueError("pair count differs from the unique unordered member pairs")
        orders = [member.measurement_order for member in self.members]
        if orders != sorted(orders) or orders != list(range(orders[0], orders[-1] + 1)):
            raise ValueError("member measurement orders must be sorted and continuous")
        if self.measurement_order_min != orders[0] or self.measurement_order_max != orders[-1]:
            raise ValueError("measurement order aggregate differs")
        latencies = [member.latency_samples for member in self.members]
        if (
            self.latency_min_samples != min(latencies)
            or self.latency_max_samples != max(latencies)
            or self.latency_span_samples != max(latencies) - min(latencies)
        ):
            raise ValueError("latency aggregate differs")
        expected_pair_members = [
            (left.identity, right.identity, left.measurement_order, right.measurement_order)
            for left, right in combinations(self.members, 2)
        ]
        actual_pair_members = [
            (
                pair.left_member,
                pair.right_member,
                pair.left_measurement_order,
                pair.right_measurement_order,
            )
            for pair in self.pairs
        ]
        if actual_pair_members != expected_pair_members:
            raise ValueError("pair records differ from the complete ordered member pairs")

        def defined_min_mean(
            values: list[float | None],
        ) -> tuple[int, float | None, float | None]:
            present = [value for value in values if value is not None]
            if not present:
                return 0, None, None
            return len(present), min(present), fmean(present)

        def defined_mean_max(
            values: list[float | None],
        ) -> tuple[int, float | None, float | None]:
            present = [value for value in values if value is not None]
            if not present:
                return 0, None, None
            return len(present), fmean(present), max(present)

        aggregate_checks: tuple[tuple[object, object], ...] = (
            (
                self.pairwise_maximum_absolute_latency_delta_samples,
                max(pair.latency_absolute_delta_samples for pair in self.pairs),
            ),
            (
                (
                    self.captured_input_correlation_defined_count,
                    self.captured_input_correlation_min,
                    self.captured_input_correlation_mean,
                ),
                defined_min_mean([pair.captured_input_correlation for pair in self.pairs]),
            ),
            (
                (
                    self.ir_correlation_defined_count,
                    self.ir_correlation_min,
                    self.ir_correlation_mean,
                ),
                defined_min_mean([pair.ir_correlation for pair in self.pairs]),
            ),
            (
                (
                    self.ir_symmetric_nrmse_defined_count,
                    self.ir_symmetric_nrmse_mean,
                    self.ir_symmetric_nrmse_max,
                ),
                defined_mean_max([pair.ir_symmetric_nrmse for pair in self.pairs]),
            ),
            (
                (
                    self.complex_transfer_relative_l2_defined_count,
                    self.complex_transfer_relative_l2_mean,
                    self.complex_transfer_relative_l2_max,
                ),
                defined_mean_max([pair.complex_transfer_relative_l2 for pair in self.pairs]),
            ),
            (
                (
                    self.magnitude_rmse_db_defined_count,
                    self.magnitude_rmse_db_mean,
                    self.magnitude_rmse_db_max,
                ),
                (
                    self.pair_count,
                    fmean(pair.magnitude_rmse_db for pair in self.pairs),
                    max(pair.magnitude_rmse_db for pair in self.pairs),
                ),
            ),
            (
                (
                    self.phase_rms_rad_defined_count,
                    self.phase_rms_rad_mean,
                    self.phase_rms_rad_max,
                ),
                defined_mean_max([pair.phase_rms_rad for pair in self.pairs]),
            ),
            (
                (self.phase_valid_fraction_min, self.phase_valid_fraction_mean),
                (
                    min(pair.joint_phase_valid_fraction for pair in self.pairs),
                    fmean(pair.joint_phase_valid_fraction for pair in self.pairs),
                ),
            ),
        )
        if any(actual != expected for actual, expected in aggregate_checks):
            raise ValueError("aggregate fields differ from pair records")
        numeric = self.model_dump()
        if "NaN" in str(numeric) or "Infinity" in str(numeric):
            raise ValueError("repeatability metrics contain non-finite values")
        return self


class RepeatabilityMemberProvenance(RepeatabilityModel):
    identity: RepeatabilityMemberIdentity
    measurement_order: int = Field(ge=0)
    estimated_latency_samples: int = Field(ge=0)
    capture_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    captured_input_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    processing_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    processing_arrays_sha256: str = Field(pattern=SHA256_PATTERN)
    qc_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    qc_receipt_sha256: str = Field(pattern=SHA256_PATTERN)


class ProvisionalRepeatabilityReceipt(RepeatabilityModel):
    schema_version: Literal["1.0.0"]
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    reassembly_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    repeat_set_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    members: list[RepeatabilityMemberProvenance]
    normalized_member_list_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    audio_config_reference: str
    audio_config_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    audio_config_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_config_reference: str
    analysis_config_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_config_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    virtual_scenario_reference: str
    virtual_scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    virtual_scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_artifact_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    source_ess_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    processing_schema_version: Literal["1.1.0"]
    processing_algorithm_id: Literal["offline_ess_deconvolution_transfer"]
    processing_algorithm_version: Literal["1.1.0"]
    qc_schema_version: Literal["1.0.0"]
    qc_algorithm_id: Literal["provisional_offline_qc_metrics"]
    qc_algorithm_version: Literal["1.0.0"]
    sample_rate_hz: int = Field(gt=0)
    sweep_sample_count: int = Field(gt=1)
    pre_silence_sample_count: int = Field(ge=0)
    post_silence_sample_count: int = Field(ge=0)
    transfer_fft_length: int = Field(gt=0)
    frequency_bin_count: int = Field(gt=0)
    ir_sample_count: int = Field(gt=0)
    analysis_band_bin_count: int = Field(gt=0)
    analysis_band_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    repeatability_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    repeatability_algorithm_id: Literal["provisional_continuous_repeatability_metrics"]
    repeatability_algorithm_version: Literal["1.0.0"]
    pair_enumeration_formula_id: Literal["all_unique_unordered_pairs_in_measurement_order"]
    captured_input_correlation_formula_id: Literal[
        "normalized_dot_after_pre_silence_without_epsilon"
    ]
    latency_delta_formula_id: Literal["validated_processing_latency_j_minus_i"]
    ir_correlation_formula_id: Literal["normalized_dot_aligned_ir_without_epsilon"]
    ir_symmetric_nrmse_formula_id: Literal["symmetric_l2_over_root_mean_square_norm"]
    complex_transfer_relative_l2_formula_id: Literal[
        "analysis_band_symmetric_complex_l2_over_root_mean_square_norm"
    ]
    magnitude_rmse_formula_id: Literal["float64_tiny_floor_20_log10_magnitude_rmse_db"]
    phase_rms_formula_id: Literal["joint_nonzero_angle_h_i_times_conjugate_h_j_rms_without_unwrap"]
    metric_computation_status: Literal["complete"]
    evaluation_status: Literal["provisional_repeatability_metrics_only"]
    decision_status: Literal["not_evaluated"]
    thresholds_applied: Literal[False]
    repeatability_threshold: None
    threshold_source: None
    baseline_assigned: Literal[False]
    baseline_role: None
    baseline_difference_computed: Literal[False]
    protocol_condition_binding_performed: Literal[False]
    drift_evaluated: Literal[False]
    create_only: Literal[True]
    immutable: Literal[True]
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
    safety_marker: Literal["SYNTHETIC_PROVISIONAL_REPEATABILITY_METRICS_NOT_AN_EXPERIMENTAL_RESULT"]

    @field_validator(
        "audio_config_reference", "analysis_config_reference", "virtual_scenario_reference"
    )
    @classmethod
    def references_are_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @model_validator(mode="after")
    def normalized_members_are_valid(self) -> ProvisionalRepeatabilityReceipt:
        if len(self.members) < 2:
            raise ValueError("repeatability receipt requires at least two members")
        orders = [member.measurement_order for member in self.members]
        if orders != sorted(orders) or orders != list(range(orders[0], orders[-1] + 1)):
            raise ValueError("receipt members must have sorted continuous measurement orders")
        identities = [member.identity.model_dump_json() for member in self.members]
        source_runs = [member.identity.source_run_id for member in self.members]
        if len(set(identities)) != len(identities) or len(set(source_runs)) != len(source_runs):
            raise ValueError("receipt members must have unique identities and source runs")
        if self.frequency_bin_count != self.transfer_fft_length // 2 + 1:
            raise ValueError("frequency-bin count differs from transfer FFT length")
        if self.analysis_band_bin_count > self.frequency_bin_count:
            raise ValueError("analysis-band count exceeds frequency-bin count")
        expected_member_digest = sha256_bytes(
            canonical_json_bytes([member.model_dump(mode="json") for member in self.members])
        )
        if self.normalized_member_list_sha256 != expected_member_digest:
            raise ValueError("normalized member-list digest differs from receipt members")
        return self


class RepeatabilityRecord(RepeatabilityModel):
    schema_version: Literal["1.0.0"]
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    reassembly_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    repeat_set_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    created_at: AwareDatetime
    status: Literal["complete"]
    repeatability_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    repeatability_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    normalized_member_list_sha256: str = Field(pattern=SHA256_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    evaluation_status: Literal["provisional_repeatability_metrics_only"]
    decision_status: Literal["not_evaluated"]
    baseline_assigned: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    result_marker: Literal["NOT_AN_EXPERIMENTAL_RESULT"]


class RepeatabilityCreatedEvent(RepeatabilityModel):
    schema_version: Literal["1.0.0"]
    event: Literal["repeatability_created"]
    sequence: int = Field(gt=0)
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    data_origin: Literal["synthetic"]
    reassembly_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    repeat_set_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    created_at: AwareDatetime
    repeatability_record_sha256: str = Field(pattern=SHA256_PATTERN)
    repeatability_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    repeatability_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    normalized_member_list_sha256: str = Field(pattern=SHA256_PATTERN)


@dataclass(frozen=True)
class PublishedProvisionalRepeatability:
    repeatability_path: Path
    metrics: ProvisionalRepeatabilityMetrics
    receipt: ProvisionalRepeatabilityReceipt
    metrics_sha256: str
    receipt_sha256: str
    record_created_at: datetime
