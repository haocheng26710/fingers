import hashlib
import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder import cli
from acoustic_ladder.audio.conditioned_virtual_capture import (
    load_conditioned_virtual_capture_scenario,
)
from acoustic_ladder.audio.excitation_persistence import publish_offline_ess_artifact
from acoustic_ladder.config.schema import export_schemas
from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.protocol.synthetic_execution import (
    DevelopmentSyntheticProtocolExecutionStore,
    SyntheticProtocolExecutionError,
    apply_synthetic_protocol_execution_control,
    derive_synthetic_protocol_work_orders,
    execute_next_synthetic_protocol_work_order,
    initialize_synthetic_protocol_execution,
    read_synthetic_protocol_execution_status,
    recover_current_synthetic_protocol_work_order,
    validate_synthetic_protocol_execution,
)
from acoustic_ladder.protocol.synthetic_execution_models import (
    SyntheticProtocolExecutionControl,
)
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore
from tests.dev05.test_protocol_rehearsal import _published_plan

PROJECT_ROOT = Path(__file__).parents[2]
FIXED_TIME = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_initialize_derives_first_work_item_without_creating_a_session(tmp_path: Path) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path, stage=1)
    session_store = ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "synthetic", real=tmp_path / "real")
    )
    execution_store = DevelopmentSyntheticProtocolExecutionStore(tmp_path / "execution-root")
    scenario = load_conditioned_virtual_capture_scenario(
        PROJECT_ROOT / "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml",
        project_root=PROJECT_ROOT,
    )
    ess = publish_offline_ess_artifact(tmp_path / "ess", "execution-ess", bundle.configs["audio"])

    initialized = initialize_synthetic_protocol_execution(
        store=execution_store,
        session_store=session_store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        execution_id="stage1-execution",
        scenario=scenario,
        ess_artifact_root=ess.artifact_root,
        now=lambda: FIXED_TIME,
    )
    status = read_synthetic_protocol_execution_status(
        store=execution_store,
        session_store=session_store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-plan",
        execution_id="stage1-execution",
        scenario=scenario,
        ess_artifact_root=ess.artifact_root,
    )

    assert status == initialized
    assert status.execution_state == "active"
    assert status.cursor == 0
    assert status.total_work_order_count == 152
    assert status.current_work_order is not None
    assert status.current_work_order.global_planned_ordinal == 1
    assert status.current_work_order.session_id == "sx_stage1-execution_s01"
    assert status.current_work_order.reassembly_id == "sx_stage1-execution_s01_r01"
    assert status.current_work_order.run_id == "sx_stage1-execution_w000001"
    assert status.current_work_order.capture_id == status.current_work_order.run_id
    assert status.current_work_order.node_states
    assert status.current_work_order.protocol_execution_performed is False
    assert status.current_work_order.measurement_performed is False
    assert status.hardware_io_performed is False
    assert status.synthetic_capture_performed is False
    assert not (tmp_path / "synthetic").exists()
    assert not (tmp_path / "real").exists()


def _control(status, action: str, reason: str | None = None):
    token = status.concurrency_token
    return SyntheticProtocolExecutionControl.model_validate(
        {
            "action": action,
            "actor_id": "synthetic-runner",
            "expected_event_sequence": token.event_sequence,
            "expected_head_sha256": token.head_event_sha256,
            "expected_current_work_order_sha256": token.current_work_order_sha256,
            "expected_cursor": token.cursor,
            "reason_code": reason,
        }
    )


def _execution_setup(tmp_path: Path, *, stage: int = 1, execution_id: str = "execution"):
    bundle, spec, plan_store = _published_plan(tmp_path, stage=stage)
    session_store = ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "synthetic", real=tmp_path / "real")
    )
    execution_store = DevelopmentSyntheticProtocolExecutionStore(tmp_path / "execution-root")
    scenario = load_conditioned_virtual_capture_scenario(
        PROJECT_ROOT / "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml",
        project_root=PROJECT_ROOT,
    )
    ess = publish_offline_ess_artifact(tmp_path / "ess", "execution-ess", bundle.configs["audio"])
    common = {
        "store": execution_store,
        "session_store": session_store,
        "plan_store": plan_store,
        "bundle": bundle,
        "spec": spec,
        "plan_id": f"stage{stage}-plan",
        "execution_id": execution_id,
        "scenario": scenario,
        "ess_artifact_root": ess.artifact_root,
    }
    return common, session_store


