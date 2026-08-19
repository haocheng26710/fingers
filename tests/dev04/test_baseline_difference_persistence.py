from __future__ import annotations

import hashlib
import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

import acoustic_ladder.storage.store as store_module
from acoustic_ladder import cli
from acoustic_ladder.audio.baseline_difference_models import (
    BaselineDifferenceCreatedEvent,
    RepeatabilitySourceIdentity,
)
from acoustic_ladder.audio.baseline_difference_persistence import (
    BASELINE_DIFFERENCE_FILE_NAMES,
    BaselineDifferencePersistenceError,
    publish_provisional_baseline_difference,
    validate_provisional_baseline_difference,
)
from acoustic_ladder.audio.condition_plan import load_development_condition_plan
from acoustic_ladder.audio.conditioned_virtual_capture import (
    load_conditioned_virtual_capture_scenario,
    publish_conditioned_virtual_capture,
)
from acoustic_ladder.audio.ess_processing_persistence import publish_ess_processing
from acoustic_ladder.audio.excitation_persistence import publish_offline_ess_artifact
from acoustic_ladder.audio.provisional_qc_persistence import publish_provisional_qc
from acoustic_ladder.audio.repeatability_models import RepeatabilityMemberIdentity
from acoustic_ladder.audio.repeatability_persistence import publish_provisional_repeatability
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes, load_bundle
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.domain.models import DataOrigin, ReassemblyRecord, RunMode, SessionRecord
from acoustic_ladder.storage.io import StorageError
from acoustic_ladder.storage.npz import load_deterministic_npz
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore

PROJECT_ROOT = Path(__file__).parents[2]
PLAN_PATH = (
    PROJECT_ROOT / "tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml"
)
SCENARIO_PATH = PROJECT_ROOT / "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml"
FIXED_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _bundle() -> LoadedBundle:
    return load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols/stage1_single_bridge.yaml",
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT
        / "tests/fixtures/synthetic/stage1_conditioned_development.yaml",
        now=lambda: FIXED_TIME,
    )


def _setup(tmp_path: Path) -> tuple[ImmutableSessionStore, LoadedBundle, Path]:
    store = ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "synthetic", real=tmp_path / "real")
    )
    bundle = _bundle()
    session = SessionRecord(
        session_id="comparison-session",
        session_schema_version="1.0.0",
        created_at=FIXED_TIME,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        operator=None,
        device_manifest_reference="manifest/device_manifest.provisional.json",
        config_bundle_reference="protocol/config_bundle.json",
        reassembly_ids=["blk-a", "candidate-a"],
        run_ids=[],
        immutable_status="immutable",
        notes="baseline difference persistence test",
    )
    reassemblies = [
        ReassemblyRecord(
            reassembly_id=reassembly_id,
            session_id=session.session_id,
            sequence_index=index,
            created_at=FIXED_TIME,
            assembly_description="condition-bound fixture",
            operator_confirmation=False,
            related_run_ids=[],
        )
        for index, reassembly_id in enumerate(session.reassembly_ids)
    ]
    store.create_synthetic_session(session, reassemblies, bundle)
    ess = publish_offline_ess_artifact(tmp_path / "ess", "comparison-ess", bundle.configs["audio"])
    return store, bundle, ess.artifact_root


def _publish_source(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    ess_root: Path,
    condition_id: str,
    reassembly_id: str,
    prefix: str,
    member_count: int = 2,
) -> RepeatabilitySourceIdentity:
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    members: list[RepeatabilityMemberIdentity] = []
    for order in range(member_count):
        run_id = f"{prefix}-run-{order + 1}"
        processing_id = f"{prefix}-processing-{order + 1}"
        qc_id = f"{prefix}-qc-{order + 1}"
        publish_conditioned_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            condition_id=condition_id,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            reassembly_id=reassembly_id,
            run_id=run_id,
            measurement_order=order,
            now=lambda: FIXED_TIME,
        )
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            source_run_id=run_id,
            processing_id=processing_id,
            now=lambda: FIXED_TIME,
        )
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            source_run_id=run_id,
            processing_id=processing_id,
            qc_id=qc_id,
            now=lambda: FIXED_TIME,
        )
        members.append(
            RepeatabilityMemberIdentity(
                source_run_id=run_id,
                processing_id=processing_id,
                qc_id=qc_id,
            )
        )
    repeat_set_id = f"{prefix}-set"
    publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="comparison-session",
        repeat_set_id=repeat_set_id,
        members=members,
        now=lambda: FIXED_TIME,
    )
    return RepeatabilitySourceIdentity(repeat_set_id=repeat_set_id, members=members)


