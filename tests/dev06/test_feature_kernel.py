import math

import numpy as np
import pytest

from acoustic_ladder.analysis.feature_kernel import (
    FEATURE_IDS,
    compute_analysis_row_features,
)
from acoustic_ladder.audio.baseline_difference import BaselineDifferenceKernelMember


def _member(order: int, raw: float, aligned: float) -> BaselineDifferenceKernelMember:
    frequency = np.ascontiguousarray(np.array([1000.0, 2000.0, 3000.0], dtype=np.float64))
    mask = np.ascontiguousarray(np.array([True, True, True], dtype=np.bool_))

    def cube(value: float, count: int) -> np.ndarray:
        return np.ascontiguousarray(np.full((1, 1, count), value, dtype=np.float64))

    return BaselineDifferenceKernelMember(
        measurement_order=order,
        frequency_hz=frequency,
        analysis_band_mask=mask,
        transfer_raw_real=cube(raw, 3),
        transfer_raw_imag=cube(0.0, 3),
        transfer_aligned_real=cube(aligned, 3),
        transfer_aligned_imag=cube(0.0, 3),
        ir_raw=cube(raw, 2),
        ir_aligned=cube(aligned, 2),
    )


def test_feature_kernel_matches_hard_coded_complex_and_ir_oracle() -> None:
    result = compute_analysis_row_features(
        baseline_members=[_member(1, 1.0, 2.0), _member(2, 3.0, 4.0)],
        candidate=_member(3, 4.0, 6.0),
    )

    expected = np.array(
        [
            math.sqrt(0.4),
            math.sqrt(0.4),
            20.0 * math.log10(2.0),
            20.0 * math.log10(2.0),
            20.0 * math.log10(2.0),
            20.0 * math.log10(2.0),
            0.0,
            0.0,
            0.0,
            0.0,
            math.sqrt(0.4),
            math.sqrt(0.4),
            2.0,
            3.0,
            0.0,
            0.0,
        ],
        dtype=np.float64,
    )
    assert result.feature_ids == FEATURE_IDS
    np.testing.assert_allclose(result.feature_vector, expected, rtol=0.0, atol=1e-12)
    np.testing.assert_array_equal(result.arrays["raw_complex_ratio_real"], 2.0)
    np.testing.assert_array_equal(result.arrays["raw_ratio_valid_mask"], True)
    np.testing.assert_array_equal(result.arrays["raw_wrapped_phase_difference_rad"], 0.0)
    np.testing.assert_array_equal(result.arrays["raw_unwrapped_phase_difference_rad"], 0.0)
    np.testing.assert_array_equal(result.arrays["raw_ir_difference"], 2.0)
    assert np.isfinite(result.feature_vector).all()


def test_feature_kernel_exposes_invalid_denominator_and_rejects_null_required_feature() -> None:
    with pytest.raises(ValueError, match="required feature") as raised:
        compute_analysis_row_features(
            baseline_members=[_member(1, 0.0, 0.0), _member(2, 0.0, 0.0)],
            candidate=_member(3, 1.0, 1.0),
        )

    assert "phase" in str(raised.value)
