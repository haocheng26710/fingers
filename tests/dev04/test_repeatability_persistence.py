from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from acoustic_ladder import cli
from acoustic_ladder.audio.ess_processing_persistence import publish_ess_processing
from acoustic_ladder.audio.excitation_persistence import publish_offline_ess_artifact
from acoustic_ladder.audio.provisional_qc_persistence import publish_provisional_qc
from acoustic_ladder.audio.repeatability_models import (
    ProvisionalRepeatabilityReceipt,
    PublishedProvisionalRepeatability,
    RepeatabilityMemberIdentity,
)
from acoustic_ladder.audio.repeatability_persistence import (
    REPEATABILITY_COMPLETE_BYTES,
    REPEATABILITY_FILE_NAMES,
    RepeatabilityPersistenceError,
    publish_provisional_repeatability,
    validate_provisional_repeatability,
)
from acoustic_ladder.audio.virtual_capture_models import (
    LoadedVirtualCaptureScenario,
    load_virtual_capture_scenario,
)
from acoustic_ladder.audio.virtual_capture_persistence import publish_virtual_capture
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.domain.models import (
    DataOrigin,
    ReassemblyRecord,
    RunMode,
    SessionRecord,
)
from acoustic_ladder.storage.io import StorageError
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore
from tests.dev03.test_virtual_capture import (
    FIXED_TIME,
    PROJECT_ROOT,
    SCENARIO_PATH,
    _capture_setup,
    _development_bundle,
)


def _members(count: int = 2) -> list[RepeatabilityMemberIdentity]:
    return [
        RepeatabilityMemberIdentity(
            source_run_id=f"capture-{index}",
            processing_id="processing-1",
            qc_id="qc-1",
        )
        for index in range(1, count + 1)
    ]


def _clock(timestamp: datetime) -> Callable[[], datetime]:
    return lambda: timestamp


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _setup(
    tmp_path: Path,
    *,
    member_count: int = 2,
) -> tuple[ImmutableSessionStore, LoadedBundle, LoadedVirtualCaptureScenario, Path, Path]:
    store, bundle, ess_root, real_root = _capture_setup(tmp_path)
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    for order, identity in enumerate(_members(member_count)):
        timestamp = FIXED_TIME + timedelta(seconds=order)
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id=identity.source_run_id,
            measurement_order=order,
            now=_clock(timestamp),
        )
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id=identity.source_run_id,
            processing_id=identity.processing_id,
            now=_clock(timestamp),
        )
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id=identity.source_run_id,
            processing_id=identity.processing_id,
            qc_id=identity.qc_id,
            now=_clock(timestamp),
        )
    return store, bundle, scenario, ess_root, real_root


def test_repeatability_publication_and_read_only_replay(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, real_root = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="repeat-1",
        members=list(reversed(_members())),
        now=lambda: FIXED_TIME,
    )

    assert published.repeatability_path == (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "qc/repeat_sets/reassembly_assembly-1/repeat_set_repeat-1"
    )
    assert {entry.name for entry in published.repeatability_path.iterdir()} == (
        REPEATABILITY_FILE_NAMES
    )
    assert (
        published.repeatability_path / "REPEATABILITY_COMPLETE"
    ).read_bytes() == REPEATABILITY_COMPLETE_BYTES
    assert [member.measurement_order for member in published.receipt.members] == [0, 1]
    assert published.metrics.pair_count == 1
    assert published.receipt.baseline_assigned is False
    assert published.receipt.thresholds_applied is False
    assert not real_root.exists()

    before = {path.name: path.read_bytes() for path in published.repeatability_path.iterdir()}
    validated = validate_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="repeat-1",
        members=_members(),
    )
    after = {path.name: path.read_bytes() for path in published.repeatability_path.iterdir()}
    assert validated.metrics == published.metrics
    assert validated.receipt == published.receipt
    assert after == before


def test_repeatability_duplicate_is_create_only(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    first = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="repeat-1",
        members=_members(),
        now=lambda: FIXED_TIME,
    )
    before = {path.name: path.read_bytes() for path in first.repeatability_path.iterdir()}
    with pytest.raises(RepeatabilityPersistenceError, match="already exists"):
        publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="repeat-1",
            members=_members(),
            now=lambda: FIXED_TIME,
        )
    assert {path.name: path.read_bytes() for path in first.repeatability_path.iterdir()} == before


