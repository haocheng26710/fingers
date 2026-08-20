from collections import Counter
from pathlib import Path

from acoustic_ladder.analysis.measurement_identity import (
    build_baseline_reference_map,
    derive_measurement_identities,
)
from acoustic_ladder.protocol.synthetic_execution import (
    derive_synthetic_protocol_work_orders,
)
from tests.dev05.test_protocol_rehearsal import _published_plan


def _all_stage_orders(tmp_path: Path):
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
    return tuple(orders)


def test_plan_derived_measurement_identities_and_leave_one_repeat_out_baselines(
    tmp_path: Path,
) -> None:
    identities = derive_measurement_identities(_all_stage_orders(tmp_path))

    assert len(identities) == 344
    assert Counter(row.experiment_stage for row in identities) == {
        1: 152,
        2: 32,
        3: 32,
        4: 128,
    }
    assert len({row.row_id for row in identities}) == 344
    assert all(row.node_states for row in identities)
    assert all(
        row.selected_state_ids
        == tuple(row.node_states[node].state_id for node in row.selected_node_ids)
        for row in identities
    )
    assert all(
        row.selected_module_ids
        == tuple(row.node_states[node].module_id for node in row.selected_node_ids)
        for row in identities
    )
    assert all(row.repeat_kind == "continuous_repeat" for row in identities)
    assert all(row.proxy_state for row in identities if row.experiment_stage == 2)
    assert not any(row.proxy_state for row in identities if row.experiment_stage != 2)

    references = build_baseline_reference_map(identities)
    by_id = {row.row_id: row for row in identities}
    assert set(references) == set(by_id)
    for candidate_id, baseline_ids in references.items():
        candidate = by_id[candidate_id]
        assert candidate_id not in baseline_ids
        assert len(baseline_ids) == (1 if candidate.is_all_blk else 2)
        for baseline_id in baseline_ids:
            baseline = by_id[baseline_id]
            assert baseline.is_all_blk
            assert baseline.experiment_stage == candidate.experiment_stage
            assert baseline.session_id == candidate.session_id
            assert baseline.reassembly_id == candidate.reassembly_id
            assert baseline.baseline_group_id == candidate.baseline_group_id

    reversed_references = build_baseline_reference_map(tuple(reversed(identities)))
    assert references == reversed_references
