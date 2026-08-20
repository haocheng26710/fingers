from pathlib import Path

import pytest

from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.protocol import synthetic_execution as execution_module
from acoustic_ladder.protocol.synthetic_execution import (
    SyntheticProtocolExecutionError,
    apply_synthetic_protocol_execution_control,
    execute_next_synthetic_protocol_work_order,
    initialize_synthetic_protocol_execution,
    read_synthetic_protocol_execution_status,
    recover_current_synthetic_protocol_work_order,
    validate_synthetic_protocol_execution,
)
from tests.dev05.test_synthetic_protocol_execution import (
    FIXED_TIME,
    _control,
    _execution_setup,
)


def _file_tree(*roots: Path) -> dict[str, bytes]:
    return {
        f"{index}/{path.relative_to(root).as_posix()}": path.read_bytes()
        for index, root in enumerate(roots)
        if root.exists()
        for path in root.rglob("*")
        if path.is_file()
    }


def _capture_recovery_status(common: dict[str, object]):
    initialized = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)

    def fail_after_capture(stage: str) -> None:
        if stage == "after_capture_before_event":
            raise RuntimeError("establish capture recovery")

    with pytest.raises(SyntheticProtocolExecutionError):
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=initialized.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
            fault_injector=fail_after_capture,
        )
    return read_synthetic_protocol_execution_status(**common)


def _completion_recovery_status(common: dict[str, object]):
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    while status.cursor < status.total_work_order_count - 1:
        status = execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    def fail_after_event(stage: str) -> None:
        if stage == "after_event_before_completion":
            raise RuntimeError("establish completion recovery")

    with pytest.raises(SyntheticProtocolExecutionError):
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
            fault_injector=fail_after_event,
        )
    return read_synthetic_protocol_execution_status(**common)


def test_capture_recovery_normalizes_event_io_failure_from_persisted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, execution_id="capture-io-error")
    recovery = _capture_recovery_status(common)
    execution_root = common["store"].execution_path("capture-io-error")
    first = recovery.current_work_order
    assert first is not None
    session_root = session_store.session_path(DataOrigin.SYNTHETIC, first.session_id)
    before = _file_tree(execution_root, session_root)

    original = execution_module._publish_event_pair

    def fail_before_publish(*_args: object, **_kwargs: object) -> str:
        raise OSError("injected event write failure")

    monkeypatch.setattr(execution_module, "_publish_event_pair", fail_before_publish)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    unchanged = read_synthetic_protocol_execution_status(**common)
    assert unchanged.execution_state == "recovery_required"
    assert unchanged.recovery_kind == "capture"
    assert unchanged.cursor == 0
    assert unchanged.concurrency_token == recovery.concurrency_token
    assert list((execution_root / "events").iterdir()) == []
    assert _file_tree(execution_root, session_root) == before
    monkeypatch.setattr(execution_module, "_publish_event_pair", original)
    fresh = read_synthetic_protocol_execution_status(**common)
    recovered = recover_current_synthetic_protocol_work_order(
        **common,
        concurrency_token=fresh.concurrency_token,
        actor_id="recovery-runner",
        now=lambda: FIXED_TIME,
    )
    assert recovered.cursor == 1
    assert len(list((execution_root / "events").glob("event_*.json"))) == 1
    raw = session_root / "raw"
    assert [path.name for path in raw.iterdir()] == [f"run_{first.run_id}"]
    after = _file_tree(execution_root, session_root)
    with pytest.raises(SyntheticProtocolExecutionError):
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=fresh.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )
    assert _file_tree(execution_root, session_root) == after


