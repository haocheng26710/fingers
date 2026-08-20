"""Central plan-bound adapter for existing ESS processing and provisional QC kernels."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from acoustic_ladder.audio.ess_processing import EssProcessingResult, process_ess_waveforms
from acoustic_ladder.audio.excitation_persistence import (
    WAV_NAME,
    decode_ieee_float32_wav,
    validate_offline_ess_artifact,
)
from acoustic_ladder.audio.provisional_qc import (
    QcProcessingEvidence,
    compute_provisional_qc_metrics,
)
from acoustic_ladder.audio.provisional_qc_models import ProvisionalQcMetrics
from acoustic_ladder.audio.virtual_capture_persistence import INPUT_WAV, OUTPUT_WAV
from acoustic_ladder.protocol.plan_bound_capture import PublishedPlanBoundSyntheticCapture
from acoustic_ladder.protocol.synthetic_execution_models import SyntheticProtocolWorkOrder

from .source_validation import ValidatedAnalysisExecution, ValidatedAnalysisRowSource


class AnalysisProcessingError(ValueError):
    """Raised when one validated source row cannot be processed without exclusion."""


@dataclass(frozen=True)
class ProcessedAnalysisRow:
    work_order: SyntheticProtocolWorkOrder
    capture: PublishedPlanBoundSyntheticCapture
    processing: EssProcessingResult
    qc: ProvisionalQcMetrics
    sample_rate_hz: int
    qc_decision: str = "not_evaluated"
    thresholds_applied: bool = False


def process_validated_analysis_row(
    execution: ValidatedAnalysisExecution, row: ValidatedAnalysisRowSource
) -> ProcessedAnalysisRow:
    """Run existing pure kernels for one row already bound to a validated capability."""

    if row not in execution.rows:
        raise AnalysisProcessingError("row is foreign to the validated execution capability")
    source = execution.source
    spec = source.bundle.configs.get("analysis")
    if spec is None:
        raise AnalysisProcessingError("validated source omitted analysis config")
    expected = execution.rows[row.work_order.global_planned_ordinal - 1]
    if expected.work_order != row.work_order or expected.capture != row.capture:
        raise AnalysisProcessingError("row ordinal differs from the validated work-order order")
    try:
        ess = validate_offline_ess_artifact(
            source.ess_artifact_root, source.bundle.configs["audio"]
        )
        output, output_rate = decode_ieee_float32_wav(
            (row.capture.run_path / OUTPUT_WAV).read_bytes()
        )
        captured, input_rate = decode_ieee_float32_wav(
            (row.capture.run_path / INPUT_WAV).read_bytes()
        )
        source_wav, source_rate = decode_ieee_float32_wav(
            (ess.artifact_root / WAV_NAME).read_bytes()
        )
        if output_rate != input_rate or output_rate != source_rate:
            raise AnalysisProcessingError("source sample rates disagree")
        if not np.array_equal(output[:, : source_wav.shape[1]], source_wav):
            raise AnalysisProcessingError("output reference does not begin with validated ESS")
        timing = ess.metadata.timing
        ess_spec = ess.metadata.spec
        analysis_spec = execution.source.bundle.configs["analysis"].model
        from acoustic_ladder.config.models import AnalysisConfig

        if not isinstance(analysis_spec, AnalysisConfig):
            raise AnalysisProcessingError("source analysis config has the wrong type")
        processing = process_ess_waveforms(
            output,
            captured,
            sample_rate_hz=source_rate,
            sweep_sample_count=timing.sweep_sample_count,
            pre_silence_sample_count=timing.pre_silence_sample_count,
            start_frequency_hz=ess_spec.start_frequency_hz,
            end_frequency_hz=ess_spec.end_frequency_hz,
            analysis_lower_hz=analysis_spec.analysis_band.lower_hz,
            analysis_upper_hz=analysis_spec.analysis_band.upper_hz,
            smoothing_enabled=analysis_spec.smoothing.enabled,
        )
        evidence = QcProcessingEvidence(
            sample_rate_hz=source_rate,
            sweep_sample_count=timing.sweep_sample_count,
            pre_silence_sample_count=timing.pre_silence_sample_count,
            transfer_fft_length=processing.transfer_fft_length,
            estimated_latency_samples=processing.estimated_latency_samples,
            estimated_latency_seconds=processing.estimated_latency_samples / source_rate,
            matched_correlation_signed=processing.latency_correlation_coefficient,
            matched_correlation_absolute=abs(processing.latency_correlation_coefficient),
            ir_dominant_peak_index=processing.ir_raw_dominant_peak_index,
            ir_dominant_peak_value=processing.ir_raw_dominant_peak_value,
            reference_peak_index=processing.reference_peak_index,
        )
        qc = compute_provisional_qc_metrics(output, captured, processing.arrays, evidence)
    except AnalysisProcessingError:
        raise
    except Exception as exc:
        raise AnalysisProcessingError(
            f"analysis row {row.work_order.global_planned_ordinal} processing failed: {exc}"
        ) from exc
    return ProcessedAnalysisRow(
        work_order=row.work_order,
        capture=row.capture,
        processing=processing,
        qc=qc,
        sample_rate_hz=source_rate,
    )


__all__ = [
    "AnalysisProcessingError",
    "ProcessedAnalysisRow",
    "process_validated_analysis_row",
]
