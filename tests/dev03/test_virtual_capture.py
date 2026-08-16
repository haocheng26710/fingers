import ast
import hashlib
import inspect
import json
import math
import struct
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from acoustic_ladder import cli
from acoustic_ladder.audio.ess import generate_ess, spec_from_audio_config
from acoustic_ladder.audio.excitation_persistence import publish_offline_ess_artifact
from acoustic_ladder.audio.virtual_capture import CaptureStateMachine, VirtualCaptureEngine
from acoustic_ladder.audio.virtual_capture_backend import BackendBlockResult
from acoustic_ladder.audio.virtual_capture_models import (
    CaptureState,
    CaptureTransitionError,
    FaultMode,
    LoadedVirtualCaptureScenario,
    VirtualCaptureExecutionError,
    VirtualCaptureScenario,
    VirtualScenarioError,
    load_virtual_capture_scenario,
)
from acoustic_ladder.audio.virtual_capture_persistence import (
    VirtualCapturePersistenceError,
    publish_virtual_capture,
    validate_virtual_capture,
)
from acoustic_ladder.config.bundle import (
    LoadedBundle,
    canonical_json_bytes,
    load_bundle,
    load_config,
)
from acoustic_ladder.config.models import AudioConfig
from acoustic_ladder.domain.models import DataOrigin, ReassemblyRecord, RunMode, SessionRecord
from acoustic_ladder.storage.io import StorageError
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore

PROJECT_ROOT = Path(__file__).parents[2]
SCENARIO_PATH = PROJECT_ROOT / "tests/fixtures/audio/virtual_duplex_development.yaml"
FIXED_TIME = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _scenario() -> VirtualCaptureScenario:
    return load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT).model


def _ess() -> tuple[np.ndarray, int]:
    loaded = load_config(
        "audio",
        PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        project_root=PROJECT_ROOT,
    )
    assert isinstance(loaded.model, AudioConfig)
    generated = generate_ess(spec_from_audio_config(loaded.model))
    return generated.samples, loaded.model.sample_rate_hz


def _development_bundle() -> LoadedBundle:
    return load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols/stage4_four_node_states.yaml",
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )


def _capture_setup(tmp_path: Path) -> tuple[ImmutableSessionStore, LoadedBundle, Path, Path]:
    synthetic_root = tmp_path / "synthetic"
    real_root = tmp_path / "real"
    store = ImmutableSessionStore(DataRoots(synthetic=synthetic_root, real=real_root))
    bundle = _development_bundle()
    session = SessionRecord(
        session_id="capture-session",
        session_schema_version="1.0.0",
        created_at=FIXED_TIME,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        operator=None,
        device_manifest_reference="manifest/device_manifest.provisional.json",
        config_bundle_reference="protocol/config_bundle.json",
        reassembly_ids=["assembly-1"],
        run_ids=[],
        immutable_status="immutable",
        notes="virtual capture test",
    )
    reassembly = ReassemblyRecord(
        reassembly_id="assembly-1",
        session_id=session.session_id,
        sequence_index=0,
        created_at=FIXED_TIME,
        assembly_description="virtual capture test assembly",
        operator_confirmation=False,
        related_run_ids=[],
    )
    store.create_synthetic_session(session, [reassembly], bundle)
    ess = publish_offline_ess_artifact(tmp_path / "ess", "source-ess", bundle.configs["audio"])
    return store, bundle, ess.artifact_root, real_root


def _scenario_payload(**updates: object) -> dict[str, object]:
    payload = _scenario().model_dump(mode="json")
    payload.update(updates)
    return payload


def _loaded_scenario(tmp_path: Path, **updates: object) -> LoadedVirtualCaptureScenario:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(_scenario_payload(**updates)), encoding="utf-8")
    return load_virtual_capture_scenario(path, project_root=tmp_path)