def test_completion_recovery_reports_existing_capture_and_event_on_io_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, stage=2, execution_id="completion-io-error")
    recovery = _completion_recovery_status(common)
    execution_root = common["store"].execution_path("completion-io-error")
    final = recovery.current_work_order
    assert final is None
    session_roots = sorted(session_store.roots.synthetic.glob("session_*"))
    before = _file_tree(execution_root, *session_roots)

    original = execution_module._publish_completion

    def fail_before_publish(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("injected completion write failure")

    monkeypatch.setattr(execution_module, "_publish_completion", fail_before_publish)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    unchanged = read_synthetic_protocol_execution_status(**common)
    assert unchanged.execution_state == "recovery_required"
    assert unchanged.recovery_kind == "completion"
    assert unchanged.cursor == unchanged.total_work_order_count == 32
    assert unchanged.concurrency_token == recovery.concurrency_token
    assert len(list((execution_root / "events").glob("event_*.json"))) == 32
    assert not (execution_root / "SYNTHETIC_EXECUTION_COMPLETE").exists()
    assert _file_tree(execution_root, *session_roots) == before
    monkeypatch.setattr(execution_module, "_publish_completion", original)
    fresh = read_synthetic_protocol_execution_status(**common)
    complete = recover_current_synthetic_protocol_work_order(
        **common,
        concurrency_token=fresh.concurrency_token,
        actor_id="recovery-runner",
        now=lambda: FIXED_TIME,
    )
    assert complete.execution_state == "complete"
    assert validate_synthetic_protocol_execution(**common) == complete
    assert len(list(execution_root.glob("synthetic_execution_completion.json"))) == 1
    after = _file_tree(execution_root, *session_roots)
    with pytest.raises(SyntheticProtocolExecutionError):
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=fresh.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )
    assert _file_tree(execution_root, *session_roots) == after


@pytest.mark.parametrize("action", ["pause", "resume", "retry", "abort"])
def test_control_event_io_failure_is_normalized_without_state_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    execution_id = f"{action}-control-io-error"
    common, _ = _execution_setup(tmp_path, execution_id=execution_id)
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    if action == "resume":
        status = apply_synthetic_protocol_execution_control(
            **common,
            command=_control(status, "pause"),
            concurrency_token=status.concurrency_token,
            now=lambda: FIXED_TIME,
        )
    elif action == "retry":

        def fail_capture(stage: str) -> None:
            if stage == "after_session_before_capture":
                raise RuntimeError("establish failed state")

        with pytest.raises(SyntheticProtocolExecutionError):
            execute_next_synthetic_protocol_work_order(
                **common,
                concurrency_token=status.concurrency_token,
                actor_id="synthetic-runner",
                now=lambda: FIXED_TIME,
                fault_injector=fail_capture,
            )
        status = read_synthetic_protocol_execution_status(**common)
    execution_root = common["store"].execution_path(execution_id)
    before = _file_tree(execution_root)
    event_count = len(list((execution_root / "events").glob("event_*.json")))

    def fail_before_publish(*_args: object, **_kwargs: object) -> str:
        raise OSError("injected control event write failure")

    monkeypatch.setattr(execution_module, "_publish_event_pair", fail_before_publish)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(status, action, "operator_abort" if action == "abort" else None),
            concurrency_token=status.concurrency_token,
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    unchanged = read_synthetic_protocol_execution_status(**common)
    assert unchanged == status
    assert len(list((execution_root / "events").glob("event_*.json"))) == event_count
    assert _file_tree(execution_root) == before


def test_capture_recovery_detects_event_published_before_publisher_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, execution_id="event-then-error")
    recovery = _capture_recovery_status(common)
    execution_root = common["store"].execution_path("event-then-error")
    first = recovery.current_work_order
    assert first is not None
    original = execution_module._publish_event_pair

    def publish_then_raise(*args: object, **kwargs: object) -> str:
        original(*args, **kwargs)
        raise OSError("event published before injected failure")

    monkeypatch.setattr(execution_module, "_publish_event_pair", publish_then_raise)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    advanced = read_synthetic_protocol_execution_status(**common)
    assert advanced.execution_state == "active"
    assert advanced.cursor == 1
    assert advanced.concurrency_token.event_sequence == 1
    assert len(list((execution_root / "events").glob("event_*.json"))) == 1
    raw = session_store.session_path(DataOrigin.SYNTHETIC, first.session_id) / "raw"
    assert [path.name for path in raw.iterdir()] == [f"run_{first.run_id}"]
    assert validate_synthetic_protocol_execution(**common) == advanced
    after = _file_tree(execution_root, raw)
    with pytest.raises(SyntheticProtocolExecutionError):
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )
    assert _file_tree(execution_root, raw) == after


def test_control_detects_event_published_before_publisher_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="control-event-then-error")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("control-event-then-error")
    original = execution_module._publish_event_pair

    def publish_then_raise(*args: object, **kwargs: object) -> str:
        original(*args, **kwargs)
        raise RuntimeError("control event published before injected failure")

    monkeypatch.setattr(execution_module, "_publish_event_pair", publish_then_raise)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    paused = read_synthetic_protocol_execution_status(**common)
    assert paused.execution_state == "paused"
    assert paused.cursor == 0
    assert paused.concurrency_token.event_sequence == 1
    assert len(list((execution_root / "events").glob("event_*.json"))) == 1
    after = _file_tree(execution_root)
    with pytest.raises(SyntheticProtocolExecutionError):
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )
    assert _file_tree(execution_root) == after


