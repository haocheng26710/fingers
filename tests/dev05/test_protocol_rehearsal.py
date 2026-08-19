import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import acoustic_ladder.protocol.rehearsal as rehearsal_module
from acoustic_ladder import cli
from acoustic_ladder.config.bundle import canonical_json_bytes, load_bundle
from acoustic_ladder.config.schema import export_schemas
from acoustic_ladder.protocol.planning import load_development_protocol_plan_spec
from acoustic_ladder.protocol.planning_persistence import (
    DevelopmentProtocolPlanStore,
    publish_development_protocol_plan,
)
from acoustic_ladder.protocol.rehearsal import (
    DevelopmentProtocolRehearsalStore,
    ProtocolRehearsalError,
    apply_protocol_rehearsal_transition,
    initialize_protocol_rehearsal,
    read_protocol_rehearsal_status,
)
from acoustic_ladder.protocol.rehearsal_models import ProtocolRehearsalTransitionCommand

PROJECT_ROOT = Path(__file__).parents[2]
FIXED_TIME = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)


def _published_plan(tmp_path: Path, stage: int = 1):
    protocols = {
        1: "stage1_single_bridge.yaml",
        2: "stage2_single_node_proxy_states.yaml",
        3: "stage3_two_node_interaction.yaml",
        4: "stage4_four_node_states.yaml",
    }
    bundle = load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols" / protocols[stage],
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    spec = load_development_protocol_plan_spec(
        PROJECT_ROOT / f"tests/fixtures/protocol/stage{stage}_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )
    plan_store = DevelopmentProtocolPlanStore(tmp_path / "plans")
    publish_development_protocol_plan(
        store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id=f"stage{stage}-plan",
        now=lambda: FIXED_TIME,
    )
    return bundle, spec, plan_store


def _isolated_published_plan(tmp_path: Path):
    project = tmp_path / "project"
    relatives = (
        "config/devices/device_manifest.provisional.json",
        "config/devices/device_manifest.provisional.sha256",
        "config/protocols/stage1_single_bridge.yaml",
        "config/analysis/default.yaml",
        "config/synthetic/default.yaml",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
    )
    for relative in relatives:
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, target)
    bundle = load_bundle(
        project_root=project,
        manifest_path=project / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=project / "config/devices/device_manifest.provisional.sha256",
        audio_path=project / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=project / "config/protocols/stage1_single_bridge.yaml",
        analysis_path=project / "config/analysis/default.yaml",
        synthetic_path=project / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    spec = load_development_protocol_plan_spec(
        project / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        project_root=project,
        bundle=bundle,
    )
    plan_store = DevelopmentProtocolPlanStore(tmp_path / "plans")
    publish_development_protocol_plan(
        store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="isolated-plan",
        now=lambda: FIXED_TIME,
    )
    return project, bundle, spec, plan_store


def _clock():
    current = FIXED_TIME

    def now() -> datetime:
        nonlocal current
        value = current
        current += timedelta(seconds=1)
        return value

    return now


def _command(status, action: str, **updates: object) -> ProtocolRehearsalTransitionCommand:
    payload: dict[str, object] = {
        "action": action,
        "rehearsal_actor_id": "offline-runner",
        "expected_event_sequence": status.concurrency_token.event_sequence,
        "expected_head_sha256": status.concurrency_token.head_event_sha256,
        "expected_current_work_order_sha256": (status.concurrency_token.current_work_order_sha256),
        "reason_code": None,
        "detail": None,
    }
    payload.update(updates)
    return ProtocolRehearsalTransitionCommand.model_validate(payload)


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_initialize_and_read_first_derived_work_order(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    rehearsal_store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")

    initialized = initialize_protocol_rehearsal(
        store=rehearsal_store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="stage1-rehearsal",
        now=_clock(),
    )
    status = read_protocol_rehearsal_status(
        store=rehearsal_store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="stage1-rehearsal",
    )

    assert initialized == status
    assert status.rehearsal_state == "active"
    assert status.current_work_order_phase == "awaiting_requirements_presentation"
    assert status.current_work_order is not None
    assert status.current_work_order.global_planned_ordinal == 1
    assert status.current_work_order.plan_id == "stage1-plan"
    assert status.current_work_order.node_states
    assert status.current_work_order.operator_confirmation_status == "pending"
    assert status.current_work_order.protocol_execution_performed is False
    assert status.current_work_order.measurement_performed is False
    assert status.current_work_order.hardware_io_performed is False
    assert status.total_work_order_count == 152
    assert status.rehearsed_work_order_count == 0
    assert status.concurrency_token.event_sequence == 0
    assert status.concurrency_token.current_work_order_sha256 == (
        status.current_work_order.work_order_sha256
    )


def test_present_claim_and_rehearse_advances_exactly_one_work_order(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="normal-flow",
        now=_clock(),
    )
    now = _clock()

    for action, expected_phase in (
        ("present-requirements", "requirements_presented"),
        ("claim", "claimed"),
        ("mark-rehearsed", "awaiting_requirements_presentation"),
    ):
        status = apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="normal-flow",
            command=_command(status, action),
            token=status.concurrency_token,
            now=now,
        )
        assert status.current_work_order_phase == expected_phase

    assert status.rehearsal_state == "active"
    assert status.cursor == 1
    assert status.rehearsed_work_order_count == 1
    assert status.current_work_order is not None
    assert status.current_work_order.global_planned_ordinal == 2
    assert status.concurrency_token.event_sequence == 3
    events = store.rehearsal_path("normal-flow") / "events"
    assert sorted(path.name for path in events.iterdir()) == [
        "event_00000001.json",
        "event_00000001.sha256",
        "event_00000002.json",
        "event_00000002.sha256",
        "event_00000003.json",
        "event_00000003.sha256",
    ]


def test_pause_and_resume_preserve_current_work_order_and_phase(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="pause-resume",
        now=_clock(),
    )
    original_sha = status.concurrency_token.current_work_order_sha256
    now = _clock()

    paused = apply_protocol_rehearsal_transition(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="pause-resume",
        command=_command(status, "pause"),
        token=status.concurrency_token,
        now=now,
    )
    resumed = apply_protocol_rehearsal_transition(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="pause-resume",
        command=_command(paused, "resume"),
        token=paused.concurrency_token,
        now=now,
    )

    assert paused.rehearsal_state == "paused"
    assert paused.current_work_order_phase == "awaiting_requirements_presentation"
    assert resumed.rehearsal_state == "active"
    assert resumed.current_work_order_phase == "awaiting_requirements_presentation"
    assert paused.cursor == resumed.cursor == 0
    assert paused.concurrency_token.current_work_order_sha256 == original_sha
    assert resumed.concurrency_token.current_work_order_sha256 == original_sha


def test_failed_claim_retries_the_same_work_order_from_requirements(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="fail-retry",
        now=_clock(),
    )
    now = _clock()
    for action in ("present-requirements", "claim"):
        status = apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="fail-retry",
            command=_command(status, action),
            token=status.concurrency_token,
            now=now,
        )
    claimed_sha = status.concurrency_token.current_work_order_sha256

    failed = apply_protocol_rehearsal_transition(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="fail-retry",
        command=_command(
            status,
            "mark-failed",
            reason_code="offline-check-failed",
            detail="Rehearsal-only injected failure.",
        ),
        token=status.concurrency_token,
        now=now,
    )
    retried = apply_protocol_rehearsal_transition(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="fail-retry",
        command=_command(failed, "retry"),
        token=failed.concurrency_token,
        now=now,
    )

    assert failed.rehearsal_state == "failed"
    assert failed.current_work_order_phase == "failed"
    assert failed.cursor == 0
    assert retried.rehearsal_state == "active"
    assert retried.current_work_order_phase == "awaiting_requirements_presentation"
    assert retried.cursor == 0
    assert retried.concurrency_token.current_work_order_sha256 == claimed_sha
    assert retried.requirements_presented_for_rehearsal is False


