from pathlib import Path

import pytest

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
from tests.dev05.test_synthetic_execution_publication_errors import (
    _capture_recovery_status,
    _completion_recovery_status,
)
from tests.dev05.test_synthetic_protocol_execution import (
    FIXED_TIME,
    _control,
    _execution_setup,
)


def _file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_control_unlink_failure_reports_durable_event_and_preserves_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="control-unlink-denied")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("control-unlink-denied")
    lock = execution_root.parent / ".control-unlink-denied.transition.lock"
    original_unlink = Path.unlink

    def deny_lock_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == lock:
            raise PermissionError("injected mutation lock unlink denial")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_lock_unlink)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    assert "mutation lock cleanup failed" in str(raised.value)
    assert lock.is_file()
    paused = read_synthetic_protocol_execution_status(**common)
    assert paused.execution_state == "paused"
    assert paused.cursor == 0
    assert paused.concurrency_token.event_sequence == 1
    assert len(list((execution_root / "events").glob("event_*.json"))) == 1
    before = _file_tree(execution_root)
    with pytest.raises(SyntheticProtocolExecutionError, match="already in progress"):
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(paused, "resume"),
            concurrency_token=paused.concurrency_token,
            now=lambda: FIXED_TIME,
        )
    assert lock.is_file()
    assert _file_tree(execution_root) == before


def _deny_exact_unlink(monkeypatch: pytest.MonkeyPatch, target: Path, message: str) -> None:
    original_unlink = Path.unlink

    def deny(path: Path, *args: object, **kwargs: object) -> None:
        if path == target:
            raise PermissionError(message)
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny)


def test_initialize_unlink_failure_reports_verified_base_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="initialize-unlink-denied")
    execution_root = common["store"].execution_path("initialize-unlink-denied")
    lock = execution_root.parent / ".initialize-unlink-denied.initialize.lock"
    _deny_exact_unlink(monkeypatch, lock, "injected initialization lock unlink denial")

    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)

    assert isinstance(raised.value.__cause__, PermissionError)
    assert "initialization/base envelope verified from persistent storage" in str(raised.value)
    assert "mutation lock cleanup failed" in str(raised.value)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    assert lock.is_file()
    before = _file_tree(execution_root)
    status = read_synthetic_protocol_execution_status(**common)
    assert status.execution_state == "active"
    assert status.cursor == 0
    assert _file_tree(execution_root) == before


def test_execute_next_unlink_failure_reports_verified_capture_and_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="execute-unlink-denied")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("execute-unlink-denied")
    lock = execution_root.parent / ".execute-unlink-denied.transition.lock"
    _deny_exact_unlink(monkeypatch, lock, "injected execute lock unlink denial")

    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=active.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    assert lock.is_file()
    advanced = read_synthetic_protocol_execution_status(**common)
    assert advanced.cursor == 1
    assert advanced.concurrency_token.event_sequence == 1
    before = _file_tree(execution_root)
    with pytest.raises(SyntheticProtocolExecutionError, match="already in progress"):
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=advanced.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )
    assert _file_tree(execution_root) == before


def test_capture_recovery_unlink_failure_reports_verified_capture_and_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="recovery-unlink-denied")
    recovery = _capture_recovery_status(common)
    execution_root = common["store"].execution_path("recovery-unlink-denied")
    lock = execution_root.parent / ".recovery-unlink-denied.transition.lock"
    _deny_exact_unlink(monkeypatch, lock, "injected recovery lock unlink denial")

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
    assert lock.is_file()
    recovered = read_synthetic_protocol_execution_status(**common)
    assert recovered.cursor == 1
    assert recovered.concurrency_token.event_sequence == 1


def test_completion_recovery_unlink_failure_reports_all_verified_publications(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, stage=2, execution_id="completion-unlink-denied")
    recovery = _completion_recovery_status(common)
    execution_root = common["store"].execution_path("completion-unlink-denied")
    lock = execution_root.parent / ".completion-unlink-denied.transition.lock"
    _deny_exact_unlink(monkeypatch, lock, "injected completion recovery unlink denial")

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
    assert raised.value.completion_published is True
    assert lock.is_file()
    complete = read_synthetic_protocol_execution_status(**common)
    assert complete.execution_state == "complete"
    assert complete.cursor == complete.total_work_order_count == 32
    assert validate_synthetic_protocol_execution(**common) == complete


