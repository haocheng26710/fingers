"""Strict contracts for deterministic synthetic offline ESS processing artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.domain.models import ConfigSnapshot
from acoustic_ladder.domain.paths import validate_relative_path

SHA256_PATTERN = r"^[0-9a-f]{64}$"
SAFETY_MARKER: Literal["SYNTHETIC_OFFLINE_ESS_PROCESSING_NOT_AN_EXPERIMENTAL_RESULT"] = (
    "SYNTHETIC_OFFLINE_ESS_PROCESSING_NOT_AN_EXPERIMENTAL_RESULT"
)


class EssProcessingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ProcessingArrayDescriptor(EssProcessingModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    dtype: Literal["float64", "int64", "bool"]
    shape: tuple[int, ...]
    raw_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("shape")
    @classmethod
    def shape_is_nonempty_and_nonnegative(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or any(dimension < 0 for dimension in value):
            raise ValueError("array shape must be non-empty and non-negative")
        return value


class EssProcessingReceipt(EssProcessingModel):
    schema_version: Literal["1.1.0"]
    processing_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    source_run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    source_capture_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_output_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_input_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_output_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    source_input_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    source_capture_scenario_reference: str
    source_capture_scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    source_capture_scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_artifact_id: str
    source_ess_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    config_snapshots: dict[str, ConfigSnapshot]
    analysis_config_reference: str
    analysis_config_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    analysis_config_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    algorithm_id: Literal["offline_ess_deconvolution_transfer"]
    algorithm_version: Literal["1.1.0"]
    inverse_formula_id: Literal["farina_exponential_sweep_amplitude_compensation"]
    inverse_filter_formula: Literal["s[N-1-n]*exp(-ln(f_end/f_start)*n/N)"]
    convolution_method: Literal["full_linear_rfft_power_of_two"]
    latency_method: Literal["normalized_full_sweep_matched_correlation"]
    lag_convention: Literal["positive_input_lags_output"]
    alignment_method: Literal["zero_fill_no_circular_wrap"]
    transfer_estimator_id: Literal["complex_spectral_ratio"]
    transfer_raw_definition: Literal["rfft(input_after_pre)/rfft(output_after_pre)"]
    transfer_aligned_definition: Literal[
        "rfft(zero_fill_advance(input_after_pre,estimated_latency_samples))/rfft(output_after_pre)"
    ]
    spectral_division_threshold_formula: Literal[
        "max_abs_reference_spectrum*float64_epsilon*reference_sample_count"
    ]
    spectral_division_below_threshold_policy: Literal["zero_where_reference_at_or_below_threshold"]
    deconvolution_time_origin: Literal["reference_deconvolution_unique_absolute_peak"]
    ir_raw_definition: Literal["input_deconvolution_from_reference_peak"]
    phase_unwrap_axis: Literal["frequency_last_axis"]
    sample_rate_hz: int = Field(gt=0)
    sweep_sample_count: int = Field(gt=1)
    pre_silence_sample_count: int = Field(ge=0)
    post_silence_sample_count: int = Field(ge=0)
    source_output_sample_count: int = Field(gt=0)
    source_input_sample_count: int = Field(gt=0)
    output_after_pre_sample_count: int = Field(gt=0)
    input_after_pre_sample_count: int = Field(gt=0)
    inverse_filter_sample_count: int = Field(gt=0)
    reference_deconvolution_sample_count: int = Field(gt=0)
    input_deconvolution_sample_count: int = Field(gt=0)
    ir_sample_count: int = Field(gt=0)
    inverse_fft_length: int = Field(gt=0)
    deconvolution_fft_length: int = Field(gt=0)
    transfer_fft_length: int = Field(gt=0)
    frequency_bin_count: int = Field(gt=0)
    reference_peak_index: int = Field(ge=0)
    inverse_pre_normalization_peak: float = Field(gt=0)
    inverse_normalization_factor: float
    inverse_post_normalization_peak: float = Field(gt=0)
    estimated_latency_samples: int = Field(ge=0)
    estimated_latency_seconds: float = Field(ge=0)
    matched_correlation_signed: float = Field(ge=-1, le=1)
    matched_correlation_absolute: float = Field(ge=0, le=1)
    candidate_lag_min: Literal[0]
    candidate_lag_max: int = Field(ge=0)
    ir_dominant_peak_index: int = Field(ge=0)
    ir_dominant_peak_value: float
    analysis_band_lower_hz: float = Field(gt=0)
    analysis_band_upper_hz: float = Field(gt=0)
    smoothing_enabled: Literal[False]
    db_floor_strategy: Literal["numpy_float64_tiny_before_log10"]
    array_descriptors: dict[str, ProcessingArrayDescriptor]
    processing_arrays_npz_sha256: str = Field(pattern=SHA256_PATTERN)
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
    safety_marker: Literal["SYNTHETIC_OFFLINE_ESS_PROCESSING_NOT_AN_EXPERIMENTAL_RESULT"]

    @field_validator("source_capture_scenario_reference", "analysis_config_reference")
    @classmethod
    def references_are_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @model_validator(mode="after")
    def descriptor_names_match_keys(self) -> EssProcessingReceipt:
        if any(name != descriptor.name for name, descriptor in self.array_descriptors.items()):
            raise ValueError("array descriptor keys must match descriptor names")
        if self.analysis_band_lower_hz >= self.analysis_band_upper_hz:
            raise ValueError("analysis band must be ordered")
        if self.frequency_bin_count != self.transfer_fft_length // 2 + 1:
            raise ValueError("frequency bin count does not match transfer FFT length")
        return self


class ProcessingRecord(EssProcessingModel):
    schema_version: Literal["1.0.0"]
    processing_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    source_run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    created_at: AwareDatetime
    status: Literal["complete"]
    processing_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    result_marker: Literal["NOT_AN_EXPERIMENTAL_RESULT"]


class ProcessingCreatedEvent(EssProcessingModel):
    schema_version: Literal["1.0.0"]
    event: Literal["processing_created"]
    sequence: int = Field(gt=0)
    session_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    data_origin: Literal["synthetic"]
    processing_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    source_run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    created_at: AwareDatetime
    processing_record_sha256: str = Field(pattern=SHA256_PATTERN)
    processing_receipt_sha256: str = Field(pattern=SHA256_PATTERN)


@dataclass(frozen=True)
class PublishedEssProcessing:
    processing_path: Path
    receipt: EssProcessingReceipt
    receipt_sha256: str
    arrays_sha256: str
    record_created_at: datetime
