from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from acoustic_ladder.analysis.research import (
    RESEARCH_OUTPUT_NAMES,
    ResearchDataset,
    ResearchFold,
    ResearchObservation,
    ResearchState,
    compute_stage1_effects,
    compute_stage2_proxy_analysis,
    compute_stage3_interactions,
    compute_stage4_classification,
    run_research_analysis,
)
from acoustic_ladder.cli import main
from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.storage.io import StorageError


def _row(
    row_id: str,
    value_state: ResearchState,
    *,
    baseline: bool = False,
) -> ResearchObservation:
    return ResearchObservation(
        row_id=row_id,
        experiment_stage=1,
        baseline_group_id="group_1",
        session_group_id="session_1",
        reassembly_group_id="reassembly_1",
        condition_label="BLK" if baseline else "candidate",
        selected_node_ids=() if baseline else ("node_alpha",),
        node_states=(value_state,),
        baseline_reference_row_ids=("blk_1", "blk_2"),
    )


def test_stage1_reports_hand_calculated_baseline_delta() -> None:
    blocked = ResearchState("node_alpha", "blocked", "BLK", "0", None, False)
    active = ResearchState("node_alpha", "bridge_x", "BRIDGE", "1", None, False)
    rows = (
        _row("blk_1", blocked, baseline=True),
        _row("blk_2", blocked, baseline=True),
        _row("active_1", active),
        _row("active_2", active),
    )

    effects = compute_stage1_effects(
        rows,
        ((1.0,), (3.0,), (5.0,), (7.0,)),
        ("feature_a",),
    )

    assert len(effects) == 1
    assert effects[0].active_node_id == "node_alpha"
    assert effects[0].bridge_state_id == "bridge_x"
    assert effects[0].sample_count == 2
    assert effects[0].mean == 6.0
    assert effects[0].standard_deviation == 1.0
    assert effects[0].mean_baseline_delta == 4.0


def test_stage2_uses_only_explicit_continuous_labels_for_trend() -> None:
    low = ResearchState("node_alpha", "low", "PROXY", None, 1.0, True)
    high = ResearchState("node_alpha", "high", "PROXY", None, 2.0, True)
    rows = tuple(
        ResearchObservation(
            row_id=f"proxy_{index}",
            experiment_stage=2,
            baseline_group_id="group_1",
            session_group_id="session_1",
            reassembly_group_id="reassembly_1",
            condition_label=label,
            selected_node_ids=("node_alpha",),
            node_states=(state,),
            baseline_reference_row_ids=("unused",),
        )
        for index, (label, state) in enumerate(
            (("light", low), ("light", low), ("heavy", high), ("heavy", high)), start=1
        )
    )

    trend = compute_stage2_proxy_analysis(rows, ((2.0,), (2.0,), (4.0,), (4.0,)), ("f",))

    assert len(trend) == 1
    assert trend[0].trend_status == "computed"
    assert trend[0].continuous_label_field == "node_states.node_alpha.continuous_value"
    assert trend[0].slope == 2.0
    assert trend[0].r_squared == 1.0


def test_stage2_does_not_guess_continuous_values_from_condition_names() -> None:
    state = ResearchState("node_alpha", "level_10", "PROXY", None, None, True)
    rows = tuple(
        ResearchObservation(
            row_id=f"proxy_{index}",
            experiment_stage=2,
            baseline_group_id="group_1",
            session_group_id="session_1",
            reassembly_group_id="reassembly_1",
            condition_label=label,
            selected_node_ids=("node_alpha",),
            node_states=(state,),
            baseline_reference_row_ids=("unused",),
        )
        for index, label in enumerate(("level_10", "level_20"), start=1)
    )

    grouped = compute_stage2_proxy_analysis(rows, ((2.0,), (4.0,)), ("f",))

    assert [item.trend_status for item in grouped] == [
        "not_computed_missing_continuous_label",
        "not_computed_missing_continuous_label",
    ]
    assert [item.proxy_state_label for item in grouped] == ["level_10", "level_20"]