def _sources(
    store: ImmutableSessionStore, bundle: LoadedBundle, ess_root: Path
) -> tuple[RepeatabilitySourceIdentity, RepeatabilitySourceIdentity]:
    candidate = _publish_source(
        store=store,
        bundle=bundle,
        ess_root=ess_root,
        condition_id="n1_b40",
        reassembly_id="candidate-a",
        prefix="candidate",
    )
    baseline = _publish_source(
        store=store,
        bundle=bundle,
        ess_root=ess_root,
        condition_id="all_blk",
        reassembly_id="blk-a",
        prefix="baseline",
    )
    return candidate, baseline


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_publish_and_read_only_replay_exact_condition_bound_envelope(tmp_path: Path) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first, second = _sources(store, bundle, ess_root)

    published = publish_provisional_baseline_difference(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        ess_artifact_root=ess_root,
        session_id="comparison-session",
        comparison_id="comparison-1",
        source_a=first,
        source_b=second,
        now=lambda: FIXED_TIME,
    )
    replayed = validate_provisional_baseline_difference(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        ess_artifact_root=ess_root,
        session_id="comparison-session",
        comparison_id="comparison-1",
        source_a=first,
        source_b=second,
    )

    assert {path.name for path in published.comparison_path.iterdir()} == (
        BASELINE_DIFFERENCE_FILE_NAMES
    )
    assert replayed.receipt == published.receipt
    assert published.receipt.baseline_source.condition_role == "all_blk_reference"
    assert published.receipt.candidate_source.condition_role == "single_bridge_candidate"
    assert published.receipt.baseline_source.reassembly_id == "blk-a"
    assert published.receipt.candidate_source.reassembly_id == "candidate-a"
    assert published.receipt.baseline_assigned is True
    assert published.receipt.baseline_difference_computed is True
    assert published.receipt.decision_status == "not_evaluated"
    assert published.receipt.thresholds_applied is False
    assert published.receipt.hardware_io_performed is False
    assert published.receipt.formal_eligible is False
    assert published.receipt.experimental_result is False
    assert published.metrics.raw_ir.difference_l2 > 0
    assert not (tmp_path / "real").exists()


