"""Pure deterministic pairwise repeatability mathematics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from statistics import fmean
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.repeatability_models import (
    ProvisionalRepeatabilityMetrics,
    RepeatabilityMemberEvidence,
    RepeatabilityMemberIdentity,
    RepeatabilityPairMetrics,
)


class RepeatabilityError(ValueError):
    """Raised when repeatability inputs cannot satisfy the mathematical contract."""


@dataclass(frozen=True)
class RepeatabilityKernelMember:
    identity: RepeatabilityMemberIdentity
    measurement_order: int
    latency_samples: int
    pre_silence_sample_count: int
    captured_input: NDArray[np.generic]
    ir_aligned: NDArray[np.generic]
    transfer_aligned_real: NDArray[np.generic]
    transfer_aligned_imag: NDArray[np.generic]
    analysis_band_mask: NDArray[np.generic]


@dataclass(frozen=True)
class _NormalizedMember:
    evidence: RepeatabilityMemberEvidence
    captured_after_pre: NDArray[np.float64]
    ir: NDArray[np.float64]
    transfer_in_band: NDArray[np.complex128]
    analysis_band_mask: NDArray[np.bool_]


CorrelationStatus = Literal["computed", "zero_left_norm", "zero_right_norm", "zero_both_norm"]


def _real_array(
    value: NDArray[np.generic], shape_prefix: tuple[int, ...], label: str
) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype.kind not in "iuf" or array.ndim != len(shape_prefix) + 1:
        raise RepeatabilityError(f"{label} has invalid shape or dtype")
    if tuple(array.shape[:-1]) != shape_prefix or array.shape[-1] == 0:
        raise RepeatabilityError(f"{label} has invalid shape or is empty")
    normalized = np.ascontiguousarray(array, dtype=np.float64)
    if not bool(np.isfinite(normalized).all()):
        raise RepeatabilityError(f"{label} contains non-finite values")
    return normalized


def _normalized(member: RepeatabilityKernelMember) -> _NormalizedMember:
    if (
        isinstance(member.measurement_order, bool)
        or not isinstance(member.measurement_order, int)
        or member.measurement_order < 0
        or isinstance(member.latency_samples, bool)
        or not isinstance(member.latency_samples, int)
        or member.latency_samples < 0
        or isinstance(member.pre_silence_sample_count, bool)
        or not isinstance(member.pre_silence_sample_count, int)
        or member.pre_silence_sample_count < 0
    ):
        raise RepeatabilityError("member counts must be non-negative integers")
    captured = _real_array(member.captured_input, (1,), "captured input")
    if member.pre_silence_sample_count >= captured.shape[-1]:
        raise RepeatabilityError("pre-silence removes the entire captured input")
    ir = _real_array(member.ir_aligned, (1, 1), "aligned IR")
    real = _real_array(member.transfer_aligned_real, (1, 1), "aligned transfer real")
    imag = _real_array(member.transfer_aligned_imag, (1, 1), "aligned transfer imaginary")
    mask = np.asarray(member.analysis_band_mask)
    if mask.dtype != np.bool_ or mask.ndim != 1 or mask.size == 0:
        raise RepeatabilityError("analysis band mask must be a non-empty boolean vector")
    if real.shape != imag.shape or real.shape[-1] != mask.size:
        raise RepeatabilityError("aligned transfer dimensions disagree with the analysis mask")
    if not bool(mask.any()):
        raise RepeatabilityError("analysis band contains no bins")
    transfer = np.ascontiguousarray(real[0, 0, mask] + 1j * imag[0, 0, mask])
    return _NormalizedMember(
        evidence=RepeatabilityMemberEvidence(
            identity=member.identity,
            measurement_order=member.measurement_order,
            latency_samples=member.latency_samples,
        ),
        captured_after_pre=np.ascontiguousarray(
            captured[0, member.pre_silence_sample_count :], dtype=np.float64
        ),
        ir=np.ascontiguousarray(ir[0, 0], dtype=np.float64),
        transfer_in_band=transfer,
        analysis_band_mask=np.ascontiguousarray(mask, dtype=np.bool_),
    )


def _norm(value: np.ndarray, label: str) -> float:
    result = float(np.linalg.norm(value))
    if not math.isfinite(result):
        raise RepeatabilityError(f"{label} norm is non-finite")
    return result


def _correlation(
    left: NDArray[np.float64], right: NDArray[np.float64], label: str
) -> tuple[float | None, CorrelationStatus]:
    left_norm = _norm(left, f"{label} left")
    right_norm = _norm(right, f"{label} right")
    if left_norm == 0 and right_norm == 0:
        return None, "zero_both_norm"
    if left_norm == 0:
        return None, "zero_left_norm"
    if right_norm == 0:
        return None, "zero_right_norm"
    value = float(np.dot(left, right) / (left_norm * right_norm))
    if not math.isfinite(value) or value < -1.0 - 1e-12 or value > 1.0 + 1e-12:
        raise RepeatabilityError(f"{label} correlation is outside its numeric contract")
    return min(1.0, max(-1.0, value)), "computed"


def _symmetric_relative(
    left: np.ndarray, right: np.ndarray, label: str
) -> tuple[float | None, Literal["computed", "zero_symmetric_norm"]]:
    left_norm = _norm(left, f"{label} left")
    right_norm = _norm(right, f"{label} right")
    denominator = math.sqrt((left_norm**2 + right_norm**2) / 2.0)
    if denominator == 0:
        return None, "zero_symmetric_norm"
    value = _norm(left - right, f"{label} difference") / denominator
    if not math.isfinite(value):
        raise RepeatabilityError(f"{label} relative difference is non-finite")
    return value, "computed"


def _pair(left: _NormalizedMember, right: _NormalizedMember) -> RepeatabilityPairMetrics:
    if left.captured_after_pre.shape != right.captured_after_pre.shape:
        raise RepeatabilityError("captured-input lengths differ")
    if left.ir.shape != right.ir.shape:
        raise RepeatabilityError("aligned-IR lengths differ")
    if left.transfer_in_band.shape != right.transfer_in_band.shape:
        raise RepeatabilityError("analysis-band transfer dimensions differ")
    captured_corr, captured_status = _correlation(
        left.captured_after_pre, right.captured_after_pre, "captured input"
    )
    ir_corr, ir_corr_status = _correlation(left.ir, right.ir, "aligned IR")
    ir_nrmse, ir_nrmse_status = _symmetric_relative(left.ir, right.ir, "aligned IR")
    transfer_l2, transfer_l2_status = _symmetric_relative(
        left.transfer_in_band, right.transfer_in_band, "complex transfer"
    )
    floor = np.finfo(np.float64).tiny
    left_db = 20.0 * np.log10(np.maximum(np.abs(left.transfer_in_band), floor))
    right_db = 20.0 * np.log10(np.maximum(np.abs(right.transfer_in_band), floor))
    magnitude_rmse = float(np.sqrt(np.mean(np.square(left_db - right_db))))
    if not math.isfinite(magnitude_rmse):
        raise RepeatabilityError("magnitude RMSE is non-finite")
    phase_valid = (np.abs(left.transfer_in_band) > 0) & (np.abs(right.transfer_in_band) > 0)
    phase_count = int(np.count_nonzero(phase_valid))
    phase_fraction = phase_count / int(phase_valid.size)
    if phase_count == 0:
        phase_rms = None
        phase_status: Literal["computed", "no_joint_phase_valid_bins"] = "no_joint_phase_valid_bins"
    else:
        delta = np.angle(
            left.transfer_in_band[phase_valid] * np.conjugate(right.transfer_in_band[phase_valid])
        )
        phase_rms = float(np.sqrt(np.mean(np.square(delta))))
        if not math.isfinite(phase_rms):
            raise RepeatabilityError("phase RMS is non-finite")
        phase_status = "computed"
    latency_delta = right.evidence.latency_samples - left.evidence.latency_samples
    return RepeatabilityPairMetrics(
        left_member=left.evidence.identity,
        right_member=right.evidence.identity,
        left_measurement_order=left.evidence.measurement_order,
        right_measurement_order=right.evidence.measurement_order,
        captured_input_correlation=captured_corr,
        captured_input_correlation_status=captured_status,
        latency_delta_samples=latency_delta,
        latency_absolute_delta_samples=abs(latency_delta),
        ir_correlation=ir_corr,
        ir_correlation_status=ir_corr_status,
        ir_symmetric_nrmse=ir_nrmse,
        ir_symmetric_nrmse_status=ir_nrmse_status,
        complex_transfer_relative_l2=transfer_l2,
        complex_transfer_relative_l2_status=transfer_l2_status,
        magnitude_rmse_db=magnitude_rmse,
        analysis_band_bin_count=int(phase_valid.size),
        joint_phase_valid_bin_count=phase_count,
        joint_phase_valid_fraction=phase_fraction,
        phase_rms_rad=phase_rms,
        phase_rms_status=phase_status,
    )


def _defined(values: Sequence[float | None]) -> tuple[int, float | None, float | None]:
    present = [value for value in values if value is not None]
    if not present:
        return 0, None, None
    return len(present), min(present), fmean(present)


def _mean_max(values: Sequence[float | None]) -> tuple[int, float | None, float | None]:
    present = [value for value in values if value is not None]
    if not present:
        return 0, None, None
    return len(present), fmean(present), max(present)


def compute_provisional_repeatability_metrics(
    members: Sequence[RepeatabilityKernelMember],
) -> ProvisionalRepeatabilityMetrics:
    """Normalize members by measured order and compute all unique unordered pairs."""

    if len(members) < 2:
        raise RepeatabilityError("repeatability requires at least two members")
    normalized = sorted(
        (_normalized(member) for member in members),
        key=lambda item: item.evidence.measurement_order,
    )
    identities = [member.evidence.identity for member in normalized]
    source_runs = [identity.source_run_id for identity in identities]
    orders = [member.evidence.measurement_order for member in normalized]
    if len(set(identity.model_dump_json() for identity in identities)) != len(identities):
        raise RepeatabilityError("repeatability member identity is duplicated")
    if len(set(source_runs)) != len(source_runs):
        raise RepeatabilityError("a source run cannot appear more than once")
    if len(set(orders)) != len(orders):
        raise RepeatabilityError("measurement order is duplicated")
    if orders != list(range(orders[0], orders[-1] + 1)):
        raise RepeatabilityError("measurement orders must be continuous")
    if any(
        not np.array_equal(member.analysis_band_mask, normalized[0].analysis_band_mask)
        for member in normalized[1:]
    ):
        raise RepeatabilityError("analysis-band masks differ")
    pairs = [_pair(left, right) for left, right in combinations(normalized, 2)]
    captured_count, captured_min, captured_mean = _defined(
        [pair.captured_input_correlation for pair in pairs]
    )
    ir_corr_count, ir_corr_min, ir_corr_mean = _defined([pair.ir_correlation for pair in pairs])
    ir_nrmse_count, ir_nrmse_mean, ir_nrmse_max = _mean_max(
        [pair.ir_symmetric_nrmse for pair in pairs]
    )
    transfer_count, transfer_mean, transfer_max = _mean_max(
        [pair.complex_transfer_relative_l2 for pair in pairs]
    )
    phase_count, phase_mean, phase_max = _mean_max([pair.phase_rms_rad for pair in pairs])
    magnitudes = [pair.magnitude_rmse_db for pair in pairs]
    phase_fractions = [pair.joint_phase_valid_fraction for pair in pairs]
    latencies = [member.evidence.latency_samples for member in normalized]
    return ProvisionalRepeatabilityMetrics(
        schema_version="1.0.0",
        members=[member.evidence for member in normalized],
        pairs=pairs,
        member_count=len(normalized),
        pair_count=len(pairs),
        measurement_order_min=orders[0],
        measurement_order_max=orders[-1],
        latency_min_samples=min(latencies),
        latency_max_samples=max(latencies),
        latency_span_samples=max(latencies) - min(latencies),
        pairwise_maximum_absolute_latency_delta_samples=max(
            pair.latency_absolute_delta_samples for pair in pairs
        ),
        captured_input_correlation_defined_count=captured_count,
        captured_input_correlation_min=captured_min,
        captured_input_correlation_mean=captured_mean,
        ir_correlation_defined_count=ir_corr_count,
        ir_correlation_min=ir_corr_min,
        ir_correlation_mean=ir_corr_mean,
        ir_symmetric_nrmse_defined_count=ir_nrmse_count,
        ir_symmetric_nrmse_mean=ir_nrmse_mean,
        ir_symmetric_nrmse_max=ir_nrmse_max,
        complex_transfer_relative_l2_defined_count=transfer_count,
        complex_transfer_relative_l2_mean=transfer_mean,
        complex_transfer_relative_l2_max=transfer_max,
        magnitude_rmse_db_defined_count=len(magnitudes),
        magnitude_rmse_db_mean=fmean(magnitudes),
        magnitude_rmse_db_max=max(magnitudes),
        phase_rms_rad_defined_count=phase_count,
        phase_rms_rad_mean=phase_mean,
        phase_rms_rad_max=phase_max,
        phase_valid_fraction_min=min(phase_fractions),
        phase_valid_fraction_mean=fmean(phase_fractions),
        all_required_numeric_values_finite=True,
    )