def test_abort_is_terminal_and_rejected_transition_writes_nothing(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="aborted",
        now=_clock(),
    )
    aborted = apply_protocol_rehearsal_transition(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="aborted",
        command=_command(status, "abort", reason_code="operator-ended-rehearsal"),
        token=status.concurrency_token,
        now=_clock(),
    )
    before = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError, match=r"terminal|state"):
        apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="aborted",
            command=_command(aborted, "present-requirements"),
            token=aborted.concurrency_token,
            now=_clock(),
        )

    assert aborted.rehearsal_state == "aborted"
    assert aborted.cursor == 0
    assert _tree(store.root) == before


def test_last_work_order_creates_bound_completion_only_after_full_rehearsal(
    tmp_path: Path,
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path, stage=2)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage2-plan",
        rehearsal_id="stage2-complete",
        now=_clock(),
    )
    root = store.rehearsal_path("stage2-complete")
    assert not (root / "PROTOCOL_REHEARSAL_COMPLETE").exists()
    now = _clock()

    for _ in range(32):
        for action in ("present-requirements", "claim", "mark-rehearsed"):
            status = apply_protocol_rehearsal_transition(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id="stage2-plan",
                rehearsal_id="stage2-complete",
                command=_command(status, action),
                token=status.concurrency_token,
                now=now,
            )

    assert status.rehearsal_state == "complete"
    assert status.current_work_order is None
    assert status.cursor == status.rehearsed_work_order_count == 32
    assert status.concurrency_token.event_sequence == 96
    assert (root / "PROTOCOL_REHEARSAL_COMPLETE").read_bytes() == b"complete\n"
    assert (root / "protocol_rehearsal_completion.json").is_file()
    assert (root / "protocol_rehearsal_completion.sha256").is_file()
    assert len(list((root / "events").glob("event_*.json"))) == 96


