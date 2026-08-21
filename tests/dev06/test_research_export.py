from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from acoustic_ladder.analysis.report_export import REPORT_OUTPUT_NAMES, export_research_report
from acoustic_ladder.analysis.research import run_research_analysis
from acoustic_ladder.cli import main
from acoustic_ladder.storage.io import StorageError

from .test_research_analysis import _research_dataset


def test_small_research_fixture_exports_all_figures_and_summary(tmp_path: Path) -> None:
    research = run_research_analysis(_research_dataset(), tmp_path / "research", seed=17)

    exported = export_research_report(research.output_path, tmp_path / "report")

    assert {path.name for path in exported.output_path.iterdir()} == REPORT_OUTPUT_NAMES
    for stem in (
        "stage1_effects",
        "stage2_proxy",
        "stage3_interactions",
        "stage4_confusion_matrix",
    ):
        png = exported.output_path / f"{stem}.png"
        svg = exported.output_path / f"{stem}.svg"
        assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png.read_bytes()) > 100
        assert svg.read_text(encoding="utf-8").lstrip().startswith("<?xml")
        assert "SYNTHETIC / PROVISIONAL" in svg.read_text(encoding="utf-8")
    summary = (exported.output_path / "analysis_summary.md").read_text(encoding="utf-8")
    assert "Proxy / no continuous label" not in summary
    assert "not a formal experimental conclusion" in summary
    manifest = json.loads(
        (exported.output_path / "report_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["synthetic"] is True
    assert manifest["experimental_result"] is False


def test_export_rejects_missing_required_input(tmp_path: Path) -> None:
    research = run_research_analysis(_research_dataset(), tmp_path / "research", seed=17)
    (research.output_path / "stage3_interactions.csv").unlink()

    with pytest.raises(StorageError, match="missing files"):
        export_research_report(research.output_path, tmp_path / "report")


def test_export_rejects_missing_required_csv_column(tmp_path: Path) -> None:
    research = run_research_analysis(_research_dataset(), tmp_path / "research", seed=17)
    stage1 = research.output_path / "stage1_effects.csv"
    text = stage1.read_text(encoding="utf-8")
    stage1.write_text(text.replace("mean_baseline_delta", "wrong_column", 1), encoding="utf-8")

    with pytest.raises(StorageError, match="CSV columns differ"):
        export_research_report(research.output_path, tmp_path / "report")


def test_stage2_missing_continuous_label_does_not_fabricate_trend(tmp_path: Path) -> None:
    dataset = _research_dataset()
    observations = tuple(
        replace(
            row,
            node_states=tuple(replace(state, continuous_value=None) for state in row.node_states),
        )
        if row.experiment_stage == 2
        else row
        for row in dataset.observations
    )
    research = run_research_analysis(
        replace(dataset, observations=observations), tmp_path / "research", seed=17
    )

    exported = export_research_report(research.output_path, tmp_path / "report")

    svg = (exported.output_path / "stage2_proxy.svg").read_text(encoding="utf-8")
    assert "Proxy / no continuous label" in svg
    assert "OLS slope" not in svg
    summary = (exported.output_path / "analysis_summary.md").read_text(encoding="utf-8")
    assert "lacks a trusted continuous label" in summary


def test_export_rejects_existing_output_directory(tmp_path: Path) -> None:
    research = run_research_analysis(_research_dataset(), tmp_path / "research", seed=17)
    output = tmp_path / "report"
    output.mkdir()

    with pytest.raises(StorageError, match="already exists"):
        export_research_report(research.output_path, output)


def test_research_report_export_cli_smoke(tmp_path: Path, capsys: object) -> None:
    research = run_research_analysis(_research_dataset(), tmp_path / "research", seed=17)
    output = tmp_path / "report"

    main(
        [
            "research-report-export",
            "--research-output-dir",
            str(research.output_path),
            "--output-dir",
            str(output),
        ]
    )

    assert {path.name for path in output.iterdir()} == REPORT_OUTPUT_NAMES
