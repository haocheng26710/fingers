from pathlib import Path

import pytest

from acoustic_ladder.analysis.persistence import (
    AnalysisPersistenceError,
    SyntheticMeasurementMatrixStore,
    compute_synthetic_measurement_matrix,
    validate_synthetic_measurement_matrix,
)
from acoustic_ladder.analysis.spec import load_development_analysis_matrix_spec

PROJECT_ROOT = Path(__file__).parents[2]


def test_public_compute_rejects_path_traversal_without_writing(tmp_path: Path) -> None:
    synthetic_root = tmp_path / "synthetic"
    store = SyntheticMeasurementMatrixStore(synthetic_root)
    spec = load_development_analysis_matrix_spec(
        PROJECT_ROOT / "config/analysis/development_measurement_matrix.yaml",
        project_root=PROJECT_ROOT,
    )

    with pytest.raises(AnalysisPersistenceError, match="unsafe analysis_id"):
        compute_synthetic_measurement_matrix(
            store=store,
            sources=(),
            analysis_spec=spec,
            analysis_id="../escape",
        )

    assert not synthetic_root.exists()
    assert not (tmp_path / "escape").exists()


def test_publication_gates_reject_partial_target_and_stale_lock(tmp_path: Path) -> None:
    store = SyntheticMeasurementMatrixStore(tmp_path / "synthetic")
    spec = load_development_analysis_matrix_spec(
        PROJECT_ROOT / "config/analysis/development_measurement_matrix.yaml",
        project_root=PROJECT_ROOT,
    )
    target = store.analysis_path("matrix")
    target.mkdir(parents=True)
    (target / "partial.json").write_text("{}", encoding="utf-8")
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    with pytest.raises(AnalysisPersistenceError, match="partial analysis target"):
        compute_synthetic_measurement_matrix(
            store=store, sources=(), analysis_spec=spec, analysis_id="matrix"
        )
    with pytest.raises(AnalysisPersistenceError, match="incomplete analysis envelope"):
        validate_synthetic_measurement_matrix(
            store=store, sources=(), analysis_spec=spec, analysis_id="matrix"
        )
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after

    target.rename(store.analysis_path("old-partial"))
    lock = store.analyses_root / ".analysis_matrix.lock"
    lock.write_bytes(b"")
    with pytest.raises(AnalysisPersistenceError, match="already in progress"):
        compute_synthetic_measurement_matrix(
            store=store, sources=(), analysis_spec=spec, analysis_id="matrix"
        )
    assert lock.exists()
