"""Strict models for synthetic provisional offline QC evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.domain.paths import validate_relative_path

SHA256_PATTERN = r"^[0-9a-f]{64}$"
SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.-]+$"
QC_SAFETY_MARKER: Literal["SYNTHETIC_PROVISIONAL_QC_METRICS_NOT_AN_EXPERIMENTAL_RESULT"] = (
    "SYNTHETIC_PROVISIONAL_QC_METRICS_NOT_AN_EXPERIMENTAL_RESULT"
)


class ProvisionalQcModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def identifiers_are_not_path_tokens(self) -> ProvisionalQcModel:
        for name, value in self.__dict__.items():
            if name.endswith("_id") and value in {".", ".."}:
                raise ValueError(f"{name} must not be a path token")
        return self


class WaveformQcMetrics(ProvisionalQcModel):
    full_sample_count: int = Field(gt=0)
    peak_abs: float = Field(ge=0)
    rms: float = Field(ge=0)
    active_sweep_rms: float = Field(ge=0)
    pre_silence_rms: float | None = Field(default=None, ge=0)
    pre_silence_rms_status: Literal["computed", "pre_silence_absent"]
    clipped_sample_count: int = Field(ge=0)
    clipped_sample_fraction: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def nullable_pre_silence_matches_status(self) -> WaveformQcMetrics:
        if (self.pre_silence_rms is None) != (self.pre_silence_rms_status == "pre_silence_absent"):
            raise ValueError("pre-silence RMS nullability does not match its status")
        if self.clipped_sample_count > self.full_sample_count:
            raise ValueError("clipped sample count exceeds full sample count")
        if not math.isclose(
            self.clipped_sample_fraction,
            self.clipped_sample_count / self.full_sample_count,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise ValueError("clipped sample fraction differs from its counts")
        return self


class ProvisionalQcMetrics(ProvisionalQcModel):
    schema_version: Literal["1.0.0"]
    output_reference: WaveformQcMetrics
    captured_input: WaveformQcMetrics
    input_pre_silence_snr_proxy_db: float | None
    input_pre_silence_snr_proxy_status: Literal[
        "computed",
        "pre_silence_absent",
        "zero_pre_silence_rms",
        "zero_active_sweep_rms",
    ]
    estimated_latency_samples: int = Field(ge=0)
    estimated_latency_seconds: float = Field(ge=0)
    matched_correlation_signed: float = Field(ge=-1, le=1)
    matched_correlation_absolute: float = Field(ge=0, le=1)
    ir_dominant_peak_index: int = Field(ge=0)
    ir_dominant_peak_value: float
    ir_dominant_peak_abs: float = Field(gt=0)
    ir_second_largest_abs: float | None = Field(default=None, ge=0)
    ir_peak_to_second_peak_ratio: float | None = Field(default=None, ge=0)
    ir_peak_to_second_peak_ratio_status: Literal[
        "computed", "single_sample_ir", "zero_second_largest_abs"
    ]
    reference_deconvolution_peak_abs: float = Field(gt=0)
    reference_deconvolution_off_peak_rms: float | None = Field(default=None, ge=0)
    reference_peak_to_off_peak_rms_ratio: float | None = Field(default=None, ge=0)
    reference_peak_to_off_peak_rms_ratio_status: Literal[
        "computed", "no_off_peak_samples", "zero_off_peak_rms"
    ]
    analysis_band_bin_count: int = Field(gt=0)
    spectral_division_valid_bin_count_in_band: int = Field(ge=0)
    spectral_division_zeroed_bin_count_in_band: int = Field(ge=0)
    spectral_division_valid_fraction_in_band: float = Field(ge=0, le=1)
    transfer_raw_finite_bin_count_in_band: int = Field(ge=0)
    transfer_raw_finite_fraction_in_band: float = Field(ge=0, le=1)
    transfer_aligned_finite_bin_count_in_band: int = Field(ge=0)
    transfer_aligned_finite_fraction_in_band: float = Field(ge=0, le=1)
    all_required_numeric_values_finite: Literal[True]

    @model_validator(mode="after")
    def nullable_metrics_and_counts_are_consistent(self) -> ProvisionalQcMetrics:
        snr_computed = self.input_pre_silence_snr_proxy_status == "computed"
        if (self.input_pre_silence_snr_proxy_db is not None) != snr_computed:
            raise ValueError("SNR proxy nullability does not match its status")
        pre_rms = self.captured_input.pre_silence_rms
        active_rms = self.captured_input.active_sweep_rms
        if self.input_pre_silence_snr_proxy_status == "pre_silence_absent" and (
            self.captured_input.pre_silence_rms_status != "pre_silence_absent"
        ):
            raise ValueError("SNR absent status requires absent pre-silence")
        if self.input_pre_silence_snr_proxy_status == "zero_pre_silence_rms" and (
            pre_rms != 0 or active_rms <= 0
        ):
            raise ValueError("zero pre-silence SNR status differs from waveform metrics")
        if self.input_pre_silence_snr_proxy_status == "zero_active_sweep_rms" and (active_rms != 0):
            raise ValueError("zero active-sweep SNR status differs from waveform metrics")
        if snr_computed and (pre_rms is None or pre_rms <= 0 or active_rms <= 0):
            raise ValueError("computed SNR requires positive active and pre-silence RMS")

        ir_computed = self.ir_peak_to_second_peak_ratio_status == "computed"
        if (self.ir_peak_to_second_peak_ratio is not None) != ir_computed:
            raise ValueError("IR peak ratio nullability does not match its status")
        if (self.ir_second_largest_abs is None) != (
            self.ir_peak_to_second_peak_ratio_status == "single_sample_ir"
        ):
            raise ValueError("IR second peak nullability does not match its status")
        if self.ir_peak_to_second_peak_ratio_status == "zero_second_largest_abs" and (
            self.ir_second_largest_abs != 0
        ):
            raise ValueError("zero second-peak status requires a zero second peak")

        reference_computed = self.reference_peak_to_off_peak_rms_ratio_status == "computed"
        if (self.reference_peak_to_off_peak_rms_ratio is not None) != reference_computed:
            raise ValueError("reference ratio nullability does not match its status")
        if (self.reference_deconvolution_off_peak_rms is None) != (
            self.reference_peak_to_off_peak_rms_ratio_status == "no_off_peak_samples"
        ):
            raise ValueError("reference off-peak RMS nullability does not match its status")
        if self.reference_peak_to_off_peak_rms_ratio_status == "zero_off_peak_rms" and (
            self.reference_deconvolution_off_peak_rms != 0
        ):
            raise ValueError("zero off-peak status requires zero off-peak RMS")

        if (
            self.spectral_division_valid_bin_count_in_band
            + self.spectral_division_zeroed_bin_count_in_band
            != self.analysis_band_bin_count
        ):
            raise ValueError("spectral division coverage counts do not cover the analysis band")
        if self.transfer_raw_finite_bin_count_in_band > self.analysis_band_bin_count:
            raise ValueError("raw finite count exceeds analysis band")
        if self.transfer_aligned_finite_bin_count_in_band > self.analysis_band_bin_count:
            raise ValueError("aligned finite count exceeds analysis band")
        fractions = (
            (
                self.spectral_division_valid_fraction_in_band,
                self.spectral_division_valid_bin_count_in_band,
            ),
            (
                self.transfer_raw_finite_fraction_in_band,
                self.transfer_raw_finite_bin_count_in_band,
            ),
            (
                self.transfer_aligned_finite_fraction_in_band,
                self.transfer_aligned_finite_bin_count_in_band,
            ),
        )
        if any(
            not math.isclose(fraction, count / self.analysis_band_bin_count, rel_tol=0, abs_tol=0)
            for fraction, count in fractions
        ):
            raise ValueError("analysis-band fraction differs from its counts")
        if not math.isclose(
            self.matched_correlation_absolute,
            abs(self.matched_correlation_signed),
            rel_tol=0,
            abs_tol=1e-15,
        ):
            raise ValueError("absolute correlation differs from signed correlation")
        return self


class ProvisionalQcReceipt(ProvisionalQcModel):
    schema_version: Literal["1.0.0"]
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    source_run_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    processing_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    qc_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    source_capture_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_processing_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_processing_arrays_sha256: str = Field(pattern=SHA256_PATTERN)
    source_processing_schema_version: Literal["1.1.0"]
    source_processing_algorithm_id: Literal["offline_ess_deconvolution_transfer"]
    source_processing_algorithm_version: Literal["1.1.0"]
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_config_reference: str
    analysis_config_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_config_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    qc_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    qc_algorithm_id: Literal["provisional_offline_qc_metrics"]
    qc_algorithm_version: Literal["1.0.0"]
    waveform_metric_formula_id: Literal["float64_peak_rms_active_pre_and_abs_ge_one_clip"]
    snr_proxy_formula_id: Literal["20_log10_input_active_rms_over_pre_silence_rms"]
    latency_evidence_source: Literal["validated_processing_receipt"]
    ir_concentration_formula_id: Literal["dominant_abs_over_second_largest_abs"]
    reference_residual_formula_id: Literal["reference_peak_abs_over_off_peak_rms"]
    spectral_coverage_formula_id: Literal[
        "rfft_reference_above_max_abs_times_float64_epsilon_times_reference_count"
    ]
    metric_computation_status: Literal["complete"]
    evaluation_status: Literal["provisional_metrics_only"]
    decision_status: Literal["not_evaluated"]
    thresholds_applied: Literal[False]
    qc_threshold: None
    threshold_source: None
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
    safety_marker: Literal["SYNTHETIC_PROVISIONAL_QC_METRICS_NOT_AN_EXPERIMENTAL_RESULT"]

    @field_validator("analysis_config_reference")
    @classmethod
    def analysis_reference_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)


class QcRecord(ProvisionalQcModel):
    schema_version: Literal["1.0.0"]
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    source_run_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    processing_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    qc_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    created_at: AwareDatetime
    status: Literal["complete"]
    qc_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    qc_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    evaluation_status: Literal["provisional_metrics_only"]
    decision_status: Literal["not_evaluated"]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    result_marker: Literal["NOT_AN_EXPERIMENTAL_RESULT"]


class QcCreatedEvent(ProvisionalQcModel):
    schema_version: Literal["1.0.0"]
    event: Literal["qc_created"]
    sequence: int = Field(gt=0)
    session_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    data_origin: Literal["synthetic"]
    source_run_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    processing_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    qc_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    created_at: AwareDatetime
    qc_record_sha256: str = Field(pattern=SHA256_PATTERN)
    qc_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    qc_receipt_sha256: str = Field(pattern=SHA256_PATTERN)


@dataclass(frozen=True)
class PublishedProvisionalQc:
    qc_path: Path
    metrics: ProvisionalQcMetrics
    receipt: ProvisionalQcReceipt
    metrics_sha256: str
    receipt_sha256: str
    record_created_at: datetime
