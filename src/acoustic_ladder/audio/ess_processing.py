"""Pure deterministic offline ESS deconvolution and transfer-function processing."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Float64Array = NDArray[np.float64]
ProcessingArray = Float64Array | NDArray[np.int64] | NDArray[np.bool_]


class EssProcessingError(ValueError):
    """Raised when offline ESS mathematics cannot satisfy its strict contract."""


@dataclass(frozen=True)
class EssProcessingResult:
    arrays: dict[str, ProcessingArray]
    inverse_fft_length: int
    deconvolution_fft_length: int
    transfer_fft_length: int
    reference_peak_index: int
    inverse_pre_normalization_peak: float
    inverse_normalization_factor: float
    inverse_post_normalization_peak: float
    estimated_latency_samples: int
    latency_correlation_coefficient: float
    ir_raw_dominant_peak_index: int
    ir_raw_dominant_peak_value: float


def _next_power_of_two(value: int) -> int:
    if value <= 0:
        raise EssProcessingError("FFT length source must be positive")
    return 1 << (value - 1).bit_length()


def _finite_vector(value: NDArray[np.generic], label: str) -> Float64Array:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 1 or array.size == 0:
        raise EssProcessingError(f"{label} must be a non-empty one-dimensional array")
    if not bool(np.isfinite(array).all()):
        raise EssProcessingError(f"{label} contains non-finite values")
    return np.ascontiguousarray(array)


def fft_linear_convolve(
    left: NDArray[np.generic], right: NDArray[np.generic]
) -> tuple[Float64Array, int]:
    """Return exact-length full linear convolution using a power-of-two FFT."""

    first = _finite_vector(left, "left convolution input")
    second = _finite_vector(right, "right convolution input")
    full_length = first.size + second.size - 1
    fft_length = _next_power_of_two(full_length)
    result = np.fft.irfft(
        np.fft.rfft(first, n=fft_length) * np.fft.rfft(second, n=fft_length),
        n=fft_length,
    )[:full_length]
    if not bool(np.isfinite(result).all()):
        raise EssProcessingError("linear convolution produced non-finite values")
    return np.ascontiguousarray(result, dtype=np.float64), fft_length


def _unique_absolute_peak(array: Float64Array, label: str) -> tuple[int, float]:
    magnitudes = np.abs(array)
    peak = float(np.max(magnitudes))
    if not math.isfinite(peak) or peak <= 0:
        raise EssProcessingError(f"{label} must have a finite non-zero peak")
    indices = np.flatnonzero(magnitudes == peak)
    if indices.size != 1:
        raise EssProcessingError(f"{label} absolute peak must be unique")
    index = int(indices[0])
    return index, float(array[index])


def build_inverse_filter(
    active_sweep: NDArray[np.generic],
    *,
    start_frequency_hz: float,
    end_frequency_hz: float,
) -> tuple[Float64Array, Float64Array, int, float, float, float, int]:
    """Build and reference-normalize the Farina-style time-reversed ESS inverse."""

    sweep = _finite_vector(active_sweep, "active sweep")
    if (
        not math.isfinite(start_frequency_hz)
        or not math.isfinite(end_frequency_hz)
        or start_frequency_hz <= 0
        or end_frequency_hz <= start_frequency_hz
    ):
        raise EssProcessingError("ESS frequency bounds must be finite, positive and ordered")
    sample_count = sweep.size
    log_ratio = math.log(end_frequency_hz / start_frequency_hz)
    positions = np.arange(sample_count, dtype=np.float64)
    inverse = np.ascontiguousarray(
        sweep[::-1] * np.exp(-log_ratio * positions / sample_count), dtype=np.float64
    )
    reference_before, fft_length = fft_linear_convolve(sweep, inverse)
    peak_index, signed_peak = _unique_absolute_peak(reference_before, "reference deconvolution")
    pre_peak = abs(signed_peak)
    factor = 1.0 / signed_peak
    if not math.isfinite(factor) or factor == 0:
        raise EssProcessingError("inverse normalization factor is invalid")
    normalized_inverse = np.ascontiguousarray(inverse * factor)
    reference, _ = fft_linear_convolve(sweep, normalized_inverse)
    normalized_index, normalized_value = _unique_absolute_peak(
        reference, "normalized reference deconvolution"
    )
    if normalized_index != peak_index or not math.isclose(
        normalized_value, 1.0, rel_tol=0.0, abs_tol=1e-12
    ):
        raise EssProcessingError("inverse normalization did not produce a positive unit peak")
    return (
        normalized_inverse,
        reference,
        peak_index,
        factor,
        pre_peak,
        normalized_value,
        fft_length,
    )


def estimate_latency_samples(
    active_sweep: NDArray[np.generic], input_after_pre_silence: NDArray[np.generic]
) -> tuple[int, float]:
    """Estimate non-negative lag by normalized full-sweep matched correlation."""

    sweep = _finite_vector(active_sweep, "active sweep")
    captured = _finite_vector(input_after_pre_silence, "captured input")
    if captured.size < sweep.size:
        raise EssProcessingError("captured input is shorter than the full active sweep")
    numerator_full, _ = fft_linear_convolve(captured, sweep[::-1])
    numerators = numerator_full[sweep.size - 1 : captured.size]
    sweep_energy = float(np.dot(sweep, sweep))
    squared = np.square(captured, dtype=np.float64)
    cumulative = np.concatenate((np.zeros(1, dtype=np.float64), np.cumsum(squared)))
    window_energy = cumulative[sweep.size :] - cumulative[: -sweep.size]
    denominators = np.sqrt(sweep_energy * window_energy)
    coefficients = np.divide(
        numerators,
        denominators,
        out=np.zeros_like(numerators),
        where=denominators > 0,
    )
    if not bool(np.isfinite(coefficients).all()):
        raise EssProcessingError("matched correlation produced non-finite coefficients")
    index, signed_coefficient = _unique_absolute_peak(
        np.ascontiguousarray(coefficients), "matched correlation"
    )
    return index, signed_coefficient


def zero_fill_align(raw: NDArray[np.generic], latency_samples: int) -> Float64Array:
    """Advance by a measured lag with zeros, never circularly wrapping samples."""

    source = _finite_vector(raw, "raw impulse response")
    if isinstance(latency_samples, bool) or not isinstance(latency_samples, int):
        raise EssProcessingError("latency_samples must be an integer")
    aligned = np.zeros_like(source)
    if latency_samples >= 0:
        if latency_samples < source.size:
            aligned[: source.size - latency_samples] = source[latency_samples:]
    else:
        delay = -latency_samples
        if delay < source.size:
            aligned[delay:] = source[: source.size - delay]
    return np.ascontiguousarray(aligned)


def _spectral_ratio(
    response: Float64Array, reference: Float64Array, *, fft_length: int
) -> NDArray[np.complex128]:
    reference_spectrum = np.fft.rfft(reference, n=fft_length)
    response_spectrum = np.fft.rfft(response, n=fft_length)
    threshold = (
        float(np.max(np.abs(reference_spectrum))) * np.finfo(np.float64).eps * reference.size
    )
    transfer = np.zeros_like(response_spectrum)
    np.divide(
        response_spectrum,
        reference_spectrum,
        out=transfer,
        where=np.abs(reference_spectrum) > threshold,
    )
    if not bool(np.isfinite(transfer).all()):
        raise EssProcessingError("spectral division produced non-finite values")
    return np.ascontiguousarray(transfer, dtype=np.complex128)


def _channel_first(value: NDArray[np.generic], label: str) -> Float64Array:
    array = np.asarray(value)
    if array.ndim != 2 or array.shape[0] != 1 or array.shape[1] == 0:
        raise EssProcessingError(f"{label} must have channel-first shape [1,n]")
    converted = np.ascontiguousarray(array, dtype=np.float64)
    if not bool(np.isfinite(converted).all()):
        raise EssProcessingError(f"{label} contains non-finite values")
    return converted


def process_ess_waveforms(
    output_reference: NDArray[np.generic],
    captured_input: NDArray[np.generic],
    *,
    sample_rate_hz: int,
    sweep_sample_count: int,
    pre_silence_sample_count: int,
    start_frequency_hz: float,
    end_frequency_hz: float,
    analysis_lower_hz: float,
    analysis_upper_hz: float,
    smoothing_enabled: bool,
) -> EssProcessingResult:
    """Process one mono ESS reference/input pair using only waveform and metadata facts."""

    output = _channel_first(output_reference, "output reference")
    captured = _channel_first(captured_input, "captured input")
    if output.shape != captured.shape:
        raise EssProcessingError("output reference and captured input shapes must match")
    if (
        isinstance(sample_rate_hz, bool)
        or not isinstance(sample_rate_hz, int)
        or sample_rate_hz <= 0
    ):
        raise EssProcessingError("sample_rate_hz must be a positive integer")
    if sweep_sample_count <= 1 or pre_silence_sample_count < 0:
        raise EssProcessingError("ESS sample timing is invalid")
    if pre_silence_sample_count + sweep_sample_count > output.shape[1]:
        raise EssProcessingError("ESS timing exceeds the available waveforms")
    if smoothing_enabled:
        raise EssProcessingError("smoothing must remain disabled for DEV-04.01")
    nyquist = sample_rate_hz / 2
    if not (0 < analysis_lower_hz < analysis_upper_hz < nyquist):
        raise EssProcessingError("analysis band must be ordered and below Nyquist")

    output_after_pre = output[0, pre_silence_sample_count:]
    input_after_pre = captured[0, pre_silence_sample_count:]
    active_sweep = output_after_pre[:sweep_sample_count]
    (
        inverse,
        active_reference_deconvolution,
        active_reference_peak,
        normalization_factor,
        pre_peak,
        post_peak,
        inverse_fft_length,
    ) = build_inverse_filter(
        active_sweep,
        start_frequency_hz=start_frequency_hz,
        end_frequency_hz=end_frequency_hz,
    )
    reference_deconvolution, reference_fft_length = fft_linear_convolve(output_after_pre, inverse)
    input_deconvolution, input_fft_length = fft_linear_convolve(input_after_pre, inverse)
    if reference_fft_length != input_fft_length:
        raise EssProcessingError("reference and input deconvolution FFT lengths disagree")
    reference_peak_index, reference_peak_value = _unique_absolute_peak(
        reference_deconvolution, "full reference deconvolution"
    )
    if reference_peak_index != active_reference_peak or not math.isclose(
        reference_peak_value, post_peak, rel_tol=0.0, abs_tol=1e-12
    ):
        raise EssProcessingError("full reference peak disagrees with inverse normalization")
    latency, correlation = estimate_latency_samples(active_sweep, input_after_pre)
    relative_samples = (
        np.arange(reference_deconvolution.size, dtype=np.int64) - reference_peak_index
    )
    relative_seconds = relative_samples.astype(np.float64) / sample_rate_hz
    ir_raw_vector = np.ascontiguousarray(input_deconvolution[reference_peak_index:])
    peak_index, peak_value = _unique_absolute_peak(ir_raw_vector, "raw impulse response")
    ir_aligned_vector = zero_fill_align(ir_raw_vector, latency)
    transfer_fft_length = _next_power_of_two(ir_raw_vector.size)
    transfer_raw = _spectral_ratio(
        input_after_pre, output_after_pre, fft_length=transfer_fft_length
    )
    aligned_input_after_pre = zero_fill_align(input_after_pre, latency)
    transfer_aligned = _spectral_ratio(
        aligned_input_after_pre, output_after_pre, fft_length=transfer_fft_length
    )
    frequency = np.fft.rfftfreq(transfer_fft_length, d=1.0 / sample_rate_hz)
    magnitude_raw = np.abs(transfer_raw)
    magnitude_aligned = np.abs(transfer_aligned)
    floor = np.finfo(np.float64).tiny

    def channel_cube(vector: Float64Array) -> Float64Array:
        return np.ascontiguousarray(vector.reshape(1, 1, -1), dtype=np.float64)

    arrays: dict[str, ProcessingArray] = {
        "inverse_filter": inverse,
        "reference_deconvolution": reference_deconvolution,
        "input_deconvolution": input_deconvolution,
        "deconvolution_relative_samples": np.ascontiguousarray(relative_samples),
        "deconvolution_relative_seconds": np.ascontiguousarray(relative_seconds),
        "ir_raw": channel_cube(ir_raw_vector),
        "ir_aligned": channel_cube(ir_aligned_vector),
        "frequency_hz": np.ascontiguousarray(frequency, dtype=np.float64),
        "transfer_raw_real": channel_cube(transfer_raw.real),
        "transfer_raw_imag": channel_cube(transfer_raw.imag),
        "transfer_aligned_real": channel_cube(transfer_aligned.real),
        "transfer_aligned_imag": channel_cube(transfer_aligned.imag),
        "magnitude_raw_linear": channel_cube(magnitude_raw),
        "magnitude_raw_db": channel_cube(20.0 * np.log10(np.maximum(magnitude_raw, floor))),
        "phase_raw_rad": channel_cube(np.angle(transfer_raw)),
        "phase_raw_unwrapped_rad": channel_cube(np.unwrap(np.angle(transfer_raw))),
        "magnitude_aligned_linear": channel_cube(magnitude_aligned),
        "magnitude_aligned_db": channel_cube(20.0 * np.log10(np.maximum(magnitude_aligned, floor))),
        "phase_aligned_rad": channel_cube(np.angle(transfer_aligned)),
        "phase_aligned_unwrapped_rad": channel_cube(np.unwrap(np.angle(transfer_aligned))),
        "analysis_band_mask": np.ascontiguousarray(
            (frequency >= analysis_lower_hz) & (frequency <= analysis_upper_hz)
        ),
    }
    if any(not array.flags.c_contiguous for array in arrays.values()):
        raise EssProcessingError("processing arrays must be C-contiguous")
    if any(
        not bool(np.isfinite(array).all()) for array in arrays.values() if array.dtype != np.bool_
    ):
        raise EssProcessingError("processing arrays contain non-finite values")
    del active_reference_deconvolution
    return EssProcessingResult(
        arrays=arrays,
        inverse_fft_length=inverse_fft_length,
        deconvolution_fft_length=reference_fft_length,
        transfer_fft_length=transfer_fft_length,
        reference_peak_index=reference_peak_index,
        inverse_pre_normalization_peak=pre_peak,
        inverse_normalization_factor=normalization_factor,
        inverse_post_normalization_peak=post_peak,
        estimated_latency_samples=latency,
        latency_correlation_coefficient=correlation,
        ir_raw_dominant_peak_index=peak_index,
        ir_raw_dominant_peak_value=peak_value,
    )
