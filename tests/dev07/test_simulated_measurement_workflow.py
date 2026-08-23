import json
from datetime import UTC, datetime
from pathlib import Path

from acoustic_ladder.audio.pilot_capture import CancellationToken
from acoustic_ladder.ui.plans import load_wizard_plans
from acoustic_ladder.ui.simulated_workflow import (
    CALIBRATION_SHA256,
    SimulatedMeasurementRunner,
    validate_simulated_repeat_evidence,
)

PROJECT_ROOT = Path(__file__).parents[2]


def test_one_repeat_publishes_replay_validated_calibrated_processing(tmp_path: Path) -> None:
    condition = load_wizard_plans(PROJECT_ROOT).demo_plan.conditions[0]
    session_root = tmp_path / "development" / "demo" / "one-repeat"
    target = session_root / "captures" / "condition_001" / "repeat_1"
    runner = SimulatedMeasurementRunner(
        project_root=PROJECT_ROOT,
        session_root=session_root,
        now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )

    result = runner.run_repeat(
        condition=condition,
        repeat_index=1,
        target=target,
        run_id="one-repeat-c001-r1-a001",
        cancellation=CancellationToken(),
    )

    assert result.run_id == "one-repeat-c001-r1-a001"
    assert result.capture_status == "completed"
    assert result.bundle_status == "passed"
    assert result.processing_status == "passed"
    assert result.calibration_status == "applied"
    assert result.calibration_band_valid is True
    assert result.structural_status == "passed"
    assert {path.name for path in result.bundle_path.iterdir()} == {
        "captured_input.wav",
        "output_reference.wav",
        "run.json",
        "qc.json",
    }
    assert {path.name for path in result.processing_directory.iterdir()} == {
        "processing_arrays.npz",
        "processing_arrays.npz.sha256",
        "processing_receipt.json",
        "processing_receipt.sha256",
        "processing_metadata.json",
        "processing_record.json",
        "PROCESSING_COMPLETE",
    }
    receipt = json.loads(result.processing_receipt_path.read_bytes())
    assert receipt["source_run_id"] == result.run_id
    assert receipt["microphone_calibration"]["calibration_sha256"] == CALIBRATION_SHA256
    assert receipt["phase_calibrated"] is False
    assert receipt["absolute_spl_calibrated"] is False

    validated = validate_simulated_repeat_evidence(
        result.bundle_path,
        result.processing_directory,
        project_root=PROJECT_ROOT,
        expected_run_id=result.run_id,
    )
    assert validated == result
