import hashlib
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.config.bundle import canonical_json_bytes, load_bundle
from acoustic_ladder.protocol.planning import (
    ProtocolPlanningError,
    compile_development_protocol_plan,
    load_development_protocol_plan_spec,
)

PROJECT_ROOT = Path(__file__).parents[2]
FIXED_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _bundle(stage: int):
    protocol_names = {
        1: "stage1_single_bridge.yaml",
        2: "stage2_single_node_proxy_states.yaml",
        3: "stage3_two_node_interaction.yaml",
        4: "stage4_four_node_states.yaml",
    }
    return load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols" / protocol_names[stage],
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )


def test_stage1_compiles_baseline_and_every_single_bridge_condition() -> None:
    bundle = _bundle(1)
    spec = load_development_protocol_plan_spec(
        PROJECT_ROOT / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )

    plan = compile_development_protocol_plan(bundle=bundle, spec=spec, plan_id="stage1-plan")

    assert plan.experiment_stage == 1
    assert plan.condition_count == 19
    assert len(plan.condition_matrix) == 19
    baseline = plan.condition_matrix[0]
    assert baseline.condition_role == "all_blk_baseline"
    assert baseline.active_node_count == 0
    assert {state.module_id for state in baseline.node_states.values()} == {"BLK"}
    candidates = plan.condition_matrix[1:]
    assert all(condition.active_node_count == 1 for condition in candidates)
    assert all(len(condition.node_states) == 6 for condition in plan.condition_matrix)
    assert {
        (condition.selected_nodes[0], condition.selected_modules[0]) for condition in candidates
    } == {
        (node_id, module_id)
        for module_id in ("B40", "B32", "B28")
        for node_id in ("N1", "N2", "N3", "N4", "N5", "N6")
    }
    assert plan.operator_confirmation_status == "pending"
    assert plan.protocol_execution_performed is False
    assert plan.hardware_io_performed is False
    assert plan.formal_eligible is False
    assert plan.experimental_result is False


