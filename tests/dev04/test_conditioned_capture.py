from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.audio.condition_plan import load_development_condition_plan
from acoustic_ladder.audio.conditioned_virtual_capture import (
    ConditionedVirtualCapturePersistenceError,
    load_conditioned_virtual_capture_scenario,
    publish_conditioned_virtual_capture,
    validate_conditioned_virtual_capture,
)
from acoustic_ladder.audio.ess_processing_persistence import publish_ess_processing
from acoustic_ladder.audio.excitation_persistence import publish_offline_ess_artifact
from acoustic_ladder.audio.provisional_qc_persistence import publish_provisional_qc
from acoustic_ladder.audio.repeatability_models import RepeatabilityMemberIdentity
from acoustic_ladder.audio.repeatability_persistence import (
    RepeatabilityPersistenceError,
    publish_provisional_repeatability,
)
from acoustic_ladder.config.bundle import LoadedBundle, load_bundle
from acoustic_ladder.domain.models import DataOrigin, ReassemblyRecord, RunMode, SessionRecord
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore

PROJECT_ROOT = Path(__file__).parents[2]
PLAN_PATH = (
    PROJECT_ROOT / "tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml"
)
SCENARIO_PATH = PROJECT_ROOT / "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml"
FIXED_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _conditioned_bundle() -> LoadedBundle:
    return load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols/stage1_single_bridge.yaml",
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=(
            PROJECT_ROOT / "tests/fixtures/synthetic/stage1_conditioned_development.yaml"
        ),
        now=lambda: FIXED_TIME,
    )


def _setup(tmp_path: Path) -> tuple[ImmutableSessionStore, LoadedBundle, Path, Path]:
    synthetic_root = tmp_path / "synthetic"
    real_root = tmp_path / "real"
    store = ImmutableSessionStore(DataRoots(synthetic=synthetic_root, real=real_root))
    bundle = _conditioned_bundle()
    session = SessionRecord(
        session_id="condition-session",
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
        notes="condition-aware virtual capture test",
    )
    reassemblies = [
        ReassemblyRecord(
            reassembly_id=reassembly_id,
            session_id=session.session_id,
            sequence_index=index,
            created_at=FIXED_TIME,
            assembly_description="condition-aware development fixture",
            operator_confirmation=False,
            related_run_ids=[],
        )
        for index, reassembly_id in enumerate(session.reassembly_ids)
    ]
    store.create_synthetic_session(session, reassemblies, bundle)
    ess = publish_offline_ess_artifact(tmp_path / "ess", "source-ess", bundle.configs["audio"])
    return store, bundle, ess.artifact_root, real_root


def test_all_blk_condition_is_published_and_replayed_with_bound_node_states(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root, real_root = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(
        SCENARIO_PATH,
        project_root=PROJECT_ROOT,
    )

    published = publish_conditioned_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        condition_id="all_blk",
        ess_artifact_root=ess_root,
        session_id="condition-session",
        reassembly_id="blk-a",
        run_id="blk-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    replayed = validate_conditioned_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="condition-session",
        run_id="blk-1",
    )
    run = store.validate_run(DataOrigin.SYNTHETIC, "condition-session", "blk-1")

    assert replayed.receipt == published.receipt
    assert published.receipt.condition_id == "all_blk"
    assert published.receipt.condition_role == "all_blk_reference"
    assert published.receipt.condition_binding_performed is True
    assert published.receipt.protocol_condition_binding_performed is True
    assert published.receipt.protocol_execution_performed is False
    assert {state.module_id for state in published.receipt.resolved_node_states.values()} == {"BLK"}
    assert run.node_states == published.receipt.resolved_node_states
    assert published.receipt.synthetic_ir_raw_sha256
    assert set(published.receipt.manifest_node_delay_samples) == set(run.node_states)
    assert set(published.receipt.manifest_module_node_weights) == set(run.node_states)
    assert published.receipt.hardware_io_performed is False
    assert published.receipt.formal_eligible is False
    assert published.receipt.experimental_result is False
    assert not real_root.exists()


def test_conditioned_capture_can_feed_existing_processing_public_api(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(
        SCENARIO_PATH,
        project_root=PROJECT_ROOT,
    )
    capture = publish_conditioned_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        condition_id="n1_b40",
        ess_artifact_root=ess_root,
        session_id="condition-session",
        reassembly_id="candidate-a",
        run_id="candidate-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )

    processing = publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="condition-session",
        source_run_id="candidate-1",
        processing_id="processing-1",
        now=lambda: FIXED_TIME,
    )

    assert processing.receipt.source_capture_receipt_sha256 == capture.receipt_sha256
    assert processing.receipt.source_run_id == "candidate-1"


def test_conditioned_members_feed_qc_and_bind_repeatability_condition_provenance(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root, _ = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    identities: list[RepeatabilityMemberIdentity] = []
    for order in range(2):
        run_id = f"candidate-{order + 1}"
        processing_id = f"processing-{order + 1}"
        qc_id = f"qc-{order + 1}"
        publish_conditioned_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            condition_id="n1_b40",
            ess_artifact_root=ess_root,
            session_id="condition-session",
            reassembly_id="candidate-a",
            run_id=run_id,
            measurement_order=order,
            now=lambda: FIXED_TIME,
        )
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="condition-session",
            source_run_id=run_id,
            processing_id=processing_id,
            now=lambda: FIXED_TIME,
        )
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="condition-session",
            source_run_id=run_id,
            processing_id=processing_id,
            qc_id=qc_id,
            now=lambda: FIXED_TIME,
        )
        identities.append(
            RepeatabilityMemberIdentity(
                source_run_id=run_id,
                processing_id=processing_id,
                qc_id=qc_id,
            )
        )

    repeatability = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="condition-session",
        repeat_set_id="candidate-set",
        members=identities,
        now=lambda: FIXED_TIME,
    )

    assert repeatability.receipt.schema_version == "1.2.0"
    assert repeatability.receipt.condition_id == "n1_b40"
    assert repeatability.receipt.condition_role == "single_bridge_candidate"
    assert repeatability.receipt.resolved_node_states == plan.binding("n1_b40").resolved_node_states
    assert repeatability.receipt.protocol_condition_binding_performed is True
    assert repeatability.receipt.baseline_assigned is False