def test_concurrent_mark_rehearsed_advances_only_one_work_order(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="concurrent-step",
        now=_clock(),
    )
    now = _clock()
    for action in ("present-requirements", "claim"):
        status = apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="concurrent-step",
            command=_command(status, action),
            token=status.concurrency_token,
            now=now,
        )
    command = _command(status, "mark-rehearsed")
    token = status.concurrency_token

    def step() -> str:
        try:
            result = apply_protocol_rehearsal_transition(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id="stage1-plan",
                rehearsal_id="concurrent-step",
                command=command,
                token=token,
                now=now,
            )
            return f"advanced:{result.cursor}"
        except ProtocolRehearsalError as exc:
            assert exc.published is False
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: step(), range(2)))

    recovered = read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="concurrent-step",
    )
    assert sorted(outcomes) == ["advanced:1", "rejected"]
    assert recovered.cursor == 1
    assert recovered.concurrency_token.event_sequence == 3
    assert len(list((store.rehearsal_path("concurrent-step") / "events").glob("*.json"))) == 3


def test_read_only_recovery_rejects_rehashed_event_semantic_tamper_and_recovers(
    tmp_path: Path,
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="tamper-event",
        now=_clock(),
    )
    apply_protocol_rehearsal_transition(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="tamper-event",
        command=_command(status, "present-requirements"),
        token=status.concurrency_token,
        now=_clock(),
    )
    events = store.rehearsal_path("tamper-event") / "events"
    body = events / "event_00000001.json"
    sidecar = events / "event_00000001.sha256"
    original_body = body.read_bytes()
    original_sidecar = sidecar.read_bytes()
    value = json.loads(original_body)
    value["event_type"] = "work_order_claimed"
    attacked = canonical_json_bytes(value)
    body.write_bytes(attacked)
    sidecar.write_bytes(
        f"{hashlib.sha256(attacked).hexdigest()}  event_00000001.json\n".encode("ascii")
    )
    before = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="tamper-event",
        )

    assert _tree(store.root) == before
    body.write_bytes(original_body)
    sidecar.write_bytes(original_sidecar)
    recovered = read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="tamper-event",
    )
    assert recovered.current_work_order_phase == "requirements_presented"


def test_illegal_transition_is_unpublished_and_preserves_tree(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="illegal-transition",
        now=_clock(),
    )
    before = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError) as failure:
        apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="illegal-transition",
            command=_command(status, "claim"),
            token=status.concurrency_token,
            now=_clock(),
        )

    assert failure.value.published is False
    assert _tree(store.root) == before


def test_stale_command_and_foreign_token_are_rejected_without_writes(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="stale-token",
        now=_clock(),
    )
    before = _tree(store.root)
    stale_command = _command(status, "present-requirements").model_copy(
        update={"expected_head_sha256": "f" * 64}
    )
    foreign_token = status.concurrency_token.model_copy(
        update={"rehearsal_id": "another-rehearsal"}
    )

    for command, token in (
        (stale_command, status.concurrency_token),
        (_command(status, "present-requirements"), foreign_token),
    ):
        with pytest.raises(ProtocolRehearsalError) as failure:
            apply_protocol_rehearsal_transition(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id="stage1-plan",
                rehearsal_id="stale-token",
                command=command,
                token=token,
                now=_clock(),
            )
        assert failure.value.published is False
        assert _tree(store.root) == before


