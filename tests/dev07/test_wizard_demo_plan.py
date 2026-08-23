from pathlib import Path

from acoustic_ladder.ui.plans import load_wizard_plans

PROJECT_ROOT = Path(__file__).parents[2]


def test_demo_plan_is_a_three_condition_fake_only_projection() -> None:
    plans = load_wizard_plans(PROJECT_ROOT)

    assert plans.demo_plan.mode == "development_demo"
    assert plans.demo_plan.repeat_count == 2
    assert len(plans.demo_plan.conditions) == 3
    assert plans.demo_plan.sweep_count == 6
    assemblies = [
        tuple((node.node_id, node.module_id) for node in condition.nodes)
        for condition in plans.demo_plan.conditions
    ]
    assert all(len(assembly) == 6 for assembly in assemblies)
    assert len(set(assemblies)) == 3
    assert all(condition.stage == 1 for condition in plans.demo_plan.conditions)