def test_repeatability_api_has_only_identity_authority() -> None:
    allowed = {
        "store",
        "bundle",
        "scenario",
        "ess_artifact_root",
        "session_id",
        "repeat_set_id",
        "members",
        "now",
    }
    assert set(inspect.signature(publish_provisional_repeatability).parameters) == allowed
    assert set(inspect.signature(validate_provisional_repeatability).parameters) == allowed - {
        "now"
    }


def test_unsafe_repeat_set_is_rejected_without_repeatability_directory(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    repeat_sets = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "qc/repeat_sets"
    with pytest.raises(RepeatabilityPersistenceError, match="unsafe repeat_set_id"):
        publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="../escape",
            members=_members(),
            now=lambda: FIXED_TIME,
        )
    assert not repeat_sets.exists()


def test_repeatability_cli_compute_then_validate_has_fixed_safety_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store, _, _, ess_root, _ = _setup(tmp_path)
    arguments = [
        "--project-root",
        str(PROJECT_ROOT),
        "--audio",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "--protocol",
        "config/protocols/stage4_four_node_states.yaml",
        "--synthetic-root",
        str(store.roots.synthetic),
        "--session-id",
        "capture-session",
        "--repeat-set-id",
        "cli-repeat",
        "--member",
        "capture-2:processing-1:qc-1",
        "--member",
        "capture-1:processing-1:qc-1",
        "--scenario",
        "tests/fixtures/audio/virtual_duplex_development.yaml",
        "--ess-artifact-root",
        str(ess_root),
    ]
    cli.main(["repeatability-compute", *arguments])
    computed = capsys.readouterr().out
    cli.main(["repeatability-validate", *arguments])
    validated = capsys.readouterr().out
    markers = (
        "SYNTHETIC_ONLY",
        "PROVISIONAL_REPEATABILITY_METRICS_ONLY",
        "REPEATABILITY_NOT_EVALUATED",
        "THRESHOLDS_NOT_APPLIED",
        "BASELINE_NOT_ASSIGNED",
        "BASELINE_SELECTION_DEFERRED_UNTIL_PROTOCOL_BINDING",
        "NO_BASELINE_DIFFERENCE_COMPUTED",
        "DRIFT_NOT_EVALUATED",
        "NO_HARDWARE_AUDIO_IO_PERFORMED",
        "NOT_AN_EXPERIMENTAL_RESULT",
    )
    for output in (computed, validated):
        assert all(marker in output for marker in markers)
        assert "member_count=2" in output
        assert "pair_count=1" in output


@pytest.mark.parametrize(
    "forbidden",
    ["--real-root", "--threshold", "--baseline", "--wav", "--npz", "--device"],
)
def test_repeatability_cli_rejects_forbidden_authority_options(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "repeatability-compute",
                "--protocol",
                "config/protocols/stage4_four_node_states.yaml",
                "--synthetic-root",
                "synthetic",
                "--session-id",
                "session",
                "--repeat-set-id",
                "repeat",
                "--member",
                "capture1:processing1:qc1",
                "--member",
                "capture2:processing1:qc1",
                "--scenario",
                "scenario.yaml",
                "--ess-artifact-root",
                "ess",
                forbidden,
                "value",
            ]
        )


def test_repeatability_cli_rejects_malformed_member() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "repeatability-compute",
                "--protocol",
                "config/protocols/stage4_four_node_states.yaml",
                "--synthetic-root",
                "synthetic",
                "--session-id",
                "session",
                "--repeat-set-id",
                "repeat",
                "--member",
                "not-a-triple",
                "--scenario",
                "scenario.yaml",
                "--ess-artifact-root",
                "ess",
            ]
        )


