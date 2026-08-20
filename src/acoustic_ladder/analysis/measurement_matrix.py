"""Canonical row processing and full-array measurement-matrix assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.baseline_difference import BaselineDifferenceKernelMember

from .feature_kernel import AnalysisRowFeatureResult, compute_analysis_row_features
from .measurement_identity import (
    MeasurementIdentity,
    build_baseline_reference_map,
    derive_measurement_identities,
)
from .processing_adapter import ProcessedAnalysisRow, process_validated_analysis_row
from .source_validation import ValidatedSyntheticAnalysisSources


@dataclass(frozen=True)
class AssembledMeasurementArrays:
    row_ids: tuple[str, ...]
    baseline_reference_row_ids: dict[str, tuple[str, ...]]
    arrays: dict[str, NDArray[np.generic]]
    row_results: dict[str, AnalysisRowFeatureResult]


@dataclass(frozen=True)
class ComputedMeasurementMatrix:
    sources: ValidatedSyntheticAnalysisSources
    identities: tuple[MeasurementIdentity, ...]
    processed_rows: tuple[ProcessedAnalysisRow, ...]
    assembled: AssembledMeasurementArrays


def _member(processed: ProcessedAnalysisRow) -> BaselineDifferenceKernelMember:
    arrays = processed.processing.arrays
    return BaselineDifferenceKernelMember(
        measurement_order=processed.work_order.global_planned_ordinal,
        frequency_hz=arrays["frequency_hz"],
        analysis_band_mask=arrays["analysis_band_mask"],
        transfer_raw_real=arrays["transfer_raw_real"],
        transfer_raw_imag=arrays["transfer_raw_imag"],
        transfer_aligned_real=arrays["transfer_aligned_real"],
        transfer_aligned_imag=arrays["transfer_aligned_imag"],
        ir_raw=arrays["ir_raw"],
        ir_aligned=arrays["ir_aligned"],
    )


def assemble_measurement_arrays(
    *,
    rows: Sequence[MeasurementIdentity],
    members: Mapping[str, BaselineDifferenceKernelMember],
) -> AssembledMeasurementArrays:
    """Assemble every candidate, same-group reference and fixed feature in row order."""

    canonical_rows = tuple(sorted(rows, key=lambda row: row.row_id))
    row_ids = tuple(row.row_id for row in canonical_rows)
    if set(members) != set(row_ids):
        raise ValueError("kernel member identities differ from measurement row identities")
    references = build_baseline_reference_map(canonical_rows)
    results: dict[str, AnalysisRowFeatureResult] = {}
    for row in canonical_rows:
        results[row.row_id] = compute_analysis_row_features(
            baseline_members=[members[row_id] for row_id in references[row.row_id]],
            candidate=members[row.row_id],
        )
    array_names = tuple(sorted(next(iter(results.values())).arrays))
    if any(tuple(sorted(result.arrays)) != array_names for result in results.values()):
        raise ValueError("row feature array schemas differ")
    arrays = {
        name: np.ascontiguousarray(
            np.stack([results[row_id].arrays[name] for row_id in row_ids], axis=0)
        )
        for name in array_names
    }
    arrays["feature_matrix"] = np.ascontiguousarray(
        np.stack([results[row_id].feature_vector for row_id in row_ids], axis=0),
        dtype=np.float64,
    )
    return AssembledMeasurementArrays(
        row_ids=row_ids,
        baseline_reference_row_ids=references,
        arrays=dict(sorted(arrays.items())),
        row_results=results,
    )


def compute_measurement_matrix(
    sources: ValidatedSyntheticAnalysisSources,
) -> ComputedMeasurementMatrix:
    """Process each validated capability row once and assemble the canonical matrix."""

    if {execution.stage for execution in sources.executions} != {1, 2, 3, 4}:
        raise ValueError("measurement matrix requires exactly one execution for every Stage 1-4")
    processed: list[ProcessedAnalysisRow] = []
    for execution in sources.executions:
        processed.extend(process_validated_analysis_row(execution, row) for row in execution.rows)
    identities = derive_measurement_identities([row.work_order for row in processed])
    processed_by_digest = {row.work_order.work_order_sha256: row for row in processed}
    if len(processed_by_digest) != len(processed):
        raise ValueError("processed source work-order identities are not unique")
    members = {
        identity.row_id: _member(processed_by_digest[identity.work_order_sha256])
        for identity in identities
    }
    assembled = assemble_measurement_arrays(rows=identities, members=members)
    return ComputedMeasurementMatrix(
        sources=sources,
        identities=identities,
        processed_rows=tuple(processed),
        assembled=assembled,
    )


__all__ = [
    "AssembledMeasurementArrays",
    "ComputedMeasurementMatrix",
    "assemble_measurement_arrays",
    "compute_measurement_matrix",
]