def test_load_nominal_virtual_capture_scenario() -> None:
    loaded = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)

    assert loaded.model.scenario_id == "virtual_duplex_nominal_v1"
    assert loaded.model.block_size_frames == 256
    assert loaded.model.integer_latency_samples == 37
    assert loaded.model.capture_tail_samples == 64
    assert loaded.model.linear_gain == 0.5
    assert loaded.model.fault_mode == "none"
    assert loaded.model.fault_block_index is None
    assert loaded.source_path == SCENARIO_PATH.resolve()
    assert loaded.project_root == PROJECT_ROOT.resolve()
    assert loaded.original_relative_path == ("tests/fixtures/audio/virtual_duplex_development.yaml")
    assert loaded.original_sha256 == (
        "74eefa7181d739272726fd59472ae0cd766ec7a8a9391b9a566f0031d6a81ab2"
    )
    assert loaded.normalized_sha256 == (
        "cd5b82148d5fb88ea1fd86737510504030bca219ebe61de018b0f0b00bf90dbe"
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"block_size_frames": 0}, "greater than 0"),
        ({"block_size_frames": -1}, "greater than 0"),
        ({"integer_latency_samples": -1}, "greater than or equal to 0"),
        ({"capture_tail_samples": 36}, "must cover"),
        ({"linear_gain": 0.0}, "greater than 0"),
        ({"linear_gain": -0.5}, "greater than 0"),
        ({"fault_mode": "dropout", "fault_block_index": None}, "required"),
        ({"fault_mode": "none", "fault_block_index": 0}, "must be null"),
        ({"unexpected": "field"}, "Extra inputs"),
    ],
)
def test_virtual_capture_scenario_rejects_invalid_values(
    tmp_path: Path, updates: dict[str, object], message: str
) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(_scenario_payload(**updates)), encoding="utf-8")
    with pytest.raises(VirtualScenarioError, match=message):
        load_virtual_capture_scenario(path, project_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("block_size_frames", "256"),
        ("block_size_frames", True),
        ("linear_gain", "0.5"),
        ("linear_gain", math.nan),
        ("linear_gain", math.inf),
    ],
)
def test_virtual_capture_scenario_is_numeric_strict(
    tmp_path: Path, field: str, value: object
) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(_scenario_payload(**{field: value})), encoding="utf-8")
    with pytest.raises(VirtualScenarioError):
        load_virtual_capture_scenario(path, project_root=tmp_path)


def test_virtual_capture_scenario_must_be_inside_project_root(tmp_path: Path) -> None:
    with pytest.raises(VirtualScenarioError, match="inside project root"):
        load_virtual_capture_scenario(SCENARIO_PATH, project_root=tmp_path)


def test_capture_state_machine_records_normal_sequence() -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    machine.transition(CaptureState.PREPARED, "backend prepared")
    machine.transition(CaptureState.ARMED, "backend armed")
    machine.transition(CaptureState.RUNNING, "exchange started")
    machine.complete(sample_cursor=10, completed_block_count=2)

    assert [record.to_state for record in machine.transitions] == [
        CaptureState.PREPARED,
        CaptureState.ARMED,
        CaptureState.RUNNING,
        CaptureState.COMPLETED,
    ]
    assert [record.sequence for record in machine.transitions] == [1, 2, 3, 4]
    assert machine.state is CaptureState.COMPLETED


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (CaptureState.ARMED, "illegal capture state transition"),
        (CaptureState.RUNNING, "illegal capture state transition"),
        (CaptureState.COMPLETED, "illegal capture state transition"),
    ],
)
def test_capture_state_machine_cannot_skip_prepared(target: CaptureState, message: str) -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    with pytest.raises(CaptureTransitionError, match=message):
        machine.transition(target, "invalid")


@pytest.mark.parametrize("terminal", [CaptureState.FAILED, CaptureState.ABORTED])
def test_capture_state_machine_terminal_states_cannot_continue(
    terminal: CaptureState,
) -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    machine.transition(CaptureState.PREPARED, "prepared")
    machine.transition(terminal, "stopped")
    with pytest.raises(CaptureTransitionError, match="terminal"):
        machine.transition(CaptureState.ARMED, "too late")


def test_capture_state_machine_rejects_early_completion() -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    machine.transition(CaptureState.PREPARED, "prepared")
    machine.transition(CaptureState.ARMED, "armed")
    machine.transition(CaptureState.RUNNING, "running")
    with pytest.raises(CaptureTransitionError, match="sample cursor"):
        machine.complete(sample_cursor=9, completed_block_count=1)


def test_capture_state_machine_rejects_completion_with_unhandled_flag() -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    machine.transition(CaptureState.PREPARED, "prepared")
    machine.transition(CaptureState.ARMED, "armed")
    machine.transition(CaptureState.RUNNING, "running")
    with pytest.raises(CaptureTransitionError, match="unhandled backend status"):
        machine.complete(sample_cursor=10, completed_block_count=1, has_unhandled_status=True)


@pytest.mark.parametrize("terminal", [CaptureState.FAILED, CaptureState.ABORTED])
@pytest.mark.parametrize(
    "source",
    [CaptureState.CREATED, CaptureState.PREPARED, CaptureState.ARMED, CaptureState.RUNNING],
)
def test_capture_state_machine_allows_declared_terminal_paths(
    source: CaptureState, terminal: CaptureState
) -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    if source is not CaptureState.CREATED:
        machine.transition(CaptureState.PREPARED, "prepared")
    if source in {CaptureState.ARMED, CaptureState.RUNNING}:
        machine.transition(CaptureState.ARMED, "armed")
    if source is CaptureState.RUNNING:
        machine.transition(CaptureState.RUNNING, "running")
    machine.transition(terminal, "stopped", sample_cursor=4, completed_block_count=1)
    assert machine.state is terminal