def test_duplicate_and_concurrent_initialization_never_overwrite(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")

    def initialize() -> str:
        try:
            result = initialize_protocol_rehearsal(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id="stage1-plan",
                rehearsal_id="concurrent-init",
                now=lambda: FIXED_TIME,
            )
            return result.concurrency_token.current_work_order_sha256
        except ProtocolRehearsalError as exc:
            assert exc.published is False
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: initialize(), range(2)))
    assert outcomes.count("rejected") == 1
    target = store.rehearsal_path("concurrent-init")
    original = _tree(target)

    with pytest.raises(ProtocolRehearsalError) as duplicate:
        initialize_protocol_rehearsal(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="concurrent-init",
            now=lambda: FIXED_TIME,
        )

    assert duplicate.value.published is False
    assert _tree(target) == original
    assert not list(target.parent.glob("*.lock"))
    assert not list(target.parent.glob("*.staging-*"))


def test_injected_event_staging_failure_leaves_no_half_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="event-failure",
        now=_clock(),
    )

    def fail_write(path: str | Path, payload: bytes) -> None:
        raise OSError(f"injected event write failure: {path} ({len(payload)} bytes)")

    monkeypatch.setattr(rehearsal_module, "atomic_write_bytes", fail_write)
    with pytest.raises(ProtocolRehearsalError) as failure:
        apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="event-failure",
            command=_command(status, "present-requirements"),
            token=status.concurrency_token,
            now=_clock(),
        )

    events = store.rehearsal_path("event-failure") / "events"
    assert failure.value.published is False
    assert not list(events.iterdir())
    assert not list(events.glob("*.staging-*"))
    assert not list(store.rehearsal_path("event-failure").parent.glob("*.lock"))


def test_injected_initialization_failure_removes_only_owned_staging_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    real_write = rehearsal_module.atomic_write_bytes
    writes = 0

    def fail_second_write(path: str | Path, payload: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("injected initialization write failure")
        real_write(path, payload)

    monkeypatch.setattr(rehearsal_module, "atomic_write_bytes", fail_second_write)
    with pytest.raises(ProtocolRehearsalError) as failure:
        initialize_protocol_rehearsal(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="init-failure",
            now=_clock(),
        )

    parent = store.root / "rehearsals"
    assert failure.value.published is False
    assert not store.rehearsal_path("init-failure").exists()
    assert not list(parent.glob("*.lock"))
    assert not list(parent.glob("*.staging-*"))


def test_post_event_failure_reports_published_true_and_keeps_valid_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="post-event-failure",
        now=_clock(),
    )
    real_read = rehearsal_module.read_protocol_rehearsal_status
    calls = 0

    def fail_second_read(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ProtocolRehearsalError("injected post-publication failure", published=False)
        return real_read(**kwargs)

    monkeypatch.setattr(rehearsal_module, "read_protocol_rehearsal_status", fail_second_read)
    with pytest.raises(ProtocolRehearsalError) as failure:
        apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="post-event-failure",
            command=_command(status, "present-requirements"),
            token=status.concurrency_token,
            now=_clock(),
        )

    assert failure.value.published is True
    monkeypatch.setattr(rehearsal_module, "read_protocol_rehearsal_status", real_read)
    recovered = read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="post-event-failure",
    )
    assert recovered.current_work_order_phase == "requirements_presented"
    assert recovered.concurrency_token.event_sequence == 1


