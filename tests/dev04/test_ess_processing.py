from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from acoustic_ladder.audio.ess import generate_ess, spec_from_audio_config
from acoustic_ladder.audio.ess_processing import (
    EssProcessingError,
    EssProcessingResult,
    build_inverse_filter,
    estimate_latency_samples,
    fft_linear_convolve,
    process_ess_waveforms,
    zero_fill_align,
)
from acoustic_ladder.config.bundle import load_config
from acoustic_ladder.config.models import AudioConfig

PROJECT_ROOT = Path(__file__).parents[2]
AUDIO_FIXTURE = PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml"


def _fixture_waveforms() -> tuple[np.ndarray, np.ndarray, AudioConfig]:
    loaded = load_config("audio", AUDIO_FIXTURE, project_root=PROJECT_ROOT)
    assert isinstance(loaded.model, AudioConfig)
    generated = generate_ess(spec_from_audio_config(loaded.model))
    output = np.pad(generated.samples, ((0, 0), (0, 64)))
    captured = np.zeros_like(output)
    captured[:, 37:] = output[:, :-37] * np.float32(0.5)
    return output, captured, loaded.model


def test_fft_linear_convolution_matches_direct_full_convolution() -> None:
    left = np.array([1.0, -2.0, 0.5], dtype=np.float64)
    right = np.array([0.25, 3.0], dtype=np.float64)
    actual, fft_length = fft_linear_convolve(left, right)
    np.testing.assert_allclose(actual, np.convolve(left, right, mode="full"), atol=1e-14)
    assert actual.shape == (4,)
    assert fft_length == 4


def test_fft_linear_convolution_uses_next_power_of_two() -> None:
    actual, fft_length = fft_linear_convolve(np.ones(5), np.ones(4))
    assert actual.shape == (8,)
    assert fft_length == 8


def test_inverse_filter_normalizes_unique_reference_peak_to_positive_one() -> None:
    active = np.array([0.0, 1.0, 0.5, -0.25], dtype=np.float64)
    inverse, reference, peak_index, factor, pre_peak, post_peak, _ = build_inverse_filter(
        active,
        start_frequency_hz=1.0,
        end_frequency_hz=4.0,
    )
    assert pre_peak > 0
    assert factor > 0
    assert post_peak == pytest.approx(1.0, abs=1e-14)
    assert reference[peak_index] == pytest.approx(1.0, abs=1e-14)
    assert inverse.dtype == np.float64


@pytest.mark.parametrize(
    "reference",
    [
        np.zeros(4, dtype=np.float64),
        np.array([np.nan, 0.0], dtype=np.float64),
    ],
)
def test_inverse_filter_rejects_zero_or_nonfinite_reference(reference: np.ndarray) -> None:
    with pytest.raises(EssProcessingError):
        build_inverse_filter(reference, start_frequency_hz=1.0, end_frequency_hz=4.0)


def test_latency_estimation_uses_only_full_sweep_overlap() -> None:
    sweep = np.array([1.0, -1.0, 0.5, 0.25], dtype=np.float64)
    captured = np.pad(sweep * 0.5, (3, 2))
    lag, coefficient = estimate_latency_samples(sweep, captured)
    assert lag == 3
    assert coefficient == pytest.approx(1.0)


def test_latency_estimation_rejects_tied_absolute_maximum() -> None:
    sweep = np.array([1.0, 0.0], dtype=np.float64)
    with pytest.raises(EssProcessingError, match="unique"):
        estimate_latency_samples(sweep, np.array([1.0, 0.0, -1.0, 0.0]))


def test_zero_fill_alignment_never_wraps_samples() -> None:
    raw = np.array([0.0, 0.0, 2.0, 3.0], dtype=np.float64)
    aligned = zero_fill_align(raw, 2)
    assert np.array_equal(aligned, np.array([2.0, 3.0, 0.0, 0.0]))
    assert np.array_equal(raw, np.array([0.0, 0.0, 2.0, 3.0]))


def test_nominal_processing_recovers_latency_and_gain_from_waveforms() -> None:
    output, captured, audio = _fixture_waveforms()
    result = process_ess_waveforms(
        output,
        captured,
        sample_rate_hz=audio.sample_rate_hz,
        sweep_sample_count=12000,
        pre_silence_sample_count=480,
        start_frequency_hz=audio.ess_start_frequency_hz,
        end_frequency_hz=audio.ess_end_frequency_hz,
        analysis_lower_hz=500.0,
        analysis_upper_hz=8000.0,
        smoothing_enabled=False,
    )
    assert result.estimated_latency_samples == 37
    assert result.ir_raw_dominant_peak_index == 37
    assert result.arrays["ir_raw"][0, 0, 37] == pytest.approx(0.5, abs=1e-6)
    assert result.arrays["ir_aligned"][0, 0, 0] == pytest.approx(0.5, abs=1e-6)
    assert result.arrays["analysis_band_mask"].dtype == np.bool_