def test_capture_state_machine_rejects_prepared_to_running_jump() -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    machine.transition(CaptureState.PREPARED, "prepared")
    with pytest.raises(CaptureTransitionError, match="illegal capture state transition"):
        machine.transition(CaptureState.RUNNING, "skipped arm")


def test_capture_state_machine_completed_state_is_terminal() -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    machine.transition(CaptureState.PREPARED, "prepared")
    machine.transition(CaptureState.ARMED, "armed")
    machine.transition(CaptureState.RUNNING, "running")
    machine.complete(sample_cursor=10, completed_block_count=1)
    with pytest.raises(CaptureTransitionError, match="terminal"):
        machine.complete(sample_cursor=10, completed_block_count=1)


def test_capture_state_machine_rejects_backwards_sample_cursor() -> None:
    machine = CaptureStateMachine(expected_sample_count=10)
    machine.transition(CaptureState.PREPARED, "prepared", sample_cursor=2)
    with pytest.raises(CaptureTransitionError, match="cannot move backwards"):
        machine.transition(CaptureState.ARMED, "armed", sample_cursor=1)


def test_nominal_virtual_capture_is_exact_blockwise_delay_and_gain() -> None:
    excitation, rate = _ess()
    result = VirtualCaptureEngine().execute(excitation, rate, _scenario())

    assert result.output_samples.shape == (1, 13024)
    assert result.input_samples.shape == (1, 13024)
    assert result.output_samples.dtype == np.float32
    assert result.input_samples.dtype == np.float32
    assert result.output_samples.flags.c_contiguous
    assert result.input_samples.flags.c_contiguous
    assert np.array_equal(result.output_samples[:, :12960], excitation)
    assert np.array_equal(result.output_samples[:, 12960:], np.zeros((1, 64), np.float32))
    assert np.array_equal(result.input_samples[:, :37], np.zeros((1, 37), np.float32))
    assert np.array_equal(
        result.input_samples[:, 37:], result.output_samples[:, :-37] * np.float32(0.5)
    )
    assert result.planned_block_count == 51
    assert result.actual_block_count == 51
    assert result.block_trace[-1].requested_frame_count == 224
    assert result.final_state is CaptureState.COMPLETED


def test_nominal_virtual_capture_block_trace_is_contiguous() -> None:
    excitation, rate = _ess()
    result = VirtualCaptureEngine().execute(excitation, rate, _scenario())

    assert [block.sequence for block in result.block_trace] == list(range(1, 52))
    assert [block.start_frame for block in result.block_trace] == [
        index * 256 for index in range(51)
    ]
    assert all(
        left.start_frame + left.requested_frame_count == right.start_frame
        for left, right in zip(result.block_trace, result.block_trace[1:], strict=False)
    )
    assert all(block.status_flags == [] for block in result.block_trace)


def test_nominal_virtual_capture_is_deterministic() -> None:
    excitation, rate = _ess()
    first = VirtualCaptureEngine().execute(excitation, rate, _scenario())
    second = VirtualCaptureEngine().execute(excitation, rate, _scenario())
    assert np.array_equal(first.output_samples, second.output_samples)
    assert np.array_equal(first.input_samples, second.input_samples)
    assert first.block_trace == second.block_trace
    assert first.transitions == second.transitions


@pytest.mark.parametrize(
    ("fault_mode", "expected_state", "error_code"),
    [
        (FaultMode.SHORT_INPUT_BLOCK, CaptureState.FAILED, "short_input_block"),
        (FaultMode.DROPOUT, CaptureState.FAILED, "dropout"),
        (FaultMode.CLIPPING, CaptureState.FAILED, "clipping"),
        (FaultMode.BACKEND_ERROR, CaptureState.FAILED, "backend_error"),
        (FaultMode.ABORT_REQUESTED, CaptureState.ABORTED, "abort_requested"),
    ],
)
def test_virtual_capture_faults_stop_without_completion(
    fault_mode: FaultMode, expected_state: CaptureState, error_code: str
) -> None:
    excitation, rate = _ess()
    scenario = VirtualCaptureScenario.model_validate(
        {**_scenario().model_dump(), "fault_mode": fault_mode, "fault_block_index": 2}
    )
    with pytest.raises(VirtualCaptureExecutionError) as caught:
        VirtualCaptureEngine().execute(excitation, rate, scenario)
    assert caught.value.diagnostics.final_state is expected_state
    assert caught.value.diagnostics.error_code == error_code
    assert caught.value.diagnostics.fault_block_index == 2
    assert CaptureState.COMPLETED not in [
        transition.to_state for transition in caught.value.diagnostics.transitions
    ]


