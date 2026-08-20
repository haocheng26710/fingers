import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.analysis.persistence import (
    ENVELOPE_NAMES,
    AnalysisPersistenceError,
    SyntheticMeasurementMatrixStore,
    compute_synthetic_measurement_matrix,
    validate_synthetic_measurement_matrix,
)
from acoustic_ladder.analysis.source_validation import AnalysisExecutionSource
from acoustic_ladder.analysis.spec import load_development_analysis_matrix_spec
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


def _tree_digest(tree: dict[str, bytes]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            [
                {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
                for path, payload in sorted(tree.items())
            ]
        )
    ).hexdigest()


def _canonical_update(
    payload: bytes,
    updates: dict[str, object] | None = None,
    *,
    remove: tuple[str, ...] = (),
) -> bytes:
    document = json.loads(payload)
    document.update(updates or {})
    for field in remove:
        document.pop(field)
    return canonical_json_bytes(document)


def _execute_all_stages(
    root: Path,
) -> tuple[dict[int, int], str, dict[str, bytes], tuple[AnalysisExecutionSource, ...]]:
    counts: dict[int, int] = {}
    combined: dict[str, bytes] = {}
    sources: list[AnalysisExecutionSource] = []
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
        sources.append(
            AnalysisExecutionSource(
                store=execution_store,
                session_store=session_store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id=f"stage{stage}-plan",
                execution_id=f"stage{stage}-execution",
                scenario=scenario,
                ess_artifact_root=ess.artifact_root,
            )
        )
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
    return counts, aggregate, combined, tuple(sources)