def test_validator_rejects_byte_attacks_without_writing_and_recovers_after_restore(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first, second = _sources(store, bundle, ess_root)
    published = publish_provisional_baseline_difference(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        ess_artifact_root=ess_root,
        session_id="comparison-session",
        comparison_id="attacks",
        source_a=first,
        source_b=second,
        now=lambda: FIXED_TIME,
    )
    arguments = {
        "store": store,
        "bundle": bundle,
        "scenario": scenario,
        "condition_plan": plan,
        "ess_artifact_root": ess_root,
        "session_id": "comparison-session",
        "comparison_id": "attacks",
        "source_a": first,
        "source_b": second,
    }
    root = published.comparison_path
    targets = [
        root / "baseline_difference_arrays.npz.sha256",
        root / "BASELINE_DIFFERENCE_COMPLETE",
        root / "baseline_difference_receipt.json",
        root / "condition_binding.json",
        root / "baseline_difference_metadata.json",
        root / "baseline_difference_record.json",
    ]
    for target in targets:
        original = target.read_bytes()
        target.write_bytes(original + b"\r\n")
        before = _tree_hash(store.session_path(DataOrigin.SYNTHETIC, "comparison-session"))
        with pytest.raises(BaselineDifferencePersistenceError):
            validate_provisional_baseline_difference(**arguments)
        assert _tree_hash(store.session_path(DataOrigin.SYNTHETIC, "comparison-session")) == before
        target.write_bytes(original)
        validate_provisional_baseline_difference(**arguments)

    extra = root / "unexpected.bin"
    extra.write_bytes(b"unexpected")
    with pytest.raises(BaselineDifferencePersistenceError, match="exactly"):
        validate_provisional_baseline_difference(**arguments)
    extra.unlink()
    validate_provisional_baseline_difference(**arguments)

    event = next(
        (store.session_path(DataOrigin.SYNTHETIC, "comparison-session") / "events").glob(
            "*_baseline_difference_created.json"
        )
    )
    event_bytes = event.read_bytes()
    event.unlink()
    with pytest.raises(BaselineDifferencePersistenceError, match="exactly one"):
        validate_provisional_baseline_difference(**arguments)
    event.write_bytes(event_bytes)
    duplicate = event.with_name("999999_baseline_difference_created.json")
    duplicate.write_bytes(event_bytes.replace(b'"sequence":', b'"sequence":999999,"old_sequence":'))
    with pytest.raises(BaselineDifferencePersistenceError):
        validate_provisional_baseline_difference(**arguments)
    duplicate.unlink()
    validate_provisional_baseline_difference(**arguments)
    event_payload = BaselineDifferenceCreatedEvent.model_validate_json(event_bytes).model_dump(
        mode="python"
    )
    for field, value in (
        ("candidate_repeat_set_id", "wrong-set"),
        ("created_at", datetime(2026, 8, 19, 13, 0, tzinfo=UTC)),
        ("arrays_sha256", "0" * 64),
    ):
        attacked = {**event_payload, field: value}
        event.write_bytes(
            canonical_json_bytes(
                BaselineDifferenceCreatedEvent.model_validate(attacked).model_dump(mode="json")
            )
        )
        with pytest.raises(BaselineDifferencePersistenceError, match="event binding differs"):
            validate_provisional_baseline_difference(**arguments)
        event.write_bytes(event_bytes)
        validate_provisional_baseline_difference(**arguments)


def test_duplicate_publication_is_create_only(tmp_path: Path) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first, second = _sources(store, bundle, ess_root)
    arguments = {
        "store": store,
        "bundle": bundle,
        "scenario": scenario,
        "condition_plan": plan,
        "ess_artifact_root": ess_root,
        "session_id": "comparison-session",
        "comparison_id": "duplicate",
        "source_a": first,
        "source_b": second,
        "now": lambda: FIXED_TIME,
    }
    original = publish_provisional_baseline_difference(**arguments)
    before = _tree_hash(original.comparison_path)

    with pytest.raises(BaselineDifferencePersistenceError) as failure:
        publish_provisional_baseline_difference(**arguments)

    assert failure.value.published is True
    assert _tree_hash(original.comparison_path) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("baseline_selection_rule", "all_blk"),
        ("features", ["magnitude"]),
        ("normalization", "zscore"),
        ("cross_validation_strategy", "group_k_fold"),
        ("qc_threshold", 0.1),
        ("effect_threshold", 0.1),
        ("drift_threshold", 0.1),
        ("classification_pass_threshold", 0.1),
        ("smoothing", True),
    ],
)
def test_analysis_authority_is_rejected_before_comparison_parent_creation(
    tmp_path: Path, field: str, value: object
) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first, second = _sources(store, bundle, ess_root)
    loaded = bundle.configs["analysis"]
    assert isinstance(loaded.model, AnalysisConfig)
    analysis = loaded.model
    if field == "smoothing":
        model = analysis.model_copy(
            update={"smoothing": analysis.smoothing.model_copy(update={"enabled": True})}
        )
    elif field.endswith("_threshold"):
        gates = analysis.decision_gates.model_copy(update={field: value})
        model = analysis.model_copy(update={"decision_gates": gates})
    else:
        model = analysis.model_copy(update={field: value})
    mutated = replace(bundle, configs={**bundle.configs, "analysis": replace(loaded, model=model)})
    session = store.session_path(DataOrigin.SYNTHETIC, "comparison-session")
    before = _tree_hash(session)

    with pytest.raises(BaselineDifferencePersistenceError) as failure:
        publish_provisional_baseline_difference(
            store=store,
            bundle=mutated,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id=f"authority-{field}",
            source_a=first,
            source_b=second,
            now=lambda: FIXED_TIME,
        )

    assert failure.value.published is False
    assert not (session / "processed" / "baseline_differences").exists()
    assert _tree_hash(session) == before
    assert not (tmp_path / "real").exists()