def test_pause_resume_abort_and_terminal_rejection_are_event_sourced(tmp_path: Path) -> None:
    common, _ = _execution_setup(tmp_path)
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    paused = apply_synthetic_protocol_execution_control(
        **common,
        command=_control(status, "pause"),
        concurrency_token=status.concurrency_token,
        now=lambda: FIXED_TIME,
    )
    assert paused.execution_state == "paused"
    with pytest.raises(SyntheticProtocolExecutionError):
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=paused.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )
    resumed = apply_synthetic_protocol_execution_control(
        **common,
        command=_control(paused, "resume"),
        concurrency_token=paused.concurrency_token,
        now=lambda: FIXED_TIME,
    )
    aborted = apply_synthetic_protocol_execution_control(
        **common,
        command=_control(resumed, "abort", "operator_abort"),
        concurrency_token=resumed.concurrency_token,
        now=lambda: FIXED_TIME,
    )
    assert aborted.execution_state == "aborted"
    with pytest.raises(SyntheticProtocolExecutionError):
        apply_synthetic_protocol_execution_control(
            **common,
            command=_control(aborted, "abort", "again"),
            concurrency_token=aborted.concurrency_token,
            now=lambda: FIXED_TIME,
        )


def test_capture_event_boundary_requires_explicit_recovery_and_adopts_once(
    tmp_path: Path,
) -> None:
    common, session_store = _execution_setup(tmp_path)
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)

    def fail(stage: str) -> None:
        if stage == "after_capture_before_event":
            raise RuntimeError("injected capture/event boundary")

    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
            fault_injector=fail,
        )
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is False
    orphan = read_synthetic_protocol_execution_status(**common)
    assert orphan.execution_state == "recovery_required"
    assert orphan.recovery_kind == "capture"
    assert orphan.cursor == 0

    recovered = recover_current_synthetic_protocol_work_order(
        **common,
        concurrency_token=orphan.concurrency_token,
        actor_id="recovery-runner",
        now=lambda: FIXED_TIME,
    )
    assert recovered.cursor == 1
    assert recovered.execution_state == "active"
    first = status.current_work_order
    assert first is not None
    assert (
        session_store.validate_run(DataOrigin.SYNTHETIC, first.session_id, first.run_id).run_id
        == first.run_id
    )
    with pytest.raises(SyntheticProtocolExecutionError):
        recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=orphan.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )


def test_failed_capture_requires_retry_and_preserves_work_order_identity(tmp_path: Path) -> None:
    common, _ = _execution_setup(tmp_path)
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)

    def fail(stage: str) -> None:
        if stage == "after_session_before_capture":
            raise RuntimeError("injected pre-capture failure")

    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
            fault_injector=fail,
        )
    assert raised.value.capture_published is False
    assert raised.value.ledger_event_published is True
    failed = read_synthetic_protocol_execution_status(**common)
    assert failed.execution_state == "failed"
    assert failed.current_work_order == status.current_work_order
    retried = apply_synthetic_protocol_execution_control(
        **common,
        command=_control(failed, "retry"),
        concurrency_token=failed.concurrency_token,
        now=lambda: FIXED_TIME,
    )
    assert retried.execution_state == "active"
    assert retried.current_work_order == status.current_work_order


def test_two_threads_with_one_token_publish_at_most_one_run_and_event(tmp_path: Path) -> None:
    common, session_store = _execution_setup(tmp_path)
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)

    def execute():
        return execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute) for _ in range(2)]
    successes = [future.result() for future in futures if future.exception() is None]
    failures = [future.exception() for future in futures if future.exception() is not None]
    assert len(successes) == 1
    assert len(failures) == 1
    assert successes[0].cursor == 1
    first = status.current_work_order
    assert first is not None
    raw = session_store.session_path(DataOrigin.SYNTHETIC, first.session_id) / "raw"
    assert [path.name for path in raw.iterdir()] == [f"run_{first.run_id}"]
    events = common["store"].execution_path("execution") / "events"
    assert len(list(events.glob("event_*.json"))) == 1


