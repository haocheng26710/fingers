"""Strict contracts for deterministic, offline-only ESS excitation artifacts."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.domain.paths import validate_relative_path


def round_half_up_samples(seconds: float, sample_rate_hz: int) -> int:
    """Convert non-negative seconds to samples with floor(x + 0.5)."""

    return math.floor(seconds * sample_rate_hz + 0.5)


class ExcitationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class EssSignalSpec(ExcitationModel):
    schema_version: Literal["1.0.0"]
    algorithm_id: Literal["exponential_sine_sweep"]
    algorithm_version: Literal["1.0.0"]
    sample_rate_hz: int = Field(gt=0)
    start_frequency_hz: float = Field(gt=0)
    end_frequency_hz: float = Field(gt=0)
    sweep_duration_s: float = Field(gt=0)
    pre_silence_s: float = Field(ge=0)
    post_silence_s: float = Field(ge=0)
    fade_in_s: float = Field(ge=0)
    fade_out_s: float = Field(ge=0)
    digital_peak_dbfs: float = Field(le=0)
    output_channel_count: Literal[1]
    output_dtype: Literal["float32"]
    usage_scope: Literal["development_fixture"]
    playback_authorized: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    artifact_origin: Literal["software_generated"]
    artifact_role: Literal["development_test_excitation"]

    @model_validator(mode="after")
    def validate_signal_boundaries(self) -> EssSignalSpec:
        if self.end_frequency_hz <= self.start_frequency_hz:
            raise ValueError("end_frequency_hz must be above start_frequency_hz")
        if self.end_frequency_hz >= self.sample_rate_hz / 2:
            raise ValueError("end_frequency_hz must be below Nyquist")
        if self.fade_in_s + self.fade_out_s > self.sweep_duration_s:
            raise ValueError("fade durations cannot exceed sweep duration")
        sweep_count = round_half_up_samples(self.sweep_duration_s, self.sample_rate_hz)
        if sweep_count < 2:
            raise ValueError("sweep duration must produce at least two samples")
        target_peak = 10.0 ** (self.digital_peak_dbfs / 20.0)
        target_peak_float32 = np.float32(target_peak)
        if (
            not math.isfinite(target_peak)
            or target_peak <= 0
            or not np.isfinite(target_peak_float32)
            or target_peak_float32 <= 0
        ):
            raise ValueError("digital peak is not representable as a positive float32 amplitude")
        fade_counts = (
            round_half_up_samples(self.fade_in_s, self.sample_rate_hz),
            round_half_up_samples(self.fade_out_s, self.sample_rate_hz),
        )
        if any(
            duration > 0 and count < 2
            for duration, count in zip((self.fade_in_s, self.fade_out_s), fade_counts, strict=True)
        ):
            raise ValueError("each non-zero fade must contain at least two samples")
        if sum(fade_counts) > sweep_count:
            raise ValueError("derived fade sample counts cannot exceed sweep sample count")
        return self


class EssSampleTiming(ExcitationModel):
    requested_sweep_duration_s: float = Field(gt=0)
    actual_sweep_duration_s: float = Field(gt=0)
    sweep_duration_error_s: float
    requested_pre_silence_s: float = Field(ge=0)
    actual_pre_silence_s: float = Field(ge=0)
    pre_silence_error_s: float
    requested_post_silence_s: float = Field(ge=0)
    actual_post_silence_s: float = Field(ge=0)
    post_silence_error_s: float
    requested_fade_in_s: float = Field(ge=0)
    actual_fade_in_s: float = Field(ge=0)
    fade_in_error_s: float
    requested_fade_out_s: float = Field(ge=0)
    actual_fade_out_s: float = Field(ge=0)
    fade_out_error_s: float
    sweep_sample_count: int = Field(ge=2)
    pre_silence_sample_count: int = Field(ge=0)
    post_silence_sample_count: int = Field(ge=0)
    fade_in_sample_count: int = Field(ge=0)
    fade_out_sample_count: int = Field(ge=0)
    total_sample_count: int = Field(gt=0)


class EssSignalMetrics(ExcitationModel):
    target_peak_dbfs: float = Field(le=0)
    target_linear_peak: float = Field(gt=0, le=1)
    pre_normalization_peak: float = Field(gt=0)
    normalization_factor: float = Field(gt=0)
    actual_peak: float = Field(gt=0, le=1)
    rms: float = Field(gt=0)
    crest_factor: float = Field(gt=0)
    mean_dc: float
    minimum: float = Field(ge=-1, le=1)
    maximum: float = Field(ge=-1, le=1)
    all_finite: Literal[True]


class EssArtifactMetadata(ExcitationModel):
    schema_version: Literal["1.0.0"]
    artifact_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    artifact_origin: Literal["software_generated"]
    artifact_role: Literal["development_test_excitation"]
    algorithm_id: Literal["exponential_sine_sweep"]
    algorithm_version: Literal["1.0.0"]
    source_audio_config_reference: str
    source_audio_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_audio_config_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    spec: EssSignalSpec
    sample_rate_hz: int = Field(gt=0)
    channel_count: Literal[1]
    dtype: Literal["float32"]
    shape: tuple[Literal[1], int]
    timing: EssSampleTiming
    metrics: EssSignalMetrics
    raw_float32_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    wav_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    wav_writer: Literal["acoustic_ladder_ieee_float_wav"]
    wav_writer_version: Literal["1.0.0"]
    memory_layout: Literal["channel_first_c_contiguous"]
    fade_window: Literal["half_cosine_inclusive_endpoints"]
    sample_rounding: Literal["floor_seconds_times_rate_plus_0.5"]
    playback_authorized: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    hardware_ready: Literal[False]
    safety_marker: Literal["OFFLINE_GENERATION_ONLY_NOT_AUTHORIZED_FOR_PLAYBACK"]

    @field_validator("source_audio_config_reference")
    @classmethod
    def source_reference_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @model_validator(mode="after")
    def derived_identity_matches_spec(self) -> EssArtifactMetadata:
        if self.algorithm_id != self.spec.algorithm_id:
            raise ValueError("metadata algorithm_id does not match spec")
        if self.algorithm_version != self.spec.algorithm_version:
            raise ValueError("metadata algorithm_version does not match spec")
        if self.sample_rate_hz != self.spec.sample_rate_hz:
            raise ValueError("metadata sample rate does not match spec")
        if self.shape != (1, self.timing.total_sample_count):
            raise ValueError("metadata shape does not match sample timing")
        return self
