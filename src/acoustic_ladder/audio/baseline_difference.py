"""Pure float64 kernels for provisional synthetic baseline differences."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class BaselineDifferenceError(ValueError):
    """Raised when baseline-difference kernel inputs violate the public contract."""


class _MetricModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class NullableMetric(_MetricModel):
    value: float | None = Field(default=None, ge=0)
    status: Literal["computed", "zero_symmetric_norm", "no_valid_bins"]


class TransferDifferenceMetrics(_MetricModel):
    analysis_band_bin_count: int = Field(gt=0)
    analysis_band_valid_bin_count: int = Field(ge=0)
    analysis_band_valid_fraction: float = Field(ge=0, le=1)
    complex_additive_difference_symmetric_relative_l2: float | None = Field(default=None, ge=0)
    complex_additive_difference_symmetric_relative_l2_status: Literal[
        "computed", "zero_symmetric_norm"
    ]
    magnitude_difference_rms_db: float = Field(ge=0)
    magnitude_difference_maximum_absolute_db: float = Field(ge=0)
    phase_difference_rms_rad: float | None = Field(default=None, ge=0)
    phase_difference_maximum_absolute_rad: float | None = Field(default=None, ge=0)
    phase_difference_status: Literal["computed", "no_valid_bins"]
    phase_defined_count: int = Field(ge=0)
    phase_defined_fraction: float = Field(ge=0, le=1)


class IrDifferenceMetrics(_MetricModel):
    symmetric_nrmse: float | None = Field(default=None, ge=0)
    symmetric_nrmse_status: Literal["computed", "zero_symmetric_norm"]
    difference_l2: float = Field(ge=0)
    difference_absolute_peak: float = Field(ge=0)
    difference_peak_index: int = Field(ge=0)


class ProvisionalBaselineDifferenceMetrics(_MetricModel):
    raw_transfer: TransferDifferenceMetrics
    aligned_transfer: TransferDifferenceMetrics
    raw_ir: IrDifferenceMetrics
    aligned_ir: IrDifferenceMetrics


@dataclass(frozen=True)
class BaselineDifferenceKernelMember:
    measurement_order: int
    frequency_hz: np.ndarray
    analysis_band_mask: np.ndarray
    transfer_raw_real: np.ndarray
    transfer_raw_imag: np.ndarray
    transfer_aligned_real: np.ndarray
    transfer_aligned_imag: np.ndarray
    ir_raw: np.ndarray
    ir_aligned: np.ndarray


@dataclass(frozen=True)
class ProvisionalBaselineDifferenceResult:
    arrays: dict[str, np.ndarray]
    metrics: ProvisionalBaselineDifferenceMetrics
    denominator_floor: float
    ratio_valid_bin_count: dict[Literal["raw", "aligned"], int]
    ratio_invalid_bin_count: dict[Literal["raw", "aligned"], int]


_FLOAT_FIELDS = (
    "frequency_hz",
    "transfer_raw_real",
    "transfer_raw_imag",
    "transfer_aligned_real",
    "transfer_aligned_imag",
    "ir_raw",
    "ir_aligned",
)
_TRANSFER_REPRESENTATIONS: tuple[Literal["raw", "aligned"], ...] = ("raw", "aligned")


def _validate_member(member: BaselineDifferenceKernelMember) -> None:
    if type(member.measurement_order) is not int or member.measurement_order < 0:
        raise BaselineDifferenceError("measurement_order must be a non-negative integer")
    for name in _FLOAT_FIELDS:
        array = getattr(member, name)
        if not isinstance(array, np.ndarray) or array.dtype != np.dtype(np.float64):
            raise BaselineDifferenceError(f"{name} must be a canonical float64 array")
        if not np.all(np.isfinite(array)):
            raise BaselineDifferenceError(f"{name} contains non-finite values")
    if not isinstance(
        member.analysis_band_mask, np.ndarray
    ) or member.analysis_band_mask.dtype != np.dtype(np.bool_):
        raise BaselineDifferenceError("analysis_band_mask must be a canonical bool array")
    if (
        member.frequency_hz.ndim != 1
        or member.analysis_band_mask.shape != member.frequency_hz.shape
    ):
        raise BaselineDifferenceError("frequency axis and analysis mask must be matching vectors")
    if member.frequency_hz.size == 0 or not np.any(member.analysis_band_mask):
        raise BaselineDifferenceError("frequency axis and analysis band must be non-empty")
    if np.any(member.frequency_hz < 0) or np.any(np.diff(member.frequency_hz) <= 0):
        raise BaselineDifferenceError("frequency axis must be strictly increasing and non-negative")
    transfer_shape = member.transfer_raw_real.shape
    if len(transfer_shape) != 3 or transfer_shape[-1] != member.frequency_hz.size:
        raise BaselineDifferenceError("transfer arrays must be channel-first frequency cubes")
    for name in (
        "transfer_raw_imag",
        "transfer_aligned_real",
        "transfer_aligned_imag",
    ):
        if getattr(member, name).shape != transfer_shape:
            raise BaselineDifferenceError("transfer array shapes differ")
    if member.ir_raw.ndim != 3 or member.ir_aligned.shape != member.ir_raw.shape:
        raise BaselineDifferenceError("IR arrays must be matching channel-first cubes")


def _ordered(
    members: Sequence[BaselineDifferenceKernelMember], label: str
) -> list[BaselineDifferenceKernelMember]:
    if not members:
        raise BaselineDifferenceError(f"{label} requires at least one member")
    ordered = sorted(members, key=lambda member: member.measurement_order)
    orders = [member.measurement_order for member in ordered]
    if len(set(orders)) != len(orders):
        raise BaselineDifferenceError(f"{label} measurement orders must be unique")
    for member in ordered:
        _validate_member(member)
    return ordered


def _validate_compatible(
    baseline: Sequence[BaselineDifferenceKernelMember],
    candidate: Sequence[BaselineDifferenceKernelMember],
) -> None:
    reference = baseline[0]
    for member in [*baseline[1:], *candidate]:
        for name in _FLOAT_FIELDS[1:]:
            if getattr(member, name).shape != getattr(reference, name).shape:
                raise BaselineDifferenceError(f"{name} shape differs between members")
        if not np.array_equal(member.frequency_hz, reference.frequency_hz):
            raise BaselineDifferenceError("frequency axes differ between members")
        if not np.array_equal(member.analysis_band_mask, reference.analysis_band_mask):
            raise BaselineDifferenceError("analysis masks differ between members")


def _mean(members: Sequence[BaselineDifferenceKernelMember], name: str) -> np.ndarray:
    stacked = np.stack([getattr(member, name) for member in members], axis=0)
    return np.ascontiguousarray(np.mean(stacked, axis=0, dtype=np.float64), dtype=np.float64)


def _symmetric_relative_l2(
    difference: np.ndarray, baseline: np.ndarray, candidate: np.ndarray
) -> tuple[float | None, Literal["computed", "zero_symmetric_norm"]]:
    denominator = float(
        np.sqrt((np.sum(np.abs(baseline) ** 2) + np.sum(np.abs(candidate) ** 2)) / 2.0)
    )
    if denominator == 0.0:
        return None, "zero_symmetric_norm"
    return float(np.linalg.norm(difference.ravel()) / denominator), "computed"


def _unwrap_contiguous(wrapped: np.ndarray, valid: np.ndarray) -> np.ndarray:
    output = np.zeros(wrapped.shape, dtype=np.float64)
    flattened_wrapped = wrapped.reshape(-1, wrapped.shape[-1])
    flattened_valid = valid.reshape(-1, valid.shape[-1])
    flattened_output = output.reshape(-1, output.shape[-1])
    for row, (angles, flags) in enumerate(zip(flattened_wrapped, flattened_valid, strict=True)):
        index = 0
        while index < flags.size:
            if not flags[index]:
                index += 1
                continue
            end = index + 1
            while end < flags.size and flags[end]:
                end += 1
            flattened_output[row, index:end] = np.unwrap(angles[index:end])
            index = end
    return np.ascontiguousarray(output)


def _transfer_outputs(
    representation: str,
    baseline: np.ndarray,
    candidate: np.ndarray,
    analysis_mask: np.ndarray,
    floor: float,
) -> tuple[dict[str, np.ndarray], TransferDifferenceMetrics, int, int]:
    difference = candidate - baseline
    denominator_valid = np.abs(baseline) > floor
    phase_valid = denominator_valid & (np.abs(candidate) > floor)
    ratio = np.zeros(baseline.shape, dtype=np.complex128)
    np.divide(candidate, baseline, out=ratio, where=denominator_valid)
    baseline_db = 20.0 * np.log10(np.maximum(np.abs(baseline), np.finfo(np.float64).tiny))
    candidate_db = 20.0 * np.log10(np.maximum(np.abs(candidate), np.finfo(np.float64).tiny))
    magnitude_difference = candidate_db - baseline_db
    wrapped = np.zeros(baseline.shape, dtype=np.float64)
    wrapped[phase_valid] = np.angle(candidate[phase_valid] * np.conjugate(baseline[phase_valid]))
    unwrapped = _unwrap_contiguous(wrapped, phase_valid)
    band = np.broadcast_to(analysis_mask, baseline.shape)
    band_valid = band & denominator_valid
    band_phase = band & phase_valid
    band_count = int(np.count_nonzero(band))
    valid_count = int(np.count_nonzero(band_valid))
    phase_count = int(np.count_nonzero(band_phase))
    relative, relative_status = _symmetric_relative_l2(
        difference[band], baseline[band], candidate[band]
    )
    magnitude_band = magnitude_difference[band]
    if phase_count:
        phase_values = unwrapped[band_phase]
        phase_rms: float | None = float(np.sqrt(np.mean(phase_values**2)))
        phase_max: float | None = float(np.max(np.abs(phase_values)))
        phase_status: Literal["computed", "no_valid_bins"] = "computed"
    else:
        phase_rms = None
        phase_max = None
        phase_status = "no_valid_bins"
    metrics = TransferDifferenceMetrics(
        analysis_band_bin_count=band_count,
        analysis_band_valid_bin_count=valid_count,
        analysis_band_valid_fraction=valid_count / band_count,
        complex_additive_difference_symmetric_relative_l2=relative,
        complex_additive_difference_symmetric_relative_l2_status=relative_status,
        magnitude_difference_rms_db=float(np.sqrt(np.mean(magnitude_band**2))),
        magnitude_difference_maximum_absolute_db=float(np.max(np.abs(magnitude_band))),
        phase_difference_rms_rad=phase_rms,
        phase_difference_maximum_absolute_rad=phase_max,
        phase_difference_status=phase_status,
        phase_defined_count=phase_count,
        phase_defined_fraction=phase_count / band_count,
    )
    arrays = {
        f"{representation}_baseline_mean_transfer_real": np.ascontiguousarray(baseline.real),
        f"{representation}_baseline_mean_transfer_imag": np.ascontiguousarray(baseline.imag),
        f"{representation}_candidate_mean_transfer_real": np.ascontiguousarray(candidate.real),
        f"{representation}_candidate_mean_transfer_imag": np.ascontiguousarray(candidate.imag),
        f"{representation}_complex_additive_difference_real": np.ascontiguousarray(difference.real),
        f"{representation}_complex_additive_difference_imag": np.ascontiguousarray(difference.imag),
        f"{representation}_complex_ratio_real": np.ascontiguousarray(ratio.real),
        f"{representation}_complex_ratio_imag": np.ascontiguousarray(ratio.imag),
        f"{representation}_ratio_valid_mask": np.ascontiguousarray(denominator_valid),
        f"{representation}_baseline_magnitude_db": np.ascontiguousarray(baseline_db),
        f"{representation}_candidate_magnitude_db": np.ascontiguousarray(candidate_db),
        f"{representation}_magnitude_difference_db": np.ascontiguousarray(magnitude_difference),
        f"{representation}_wrapped_phase_difference_rad": np.ascontiguousarray(wrapped),
        f"{representation}_unwrapped_phase_difference_rad": unwrapped,
        f"{representation}_phase_valid_mask": np.ascontiguousarray(phase_valid),
    }
    return (
        arrays,
        metrics,
        int(np.count_nonzero(denominator_valid)),
        int(denominator_valid.size - np.count_nonzero(denominator_valid)),
    )


def _ir_outputs(
    representation: str, baseline: np.ndarray, candidate: np.ndarray
) -> tuple[dict[str, np.ndarray], IrDifferenceMetrics]:
    difference = candidate - baseline
    symmetric, status = _symmetric_relative_l2(difference, baseline, candidate)
    absolute = np.abs(difference).ravel()
    arrays = {
        f"baseline_mean_{representation}_ir": np.ascontiguousarray(baseline),
        f"candidate_mean_{representation}_ir": np.ascontiguousarray(candidate),
        f"{representation}_ir_difference": np.ascontiguousarray(difference),
    }
    return arrays, IrDifferenceMetrics(
        symmetric_nrmse=symmetric,
        symmetric_nrmse_status=status,
        difference_l2=float(np.linalg.norm(difference.ravel())),
        difference_absolute_peak=float(np.max(absolute)),
        difference_peak_index=int(np.argmax(absolute)),
    )


def compute_provisional_baseline_difference(
    baseline_members: Sequence[BaselineDifferenceKernelMember],
    candidate_members: Sequence[BaselineDifferenceKernelMember],
) -> ProvisionalBaselineDifferenceResult:
    """Compute deterministic raw/aligned continuous differences without decisions."""

    baseline = _ordered(baseline_members, "baseline")
    candidate = _ordered(candidate_members, "candidate")
    _validate_compatible(baseline, candidate)
    baseline_transfers: dict[str, np.ndarray] = {}
    candidate_transfers: dict[str, np.ndarray] = {}
    for representation in _TRANSFER_REPRESENTATIONS:
        baseline_transfers[representation] = _mean(baseline, f"transfer_{representation}_real") + (
            1j * _mean(baseline, f"transfer_{representation}_imag")
        )
        candidate_transfers[representation] = _mean(
            candidate, f"transfer_{representation}_real"
        ) + (1j * _mean(candidate, f"transfer_{representation}_imag"))
    maximum = max(float(np.max(np.abs(value))) for value in baseline_transfers.values())
    frequency_count = baseline[0].frequency_hz.size
    floor = max(
        maximum * np.finfo(np.float64).eps * max(1, frequency_count),
        np.finfo(np.float64).tiny,
    )
    arrays: dict[str, np.ndarray] = {
        "frequency_hz": np.ascontiguousarray(baseline[0].frequency_hz),
        "analysis_band_mask": np.ascontiguousarray(baseline[0].analysis_band_mask),
    }
    transfer_metrics: dict[Literal["raw", "aligned"], TransferDifferenceMetrics] = {}
    valid_counts: dict[Literal["raw", "aligned"], int] = {}
    invalid_counts: dict[Literal["raw", "aligned"], int] = {}
    for representation in _TRANSFER_REPRESENTATIONS:
        values, transfer_metric, valid, invalid = _transfer_outputs(
            representation,
            baseline_transfers[representation],
            candidate_transfers[representation],
            baseline[0].analysis_band_mask,
            floor,
        )
        arrays.update(values)
        transfer_metrics[representation] = transfer_metric
        valid_counts[representation] = valid
        invalid_counts[representation] = invalid
    ir_metrics: dict[str, IrDifferenceMetrics] = {}
    for representation in _TRANSFER_REPRESENTATIONS:
        values, ir_metric = _ir_outputs(
            representation,
            _mean(baseline, f"ir_{representation}"),
            _mean(candidate, f"ir_{representation}"),
        )
        arrays.update(values)
        ir_metrics[representation] = ir_metric
    return ProvisionalBaselineDifferenceResult(
        arrays=arrays,
        metrics=ProvisionalBaselineDifferenceMetrics(
            raw_transfer=transfer_metrics["raw"],
            aligned_transfer=transfer_metrics["aligned"],
            raw_ir=ir_metrics["raw"],
            aligned_ir=ir_metrics["aligned"],
        ),
        denominator_floor=float(floor),
        ratio_valid_bin_count=valid_counts,
        ratio_invalid_bin_count=invalid_counts,
    )


__all__ = [
    "BaselineDifferenceError",
    "BaselineDifferenceKernelMember",
    "ProvisionalBaselineDifferenceMetrics",
    "ProvisionalBaselineDifferenceResult",
    "compute_provisional_baseline_difference",
]