@pytest.mark.parametrize("stage, expected", [(1, 152), (2, 32), (3, 32), (4, 128)])
def test_stage_work_order_counts_are_derived_from_each_compiled_plan(
    tmp_path: Path, stage: int, expected: int
) -> None:
    common, _ = _execution_setup(tmp_path, stage=stage, execution_id=f"stage{stage}-execution")
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    assert status.total_work_order_count == expected
    assert status.current_work_order is not None
    assert status.current_work_order.experiment_stage == stage
    orders = derive_synthetic_protocol_work_orders(
        plan_store=common["plan_store"],
        bundle=common["bundle"],
        spec=common["spec"],
        plan_id=common["plan_id"],
        execution_id=common["execution_id"],
    )
    assert len(orders) == expected
    assert [item.global_planned_ordinal for item in orders] == list(range(1, expected + 1))
    if stage == 2:
        assert len({item.condition_id for item in orders}) == 4
        assert any(any(state.proxy_state for state in item.node_states.values()) for item in orders)
    if stage == 3:
        assert len({item.condition_id for item in orders}) == 4
    if stage == 4:
        assert len({item.condition_id for item in orders}) == 16


@pytest.mark.parametrize("unsafe", ["", ".", "..", "../escape", "a/b", "a\\b", "x" * 33])
def test_unsafe_execution_id_is_rejected_without_execution_root(
    tmp_path: Path, unsafe: str
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id=unsafe)
    with pytest.raises(SyntheticProtocolExecutionError):
        initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    assert not (tmp_path / "execution-root").exists()


def test_concurrent_initialization_has_one_create_only_winner(tmp_path: Path) -> None:
    common, _ = _execution_setup(tmp_path)

    def initialize():
        return initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(initialize) for _ in range(2)]
    assert sum(future.exception() is None for future in futures) == 1
    assert (
        sum(isinstance(future.exception(), SyntheticProtocolExecutionError) for future in futures)
        == 1
    )
    assert read_synthetic_protocol_execution_status(**common).cursor == 0


def test_concurrent_recovery_adopts_orphan_once(tmp_path: Path) -> None:
    common, _ = _execution_setup(tmp_path)
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)

    def fail(stage: str) -> None:
        if stage == "after_capture_before_event":
            raise RuntimeError("injected orphan")

    with pytest.raises(SyntheticProtocolExecutionError):
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
            fault_injector=fail,
        )
    orphan = read_synthetic_protocol_execution_status(**common)

    def recover():
        return recover_current_synthetic_protocol_work_order(
            **common,
            concurrency_token=orphan.concurrency_token,
            actor_id="recovery-runner",
            now=lambda: FIXED_TIME,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recover) for _ in range(2)]
    assert sum(future.exception() is None for future in futures) == 1
    assert read_synthetic_protocol_execution_status(**common).cursor == 1


def test_manifest_tamper_is_read_only_rejected_and_original_bytes_recover(
    tmp_path: Path,
) -> None:
    common, _ = _execution_setup(tmp_path)
    initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    root = common["store"].execution_path("execution")
    manifest = root / "synthetic_execution_manifest.json"
    original = manifest.read_bytes()
    tampered = original.replace(b"execution", b"executioX", 1)
    assert tampered != original
    manifest.write_bytes(tampered)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(SyntheticProtocolExecutionError):
        read_synthetic_protocol_execution_status(**common)
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
    manifest.write_bytes(original)
    assert read_synthetic_protocol_execution_status(**common).execution_state == "active"


def test_execution_persisted_models_are_exported_as_schemas(tmp_path: Path) -> None:
    exported = {path.name for path in export_schemas(tmp_path)}
    assert {
        "synthetic_protocol_execution_manifest.schema.json",
        "synthetic_protocol_execution_record.schema.json",
        "synthetic_protocol_execution_event.schema.json",
        "synthetic_protocol_execution_completion.schema.json",
        "plan_bound_synthetic_capture_receipt.schema.json",
    }.issubset(exported)