def test_three_member_payloads_are_deterministic_across_independent_roots(
    tmp_path: Path,
) -> None:
    published: list[PublishedProvisionalRepeatability] = []
    for root_name, reversed_input in (("first", False), ("second", True)):
        store, bundle, scenario, ess_root, real_root = _setup(tmp_path / root_name, member_count=3)
        members = _members(3)
        result = publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="repeatset001",
            members=list(reversed(members)) if reversed_input else members,
            now=lambda: FIXED_TIME,
        )
        validate_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="repeatset001",
            members=members,
        )
        assert [member.measurement_order for member in result.receipt.members] == [0, 1, 2]
        assert result.metrics.pair_count == 3
        assert not real_root.exists()
        published.append(result)
    deterministic = (
        "repeatability_metrics.json",
        "repeatability_metrics.sha256",
        "repeatability_receipt.json",
        "repeatability_receipt.sha256",
        "repeatability_metadata.json",
    )
    for name in deterministic:
        assert (published[0].repeatability_path / name).read_bytes() == (
            published[1].repeatability_path / name
        ).read_bytes()
    assert (
        hashlib.sha256(
            (published[0].repeatability_path / "repeatability_metrics.json").read_bytes()
        ).hexdigest()
        == "730872025244fb847b6ed9937865017b9563cb030865fb8bac193ea0cd2928b3"
    )
    assert (
        hashlib.sha256(
            (published[0].repeatability_path / "repeatability_metrics.sha256").read_bytes()
        ).hexdigest()
        == "2581bdb2b036e87035e5f0da5e45c93d173b4e75d84eb71b4279b6a76853a6c8"
    )
    assert (
        hashlib.sha256(
            (published[0].repeatability_path / "repeatability_receipt.json").read_bytes()
        ).hexdigest()
        == "916b67b54bc1f4ec59176ce57a6160d6de0c7a8c68c902a4597283d5f5a27f60"
    )
    assert (
        hashlib.sha256(
            (published[0].repeatability_path / "repeatability_receipt.sha256").read_bytes()
        ).hexdigest()
        == "99dda95fa7705b43bab13328b4491166b8aebe426433f421c02aee07a0444a98"
    )
    assert (
        hashlib.sha256(
            (published[0].repeatability_path / "repeatability_metadata.json").read_bytes()
        ).hexdigest()
        == "474e96ddf753bc07ac7189ed380173c6ecbd7af5a69a42600b7e1fc095aa3d6d"
    )
    receipt = published[0].receipt
    assert receipt.schema_version == "1.1.0"
    assert receipt.repeatability_algorithm_version == "1.1.0"
    expected_state = {
        "decision_status": "not_evaluated",
        "repeatability_decision": "not_evaluated",
        "thresholds_applied": False,
        "repeatability_threshold": None,
        "threshold_source": None,
        "baseline_assigned": False,
        "baseline_role": "not_assigned",
        "baseline_selection_status": "deferred_until_protocol_binding",
        "baseline_difference_computed": False,
        "protocol_condition_binding_performed": False,
        "drift_evaluated": False,
        "drift_decision": "not_evaluated",
    }
    receipt_payload = receipt.model_dump(mode="json")
    record = json.loads(
        (published[0].repeatability_path / "repeatability_record.json").read_bytes()
    )
    metadata = json.loads(
        (published[0].repeatability_path / "repeatability_metadata.json").read_bytes()
    )
    assert record["schema_version"] == "1.1.0"
    for field, value in expected_state.items():
        assert receipt_payload[field] == value
        assert record[field] == value
        assert metadata[field] == value


def test_repeatability_validator_rejects_tampering_without_writeback(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="repeat-1",
        members=_members(),
        now=lambda: FIXED_TIME,
    )
    session_root = store.session_path(DataOrigin.SYNTHETIC, "capture-session")

    def validate() -> None:
        validate_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="repeat-1",
            members=_members(),
        )

    for name in (
        "repeatability_metrics.json",
        "repeatability_metrics.sha256",
        "repeatability_receipt.json",
        "repeatability_receipt.sha256",
        "repeatability_metadata.json",
        "repeatability_record.json",
        "REPEATABILITY_COMPLETE",
    ):
        target = published.repeatability_path / name
        original = target.read_bytes()
        target.write_bytes(original + b"tamper")
        attacked = target.read_bytes()
        attacked_tree = _tree_sha256(session_root)
        with pytest.raises((RepeatabilityPersistenceError, ValidationError, OSError)):
            validate()
        assert target.read_bytes() == attacked
        assert _tree_sha256(session_root) == attacked_tree
        target.write_bytes(original)
        validate()

    extra = published.repeatability_path / "extra.json"
    extra.write_bytes(b"{}\n")
    attacked_tree = _tree_sha256(session_root)
    with pytest.raises(RepeatabilityPersistenceError, match="exactly"):
        validate()
    assert extra.read_bytes() == b"{}\n"
    assert _tree_sha256(session_root) == attacked_tree
    extra.unlink()

    record = published.repeatability_path / "repeatability_record.json"
    original_record = record.read_bytes()
    record_payload = json.loads(original_record)
    record_payload["created_at"] = "2030-01-01T00:00:00Z"
    record.write_bytes(canonical_json_bytes(record_payload))
    attacked_tree = _tree_sha256(session_root)
    with pytest.raises(RepeatabilityPersistenceError, match="binding"):
        validate()
    assert _tree_sha256(session_root) == attacked_tree
    record.write_bytes(original_record)
    validate()

    event = next(
        (store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "events").glob(
            "*_repeatability_created.json"
        )
    )
    original_event = event.read_bytes()
    event_payload = json.loads(original_event)
    event_payload["repeatability_metrics_sha256"] = "0" * 64
    event.write_bytes(canonical_json_bytes(event_payload))
    attacked_event = event.read_bytes()
    attacked_tree = _tree_sha256(session_root)
    with pytest.raises(RepeatabilityPersistenceError, match="binding"):
        validate()
    assert event.read_bytes() == attacked_event
    assert _tree_sha256(session_root) == attacked_tree
    event.write_bytes(original_event)
    validate()


