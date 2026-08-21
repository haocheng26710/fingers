"""Static, synthetic-only report export for DEV-06.02 research results."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "acoustic-ladder-matplotlib")
)

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize
from matplotlib.figure import Figure

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.storage.io import StorageError, sha256_bytes

RESEARCH_INPUT_NAMES = frozenset(
    {
        "research_summary.json",
        "stage1_effects.csv",
        "stage2_proxy_analysis.csv",
        "stage3_interactions.csv",
        "stage4_predictions.csv",
        "research_receipt.json",
    }
)
REPORT_OUTPUT_NAMES = frozenset(
    {
        "stage1_effects.png",
        "stage1_effects.svg",
        "stage2_proxy.png",
        "stage2_proxy.svg",
        "stage3_interactions.png",
        "stage3_interactions.svg",
        "stage4_confusion_matrix.png",
        "stage4_confusion_matrix.svg",
        "analysis_summary.md",
        "report_manifest.json",
    }
)

_STAGE1_COLUMNS = (
    "active_node_id",
    "bridge_state_id",
    "feature_id",
    "sample_count",
    "mean",
    "standard_deviation",
    "mean_baseline_delta",
)
_STAGE2_COLUMNS = (
    "feature_id",
    "trend_status",
    "sample_count",
    "proxy_state_label",
    "mean",
    "standard_deviation",
    "continuous_label_field",
    "slope",
    "r_squared",
)
_STAGE3_COLUMNS = (
    "node_a_id",
    "node_b_id",
    "feature_id",
    "node_a_delta",
    "node_b_delta",
    "observed_pair_delta",
    "additive_expected_delta",
    "interaction_residual",
    "sample_count",
)
_STAGE4_COLUMNS = ("fold_id", "strategy", "row_id", "true_class", "predicted_class")


@dataclass(frozen=True)
class PublishedResearchReport:
    output_path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True)
class _ResearchResults:
    root: Path
    summary: dict[str, Any]
    receipt: dict[str, Any]
    receipt_sha256: str
    stage1: tuple[dict[str, str], ...]
    stage2: tuple[dict[str, str], ...]
    stage3: tuple[dict[str, str], ...]
    stage4: tuple[dict[str, str], ...]
    feature_ids: tuple[str, ...]
    stage2_missing_continuous_label: bool


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise StorageError(f"invalid report input JSON: {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise StorageError(f"report input JSON is not an object: {path.name}")
    return value


def _csv_rows(path: Path, expected: tuple[str, ...]) -> tuple[dict[str, str], ...]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != expected:
                raise StorageError(f"report input CSV columns differ: {path.name}")
            rows = tuple(dict(row) for row in reader)
    except UnicodeError as exc:
        raise StorageError(f"invalid report input CSV encoding: {path.name}") from exc
    if not rows:
        raise StorageError(f"report input CSV contains no rows: {path.name}")
    return rows


def _finite(value: str, *, field: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise StorageError(f"report input has invalid numeric {field}") from exc
    if not math.isfinite(parsed):
        raise StorageError(f"report input has non-finite numeric {field}")
    return parsed


def _positive_count(value: str, *, field: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise StorageError(f"report input has invalid count {field}") from exc
    if parsed <= 0:
        raise StorageError(f"report input has non-positive count {field}")
    return parsed


def _require_strings(rows: Iterable[dict[str, str]], fields: tuple[str, ...]) -> None:
    for row in rows:
        if any(not row[field] for field in fields):
            raise StorageError(f"report input has an empty required label: {fields}")


def _validate_stage_rows(
    stage1: tuple[dict[str, str], ...],
    stage2: tuple[dict[str, str], ...],
    stage3: tuple[dict[str, str], ...],
    stage4: tuple[dict[str, str], ...],
    feature_ids: tuple[str, ...],
) -> bool:
    _require_strings(stage1, ("active_node_id", "bridge_state_id", "feature_id"))
    for row in stage1:
        _positive_count(row["sample_count"], field="stage1.sample_count")
        for field in ("mean", "standard_deviation", "mean_baseline_delta"):
            _finite(row[field], field=f"stage1.{field}")
    _require_strings(stage2, ("feature_id", "trend_status"))
    statuses = {row["trend_status"] for row in stage2}
    allowed = {"computed", "not_computed_missing_continuous_label"}
    if not statuses or not statuses.issubset(allowed) or len(statuses) != 1:
        raise StorageError("Stage 2 trend status is inconsistent")
    missing = statuses == {"not_computed_missing_continuous_label"}
    for row in stage2:
        _positive_count(row["sample_count"], field="stage2.sample_count")
        if missing:
            if not row["proxy_state_label"] or any(
                row[field] for field in ("continuous_label_field", "slope", "r_squared")
            ):
                raise StorageError("Stage 2 missing-label row contains a fabricated trend")
            _finite(row["mean"], field="stage2.mean")
            _finite(row["standard_deviation"], field="stage2.standard_deviation")
        else:
            if not row["continuous_label_field"] or any(
                row[field] for field in ("proxy_state_label", "mean", "standard_deviation")
            ):
                raise StorageError("Stage 2 computed trend row is inconsistent")
            _finite(row["slope"], field="stage2.slope")
            _finite(row["r_squared"], field="stage2.r_squared")
    _require_strings(stage3, ("node_a_id", "node_b_id", "feature_id"))
    for row in stage3:
        _positive_count(row["sample_count"], field="stage3.sample_count")
        for field in (
            "node_a_delta",
            "node_b_delta",
            "observed_pair_delta",
            "additive_expected_delta",
            "interaction_residual",
        ):
            _finite(row[field], field=f"stage3.{field}")
    _require_strings(stage4, _STAGE4_COLUMNS)
    expected_features = set(feature_ids)
    for name, rows in (("Stage 1", stage1), ("Stage 2", stage2), ("Stage 3", stage3)):
        if {row["feature_id"] for row in rows} != expected_features:
            raise StorageError(f"{name} feature labels differ from research summary")
    return missing


def _load_results(root_value: str | Path) -> _ResearchResults:
    root = Path(root_value).resolve()
    if not root.is_dir():
        raise StorageError("research report input directory does not exist")
    names = {path.name for path in root.iterdir()}
    missing_names = RESEARCH_INPUT_NAMES - names
    if missing_names:
        raise StorageError(f"research report input is missing files: {sorted(missing_names)}")
    summary = _json_object(root / "research_summary.json")
    receipt = _json_object(root / "research_receipt.json")
    stage1 = _csv_rows(root / "stage1_effects.csv", _STAGE1_COLUMNS)
    stage2 = _csv_rows(root / "stage2_proxy_analysis.csv", _STAGE2_COLUMNS)
    stage3 = _csv_rows(root / "stage3_interactions.csv", _STAGE3_COLUMNS)
    stage4 = _csv_rows(root / "stage4_predictions.csv", _STAGE4_COLUMNS)
    if (
        summary.get("analysis_id") != receipt.get("analysis_id")
        or summary.get("synthetic") is not True
        or summary.get("development") is not True
        or summary.get("provisional") is not True
        or summary.get("experimental_result") is not False
        or receipt.get("synthetic") is not True
        or receipt.get("development") is not True
        or receipt.get("provisional") is not True
        or receipt.get("experimental_result") is not False
        or receipt.get("hardware_io_performed") is not False
        or receipt.get("formal_experiment_performed") is not False
    ):
        raise StorageError("research summary and receipt state differ")
    feature_values = summary.get("feature_ids")
    if not isinstance(feature_values, list) or not feature_values:
        raise StorageError("research summary has no feature IDs")
    feature_ids = tuple(str(value) for value in feature_values)
    if len(feature_ids) != len(set(feature_ids)):
        raise StorageError("research summary feature IDs are not unique")
    output_hashes = receipt.get("output_file_sha256")
    if not isinstance(output_hashes, dict):
        raise StorageError("research receipt has no output hash bindings")
    for filename in RESEARCH_INPUT_NAMES - {"research_receipt.json"}:
        expected = output_hashes.get(filename)
        actual = sha256_bytes((root / filename).read_bytes())
        if expected != actual:
            raise StorageError(f"research receipt hash binding differs: {filename}")
    stage2_missing = _validate_stage_rows(stage1, stage2, stage3, stage4, feature_ids)
    stage_counts = (
        (summary.get("stage_1"), "effect_row_count", len(stage1)),
        (summary.get("stage_2"), "result_row_count", len(stage2)),
        (summary.get("stage_3"), "interaction_row_count", len(stage3)),
        (summary.get("stage_4"), "prediction_row_count", len(stage4)),
    )
    for stage, field, count in stage_counts:
        if (
            not isinstance(stage, dict)
            or stage.get("completed") is not True
            or stage.get(field) != count
        ):
            raise StorageError("research summary stage count differs from CSV")
    stage2_summary = summary["stage_2"]
    if stage2_summary.get("trusted_continuous_label_present") is stage2_missing:
        raise StorageError("Stage 2 label status differs between summary and CSV")
    receipt_sha256 = hashlib.sha256((root / "research_receipt.json").read_bytes()).hexdigest()
    return _ResearchResults(
        root=root,
        summary=summary,
        receipt=receipt,
        receipt_sha256=receipt_sha256,
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
        feature_ids=feature_ids,
        stage2_missing_continuous_label=stage2_missing,
    )


def _matrix(
    rows: Sequence[dict[str, str]],
    row_labels: Sequence[str],
    feature_ids: tuple[str, ...],
    *,
    value_field: str,
    label_field: str,
) -> np.ndarray:
    lookup = {
        (row[label_field], row["feature_id"]): _finite(row[value_field], field=value_field)
        for row in rows
    }
    try:
        return np.asarray(
            [[lookup[(label, feature)] for feature in feature_ids] for label in row_labels],
            dtype=np.float64,
        )
    except KeyError as exc:
        raise StorageError("report heatmap input is not rectangular") from exc


def _marked_figure(title: str, *, width: float, height: float) -> tuple[Figure, Any]:
    figure, axis = plt.subplots(figsize=(width, height), constrained_layout=True)
    figure.suptitle(f"{title} - SYNTHETIC / PROVISIONAL", fontsize=12, fontweight="bold")
    figure.text(
        0.995,
        0.005,
        "SYNTHETIC / PROVISIONAL",
        ha="right",
        va="bottom",
        fontsize=8,
        color="dimgray",
    )
    return figure, axis


def _heatmap(
    figure: Figure,
    axis: Any,
    values: np.ndarray,
    row_labels: Sequence[str],
    feature_ids: tuple[str, ...],
    *,
    colorbar_label: str,
) -> None:
    bound = max(float(np.max(np.abs(values))), np.finfo(np.float64).eps)
    image = axis.imshow(values, aspect="auto", cmap="coolwarm", norm=Normalize(-bound, bound))
    axis.set_xticks(range(len(feature_ids)), labels=feature_ids, rotation=45, ha="right")
    axis.set_yticks(range(len(row_labels)), labels=row_labels)
    axis.set_xlabel("Feature ID (from research input)")
    figure.colorbar(image, ax=axis, label=colorbar_label, shrink=0.85)


def _stage1_figure(results: _ResearchResults) -> Figure:
    labels = tuple(
        sorted({f"{row['active_node_id']} / {row['bridge_state_id']}" for row in results.stage1})
    )
    normalized_rows = tuple(
        {**row, "group": f"{row['active_node_id']} / {row['bridge_state_id']}"}
        for row in results.stage1
    )
    values = _matrix(
        normalized_rows,
        labels,
        results.feature_ids,
        value_field="mean_baseline_delta",
        label_field="group",
    )
    figure, axis = _marked_figure(
        "Stage 1 mean difference relative to matched BLK",
        width=max(9.0, len(results.feature_ids) * 0.55),
        height=max(4.0, len(labels) * 0.38 + 2.0),
    )
    _heatmap(
        figure,
        axis,
        values,
        labels,
        results.feature_ids,
        colorbar_label="Mean feature difference relative to BLK",
    )
    axis.set_ylabel("Active node / bridge state")
    return figure


def _stage2_figure(results: _ResearchResults) -> Figure:
    if results.stage2_missing_continuous_label:
        labels = tuple(sorted({row["proxy_state_label"] for row in results.stage2}))
        values = _matrix(
            results.stage2,
            labels,
            results.feature_ids,
            value_field="mean",
            label_field="proxy_state_label",
        )
        figure, axis = _marked_figure(
            "Stage 2 Proxy / no continuous label — descriptive mean",
            width=max(9.0, len(results.feature_ids) * 0.55),
            height=max(4.0, len(labels) * 0.4 + 2.0),
        )
        image = axis.imshow(values, aspect="auto", cmap="viridis")
        axis.set_xticks(
            range(len(results.feature_ids)), labels=results.feature_ids, rotation=45, ha="right"
        )
        axis.set_yticks(range(len(labels)), labels=labels)
        axis.set_xlabel("Feature ID (from research input)")
        axis.set_ylabel("Proxy state label")
        figure.colorbar(image, ax=axis, label="Descriptive feature mean", shrink=0.85)
        return figure
    slopes = [_finite(row["slope"], field="stage2.slope") for row in results.stage2]
    figure, axis = _marked_figure(
        "Stage 2 explicit continuous-label OLS trend",
        width=max(9.0, len(results.feature_ids) * 0.6),
        height=5.0,
    )
    axis.bar(results.feature_ids, slopes, color="#4477aa")
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.tick_params(axis="x", labelrotation=45)
    for label in axis.get_xticklabels():
        label.set_ha("right")
    axis.set_xlabel("Feature ID (from research input)")
    axis.set_ylabel("OLS slope from research result")
    return figure


def _stage3_figure(results: _ResearchResults) -> Figure:
    labels = tuple(sorted({f"{row['node_a_id']} + {row['node_b_id']}" for row in results.stage3}))
    normalized_rows = tuple(
        {**row, "pair": f"{row['node_a_id']} + {row['node_b_id']}"} for row in results.stage3
    )
    values = _matrix(
        normalized_rows,
        labels,
        results.feature_ids,
        value_field="interaction_residual",
        label_field="pair",
    )
    figure, axis = _marked_figure(
        "Stage 3 interaction residual",
        width=max(9.0, len(results.feature_ids) * 0.55),
        height=max(4.0, len(labels) * 0.45 + 2.0),
    )
    _heatmap(
        figure,
        axis,
        values,
        labels,
        results.feature_ids,
        colorbar_label="Interaction residual (zero-centered)",
    )
    axis.set_ylabel("Node pair")
    return figure


def _stage4_figure(results: _ResearchResults) -> Figure:
    strategies = tuple(sorted({row["strategy"] for row in results.stage4}))
    classes = tuple(
        sorted(
            {row["true_class"] for row in results.stage4}
            | {row["predicted_class"] for row in results.stage4}
        )
    )
    figure, axes_value = plt.subplots(
        1,
        len(strategies),
        figsize=(
            max(12.0, len(classes) * 0.75 * len(strategies)),
            max(6.0, len(classes) * 0.55),
        ),
        constrained_layout=True,
        squeeze=False,
    )
    figure.suptitle(
        "Stage 4 out-of-fold confusion matrix - synthetic development fixture - "
        "SYNTHETIC / PROVISIONAL",
        fontsize=12,
        fontweight="bold",
    )
    figure.text(
        0.995,
        0.005,
        "SYNTHETIC / PROVISIONAL",
        ha="right",
        fontsize=8,
        color="dimgray",
    )
    index = {label: position for position, label in enumerate(classes)}
    maximum_count = 0
    matrices: dict[str, np.ndarray] = {}
    for strategy in strategies:
        values = np.zeros((len(classes), len(classes)), dtype=np.int64)
        for row in results.stage4:
            if row["strategy"] == strategy:
                values[index[row["true_class"]], index[row["predicted_class"]]] += 1
        matrices[strategy] = values
        maximum_count = max(maximum_count, int(np.max(values)))
    image = None
    for axis, strategy in zip(axes_value[0], strategies, strict=True):
        image = axis.imshow(matrices[strategy], cmap="Blues", vmin=0, vmax=maximum_count)
        axis.set_xticks(range(len(classes)), labels=classes, rotation=45, ha="right")
        axis.set_yticks(range(len(classes)), labels=classes)
        axis.set_xlabel("Predicted four-node state", fontsize=9)
        axis.set_ylabel("True four-node state", fontsize=9)
        axis.set_title(strategy.replace("leave_one_", "leave_one_\n"), fontsize=10)
        axis.set_box_aspect(1)
    if image is None:
        raise StorageError("Stage 4 input has no fold strategies")
    figure.colorbar(image, ax=list(axes_value[0]), label="OOF count", shrink=0.75)
    return figure


def _save_figure(figure: Figure, staging: Path, stem: str) -> None:
    figure.savefig(
        staging / f"{stem}.png",
        format="png",
        dpi=300,
        bbox_inches="tight",
        metadata={"Software": "Acoustic Ladder"},
    )
    figure.savefig(
        staging / f"{stem}.svg",
        format="svg",
        bbox_inches="tight",
        metadata={"Creator": "Acoustic Ladder", "Date": None},
    )
    plt.close(figure)


def _summary_markdown(results: _ResearchResults) -> bytes:
    stage4 = results.summary["stage_4"]
    model = results.summary["model"]
    metrics = stage4["strategy_metrics"]
    stage2_line = (
        "Stage 2 lacks a trusted continuous label; Proxy / no continuous label "
        "descriptive means are shown."
        if results.stage2_missing_continuous_label
        else (
            "Stage 2 contains an explicit continuous label; reported OLS trend "
            "coefficients are shown."
        )
    )
    lines = [
        "# Synthetic provisional analysis summary",
        "",
        "## Data status",
        "",
        f"- Analysis ID: `{results.summary['analysis_id']}`",
        "- Source status: synthetic / development / provisional",
        "- Experimental result: false",
        "",
        "## Stage 1-4 results",
        "",
        (
            f"- Stage 1: {len(results.stage1)} node/state/feature descriptive effects "
            "relative to matched BLK."
        ),
        f"- Stage 2: {stage2_line}",
        f"- Stage 3: {len(results.stage3)} node-pair/feature interaction residuals.",
        f"- Stage 4 model: `{model['name']}` (`solver={model['solver']}`, `C={model['C']}`, "
        f"  `max_iter={model['max_iter']}`, `random_seed={model['random_seed']}`).",
        "",
        "| Fold strategy | Folds | Accuracy | Balanced accuracy | Macro-F1 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for strategy in sorted(metrics):
        value = metrics[strategy]
        lines.append(
            f"| {strategy} | {value['fold_count']} | {value['accuracy']:.6g} | "
            f"{value['balanced_accuracy']:.6g} | {value['macro_f1']:.6g} |"
        )
    lines.extend(
        [
            "",
            "## Figures",
            "",
            "- [Stage 1 effects](stage1_effects.png) ([SVG](stage1_effects.svg))",
            "- [Stage 2 proxy](stage2_proxy.png) ([SVG](stage2_proxy.svg))",
            "- [Stage 3 interactions](stage3_interactions.png) ([SVG](stage3_interactions.svg))",
            "- [Stage 4 confusion matrix](stage4_confusion_matrix.png) "
            "([SVG](stage4_confusion_matrix.svg))",
            "",
            "## Limitations",
            "",
            "All values are synthetic development fixture outputs and remain provisional. "
            "Feature IDs are reproduced from the research input; DEV-06.02 does not persist "
            "feature units in its result directory. Fixture classification scores are not device "
            "performance. This report is not a formal experimental conclusion.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def export_research_report(
    research_output_dir: str | Path,
    output_dir: str | Path,
) -> PublishedResearchReport:
    """Validate a DEV-06.02 result and publish one static ten-file report."""

    output = Path(output_dir).resolve()
    if output.exists():
        raise StorageError("research report output directory already exists")
    results = _load_results(research_output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        _save_figure(_stage1_figure(results), staging, "stage1_effects")
        _save_figure(_stage2_figure(results), staging, "stage2_proxy")
        _save_figure(_stage3_figure(results), staging, "stage3_interactions")
        _save_figure(_stage4_figure(results), staging, "stage4_confusion_matrix")
        with (staging / "analysis_summary.md").open("xb") as handle:
            handle.write(_summary_markdown(results))
            handle.flush()
            os.fsync(handle.fileno())
        manifest: dict[str, Any] = {
            "schema_version": "1.0.0",
            "input_research_receipt": {
                "analysis_id": results.receipt["analysis_id"],
                "sha256": results.receipt_sha256,
            },
            "generated_files": sorted(REPORT_OUTPUT_NAMES),
            "runtime": {
                "matplotlib": matplotlib.__version__,
                "python": platform.python_version(),
            },
            "synthetic": True,
            "provisional": True,
            "experimental_result": False,
        }
        with (staging / "report_manifest.json").open("xb") as handle:
            handle.write(canonical_json_bytes(manifest))
            handle.flush()
            os.fsync(handle.fileno())
        if {path.name for path in staging.iterdir()} != REPORT_OUTPUT_NAMES:
            raise StorageError("research report staging file set differs")
        os.rename(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return PublishedResearchReport(output_path=output, manifest=manifest)


__all__ = [
    "REPORT_OUTPUT_NAMES",
    "PublishedResearchReport",
    "export_research_report",
]
