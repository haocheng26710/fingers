import hashlib
from datetime import UTC, datetime
from pathlib import Path

from acoustic_ladder.audio.conditioned_virtual_capture import (
    load_conditioned_virtual_capture_scenario,
)
from acoustic_ladder.audio.excitation_persistence import publish_offline_ess_artifact
from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.protocol.synthetic_execution import (
    DevelopmentSyntheticProtocolExecutionStore,
    execute_next_synthetic_protocol_work_order,
    initialize_synthetic_protocol_execution,
    validate_synthetic_protocol_execution,
)
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore
from tests.dev05.test_protocol_rehearsal import _published_plan

PROJECT_ROOT = Path(__file__).parents[2]
FIXED_TIME = datetime(2026, 8, 20, 11, 0, tzinfo=UTC)
EXPECTED_COUNTS = {1: 152, 2: 32, 3: 32, 4: 128}


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _execute_all_stages(root: Path) -> tuple[dict[int, int], str, dict[str, bytes]]:
    counts: dict[int, int] = {}
    combined: dict[str, bytes] = {}
    for stage, expected in EXPECTED_COUNTS.items():
        stage_root = root / f"stage{stage}"
        bundle, spec, plan_store = _published_plan(stage_root, stage=stage)
        session_store = ImmutableSessionStore(
            DataRoots(
                synthetic=stage_root / "synthetic",
                real=stage_root / "real",
            )
        )
        execution_store = DevelopmentSyntheticProtocolExecutionStore(stage_root / "execution")
        scenario = load_conditioned_virtual_capture_scenario(
            PROJECT_ROOT / "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml",
            project_root=PROJECT_ROOT,
        )
        ess = publish_offline_ess_artifact(
            stage_root / "ess", "protocol-execution-ess", bundle.configs["audio"]
        )
        common = {
            "store": execution_store,
            "session_store": session_store,
            "plan_store": plan_store,
            "bundle": bundle,
            "spec": spec,
            "plan_id": f"stage{stage}-plan",
            "execution_id": f"stage{stage}-execution",
            "scenario": scenario,
            "ess_artifact_root": ess.artifact_root,
        }
        status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
        while status.execution_state != "complete":
            status = execute_next_synthetic_protocol_work_order(
                **common,
                concurrency_token=status.concurrency_token,
                actor_id="synthetic-runner",
                now=lambda: FIXED_TIME,
            )
        validated = validate_synthetic_protocol_execution(**common)
        assert validated == status
        assert status.cursor == expected
        assert status.successful_work_order_count == expected
        assert status.synthetic_capture_performed is True
        assert status.hardware_io_performed is False
        assert status.formal_protocol_execution_performed is False
        assert status.measurement_performed is False
        assert status.experimental_result is False
        assert not (stage_root / "real").exists()
        counts[stage] = status.cursor
        for prefix, tree_root in (
            ("execution", execution_store.root),
            ("synthetic", stage_root / "synthetic"),
        ):
            for relative, payload in _tree(tree_root).items():
                combined[f"stage{stage}/{prefix}/{relative}"] = payload
    aggregate = hashlib.sha256(
        canonical_json_bytes(
            [
                {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
                for path, payload in sorted(combined.items())
            ]
        )
    ).hexdigest()
    return counts, aggregate, combined


def test_all_four_stages_execute_deterministically_in_two_independent_roots(
    tmp_path: Path,
) -> None:
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    assert not left_root.exists()
    assert not right_root.exists()

    left_counts, left_aggregate, left_tree = _execute_all_stages(left_root)
    right_counts, right_aggregate, right_tree = _execute_all_stages(right_root)

    assert left_counts == right_counts == EXPECTED_COUNTS
    assert sum(left_counts.values()) == 344
    assert left_aggregate == right_aggregate
    assert left_tree == right_tree