def test_public_comparison_api_has_no_payload_path_role_or_threshold_authority() -> None:
    parameters = inspect.signature(publish_provisional_baseline_difference).parameters
    forbidden = {
        "baseline_role",
        "condition_id",
        "reassembly_id",
        "node_states",
        "waveform",
        "ir",
        "npz",
        "metrics",
        "threshold",
        "decision",
        "real_root",
        "output_path",
    }

    assert forbidden.isdisjoint(parameters)


def test_source_repeatability_tamper_and_unsafe_comparison_id_are_rejected_prepublication(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    candidate, baseline = _sources(store, bundle, ess_root)
    session = store.session_path(DataOrigin.SYNTHETIC, "comparison-session")
    source_receipt = (
        session
        / "qc/repeat_sets/reassembly_candidate-a/repeat_set_candidate-set"
        / "repeatability_receipt.json"
    )
    original = source_receipt.read_bytes()
    source_receipt.write_bytes(original + b"\n")

    with pytest.raises(BaselineDifferencePersistenceError) as tamper_failure:
        publish_provisional_baseline_difference(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id="source-tamper",
            source_a=candidate,
            source_b=baseline,
            now=lambda: FIXED_TIME,
        )
    assert tamper_failure.value.published is False
    assert not (session / "processed/baseline_differences").exists()
    source_receipt.write_bytes(original)

    with pytest.raises(BaselineDifferencePersistenceError) as unsafe_failure:
        publish_provisional_baseline_difference(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id="../escape",
            source_a=candidate,
            source_b=baseline,
            now=lambda: FIXED_TIME,
        )
    assert unsafe_failure.value.published is False
    assert not (session / "processed/baseline_differences").exists()


def test_two_all_blk_sources_are_rejected_before_comparison_parent(tmp_path: Path) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first = _publish_source(
        store=store,
        bundle=bundle,
        ess_root=ess_root,
        condition_id="all_blk",
        reassembly_id="blk-a",
        prefix="baseline-one",
    )
    second = _publish_source(
        store=store,
        bundle=bundle,
        ess_root=ess_root,
        condition_id="all_blk",
        reassembly_id="candidate-a",
        prefix="baseline-two",
    )

    with pytest.raises(BaselineDifferencePersistenceError, match="exactly one all-BLK"):
        publish_provisional_baseline_difference(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id="two-baselines",
            source_a=first,
            source_b=second,
            now=lambda: FIXED_TIME,
        )

    assert not (
        store.session_path(DataOrigin.SYNTHETIC, "comparison-session")
        / "processed/baseline_differences"
    ).exists()


def test_append_event_failure_reports_published_true_and_keeps_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first, second = _sources(store, bundle, ess_root)

    def reject_event(*args: object, **kwargs: object) -> None:
        raise StorageError("injected append-event failure")

    monkeypatch.setattr(store, "append_event", reject_event)
    with pytest.raises(BaselineDifferencePersistenceError) as failure:
        publish_provisional_baseline_difference(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id="event-failure",
            source_a=first,
            source_b=second,
            now=lambda: FIXED_TIME,
        )

    target = (
        store.session_path(DataOrigin.SYNTHETIC, "comparison-session")
        / "processed/baseline_differences/comparison_event-failure"
    )
    assert failure.value.published is True
    assert (target / "BASELINE_DIFFERENCE_COMPLETE").read_bytes() == b"complete\n"


def test_concurrent_publication_has_one_winner_without_overwrite(tmp_path: Path) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first, second = _sources(store, bundle, ess_root)

    def publish() -> str:
        try:
            result = publish_provisional_baseline_difference(
                store=store,
                bundle=bundle,
                scenario=scenario,
                condition_plan=plan,
                ess_artifact_root=ess_root,
                session_id="comparison-session",
                comparison_id="concurrent",
                source_a=first,
                source_b=second,
                now=lambda: FIXED_TIME,
            )
            return result.receipt_sha256
        except BaselineDifferencePersistenceError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: publish(), range(2)))

    assert outcomes.count("rejected") == 1
    assert len([value for value in outcomes if value != "rejected"]) == 1
    target = (
        store.session_path(DataOrigin.SYNTHETIC, "comparison-session")
        / "processed/baseline_differences/comparison_concurrent"
    )
    assert {path.name for path in target.iterdir()} == BASELINE_DIFFERENCE_FILE_NAMES
    parent = target.parent
    assert not list(parent.glob("*.lock"))
    assert not list(parent.glob("*.staging-*"))