def test_stage3_reports_hand_calculated_interaction_residual() -> None:
    def interaction_row(row_id: str, left: str, right: str) -> ResearchObservation:
        states = (
            ResearchState("left", left, "BLK" if left == "0" else "BRIDGE", left, None, False),
            ResearchState("right", right, "BLK" if right == "0" else "BRIDGE", right, None, False),
        )
        return ResearchObservation(
            row_id=row_id,
            experiment_stage=3,
            baseline_group_id="group_3",
            session_group_id="session_3",
            reassembly_group_id="reassembly_3",
            condition_label=left + right,
            selected_node_ids=("left", "right"),
            node_states=states,
            baseline_reference_row_ids=("s3_00",),
        )

    rows = tuple(
        interaction_row(row_id, left, right)
        for row_id, left, right in (
            ("s3_00", "0", "0"),
            ("s3_10", "1", "0"),
            ("s3_01", "0", "1"),
            ("s3_11", "1", "1"),
        )
    )

    interactions = compute_stage3_interactions(rows, ((10.0,), (13.0,), (15.0,), (20.0,)), ("f",))

    assert len(interactions) == 1
    assert interactions[0].node_a_delta == 3.0
    assert interactions[0].node_b_delta == 5.0
    assert interactions[0].observed_pair_delta == 10.0
    assert interactions[0].additive_expected_delta == 8.0
    assert interactions[0].interaction_residual == 2.0
    assert interactions[0].sample_count == 1


def test_stage4_uses_train_only_standardization_and_covers_fold_predictions() -> None:
    node_order = ("n1", "n2", "n3", "n4")
    classes = ("0000", "0001", "0010", "0011")
    rows: list[ResearchObservation] = []
    matrix: list[tuple[float, ...]] = []
    for group, offset in (("train", 0.0), ("test", 100.0)):
        for class_index, label in enumerate(classes):
            states = tuple(
                ResearchState(node, bit, "BLK" if bit == "0" else "BRIDGE", bit, None, False)
                for node, bit in zip(node_order, label, strict=True)
            )
            rows.append(
                ResearchObservation(
                    row_id=f"{group}_{label}",
                    experiment_stage=4,
                    baseline_group_id=group,
                    session_group_id=group,
                    reassembly_group_id=group,
                    condition_label=label,
                    selected_node_ids=node_order,
                    node_states=states,
                    baseline_reference_row_ids=(f"{group}_0000",),
                )
            )
            matrix.append(tuple(offset + float(value == class_index) for value in range(4)))
    train_ids = tuple(f"train_{label}" for label in classes)
    test_ids = tuple(f"test_{label}" for label in classes)
    folds = (
        ResearchFold("stage_4_session_fold_a", "leave_one_session_out", test_ids, train_ids),
        ResearchFold("stage_4_session_fold_b", "leave_one_session_out", train_ids, test_ids),
        ResearchFold("stage_4_reassembly_fold_a", "leave_one_reassembly_out", test_ids, train_ids),
        ResearchFold("stage_4_reassembly_fold_b", "leave_one_reassembly_out", train_ids, test_ids),
    )

    result = compute_stage4_classification(rows, matrix, ("f1", "f2", "f3", "f4"), folds, seed=7)

    session_fold = next(fold for fold in result.folds if fold.fold_id == "stage_4_session_fold_b")
    assert session_fold.training_feature_mean == (0.25, 0.25, 0.25, 0.25)
    assert session_fold.training_feature_scale == (
        0.4330127018922193,
        0.4330127018922193,
        0.4330127018922193,
        0.4330127018922193,
    )
    assert {item.row_id for item in result.predictions} == {
        f"{group}_{label}" for group in ("train", "test") for label in classes
    }
    assert len(result.predictions) == 16


