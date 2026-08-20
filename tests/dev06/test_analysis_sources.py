from pathlib import Path

import pytest

from acoustic_ladder.analysis.processing_adapter import process_validated_analysis_row
from acoustic_ladder.analysis.source_validation import (
    AnalysisExecutionSource,
    AnalysisSourceError,
    validate_synthetic_analysis_sources,
)
from acoustic_ladder.analysis.spec import load_development_analysis_matrix_spec
from acoustic_ladder.protocol.synthetic_execution import (
    execute_next_synthetic_protocol_work_order,
    initialize_synthetic_protocol_execution,
)
from tests.dev05.test_synthetic_protocol_execution import FIXED_TIME, _execution_setup

PROJECT_ROOT = Path(__file__).parents[2]


def test_incomplete_execution_cannot_create_analysis_source_capability(tmp_path: Path) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="analysis-incomplete")
    initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    source = AnalysisExecutionSource(**common)
    analysis_spec = load_development_analysis_matrix_spec(
        PROJECT_ROOT / "config/analysis/development_measurement_matrix.yaml",
        project_root=PROJECT_ROOT,
    )

    with pytest.raises(AnalysisSourceError, match="complete"):
        validate_synthetic_analysis_sources(sources=[source], analysis_spec=analysis_spec)

    assert not (tmp_path / "analysis").exists()


def test_completed_plan_bound_run_reuses_processing_and_qc_without_publishing_children(
    tmp_path: Path,
) -> None:
    common, _ = _execution_setup(tmp_path, stage=2, execution_id="analysis-processing")
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    while status.execution_state != "complete":
        status = execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )
    analysis_spec = load_development_analysis_matrix_spec(
        PROJECT_ROOT / "config/analysis/development_measurement_matrix.yaml",
        project_root=PROJECT_ROOT,
    )
    capability = validate_synthetic_analysis_sources(
        sources=[AnalysisExecutionSource(**common)], analysis_spec=analysis_spec
    )

    processed = process_validated_analysis_row(capability.executions[0], capability.rows[0])

    assert processed.work_order.global_planned_ordinal == 1
    assert processed.processing.arrays["frequency_hz"].ndim == 1
    assert processed.processing.arrays["ir_raw"].shape[:2] == (1, 1)
    assert processed.processing.estimated_latency_samples >= 0
    assert -1.0 <= processed.processing.latency_correlation_coefficient <= 1.0
    assert processed.qc.schema_version == "1.0.0"
    assert processed.qc_decision == "not_evaluated"
    assert processed.thresholds_applied is False
    assert not any(processed.capture.run_path.glob("processing_*"))
    assert not any(processed.capture.run_path.glob("qc_*"))
