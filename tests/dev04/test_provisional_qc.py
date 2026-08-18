from __future__ import annotations

import inspect
import math

import numpy as np
import pytest
from pydantic import ValidationError

from acoustic_ladder.audio.provisional_qc import (
    ProvisionalQcError,
    QcProcessingEvidence,
    compute_provisional_qc_metrics,
)
from acoustic_ladder.audio.provisional_qc_models import ProvisionalQcMetrics


def _rms_for_test(value: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(value, dtype=np.float64))))


def _evidence(
    *,
    sweep_sample_count: int = 4,
    pre_silence_sample_count: int = 2,
    ir_dominant_peak_index: int = 0,
    reference_peak_index: int = 0,
) -> QcProcessingEvidence:
    return QcProcessingEvidence(
        sample_rate_hz=8_000,
        sweep_sample_count=sweep_sample_count,
        pre_silence_sample_count=pre_silence_sample_count,
        transfer_fft_length=8,
        estimated_latency_samples=2,
        estimated_latency_seconds=0.00025,
        matched_correlation_signed=-0.75,
        matched_correlation_absolute=0.75,
        ir_dominant_peak_index=ir_dominant_peak_index,
        ir_dominant_peak_value=2.0,
        reference_peak_index=reference_peak_index,
    )


def _arrays() -> dict[str, np.ndarray]:
    return {
        "ir_raw": np.array([[[2.0, 0.5, -0.25]]], dtype=np.float64),
        "reference_deconvolution": np.array([1.0, 0.1, -0.1], dtype=np.float64),
        "analysis_band_mask": np.ones(5, dtype=np.bool_),
        "transfer_raw_real": np.zeros((1, 1, 5), dtype=np.float64),
        "transfer_raw_imag": np.zeros((1, 1, 5), dtype=np.float64),
        "transfer_aligned_real": np.zeros((1, 1, 5), dtype=np.float64),
        "transfer_aligned_imag": np.zeros((1, 1, 5), dtype=np.float64),
    }


def test_compute_provisional_qc_metrics_uses_fixed_float64_formulas() -> None:
    output = np.array([[0.0, 0.0, 1.0, 0.5, -0.5, 0.25]], dtype=np.float32)
    captured = np.array([[0.1, -0.1, 0.5, 0.5, 0.5, 0.5]], dtype=np.float32)

    metrics = compute_provisional_qc_metrics(output, captured, _arrays(), _evidence())

    assert metrics.output_reference.full_sample_count == 6
    assert metrics.output_reference.peak_abs == 1.0
    assert metrics.output_reference.rms == math.sqrt(1.5625 / 6)
    assert metrics.output_reference.active_sweep_rms == math.sqrt(1.5625 / 4)
    assert metrics.output_reference.pre_silence_rms == 0.0
    assert metrics.output_reference.pre_silence_rms_status == "computed"
    assert metrics.output_reference.clipped_sample_count == 1
    assert metrics.output_reference.clipped_sample_fraction == 1 / 6
    assert metrics.captured_input.active_sweep_rms == 0.5
    assert metrics.input_pre_silence_snr_proxy_status == "computed"
    assert metrics.input_pre_silence_snr_proxy_db == pytest.approx(20 * math.log10(5))
    assert metrics.estimated_latency_samples == 2
    assert metrics.matched_correlation_signed == -0.75
    assert metrics.matched_correlation_absolute == 0.75
    assert metrics.ir_dominant_peak_abs == 2.0
    assert metrics.ir_second_largest_abs == 0.5
    assert metrics.ir_peak_to_second_peak_ratio == 4.0
    assert metrics.ir_peak_to_second_peak_ratio_status == "computed"
    assert metrics.reference_deconvolution_peak_abs == 1.0
    assert metrics.reference_deconvolution_off_peak_rms == pytest.approx(0.1)
    assert metrics.reference_peak_to_off_peak_rms_ratio == pytest.approx(10.0)
    assert metrics.reference_peak_to_off_peak_rms_ratio_status == "computed"
    assert metrics.analysis_band_bin_count == 5
    assert (
        metrics.spectral_division_valid_bin_count_in_band
        + metrics.spectral_division_zeroed_bin_count_in_band
        == 5
    )
    assert metrics.transfer_raw_finite_bin_count_in_band == 5
    assert metrics.transfer_aligned_finite_fraction_in_band == 1.0
    assert metrics.all_required_numeric_values_finite is True


def test_metric_api_has_no_scenario_truth_or_threshold_parameters() -> None:
    parameters = set(inspect.signature(compute_provisional_qc_metrics).parameters)
    assert parameters == {
        "output_reference",
        "captured_input",
        "processing_arrays",
        "processing_evidence",
    }
    assert not {"scenario", "expected_latency", "expected_gain", "threshold"}.intersection(
        parameters
    )


def test_clipping_boundary_counts_positive_and_negative_one() -> None:
    waveform = np.array([[0.0, 0.999, 1.0, -1.0, -1.2]], dtype=np.float64)
    metrics = compute_provisional_qc_metrics(
        waveform,
        waveform,
        _arrays(),
        _evidence(sweep_sample_count=5, pre_silence_sample_count=0),
    )
    assert metrics.output_reference.clipped_sample_count == 3
    assert metrics.output_reference.clipped_sample_fraction == 3 / 5