def test_concurrent_repeatability_publication_allows_exactly_one_success(
    tmp_path: Path,
) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)

    def publish() -> PublishedProvisionalRepeatability:
        return publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="concurrent",
            members=_members(),
            now=lambda: FIXED_TIME,
        )

    successes: list[PublishedProvisionalRepeatability] = []
    failures: list[Exception] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        for future in (executor.submit(publish), executor.submit(publish)):
            try:
                successes.append(future.result())
            except Exception as exc:
                failures.append(exc)
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], RepeatabilityPersistenceError)
    assert {entry.name for entry in successes[0].repeatability_path.iterdir()} == (
        REPEATABILITY_FILE_NAMES
    )


def test_event_append_failure_reports_published_true_and_preserves_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)

    def fail_event(*args: object, **kwargs: object) -> Path:
        del args, kwargs
        raise StorageError("injected event failure")

    monkeypatch.setattr(store, "append_event", fail_event)
    with pytest.raises(RepeatabilityPersistenceError, match="published=true"):
        publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="event-failure",
            members=_members(),
            now=lambda: FIXED_TIME,
        )
    target = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "qc/repeat_sets/reassembly_assembly-1/repeat_set_event-failure"
    )
    assert {entry.name for entry in target.iterdir()} == REPEATABILITY_FILE_NAMES


def test_two_repeat_sets_in_one_reassembly_have_independent_events(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    for repeat_set_id in ("repeat-1", "repeat-2"):
        publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id=repeat_set_id,
            members=_members(),
            now=lambda: FIXED_TIME,
        )
    for repeat_set_id in ("repeat-1", "repeat-2"):
        validated = validate_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id=repeat_set_id,
            members=_members(),
        )
        assert validated.receipt.repeat_set_id == repeat_set_id