def test_failed_staging_is_cleaned_without_target_or_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first, second = _sources(store, bundle, ess_root)

    def reject_write(path: str | Path, payload: bytes) -> None:
        raise StorageError(f"injected staging write failure: {path} ({len(payload)} bytes)")

    monkeypatch.setattr(store_module, "atomic_write_bytes", reject_write)
    with pytest.raises(BaselineDifferencePersistenceError) as failure:
        publish_provisional_baseline_difference(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id="staging-failure",
            source_a=first,
            source_b=second,
            now=lambda: FIXED_TIME,
        )

    parent = (
        store.session_path(DataOrigin.SYNTHETIC, "comparison-session")
        / "processed/baseline_differences"
    )
    assert failure.value.published is False
    assert not (parent / "comparison_staging-failure").exists()
    assert not list(parent.glob("*.lock"))
    assert not list(parent.glob("*.staging-*"))
    assert not list(
        (store.session_path(DataOrigin.SYNTHETIC, "comparison-session") / "events").glob(
            "*_baseline_difference_created.json"
        )
    )


def test_compute_and_validate_cli_derive_roles_and_emit_receipt_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store, bundle, ess_root = _setup(tmp_path)
    candidate, baseline = _sources(store, bundle, ess_root)

    def member_arguments(flag: str, source: RepeatabilitySourceIdentity) -> list[str]:
        values: list[str] = []
        for member in source.members:
            values.extend(
                [
                    flag,
                    f"{member.source_run_id}:{member.processing_id}:{member.qc_id}",
                ]
            )
        return values

    common = [
        "--project-root",
        str(PROJECT_ROOT),
        "--manifest",
        "config/devices/device_manifest.provisional.json",
        "--manifest-sidecar",
        "config/devices/device_manifest.provisional.sha256",
        "--audio",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "--protocol",
        "config/protocols/stage1_single_bridge.yaml",
        "--analysis",
        "config/analysis/default.yaml",
        "--synthetic",
        "tests/fixtures/synthetic/stage1_conditioned_development.yaml",
        "--synthetic-root",
        str(tmp_path / "synthetic"),
        "--session-id",
        "comparison-session",
        "--comparison-id",
        "cli-comparison",
        "--scenario",
        "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml",
        "--condition-plan",
        "tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml",
        "--ess-artifact-root",
        str(ess_root),
        "--baseline-repeat-set-id",
        candidate.repeat_set_id,
        *member_arguments("--baseline-member", candidate),
        "--candidate-repeat-set-id",
        baseline.repeat_set_id,
        *member_arguments("--candidate-member", baseline),
    ]
    cli.main(["baseline-difference-compute", *common])
    computed = capsys.readouterr().out
    cli.main(["baseline-difference-validate", *common])
    validated = capsys.readouterr().out

    for output in (computed, validated):
        assert "PASS provisional baseline difference" in output
        assert "baseline_condition_id=all_blk" in output
        assert "candidate_condition_id=n1_b40" in output
        assert "baseline_difference_computed=true" in output
        assert "decision_status=not_evaluated" in output
        assert "thresholds_applied=false" in output
        assert "PROTOCOL_CONDITION_BINDING_ONLY" in output
        assert "NO_HARDWARE_AUDIO_IO_PERFORMED" in output
        assert "NOT_AN_EXPERIMENTAL_RESULT" in output


@pytest.mark.parametrize(
    "forbidden",
    ["--threshold", "--output-path", "--real-root", "--baseline-role", "--condition-id"],
)
def test_baseline_difference_cli_has_no_forbidden_authority(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "baseline-difference-compute",
                "--protocol",
                "protocol.yaml",
                "--synthetic-root",
                "synthetic",
                "--session-id",
                "session",
                "--comparison-id",
                "comparison",
                "--scenario",
                "scenario.yaml",
                "--condition-plan",
                "plan.yaml",
                "--ess-artifact-root",
                "ess",
                "--baseline-repeat-set-id",
                "baseline",
                "--baseline-member",
                "run:processing:qc",
                "--candidate-repeat-set-id",
                "candidate",
                "--candidate-member",
                "run2:processing2:qc2",
                forbidden,
                "forbidden",
            ]
        )