def _research_dataset() -> ResearchDataset:
    blocked = ResearchState("n1", "blocked", "BLK", "0", None, False)
    active = ResearchState("n1", "active", "BRIDGE", "1", None, False)
    rows: list[ResearchObservation] = [
        ResearchObservation("s1_blk_1", 1, "s1", "s1", "s1", "BLK", (), (blocked,), ("s1_blk_2",)),
        ResearchObservation("s1_blk_2", 1, "s1", "s1", "s1", "BLK", (), (blocked,), ("s1_blk_1",)),
        ResearchObservation(
            "s1_active", 1, "s1", "s1", "s1", "active", ("n1",), (active,), ("s1_blk_1", "s1_blk_2")
        ),
    ]
    matrix: list[tuple[float, ...]] = [
        (1.0, 0.0, 0.0, 0.0),
        (3.0, 0.0, 0.0, 0.0),
        (5.0, 0.0, 0.0, 0.0),
    ]
    for index, value in enumerate((1.0, 2.0), start=1):
        proxy = ResearchState("n1", f"proxy_{index}", "PROXY", None, value, True)
        rows.append(
            ResearchObservation(
                f"s2_{index}", 2, "s2", "s2", "s2", f"proxy_{index}", ("n1",), (proxy,), ("s2_1",)
            )
        )
        matrix.append((value, value * 2.0, 0.0, 0.0))
    for label, value in (("00", 10.0), ("10", 13.0), ("01", 15.0), ("11", 20.0)):
        states = tuple(
            ResearchState(node, bit, "BLK" if bit == "0" else "BRIDGE", bit, None, False)
            for node, bit in zip(("n1", "n2"), label, strict=True)
        )
        rows.append(
            ResearchObservation(
                f"s3_{label}", 3, "s3", "s3", "s3", label, ("n1", "n2"), states, ("s3_00",)
            )
        )
        matrix.append((value, 0.0, 0.0, 0.0))
    node_order = ("n1", "n2", "n3", "n4")
    classes = ("0000", "0001", "0010", "0011")
    for group in ("a", "b"):
        for class_index, label in enumerate(classes):
            states = tuple(
                ResearchState(node, bit, "BLK" if bit == "0" else "BRIDGE", bit, None, False)
                for node, bit in zip(node_order, label, strict=True)
            )
            rows.append(
                ResearchObservation(
                    f"s4_{group}_{label}",
                    4,
                    f"s4_{group}",
                    f"s4_{group}",
                    f"s4_{group}",
                    label,
                    node_order,
                    states,
                    (f"s4_{group}_0000",),
                )
            )
            matrix.append(tuple(float(value == class_index) for value in range(4)))
    group_a = tuple(f"s4_a_{label}" for label in classes)
    group_b = tuple(f"s4_b_{label}" for label in classes)
    folds = (
        ResearchFold("stage_4_session_fold_a", "leave_one_session_out", group_b, group_a),
        ResearchFold("stage_4_session_fold_b", "leave_one_session_out", group_a, group_b),
        ResearchFold("stage_4_reassembly_fold_a", "leave_one_reassembly_out", group_b, group_a),
        ResearchFold("stage_4_reassembly_fold_b", "leave_one_reassembly_out", group_a, group_b),
    )
    return ResearchDataset(
        analysis_id="tiny_analysis",
        analysis_receipt_sha256="a" * 64,
        feature_schema_version="1.0.0",
        feature_ids=("f1", "f2", "f3", "f4"),
        observations=tuple(rows),
        feature_matrix=tuple(matrix),
        folds=folds,
        input_file_sha256={"analysis_receipt.json": "a" * 64},
    )


def test_same_input_and_seed_publish_identical_structured_results(tmp_path: Path) -> None:
    first = run_research_analysis(_research_dataset(), tmp_path / "first", seed=17)
    second = run_research_analysis(_research_dataset(), tmp_path / "second", seed=17)

    assert {path.name for path in first.output_path.iterdir()} == RESEARCH_OUTPUT_NAMES
    assert first.summary == second.summary
    assert {path.name: path.read_bytes() for path in first.output_path.iterdir()} == {
        path.name: path.read_bytes() for path in second.output_path.iterdir()
    }
    with pytest.raises(StorageError, match="already exists"):
        run_research_analysis(_research_dataset(), first.output_path, seed=17)