@pytest.mark.parametrize(
    ("pre", "active", "status"),
    [
        (np.empty(0), np.array([1.0, 1.0]), "pre_silence_absent"),
        (np.zeros(2), np.array([1.0, 1.0]), "zero_pre_silence_rms"),
        (np.ones(2), np.zeros(2), "zero_active_sweep_rms"),
    ],
)
def test_snr_null_states_do_not_invent_infinity(
    pre: np.ndarray, active: np.ndarray, status: str
) -> None:
    waveform = np.concatenate((pre, active)).reshape(1, -1)
    evidence = _evidence(
        pre_silence_sample_count=pre.size,
        sweep_sample_count=active.size,
    )
    metrics = compute_provisional_qc_metrics(waveform, waveform, _arrays(), evidence)

    assert metrics.input_pre_silence_snr_proxy_db is None
    assert metrics.input_pre_silence_snr_proxy_status == status
    if pre.size == 0:
        assert metrics.captured_input.pre_silence_rms is None
    else:
        assert metrics.captured_input.pre_silence_rms == _rms_for_test(pre)


def test_ratio_null_states_are_explicit() -> None:
    arrays = _arrays()
    arrays["ir_raw"] = np.array([[[2.0]]], dtype=np.float64)
    arrays["reference_deconvolution"] = np.array([1.0], dtype=np.float64)
    metrics = compute_provisional_qc_metrics(
        np.ones((1, 4)),
        np.ones((1, 4)),
        arrays,
        _evidence(pre_silence_sample_count=0, reference_peak_index=0),
    )

    assert metrics.ir_second_largest_abs is None
    assert metrics.ir_peak_to_second_peak_ratio is None
    assert metrics.ir_peak_to_second_peak_ratio_status == "single_sample_ir"
    assert metrics.reference_deconvolution_off_peak_rms is None
    assert metrics.reference_peak_to_off_peak_rms_ratio is None
    assert metrics.reference_peak_to_off_peak_rms_ratio_status == "no_off_peak_samples"


def test_zero_ratio_denominators_are_explicit() -> None:
    arrays = _arrays()
    arrays["ir_raw"] = np.array([[[2.0, 0.0]]], dtype=np.float64)
    arrays["reference_deconvolution"] = np.array([1.0, 0.0], dtype=np.float64)
    metrics = compute_provisional_qc_metrics(
        np.ones((1, 4)),
        np.ones((1, 4)),
        arrays,
        _evidence(pre_silence_sample_count=0),
    )

    assert metrics.ir_second_largest_abs == 0.0
    assert metrics.ir_peak_to_second_peak_ratio is None
    assert metrics.ir_peak_to_second_peak_ratio_status == "zero_second_largest_abs"
    assert metrics.reference_deconvolution_off_peak_rms == 0.0
    assert metrics.reference_peak_to_off_peak_rms_ratio is None
    assert metrics.reference_peak_to_off_peak_rms_ratio_status == "zero_off_peak_rms"


@pytest.mark.parametrize(
    "bad",
    [
        np.array([1.0]),
        np.empty((1, 0)),
        np.ones((2, 4)),
        np.array([[1.0, np.nan, 1.0, 1.0]]),
        np.array([[1.0, np.inf, 1.0, 1.0]]),
        np.array([["1", "2", "3", "4"]]),
        np.array([[True, False, True, False]]),
    ],
)
def test_waveform_contract_rejects_non_mono_empty_or_nonfinite(bad: np.ndarray) -> None:
    with pytest.raises(ProvisionalQcError):
        compute_provisional_qc_metrics(bad, np.ones((1, 4)), _arrays(), _evidence())


def test_processing_evidence_mismatch_is_rejected() -> None:
    with pytest.raises(ProvisionalQcError, match="dominant peak"):
        compute_provisional_qc_metrics(
            np.ones((1, 4)),
            np.ones((1, 4)),
            _arrays(),
            _evidence(pre_silence_sample_count=0, ir_dominant_peak_index=1),
        )


def test_empty_analysis_band_is_rejected() -> None:
    arrays = _arrays()
    arrays["analysis_band_mask"] = np.zeros(5, dtype=np.bool_)
    with pytest.raises(ProvisionalQcError, match="analysis band"):
        compute_provisional_qc_metrics(
            np.ones((1, 4)),
            np.ones((1, 4)),
            arrays,
            _evidence(pre_silence_sample_count=0),
        )


def test_nonfinite_processing_array_is_rejected() -> None:
    arrays = _arrays()
    arrays["transfer_raw_real"][0, 0, 2] = np.nan
    with pytest.raises(ProvisionalQcError, match="non-finite"):
        compute_provisional_qc_metrics(
            np.ones((1, 4)),
            np.ones((1, 4)),
            arrays,
            _evidence(pre_silence_sample_count=0),
        )


def test_spectral_zeroed_bins_and_fractions_follow_fixed_threshold() -> None:
    metrics = compute_provisional_qc_metrics(
        np.ones((1, 4)),
        np.ones((1, 4)),
        _arrays(),
        _evidence(pre_silence_sample_count=0),
    )
    assert metrics.spectral_division_valid_bin_count_in_band == 3
    assert metrics.spectral_division_zeroed_bin_count_in_band == 2
    assert metrics.spectral_division_valid_fraction_in_band == 0.6
    assert metrics.transfer_raw_finite_bin_count_in_band == 5
    assert metrics.transfer_aligned_finite_bin_count_in_band == 5


def test_nullable_metric_status_pairs_are_strict() -> None:
    metrics = compute_provisional_qc_metrics(
        np.ones((1, 4)),
        np.ones((1, 4)),
        _arrays(),
        _evidence(pre_silence_sample_count=0),
    )
    payload = metrics.model_dump()
    payload["input_pre_silence_snr_proxy_db"] = 1.0
    with pytest.raises(ValidationError):
        ProvisionalQcMetrics.model_validate(payload)