def test_all_four_stages_execute_deterministically_in_two_independent_roots(
    tmp_path: Path,
) -> None:
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    assert not left_root.exists()
    assert not right_root.exists()

    left_counts, left_aggregate, left_tree, left_sources = _execute_all_stages(left_root)
    right_counts, right_aggregate, right_tree, right_sources = _execute_all_stages(right_root)

    assert left_counts == right_counts == EXPECTED_COUNTS
    assert sum(left_counts.values()) == 344
    assert left_aggregate == right_aggregate
    assert left_tree == right_tree

    analysis_spec = load_development_analysis_matrix_spec(
        PROJECT_ROOT / "config/analysis/development_measurement_matrix.yaml",
        project_root=PROJECT_ROOT,
    )
    left_store = SyntheticMeasurementMatrixStore(left_root / "analysis-synthetic")
    right_store = SyntheticMeasurementMatrixStore(right_root / "analysis-synthetic")
    left = compute_synthetic_measurement_matrix(
        store=left_store,
        sources=left_sources,
        analysis_spec=analysis_spec,
        analysis_id="stages-1-4",
    )
    right = compute_synthetic_measurement_matrix(
        store=right_store,
        sources=tuple(reversed(right_sources)),
        analysis_spec=analysis_spec,
        analysis_id="stages-1-4",
    )
    assert left.receipt == right.receipt
    assert left.receipt.measurement_row_count == 344
    assert left.receipt.rows_excluded == 0
    assert left.receipt.model_fit_performed is False
    assert left.receipt.hardware_io_performed is False
    left_analysis_tree = _tree(left_store.analyses_root)
    right_analysis_tree = _tree(right_store.analyses_root)
    assert left_analysis_tree == right_analysis_tree
    assert len(left_analysis_tree) == len(ENVELOPE_NAMES) == 15

    left_before = _tree(left_store.analyses_root)
    assert (
        validate_synthetic_measurement_matrix(
            store=left_store,
            sources=left_sources,
            analysis_spec=analysis_spec,
            analysis_id="stages-1-4",
        ).receipt
        == left.receipt
    )
    assert _tree(left_store.analyses_root) == left_before
    assert (
        validate_synthetic_measurement_matrix(
            store=right_store,
            sources=tuple(reversed(right_sources)),
            analysis_spec=analysis_spec,
            analysis_id="stages-1-4",
        ).receipt
        == right.receipt
    )

    left_analysis = Path(left.analysis_path)
    metadata_path = left_analysis / "analysis_metadata.json"
    record_path = left_analysis / "analysis_record.json"
    receipt_path = left_analysis / "analysis_receipt.json"
    receipt_sidecar_path = left_analysis / "analysis_receipt.sha256"
    original_metadata = metadata_path.read_bytes()
    original_record = record_path.read_bytes()
    original_receipt = receipt_path.read_bytes()
    original_receipt_sidecar = receipt_sidecar_path.read_bytes()
    original_left_tree = _tree(left_store.analyses_root)
    original_right_tree = _tree(right_store.analyses_root)

    def assert_attack_rejected(mutations: dict[str, bytes]) -> None:
        originals = {name: (left_analysis / name).read_bytes() for name in mutations}
        try:
            for name, payload in mutations.items():
                (left_analysis / name).write_bytes(payload)
            before_tree = _tree(left_store.analyses_root)
            before_digest = _tree_digest(before_tree)
            before_stats = {
                path.relative_to(left_store.analyses_root).as_posix(): (
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                )
                for path in left_store.analyses_root.rglob("*")
                if path.is_file()
            }
            with pytest.raises(AnalysisPersistenceError, match="full replay"):
                validate_synthetic_measurement_matrix(
                    store=left_store,
                    sources=left_sources,
                    analysis_spec=analysis_spec,
                    analysis_id="stages-1-4",
                )
            after_tree = _tree(left_store.analyses_root)
            after_stats = {
                path.relative_to(left_store.analyses_root).as_posix(): (
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                )
                for path in left_store.analyses_root.rglob("*")
                if path.is_file()
            }
            assert after_tree == before_tree
            assert _tree_digest(after_tree) == before_digest
            assert after_stats == before_stats
            assert not list(left_store.analyses_root.glob("*.lock"))
            assert not list(left_store.analyses_root.glob("*.staging-*"))
            assert _tree(right_store.analyses_root) == original_right_tree
        finally:
            for name, payload in originals.items():
                (left_analysis / name).write_bytes(payload)

    next_day = "2026-08-21T11:00:00Z"
    same_instant_offset = "2026-08-20T12:00:00+01:00"
    changed_metadata_time = _canonical_update(
        original_metadata, {"analysis_evidence_time": next_day}
    )
    changed_record_time = _canonical_update(original_record, {"analysis_evidence_time": next_day})
    assert_attack_rejected({"analysis_metadata.json": changed_metadata_time})
    assert_attack_rejected({"analysis_record.json": changed_record_time})
    assert_attack_rejected(
        {
            "analysis_metadata.json": changed_metadata_time,
            "analysis_record.json": changed_record_time,
        }
    )
    assert_attack_rejected(
        {
            "analysis_metadata.json": _canonical_update(
                original_metadata, {"analysis_evidence_time": same_instant_offset}
            ),
            "analysis_record.json": _canonical_update(
                original_record, {"analysis_evidence_time": same_instant_offset}
            ),
        }
    )
    assert_attack_rejected(
        {
            "analysis_metadata.json": _canonical_update(
                original_metadata, {"analysis_evidence_time": "2026-08-20T11:00:00"}
            )
        }
    )
    assert_attack_rejected(
        {
            "analysis_metadata.json": _canonical_update(
                original_metadata, {"analysis_evidence_time": "not-a-datetime"}
            )
        }
    )
    assert_attack_rejected(
        {
            "analysis_metadata.json": _canonical_update(
                original_metadata, {"analysis_evidence_time_basis": "runtime_now"}
            )
        }
    )
    assert_attack_rejected(
        {
            "analysis_metadata.json": changed_metadata_time,
            "analysis_record.json": _canonical_update(
                original_record, {"analysis_evidence_time": "2026-08-22T11:00:00Z"}
            ),
        }
    )

    for field, value in (
        ("formal_eligible", True),
        ("experimental_result", True),
        ("hardware_io_performed", True),
        ("thresholds_applied", True),
        ("classification_performed", True),
        ("analysis_status", "tampered"),
        ("ordered_source_aggregate_sha256", "f" * 64),
    ):
        assert_attack_rejected(
            {"analysis_metadata.json": _canonical_update(original_metadata, {field: value})}
        )
    assert_attack_rejected(
        {
            "analysis_record.json": _canonical_update(
                original_record, {"immutable_status": "partial"}
            )
        }
    )
    assert_attack_rejected(
        {
            "analysis_record.json": _canonical_update(
                original_record, {"analysis_relative_path": "analyses/analysis_foreign"}
            )
        }
    )

    changed_metadata_state = _canonical_update(original_metadata, {"formal_eligible": True})
    changed_record_state = _canonical_update(original_record, {"formal_eligible": True})
    assert_attack_rejected(
        {
            "analysis_metadata.json": changed_metadata_state,
            "analysis_record.json": changed_record_state,
        }
    )
    receipt_with_changed_hashes = _canonical_update(
        original_receipt,
        {
            "analysis_metadata_sha256": hashlib.sha256(changed_metadata_state).hexdigest(),
            "analysis_record_sha256": hashlib.sha256(changed_record_state).hexdigest(),
        },
    )
    assert_attack_rejected(
        {
            "analysis_metadata.json": changed_metadata_state,
            "analysis_record.json": changed_record_state,
            "analysis_receipt.json": receipt_with_changed_hashes,
        }
    )
    changed_receipt_digest = hashlib.sha256(receipt_with_changed_hashes).hexdigest()
    assert_attack_rejected(
        {
            "analysis_metadata.json": changed_metadata_state,
            "analysis_record.json": changed_record_state,
            "analysis_receipt.json": receipt_with_changed_hashes,
            "analysis_receipt.sha256": (
                f"{changed_receipt_digest}  analysis_receipt.json\n".encode("ascii")
            ),
        }
    )
    assert_attack_rejected(
        {
            "analysis_receipt.json": _canonical_update(
                original_receipt,
                {"schema_version": "1.0.0", "algorithm_version": "1.0.0"},
            )
        }
    )
    assert_attack_rejected(
        {
            "analysis_receipt.json": _canonical_update(
                original_receipt, remove=("analysis_metadata_sha256",)
            )
        }
    )
    assert_attack_rejected(
        {"analysis_receipt.json": _canonical_update(original_receipt, {"unexpected": "extra"})}
    )
    parsed_receipt = json.loads(original_receipt)
    assert_attack_rejected(
        {
            "analysis_receipt.json": _canonical_update(
                original_receipt,
                {
                    "analysis_metadata_sha256": parsed_receipt["analysis_record_sha256"],
                    "analysis_record_sha256": parsed_receipt["analysis_metadata_sha256"],
                },
            )
        }
    )
    assert _tree(left_store.analyses_root) == original_left_tree
    assert receipt_path.read_bytes() == original_receipt
    assert receipt_sidecar_path.read_bytes() == original_receipt_sidecar

    with pytest.raises(AnalysisPersistenceError, match="already exists"):
        compute_synthetic_measurement_matrix(
            store=left_store,
            sources=left_sources,
            analysis_spec=analysis_spec,
            analysis_id="stages-1-4",
        )
    stale_lock = left_store.analyses_root / ".analysis_stale.lock"
    stale_lock.write_bytes(b"")
    with pytest.raises(AnalysisPersistenceError, match="already in progress"):
        compute_synthetic_measurement_matrix(
            store=left_store,
            sources=left_sources,
            analysis_spec=analysis_spec,
            analysis_id="stale",
        )
    assert stale_lock.read_bytes() == b""
    stale_lock.unlink()

    right_receipt = Path(right.analysis_path) / "analysis_receipt.json"
    right_receipt.write_bytes(right_receipt.read_bytes().replace(b"344", b"343", 1))
    with pytest.raises(AnalysisPersistenceError, match="full replay"):
        validate_synthetic_measurement_matrix(
            store=right_store,
            sources=tuple(reversed(right_sources)),
            analysis_spec=analysis_spec,
            analysis_id="stages-1-4",
        )