def test_control_close_failure_is_normalized_after_unlink_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="control-close-denied")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("control-close-denied")
    lock = execution_root.parent / ".control-close-denied.transition.lock"
    original_close = execution_module.os.close

    def close_then_raise(descriptor: int) -> None:
        original_close(descriptor)
        raise PermissionError("injected mutation lock close denial")

    monkeypatch.setattr(execution_module.os, "close", close_then_raise)
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    assert not lock.exists()
    assert read_synthetic_protocol_execution_status(**common).execution_state == "paused"


def test_body_and_unlink_failures_are_both_preserved_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="body-cleanup-failure")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("body-cleanup-failure")
    lock = execution_root.parent / ".body-cleanup-failure.transition.lock"

    def fail_event(*_args: object, **_kwargs: object) -> str:
        raise OSError("injected event body failure")

    monkeypatch.setattr(execution_module, "_publish_event_pair", fail_event)
    _deny_exact_unlink(monkeypatch, lock, "injected cleanup failure after body error")
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert "injected event body failure" in str(raised.value)
    assert "injected cleanup failure after body error" in str(raised.value)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is False
    assert raised.value.completion_published is False
    assert lock.is_file()
    assert list((execution_root / "events").iterdir()) == []


def test_publish_then_raise_and_unlink_failure_keep_verified_event_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="publish-cleanup-failure")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("publish-cleanup-failure")
    lock = execution_root.parent / ".publish-cleanup-failure.transition.lock"
    original_publish = execution_module._publish_event_pair

    def publish_then_raise(*args: object, **kwargs: object) -> str:
        original_publish(*args, **kwargs)
        raise OSError("injected error after event publication")

    monkeypatch.setattr(execution_module, "_publish_event_pair", publish_then_raise)
    _deny_exact_unlink(monkeypatch, lock, "injected cleanup failure after publication")
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(active, "pause"),
            concurrency_token=active.concurrency_token,
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert "injected error after event publication" in str(raised.value)
    assert "injected cleanup failure after publication" in str(raised.value)
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    assert lock.is_file()
    paused = read_synthetic_protocol_execution_status(**common)
    assert paused.execution_state == "paused"
    assert paused.concurrency_token.event_sequence == 1
    assert len(list((execution_root / "events").glob("event_*.json"))) == 1


def test_completion_publish_then_raise_and_unlink_failure_preserve_all_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, stage=2, execution_id="completion-publish-cleanup")
    recovery = _completion_recovery_status(common)
    execution_root = common["store"].execution_path("completion-publish-cleanup")
    lock = execution_root.parent / ".completion-publish-cleanup.transition.lock"
    original_publish = execution_module._publish_completion

    def publish_then_raise(*args: object, **kwargs: object) -> None:
        original_publish(*args, **kwargs)
        raise OSError("injected error after completion publication")

    monkeypatch.setattr(execution_module, "_publish_completion", publish_then_raise)
    _deny_exact_unlink(monkeypatch, lock, "injected cleanup failure after completion publication")
    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    assert isinstance(raised.value.__cause__, OSError)
    assert "injected error after completion publication" in str(raised.value)
    assert "injected cleanup failure after completion publication" in str(raised.value)
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is True
    assert lock.is_file()
    complete = validate_synthetic_protocol_execution(**common)
    assert complete.execution_state == "complete"
    assert complete.cursor == complete.total_work_order_count == 32
    assert len(list(execution_root.glob("synthetic_execution_completion.json"))) == 1
    before = _file_tree(execution_root)
    with pytest.raises(SyntheticProtocolExecutionError, match="already in progress"):
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=recovery.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )
    assert _file_tree(execution_root) == before


def test_execute_next_base_exception_propagates_after_successful_lock_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="execute-interrupt")
    active = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    execution_root = common["store"].execution_path("execute-interrupt")
    lock = execution_root.parent / ".execute-interrupt.transition.lock"

    def interrupt(*_args: object, **_kwargs: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(execution_module, "_publish_event_pair", interrupt)
    with pytest.raises(KeyboardInterrupt):
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=active.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    assert not lock.exists()
    assert list((execution_root / "events").iterdir()) == []
    before = _file_tree(execution_root)
    recovery = read_synthetic_protocol_execution_status(**common)
    assert recovery.execution_state == "recovery_required"
    assert recovery.recovery_kind == "capture"
    assert recovery.cursor == 0
    assert _file_tree(execution_root) == before
