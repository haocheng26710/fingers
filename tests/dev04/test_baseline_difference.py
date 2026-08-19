from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pytest

from acoustic_ladder.audio.baseline_difference import (
    BaselineDifferenceError,
    BaselineDifferenceKernelMember,
    compute_provisional_baseline_difference,
)


def _member(
    order: int,
    raw: np.ndarray,
    *,
    aligned: np.ndarray | None = None,
    raw_ir: np.ndarray | None = None,
    aligned_ir: np.ndarray | None = None,
    mask: np.ndarray | None = None,
) -> BaselineDifferenceKernelMember:
    transfer = np.asarray(raw, dtype=np.complex128).reshape(1, 1, -1)
    aligned_transfer = (
        transfer.copy()
        if aligned is None
        else np.asarray(aligned, dtype=np.complex128).reshape(1, 1, -1)
    )
    ir = np.asarray([0.0, 1.0] if raw_ir is None else raw_ir, dtype=np.float64).reshape(1, 1, -1)
    ir_aligned = (
        ir.copy()
        if aligned_ir is None
        else np.asarray(aligned_ir, dtype=np.float64).reshape(1, 1, -1)
    )
    frequency = np.arange(transfer.shape[-1], dtype=np.float64) * 100.0
    band = np.ones(frequency.shape, dtype=np.bool_) if mask is None else mask
    return BaselineDifferenceKernelMember(
        measurement_order=order,
        frequency_hz=frequency,
        analysis_band_mask=band,
        transfer_raw_real=transfer.real,
        transfer_raw_imag=transfer.imag,
        transfer_aligned_real=aligned_transfer.real,
        transfer_aligned_imag=aligned_transfer.imag,
        ir_raw=ir,
        ir_aligned=ir_aligned,
    )


def test_hard_coded_complex_oracle_and_ir_oracle() -> None:
    baseline = [
        _member(0, np.array([1 + 0j, 0 + 1j]), raw_ir=np.array([1.0, 3.0])),
        _member(1, np.array([3 + 0j, 0 + 3j]), raw_ir=np.array([3.0, 5.0])),
    ]
    candidate = [
        _member(0, np.array([2 + 0j, 0 + 2j]), raw_ir=np.array([2.0, 4.0])),
        _member(1, np.array([6 + 0j, 0 + 6j]), raw_ir=np.array([6.0, 8.0])),
    ]

    result = compute_provisional_baseline_difference(baseline, candidate)
    arrays = result.arrays

    np.testing.assert_array_equal(arrays["raw_baseline_mean_transfer_real"], [[[2.0, 0.0]]])
    np.testing.assert_array_equal(arrays["raw_baseline_mean_transfer_imag"], [[[0.0, 2.0]]])
    np.testing.assert_array_equal(arrays["raw_candidate_mean_transfer_real"], [[[4.0, 0.0]]])
    np.testing.assert_array_equal(arrays["raw_candidate_mean_transfer_imag"], [[[0.0, 4.0]]])
    np.testing.assert_array_equal(arrays["raw_complex_additive_difference_real"], [[[2.0, 0.0]]])
    np.testing.assert_array_equal(arrays["raw_complex_additive_difference_imag"], [[[0.0, 2.0]]])
    np.testing.assert_array_equal(arrays["raw_complex_ratio_real"], [[[2.0, 2.0]]])
    np.testing.assert_array_equal(arrays["raw_complex_ratio_imag"], [[[0.0, 0.0]]])
    np.testing.assert_allclose(
        arrays["raw_magnitude_difference_db"],
        np.full((1, 1, 2), 20.0 * np.log10(2.0)),
        atol=1e-12,
    )
    np.testing.assert_array_equal(arrays["raw_wrapped_phase_difference_rad"], 0.0)
    np.testing.assert_array_equal(arrays["baseline_mean_raw_ir"], [[[2.0, 4.0]]])
    np.testing.assert_array_equal(arrays["candidate_mean_raw_ir"], [[[4.0, 6.0]]])
    np.testing.assert_array_equal(arrays["raw_ir_difference"], [[[2.0, 2.0]]])
    assert result.metrics.raw_ir.difference_l2 == pytest.approx(np.sqrt(8.0))
    assert result.metrics.raw_ir.difference_absolute_peak == 2.0
    assert result.metrics.raw_ir.difference_peak_index == 0
    assert result.metrics.raw_ir.symmetric_nrmse == pytest.approx(
        np.sqrt(8.0) / np.sqrt((20.0 + 52.0) / 2.0)
    )


def test_zero_baseline_bin_is_masked_and_outputs_zero_without_nonfinite_values() -> None:
    result = compute_provisional_baseline_difference(
        [_member(0, np.array([0 + 0j, 1 + 0j]))],
        [_member(0, np.array([1 + 0j, 0 + 1j]))],
    )
    arrays = result.arrays

    np.testing.assert_array_equal(arrays["raw_ratio_valid_mask"], [[[False, True]]])
    np.testing.assert_array_equal(arrays["raw_complex_ratio_real"][..., 0], 0.0)
    np.testing.assert_array_equal(arrays["raw_complex_ratio_imag"][..., 0], 0.0)
    np.testing.assert_array_equal(arrays["raw_phase_valid_mask"], [[[False, True]]])
    np.testing.assert_array_equal(arrays["raw_wrapped_phase_difference_rad"][..., 0], 0.0)
    np.testing.assert_array_equal(arrays["raw_unwrapped_phase_difference_rad"][..., 0], 0.0)
    assert all(np.all(np.isfinite(value)) for value in arrays.values() if value.dtype != np.bool_)