def test_virtual_capture_rejects_fault_block_outside_plan() -> None:
    excitation, rate = _ess()
    scenario = VirtualCaptureScenario.model_validate(
        {
            **_scenario().model_dump(),
            "fault_mode": FaultMode.DROPOUT,
            "fault_block_index": 51,
        }
    )
    with pytest.raises(VirtualCaptureExecutionError, match="outside planned block range"):
        VirtualCaptureEngine().execute(excitation, rate, scenario)


def test_virtual_capture_rejects_non_finite_backend_block() -> None:
    class NonFiniteBackend:
        def prepare(self, *, sample_rate_hz: int, total_frame_count: int) -> None:
            del sample_rate_hz, total_frame_count

        def arm(self) -> None:
            pass

        def exchange_block(
            self, output_block: np.ndarray, *, frame_count: int, block_index: int
        ) -> BackendBlockResult:
            del output_block, block_index
            return BackendBlockResult(np.full((1, frame_count), np.nan, dtype=np.float32))

        def close(self) -> None:
            pass

        def abort(self) -> None:
            pass

    excitation, rate = _ess()
    with pytest.raises(VirtualCaptureExecutionError) as caught:
        VirtualCaptureEngine().execute(excitation, rate, _scenario(), backend=NonFiniteBackend())
    assert caught.value.diagnostics.error_code == "non_finite_input"
    assert caught.value.diagnostics.final_state is CaptureState.FAILED


def test_virtual_capture_publication_has_no_real_origin_or_waveform_parameters() -> None:
    parameters = inspect.signature(publish_virtual_capture).parameters
    assert "origin" not in parameters
    assert "data_origin" not in parameters
    assert "waveform" not in parameters
    assert "spec" not in parameters
    assert "linear_gain" not in parameters
    assert "integer_latency_samples" not in parameters


def test_dev0304_modules_have_no_hardware_audio_or_sleep_calls() -> None:
    module_names = (
        "virtual_capture_models.py",
        "virtual_capture_backend.py",
        "virtual_capture.py",
        "virtual_capture_persistence.py",
    )
    forbidden_calls = {
        "query_devices",
        "query_hostapis",
        "check_input_settings",
        "check_output_settings",
        "InputStream",
        "OutputStream",
        "Stream",
        "play",
        "rec",
        "playrec",
        "sleep",
    }
    for name in module_names:
        path = PROJECT_ROOT / "src/acoustic_ladder/audio" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert "sounddevice" not in imports
        assert calls.isdisjoint(forbidden_calls)


@pytest.mark.parametrize(
    "forbidden_option", ["--real-root", "--linear-gain", "--integer-latency-samples"]
)
def test_simulate_cli_has_no_real_root_or_numeric_override(
    forbidden_option: str,
) -> None:
    arguments = [
        "simulate-duplex-capture",
        "--protocol",
        "config/protocols/stage4_four_node_states.yaml",
        "--synthetic-root",
        "synthetic",
        "--session-id",
        "session",
        "--reassembly-id",
        "assembly",
        "--run-id",
        "run",
        "--scenario",
        "tests/fixtures/audio/virtual_duplex_development.yaml",
        "--ess-artifact-root",
        "ess",
        forbidden_option,
        "1",
    ]
    with pytest.raises(SystemExit):
        cli._parser().parse_args(arguments)


