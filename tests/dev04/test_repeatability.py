from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest
from pydantic import ValidationError

from acoustic_ladder.audio.repeatability import (
    RepeatabilityError,
    RepeatabilityKernelMember,
    compute_provisional_repeatability_metrics,
)
from acoustic_ladder.audio.repeatability_models import (
    ProvisionalRepeatabilityMetrics,
    RepeatabilityMemberIdentity,
)


def _member(
    *,
    run: str,
    order: int,
    latency: int,
    captured: list[float],
    ir: list[float],
    transfer: list[complex],
) -> RepeatabilityKernelMember:
    complex_values = np.asarray(transfer, dtype=np.complex128)
    return RepeatabilityKernelMember(
        identity=RepeatabilityMemberIdentity(
            source_run_id=run,
            processing_id="processing001",
            qc_id="qc001",
        ),
        measurement_order=order,
        latency_samples=latency,
        pre_silence_sample_count=1,
        captured_input=np.asarray([captured], dtype=np.float64),
        ir_aligned=np.asarray([[ir]], dtype=np.float64),
        transfer_aligned_real=np.asarray([[complex_values.real]], dtype=np.float64),
        transfer_aligned_imag=np.asarray([[complex_values.imag]], dtype=np.float64),
        analysis_band_mask=np.ones(complex_values.size, dtype=np.bool_),
    )


def test_two_different_members_compute_independent_pair_oracles() -> None:
    first = _member(
        run="capture001",
        order=0,
        latency=2,
        captured=[0.0, 1.0, 2.0],
        ir=[1.0, 0.0],
        transfer=[1.0 + 0.0j, 1.0 + 0.0j],
    )
    second = _member(
        run="capture002",
        order=1,
        latency=5,
        captured=[0.0, 2.0, 1.0],
        ir=[0.0, 1.0],
        transfer=[2.0 + 0.0j, 0.0 + 1.0j],
    )

    metrics = compute_provisional_repeatability_metrics([second, first])

    assert [member.measurement_order for member in metrics.members] == [0, 1]
    assert metrics.member_count == 2
    assert metrics.pair_count == 1
    pair = metrics.pairs[0]
    assert pair.captured_input_correlation == pytest.approx(4.0 / 5.0)
    assert pair.latency_delta_samples == 3
    assert pair.latency_absolute_delta_samples == 3
    assert pair.ir_correlation == 0.0
    assert pair.ir_symmetric_nrmse == pytest.approx(math.sqrt(2.0))
    assert pair.complex_transfer_relative_l2 == pytest.approx(math.sqrt(3.0 / 3.5))
    expected_magnitude = math.sqrt((20.0 * math.log10(2.0)) ** 2 / 2.0)
    assert pair.magnitude_rmse_db == pytest.approx(expected_magnitude)
    assert pair.phase_rms_rad == pytest.approx(math.pi / math.sqrt(8.0))
    assert pair.joint_phase_valid_bin_count == 2
    assert pair.joint_phase_valid_fraction == 1.0
    assert metrics.latency_span_samples == 3
    assert metrics.ir_symmetric_nrmse_max == pytest.approx(math.sqrt(2.0))
    assert metrics.all_required_numeric_values_finite is True


def test_metrics_model_recomputes_aggregates_from_pair_records() -> None:
    first = _member(
        run="capture001",
        order=0,
        latency=2,
        captured=[0.0, 1.0, 2.0],
        ir=[1.0, 0.0],
        transfer=[1.0 + 0.0j, 1.0 + 0.0j],
    )
    second = _member(
        run="capture002",
        order=1,
        latency=5,
        captured=[0.0, 2.0, 1.0],
        ir=[0.0, 1.0],
        transfer=[2.0 + 0.0j, 0.0 + 1.0j],
    )
    metrics = compute_provisional_repeatability_metrics([first, second])
    payload = metrics.model_dump()
    payload["ir_symmetric_nrmse_mean"] += 0.25

    with pytest.raises(ValidationError, match="aggregate"):
        ProvisionalRepeatabilityMetrics.model_validate(payload)