def test_phase_unwrap_does_not_cross_an_invalid_gap() -> None:
    baseline = _member(0, np.ones(3, dtype=np.complex128))
    candidate = _member(
        0,
        np.exp(1j * np.array([3.0, 0.0, -3.0])),
    )
    candidate = replace(
        candidate,
        transfer_raw_real=np.array([[[np.cos(3.0), 0.0, np.cos(-3.0)]]]),
        transfer_raw_imag=np.array([[[np.sin(3.0), 0.0, np.sin(-3.0)]]]),
    )

    result = compute_provisional_baseline_difference([baseline], [candidate])

    np.testing.assert_array_equal(result.arrays["raw_phase_valid_mask"], [[[True, False, True]]])
    np.testing.assert_allclose(
        result.arrays["raw_unwrapped_phase_difference_rad"],
        [[[3.0, 0.0, -3.0]]],
        atol=1e-12,
    )


def test_member_input_order_does_not_change_any_output() -> None:
    baseline = [_member(0, np.array([1 + 1j])), _member(1, np.array([3 + 1j]))]
    candidate = [_member(0, np.array([2 + 2j])), _member(1, np.array([4 + 2j]))]
    forward = compute_provisional_baseline_difference(baseline, candidate)
    reverse = compute_provisional_baseline_difference(baseline[::-1], candidate[::-1])

    assert forward.metrics == reverse.metrics
    assert forward.denominator_floor == reverse.denominator_floor
    assert forward.arrays.keys() == reverse.arrays.keys()
    for name in forward.arrays:
        np.testing.assert_array_equal(forward.arrays[name], reverse.arrays[name])


def test_raw_aligned_and_unequal_member_counts_remain_separate() -> None:
    baseline = [
        _member(0, np.array([1 + 0j]), aligned=np.array([2 + 0j])),
        _member(1, np.array([3 + 0j]), aligned=np.array([4 + 0j])),
    ]
    candidate = [
        _member(0, np.array([2 + 0j]), aligned=np.array([6 + 0j])),
        _member(1, np.array([4 + 0j]), aligned=np.array([8 + 0j])),
        _member(2, np.array([6 + 0j]), aligned=np.array([10 + 0j])),
    ]

    result = compute_provisional_baseline_difference(baseline, candidate)

    np.testing.assert_array_equal(result.arrays["raw_complex_additive_difference_real"], [[[2.0]]])
    np.testing.assert_array_equal(
        result.arrays["aligned_complex_additive_difference_real"], [[[5.0]]]
    )
    assert result.metrics.raw_transfer.analysis_band_valid_bin_count == 1
    assert result.metrics.raw_transfer.analysis_band_valid_fraction == 1.0


def test_zero_symmetric_denominators_return_null_with_explicit_status() -> None:
    zero = _member(
        0,
        np.array([0 + 0j]),
        raw_ir=np.array([0.0, 0.0]),
        aligned_ir=np.array([0.0, 0.0]),
    )

    result = compute_provisional_baseline_difference([zero], [zero])

    assert result.metrics.raw_transfer.complex_additive_difference_symmetric_relative_l2 is None
    assert (
        result.metrics.raw_transfer.complex_additive_difference_symmetric_relative_l2_status
        == "zero_symmetric_norm"
    )
    assert result.metrics.raw_transfer.phase_difference_rms_rad is None
    assert result.metrics.raw_transfer.phase_difference_status == "no_valid_bins"
    assert result.metrics.raw_ir.symmetric_nrmse is None
    assert result.metrics.raw_ir.symmetric_nrmse_status == "zero_symmetric_norm"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda member: replace(member, transfer_raw_real=np.array([[[np.nan]]])),
        lambda member: replace(member, transfer_raw_real=np.zeros((1, 2, 1))),
        lambda member: replace(member, frequency_hz=np.array([1.0])),
        lambda member: replace(member, analysis_band_mask=np.array([True], dtype=np.bool_)),
        lambda member: replace(
            member, transfer_raw_real=member.transfer_raw_real.astype(np.float32)
        ),
    ],
)
def test_nonfinite_shape_frequency_mask_and_dtype_mismatches_are_rejected(
    mutation: Callable[[BaselineDifferenceKernelMember], BaselineDifferenceKernelMember],
) -> None:
    baseline = _member(0, np.array([1 + 0j, 2 + 0j]))
    candidate = _member(0, np.array([1 + 0j, 2 + 0j]))

    with pytest.raises(BaselineDifferenceError):
        compute_provisional_baseline_difference([baseline], [mutation(candidate)])