def test_public_pipeline_identity_oracle_recovers_unity_zero_lag() -> None:
    output, _, audio = _fixture_waveforms()
    result = process_ess_waveforms(
        output,
        output.copy(),
        sample_rate_hz=audio.sample_rate_hz,
        sweep_sample_count=12000,
        pre_silence_sample_count=480,
        start_frequency_hz=audio.ess_start_frequency_hz,
        end_frequency_hz=audio.ess_end_frequency_hz,
        analysis_lower_hz=500.0,
        analysis_upper_hz=8000.0,
        smoothing_enabled=False,
    )
    mask = result.arrays["analysis_band_mask"]
    assert result.estimated_latency_samples == 0
    assert result.latency_correlation_coefficient == pytest.approx(1.0, abs=1e-12)
    assert result.ir_raw_dominant_peak_index == 0
    assert result.arrays["ir_raw"][0, 0, 0] == pytest.approx(1.0, abs=1e-12)
    np.testing.assert_allclose(result.arrays["magnitude_raw_linear"][0, 0, mask], 1.0, atol=1e-12)
    np.testing.assert_allclose(result.arrays["phase_raw_rad"][0, 0, mask], 0.0, atol=1e-12)


def test_public_pipeline_multitap_fir_oracle_retains_taps_and_signs() -> None:
    output, _, audio = _fixture_waveforms()
    impulse_response = np.zeros(24, dtype=np.float64)
    impulse_response[7] = 0.25
    impulse_response[23] = -0.10
    captured = np.convolve(output[0], impulse_response, mode="full")[: output.shape[1]][
        np.newaxis, :
    ]
    result = process_ess_waveforms(
        output,
        captured,
        sample_rate_hz=audio.sample_rate_hz,
        sweep_sample_count=12000,
        pre_silence_sample_count=480,
        start_frequency_hz=audio.ess_start_frequency_hz,
        end_frequency_hz=audio.ess_end_frequency_hz,
        analysis_lower_hz=500.0,
        analysis_upper_hz=8000.0,
        smoothing_enabled=False,
    )
    ir = result.arrays["ir_raw"][0, 0]
    active_sweep = output[0, 480 : 480 + 12000].astype(np.float64)
    positions = np.arange(active_sweep.size, dtype=np.float64)
    inverse = active_sweep[::-1] * np.exp(
        -np.log(audio.ess_end_frequency_hz / audio.ess_start_frequency_hz)
        * positions
        / active_sweep.size
    )
    reference_before = np.convolve(active_sweep, inverse, mode="full")
    reference_peak = int(np.argmax(np.abs(reference_before)))
    reference = reference_before / reference_before[reference_peak]
    expected_tap_7 = 0.25 * reference[reference_peak] - 0.10 * reference[reference_peak - 16]
    expected_tap_23 = 0.25 * reference[reference_peak + 16] - 0.10 * reference[reference_peak]
    assert result.estimated_latency_samples == 7
    assert result.ir_raw_dominant_peak_index == 7
    assert ir[7] == pytest.approx(expected_tap_7, abs=1e-10)
    assert ir[23] == pytest.approx(expected_tap_23, abs=1e-10)
    assert ir[7] > 0.0
    assert ir[23] < 0.0
    assert ir[23] / ir[7] == pytest.approx(expected_tap_23 / expected_tap_7, abs=1e-10)


def test_public_pipeline_polarity_oracle_preserves_negative_sign() -> None:
    output, _, audio = _fixture_waveforms()
    result = process_ess_waveforms(
        output,
        -output,
        sample_rate_hz=audio.sample_rate_hz,
        sweep_sample_count=12000,
        pre_silence_sample_count=480,
        start_frequency_hz=audio.ess_start_frequency_hz,
        end_frequency_hz=audio.ess_end_frequency_hz,
        analysis_lower_hz=500.0,
        analysis_upper_hz=8000.0,
        smoothing_enabled=False,
    )
    assert result.estimated_latency_samples == 0
    assert result.latency_correlation_coefficient == pytest.approx(-1.0, abs=1e-12)
    assert abs(result.latency_correlation_coefficient) == pytest.approx(1.0, abs=1e-12)
    assert result.ir_raw_dominant_peak_index == 0
    assert result.ir_raw_dominant_peak_value == pytest.approx(-1.0, abs=1e-12)


def test_processing_api_contains_no_truth_or_scenario_parameters() -> None:
    parameters = inspect.signature(process_ess_waveforms).parameters
    assert not {
        "expected_latency",
        "expected_gain",
        "integer_latency_samples",
        "linear_gain",
        "scenario",
    }.intersection(parameters)


EXPECTED_ARRAY_NAMES = {
    "inverse_filter",
    "reference_deconvolution",
    "input_deconvolution",
    "deconvolution_relative_samples",
    "deconvolution_relative_seconds",
    "ir_raw",
    "ir_aligned",
    "frequency_hz",
    "transfer_raw_real",
    "transfer_raw_imag",
    "transfer_aligned_real",
    "transfer_aligned_imag",
    "magnitude_raw_linear",
    "magnitude_raw_db",
    "phase_raw_rad",
    "phase_raw_unwrapped_rad",
    "magnitude_aligned_linear",
    "magnitude_aligned_db",
    "phase_aligned_rad",
    "phase_aligned_unwrapped_rad",
    "analysis_band_mask",
}