def test_publish_virtual_capture_creates_exact_immutable_payload(tmp_path: Path) -> None:
    store, bundle, ess_root, real_root = _capture_setup(tmp_path)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT),
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )

    expected_payloads = {
        "excitation.metadata.json",
        "excitation.metadata.sha256",
        "output_reference.wav",
        "output_reference.wav.sha256",
        "simulated_input.wav",
        "simulated_input.wav.sha256",
        "capture_receipt.json",
        "capture_receipt.sha256",
    }
    assert {path.name for path in published.run_path.iterdir()} == expected_payloads | {
        "synthetic_metadata.json",
        "run_record.json",
        "RUN_COMPLETE",
    }
    assert published.receipt.capture_sample_count == 13024
    assert published.receipt.actual_block_count == 51
    assert published.receipt.last_block_frame_count == 224
    assert published.receipt.measurement_order == 0
    assert published.receipt.output_raw_float32_sha256 == (
        "51531aedf7b6d253085315bf2ffd1efc7c760de363bc68565756ed5b2c2b3621"
    )
    assert published.receipt.input_raw_float32_sha256 == (
        "284c6bd0d320dfd0d1a97015d80e0bcc6aff3b49d9a2befbe68e55b5ef550b81"
    )
    assert published.receipt.output_wav_sha256 == (
        "1aea497f8868d1f2e187b2ed1f80efd7b05e4c0a6084f1901dcc425180bdb508"
    )
    assert published.receipt.input_wav_sha256 == (
        "51d68378a916f82e9080cba276c8c5dfb386ffd19f4fb3c0b3dd9e9d594222b1"
    )
    assert published.receipt.data_origin == "synthetic"
    assert published.receipt.virtual_duplex_scheduler_exercised is True
    assert published.receipt.hardware_io_performed is False
    expected_metadata = {
        "capture_receipt_sha256": published.receipt_sha256,
        "data_origin": "synthetic",
        "hardware_io_performed": False,
        "safety_marker": "SYNTHETIC_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT",
    }
    assert (published.run_path / "synthetic_metadata.json").read_bytes() == (
        canonical_json_bytes(expected_metadata)
    )
    assert published.receipt.full_duplex_verified is False
    assert not real_root.exists()


def test_publish_rejects_forged_scenario_model_without_source_change(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    loaded = _loaded_scenario(tmp_path)
    forged_model = VirtualCaptureScenario.model_validate_json(
        json.dumps(_scenario_payload(linear_gain=0.25)), strict=True
    )
    forged_normalized = canonical_json_bytes(forged_model.model_dump(mode="json"))
    forged = replace(
        loaded,
        model=forged_model,
        normalized_bytes=forged_normalized,
        normalized_sha256=hashlib.sha256(forged_normalized).hexdigest(),
    )

    with pytest.raises(VirtualCapturePersistenceError, match="scenario source provenance"):
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=forged,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id="forged-scenario",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )

    raw = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "raw"
    assert not (raw / "run_forged-scenario").exists()
    assert not list(raw.glob(".run_forged-scenario.*"))


@pytest.mark.parametrize("source_change", ["modified", "deleted"])
def test_publish_rejects_scenario_source_changed_after_load_without_run_residue(
    tmp_path: Path, source_change: str
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    loaded = _loaded_scenario(tmp_path)
    if source_change == "modified":
        loaded.source_path.write_bytes(loaded.original_bytes + b"\n")
    else:
        loaded.source_path.unlink()

    with pytest.raises(VirtualCapturePersistenceError, match="scenario source provenance"):
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=loaded,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id=f"source-{source_change}",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )

    raw = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "raw"
    assert not (raw / f"run_source-{source_change}").exists()
    assert not list(raw.glob(f".run_source-{source_change}.*"))
    if source_change == "modified":
        assert loaded.source_path.read_bytes() == loaded.original_bytes + b"\n"
    else:
        assert not loaded.source_path.exists()


def test_publish_rejects_scenario_source_moved_outside_bound_project_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    loaded = _loaded_scenario(project)
    outside = tmp_path / "outside.json"
    loaded.source_path.replace(outside)
    moved = replace(loaded, source_path=outside)
    store, bundle, ess_root, _ = _capture_setup(tmp_path / "capture")

    with pytest.raises(VirtualCapturePersistenceError, match="inside project root"):
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=moved,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id="moved-scenario",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )

    raw = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "raw"
    assert not (raw / "run_moved-scenario").exists()


def test_validator_rejects_forged_scenario_against_current_source(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    loaded = _loaded_scenario(tmp_path)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=loaded,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    forged_model = VirtualCaptureScenario.model_validate_json(
        json.dumps(_scenario_payload(linear_gain=0.25)), strict=True
    )
    forged_normalized = canonical_json_bytes(forged_model.model_dump(mode="json"))
    forged = replace(
        loaded,
        model=forged_model,
        normalized_bytes=forged_normalized,
        normalized_sha256=hashlib.sha256(forged_normalized).hexdigest(),
    )
    before = (published.run_path / "capture_receipt.json").read_bytes()

    with pytest.raises(
        VirtualCapturePersistenceError,
        match=r"scenario source provenance.*published=true",
    ):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=forged,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )

    assert (published.run_path / "capture_receipt.json").read_bytes() == before


def test_validate_virtual_capture_replays_semantics(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    validated = validate_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        run_id="capture-1",
    )
    assert validated.receipt == published.receipt
    assert validated.receipt_sha256 == published.receipt_sha256