@pytest.mark.parametrize(
    "filename",
    [
        "protocol_rehearsal_manifest.json",
        "protocol_rehearsal_manifest.sha256",
        "protocol_rehearsal_record.json",
        "protocol_rehearsal_record.sha256",
        "REHEARSAL_INITIALIZED",
    ],
)
def test_base_envelope_tamper_is_read_only_rejected_and_original_recovers(
    tmp_path: Path, filename: str
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="base-tamper",
        now=_clock(),
    )
    target = store.rehearsal_path("base-tamper") / filename
    original = target.read_bytes()
    target.write_bytes(original + b"\r\n")
    before = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="base-tamper",
        )

    assert _tree(store.root) == before
    target.write_bytes(original)
    read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="base-tamper",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("previous_event_sha256", "f" * 64),
        ("current_work_order_sha256", "f" * 64),
        ("derived_cursor_after", 1),
        ("after_rehearsal_state", "failed"),
        ("after_work_order_phase", "claimed"),
        ("experimental_result", True),
        ("event_sequence", 2),
        ("plan_id", "other-plan"),
    ],
)
def test_rehashed_event_identity_state_cursor_and_safety_attacks_are_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="event-attacks",
        now=_clock(),
    )
    apply_protocol_rehearsal_transition(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="event-attacks",
        command=_command(status, "present-requirements"),
        token=status.concurrency_token,
        now=_clock(),
    )
    root = store.rehearsal_path("event-attacks")
    body = root / "events/event_00000001.json"
    sidecar = root / "events/event_00000001.sha256"
    originals = (body.read_bytes(), sidecar.read_bytes())
    payload = json.loads(originals[0])
    payload[field] = value
    attacked = canonical_json_bytes(payload)
    body.write_bytes(attacked)
    sidecar.write_bytes(
        f"{hashlib.sha256(attacked).hexdigest()}  event_00000001.json\n".encode("ascii")
    )
    before = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="event-attacks",
        )

    assert _tree(store.root) == before
    body.write_bytes(originals[0])
    sidecar.write_bytes(originals[1])
    read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="event-attacks",
    )


@pytest.mark.parametrize(
    "target_key",
    [
        "manifest",
        "manifest-sidecar",
        "protocol",
        "plan-spec",
        "compiled-plan",
        "compiled-plan-sidecar",
        "receipt",
        "receipt-sidecar",
        "metadata",
        "record",
        "plan-completion",
    ],
)
def test_current_plan_source_or_plan_tamper_blocks_rehearsal_without_writing(
    tmp_path: Path, target_key: str
) -> None:
    project, bundle, spec, plan_store = _isolated_published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="isolated-plan",
        rehearsal_id="source-bound",
        now=_clock(),
    )
    targets = {
        "manifest": project / "config/devices/device_manifest.provisional.json",
        "manifest-sidecar": project / "config/devices/device_manifest.provisional.sha256",
        "protocol": project / "config/protocols/stage1_single_bridge.yaml",
        "plan-spec": project / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        "compiled-plan": plan_store.plan_path("isolated-plan") / "compiled_protocol_plan.json",
        "compiled-plan-sidecar": (
            plan_store.plan_path("isolated-plan") / "compiled_protocol_plan.sha256"
        ),
        "receipt": plan_store.plan_path("isolated-plan") / "protocol_plan_receipt.json",
        "receipt-sidecar": (plan_store.plan_path("isolated-plan") / "protocol_plan_receipt.sha256"),
        "metadata": plan_store.plan_path("isolated-plan") / "protocol_plan_metadata.json",
        "record": plan_store.plan_path("isolated-plan") / "protocol_plan_record.json",
        "plan-completion": plan_store.plan_path("isolated-plan") / "PROTOCOL_PLAN_COMPLETE",
    }
    target = targets[target_key]
    original = target.read_bytes()
    target.unlink()
    before = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="isolated-plan",
            rehearsal_id="source-bound",
        )

    assert _tree(store.root) == before
    target.write_bytes(original)
    read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="isolated-plan",
        rehearsal_id="source-bound",
    )


@pytest.mark.parametrize("attack", ["missing", "extra", "reordered"])
def test_event_set_missing_extra_and_reordered_attacks_are_read_only_rejected(
    tmp_path: Path, attack: str
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="event-set",
        now=_clock(),
    )
    for action in ("present-requirements", "claim"):
        status = apply_protocol_rehearsal_transition(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="event-set",
            command=_command(status, action),
            token=status.concurrency_token,
            now=_clock(),
        )
    events = store.rehearsal_path("event-set") / "events"
    originals = _tree(store.root)
    if attack == "missing":
        (events / "event_00000002.sha256").unlink()
    elif attack == "extra":
        (events / "unexpected.txt").write_bytes(b"extra\n")
    else:
        first = events / "event_00000001.json"
        second = events / "event_00000002.json"
        first_bytes, second_bytes = first.read_bytes(), second.read_bytes()
        first.write_bytes(second_bytes)
        second.write_bytes(first_bytes)
    attacked = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="event-set",
        )

    assert _tree(store.root) == attacked
    for path in store.root.rglob("*"):
        if path.is_file():
            path.unlink()
    for relative, payload in originals.items():
        target = store.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="event-set",
    )


