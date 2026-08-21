"""Deterministic, synthetic-only Stage 1-4 research analysis."""

from __future__ import annotations

import csv
import io
import json
import os
import platform
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

import numpy as np
import sklearn
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.storage.io import StorageError, sha256_bytes

from .persistence import COMPLETE_BYTES, ENVELOPE_NAMES

RESEARCH_OUTPUT_NAMES = frozenset(
    {
        "research_summary.json",
        "stage1_effects.csv",
        "stage2_proxy_analysis.csv",
        "stage3_interactions.csv",
        "stage4_predictions.csv",
        "research_receipt.json",
    }
)


@dataclass(frozen=True)
class ResearchState:
    node_id: str
    state_id: str
    module_id: str
    discrete_label: str | None
    continuous_value: float | None
    proxy_state: bool


@dataclass(frozen=True)
class ResearchObservation:
    row_id: str
    experiment_stage: int
    baseline_group_id: str
    session_group_id: str
    reassembly_group_id: str
    condition_label: str
    selected_node_ids: tuple[str, ...]
    node_states: tuple[ResearchState, ...]
    baseline_reference_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class Stage1Effect:
    active_node_id: str
    bridge_state_id: str
    feature_id: str
    sample_count: int
    mean: float
    standard_deviation: float
    mean_baseline_delta: float


@dataclass(frozen=True)
class Stage2ProxyResult:
    feature_id: str
    trend_status: str
    sample_count: int
    proxy_state_label: str | None
    mean: float | None
    standard_deviation: float | None
    continuous_label_field: str | None
    slope: float | None
    r_squared: float | None


@dataclass(frozen=True)
class Stage3Interaction:
    node_a_id: str
    node_b_id: str
    feature_id: str
    node_a_delta: float
    node_b_delta: float
    observed_pair_delta: float
    additive_expected_delta: float
    interaction_residual: float
    sample_count: int


@dataclass(frozen=True)
class ResearchFold:
    fold_id: str
    strategy: str
    train_row_ids: tuple[str, ...]
    test_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class Stage4Prediction:
    fold_id: str
    strategy: str
    row_id: str
    true_class: str
    predicted_class: str


@dataclass(frozen=True)
class Stage4FoldResult:
    fold_id: str
    strategy: str
    accuracy: float
    balanced_accuracy: float
    macro_f1: float
    class_order: tuple[str, ...]
    confusion_matrix: tuple[tuple[int, ...], ...]
    training_feature_mean: tuple[float, ...]
    training_feature_scale: tuple[float, ...]


@dataclass(frozen=True)
class Stage4Classification:
    folds: tuple[Stage4FoldResult, ...]
    predictions: tuple[Stage4Prediction, ...]


@dataclass(frozen=True)
class ResearchDataset:
    analysis_id: str
    analysis_receipt_sha256: str
    feature_schema_version: str
    feature_ids: tuple[str, ...]
    observations: tuple[ResearchObservation, ...]
    feature_matrix: tuple[tuple[float, ...], ...]
    folds: tuple[ResearchFold, ...]
    input_file_sha256: dict[str, str]


@dataclass(frozen=True)
class PublishedResearchAnalysis:
    output_path: Path
    summary: dict[str, Any]
    receipt: dict[str, Any]