@pytest.mark.parametrize("tamper", ["semantic", "missing", "extra", "noncanonical"])
def test_validator_rejects_any_synthetic_metadata_envelope_tamper(
    tmp_path: Path, tamper: str
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = _loaded_scenario(tmp_path)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    metadata_path = published.run_path / "synthetic_metadata.json"
    value = json.loads(metadata_path.read_bytes())
    if tamper == "semantic":
        value["hardware_io_performed"] = True
        metadata_path.write_bytes(canonical_json_bytes(value))
    elif tamper == "missing":
        del value["hardware_io_performed"]
        metadata_path.write_bytes(canonical_json_bytes(value))
    elif tamper == "extra":
        value["unexpected"] = "field"
        metadata_path.write_bytes(canonical_json_bytes(value))
    else:
        metadata_path.write_text(json.dumps(value), encoding="utf-8")
    tampered_bytes = metadata_path.read_bytes()

    with pytest.raises(VirtualCapturePersistenceError, match="synthetic metadata envelope"):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )
    assert metadata_path.read_bytes() == tampered_bytes


@pytest.mark.parametrize(
    "tamper",
    [
        "measurement_order",
        "node_state",
        "software_version",
        "notes",
        "created_at",
        "started_at",
        "completed_at",
    ],
)
def test_validator_rejects_run_record_envelope_tamper(tmp_path: Path, tamper: str) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = _loaded_scenario(tmp_path)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=7,
        now=lambda: FIXED_TIME,
    )
    record_path = published.run_path / "run_record.json"
    value = json.loads(record_path.read_bytes())
    assert published.receipt.measurement_order == value["measurement_order"] == 7
    if tamper == "measurement_order":
        value["measurement_order"] = 999
    elif tamper == "node_state":
        first = sorted(value["node_states"])[0]
        value["node_states"][first]["module_id"] = "NOT_BLK"
    elif tamper == "software_version":
        value["software_version"] = "tampered"
    elif tamper == "notes":
        value["notes"] = "tampered"
    elif tamper == "created_at":
        value["created_at"] = "2026-08-16T11:59:59Z"
    elif tamper == "started_at":
        value["started_at"] = None
    else:
        value["completed_at"] = "2026-08-16T12:00:01Z"
    tampered_bytes = canonical_json_bytes(value)
    record_path.write_bytes(tampered_bytes)

    with pytest.raises(VirtualCapturePersistenceError, match="run record envelope"):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )
    assert record_path.read_bytes() == tampered_bytes


@pytest.mark.parametrize(
    "tamper",
    ["backend", "formal", "marker", "config_hash", "status_failure", "artifact_ref"],
)
def test_validator_rejects_remaining_run_record_contract_tamper(
    tmp_path: Path, tamper: str
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = _loaded_scenario(tmp_path)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    record_path = published.run_path / "run_record.json"
    value = json.loads(record_path.read_bytes())
    if tamper == "backend":
        value["backend"] = "tampered"
    elif tamper == "formal":
        value["formal_eligible"] = True
    elif tamper == "marker":
        value["result_marker"] = "tampered"
    elif tamper == "config_hash":
        value["config_hashes"]["bundle"] = "0" * 64
    elif tamper == "status_failure":
        value["status"] = "failed"
        value["failure_reason"] = None
    else:
        value["artifacts"][0]["sha256"] = "0" * 64
    tampered_bytes = canonical_json_bytes(value)
    record_path.write_bytes(tampered_bytes)

    with pytest.raises(StorageError):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )

    assert record_path.read_bytes() == tampered_bytes


@pytest.mark.parametrize("tamper", ["changed", "filename", "noncanonical", "deleted"])
def test_validator_rejects_stored_manifest_sidecar_tamper(tmp_path: Path, tamper: str) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = _loaded_scenario(tmp_path)
    publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    sidecar = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "manifest/device_manifest.provisional.sha256"
    )
    if tamper == "changed":
        sidecar.write_text(f"{'0' * 64}  device_manifest.provisional.json\n", encoding="ascii")
    elif tamper == "filename":
        sidecar.write_text(
            f"{bundle.receipt.device_manifest_sha256}  renamed.json\n",
            encoding="ascii",
        )
    elif tamper == "noncanonical":
        sidecar.write_bytes(bundle.manifest_sidecar_bytes + b"\n")
    else:
        sidecar.unlink()
    tampered_bytes = sidecar.read_bytes() if sidecar.exists() else None

    with pytest.raises(VirtualCapturePersistenceError, match="manifest sidecar"):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )
    if tampered_bytes is None:
        assert not sidecar.exists()
    else:
        assert sidecar.read_bytes() == tampered_bytes