def test_non_file_base_entry_is_rejected_without_read_side_effects(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="non-file",
        now=_clock(),
    )
    target = store.rehearsal_path("non-file") / "protocol_rehearsal_record.sha256"
    original = target.read_bytes()
    target.unlink()
    target.mkdir()
    before_names = sorted(path.relative_to(store.root).as_posix() for path in store.root.rglob("*"))

    with pytest.raises(ProtocolRehearsalError):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="non-file",
        )

    assert (
        sorted(path.relative_to(store.root).as_posix() for path in store.root.rglob("*"))
        == before_names
    )
    target.rmdir()
    target.write_bytes(original)
    read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="non-file",
    )


def test_completed_rehearsal_rejects_completion_and_tail_attacks_then_recovers(
    tmp_path: Path,
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path, stage=2)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    status = initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage2-plan",
        rehearsal_id="completion-attacks",
        now=_clock(),
    )
    now = _clock()
    for _ in range(32):
        for action in ("present-requirements", "claim", "mark-rehearsed"):
            status = apply_protocol_rehearsal_transition(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id="stage2-plan",
                rehearsal_id="completion-attacks",
                command=_command(status, action),
                token=status.concurrency_token,
                now=now,
            )
    root = store.rehearsal_path("completion-attacks")
    completion = root / "protocol_rehearsal_completion.json"
    completion_sidecar = root / "protocol_rehearsal_completion.sha256"
    completion_originals = (completion.read_bytes(), completion_sidecar.read_bytes())

    for field, value in (
        ("rehearsed_work_order_count", 31),
        ("final_event_sha256", "f" * 64),
        ("experimental_result", True),
    ):
        payload = json.loads(completion_originals[0])
        payload[field] = value
        attacked = canonical_json_bytes(payload)
        completion.write_bytes(attacked)
        completion_sidecar.write_bytes(
            (
                f"{hashlib.sha256(attacked).hexdigest()}  protocol_rehearsal_completion.json\n"
            ).encode("ascii")
        )
        before = _tree(store.root)
        with pytest.raises(ProtocolRehearsalError):
            read_protocol_rehearsal_status(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id="stage2-plan",
                rehearsal_id="completion-attacks",
            )
        assert _tree(store.root) == before
        completion.write_bytes(completion_originals[0])
        completion_sidecar.write_bytes(completion_originals[1])

    final_body = root / "events/event_00000096.json"
    final_sidecar = root / "events/event_00000096.sha256"
    final_originals = (final_body.read_bytes(), final_sidecar.read_bytes())
    final_body.unlink()
    final_sidecar.unlink()
    with pytest.raises(ProtocolRehearsalError):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage2-plan",
            rehearsal_id="completion-attacks",
        )
    final_body.write_bytes(final_originals[0])
    final_sidecar.write_bytes(final_originals[1])
    recovered = read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage2-plan",
        rehearsal_id="completion-attacks",
    )
    assert recovered.rehearsal_state == "complete"


def test_rehearsal_rejects_directory_junction_even_when_target_is_empty(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    store = DevelopmentProtocolRehearsalStore(tmp_path / "rehearsals")
    initialize_protocol_rehearsal(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="symlink-attack",
        now=_clock(),
    )
    root = store.rehearsal_path("symlink-attack")
    events = root / "events"
    outside = tmp_path / "outside-events"
    outside.mkdir()
    events.rmdir()
    subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(events), str(outside)],
        check=True,
    )
    before = _tree(store.root)

    with pytest.raises(ProtocolRehearsalError, match=r"reparse|symlink"):
        read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id="symlink-attack",
        )

    assert _tree(store.root) == before
    events.rmdir()
    events.mkdir()
    read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="symlink-attack",
    )