def test_stage2_compiles_all_proxy_states_at_the_selected_node() -> None:
    bundle = _bundle(2)
    spec = load_development_protocol_plan_spec(
        PROJECT_ROOT / "tests/fixtures/protocol/stage2_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )

    plan = compile_development_protocol_plan(bundle=bundle, spec=spec, plan_id="stage2-plan")

    assert plan.experiment_stage == 2
    assert plan.condition_count == 4
    assert [condition.selected_nodes for condition in plan.condition_matrix] == [["N2"]] * 4
    assert all(condition.proxy_experiment for condition in plan.condition_matrix)
    assert all(condition.proxy_state for condition in plan.condition_matrix)
    assert all(condition.operator_confirmation_requirements for condition in plan.condition_matrix)
    assert [condition.node_states["N2"].module_id for condition in plan.condition_matrix] == [
        "BLK",
        "B28",
        "B32",
        "B40",
    ]
    for condition in plan.condition_matrix:
        assert {
            node_id: state.module_id
            for node_id, state in condition.node_states.items()
            if node_id != "N2"
        } == {node_id: "BLK" for node_id in ("N1", "N3", "N4", "N5", "N6")}


def test_stage3_normalizes_node_order_and_compiles_all_binary_labels() -> None:
    bundle = _bundle(3)
    spec = load_development_protocol_plan_spec(
        PROJECT_ROOT / "tests/fixtures/protocol/stage3_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )

    plan = compile_development_protocol_plan(bundle=bundle, spec=spec, plan_id="stage3-plan")

    assert plan.condition_count == 4
    assert [condition.condition_label for condition in plan.condition_matrix] == [
        "00",
        "10",
        "01",
        "11",
    ]
    assert [condition.selected_nodes for condition in plan.condition_matrix] == [["N2", "N5"]] * 4
    assert [
        (
            condition.node_states["N2"].discrete_label,
            condition.node_states["N5"].discrete_label,
        )
        for condition in plan.condition_matrix
    ] == [("0", "0"), ("1", "0"), ("0", "1"), ("1", "1")]
    assert all(
        condition.node_states[node_id].module_id == "BLK"
        for condition in plan.condition_matrix
        for node_id in ("N1", "N3", "N4", "N6")
    )


def test_stage4_derives_recommended_nodes_and_enumerates_sixteen_states() -> None:
    bundle = _bundle(4)
    spec = load_development_protocol_plan_spec(
        PROJECT_ROOT / "tests/fixtures/protocol/stage4_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )

    plan = compile_development_protocol_plan(bundle=bundle, spec=spec, plan_id="stage4-plan")

    assert plan.condition_count == 16
    assert [condition.condition_label for condition in plan.condition_matrix] == [
        f"{value:04b}" for value in range(16)
    ]
    assert ["N1", "N3", "N4", "N6"] == plan.condition_matrix[0].selected_nodes
    assert all(
        condition.selected_nodes == ["N1", "N3", "N4", "N6"] for condition in plan.condition_matrix
    )
    assert all(
        condition.node_states[node_id].module_id == "BLK"
        for condition in plan.condition_matrix
        for node_id in ("N2", "N5")
    )


def test_compiler_rejects_protocol_changed_after_inputs_were_loaded(tmp_path: Path) -> None:
    for relative in (
        "config/devices/device_manifest.provisional.json",
        "config/devices/device_manifest.provisional.sha256",
        "config/protocols/stage1_single_bridge.yaml",
        "config/analysis/default.yaml",
        "config/synthetic/default.yaml",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, target)
    bundle = load_bundle(
        project_root=tmp_path,
        manifest_path=tmp_path / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=tmp_path / "config/devices/device_manifest.provisional.sha256",
        audio_path=tmp_path / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=tmp_path / "config/protocols/stage1_single_bridge.yaml",
        analysis_path=tmp_path / "config/analysis/default.yaml",
        synthetic_path=tmp_path / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    spec = load_development_protocol_plan_spec(
        tmp_path / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        project_root=tmp_path,
        bundle=bundle,
    )
    protocol_path = tmp_path / "config/protocols/stage1_single_bridge.yaml"
    protocol_path.write_bytes(protocol_path.read_bytes() + b"\n")

    with pytest.raises(ProtocolPlanningError, match="source protocol bytes"):
        compile_development_protocol_plan(bundle=bundle, spec=spec, plan_id="changed-source")


def test_plan_spec_rejects_non_ascii_random_seed(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-seed.yaml"
    invalid.write_text(
        (PROJECT_ROOT / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml")
        .read_text(encoding="utf-8")
        .replace("dev0501-test-seed-v1", "开发种子"),
        encoding="utf-8",
    )

    with pytest.raises(ProtocolPlanningError, match="random_seed"):
        load_development_protocol_plan_spec(
            invalid,
            project_root=tmp_path,
            bundle=_bundle(1),
        )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("random_seed: dev0501-test-seed-v1", "random_seed: null"),
        (
            "randomization_enabled: true\nrandom_seed: dev0501-test-seed-v1",
            "randomization_enabled: false\nrandom_seed: dev0501-test-seed-v1",
        ),
        ("session_count: 2", "session_count: true"),
        ("reassemblies_per_session: 2", "reassemblies_per_session: 0"),
        ("max_planned_measurements: 1000", "max_planned_measurements: false"),
        ("plan_spec_id: stage1_development_plan", "plan_spec_id: ../escape"),
        (
            "source_protocol_reference: config/protocols/stage1_single_bridge.yaml",
            "source_protocol_reference: C:\\\\escape.yaml",
        ),
        ("experimental_result: false", "experimental_result: false\ncondition_order: []"),
        ("experimental_result: false", "experimental_result: false\nnode_states: {}"),
    ],
)
def test_plan_spec_rejects_invalid_counts_seed_paths_and_injected_authority(
    tmp_path: Path, old: str, new: str
) -> None:
    invalid = tmp_path / "invalid.yaml"
    source = (
        PROJECT_ROOT / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml"
    ).read_text(encoding="utf-8")
    invalid.write_text(source.replace(old, new), encoding="utf-8")

    with pytest.raises(ProtocolPlanningError) as failure:
        load_development_protocol_plan_spec(
            invalid,
            project_root=tmp_path,
            bundle=_bundle(1),
        )

    assert "source protocol is missing" not in str(failure.value)


@pytest.mark.parametrize(
    ("stage", "replacement"),
    [
        (1, "selected_nodes: [N2]"),
        (2, "selected_nodes: null"),
        (2, "selected_nodes: [N2, N5]"),
        (2, "selected_nodes: [UNKNOWN]"),
        (3, "selected_nodes: [N2]"),
        (3, "selected_nodes: [N2, UNKNOWN]"),
        (4, "selected_nodes: [N1, N3, N4, N6]"),
    ],
)
def test_stage_specific_selected_node_authority_is_rejected(
    tmp_path: Path, stage: int, replacement: str
) -> None:
    protocol_names = {
        1: "stage1_single_bridge.yaml",
        2: "stage2_single_node_proxy_states.yaml",
        3: "stage3_two_node_interaction.yaml",
        4: "stage4_four_node_states.yaml",
    }
    root = tmp_path / f"stage-{stage}"
    relatives = (
        "config/devices/device_manifest.provisional.json",
        "config/devices/device_manifest.provisional.sha256",
        f"config/protocols/{protocol_names[stage]}",
        "config/analysis/default.yaml",
        "config/synthetic/default.yaml",
        "tests/fixtures/audio/ess_offline_development.yaml",
        f"tests/fixtures/protocol/stage{stage}_protocol_plan.development.yaml",
    )
    for relative in relatives:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, target)
    spec_path = root / f"tests/fixtures/protocol/stage{stage}_protocol_plan.development.yaml"
    text = spec_path.read_text(encoding="utf-8")
    text = text.replace(
        next(line for line in text.splitlines() if line.startswith("selected_nodes:")),
        replacement,
    )
    spec_path.write_text(text, encoding="utf-8")
    bundle = load_bundle(
        project_root=root,
        manifest_path=root / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=root / "config/devices/device_manifest.provisional.sha256",
        audio_path=root / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=root / "config/protocols" / protocol_names[stage],
        analysis_path=root / "config/analysis/default.yaml",
        synthetic_path=root / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )

    with pytest.raises(ProtocolPlanningError):
        loaded = load_development_protocol_plan_spec(spec_path, project_root=root, bundle=bundle)
        compile_development_protocol_plan(
            bundle=bundle, spec=loaded, plan_id=f"invalid-stage-{stage}"
        )


def test_production_compiler_contains_no_current_node_or_bridge_constants() -> None:
    source = (PROJECT_ROOT / "src/acoustic_ladder/protocol/planning.py").read_text(encoding="utf-8")

    for forbidden in ("N1", "N2", "N3", "N4", "N5", "N6", "B40", "B32", "B28"):
        assert forbidden not in source


def test_compiler_rejects_caller_forged_loaded_spec_model() -> None:
    bundle = _bundle(1)
    loaded = load_development_protocol_plan_spec(
        PROJECT_ROOT / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )
    forged_model = loaded.model.model_copy(update={"session_count": 1})
    forged_normalized = canonical_json_bytes(forged_model.model_dump(mode="json"))
    forged = replace(
        loaded,
        model=forged_model,
        normalized_bytes=forged_normalized,
        normalized_sha256=hashlib.sha256(forged_normalized).hexdigest(),
    )

    with pytest.raises(ProtocolPlanningError, match="parsed model"):
        compile_development_protocol_plan(bundle=bundle, spec=forged, plan_id="forged-loaded-spec")
