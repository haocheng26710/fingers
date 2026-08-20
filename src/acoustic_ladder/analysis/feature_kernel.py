"""Pure deterministic row-vs-baseline arrays and interpretable features."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.baseline_difference import (
    BaselineDifferenceKernelMember,
    ProvisionalBaselineDifferenceMetrics,
    compute_provisional_baseline_difference,
)

from .spec import FEATURE_IDS


@dataclass(frozen=True)
class AnalysisRowFeatureResult:
    feature_ids: tuple[str, ...]
    feature_vector: NDArray[np.float64]
    arrays: dict[str, NDArray[np.generic]]
    metrics: ProvisionalBaselineDifferenceMetrics
    denominator_floor: float


def _unwrap_segments(wrapped: np.ndarray, valid: np.ndarray) -> NDArray[np.float64]:
    output = np.zeros(wrapped.shape, dtype=np.float64)
    wrapped_rows = wrapped.reshape(-1, wrapped.shape[-1])
    valid_rows = valid.reshape(-1, valid.shape[-1])
    output_rows = output.reshape(-1, output.shape[-1])
    for row, (angles, flags) in enumerate(zip(wrapped_rows, valid_rows, strict=True)):
        start = 0
        while start < flags.size:
            if not flags[start]:
                start += 1
                continue
            end = start + 1
            while end < flags.size and flags[end]:
                end += 1
            output_rows[row, start:end] = np.unwrap(angles[start:end])
            start = end
    return np.ascontiguousarray(output)


def _source_arrays(
    candidate: BaselineDifferenceKernelMember,
    arrays: dict[str, NDArray[np.generic]],
) -> None:
    for representation in ("raw", "aligned"):
        real = getattr(candidate, f"transfer_{representation}_real")
        imag = getattr(candidate, f"transfer_{representation}_imag")
        transfer = real + (1j * imag)
        magnitude = np.abs(transfer)
        valid = magnitude > np.finfo(np.float64).tiny
        wrapped = np.zeros(transfer.shape, dtype=np.float64)
        wrapped[valid] = np.angle(transfer[valid])
        arrays[f"{representation}_transfer_real"] = np.ascontiguousarray(real)
        arrays[f"{representation}_transfer_imag"] = np.ascontiguousarray(imag)
        arrays[f"{representation}_magnitude_linear"] = np.ascontiguousarray(magnitude)
        arrays[f"{representation}_wrapped_phase_rad"] = np.ascontiguousarray(wrapped)
        arrays[f"{representation}_unwrapped_phase_rad"] = _unwrap_segments(wrapped, valid)
        arrays[f"{representation}_ir"] = np.ascontiguousarray(
            getattr(candidate, f"ir_{representation}")
        )


def compute_analysis_row_features(
    *,
    baseline_members: Sequence[BaselineDifferenceKernelMember],
    candidate: BaselineDifferenceKernelMember,
) -> AnalysisRowFeatureResult:
    """Compare one row with its leak-free group baseline and return the fixed 16 columns."""

    if any(member.measurement_order == candidate.measurement_order for member in baseline_members):
        raise ValueError("candidate row cannot participate in its own baseline reference")
    result = compute_provisional_baseline_difference(baseline_members, [candidate])
    metrics = result.metrics
    values: tuple[float | None, ...] = (
        metrics.raw_transfer.complex_additive_difference_symmetric_relative_l2,
        metrics.aligned_transfer.complex_additive_difference_symmetric_relative_l2,
        metrics.raw_transfer.magnitude_difference_rms_db,
        metrics.aligned_transfer.magnitude_difference_rms_db,
        metrics.raw_transfer.magnitude_difference_maximum_absolute_db,
        metrics.aligned_transfer.magnitude_difference_maximum_absolute_db,
        metrics.raw_transfer.phase_difference_rms_rad,
        metrics.aligned_transfer.phase_difference_rms_rad,
        metrics.raw_transfer.phase_difference_maximum_absolute_rad,
        metrics.aligned_transfer.phase_difference_maximum_absolute_rad,
        metrics.raw_ir.symmetric_nrmse,
        metrics.aligned_ir.symmetric_nrmse,
        metrics.raw_ir.difference_absolute_peak,
        metrics.aligned_ir.difference_absolute_peak,
        float(metrics.raw_ir.difference_peak_index),
        float(metrics.aligned_ir.difference_peak_index),
    )
    missing = [name for name, value in zip(FEATURE_IDS, values, strict=True) if value is None]
    if missing:
        raise ValueError(f"required feature is null: {', '.join(missing)}")
    feature_vector = np.ascontiguousarray(np.array(values, dtype=np.float64))
    if feature_vector.shape != (len(FEATURE_IDS),) or not bool(np.isfinite(feature_vector).all()):
        raise ValueError("required feature vector must be finite float64")
    arrays = {name: np.ascontiguousarray(value) for name, value in result.arrays.items()}
    _source_arrays(candidate, arrays)
    return AnalysisRowFeatureResult(
        feature_ids=FEATURE_IDS,
        feature_vector=feature_vector,
        arrays=arrays,
        metrics=metrics,
        denominator_floor=result.denominator_floor,
    )


__all__ = ["FEATURE_IDS", "AnalysisRowFeatureResult", "compute_analysis_row_features"]