def _nominal_result() -> EssProcessingResult:
    output, captured, audio = _fixture_waveforms()
    return process_ess_waveforms(
        output,
        captured,
        sample_rate_hz=audio.sample_rate_hz,
        sweep_sample_count=12000,
        pre_silence_sample_count=480,
        start_frequency_hz=audio.ess_start_frequency_hz,
        end_frequency_hz=audio.ess_end_frequency_hz,
        analysis_lower_hz=500.0,
        analysis_upper_hz=8000.0,
        smoothing_enabled=False,
    )


def test_processing_emits_exactly_twenty_one_declared_arrays() -> None:
    assert set(_nominal_result().arrays) == EXPECTED_ARRAY_NAMES


def test_processing_arrays_are_typed_finite_and_c_contiguous() -> None:
    arrays = _nominal_result().arrays
    for name, array in arrays.items():
        assert array.flags.c_contiguous, name
        if name == "deconvolution_relative_samples":
            assert array.dtype == np.int64
        elif name == "analysis_band_mask":
            assert array.dtype == np.bool_
        else:
            assert array.dtype == np.float64
        assert np.isfinite(array).all(), name


def test_ir_and_transfer_arrays_are_channel_first() -> None:
    result = _nominal_result()
    for name, array in result.arrays.items():
        if name.startswith(("ir_", "transfer_", "magnitude_", "phase_")):
            assert array.ndim == 3 and array.shape[:2] == (1, 1), name
    assert result.arrays["frequency_hz"].ndim == 1
    assert result.arrays["analysis_band_mask"].ndim == 1


def test_transfer_real_imaginary_and_magnitude_are_consistent() -> None:
    arrays = _nominal_result().arrays
    complex_raw = arrays["transfer_raw_real"] + 1j * arrays["transfer_raw_imag"]
    np.testing.assert_allclose(np.abs(complex_raw), arrays["magnitude_raw_linear"])
    expected_db = 20 * np.log10(
        np.maximum(arrays["magnitude_raw_linear"], np.finfo(np.float64).tiny)
    )
    np.testing.assert_allclose(arrays["magnitude_raw_db"], expected_db)


def test_frequency_axis_matches_rfft_contract() -> None:
    result = _nominal_result()
    frequency = result.arrays["frequency_hz"]
    assert frequency.size == result.transfer_fft_length // 2 + 1
    assert frequency[0] == 0.0
    assert frequency[-1] == 24000.0
    assert result.transfer_fft_length & (result.transfer_fft_length - 1) == 0


def test_analysis_band_mask_comes_from_configured_boundaries() -> None:
    arrays = _nominal_result().arrays
    frequency = arrays["frequency_hz"]
    mask = arrays["analysis_band_mask"]
    assert np.array_equal(mask, (frequency >= 500.0) & (frequency <= 8000.0))
    assert mask.any() and not mask.all()


def test_latency_correlation_preserves_negative_sign() -> None:
    sweep = np.array([1.0, -0.5, 0.25, 0.75], dtype=np.float64)
    lag, coefficient = estimate_latency_samples(sweep, np.pad(-sweep, (2, 1)))
    assert lag == 2
    assert coefficient == pytest.approx(-1.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sample_rate_hz", 0),
        ("sweep_sample_count", 1),
        ("pre_silence_sample_count", -1),
        ("analysis_lower_hz", 0.0),
        ("analysis_upper_hz", 24000.0),
        ("analysis_upper_hz", 400.0),
        ("smoothing_enabled", True),
    ],
)
def test_processing_rejects_invalid_numeric_contract(field: str, value: object) -> None:
    output, captured, audio = _fixture_waveforms()
    arguments: dict[str, object] = {
        "sample_rate_hz": audio.sample_rate_hz,
        "sweep_sample_count": 12000,
        "pre_silence_sample_count": 480,
        "start_frequency_hz": audio.ess_start_frequency_hz,
        "end_frequency_hz": audio.ess_end_frequency_hz,
        "analysis_lower_hz": 500.0,
        "analysis_upper_hz": 8000.0,
        "smoothing_enabled": False,
    }
    arguments[field] = value
    process: Callable[..., object] = process_ess_waveforms
    with pytest.raises(EssProcessingError):
        process(output, captured, **arguments)


@pytest.mark.parametrize(
    ("output", "captured"),
    [
        (np.ones(10), np.ones((1, 10))),
        (np.ones((2, 10)), np.ones((2, 10))),
        (np.ones((1, 10)), np.ones((1, 9))),
        (np.full((1, 10), np.nan), np.ones((1, 10))),
    ],
)
def test_processing_rejects_invalid_waveform_contract(
    output: np.ndarray, captured: np.ndarray
) -> None:
    with pytest.raises(EssProcessingError):
        process_ess_waveforms(
            output,
            captured,
            sample_rate_hz=48000,
            sweep_sample_count=4,
            pre_silence_sample_count=1,
            start_frequency_hz=300.0,
            end_frequency_hz=10000.0,
            analysis_lower_hz=500.0,
            analysis_upper_hz=8000.0,
            smoothing_enabled=False,
        )