def test_capture_payloads_are_byte_deterministic_across_separate_roots(
    tmp_path: Path,
) -> None:
    payload_names = {
        "excitation.metadata.json",
        "excitation.metadata.sha256",
        "output_reference.wav",
        "output_reference.wav.sha256",
        "simulated_input.wav",
        "simulated_input.wav.sha256",
        "capture_receipt.json",
        "capture_receipt.sha256",
    }
    published = []
    for root_name in ("first", "second"):
        store, bundle, ess_root, _ = _capture_setup(tmp_path / root_name)
        published.append(
            publish_virtual_capture(
                store=store,
                bundle=bundle,
                scenario=load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT),
                ess_artifact_root=ess_root,
                session_id="capture-session",
                reassembly_id="assembly-1",
                run_id="capture-1",
                measurement_order=0,
                now=lambda: FIXED_TIME,
            )
        )

    first, second = published
    assert first.receipt_sha256 == second.receipt_sha256
    for payload_name in payload_names:
        assert (first.run_path / payload_name).read_bytes() == (
            second.run_path / payload_name
        ).read_bytes()


def test_publish_virtual_capture_is_create_only(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    first = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    before = (first.run_path / "capture_receipt.json").read_bytes()
    with pytest.raises(VirtualCapturePersistenceError, match="published=true"):
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id="capture-1",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )
    assert (first.run_path / "capture_receipt.json").read_bytes() == before


def test_publish_rejects_negative_measurement_order_without_run_residue(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = _loaded_scenario(tmp_path)

    with pytest.raises(
        VirtualCapturePersistenceError,
        match=r"measurement_order must be non-negative.*published=false",
    ):
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id="negative-order",
            measurement_order=-1,
            now=lambda: FIXED_TIME,
        )

    raw = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "raw"
    assert not (raw / "run_negative-order").exists()
    assert not list(raw.glob(".run_negative-order.*"))


@pytest.mark.parametrize(
    "fault_mode",
    [
        FaultMode.SHORT_INPUT_BLOCK,
        FaultMode.DROPOUT,
        FaultMode.CLIPPING,
        FaultMode.BACKEND_ERROR,
        FaultMode.ABORT_REQUESTED,
    ],
)
def test_faulted_virtual_capture_does_not_publish_run(
    tmp_path: Path, fault_mode: FaultMode
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = _loaded_scenario(
        tmp_path,
        fault_mode=fault_mode.value,
        fault_block_index=1,
    )
    with pytest.raises(VirtualCaptureExecutionError):
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id="capture-fault",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )
    raw = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "raw"
    assert not (raw / "run_capture-fault").exists()
    assert not list(raw.glob(".run_capture-fault.*"))


def test_capture_validator_rejects_receipt_tamper_with_rehashed_sidecar(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    receipt_path = published.run_path / "capture_receipt.json"
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    value["linear_gain"] = 0.25
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    receipt_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (published.run_path / "capture_receipt.sha256").write_text(
        f"{digest}  capture_receipt.json\n", encoding="ascii"
    )
    with pytest.raises(StorageError):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )


def test_capture_validator_rejects_wav_tamper_even_after_digest_chain_update(
    tmp_path: Path,
) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    wav_path = published.run_path / "simulated_input.wav"
    payload = bytearray(wav_path.read_bytes())
    payload[-4:] = struct.pack("<f", 0.125)
    wav_path.write_bytes(payload)
    wav_digest = hashlib.sha256(payload).hexdigest()
    sidecar_payload = f"{wav_digest}  simulated_input.wav\n".encode("ascii")
    (published.run_path / "simulated_input.wav.sha256").write_bytes(sidecar_payload)
    run_path = published.run_path / "run_record.json"
    run_value = json.loads(run_path.read_text(encoding="utf-8"))
    replacements = {
        "simulated_input.wav": (wav_digest, len(payload)),
        "simulated_input.wav.sha256": (
            hashlib.sha256(sidecar_payload).hexdigest(),
            len(sidecar_payload),
        ),
    }
    for artifact in run_value["artifacts"]:
        for name, (artifact_digest, size) in replacements.items():
            if artifact["path"].endswith(name):
                artifact["sha256"] = artifact_digest
                artifact["byte_size"] = size
    run_path.write_bytes(canonical_json_bytes(run_value))
    with pytest.raises(VirtualCapturePersistenceError, match="semantic replay"):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )


def test_capture_validator_rejects_extra_file(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    published = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-1",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    (published.run_path / "undeclared.bin").write_bytes(b"extra")
    with pytest.raises(VirtualCapturePersistenceError, match="exactly the required files"):
        validate_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            run_id="capture-1",
        )


