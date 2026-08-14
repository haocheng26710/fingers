from __future__ import annotations

import json
from pathlib import Path

import pytest

from acoustic_ladder.config.bundle import LoadedBundle
from acoustic_ladder.domain.models import ArtifactRef, DataOrigin, NodeState
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes, confined_path
from acoustic_ladder.storage.store import (
    SESSION_DIRECTORIES,
    ImmutableSessionStore,
    verify_artifact,
)
from acoustic_ladder.synthetic.generator import SyntheticResult
from tests.dev02.conftest import (
    reassembly_record,
    run_record,
    session_record,
)


def _create_session(store: ImmutableSessionStore, bundle: LoadedBundle) -> Path:
    return store.create_synthetic_session(session_record(), [reassembly_record()], bundle)


def _create_run(
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    result: SyntheticResult,
    states: dict[str, NodeState],
) -> Path:
    record = run_record(result, states, bundle)
    return store.create_synthetic_run(
        record,
        {"synthetic_arrays.npz": result.npz_bytes},
        result.metadata,
    )


def test_create_synthetic_session_has_complete_layout_and_snapshots(
    store: ImmutableSessionStore, loaded_bundle: LoadedBundle
) -> None:
    session = _create_session(store, loaded_bundle)
    assert (session / "SESSION_COMPLETE").read_text(encoding="ascii") == "complete\n"
    assert all((session / name).is_dir() for name in SESSION_DIRECTORIES)
    assert (session / "session_record.json").is_file()
    assert (session / "manifest" / "device_manifest.provisional.json").is_file()
    assert (session / "manifest" / "device_manifest.provisional.sha256").is_file()
    receipt = json.loads((session / "protocol" / "config_bundle.json").read_text())
    assert receipt["bundle_content_sha256"] == loaded_bundle.receipt.bundle_content_sha256
    for kind, loaded in loaded_bundle.configs.items():
        assert (session / "protocol" / "config" / f"{kind}.normalized.json").read_bytes() == (
            loaded.normalized_bytes
        )


def test_duplicate_session_is_rejected_without_overwrite(
    store: ImmutableSessionStore, loaded_bundle: LoadedBundle
) -> None:
    session = _create_session(store, loaded_bundle)
    original = (session / "session_record.json").read_bytes()
    with pytest.raises(StorageError, match="already exists"):
        _create_session(store, loaded_bundle)
    assert (session / "session_record.json").read_bytes() == original


def test_duplicate_run_is_rejected_without_overwrite(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
) -> None:
    _create_session(store, loaded_bundle)
    run = _create_run(store, loaded_bundle, generated_result, blocked_states)
    original = (run / "synthetic_arrays.npz").read_bytes()
    with pytest.raises(StorageError, match="already exists"):
        _create_run(store, loaded_bundle, generated_result, blocked_states)
    assert (run / "synthetic_arrays.npz").read_bytes() == original


@pytest.mark.parametrize("relative", ["../escape", "nested/../../escape", "/absolute"])
def test_confined_path_rejects_escape_and_absolute_paths(tmp_path: Path, relative: str) -> None:
    with pytest.raises(StorageError):
        confined_path(tmp_path, relative)


def test_artifact_hash_verifies_then_detects_tampering(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
) -> None:
    session = _create_session(store, loaded_bundle)
    run = _create_run(store, loaded_bundle, generated_result, blocked_states)
    assert verify_artifact(session, generated_result.artifact) == run / "synthetic_arrays.npz"
    (run / "synthetic_arrays.npz").write_bytes(b"tampered")
    with pytest.raises(StorageError, match="mismatch"):
        verify_artifact(session, generated_result.artifact)


def test_failed_session_publish_has_no_complete_session(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_bundle(staging: Path, bundle: LoadedBundle) -> None:
        del staging, bundle
        raise OSError("injected write failure")

    monkeypatch.setattr(store, "_write_bundle", fail_bundle)
    with pytest.raises(OSError, match="injected"):
        _create_session(store, loaded_bundle)
    synthetic_root = store.roots.synthetic
    assert not store.session_path(DataOrigin.SYNTHETIC, "s001").exists()
    assert not list(synthetic_root.glob(".session_s001.*"))


def test_failed_run_publish_has_no_complete_run(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
) -> None:
    session = _create_session(store, loaded_bundle)
    bad_artifact = generated_result.artifact.model_copy(update={"sha256": "0" * 64})
    bad_record = run_record(generated_result, blocked_states, loaded_bundle).model_copy(
        update={"artifacts": [bad_artifact]}
    )
    with pytest.raises(StorageError, match="SHA256 mismatch"):
        store.create_synthetic_run(
            bad_record,
            {"synthetic_arrays.npz": generated_result.npz_bytes},
            generated_result.metadata,
        )
    assert not (session / "raw" / "run_run001").exists()
    assert not list((session / "raw").glob(".run_run001.*"))


def test_storage_rejects_incomplete_run_node_state_map(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
) -> None:
    session = _create_session(store, loaded_bundle)
    incomplete = dict(blocked_states)
    incomplete.pop("N1")
    record = run_record(generated_result, blocked_states, loaded_bundle).model_copy(
        update={"node_states": incomplete}
    )
    with pytest.raises(StorageError, match="node-state map is incomplete"):
        store.create_synthetic_run(
            record,
            {"synthetic_arrays.npz": generated_result.npz_bytes},
            generated_result.metadata,
        )
    assert not (session / "raw" / "run_run001").exists()


def test_events_are_create_only_and_sequential(
    store: ImmutableSessionStore, loaded_bundle: LoadedBundle
) -> None:
    session = _create_session(store, loaded_bundle)
    first_event = session / "events" / "000001_session_created.json"
    original = first_event.read_bytes()
    with pytest.raises(StorageError, match="already exists"):
        atomic_write_bytes(first_event, b"replacement")
    new_event = store.append_event(session, "manual_check", {"status": "ok"})
    assert new_event.name == "000003_manual_check.json"
    assert first_event.read_bytes() == original


def test_persisted_records_contain_no_machine_absolute_paths(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
) -> None:
    session = _create_session(store, loaded_bundle)
    run = _create_run(store, loaded_bundle, generated_result, blocked_states)
    for path in (session / "session_record.json", run / "run_record.json"):
        text = path.read_text(encoding="utf-8")
        assert str(session.parent) not in text
        assert ":\\" not in text


def test_synthetic_writer_refuses_real_records_and_real_root_stays_empty(
    store: ImmutableSessionStore, loaded_bundle: LoadedBundle
) -> None:
    real_record = session_record(session_id="real001", origin=DataOrigin.REAL)
    with pytest.raises(StorageError, match="refuses non-synthetic"):
        store.create_synthetic_session(real_record, [reassembly_record("real001")], loaded_bundle)
    assert not store.roots.real.exists()


def test_artifact_reference_rejects_absolute_and_parent_paths() -> None:
    common = {
        "artifact_type": "test",
        "sha256": "0" * 64,
        "byte_size": 0,
        "format": "application/octet-stream",
        "shape": None,
        "dtype": None,
        "created_by": "test",
        "immutable": True,
    }
    for unsafe in ("../artifact.bin", "C:/artifact.bin", "/artifact.bin"):
        with pytest.raises(ValueError):
            ArtifactRef.model_validate_json(json.dumps({"path": unsafe, **common}))
