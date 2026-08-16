from __future__ import annotations

import json
from pathlib import Path

import pytest

import acoustic_ladder.storage.store as store_module
from acoustic_ladder.config.bundle import LoadedBundle
from acoustic_ladder.domain.models import DataOrigin, NodeState
from acoustic_ladder.storage.io import StorageError, atomic_write_json
from acoustic_ladder.storage.store import ImmutableSessionStore
from acoustic_ladder.synthetic.generator import SyntheticResult
from tests.dev02.conftest import reassembly_record, run_record, session_record


def _create_session(
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    origin: DataOrigin = DataOrigin.SYNTHETIC,
    session_id: str = "s001",
) -> Path:
    record = session_record(session_id, origin)
    reassembly = reassembly_record(session_id)
    if origin is DataOrigin.SYNTHETIC:
        return store.create_synthetic_session(record, [reassembly], bundle)
    return store.create_session(record, [reassembly], bundle)


@pytest.mark.parametrize("origin", [DataOrigin.SYNTHETIC, DataOrigin.REAL])
def test_external_absolute_session_identifier_is_rejected_without_residue(
    store: ImmutableSessionStore, tmp_path: Path, origin: DataOrigin
) -> None:
    outside = tmp_path / "outside"
    with pytest.raises(StorageError):
        store.append_event(origin, str(outside.resolve()), "boundary_probe", {})
    assert not outside.exists()
    assert not (outside / "events").exists()
    assert not (outside / "events" / "000001_boundary_probe.json").exists()


def test_events_are_confined_to_the_selected_origin_root(
    store: ImmutableSessionStore, loaded_bundle: LoadedBundle
) -> None:
    synthetic = _create_session(store, loaded_bundle, DataOrigin.SYNTHETIC, "shared")
    real = _create_session(store, loaded_bundle, DataOrigin.REAL, "shared")

    synthetic_event = store.append_event(
        DataOrigin.SYNTHETIC, "shared", "synthetic_probe", {"value": 1}
    )
    real_event = store.append_event(DataOrigin.REAL, "shared", "real_probe", {"value": 2})

    assert synthetic_event.parent == synthetic / "events"
    assert real_event.parent == real / "events"
    assert synthetic_event.is_file()
    assert real_event.is_file()
    assert not (real / "events" / synthetic_event.name).exists()
    assert not (synthetic / "events" / real_event.name).exists()


def test_incomplete_session_cannot_receive_an_event(
    store: ImmutableSessionStore, loaded_bundle: LoadedBundle
) -> None:
    session = _create_session(store, loaded_bundle)
    (session / "SESSION_COMPLETE").unlink()
    before = sorted(path.name for path in (session / "events").iterdir())
    with pytest.raises(StorageError, match="missing or incomplete"):
        store.append_event(DataOrigin.SYNTHETIC, "s001", "forbidden", {})
    assert sorted(path.name for path in (session / "events").iterdir()) == before


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("data_origin", DataOrigin.REAL.value, "origin"),
        ("session_id", "different", "session_id"),
    ],
)
def test_session_record_identity_mismatch_is_rejected(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    field: str,
    value: str,
    message: str,
) -> None:
    session = _create_session(store, loaded_bundle)
    record_path = session / "session_record.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload[field] = value
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    before = sorted(path.name for path in (session / "events").iterdir())
    with pytest.raises(StorageError, match=message):
        store.append_event(DataOrigin.SYNTHETIC, "s001", "forbidden", {})
    assert sorted(path.name for path in (session / "events").iterdir()) == before


@pytest.mark.parametrize(
    "event",
    [
        "",
        ".",
        "..",
        "../escape",
        "a/b",
        "a\\b",
        "name:part",
        "/absolute",
        "C:\\event",
        "évent",
    ],
)
def test_unsafe_event_names_are_rejected_without_new_files(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    event: str,
) -> None:
    session = _create_session(store, loaded_bundle)
    before = {path.name: path.read_bytes() for path in (session / "events").iterdir()}
    with pytest.raises(StorageError, match="event"):
        store.append_event(DataOrigin.SYNTHETIC, "s001", event, {})
    after = {path.name: path.read_bytes() for path in (session / "events").iterdir()}
    assert after == before


@pytest.mark.parametrize("reserved", ["event", "sequence", "session_id", "data_origin"])
def test_payload_cannot_override_reserved_event_fields(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    reserved: str,
) -> None:
    session = _create_session(store, loaded_bundle)
    before = {path.name: path.read_bytes() for path in (session / "events").iterdir()}
    with pytest.raises(StorageError, match="reserved"):
        store.append_event(
            DataOrigin.SYNTHETIC,
            "s001",
            "payload_probe",
            {reserved: "attacker-controlled"},
        )
    after = {path.name: path.read_bytes() for path in (session / "events").iterdir()}
    assert after == before


def test_legal_events_are_sequential_and_existing_bytes_do_not_change(
    store: ImmutableSessionStore, loaded_bundle: LoadedBundle
) -> None:
    session = _create_session(store, loaded_bundle)
    first_event = session / "events" / "000001_session_created.json"
    first_bytes = first_event.read_bytes()

    third = store.append_event(DataOrigin.SYNTHETIC, "s001", "manual-one", {"value": 1})
    fourth = store.append_event(DataOrigin.SYNTHETIC, "s001", "manual_two", {"value": 2})

    assert third.name == "000003_manual-one.json"
    assert fourth.name == "000004_manual_two.json"
    assert first_event.read_bytes() == first_bytes
    assert json.loads(third.read_text(encoding="utf-8")) == {
        "data_origin": "synthetic",
        "event": "manual-one",
        "sequence": 3,
        "session_id": "s001",
        "value": 1,
    }


def test_numbering_collision_never_overwrites_competing_event(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _create_session(store, loaded_bundle)
    original_writer = atomic_write_json
    competitor_payload = {"event": "competitor", "sequence": 3}

    def inject_collision(path: str | Path, value: object) -> None:
        target = Path(path)
        if target.name == "000003_race_probe.json" and not target.exists():
            original_writer(target, competitor_payload)
        original_writer(target, value)

    monkeypatch.setattr(store_module, "atomic_write_json", inject_collision)
    with pytest.raises(StorageError, match="already exists"):
        store.append_event(DataOrigin.SYNTHETIC, "s001", "race_probe", {})

    collision = session / "events" / "000003_race_probe.json"
    assert json.loads(collision.read_text(encoding="utf-8")) == competitor_payload
    assert not list((session / "events").glob("*.tmp"))


def test_create_run_uses_confined_event_api(
    store: ImmutableSessionStore,
    loaded_bundle: LoadedBundle,
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
) -> None:
    session = _create_session(store, loaded_bundle)
    record = run_record(generated_result, blocked_states, loaded_bundle)
    store.create_synthetic_run(
        record,
        {"synthetic_arrays.npz": generated_result.npz_bytes},
        generated_result.metadata,
    )

    event_path = session / "events" / "000003_run_created.json"
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    assert payload["event"] == "run_created"
    assert payload["sequence"] == 3
    assert payload["session_id"] == "s001"
    assert payload["data_origin"] == "synthetic"
    assert payload["run_id"] == "run001"
