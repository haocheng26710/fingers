from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.audio.condition_plan import ConditionPlanError, load_development_condition_plan
from acoustic_ladder.config.bundle import LoadedBundle, load_bundle
from acoustic_ladder.config.models import ProtocolConfig

PROJECT_ROOT = Path(__file__).parents[2]
PLAN_PATH = (
    PROJECT_ROOT / "tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml"
)
FIXED_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _stage1_bundle() -> LoadedBundle:
    return load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols/stage1_single_bridge.yaml",
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )


def test_nominal_development_plan_resolves_all_manifest_nodes() -> None:
    bundle = _stage1_bundle()
    loaded = load_development_condition_plan(
        PLAN_PATH,
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )

    baseline = loaded.binding("all_blk")
    candidate = loaded.binding("n1_b40")
    assert baseline.condition_role == "all_blk_reference"
    assert {state.module_id for state in baseline.resolved_node_states.values()} == {"BLK"}
    assert candidate.condition_role == "single_bridge_candidate"
    assert candidate.resolved_node_states["N1"].module_id == "B40"
    assert {
        node_id: state.module_id
        for node_id, state in candidate.resolved_node_states.items()
        if node_id != "N1"
    } == {f"N{index}": "BLK" for index in range(2, 7)}
    assert loaded.source_protocol_reference == "config/protocols/stage1_single_bridge.yaml"
    assert loaded.source_protocol_raw_sha256 == bundle.configs["protocol"].snapshot.original_sha256
    assert loaded.source_protocol_normalized_sha256 == (
        bundle.configs["protocol"].snapshot.normalized_sha256
    )
    assert loaded.device_manifest_sha256 == bundle.receipt.device_manifest_sha256
    assert loaded.model.protocol_execution_authorized is False
    assert loaded.model.hardware_io_authorized is False
    assert loaded.model.formal_eligible is False
    assert loaded.model.experimental_result is False


def test_plan_rejects_duplicate_selected_node_and_state(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        PLAN_PATH.read_text(encoding="utf-8")
        + "  - condition_id: duplicate_n1_b40\n"
        + "    condition_role: single_bridge_candidate\n"
        + "    selected_node: N1\n"
        + "    selected_module: B40\n",
        encoding="utf-8",
    )

    with pytest.raises(ConditionPlanError, match="duplicate selected node/state"):
        load_development_condition_plan(
            duplicate,
            project_root=tmp_path,
            bundle=_stage1_bundle(),
        )


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("selected_node: N1", "selected_node: N9", "unknown node"),
        ("selected_module: B40", "selected_module: UNKNOWN", "absent from manifest"),
        ("condition_id: n1_b40", "condition_id: all_blk", "condition IDs"),
        (
            "condition_role: all_blk_reference\n    selected_node: null\n    selected_module: null",
            "condition_role: all_blk_reference\n    selected_node: N1\n    selected_module: B40",
            "all-BLK reference",
        ),
        (
            "condition_role: single_bridge_candidate\n"
            "    selected_node: N1\n"
            "    selected_module: B40",
            "condition_role: single_bridge_candidate\n"
            "    selected_node: null\n"
            "    selected_module: null",
            "single-bridge candidate",
        ),
    ],
)
def test_plan_rejects_invalid_nodes_modules_ids_and_roles(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(PLAN_PATH.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    with pytest.raises(ConditionPlanError, match=message):
        load_development_condition_plan(path, project_root=tmp_path, bundle=_stage1_bundle())


@pytest.mark.parametrize(
    "injected",
    [
        "unexpected: true\n",
        "threshold: 0.5\n",
        "waveform: [0.0, 1.0]\n",
        "ir: [1.0]\n",
    ],
)
def test_plan_rejects_extra_threshold_and_array_authority(tmp_path: Path, injected: str) -> None:
    path = tmp_path / "extra.yaml"
    path.write_text(PLAN_PATH.read_text(encoding="utf-8") + injected, encoding="utf-8")

    with pytest.raises(ConditionPlanError):
        load_development_condition_plan(path, project_root=tmp_path, bundle=_stage1_bundle())


def test_plan_rejects_multiple_and_missing_baselines(tmp_path: Path) -> None:
    original = PLAN_PATH.read_text(encoding="utf-8")
    multiple = tmp_path / "multiple.yaml"
    multiple.write_text(
        original
        + "  - condition_id: second_baseline\n"
        + "    condition_role: all_blk_reference\n"
        + "    selected_node: null\n"
        + "    selected_module: null\n",
        encoding="utf-8",
    )
    missing = tmp_path / "missing.yaml"
    missing.write_text(
        original.replace("all_blk_reference", "single_bridge_candidate", 1), encoding="utf-8"
    )

    with pytest.raises(ConditionPlanError):
        load_development_condition_plan(multiple, project_root=tmp_path, bundle=_stage1_bundle())
    with pytest.raises(ConditionPlanError):
        load_development_condition_plan(missing, project_root=tmp_path, bundle=_stage1_bundle())


def test_plan_rejects_source_path_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(PLAN_PATH.read_bytes())
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ConditionPlanError, match="outside project root"):
        load_development_condition_plan(outside, project_root=root, bundle=_stage1_bundle())


@pytest.mark.parametrize("protocol_change", ["stage", "boundary"])
def test_plan_rejects_non_stage1_or_wrong_boundary(protocol_change: str) -> None:
    bundle = _stage1_bundle()
    loaded = bundle.configs["protocol"]
    assert isinstance(loaded.model, ProtocolConfig)
    if protocol_change == "stage":
        protocol = loaded.model.model_copy(update={"experiment_stage": 2})
    else:
        boundary = loaded.model.boundary_conditions.model_copy(update={"tx_far": "speaker"})
        protocol = loaded.model.model_copy(update={"boundary_conditions": boundary})
    mutated = replace(
        bundle, configs={**bundle.configs, "protocol": replace(loaded, model=protocol)}
    )

    with pytest.raises(ConditionPlanError, match="Stage 1 draft boundary"):
        load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=mutated)