def test_publisher_file_exists_after_control_event_is_not_reported_as_lock_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="publisher-file-exists")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    original = execution_module._publish_event_pair

    def publish_then_raise(*args: object, **kwargs: object) -> str:
        original(*args, **kwargs)
        raise FileExistsError("publisher post-publication failure")

    monkeypatch.setattr(execution_module, "_publish_event_pair", publish_then_raise)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, FileExistsError)
    assert "already in progress" not in str(raised.value)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    paused = read_synthetic_protocol_execution_status(**common)
    assert paused.execution_state == "paused"
    assert paused.concurrency_token.event_sequence == 1


def test_control_lock_permission_error_is_normalized_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="lock-permission")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("lock-permission")
    before = _file_tree(execution_root)
    original = execution_module.os.open

    def deny_lock(*_args: object, **_kwargs: object) -> int:
        raise PermissionError("transition lock denied")

    monkeypatch.setattr(execution_module.os, "open", deny_lock)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )
    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    assert _file_tree(execution_root) == before
    monkeypatch.setattr(execution_module.os, "open", original)
    paused = apply_synthetic_protocol_execution_control(
        **common,
        command=_control(active, "pause"),
        concurrency_token=active.concurrency_token,
        now=lambda: FIXED_TIME,
    )
    assert paused.execution_state == "paused"


def test_completion_recovery_detects_completion_published_before_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(
        tmp_path, stage=2, execution_id="completion-then-error"
    )
    recovery = _completion_recovery_status(common)
    execution_root = common["store"].execution_path("completion-then-error")
    session_roots = sorted(session_store.roots.synthetic.glob("session_*"))
    original = execution_module._publish_completion

    def publish_then_raise(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)
        raise OSError("completion published before injected failure")

    monkeypatch.setattr(execution_module, "_publish_completion", publish_then_raise)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is True
    complete = read_synthetic_protocol_execution_status(**common)
    assert complete.execution_state == "complete"
    assert complete.cursor == complete.total_work_order_count == 32
    assert validate_synthetic_protocol_execution(**common) == complete
    for name in (
        "synthetic_execution_completion.json",
        "synthetic_execution_completion.sha256",
        "SYNTHETIC_EXECUTION_COMPLETE",
    ):
        assert (execution_root / name).is_file()
    after = _file_tree(execution_root, *session_roots)
    with pytest.raises(SyntheticProtocolExecutionError):
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )
    assert _file_tree(execution_root, *session_roots) == after


def test_partial_event_is_unproven_and_read_only_replay_does_not_repair_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, execution_id="partial-event")
    recovery = _capture_recovery_status(common)
    execution_root = common["store"].execution_path("partial-event")
    first = recovery.current_work_order
    assert first is not None
    session_root = session_store.session_path(DataOrigin.SYNTHETIC, first.session_id)

    def publish_partial(root: Path, *_args: object, **_kwargs: object) -> str:
        (root / "events" / "event_00000001.json").write_bytes(b"{}")
        raise OSError("partial event write")

    monkeypatch.setattr(execution_module, "_publish_event_pair", publish_partial)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    assert "publication state not proven for: ledger event" in str(raised.value)
    partial = execution_root / "events" / "event_00000001.json"
    assert partial.read_bytes() == b"{}"
    before = _file_tree(execution_root, session_root)
    for _ in range(2):
        with pytest.raises(SyntheticProtocolExecutionError):
            read_synthetic_protocol_execution_status(**common)
        assert _file_tree(execution_root, session_root) == before


def test_partial_completion_is_unproven_and_validator_does_not_repair_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, stage=2, execution_id="partial-completion")
    recovery = _completion_recovery_status(common)
    execution_root = common["store"].execution_path("partial-completion")
    session_roots = sorted(session_store.roots.synthetic.glob("session_*"))

    def publish_partial(root: Path, *_args: object, **_kwargs: object) -> None:
        (root / "synthetic_execution_completion.json").write_bytes(b"{}")
        raise PermissionError("partial completion write")

    monkeypatch.setattr(execution_module, "_publish_completion", publish_partial)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    assert "publication state not proven for: completion" in str(raised.value)
    partial = execution_root / "synthetic_execution_completion.json"
    assert partial.read_bytes() == b"{}"
    before = _file_tree(execution_root, *session_roots)
    for verifier in (
        read_synthetic_protocol_execution_status,
        validate_synthetic_protocol_execution,
    ):
        with pytest.raises(SyntheticProtocolExecutionError):
            verifier(**common)
        assert _file_tree(execution_root, *session_roots) == before


