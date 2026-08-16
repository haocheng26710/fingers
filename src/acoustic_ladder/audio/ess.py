"""Pure deterministic exponential sine sweep generation; no device APIs."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.excitation_models import (
    EssSampleTiming,
    EssSignalMetrics,
    EssSignalSpec,
    round_half_up_samples,
)
from acoustic_ladder.config.models import AudioConfig, ConfigStatus
from acoustic_ladder.domain.models import RunMode


class EssError(ValueError):
    """Raised when an offline ESS contract cannot be fulfilled."""


class MissingEssFieldsError(EssError):
    """Raised when nullable audio configuration cannot form a complete ESS spec."""


@dataclass(frozen=True)
class GeneratedEss:
    samples: NDArray[np.float32]
    timing: EssSampleTiming
    metrics: EssSignalMetrics
    raw_float32_sha256: str


def spec_from_audio_config(config: AudioConfig) -> EssSignalSpec:
    """Extract an explicit development-only specification without supplying defaults."""

    required = {
        "ess_duration_s": config.ess_duration_s,
        "pre_silence_s": config.pre_silence_s,
        "post_silence_s": config.post_silence_s,
        "ess_fade_in_s": config.ess_fade_in_s,
        "ess_fade_out_s": config.ess_fade_out_s,
        "ess_digital_peak_dbfs": config.ess_digital_peak_dbfs,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise MissingEssFieldsError("missing ESS fields: " + ", ".join(missing))
    if config.run_mode is not RunMode.DEVELOPMENT:
        raise EssError("offline ESS generation requires run_mode=development")
    if config.config_status is not ConfigStatus.DRAFT:
        raise EssError("offline ESS generation requires config_status=draft")
    prohibited_flags = {
        "playback_authorized": config.playback_authorized,
        "formal_eligible": config.formal_eligible,
        "experimental_result": config.experimental_result,
        "hardware_ready": config.hardware_ready,
    }
    enabled = [name for name, value in prohibited_flags.items() if value]
    if enabled:
        raise EssError("offline development fixture requires false flags: " + ", ".join(enabled))
    assert config.ess_duration_s is not None
    assert config.pre_silence_s is not None
    assert config.post_silence_s is not None
    assert config.ess_fade_in_s is not None
    assert config.ess_fade_out_s is not None
    assert config.ess_digital_peak_dbfs is not None
    return EssSignalSpec(
        schema_version="1.0.0",
        algorithm_id="exponential_sine_sweep",
        algorithm_version="1.0.0",
        sample_rate_hz=config.sample_rate_hz,
        start_frequency_hz=config.ess_start_frequency_hz,
        end_frequency_hz=config.ess_end_frequency_hz,
        sweep_duration_s=config.ess_duration_s,
        pre_silence_s=config.pre_silence_s,
        post_silence_s=config.post_silence_s,
        fade_in_s=config.ess_fade_in_s,
        fade_out_s=config.ess_fade_out_s,
        digital_peak_dbfs=config.ess_digital_peak_dbfs,
        output_channel_count=1,
        output_dtype="float32",
        usage_scope="development_fixture",
        playback_authorized=False,
        formal_eligible=False,
        experimental_result=False,
        artifact_origin="software_generated",
        artifact_role="development_test_excitation",
    )


def theoretical_phase(spec: EssSignalSpec, time_s: NDArray[np.float64]) -> NDArray[np.float64]:
    """Evaluate the declared ESS phase using the actual rounded sweep duration."""

    sample_count = round_half_up_samples(spec.sweep_duration_s, spec.sample_rate_hz)
    duration = sample_count / spec.sample_rate_hz
    log_ratio = math.log(spec.end_frequency_hz / spec.start_frequency_hz)
    scale = 2 * math.pi * spec.start_frequency_hz * duration / log_ratio
    return scale * (np.exp(time_s * log_ratio / duration) - 1)


def theoretical_frequency(spec: EssSignalSpec, time_s: float) -> float:
    """Return continuous-time instantaneous frequency at a declared time."""

    sample_count = round_half_up_samples(spec.sweep_duration_s, spec.sample_rate_hz)
    duration = sample_count / spec.sample_rate_hz
    ratio = spec.end_frequency_hz / spec.start_frequency_hz
    return spec.start_frequency_hz * math.exp(time_s * math.log(ratio) / duration)


def _timing(spec: EssSignalSpec) -> EssSampleTiming:
    rate = spec.sample_rate_hz
    sweep = round_half_up_samples(spec.sweep_duration_s, rate)
    pre = round_half_up_samples(spec.pre_silence_s, rate)
    post = round_half_up_samples(spec.post_silence_s, rate)
    fade_in = round_half_up_samples(spec.fade_in_s, rate)
    fade_out = round_half_up_samples(spec.fade_out_s, rate)

    def actual(count: int) -> float:
        return count / rate

    return EssSampleTiming(
        requested_sweep_duration_s=spec.sweep_duration_s,
        actual_sweep_duration_s=actual(sweep),
        sweep_duration_error_s=actual(sweep) - spec.sweep_duration_s,
        requested_pre_silence_s=spec.pre_silence_s,
        actual_pre_silence_s=actual(pre),
        pre_silence_error_s=actual(pre) - spec.pre_silence_s,
        requested_post_silence_s=spec.post_silence_s,
        actual_post_silence_s=actual(post),
        post_silence_error_s=actual(post) - spec.post_silence_s,
        requested_fade_in_s=spec.fade_in_s,
        actual_fade_in_s=actual(fade_in),
        fade_in_error_s=actual(fade_in) - spec.fade_in_s,
        requested_fade_out_s=spec.fade_out_s,
        actual_fade_out_s=actual(fade_out),
        fade_out_error_s=actual(fade_out) - spec.fade_out_s,
        sweep_sample_count=sweep,
        pre_silence_sample_count=pre,
        post_silence_sample_count=post,
        fade_in_sample_count=fade_in,
        fade_out_sample_count=fade_out,
        total_sample_count=pre + sweep + post,
    )


def raw_float32_bytes(samples: NDArray[np.float32]) -> bytes:
    """Return canonical channel-first little-endian IEEE float sample bytes."""

    return samples.astype("<f4", copy=False).tobytes(order="C")


def generate_ess(spec: EssSignalSpec) -> GeneratedEss:
    """Generate a deterministic channel-first float32 offline ESS fixture."""

    timing = _timing(spec)
    rate = spec.sample_rate_hz
    times = np.arange(timing.sweep_sample_count, dtype=np.float64) / rate
    sweep = np.sin(theoretical_phase(spec, times))
    if timing.fade_in_sample_count:
        positions = np.arange(timing.fade_in_sample_count, dtype=np.float64)
        sweep[: timing.fade_in_sample_count] *= 0.5 * (
            1 - np.cos(math.pi * positions / (timing.fade_in_sample_count - 1))
        )
    if timing.fade_out_sample_count:
        positions = np.arange(timing.fade_out_sample_count, dtype=np.float64)
        sweep[-timing.fade_out_sample_count :] *= 0.5 * (
            1 + np.cos(math.pi * positions / (timing.fade_out_sample_count - 1))
        )
    pre_normalization_peak = float(np.max(np.abs(sweep)))
    if not math.isfinite(pre_normalization_peak) or pre_normalization_peak <= 0:
        raise EssError("generated sweep has no finite non-zero peak")
    target_peak = 10.0 ** (spec.digital_peak_dbfs / 20.0)
    normalization_factor = target_peak / pre_normalization_peak
    sweep32 = np.asarray(sweep * normalization_factor, dtype=np.float32)
    samples = np.zeros((1, timing.total_sample_count), dtype=np.float32)
    start = timing.pre_silence_sample_count
    samples[0, start : start + timing.sweep_sample_count] = sweep32
    if not samples.flags.c_contiguous or not bool(np.isfinite(samples).all()):
        raise EssError("generated samples must be finite and C-contiguous")
    actual_peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    metrics = EssSignalMetrics(
        target_peak_dbfs=spec.digital_peak_dbfs,
        target_linear_peak=target_peak,
        pre_normalization_peak=pre_normalization_peak,
        normalization_factor=normalization_factor,
        actual_peak=actual_peak,
        rms=rms,
        crest_factor=actual_peak / rms,
        mean_dc=float(np.mean(samples, dtype=np.float64)),
        minimum=float(np.min(samples)),
        maximum=float(np.max(samples)),
        all_finite=True,
    )
    raw = raw_float32_bytes(samples)
    return GeneratedEss(samples, timing, metrics, hashlib.sha256(raw).hexdigest())
