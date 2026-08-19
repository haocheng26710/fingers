import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.config.bundle import canonical_json_bytes, load_bundle
from acoustic_ladder.protocol.planning import (
    compile_development_protocol_plan,
    load_development_protocol_plan_spec,
)

PROJECT_ROOT = Path(__file__).parents[2]
FIXED_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
PROTOCOLS = {
    1: "stage1_single_bridge.yaml",
    2: "stage2_single_node_proxy_states.yaml",
    3: "stage3_two_node_interaction.yaml",
    4: "stage4_four_node_states.yaml",
}


def _compile(stage: int):
    bundle = load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols" / PROTOCOLS[stage],
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    spec = load_development_protocol_plan_spec(
        PROJECT_ROOT / f"tests/fixtures/protocol/stage{stage}_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )
    return compile_development_protocol_plan(
        bundle=bundle, spec=spec, plan_id=f"stage{stage}-schedule"
    )


def _isolated_compile(
    root: Path,
    *,
    seed: str | None = "dev0501-test-seed-v1",
    selected_nodes: str = "[N5, N2]",
):
    relatives = (
        "config/devices/device_manifest.provisional.json",
        "config/devices/device_manifest.provisional.sha256",
        "config/protocols/stage3_two_node_interaction.yaml",
        "config/analysis/default.yaml",
        "config/synthetic/default.yaml",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "tests/fixtures/protocol/stage3_protocol_plan.development.yaml",
    )
    for relative in relatives:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, target)
    spec_path = root / "tests/fixtures/protocol/stage3_protocol_plan.development.yaml"
    text = spec_path.read_text(encoding="utf-8").replace("[N5, N2]", selected_nodes)
    if seed is None:
        text = text.replace("randomization_enabled: true", "randomization_enabled: false")
        text = text.replace("random_seed: dev0501-test-seed-v1", "random_seed: null")
    else:
        text = text.replace("dev0501-test-seed-v1", seed)
    spec_path.write_text(text, encoding="utf-8")
    bundle = load_bundle(
        project_root=root,
        manifest_path=root / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=root / "config/devices/device_manifest.provisional.sha256",
        audio_path=root / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=root / "config/protocols/stage3_two_node_interaction.yaml",
        analysis_path=root / "config/analysis/default.yaml",
        synthetic_path=root / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    spec = load_development_protocol_plan_spec(spec_path, project_root=root, bundle=bundle)
    return compile_development_protocol_plan(
        bundle=bundle, spec=spec, plan_id="deterministic-stage3"
    )


@pytest.mark.parametrize(("stage", "expected"), [(1, 152), (2, 32), (3, 32), (4, 128)])
def test_schedule_expands_complete_adjacent_repeat_blocks(stage: int, expected: int) -> None:
    plan = _compile(stage)

    assert plan.planned_measurement_count == expected
    assert len(plan.session_slots) == 2
    measurements = [
        measurement
        for session in plan.session_slots
        for reassembly in session.reassembly_slots
        for block in reassembly.condition_blocks
        for measurement in block.measurements
    ]
    assert [item.global_planned_ordinal for item in measurements] == list(range(1, expected + 1))
    for session in plan.session_slots:
        local = [
            measurement.session_local_measurement_order
            for reassembly in session.reassembly_slots
            for block in reassembly.condition_blocks
            for measurement in block.measurements
        ]
        assert local == list(range(1, len(local) + 1))
        for reassembly in session.reassembly_slots:
            assert {block.condition_id for block in reassembly.condition_blocks} == {
                condition.condition_id for condition in plan.condition_matrix
            }
            assert all(
                [measurement.continuous_repeat_index for measurement in block.measurements]
                == [1, 2]
                for block in reassembly.condition_blocks
            )


def test_randomization_is_cross_root_deterministic_and_seed_changes_only_order(
    tmp_path: Path,
) -> None:
    first = _isolated_compile(tmp_path / "a")
    second = _isolated_compile(tmp_path / "b")
    reversed_nodes = _isolated_compile(tmp_path / "reversed", selected_nodes="[N2, N5]")
    other_seed = _isolated_compile(tmp_path / "other-seed", seed="dev0501-test-seed-v2")
    canonical = _isolated_compile(tmp_path / "canonical", seed=None)

    assert canonical_json_bytes(first.model_dump(mode="json")) == canonical_json_bytes(
        second.model_dump(mode="json")
    )
    assert first.condition_matrix == reversed_nodes.condition_matrix
    assert first.session_slots == reversed_nodes.session_slots
    assert first.condition_matrix == other_seed.condition_matrix
    assert first.planned_measurement_count == other_seed.planned_measurement_count
    first_orders = [
        [block.condition_id for block in reassembly.condition_blocks]
        for session in first.session_slots
        for reassembly in session.reassembly_slots
    ]
    other_orders = [
        [block.condition_id for block in reassembly.condition_blocks]
        for session in other_seed.session_slots
        for reassembly in session.reassembly_slots
    ]
    assert any(left != right for left, right in zip(first_orders, other_orders, strict=True))
    expected_canonical = [condition.condition_id for condition in canonical.condition_matrix]
    assert all(
        [block.condition_id for block in reassembly.condition_blocks] == expected_canonical
        for session in canonical.session_slots
        for reassembly in session.reassembly_slots
    )
