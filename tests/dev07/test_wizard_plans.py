from pathlib import Path

from acoustic_ladder.ui.plans import load_wizard_plans

PROJECT_ROOT = Path(__file__).parents[2]


def test_formal_preview_counts_are_derived_from_compiled_stage_plans() -> None:
    plans = load_wizard_plans(PROJECT_ROOT)

    assert [
        (stage.stage, stage.condition_count, stage.sweep_count)
        for stage in plans.formal_preview.stages
    ] == [(1, 19, 152), (2, 4, 32), (3, 4, 32), (4, 16, 128)]
    assert plans.formal_preview.total_assembly_confirmations == 172
    assert plans.formal_preview.total_sweeps == 344