def test_zero_denominators_are_null_and_phase_fraction_is_count_bound() -> None:
    first = _member(
        run="capture001",
        order=0,
        latency=0,
        captured=[0.0, 0.0, 0.0],
        ir=[0.0, 0.0],
        transfer=[0.0j, 0.0j],
    )
    second = _member(
        run="capture002",
        order=1,
        latency=0,
        captured=[0.0, 0.0, 0.0],
        ir=[0.0, 0.0],
        transfer=[0.0j, 0.0j],
    )

    metrics = compute_provisional_repeatability_metrics([first, second])
    pair = metrics.pairs[0]

    assert pair.captured_input_correlation is None
    assert pair.captured_input_correlation_status == "zero_both_norm"
    assert pair.ir_correlation is None
    assert pair.ir_symmetric_nrmse is None
    assert pair.complex_transfer_relative_l2 is None
    assert pair.phase_rms_rad is None
    assert pair.phase_rms_status == "no_joint_phase_valid_bins"
    assert pair.joint_phase_valid_bin_count == 0
    assert pair.joint_phase_valid_fraction == 0.0
    payload = pair.model_dump()
    payload["joint_phase_valid_fraction"] = 0.5
    with pytest.raises(ValidationError, match="fraction"):
        type(pair).model_validate(payload)


def test_three_members_cover_polarity_scaling_and_single_bin_phase() -> None:
    members = [
        _member(
            run="capture001",
            order=0,
            latency=1,
            captured=[0.0, 1.0, 0.0],
            ir=[1.0, 0.0],
            transfer=[1.0 + 0.0j, 1.0 + 0.0j],
        ),
        _member(
            run="capture002",
            order=1,
            latency=2,
            captured=[0.0, -1.0, 0.0],
            ir=[-1.0, 0.0],
            transfer=[2.0 + 0.0j, 2.0 + 0.0j],
        ),
        _member(
            run="capture003",
            order=2,
            latency=4,
            captured=[0.0, 1.0, 0.0],
            ir=[1.0, 0.0],
            transfer=[0.0 + 1.0j, 1.0 + 0.0j],
        ),
    ]

    metrics = compute_provisional_repeatability_metrics([members[2], members[0], members[1]])

    assert metrics.member_count == 3
    assert metrics.pair_count == 3
    assert [pair.captured_input_correlation for pair in metrics.pairs] == [-1.0, 1.0, -1.0]
    assert [pair.ir_correlation for pair in metrics.pairs] == [-1.0, 1.0, -1.0]
    assert metrics.pairwise_maximum_absolute_latency_delta_samples == 3
    assert metrics.latency_span_samples == 3
    first_pair = metrics.pairs[0]
    assert first_pair.complex_transfer_relative_l2 == pytest.approx(math.sqrt(2.0 / 5.0))
    assert first_pair.magnitude_rmse_db == pytest.approx(20.0 * math.log10(2.0))
    phase_pair = metrics.pairs[1]
    assert phase_pair.phase_rms_rad == pytest.approx(math.pi / math.sqrt(8.0))
    assert metrics.captured_input_correlation_min == -1.0
    assert metrics.captured_input_correlation_mean == pytest.approx(-1.0 / 3.0)


def test_kernel_rejects_different_analysis_masks_with_same_bin_count() -> None:
    first = _member(
        run="capture001",
        order=0,
        latency=0,
        captured=[0.0, 1.0],
        ir=[1.0],
        transfer=[1.0 + 0.0j, 2.0 + 0.0j, 3.0 + 0.0j],
    )
    second = replace(
        _member(
            run="capture002",
            order=1,
            latency=0,
            captured=[0.0, 1.0],
            ir=[1.0],
            transfer=[1.0 + 0.0j, 2.0 + 0.0j, 3.0 + 0.0j],
        ),
        analysis_band_mask=np.asarray([False, True, True], dtype=np.bool_),
    )
    first = replace(first, analysis_band_mask=np.asarray([True, False, True], dtype=np.bool_))

    with pytest.raises(RepeatabilityError, match="analysis-band masks differ"):
        compute_provisional_repeatability_metrics([first, second])