def test_capture_publication_rejects_run_id_escape_without_residue(tmp_path: Path) -> None:
    store, bundle, ess_root, _ = _capture_setup(tmp_path)
    with pytest.raises(StorageError, match="unsafe"):
        publish_virtual_capture(
            store=store,
            bundle=bundle,
            scenario=load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT),
            ess_artifact_root=ess_root,
            session_id="capture-session",
            reassembly_id="assembly-1",
            run_id="../escape",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )
    assert not (tmp_path / "escape").exists()


def test_formal_bundle_is_rejected_before_completed_capture_run(tmp_path: Path) -> None:
    formal_bundle = load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "config/audio/default_1x1_ess.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols/stage4_four_node_states.yaml",
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    store = ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "formal-synthetic", real=tmp_path / "formal-real")
    )
    session = SessionRecord(
        session_id="formal-session",
        session_schema_version="1.0.0",
        created_at=FIXED_TIME,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        operator=None,
        device_manifest_reference="manifest/device_manifest.provisional.json",
        config_bundle_reference="protocol/config_bundle.json",
        reassembly_ids=["assembly-1"],
        run_ids=[],
        immutable_status="immutable",
        notes="formal config negative test",
    )
    reassembly = ReassemblyRecord(
        reassembly_id="assembly-1",
        session_id="formal-session",
        sequence_index=0,
        created_at=FIXED_TIME,
        assembly_description="formal config negative",
        operator_confirmation=False,
        related_run_ids=[],
    )
    store.create_synthetic_session(session, [reassembly], formal_bundle)
    development_audio = load_config(
        "audio",
        PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        project_root=PROJECT_ROOT,
    )
    ess_root = publish_offline_ess_artifact(
        tmp_path / "formal-ess", "source-ess", development_audio
    ).artifact_root
    missing = (
        "ess_duration_s",
        "pre_silence_s",
        "post_silence_s",
        "ess_fade_in_s",
        "ess_fade_out_s",
        "ess_digital_peak_dbfs",
    )
    with pytest.raises(StorageError) as caught:
        publish_virtual_capture(
            store=store,
            bundle=formal_bundle,
            scenario=load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT),
            ess_artifact_root=ess_root,
            session_id="formal-session",
            reassembly_id="assembly-1",
            run_id="formal-rejected",
            measurement_order=0,
            now=lambda: FIXED_TIME,
        )
    assert all(field in str(caught.value) for field in missing)
    run = store.session_path(DataOrigin.SYNTHETIC, "formal-session") / "raw/run_formal-rejected"
    assert not run.exists()


def test_virtual_capture_cli_complete_workflow_has_required_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_backend() -> None:
        raise AssertionError("hardware inventory backend must not be requested")

    monkeypatch.setattr(cli, "_audio_backend", forbidden_backend)
    synthetic_root = tmp_path / "synthetic"
    ess_root = tmp_path / "ess"
    bundle_args = [
        "--project-root",
        str(PROJECT_ROOT),
        "--audio",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "--protocol",
        "config/protocols/stage4_four_node_states.yaml",
    ]
    cli.main(
        [
            "create-synthetic-session",
            *bundle_args,
            "--synthetic-root",
            str(synthetic_root),
            "--session-id",
            "cli-capture",
            "--reassembly-id",
            "assembly-1",
        ]
    )
    capsys.readouterr()
    cli.main(
        [
            "ess-generate-offline",
            "--project-root",
            str(PROJECT_ROOT),
            "--audio-config",
            "tests/fixtures/audio/ess_offline_development.yaml",
            "--development-root",
            str(ess_root),
            "--artifact-id",
            "source-ess",
        ]
    )
    capsys.readouterr()
    command = [
        *bundle_args,
        "--synthetic-root",
        str(synthetic_root),
        "--session-id",
        "cli-capture",
        "--scenario",
        "tests/fixtures/audio/virtual_duplex_development.yaml",
        "--ess-artifact-root",
        str(ess_root / "source-ess"),
    ]
    cli.main(
        [
            "simulate-duplex-capture",
            *command,
            "--reassembly-id",
            "assembly-1",
            "--run-id",
            "capture-1",
            "--measurement-order",
            "0",
        ]
    )
    generated = capsys.readouterr().out
    assert "PASS simulated duplex capture" in generated
    assert "SYNTHETIC_ONLY" in generated
    assert "NO_HARDWARE_AUDIO_IO_PERFORMED" in generated
    assert "NOT_AN_EXPERIMENTAL_RESULT" in generated
    assert "sample_count=13024" in generated
    assert "block_count=51" in generated
    assert "final_state=completed" in generated
    cli.main(
        [
            "validate-simulated-capture",
            *command,
            "--run-id",
            "capture-1",
        ]
    )
    validated = capsys.readouterr().out
    assert "PASS simulated capture validation" in validated
    assert "NO_HARDWARE_AUDIO_IO_PERFORMED" in validated
