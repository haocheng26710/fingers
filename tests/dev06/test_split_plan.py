from collections import Counter
from pathlib import Path

from acoustic_ladder.analysis.measurement_identity import derive_measurement_identities
from acoustic_ladder.analysis.split_plan import build_grouped_split_plan
from acoustic_ladder.protocol.synthetic_execution import (
    derive_synthetic_protocol_work_orders,
)
from tests.dev05.test_protocol_rehearsal import _published_plan


def _identities(tmp_path: Path):
    orders = []
    for stage in range(1, 5):
        bundle, spec, plan_store = _published_plan(tmp_path / f"stage-{stage}", stage)
        orders.extend(
            derive_synthetic_protocol_work_orders(
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id=f"stage{stage}-plan",
                execution_id=f"stage{stage}-execution",
            )
        )
    return derive_measurement_identities(orders)


def test_grouped_stage_splits_have_zero_row_and_group_leakage(tmp_path: Path) -> None:
    rows = _identities(tmp_path)
    split_plan = build_grouped_split_plan(rows)

    assert split_plan.row_count == 344
    assert split_plan.strategies == (
        "leave_one_session_out",
        "leave_one_reassembly_out",
    )
    assert len(split_plan.folds) == 24
    assert Counter(fold.strategy for fold in split_plan.folds) == {
        "leave_one_session_out": 8,
        "leave_one_reassembly_out": 16,
    }
    for fold in split_plan.folds:
        assert set(fold.train_row_ids).isdisjoint(fold.test_row_ids)
        assert set(fold.train_group_ids).isdisjoint(fold.test_group_ids)
        assert fold.train_row_ids
        assert fold.test_row_ids
        assert set(fold.train_row_ids) | set(fold.test_row_ids) == {
            row.row_id for row in rows if row.experiment_stage == fold.experiment_stage
        }

    for strategy in split_plan.strategies:
        test_counts = Counter(
            row_id
            for fold in split_plan.folds
            if fold.strategy == strategy
            for row_id in fold.test_row_ids
        )
        assert test_counts == Counter({row.row_id: 1 for row in rows})

    assert split_plan == build_grouped_split_plan(tuple(reversed(rows)))