def test_same_repeat_set_id_is_scoped_by_derived_reassembly(tmp_path: Path) -> None:
    store = ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "synthetic", real=tmp_path / "real")
    )
    bundle = _development_bundle()
    session = SessionRecord(
        session_id="multi-assembly",
        session_schema_version="1.0.0",
        created_at=FIXED_TIME,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        operator=None,
        device_manifest_reference="manifest/device_manifest.provisional.json",
        config_bundle_reference="protocol/config_bundle.json",
        reassembly_ids=["assembly-1", "assembly-2"],
        run_ids=[],
        immutable_status="immutable",
        notes="synthetic repeatability composite identity test",
    )
    reassemblies = [
        ReassemblyRecord(
            reassembly_id=reassembly_id,
            session_id=session.session_id,
            sequence_index=index,
            created_at=FIXED_TIME,
            assembly_description="synthetic repeatability composite identity test",
            operator_confirmation=False,
            related_run_ids=[],
        )
        for index, reassembly_id in enumerate(session.reassembly_ids)
    ]
    store.create_synthetic_session(session, reassemblies, bundle)
    ess = publish_offline_ess_artifact(tmp_path / "ess", "source_ess", bundle.configs["audio"])
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    identities_by_reassembly: dict[str, list[RepeatabilityMemberIdentity]] = {}
    for reassembly_index, reassembly_id in enumerate(session.reassembly_ids, start=1):
        identities = [
            RepeatabilityMemberIdentity(
                source_run_id=f"a{reassembly_index}-capture-{order + 1}",
                processing_id="processing-1",
                qc_id="qc-1",
            )
            for order in range(2)
        ]
        identities_by_reassembly[reassembly_id] = identities
        for order, identity in enumerate(identities):
            publish_virtual_capture(
                store=store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess.artifact_root,
                session_id=session.session_id,
                reassembly_id=reassembly_id,
                run_id=identity.source_run_id,
                measurement_order=order,
                now=lambda: FIXED_TIME,
            )
            publish_ess_processing(
                store=store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess.artifact_root,
                session_id=session.session_id,
                source_run_id=identity.source_run_id,
                processing_id=identity.processing_id,
                now=lambda: FIXED_TIME,
            )
            publish_provisional_qc(
                store=store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess.artifact_root,
                session_id=session.session_id,
                source_run_id=identity.source_run_id,
                processing_id=identity.processing_id,
                qc_id=identity.qc_id,
                now=lambda: FIXED_TIME,
            )
        published = publish_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess.artifact_root,
            session_id=session.session_id,
            repeat_set_id="shared-repeat",
            members=identities,
            now=lambda: FIXED_TIME,
        )
        assert published.receipt.reassembly_id == reassembly_id
    for reassembly_id, identities in identities_by_reassembly.items():
        validated = validate_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess.artifact_root,
            session_id=session.session_id,
            repeat_set_id="shared-repeat",
            members=identities,
        )
        assert validated.receipt.reassembly_id == reassembly_id


def test_published_receipt_uses_explicit_not_assigned_baseline_role(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="state-contract",
        members=_members(),
        now=lambda: FIXED_TIME,
    )

    assert published.receipt.baseline_role == "not_assigned"


def test_published_receipt_records_deferred_baseline_selection_status(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="base-state",
        members=_members(),
        now=lambda: FIXED_TIME,
    )

    assert published.receipt.baseline_selection_status == "deferred_until_protocol_binding"


def test_published_receipt_records_explicit_drift_decision(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="drift-state",
        members=_members(),
        now=lambda: FIXED_TIME,
    )

    assert published.receipt.drift_decision == "not_evaluated"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("baseline_selection_rule", "first_capture"),
        ("qc_threshold", 0.1),
        ("effect_threshold", 0.2),
        ("drift_threshold", 0.5),
        ("classification_pass_threshold", 0.9),
    ],
    ids=["baseline", "qc", "effect", "drift", "classification"],
)
def test_public_repeatability_paths_reject_configured_decision_authority_before_writing(
    tmp_path: Path, field: str, value: str | float
) -> None:
    store, bundle, scenario, ess_root, real_root = _setup(tmp_path)
    loaded = bundle.configs["analysis"]
    assert isinstance(loaded.model, AnalysisConfig)
    if field == "baseline_selection_rule":
        modified_analysis = loaded.model.model_copy(update={"baseline_selection_rule": value})
    else:
        modified_analysis = loaded.model.model_copy(
            update={"decision_gates": loaded.model.decision_gates.model_copy(update={field: value})}
        )
    modified_bundle = replace(
        bundle,
        configs={**bundle.configs, "analysis": replace(loaded, model=modified_analysis)},
    )
    session = store.session_path(DataOrigin.SYNTHETIC, "capture-session")
    short_id = {
        "baseline_selection_rule": "b",
        "qc_threshold": "q",
        "effect_threshold": "e",
        "drift_threshold": "d",
        "classification_pass_threshold": "c",
    }[field]
    valid_id = f"v-{short_id}"
    publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id=valid_id,
        members=_members(),
        now=lambda: FIXED_TIME,
    )
    target = session / "qc/repeat_sets/reassembly_assembly-1" / f"repeat_set_p-{short_id}"
    events_before = len(list((session / "events").glob("*_repeatability_created.json")))
    tree_before = _tree_sha256(session)

    with pytest.raises(
        RepeatabilityPersistenceError,
        match=rf"{field}.*published=false",
    ):
        publish_provisional_repeatability(
            store=store,
            bundle=modified_bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id=f"p-{short_id}",
            members=_members(),
            now=lambda: FIXED_TIME,
        )
    with pytest.raises(
        RepeatabilityPersistenceError,
        match=rf"{field}.*published=false",
    ):
        validate_provisional_repeatability(
            store=store,
            bundle=modified_bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id=valid_id,
            members=_members(),
        )

    assert not target.exists()
    assert len(list((session / "events").glob("*_repeatability_created.json"))) == events_before
    assert _tree_sha256(session) == tree_before
    assert not real_root.exists()