def test_two_roots_are_byte_deterministic_with_reversed_members_and_swapped_sources(
    tmp_path: Path,
) -> None:
    outputs = []
    for index, root in enumerate((tmp_path / "a", tmp_path / "b")):
        store, bundle, ess_root = _setup(root)
        plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
        scenario = load_conditioned_virtual_capture_scenario(
            SCENARIO_PATH, project_root=PROJECT_ROOT
        )
        candidate = _publish_source(
            store=store,
            bundle=bundle,
            ess_root=ess_root,
            condition_id="n1_b40",
            reassembly_id="candidate-a",
            prefix="candidate",
            member_count=3,
        )
        baseline = _publish_source(
            store=store,
            bundle=bundle,
            ess_root=ess_root,
            condition_id="all_blk",
            reassembly_id="blk-a",
            prefix="baseline",
            member_count=3,
        )
        if index:
            candidate = candidate.model_copy(update={"members": list(reversed(candidate.members))})
            baseline = baseline.model_copy(update={"members": list(reversed(baseline.members))})
            source_a, source_b = baseline, candidate
        else:
            source_a, source_b = candidate, baseline
        published = publish_provisional_baseline_difference(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id="double-root",
            source_a=source_a,
            source_b=source_b,
            now=lambda: FIXED_TIME,
        )
        validate_provisional_baseline_difference(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            ess_artifact_root=ess_root,
            session_id="comparison-session",
            comparison_id="double-root",
            source_a=source_b,
            source_b=source_a,
        )
        arrays = load_deterministic_npz(
            (published.comparison_path / "baseline_difference_arrays.npz").read_bytes()
        )
        assert all(
            np.all(np.isfinite(value)) for value in arrays.values() if value.dtype != np.bool_
        )
        assert published.receipt.baseline_source.non_blk_node_count == 0
        assert published.receipt.candidate_source.non_blk_node_count == 1
        assert len(published.receipt.baseline_source.members) == 3
        assert len(published.receipt.candidate_source.members) == 3
        assert published.metrics.raw_ir.difference_l2 > 0
        assert not (root / "real").exists()
        payload_names = (
            "condition_binding.json",
            "condition_binding.sha256",
            "baseline_difference_arrays.npz",
            "baseline_difference_arrays.npz.sha256",
            "baseline_difference_metrics.json",
            "baseline_difference_metrics.sha256",
            "baseline_difference_receipt.json",
            "baseline_difference_receipt.sha256",
            "baseline_difference_metadata.json",
        )
        outputs.append(
            {name: (published.comparison_path / name).read_bytes() for name in payload_names}
        )

    assert outputs[0] == outputs[1]
    expected_sha256 = {
        "condition_binding.json": (
            "4dd706337e9bf68df80f4b4f315e3701bb4748d8899abab633d2d020c2937093"
        ),
        "condition_binding.sha256": (
            "570d00e4df23860864cc081221b4dbc00c254a8125207e41db5663a833aafbaa"
        ),
        "baseline_difference_arrays.npz": (
            "0e4be4450b31ef7f9d5c4965a5a70ec5446f30a06394ec1210af75d41185e97a"
        ),
        "baseline_difference_arrays.npz.sha256": (
            "3f0dd00290b5ee5b9fe419d27ce2b6e35d90c01dad7f43f02b29a9f416a5f2e0"
        ),
        "baseline_difference_metrics.json": (
            "4fe1c19ae028bcab210b9f7b0ae32233b553b379c988f959b1fa2823169c9c57"
        ),
        "baseline_difference_metrics.sha256": (
            "cb13460f8d7c370f7a9765fbefc0f181c611cd0ffedf13b42f5ec6931db5e82a"
        ),
        "baseline_difference_receipt.json": (
            "c62e2e798872b0462380aa4e8f017b315c0bc131e3f3a254fcb89534539368cf"
        ),
        "baseline_difference_receipt.sha256": (
            "b72ec605c3f6f170bc0c449c3b7ae6d2953d21dfd1f0fcb5118de84b7b76a456"
        ),
        "baseline_difference_metadata.json": (
            "a7c5dd2db64d9741b712446c7859c287aabc0776bb0bc3e63a3d65a87e138772"
        ),
    }
    assert {
        name: hashlib.sha256(payload).hexdigest() for name, payload in outputs[0].items()
    } == expected_sha256