def test_rehearsal_cli_init_status_step_and_validate_are_explicitly_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    rehearsal_root = tmp_path / "rehearsals"
    common = [
        "--project-root",
        str(PROJECT_ROOT),
        "--protocol",
        "config/protocols/stage1_single_bridge.yaml",
        "--audio",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "--plan-spec",
        "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        "--development-plan-root",
        str(plan_store.root),
        "--plan-id",
        "stage1-plan",
        "--development-rehearsal-root",
        str(rehearsal_root),
        "--rehearsal-id",
        "cli-rehearsal",
    ]
    cli.main(["protocol-rehearsal-init", *common])
    initialized = capsys.readouterr().out
    cli.main(["protocol-rehearsal-status", *common])
    status_output = capsys.readouterr().out
    status = read_protocol_rehearsal_status(
        store=DevelopmentProtocolRehearsalStore(rehearsal_root),
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        rehearsal_id="cli-rehearsal",
    )
    token = status.concurrency_token
    cli.main(
        [
            "protocol-rehearsal-step",
            *common,
            "--action",
            "present-requirements",
            "--actor-id",
            "cli-runner",
            "--expected-event-sequence",
            str(token.event_sequence),
            "--expected-head-sha256",
            token.head_event_sha256,
            "--expected-work-order-sha256",
            token.current_work_order_sha256,
        ]
    )
    stepped = capsys.readouterr().out
    cli.main(["protocol-rehearsal-validate", *common])
    validated = capsys.readouterr().out

    for output in (initialized, status_output, stepped, validated):
        assert "development_rehearsal=true" in output
        assert "physical_operator_confirmation_performed=false" in output
        assert "operator_confirmation_status=pending" in output
        assert "protocol_execution_performed=false" in output
        assert "measurement_performed=false" in output
        assert "hardware_io_performed=false" in output
        assert "hardware_ready=false" in output
        assert "formal_eligible=false" in output
        assert "experimental_result=false" in output


@pytest.mark.parametrize(
    "forbidden",
    [
        "--ordinal",
        "--condition-id",
        "--node-state",
        "--session-index",
        "--reassembly-index",
        "--repeat-index",
        "--real-root",
        "--synthetic-root",
        "--device",
        "--channel",
        "--host-api",
        "--play",
        "--record",
        "--stream",
        "--calibration",
        "--spl",
        "--threshold",
        "--decision",
        "--classification",
        "--physical-confirmation",
    ],
)
def test_rehearsal_cli_rejects_forbidden_authority(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "protocol-rehearsal-init",
                "--protocol",
                "protocol.yaml",
                "--plan-spec",
                "plan.yaml",
                "--development-plan-root",
                "plans",
                "--plan-id",
                "plan",
                "--development-rehearsal-root",
                "rehearsals",
                "--rehearsal-id",
                "rehearsal",
                forbidden,
                "forbidden",
            ]
        )


def test_persisted_rehearsal_models_are_exported_as_schemas(tmp_path: Path) -> None:
    exported = {path.name for path in export_schemas(tmp_path)}

    assert {
        "protocol_rehearsal_manifest.schema.json",
        "protocol_rehearsal_record.schema.json",
        "protocol_rehearsal_event.schema.json",
        "protocol_rehearsal_completion.schema.json",
    }.issubset(exported)


@pytest.mark.parametrize("rehearsal_id", ["", ".", "..", "../escape", "a/b", "a\\b", "C:drive"])
def test_unsafe_rehearsal_ids_are_rejected_before_root_creation(
    tmp_path: Path, rehearsal_id: str
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path)
    root = tmp_path / "must-not-exist"

    with pytest.raises(ProtocolRehearsalError):
        initialize_protocol_rehearsal(
            store=DevelopmentProtocolRehearsalStore(root),
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id="stage1-plan",
            rehearsal_id=rehearsal_id,
            now=_clock(),
        )

    assert not root.exists()


@pytest.mark.parametrize("unsafe", ["", ".", "..", "../escape", "a/b", "a\\b", "开发"])
def test_actor_and_reason_codes_require_safe_ascii_identifiers(unsafe: str) -> None:
    payload = {
        "action": "abort",
        "rehearsal_actor_id": unsafe,
        "expected_event_sequence": 0,
        "expected_head_sha256": "0" * 64,
        "expected_current_work_order_sha256": "0" * 64,
        "reason_code": "safe-reason",
        "detail": None,
    }
    with pytest.raises(ValidationError):
        ProtocolRehearsalTransitionCommand.model_validate(payload)
    payload["rehearsal_actor_id"] = "safe-actor"
    payload["reason_code"] = unsafe
    with pytest.raises(ValidationError):
        ProtocolRehearsalTransitionCommand.model_validate(payload)