def compute_stage1_effects(
    rows: Sequence[ResearchObservation],
    feature_matrix: Sequence[Sequence[float]],
    feature_ids: Sequence[str],
) -> tuple[Stage1Effect, ...]:
    """Compute descriptive single-node effects against row-bound BLK references."""

    if len(rows) != len(feature_matrix):
        raise ValueError("row count differs from feature matrix")
    values_by_id = {row.row_id: tuple(feature_matrix[index]) for index, row in enumerate(rows)}
    grouped: dict[tuple[str, str, str], list[tuple[float, float]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if row.experiment_stage != 1 or len(row.selected_node_ids) != 1:
            continue
        node_id = row.selected_node_ids[0]
        state = next(state for state in row.node_states if state.node_id == node_id)
        if state.module_id == "BLK":
            continue
        references = [values_by_id[row_id] for row_id in row.baseline_reference_row_ids]
        if not references:
            raise ValueError(f"row {row.row_id} has no BLK baseline references")
        for feature_index, feature_id in enumerate(feature_ids):
            value = float(feature_matrix[index][feature_index])
            baseline = fmean(reference[feature_index] for reference in references)
            grouped[(node_id, state.state_id, feature_id)].append((value, value - baseline))
    return tuple(
        Stage1Effect(
            active_node_id=node_id,
            bridge_state_id=state_id,
            feature_id=feature_id,
            sample_count=len(values),
            mean=fmean(value for value, _ in values),
            standard_deviation=pstdev(value for value, _ in values),
            mean_baseline_delta=fmean(delta for _, delta in values),
        )
        for (node_id, state_id, feature_id), values in sorted(grouped.items())
    )


def compute_stage2_proxy_analysis(
    rows: Sequence[ResearchObservation],
    feature_matrix: Sequence[Sequence[float]],
    feature_ids: Sequence[str],
) -> tuple[Stage2ProxyResult, ...]:
    """Compute explicit-label OLS trends or proxy-state descriptive summaries."""

    if len(rows) != len(feature_matrix):
        raise ValueError("row count differs from feature matrix")
    selected = [(index, row) for index, row in enumerate(rows) if row.experiment_stage == 2]
    labels: list[tuple[str, float] | None] = []
    for _, row in selected:
        if len(row.selected_node_ids) != 1:
            labels.append(None)
            continue
        node_id = row.selected_node_ids[0]
        state = next(state for state in row.node_states if state.node_id == node_id)
        labels.append(
            None
            if state.continuous_value is None
            else (f"node_states.{node_id}.continuous_value", state.continuous_value)
        )
    fields = {label[0] for label in labels if label is not None}
    if labels and all(label is not None for label in labels) and len(fields) == 1:
        field = next(iter(fields))
        x_values = [label[1] for label in labels if label is not None]
        x_mean = fmean(x_values)
        denominator = sum((value - x_mean) ** 2 for value in x_values)
        if denominator == 0.0:
            raise ValueError("Stage 2 continuous label has zero variance")
        results: list[Stage2ProxyResult] = []
        for feature_index, feature_id in enumerate(feature_ids):
            y_values = [float(feature_matrix[index][feature_index]) for index, _ in selected]
            y_mean = fmean(y_values)
            slope = (
                sum(
                    (x_value - x_mean) * (y_value - y_mean)
                    for x_value, y_value in zip(x_values, y_values, strict=True)
                )
                / denominator
            )
            predicted = [y_mean + slope * (x_value - x_mean) for x_value in x_values]
            residual_sum = sum(
                (actual - estimate) ** 2
                for actual, estimate in zip(y_values, predicted, strict=True)
            )
            total_sum = sum((value - y_mean) ** 2 for value in y_values)
            r_squared = 1.0 if total_sum == 0.0 else 1.0 - residual_sum / total_sum
            results.append(
                Stage2ProxyResult(
                    feature_id=feature_id,
                    trend_status="computed",
                    sample_count=len(y_values),
                    proxy_state_label=None,
                    mean=None,
                    standard_deviation=None,
                    continuous_label_field=field,
                    slope=slope,
                    r_squared=r_squared,
                )
            )
        return tuple(results)
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for index, row in selected:
        for feature_index, feature_id in enumerate(feature_ids):
            grouped[(row.condition_label, feature_id)].append(
                float(feature_matrix[index][feature_index])
            )
    return tuple(
        Stage2ProxyResult(
            feature_id=feature_id,
            trend_status="not_computed_missing_continuous_label",
            sample_count=len(values),
            proxy_state_label=state_label,
            mean=fmean(values),
            standard_deviation=pstdev(values),
            continuous_label_field=None,
            slope=None,
            r_squared=None,
        )
        for (state_label, feature_id), values in sorted(grouped.items())
    )


def compute_stage3_interactions(
    rows: Sequence[ResearchObservation],
    feature_matrix: Sequence[Sequence[float]],
    feature_ids: Sequence[str],
) -> tuple[Stage3Interaction, ...]:
    """Compute pair residuals from matched 00/10/01/11 Stage 3 groups."""

    if len(rows) != len(feature_matrix):
        raise ValueError("row count differs from feature matrix")
    grouped_rows: dict[str, list[tuple[int, ResearchObservation]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if row.experiment_stage == 3:
            grouped_rows[row.baseline_group_id].append((index, row))
    aggregates: dict[tuple[str, str, str], list[tuple[float, float, float, int]]] = defaultdict(
        list
    )
    for group_rows in grouped_rows.values():
        node_orders = {row.selected_node_ids for _, row in group_rows}
        if len(node_orders) != 1:
            raise ValueError("Stage 3 node order differs within a baseline group")
        node_a, node_b = next(iter(node_orders))
        by_vector: dict[str, list[int]] = defaultdict(list)
        for index, row in group_rows:
            state_by_node = {state.node_id: state for state in row.node_states}
            vector = "".join(
                state_by_node[node_id].discrete_label or "" for node_id in (node_a, node_b)
            )
            by_vector[vector].append(index)
        if set(by_vector) != {"00", "10", "01", "11"}:
            raise ValueError("Stage 3 group lacks the required 00/10/01/11 states")
        for feature_index, feature_id in enumerate(feature_ids):
            means = {
                vector: fmean(float(feature_matrix[index][feature_index]) for index in indices)
                for vector, indices in by_vector.items()
            }
            delta_a = means["10"] - means["00"]
            delta_b = means["01"] - means["00"]
            pair_delta = means["11"] - means["00"]
            aggregates[(node_a, node_b, feature_id)].append(
                (delta_a, delta_b, pair_delta, len(by_vector["11"]))
            )
    results: list[Stage3Interaction] = []
    for (node_a, node_b, feature_id), values in sorted(aggregates.items()):
        delta_a = fmean(value[0] for value in values)
        delta_b = fmean(value[1] for value in values)
        pair_delta = fmean(value[2] for value in values)
        expected = delta_a + delta_b
        results.append(
            Stage3Interaction(
                node_a_id=node_a,
                node_b_id=node_b,
                feature_id=feature_id,
                node_a_delta=delta_a,
                node_b_delta=delta_b,
                observed_pair_delta=pair_delta,
                additive_expected_delta=expected,
                interaction_residual=pair_delta - expected,
                sample_count=sum(value[3] for value in values),
            )
        )
    return tuple(results)


def _stage4_class(row: ResearchObservation, node_order: tuple[str, ...]) -> str:
    if row.selected_node_ids != node_order or len(node_order) != 4:
        raise ValueError("Stage 4 row does not preserve one common four-node plan order")
    states = {state.node_id: state for state in row.node_states}
    labels = tuple(states[node_id].discrete_label for node_id in node_order)
    if any(label not in {"0", "1"} for label in labels):
        raise ValueError("Stage 4 target requires explicit binary NodeState labels")
    return "".join(label for label in labels if label is not None)


def compute_stage4_classification(
    rows: Sequence[ResearchObservation],
    feature_matrix: Sequence[Sequence[float]],
    feature_ids: Sequence[str],
    folds: Sequence[ResearchFold],
    *,
    seed: int,
) -> Stage4Classification:
    """Fit one leak-free multinomial logistic model independently per Stage 4 fold."""

    matrix: NDArray[np.float64] = np.asarray(feature_matrix, dtype=np.float64)
    if matrix.shape != (len(rows), len(feature_ids)) or not np.isfinite(matrix).all():
        raise ValueError("feature matrix shape or finiteness differs from declared inputs")
    stage_rows = tuple(row for row in rows if row.experiment_stage == 4)
    if not stage_rows:
        raise ValueError("research input has no Stage 4 rows")
    node_order = stage_rows[0].selected_node_ids
    class_by_id = {row.row_id: _stage4_class(row, node_order) for row in stage_rows}
    required_classes = tuple(sorted(set(class_by_id.values())))
    index_by_id = {row.row_id: index for index, row in enumerate(rows)}
    required_strategies = {"leave_one_session_out", "leave_one_reassembly_out"}
    if {fold.strategy for fold in folds} != required_strategies:
        raise ValueError("Stage 4 requires the existing session and reassembly fold strategies")
    for strategy in sorted(required_strategies):
        coverage = Counter(
            row_id for fold in folds if fold.strategy == strategy for row_id in fold.test_row_ids
        )
        if coverage != Counter({row_id: 1 for row_id in class_by_id}):
            raise ValueError(f"Stage 4 {strategy} folds do not cover every row exactly once")
    fold_results: list[Stage4FoldResult] = []
    predictions: list[Stage4Prediction] = []
    for fold in sorted(folds, key=lambda item: item.fold_id):
        train_ids = tuple(fold.train_row_ids)
        test_ids = tuple(fold.test_row_ids)
        if (
            not train_ids
            or not test_ids
            or any(row_id not in class_by_id for row_id in train_ids + test_ids)
        ):
            raise ValueError(f"Stage 4 fold {fold.fold_id} has invalid row references")
        y_train = np.asarray([class_by_id[row_id] for row_id in train_ids])
        if tuple(sorted(set(y_train.tolist()))) != required_classes:
            raise ValueError(f"Stage 4 fold {fold.fold_id} training set lacks required classes")
        train_indices = [index_by_id[row_id] for row_id in train_ids]
        test_indices = [index_by_id[row_id] for row_id in test_ids]
        x_train = matrix[train_indices]
        x_test = matrix[test_indices]
        mean = np.mean(x_train, axis=0)
        raw_scale = np.std(x_train, axis=0)
        scale = np.where(raw_scale == 0.0, 1.0, raw_scale)
        model = LogisticRegression(solver="lbfgs", C=1.0, max_iter=1000, random_state=seed)
        model.fit((x_train - mean) / scale, y_train)
        y_true = np.asarray([class_by_id[row_id] for row_id in test_ids])
        y_pred = model.predict((x_test - mean) / scale)
        matrix_values = confusion_matrix(y_true, y_pred, labels=required_classes)
        fold_results.append(
            Stage4FoldResult(
                fold_id=fold.fold_id,
                strategy=fold.strategy,
                accuracy=float(accuracy_score(y_true, y_pred)),
                balanced_accuracy=float(balanced_accuracy_score(y_true, y_pred)),
                macro_f1=float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
                class_order=required_classes,
                confusion_matrix=tuple(
                    tuple(int(value) for value in line) for line in matrix_values
                ),
                training_feature_mean=tuple(float(value) for value in mean),
                training_feature_scale=tuple(float(value) for value in scale),
            )
        )
        predictions.extend(
            Stage4Prediction(
                fold_id=fold.fold_id,
                strategy=fold.strategy,
                row_id=row_id,
                true_class=str(actual),
                predicted_class=str(predicted),
            )
            for row_id, actual, predicted in zip(test_ids, y_true, y_pred, strict=True)
        )
    return Stage4Classification(folds=tuple(fold_results), predictions=tuple(predictions))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise StorageError(f"research analysis input is not a JSON object: {path.name}")
    return value


def _declared_sidecar(path: Path, filename: str) -> str:
    parts = path.read_text(encoding="ascii").strip().split()
    if len(parts) != 2 or parts[1] != filename or len(parts[0]) != 64:
        raise StorageError(f"invalid analysis sidecar: {path.name}")
    return parts[0]


def load_research_dataset(analysis_dir: str | Path) -> ResearchDataset:
    """Load a validated DEV-06.01 envelope without replaying ESS processing."""

    root = Path(analysis_dir).resolve()
    if not root.is_dir() or {path.name for path in root.iterdir()} != ENVELOPE_NAMES:
        raise StorageError("research input is not one complete DEV-06.01 analysis envelope")
    if (root / "ANALYSIS_COMPLETE").read_bytes() != COMPLETE_BYTES:
        raise StorageError("research input completion marker differs")
    receipt = _read_json(root / "analysis_receipt.json")
    core_bindings = {
        "analysis_source_binding.json": "analysis_source_binding_sha256",
        "measurement_row_index.json": "measurement_row_index_sha256",
        "feature_schema.json": "feature_schema_sha256",
        "split_plan.json": "split_plan_sha256",
    }
    input_hashes: dict[str, str] = {}
    for filename, receipt_field in core_bindings.items():
        digest = sha256_bytes((root / filename).read_bytes())
        sidecar_name = filename.replace(".json", ".sha256")
        sidecar_path = root / sidecar_name
        sidecar = _declared_sidecar(sidecar_path, filename)
        if digest != sidecar or receipt.get(receipt_field) != digest:
            raise StorageError(f"research input digest binding differs: {filename}")
        input_hashes[filename] = digest
        input_hashes[sidecar_name] = sha256_bytes(sidecar_path.read_bytes())
    matrix_digest = _declared_sidecar(
        root / "measurement_matrix.npz.sha256", "measurement_matrix.npz"
    )
    if receipt.get("measurement_matrix_npz_sha256") != matrix_digest:
        raise StorageError("research matrix digest differs from its validated receipt")
    input_hashes["measurement_matrix.npz"] = matrix_digest
    input_hashes["measurement_matrix.npz.sha256"] = sha256_bytes(
        (root / "measurement_matrix.npz.sha256").read_bytes()
    )
    receipt_digest = sha256_bytes((root / "analysis_receipt.json").read_bytes())
    if (
        _declared_sidecar(root / "analysis_receipt.sha256", "analysis_receipt.json")
        != receipt_digest
    ):
        raise StorageError("analysis receipt sidecar differs")
    input_hashes["analysis_receipt.json"] = receipt_digest
    input_hashes["analysis_receipt.sha256"] = sha256_bytes(
        (root / "analysis_receipt.sha256").read_bytes()
    )
    for filename in ("analysis_metadata.json", "analysis_record.json", "ANALYSIS_COMPLETE"):
        input_hashes[filename] = sha256_bytes((root / filename).read_bytes())
    source = _read_json(root / "analysis_source_binding.json")
    metadata = _read_json(root / "analysis_metadata.json")
    record = _read_json(root / "analysis_record.json")
    identities = {
        receipt.get("analysis_id"),
        source.get("analysis_id"),
        metadata.get("analysis_id"),
        record.get("analysis_id"),
    }
    if len(identities) != 1 or None in identities:
        raise StorageError("analysis envelope identity fields differ")
    if (
        receipt.get("data_origin") != "synthetic"
        or receipt.get("run_mode") != "development"
        or receipt.get("experimental_result") is not False
        or source.get("data_origin") != "synthetic"
        or source.get("run_mode") != "development"
        or metadata.get("data_origin") != "synthetic"
        or metadata.get("run_mode") != "development"
        or record.get("immutable_status") != "complete"
    ):
        raise StorageError("research input is not complete synthetic development evidence")
    row_index = _read_json(root / "measurement_row_index.json")
    raw_rows = row_index.get("rows")
    if not isinstance(raw_rows, list):
        raise StorageError("measurement row index has no rows")
    observations: list[ResearchObservation] = []
    for raw in raw_rows:
        if not isinstance(raw, dict) or not isinstance(raw.get("node_states"), dict):
            raise StorageError("measurement row structure differs")
        states = tuple(
            ResearchState(
                node_id=str(state["node_id"]),
                state_id=str(state["state_id"]),
                module_id=str(state["module_id"]),
                discrete_label=(
                    None if state.get("discrete_label") is None else str(state["discrete_label"])
                ),
                continuous_value=(
                    None
                    if state.get("continuous_value") is None
                    else float(state["continuous_value"])
                ),
                proxy_state=bool(state["proxy_state"]),
            )
            for state in raw["node_states"].values()
        )
        observations.append(
            ResearchObservation(
                row_id=str(raw["row_id"]),
                experiment_stage=int(raw["experiment_stage"]),
                baseline_group_id=str(raw["baseline_group_id"]),
                session_group_id=str(raw["session_group_id"]),
                reassembly_group_id=str(raw["reassembly_group_id"]),
                condition_label=str(raw["condition_label"]),
                selected_node_ids=tuple(str(value) for value in raw["selected_node_ids"]),
                node_states=states,
                baseline_reference_row_ids=tuple(
                    str(value) for value in raw["baseline_reference_row_ids"]
                ),
            )
        )
    schema = _read_json(root / "feature_schema.json")
    raw_columns = schema.get("columns")
    if not isinstance(raw_columns, list):
        raise StorageError("feature schema has no columns")
    ordered_columns = sorted(raw_columns, key=lambda value: int(value["ordinal"]))
    feature_ids = tuple(str(value["feature_id"]) for value in ordered_columns)
    with np.load(root / "measurement_matrix.npz", allow_pickle=False) as archive:
        if "feature_matrix" not in archive.files:
            raise StorageError("measurement matrix lacks feature_matrix")
        loaded_matrix = np.asarray(archive["feature_matrix"], dtype=np.float64)
    split = _read_json(root / "split_plan.json")
    raw_folds = split.get("folds")
    if not isinstance(raw_folds, list):
        raise StorageError("split plan has no folds")
    folds = tuple(
        ResearchFold(
            fold_id=str(fold["fold_id"]),
            strategy=str(fold["strategy"]),
            train_row_ids=tuple(str(value) for value in fold["train_row_ids"]),
            test_row_ids=tuple(str(value) for value in fold["test_row_ids"]),
        )
        for fold in raw_folds
        if int(fold.get("experiment_stage", 4)) == 4
    )
    declared = (
        int(row_index.get("row_count", -1)),
        int(schema.get("feature_count", -1)),
        int(split.get("row_count", -1)),
    )
    if (
        declared[0] != len(observations)
        or declared[1] != len(feature_ids)
        or declared[2] != len(observations)
        or int(receipt.get("measurement_row_count", -1)) != len(observations)
        or int(receipt.get("feature_count", -1)) != len(feature_ids)
        or int(receipt.get("split_fold_count", -1)) != len(raw_folds)
        or loaded_matrix.shape != (len(observations), len(feature_ids))
        or not np.isfinite(loaded_matrix).all()
    ):
        raise StorageError("analysis row, feature, matrix, or fold declarations differ")
    row_ids = {row.row_id for row in observations}
    if len(row_ids) != len(observations):
        raise StorageError("measurement row IDs are not unique")
    for fold in folds:
        if set(fold.train_row_ids) & set(fold.test_row_ids) or not set(
            fold.train_row_ids + fold.test_row_ids
        ).issubset(row_ids):
            raise StorageError(f"split fold references differ: {fold.fold_id}")
    return ResearchDataset(
        analysis_id=str(receipt["analysis_id"]),
        analysis_receipt_sha256=receipt_digest,
        feature_schema_version=str(schema["schema_version"]),
        feature_ids=feature_ids,
        observations=tuple(observations),
        feature_matrix=tuple(tuple(float(value) for value in row) for row in loaded_matrix),
        folds=folds,
        input_file_sha256=dict(sorted(input_hashes.items())),
    )


def _csv_bytes(fieldnames: tuple[str, ...], rows: Sequence[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _strategy_summary(stage4: Stage4Classification) -> dict[str, dict[str, float | int]]:
    by_strategy: dict[str, list[Stage4FoldResult]] = defaultdict(list)
    for fold in stage4.folds:
        by_strategy[fold.strategy].append(fold)
    return {
        strategy: {
            "fold_count": len(folds),
            "accuracy": fmean(fold.accuracy for fold in folds),
            "balanced_accuracy": fmean(fold.balanced_accuracy for fold in folds),
            "macro_f1": fmean(fold.macro_f1 for fold in folds),
        }
        for strategy, folds in sorted(by_strategy.items())
    }


def run_research_analysis(
    source: ResearchDataset | str | Path,
    output_dir: str | Path,
    *,
    seed: int = 602,
) -> PublishedResearchAnalysis:
    """Validate, analyze, and immutably publish the six-file research result."""

    dataset = source if isinstance(source, ResearchDataset) else load_research_dataset(source)
    output = Path(output_dir).resolve()
    if output.exists():
        raise StorageError("research output directory already exists")
    if {row.experiment_stage for row in dataset.observations} != {1, 2, 3, 4}:
        raise ValueError("research dataset must contain Stage 1-4 rows")
    stage1 = compute_stage1_effects(
        dataset.observations, dataset.feature_matrix, dataset.feature_ids
    )
    stage2 = compute_stage2_proxy_analysis(
        dataset.observations, dataset.feature_matrix, dataset.feature_ids
    )
    stage3 = compute_stage3_interactions(
        dataset.observations, dataset.feature_matrix, dataset.feature_ids
    )
    stage4 = compute_stage4_classification(
        dataset.observations,
        dataset.feature_matrix,
        dataset.feature_ids,
        dataset.folds,
        seed=seed,
    )
    stage1_bytes = _csv_bytes(
        tuple(Stage1Effect.__dataclass_fields__), [asdict(value) for value in stage1]
    )
    stage2_bytes = _csv_bytes(
        tuple(Stage2ProxyResult.__dataclass_fields__), [asdict(value) for value in stage2]
    )
    stage3_bytes = _csv_bytes(
        tuple(Stage3Interaction.__dataclass_fields__), [asdict(value) for value in stage3]
    )
    stage4_bytes = _csv_bytes(
        tuple(Stage4Prediction.__dataclass_fields__),
        [asdict(value) for value in stage4.predictions],
    )
    summary: dict[str, Any] = {
        "schema_version": "1.0.0",
        "analysis_id": dataset.analysis_id,
        "input_analysis_receipt_sha256": dataset.analysis_receipt_sha256,
        "feature_schema_version": dataset.feature_schema_version,
        "feature_ids": list(dataset.feature_ids),
        "data_status": "synthetic_development_provisional",
        "stage_1": {"completed": True, "effect_row_count": len(stage1)},
        "stage_2": {
            "completed": True,
            "trusted_continuous_label_present": all(
                value.trend_status == "computed" for value in stage2
            ),
            "result_row_count": len(stage2),
        },
        "stage_3": {"completed": True, "interaction_row_count": len(stage3)},
        "stage_4": {
            "completed": True,
            "folds": [asdict(fold) for fold in stage4.folds],
            "strategy_metrics": _strategy_summary(stage4),
            "prediction_row_count": len(stage4.predictions),
        },
        "model": {
            "name": "multinomial_logistic_regression",
            "solver": "lbfgs",
            "C": 1.0,
            "max_iter": 1000,
            "random_seed": seed,
        },
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "synthetic": True,
        "development": True,
        "provisional": True,
        "experimental_result": False,
    }
    payloads = {
        "research_summary.json": canonical_json_bytes(summary),
        "stage1_effects.csv": stage1_bytes,
        "stage2_proxy_analysis.csv": stage2_bytes,
        "stage3_interactions.csv": stage3_bytes,
        "stage4_predictions.csv": stage4_bytes,
    }
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "analysis_id": dataset.analysis_id,
        "input_file_sha256": dataset.input_file_sha256,
        "output_file_sha256": {
            name: sha256_bytes(content) for name, content in sorted(payloads.items())
        },
        "row_count": len(dataset.observations),
        "feature_count": len(dataset.feature_ids),
        "fold_count": len(dataset.folds),
        "stage_completed": {f"stage_{stage}": True for stage in range(1, 5)},
        "synthetic": True,
        "development": True,
        "provisional": True,
        "hardware_io_performed": False,
        "formal_experiment_performed": False,
        "experimental_result": False,
    }
    payloads["research_receipt.json"] = canonical_json_bytes(receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        for name, content in payloads.items():
            with (staging / name).open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        os.rename(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return PublishedResearchAnalysis(output_path=output, summary=summary, receipt=receipt)


__all__ = [
    "RESEARCH_OUTPUT_NAMES",
    "PublishedResearchAnalysis",
    "ResearchDataset",
    "ResearchFold",
    "ResearchObservation",
    "ResearchState",
    "Stage1Effect",
    "Stage2ProxyResult",
    "Stage3Interaction",
    "Stage4Classification",
    "Stage4FoldResult",
    "Stage4Prediction",
    "compute_stage1_effects",
    "compute_stage2_proxy_analysis",
    "compute_stage3_interactions",
    "compute_stage4_classification",
    "load_research_dataset",
    "run_research_analysis",
]