def test_execution_cli_init_and_status_are_explicitly_synthetic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    common, _ = _execution_setup(tmp_path, execution_id="cli-execution")
    base = [
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
        "config/synthetic/default.yaml",
        "--plan-spec",
        "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        "--development-plan-root",
        str(common["plan_store"].root),
        "--plan-id",
        "stage1-plan",
        "--development-execution-root",
        str(common["store"].root),
        "--synthetic-root",
        str(tmp_path / "synthetic"),
        "--execution-id",
        "cli-execution",
        "--scenario",
        "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml",
        "--ess-artifact-root",
        str(common["ess_artifact_root"]),
    ]
    cli.main(["synthetic-protocol-execution-init", *base])
    output = capsys.readouterr().out
    assert "PASS development synthetic protocol execution" in output
    assert "data_origin=synthetic" in output
    assert "hardware_io_performed=false" in output
    assert "experimental_result=false" in output
    cli.main(["synthetic-protocol-execution-status", *base])
    assert "state=active cursor=0" in capsys.readouterr().out


@pytest.mark.parametrize(
    "forbidden",
    [
        "--real-root",
        "--device",
        "--input-device",
        "--output-device",
        "--host-api",
        "--play",
        "--record",
        "--stream",
        "--calibration",
        "--condition-id",
        "--run-id",
        "--node-state",
    ],
)
def test_execution_cli_rejects_forbidden_authority(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        cli.main(["synthetic-protocol-execution-status", forbidden, "forbidden"])


def test_execute_next_publishes_one_plan_bound_capture_and_advances_once(
    tmp_path: Path,
) -> None:
    bundle, spec, plan_store = _published_plan(tmp_path, stage=1)
    session_store = ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "synthetic", real=tmp_path / "real")
    )
    execution_store = DevelopmentSyntheticProtocolExecutionStore(tmp_path / "execution-root")
    scenario = load_conditioned_virtual_capture_scenario(
        PROJECT_ROOT / "tests/fixtures/audio/conditioned_virtual_duplex_development.yaml",
        project_root=PROJECT_ROOT,
    )
    ess = publish_offline_ess_artifact(tmp_path / "ess", "execution-ess", bundle.configs["audio"])
    common = {
        "store": execution_store,
        "session_store": session_store,
        "plan_store": plan_store,
        "bundle": bundle,
        "spec": spec,
        "plan_id": "stage1-plan",
        "execution_id": "stage1-execution",
        "scenario": scenario,
        "ess_artifact_root": ess.artifact_root,
    }
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    first = status.current_work_order
    assert first is not None

    advanced = execute_next_synthetic_protocol_work_order(
        **common,
        concurrency_token=status.concurrency_token,
        actor_id="synthetic-runner",
        now=lambda: FIXED_TIME,
    )

    assert advanced.execution_state == "active"
    assert advanced.cursor == 1
    assert advanced.successful_work_order_count == 1
    assert advanced.current_work_order is not None
    assert advanced.current_work_order.global_planned_ordinal == 2
    session = session_store.validate_session(DataOrigin.SYNTHETIC, first.session_id)
    run = session_store.validate_run(DataOrigin.SYNTHETIC, first.session_id, first.run_id)
    assert first.reassembly_id in session.reassembly_ids
    assert run.node_states == first.node_states
    assert run.measurement_order == first.session_local_measurement_order
    receipt_path = session_store.session_path(DataOrigin.SYNTHETIC, first.session_id) / (
        f"raw/run_{first.run_id}/capture_receipt.json"
    )
    receipt = receipt_path.read_text(encoding="utf-8")
    assert first.work_order_sha256 in receipt
    assert first.condition_id in receipt
    assert not (tmp_path / "real").exists()