def _write_small_analysis_envelope(path: Path, dataset: ResearchDataset) -> None:
    path.mkdir()
    rows = {
        "row_count": len(dataset.observations),
        "rows": [
            {
                "row_id": row.row_id,
                "experiment_stage": row.experiment_stage,
                "baseline_group_id": row.baseline_group_id,
                "session_group_id": row.session_group_id,
                "reassembly_group_id": row.reassembly_group_id,
                "condition_label": row.condition_label,
                "selected_node_ids": list(row.selected_node_ids),
                "node_states": {state.node_id: state.__dict__ for state in row.node_states},
                "baseline_reference_row_ids": list(row.baseline_reference_row_ids),
            }
            for row in dataset.observations
        ],
    }
    schema = {
        "schema_version": dataset.feature_schema_version,
        "feature_count": len(dataset.feature_ids),
        "columns": [
            {"ordinal": index, "feature_id": feature_id}
            for index, feature_id in enumerate(dataset.feature_ids, start=1)
        ],
    }
    split = {
        "row_count": len(dataset.observations),
        "folds": [fold.__dict__ for fold in dataset.folds],
    }
    source = {
        "analysis_id": dataset.analysis_id,
        "data_origin": "synthetic",
        "run_mode": "development",
    }
    core = {
        "analysis_source_binding.json": canonical_json_bytes(source),
        "measurement_row_index.json": canonical_json_bytes(rows),
        "feature_schema.json": canonical_json_bytes(schema),
        "split_plan.json": canonical_json_bytes(split),
    }
    for name, content in core.items():
        (path / name).write_bytes(content)
    np.savez_compressed(
        path / "measurement_matrix.npz", feature_matrix=np.asarray(dataset.feature_matrix)
    )
    digests = {name: hashlib.sha256((path / name).read_bytes()).hexdigest() for name in core}
    digests["measurement_matrix.npz"] = hashlib.sha256(
        (path / "measurement_matrix.npz").read_bytes()
    ).hexdigest()
    receipt = {
        "analysis_id": dataset.analysis_id,
        "analysis_source_binding_sha256": digests["analysis_source_binding.json"],
        "measurement_row_index_sha256": digests["measurement_row_index.json"],
        "feature_schema_sha256": digests["feature_schema.json"],
        "split_plan_sha256": digests["split_plan.json"],
        "measurement_matrix_npz_sha256": digests["measurement_matrix.npz"],
        "measurement_row_count": len(dataset.observations),
        "feature_count": len(dataset.feature_ids),
        "split_fold_count": len(dataset.folds),
        "data_origin": "synthetic",
        "run_mode": "development",
        "experimental_result": False,
    }
    (path / "analysis_receipt.json").write_bytes(canonical_json_bytes(receipt))
    for name in core:
        digest = digests[name]
        (path / name.replace(".json", ".sha256")).write_text(
            f"{digest}  {name}\n", encoding="ascii"
        )
    (path / "measurement_matrix.npz.sha256").write_text(
        f"{digests['measurement_matrix.npz']}  measurement_matrix.npz\n", encoding="ascii"
    )
    receipt_digest = hashlib.sha256((path / "analysis_receipt.json").read_bytes()).hexdigest()
    (path / "analysis_receipt.sha256").write_text(
        f"{receipt_digest}  analysis_receipt.json\n", encoding="ascii"
    )
    (path / "analysis_metadata.json").write_bytes(
        canonical_json_bytes(
            {
                "analysis_id": dataset.analysis_id,
                "data_origin": "synthetic",
                "run_mode": "development",
            }
        )
    )
    (path / "analysis_record.json").write_bytes(
        canonical_json_bytes({"analysis_id": dataset.analysis_id, "immutable_status": "complete"})
    )
    (path / "ANALYSIS_COMPLETE").write_bytes(b"complete\n")


def test_research_analysis_cli_small_smoke(tmp_path: Path, capsys: object) -> None:
    input_path = tmp_path / "analysis"
    output_path = tmp_path / "research"
    _write_small_analysis_envelope(input_path, _research_dataset())

    main(
        [
            "research-analyze",
            "--analysis-dir",
            str(input_path),
            "--output-dir",
            str(output_path),
            "--random-seed",
            "17",
        ]
    )

    assert {path.name for path in output_path.iterdir()} == RESEARCH_OUTPUT_NAMES
    summary = json.loads((output_path / "research_summary.json").read_text(encoding="utf-8"))
    assert summary["synthetic"] is True
    assert summary["experimental_result"] is False
