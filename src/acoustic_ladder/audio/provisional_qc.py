"""Pure deterministic metrics for provisional synthetic offline QC."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.provisional_qc_models import (
    ProvisionalQcMetrics,
    WaveformQcMetrics,
)


class ProvisionalQcError(ValueError):
    """Raised when provisional QC inputs cannot satisfy the fixed metric contract."""


@dataclass(frozen=True)
class QcProcessingEvidence:
    sample_rate_hz: int
    sweep_sample_count: int
    pre_silence_sample_count: int
    transfer_fft_length: int
    estimated_latency_samples: int
    estimated_latency_seconds: float
    matched_correlation_signed: float
    matched_correlation_absolute: float
    ir_dominant_peak_index: int
    ir_dominant_peak_value: float
    reference_peak_index: int


def _waveform(value: NDArray[np.generic], label: str) -> NDArray[np.float64]:
    array = np.asarray(value)
    if array.ndim != 2 or array.shape[0] != 1 or array.shape[1] == 0:
        raise ProvisionalQcError(f"{label} must have mono channel-first shape [1,N]")
    if array.dtype.kind not in "iuf":
        raise ProvisionalQcError(f"{label} must have a real numeric dtype")
    converted = np.ascontiguousarray(array, dtype=np.float64)
    if not bool(np.isfinite(converted).all()):
        raise ProvisionalQcError(f"{label} contains non-finite values")
    return converted


def _rms(vector: NDArray[np.float64], label: str) -> float:
    with np.errstate(over="ignore", invalid="ignore"):
        value = float(np.sqrt(np.mean(np.square(vector, dtype=np.float64))))
    if not math.isfinite(value):
        raise ProvisionalQcError(f"{label} RMS is non-finite")
    return value


def _waveform_metrics(
    waveform: NDArray[np.float64], *, pre_count: int, sweep_count: int
) -> WaveformQcMetrics:
    vector = waveform[0]
    active = vector[pre_count : pre_count + sweep_count]
    pre = vector[:pre_count]
    pre_rms = None if pre_count == 0 else _rms(pre, "pre-silence")
    clipped = int(np.count_nonzero(np.abs(vector) >= 1.0))
    return WaveformQcMetrics(
        full_sample_count=int(vector.size),
        peak_abs=float(np.max(np.abs(vector))),
        rms=_rms(vector, "full waveform"),
        active_sweep_rms=_rms(active, "active sweep"),
        pre_silence_rms=pre_rms,
        pre_silence_rms_status=("pre_silence_absent" if pre_count == 0 else "computed"),
        clipped_sample_count=clipped,
        clipped_sample_fraction=clipped / int(vector.size),
    )


def _required_array(arrays: Mapping[str, NDArray[np.generic]], name: str) -> NDArray[np.generic]:
    try:
        array = np.asarray(arrays[name])
    except KeyError as exc:
        raise ProvisionalQcError(f"missing processing array: {name}") from exc
    return array


def _finite_transfer_in_band(
    arrays: Mapping[str, NDArray[np.generic]], prefix: str, mask: NDArray[np.bool_]
) -> int:
    real = _required_array(arrays, f"transfer_{prefix}_real")
    imag = _required_array(arrays, f"transfer_{prefix}_imag")
    expected = (1, 1, mask.size)
    if real.shape != expected or imag.shape != expected:
        raise ProvisionalQcError(f"transfer {prefix} arrays have invalid shape")
    finite = np.isfinite(real[0, 0]) & np.isfinite(imag[0, 0])
    if not bool(finite.all()):
        raise ProvisionalQcError(f"transfer {prefix} arrays contain non-finite values")
    return int(np.count_nonzero(finite[mask]))


def _validate_evidence(evidence: QcProcessingEvidence, sample_count: int) -> None:
    integers = (
        evidence.sample_rate_hz,
        evidence.sweep_sample_count,
        evidence.pre_silence_sample_count,
        evidence.transfer_fft_length,
        evidence.estimated_latency_samples,
        evidence.ir_dominant_peak_index,
        evidence.reference_peak_index,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
        raise ProvisionalQcError("processing evidence integer fields must be integers")
    if evidence.sample_rate_hz <= 0 or evidence.sweep_sample_count <= 0:
        raise ProvisionalQcError("processing evidence timing is invalid")
    if evidence.pre_silence_sample_count < 0 or evidence.estimated_latency_samples < 0:
        raise ProvisionalQcError("processing evidence counts must be non-negative")
    if evidence.pre_silence_sample_count + evidence.sweep_sample_count > sample_count:
        raise ProvisionalQcError("active sweep timing exceeds waveform")
    if evidence.transfer_fft_length <= 0:
        raise ProvisionalQcError("transfer FFT length must be positive")
    floats = (
        evidence.estimated_latency_seconds,
        evidence.matched_correlation_signed,
        evidence.matched_correlation_absolute,
        evidence.ir_dominant_peak_value,
    )
    if not all(math.isfinite(value) for value in floats):
        raise ProvisionalQcError("processing evidence contains non-finite values")
    if not -1 <= evidence.matched_correlation_signed <= 1:
        raise ProvisionalQcError("signed correlation is outside [-1,1]")
    if not 0 <= evidence.matched_correlation_absolute <= 1 or not math.isclose(
        evidence.matched_correlation_absolute,
        abs(evidence.matched_correlation_signed),
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ProvisionalQcError("absolute correlation differs from signed correlation")
    if not math.isclose(
        evidence.estimated_latency_seconds,
        evidence.estimated_latency_samples / evidence.sample_rate_hz,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ProvisionalQcError("latency seconds differ from samples and sample rate")


def compute_provisional_qc_metrics(
    output_reference: NDArray[np.generic],
    captured_input: NDArray[np.generic],
    processing_arrays: Mapping[str, NDArray[np.generic]],
    processing_evidence: QcProcessingEvidence,
) -> ProvisionalQcMetrics:
    """Compute threshold-free evidence from validated waveforms and processing facts."""

    output = _waveform(output_reference, "output reference")
    captured = _waveform(captured_input, "captured input")
    if output.shape != captured.shape:
        raise ProvisionalQcError("output reference and captured input shapes differ")
    _validate_evidence(processing_evidence, output.shape[1])
    pre_count = processing_evidence.pre_silence_sample_count
    sweep_count = processing_evidence.sweep_sample_count
    output_metrics = _waveform_metrics(output, pre_count=pre_count, sweep_count=sweep_count)
    input_metrics = _waveform_metrics(captured, pre_count=pre_count, sweep_count=sweep_count)

    snr_status: Literal[
        "computed",
        "pre_silence_absent",
        "zero_pre_silence_rms",
        "zero_active_sweep_rms",
    ]
    if pre_count == 0:
        snr = None
        snr_status = "pre_silence_absent"
    elif input_metrics.active_sweep_rms == 0:
        snr = None
        snr_status = "zero_active_sweep_rms"
    elif input_metrics.pre_silence_rms == 0:
        snr = None
        snr_status = "zero_pre_silence_rms"
    else:
        assert input_metrics.pre_silence_rms is not None
        snr = 20.0 * math.log10(input_metrics.active_sweep_rms / input_metrics.pre_silence_rms)
        snr_status = "computed"

    ir = _required_array(processing_arrays, "ir_raw")
    if ir.ndim != 3 or ir.shape[:2] != (1, 1) or ir.shape[2] == 0:
        raise ProvisionalQcError("ir_raw must have shape [1,1,N] with N > 0")
    ir_vector = np.ascontiguousarray(ir[0, 0], dtype=np.float64)
    if not bool(np.isfinite(ir_vector).all()):
        raise ProvisionalQcError("ir_raw contains non-finite values")
    magnitudes = np.abs(ir_vector)
    dominant_index = int(np.argmax(magnitudes))
    dominant_value = float(ir_vector[dominant_index])
    if (
        dominant_index != processing_evidence.ir_dominant_peak_index
        or dominant_value != processing_evidence.ir_dominant_peak_value
    ):
        raise ProvisionalQcError("IR dominant peak differs from processing evidence")
    dominant_abs = float(magnitudes[dominant_index])
    if dominant_abs <= 0:
        raise ProvisionalQcError("IR dominant peak must be non-zero")
    ir_status: Literal["computed", "single_sample_ir", "zero_second_largest_abs"]
    if ir_vector.size == 1:
        second_abs = None
        ir_ratio = None
        ir_status = "single_sample_ir"
    else:
        second_abs = float(np.max(np.delete(magnitudes, dominant_index)))
        if second_abs == 0:
            ir_ratio = None
            ir_status = "zero_second_largest_abs"
        else:
            ir_ratio = dominant_abs / second_abs
            ir_status = "computed"

    reference_raw = _required_array(processing_arrays, "reference_deconvolution")
    if reference_raw.ndim != 1 or reference_raw.size == 0:
        raise ProvisionalQcError("reference_deconvolution must be a non-empty vector")
    reference = np.ascontiguousarray(reference_raw, dtype=np.float64)
    if not bool(np.isfinite(reference).all()):
        raise ProvisionalQcError("reference_deconvolution contains non-finite values")
    reference_index = processing_evidence.reference_peak_index
    if reference_index >= reference.size:
        raise ProvisionalQcError("reference peak index is outside the deconvolution")
    reference_peak_abs = float(abs(reference[reference_index]))
    if reference_peak_abs <= 0 or np.count_nonzero(np.abs(reference) == reference_peak_abs) != 1:
        raise ProvisionalQcError("reference peak is not finite, non-zero and unique")
    if reference_peak_abs != float(np.max(np.abs(reference))):
        raise ProvisionalQcError("reference peak index does not identify the absolute peak")
    off_peak = np.delete(reference, reference_index)
    reference_status: Literal["computed", "no_off_peak_samples", "zero_off_peak_rms"]
    if off_peak.size == 0:
        off_peak_rms = None
        reference_ratio = None
        reference_status = "no_off_peak_samples"
    else:
        off_peak_rms = _rms(off_peak, "reference off-peak")
        if off_peak_rms == 0:
            reference_ratio = None
            reference_status = "zero_off_peak_rms"
        else:
            reference_ratio = reference_peak_abs / off_peak_rms
            reference_status = "computed"

    mask_raw = _required_array(processing_arrays, "analysis_band_mask")
    frequency_bin_count = processing_evidence.transfer_fft_length // 2 + 1
    if mask_raw.dtype != np.bool_ or mask_raw.shape != (frequency_bin_count,):
        raise ProvisionalQcError("analysis band mask differs from transfer FFT dimensions")
    mask = np.ascontiguousarray(mask_raw, dtype=np.bool_)
    band_count = int(np.count_nonzero(mask))
    if band_count == 0:
        raise ProvisionalQcError("analysis band contains no frequency bins")
    output_after_pre = output[0, pre_count:]
    spectrum = np.fft.rfft(output_after_pre, n=processing_evidence.transfer_fft_length)
    threshold = float(np.max(np.abs(spectrum))) * np.finfo(np.float64).eps * output_after_pre.size
    valid = np.abs(spectrum) > threshold
    valid_count = int(np.count_nonzero(valid[mask]))
    zeroed_count = band_count - valid_count
    raw_finite = _finite_transfer_in_band(processing_arrays, "raw", mask)
    aligned_finite = _finite_transfer_in_band(processing_arrays, "aligned", mask)

    return ProvisionalQcMetrics(
        schema_version="1.0.0",
        output_reference=output_metrics,
        captured_input=input_metrics,
        input_pre_silence_snr_proxy_db=snr,
        input_pre_silence_snr_proxy_status=snr_status,
        estimated_latency_samples=processing_evidence.estimated_latency_samples,
        estimated_latency_seconds=processing_evidence.estimated_latency_seconds,
        matched_correlation_signed=processing_evidence.matched_correlation_signed,
        matched_correlation_absolute=processing_evidence.matched_correlation_absolute,
        ir_dominant_peak_index=dominant_index,
        ir_dominant_peak_value=dominant_value,
        ir_dominant_peak_abs=dominant_abs,
        ir_second_largest_abs=second_abs,
        ir_peak_to_second_peak_ratio=ir_ratio,
        ir_peak_to_second_peak_ratio_status=ir_status,
        reference_deconvolution_peak_abs=reference_peak_abs,
        reference_deconvolution_off_peak_rms=off_peak_rms,
        reference_peak_to_off_peak_rms_ratio=reference_ratio,
        reference_peak_to_off_peak_rms_ratio_status=reference_status,
        analysis_band_bin_count=band_count,
        spectral_division_valid_bin_count_in_band=valid_count,
        spectral_division_zeroed_bin_count_in_band=zeroed_count,
        spectral_division_valid_fraction_in_band=valid_count / band_count,
        transfer_raw_finite_bin_count_in_band=raw_finite,
        transfer_raw_finite_fraction_in_band=raw_finite / band_count,
        transfer_aligned_finite_bin_count_in_band=aligned_finite,
        transfer_aligned_finite_fraction_in_band=aligned_finite / band_count,
        all_required_numeric_values_finite=True,
    )