def test_final_success_event_requires_explicit_completion_recovery(tmp_path: Path) -> None:
    common, _ = _execution_setup(tmp_path, stage=2, execution_id="completion-recovery")
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    while status.cursor < status.total_work_order_count - 1:
        status = execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
        )

    def fail(stage: str) -> None:
        if stage == "after_event_before_completion":
            raise RuntimeError("injected event/completion boundary")

    with pytest.raises(SyntheticProtocolExecutionError) as raised:
        execute_next_synthetic_protocol_work_order(
            **common,
            concurrency_token=status.concurrency_token,
            actor_id="synthetic-runner",
            now=lambda: FIXED_TIME,
            fault_injector=fail,
        )
    assert raised.value.capture_published is True
    assert raised.value.ledger_event_published is True
    assert raised.value.completion_published is False
    recovery = read_synthetic_protocol_execution_status(**common)
    assert recovery.execution_state == "recovery_required"
    assert recovery.recovery_kind == "completion"
    assert recovery.cursor == 32
    complete = recover_current_synthetic_protocol_work_order(
        **common,
        concurrency_token=recovery.concurrency_token,
        actor_id="recovery-runner",
        now=lambda: FIXED_TIME,
    )
    assert complete.execution_state == "complete"
    assert complete.cursor == 32
    assert validate_synthetic_protocol_execution(**common) == complete
    completion_root = common["store"].execution_path("completion-recovery")
    marker = completion_root / "SYNTHETIC_EXECUTION_COMPLETE"
    original_marker = marker.read_bytes()
    marker.write_bytes(b"tampered\n")
    before = {
        path.relative_to(completion_root).as_posix(): path.read_bytes()
        for path in completion_root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(SyntheticProtocolExecutionError):
        read_synthetic_protocol_execution_status(**common)
    after = {
        path.relative_to(completion_root).as_posix(): path.read_bytes()
        for path in completion_root.rglob("*")
        if path.is_file()
    }
    assert after == before
    marker.write_bytes(original_marker)
    assert validate_synthetic_protocol_execution(**common).execution_state == "complete"


def test_event_and_wav_tamper_are_read_only_rejected_then_originals_recover(
    tmp_path: Path,
) -> None:
    common, session_store = _execution_setup(tmp_path)
    status = initialize_synthetic_protocol_execution(**common, now=lambda: FIXED_TIME)
    status = execute_next_synthetic_protocol_work_order(
        **common,
        concurrency_token=status.concurrency_token,
        actor_id="synthetic-runner",
        now=lambda: FIXED_TIME,
    )
    root = common["store"].execution_path("execution")
    event = root / "events/event_00000001.json"
    event_sidecar = root / "events/event_00000001.sha256"
    original_event = event.read_bytes()
    original_sidecar = event_sidecar.read_bytes()
    changed = original_event.replace(b'"cursor_after": 1', b'"cursor_after": 2')
    assert changed != original_event
    event.write_bytes(changed)
    event_sidecar.write_bytes(
        f"{hashlib.sha256(changed).hexdigest()}  event_00000001.json\n".encode("ascii")
    )
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(SyntheticProtocolExecutionError):
        read_synthetic_protocol_execution_status(**common)
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
    event.write_bytes(original_event)
    event_sidecar.write_bytes(original_sidecar)

    first = derive_synthetic_protocol_work_orders(
        plan_store=common["plan_store"],
        bundle=common["bundle"],
        spec=common["spec"],
        plan_id=common["plan_id"],
        execution_id=common["execution_id"],
    )[0]
    wav = (
        session_store.session_path(DataOrigin.SYNTHETIC, first.session_id)
        / f"raw/run_{first.run_id}/simulated_input.wav"
    )
    original_wav = wav.read_bytes()
    wav.write_bytes(original_wav[:-1] + bytes([original_wav[-1] ^ 1]))
    with pytest.raises(SyntheticProtocolExecutionError):
        read_synthetic_protocol_execution_status(**common)
    wav.write_bytes(original_wav)
    assert read_synthetic_protocol_execution_status(**common) == status


def test_public_execution_entrypoints_expose_no_plan_fact_or_hardware_authority() -> None:
    forbidden = {
        "condition_id",
        "node_states",
        "session_index",
        "reassembly_index",
        "measurement_order",
        "run_id",
        "capture_id",
        "real_root",
        "device",
        "host_api",
        "gain",
        "latency",
        "waveform",
        "impulse_response",
    }
    for entrypoint in (
        initialize_synthetic_protocol_execution,
        execute_next_synthetic_protocol_work_order,
        recover_current_synthetic_protocol_work_order,
        apply_synthetic_protocol_execution_control,
    ):
        assert forbidden.isdisjoint(inspect.signature(entrypoint).parameters)


def test_new_execution_modules_do_not_import_hardware_audio_api() -> None:
    for relative in (
        "src/acoustic_ladder/protocol/synthetic_execution.py",
        "src/acoustic_ladder/protocol/synthetic_execution_models.py",
        "src/acoustic_ladder/protocol/plan_bound_capture.py",
    ):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "sounddevice" not in source
        assert "SoundDevice" not in source
        assert ".play(" not in source
        assert ".record(" not in source
        assert "Stream(" not in source