def test_publisher_rejects_analysis_model_that_differs_from_loaded_provenance(
    tmp_path: Path,
) -> None:
    store, bundle, scenario, ess_root, real_root = _setup(tmp_path)
    loaded = bundle.configs["analysis"]
    assert isinstance(loaded.model, AnalysisConfig)
    changed = loaded.model.model_copy(update={"notes": [*loaded.model.notes, "injected"]})
    modified_bundle = replace(
        bundle,
        configs={**bundle.configs, "analysis": replace(loaded, model=changed)},
    )
    session = store.session_path(DataOrigin.SYNTHETIC, "capture-session")
    target = session / "qc/repeat_sets/reassembly_assembly-1/repeat_set_hash-gate"
    events_before = list((session / "events").glob("*_repeatability_created.json"))
    tree_before = _tree_sha256(session)

    with pytest.raises(
        RepeatabilityPersistenceError,
        match=r"normalized provenance.*published=false",
    ):
        publish_provisional_repeatability(
            store=store,
            bundle=modified_bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="hash-gate",
            members=_members(),
            now=lambda: FIXED_TIME,
        )

    assert not target.exists()
    assert list((session / "events").glob("*_repeatability_created.json")) == events_before
    assert _tree_sha256(session) == tree_before
    assert not real_root.exists()


def test_cli_prints_structured_state_from_published_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store, _, _, ess_root, _ = _setup(tmp_path)
    arguments = [
        "--project-root",
        str(PROJECT_ROOT),
        "--audio",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "--protocol",
        "config/protocols/stage4_four_node_states.yaml",
        "--synthetic-root",
        str(store.roots.synthetic),
        "--session-id",
        "capture-session",
        "--repeat-set-id",
        "cli-state",
        "--member",
        "capture-2:processing-1:qc-1",
        "--member",
        "capture-1:processing-1:qc-1",
        "--scenario",
        "tests/fixtures/audio/virtual_duplex_development.yaml",
        "--ess-artifact-root",
        str(ess_root),
    ]

    cli.main(["repeatability-compute", *arguments])
    computed = capsys.readouterr().out
    receipt_path = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "qc/repeat_sets/reassembly_assembly-1/repeat_set_cli-state/repeatability_receipt.json"
    )
    receipt = ProvisionalRepeatabilityReceipt.model_validate_json(receipt_path.read_bytes())
    cli.main(["repeatability-validate", *arguments])
    validated = capsys.readouterr().out

    expected_fields = {
        "decision_status": receipt.decision_status,
        "repeatability_decision": receipt.repeatability_decision,
        "baseline_assigned": str(receipt.baseline_assigned).lower(),
        "baseline_role": receipt.baseline_role,
        "baseline_selection_status": receipt.baseline_selection_status,
        "baseline_difference_computed": str(receipt.baseline_difference_computed).lower(),
        "drift_evaluated": str(receipt.drift_evaluated).lower(),
        "drift_decision": receipt.drift_decision,
        "thresholds_applied": str(receipt.thresholds_applied).lower(),
        "repeatability_threshold": "null",
        "threshold_source": "null",
    }
    for output in (computed, validated):
        assert all(f"{field}={value}" in output for field, value in expected_fields.items())
        assert "REPEATABILITY_NOT_EVALUATED" in output
        assert "BASELINE_NOT_ASSIGNED" in output
        assert "BASELINE_SELECTION_DEFERRED_UNTIL_PROTOCOL_BINDING" in output
        assert "DRIFT_NOT_EVALUATED" in output
        assert "THRESHOLDS_NOT_APPLIED" in output