def test_control_does_not_swallow_base_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="base-exception")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("base-exception")
    original = execution_module._publish_event_pair

    def interrupt(*_args: object, **_kwargs: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(execution_module, "_publish_event_pair", interrupt)
    with pytest.raises(KeyboardInterrupt):
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )
    assert list((execution_root / "events").iterdir()) == []
    assert not (execution_root.parent / ".base-exception.transition.lock").exists()
    monkeypatch.setattr(execution_module, "_publish_event_pair", original)
    paused = apply_synthetic_protocol_execution_control(
        **common,
        command=_control(active, "pause"),
        concurrency_token=active.concurrency_token,
        now=lambda: FIXED_TIME,
    )
    assert paused.execution_state == "paused"


def test_execute_next_detects_event_published_before_publisher_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, execution_id="execute-event-error")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    first = active.current_work_order
    assert first is not None
    execution_root = common["store"].execution_path("execute-event-error")
    original = execution_module._publish_event_pair

    def publish_then_raise(*args: object, **kwargs: object) -> str:
        original(*args, **kwargs)
        raise OSError("execute event published before injected failure")

    monkeypatch.setattr(execution_module, "_publish_event_pair", publish_then_raise)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=active.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    advanced = read_synthetic_protocol_execution_status(**common)
    assert advanced.cursor == 1
    assert advanced.concurrency_token.event_sequence == 1
    assert len(list((execution_root / "events").glob("event_*.json"))) == 1
    raw = session_store.session_path(DataOrigin.SYNTHETIC, first.session_id) / "raw"
    assert [path.name for path in raw.iterdir()] == [f"run_{first.run_id}"]


def test_execute_next_does_not_override_unproven_capture_with_memory_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, execution_id="capture-probe-denied")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    first = active.current_work_order
    assert first is not None
    execution_root = common["store"].execution_path("capture-probe-denied")
    session_root = session_store.session_path(DataOrigin.SYNTHETIC, first.session_id)
    original_capture = execution_module._capture_for_event
    semantic_replays = 0

    def semantic_replay_then_deny(*args: object, **kwargs: object):
        nonlocal semantic_replays
        semantic_replays += 1
        if semantic_replays == 2:
            raise PermissionError("injected capture durability probe denial")
        return original_capture(*args, **kwargs)

    def fail_event_publish(*_args: object, **_kwargs: object) -> str:
        raise OSError("injected event publication failure")

    monkeypatch.setattr(execution_module, "_capture_for_event", semantic_replay_then_deny)
    monkeypatch.setattr(execution_module, "_publish_event_pair", fail_event_publish)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=active.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert "publication state not proven for: capture, ledger event" in str(raised.value)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    assert len(list((execution_root / "events").iterdir())) == 0
    assert (session_root / "raw" / f"run_{first.run_id}" / "RUN_COMPLETE").is_file()


def test_execute_next_does_not_treat_existing_invalid_capture_as_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, session_store = _execution_setup(tmp_path, execution_id="invalid-capture-probe")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    first = active.current_work_order
    assert first is not None
    execution_root = common["store"].execution_path("invalid-capture-probe")
    run_root = (
        session_store.session_path(DataOrigin.SYNTHETIC, first.session_id)
        / "raw"
        / f"run_{first.run_id}"
    )

    def corrupt_capture_then_fail_event(*_args: object, **_kwargs: object) -> str:
        (run_root / "capture_receipt.json").write_bytes(b"{}\n")
        raise OSError("injected event failure after capture corruption")

    monkeypatch.setattr(execution_module, "_publish_event_pair", corrupt_capture_then_fail_event)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=active.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert "publication state not proven for: capture, ledger event" in str(raised.value)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    assert (run_root / "RUN_COMPLETE").is_file()
    assert (run_root / "capture_receipt.json").is_file()
    assert list((execution_root / "events").iterdir()) == []
    before = _file_tree(execution_root, run_root)
    with pytest.raises(SyntheticProtocolExecutionError):
        read_synthetic_protocol_execution_status(**common)
    with pytest.raises(SyntheticProtocolExecutionError):
        read_synthetic_protocol_execution_status(**common)
    assert _file_tree(execution_root, run_root) == before