def test_candidate_has_exactly_one_bridge_and_response_differs_from_all_blk(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root, _ = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    baseline = publish_conditioned_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        condition_id="all_blk",
        ess_artifact_root=ess_root,
        session_id="condition-session",
        reassembly_id="blk-a",
        run_id="blk-response",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    candidate = publish_conditioned_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        condition_id="n1_b40",
        ess_artifact_root=ess_root,
        session_id="condition-session",
        reassembly_id="candidate-a",
        run_id="candidate-response",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )

    non_blk = {
        node_id: state.module_id
        for node_id, state in candidate.receipt.resolved_node_states.items()
        if state.module_id != "BLK"
    }
    assert non_blk == {"N1": "B40"}
    assert baseline.receipt.synthetic_ir_raw_sha256 != candidate.receipt.synthetic_ir_raw_sha256
    assert (baseline.run_path / "simulated_input.wav").read_bytes() != (
        candidate.run_path / "simulated_input.wav"
    ).read_bytes()
    assert (
        candidate.receipt.manifest_module_node_weights["N1"]
        != (baseline.receipt.manifest_module_node_weights["N1"])
    )


def test_tail_coverage_is_rejected_before_run_publication(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario_path = tmp_path / "short-tail.yaml"
    scenario_path.write_text(
        SCENARIO_PATH.read_text(encoding="utf-8").replace(
            "capture_tail_samples: 160", "capture_tail_samples: 0"
        ),
        encoding="utf-8",
    )
    scenario = load_conditioned_virtual_capture_scenario(scenario_path, project_root=tmp_path)

    with pytest.raises(ConditionedVirtualCapturePersistenceError) as failure:
        publish_conditioned_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            condition_id="n1_b40",
            ess_artifact_root=ess_root,
            session_id="condition-session",
            reassembly_id="candidate-a",
            run_id="short-tail",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )

    assert failure.value.published is False
    assert not (
        store.session_path(DataOrigin.SYNTHETIC, "condition-session") / "raw/run_short-tail"
    ).exists()


def test_condition_plan_source_tamper_is_rejected_by_capture_replay(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _setup(tmp_path)
    plan_path = tmp_path / "condition-plan.yaml"
    scenario_path = tmp_path / "scenario.yaml"
    original_plan = PLAN_PATH.read_bytes()
    plan_path.write_bytes(original_plan)
    scenario_path.write_bytes(SCENARIO_PATH.read_bytes())
    protocol_path = tmp_path / "config/protocols/stage1_single_bridge.yaml"
    protocol_path.parent.mkdir(parents=True)
    protocol_path.write_bytes(
        (PROJECT_ROOT / "config/protocols/stage1_single_bridge.yaml").read_bytes()
    )
    plan = load_development_condition_plan(plan_path, project_root=tmp_path, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(scenario_path, project_root=tmp_path)
    published = publish_conditioned_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=plan,
        condition_id="all_blk",
        ess_artifact_root=ess_root,
        session_id="condition-session",
        reassembly_id="blk-a",
        run_id="tamper-plan",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    before = published.receipt_sha256
    plan_path.write_bytes(plan_path.read_bytes() + b"\n")

    with pytest.raises(ConditionedVirtualCapturePersistenceError):
        validate_conditioned_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="condition-session",
            run_id="tamper-plan",
        )

    assert published.receipt_sha256 == before
    plan_path.write_bytes(original_plan)
    protocol_path.write_bytes(protocol_path.read_bytes() + b"\n")
    with pytest.raises(ConditionedVirtualCapturePersistenceError, match="source protocol"):
        validate_conditioned_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="condition-session",
            run_id="tamper-plan",
        )


def test_repeatability_rejects_mixed_condition_members(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _setup(tmp_path)
    plan = load_development_condition_plan(PLAN_PATH, project_root=PROJECT_ROOT, bundle=bundle)
    scenario = load_conditioned_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    members: list[RepeatabilityMemberIdentity] = []
    for order, condition_id in enumerate(("all_blk", "n1_b40")):
        run_id = f"mixed-{order}"
        processing_id = f"mixed-processing-{order}"
        qc_id = f"mixed-qc-{order}"
        publish_conditioned_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            condition_plan=plan,
            condition_id=condition_id,
            ess_artifact_root=ess_root,
            session_id="condition-session",
            reassembly_id="candidate-a",
            run_id=run_id,
            measurement_order=order,
            now=lambda: FIXED_TIME,
        )
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="condition-session",
            source_run_id=run_id,
            processing_id=processing_id,
            now=lambda: FIXED_TIME,
        )
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="condition-session",
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

    with pytest.raises(RepeatabilityPersistenceError, match="compatible provenance"):
        publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="condition-session",
            repeat_set_id="mixed-set",
            members=members,
            now=lambda: FIXED_TIME,
        )