def test_state_and_binding_attacks_are_read_only_and_restorable(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="attacks",
        members=_members(),
        now=lambda: FIXED_TIME,
    )
    session_root = store.session_path(DataOrigin.SYNTHETIC, "capture-session")

    def validate() -> None:
        validate_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            repeat_set_id="attacks",
            members=_members(),
        )

    def assert_read_only_failure() -> None:
        attacked_tree = _tree_sha256(session_root)
        with pytest.raises(RepeatabilityPersistenceError):
            validate()
        assert _tree_sha256(session_root) == attacked_tree

    receipt_path = published.repeatability_path / "repeatability_receipt.json"
    receipt_sidecar = published.repeatability_path / "repeatability_receipt.sha256"
    original_receipt = receipt_path.read_bytes()
    original_sidecar = receipt_sidecar.read_bytes()
    for field, value in (
        ("baseline_role", "assigned"),
        ("baseline_selection_status", "selected"),
        ("drift_decision", "pass"),
        ("repeatability_decision", "pass"),
    ):
        payload = json.loads(original_receipt)
        payload[field] = value
        attacked = canonical_json_bytes(payload)
        receipt_path.write_bytes(attacked)
        receipt_sidecar.write_bytes(
            f"{hashlib.sha256(attacked).hexdigest()}  repeatability_receipt.json\n".encode("ascii")
        )
        assert_read_only_failure()
        receipt_path.write_bytes(original_receipt)
        receipt_sidecar.write_bytes(original_sidecar)
        validate()

    old_payload = json.loads(original_receipt)
    old_payload["schema_version"] = "1.0.0"
    old_payload["repeatability_algorithm_version"] = "1.0.0"
    old_receipt = canonical_json_bytes(old_payload)
    receipt_path.write_bytes(old_receipt)
    receipt_sidecar.write_bytes(
        f"{hashlib.sha256(old_receipt).hexdigest()}  repeatability_receipt.json\n".encode("ascii")
    )
    assert_read_only_failure()
    receipt_path.write_bytes(original_receipt)
    receipt_sidecar.write_bytes(original_sidecar)
    validate()

    for filename, field, value in (
        ("repeatability_metadata.json", "drift_decision", "pass"),
        ("repeatability_record.json", "baseline_role", "assigned"),
    ):
        target = published.repeatability_path / filename
        original = target.read_bytes()
        payload = json.loads(original)
        payload[field] = value
        target.write_bytes(canonical_json_bytes(payload))
        assert_read_only_failure()
        target.write_bytes(original)
        validate()

    receipt_sidecar.write_bytes(original_sidecar + b"tamper")
    assert_read_only_failure()
    receipt_sidecar.write_bytes(original_sidecar)
    validate()

    event = next((session_root / "events").glob("*_repeatability_created.json"))
    original_event = event.read_bytes()
    for field in ("repeatability_receipt_sha256", "repeatability_record_sha256"):
        payload = json.loads(original_event)
        payload[field] = "0" * 64
        event.write_bytes(canonical_json_bytes(payload))
        assert_read_only_failure()
        event.write_bytes(original_event)
        validate()


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("baseline_role", None),
        ("baseline_role", "assigned"),
        ("baseline_selection_status", "selected"),
        ("drift_decision", "pass"),
        ("repeatability_decision", "pass"),
        ("drift_evaluated", True),
        ("thresholds_applied", True),
        ("repeatability_threshold", 0.5),
        ("schema_version", "1.0.0"),
        ("repeatability_algorithm_version", "1.0.0"),
        ("unexpected", "extra"),
    ],
)
def test_repeatability_receipt_rejects_invalid_state_and_old_versions(
    tmp_path: Path, mutation: str, value: object
) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="strict-state",
        members=_members(),
        now=lambda: FIXED_TIME,
    )
    payload = published.receipt.model_dump(mode="json")
    payload[mutation] = value

    with pytest.raises(ValidationError):
        ProvisionalRepeatabilityReceipt.model_validate(payload)


@pytest.mark.parametrize(
    "missing",
    ["baseline_role", "baseline_selection_status", "drift_decision"],
)
def test_repeatability_receipt_requires_every_explicit_state(tmp_path: Path, missing: str) -> None:
    store, bundle, scenario, ess_root, _ = _setup(tmp_path)
    published = publish_provisional_repeatability(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        repeat_set_id="required-state",
        members=_members(),
        now=lambda: FIXED_TIME,
    )
    payload = published.receipt.model_dump(mode="json")
    del payload[missing]

    with pytest.raises(ValidationError):
        ProvisionalRepeatabilityReceipt.model_validate(payload)
