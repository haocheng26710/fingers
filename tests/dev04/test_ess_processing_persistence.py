from __future__ import annotations

import hashlib
import inspect
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from acoustic_ladder import cli
from acoustic_ladder.audio.ess_processing_models import (
    EssProcessingReceipt,
    ProcessingArrayDescriptor,
    ProcessingRecord,
    PublishedEssProcessing,
)
from acoustic_ladder.audio.ess_processing_persistence import (
    PROCESSING_FILE_NAMES,
    EssProcessingPersistenceError,
    publish_ess_processing,
    validate_ess_processing,
)
from acoustic_ladder.audio.excitation_persistence import publish_offline_ess_artifact
from acoustic_ladder.audio.virtual_capture_models import (
    LoadedVirtualCaptureScenario,
    load_virtual_capture_scenario,
)
from acoustic_ladder.audio.virtual_capture_persistence import (
    PublishedVirtualCapture,
    publish_virtual_capture,
)
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.domain.models import (
    DataOrigin,
    ReassemblyRecord,
    RunMode,
    SessionRecord,
)
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes
from acoustic_ladder.storage.npz import deterministic_npz_bytes, load_deterministic_npz
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore
from tests.dev03.test_virtual_capture import (
    FIXED_TIME,
    PROJECT_ROOT,
    SCENARIO_PATH,
    _capture_setup,
    _development_bundle,
)


def test_deterministic_npz_sorts_names_and_has_fixed_bytes() -> None:
    arrays = {
        "zeta": np.array([1.0, 2.0], dtype=np.float64),
        "alpha": np.array([True, False], dtype=np.bool_),
    }
    first = deterministic_npz_bytes(arrays)
    second = deterministic_npz_bytes(dict(reversed(list(arrays.items()))))
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    loaded = load_deterministic_npz(first)
    assert list(loaded) == ["alpha", "zeta"]
    assert np.array_equal(loaded["zeta"], arrays["zeta"])


def test_deterministic_npz_rejects_object_arrays() -> None:
    with pytest.raises(ValueError, match="object"):
        deterministic_npz_bytes({"unsafe": np.array([object()], dtype=object)})


def test_npz_loader_rejects_noncanonical_archive() -> None:
    buffer = io.BytesIO()
    np.savez(buffer, values=np.ones(2, dtype=np.float64))
    with pytest.raises(ValueError, match="canonical"):
        load_deterministic_npz(buffer.getvalue())


def test_processing_array_descriptor_is_strict_and_hash_bound() -> None:
    descriptor = ProcessingArrayDescriptor(
        name="ir_raw",
        dtype="float64",
        shape=(1, 1, 64),
        raw_sha256="0" * 64,
    )
    assert descriptor.shape == (1, 1, 64)
    with pytest.raises(ValidationError):
        ProcessingArrayDescriptor.model_validate(
            {**descriptor.model_dump(), "shape": [1, -1], "unexpected": True}
        )


CaptureSetup = tuple[
    ImmutableSessionStore,
    LoadedBundle,
    LoadedVirtualCaptureScenario,
    Path,
    Path,
    PublishedVirtualCapture,
]
ProcessingSetup = tuple[
    ImmutableSessionStore,
    LoadedBundle,
    LoadedVirtualCaptureScenario,
    Path,
    Path,
    PublishedVirtualCapture,
    PublishedEssProcessing,
]


def _published_capture(tmp_path: Path) -> CaptureSetup:
    store, bundle, ess_root, real_root = _capture_setup(tmp_path)
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    capture = publish_virtual_capture(
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
    return store, bundle, scenario, ess_root, real_root, capture


def _publish_processing(tmp_path: Path, processing_id: str = "processing-1") -> ProcessingSetup:
    store, bundle, scenario, ess_root, real_root, capture = _published_capture(tmp_path)
    expected = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "processed"
        / "run_capture-1"
        / f"processing_{processing_id}"
    )
    assert not expected.exists()
    processing = publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id=processing_id,
        now=lambda: FIXED_TIME,
    )
    return store, bundle, scenario, ess_root, real_root, capture, processing


def _fixed_identity_processing(tmp_path: Path) -> PublishedEssProcessing:
    store = ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "synthetic", real=tmp_path / "real")
    )
    bundle = _development_bundle()
    session = SessionRecord(
        session_id="dev0401r2",
        session_schema_version="1.0.0",
        created_at=FIXED_TIME,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        operator=None,
        device_manifest_reference="manifest/device_manifest.provisional.json",
        config_bundle_reference="protocol/config_bundle.json",
        reassembly_ids=["assembly001"],
        run_ids=[],
        immutable_status="immutable",
        notes="DEV-04.01R2 deterministic golden",
    )
    reassembly = ReassemblyRecord(
        reassembly_id="assembly001",
        session_id=session.session_id,
        sequence_index=0,
        created_at=FIXED_TIME,
        assembly_description="DEV-04.01R2 deterministic golden",
        operator_confirmation=False,
        related_run_ids=[],
    )
    store.create_synthetic_session(session, [reassembly], bundle)
    ess = publish_offline_ess_artifact(tmp_path / "ess", "source_ess", bundle.configs["audio"])
    scenario = load_virtual_capture_scenario(SCENARIO_PATH, project_root=PROJECT_ROOT)
    publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess.artifact_root,
        session_id="dev0401r2",
        reassembly_id="assembly001",
        run_id="capture001",
        measurement_order=0,
        now=lambda: FIXED_TIME,
    )
    return publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess.artifact_root,
        session_id="dev0401r2",
        source_run_id="capture001",
        processing_id="processing001",
        now=lambda: FIXED_TIME,
    )


def test_processing_publisher_api_has_no_truth_waveform_or_real_root_parameters() -> None:
    parameters = inspect.signature(publish_ess_processing).parameters
    assert set(parameters) == {
        "store",
        "bundle",
        "scenario",
        "ess_artifact_root",
        "session_id",
        "source_run_id",
        "processing_id",
        "now",
    }
    assert not {
        "expected_latency",
        "expected_gain",
        "integer_latency_samples",
        "linear_gain",
        "output_samples",
        "input_samples",
        "real_root",
    }.intersection(parameters)


def test_processing_publication_creates_exact_completed_file_set(tmp_path: Path) -> None:
    *_, processing = _publish_processing(tmp_path)
    assert {entry.name for entry in processing.processing_path.iterdir()} == (PROCESSING_FILE_NAMES)
    assert (processing.processing_path / "PROCESSING_COMPLETE").read_bytes() == b"complete\n"


def test_processing_publication_appends_hash_bound_audit_event(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    event_paths = _processing_event_files(store)
    assert len(event_paths) == 1
    event = json.loads(event_paths[0].read_bytes())
    record_path = processing.processing_path / "processing_record.json"
    record = json.loads(record_path.read_bytes())
    assert event["event"] == "processing_created"
    assert event["data_origin"] == "synthetic"
    assert event["session_id"] == "capture-session"
    assert event["processing_id"] == "processing-1"
    assert event["source_run_id"] == "capture-1"
    assert event["created_at"] == record["created_at"]
    assert event["processing_record_sha256"] == hashlib.sha256(record_path.read_bytes()).hexdigest()
    assert event["processing_receipt_sha256"] == processing.receipt_sha256
    validate_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-1",
    )


def test_processing_event_append_failure_reports_published_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, bundle, scenario, ess_root, _, _ = _published_capture(tmp_path)

    def fail_event(
        origin: DataOrigin,
        session_id: str,
        event: str,
        payload: dict[str, object],
    ) -> Path:
        raise StorageError("injected processing event failure")

    monkeypatch.setattr(store, "append_event", fail_event)
    with pytest.raises(
        EssProcessingPersistenceError, match="injected processing event failure; published=true"
    ):
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="event-failure",
            now=lambda: FIXED_TIME,
        )
    target = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "processed"
        / "run_capture-1"
        / "processing_event-failure"
    )
    assert target.is_dir()
    assert {path.name for path in target.iterdir()} == PROCESSING_FILE_NAMES
    assert not _processing_event_files(store)


def test_two_processing_events_are_distinguished_by_identity(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, first = _publish_processing(tmp_path)
    second = publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-2",
        now=lambda: FIXED_TIME,
    )
    assert len(_processing_event_files(store)) == 2
    for processing_id, published in (("processing-1", first), ("processing-2", second)):
        validated = validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id=processing_id,
        )
        assert validated.processing_path == published.processing_path


def test_dev0401r2_same_processing_id_on_two_source_runs_uses_composite_event_identity(
    tmp_path: Path,
) -> None:
    store, bundle, scenario, ess_root, _, first_capture = _published_capture(tmp_path)
    second_capture = publish_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        reassembly_id="assembly-1",
        run_id="capture-2",
        measurement_order=1,
        now=lambda: FIXED_TIME + timedelta(seconds=1),
    )
    first = publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-1",
        now=lambda: FIXED_TIME,
    )
    second = publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-2",
        processing_id="processing-1",
        now=lambda: FIXED_TIME + timedelta(seconds=1),
    )

    assert first_capture.receipt.measurement_order == 0
    assert second_capture.receipt.measurement_order == 1
    assert first.processing_path != second.processing_path
    assert first.processing_path.is_dir()
    assert second.processing_path.is_dir()
    events = [json.loads(path.read_bytes()) for path in _processing_event_files(store)]
    assert {(event["source_run_id"], event["processing_id"]) for event in events} == {
        ("capture-1", "processing-1"),
        ("capture-2", "processing-1"),
    }
    for source_run_id, published in (("capture-1", first), ("capture-2", second)):
        event = next(event for event in events if event["source_run_id"] == source_run_id)
        record_path = published.processing_path / "processing_record.json"
        record = json.loads(record_path.read_bytes())
        assert event["created_at"] == record["created_at"]
        assert (
            event["processing_record_sha256"]
            == hashlib.sha256(record_path.read_bytes()).hexdigest()
        )
        assert event["processing_receipt_sha256"] == published.receipt_sha256

    failures: list[str] = []
    for source_run_id, published in (("capture-1", first), ("capture-2", second)):
        try:
            validated = validate_ess_processing(
                store=store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess_root,
                session_id="capture-session",
                source_run_id=source_run_id,
                processing_id="processing-1",
            )
            assert validated.processing_path == published.processing_path
        except EssProcessingPersistenceError as exc:
            failures.append(f"{source_run_id}: {exc}")
    assert failures == []


def test_nominal_publication_recovers_waveform_latency_and_gain(tmp_path: Path) -> None:
    *_, processing = _publish_processing(tmp_path)
    arrays = load_deterministic_npz(
        (processing.processing_path / "processing_arrays.npz").read_bytes()
    )
    assert processing.receipt.estimated_latency_samples == 37
    assert processing.receipt.ir_dominant_peak_index == 37
    assert arrays["ir_raw"][0, 0, 37] == pytest.approx(0.5, abs=1e-6)
    assert arrays["ir_aligned"][0, 0, 0] == pytest.approx(0.5, abs=1e-6)


def test_processing_validator_replays_semantics_read_only(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, published = _publish_processing(tmp_path)
    before = {path.name: path.read_bytes() for path in published.processing_path.iterdir()}
    validated = validate_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-1",
    )
    assert validated.receipt == published.receipt
    assert {path.name: path.read_bytes() for path in published.processing_path.iterdir()} == before


def test_processing_publication_never_creates_real_root(tmp_path: Path) -> None:
    *_, real_root, _, _ = _publish_processing(tmp_path)
    assert not real_root.exists()


def test_processing_publication_is_create_only_and_preserves_bytes(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, first = _publish_processing(tmp_path)
    before = {path.name: path.read_bytes() for path in first.processing_path.iterdir()}
    with pytest.raises(EssProcessingPersistenceError, match="published=true"):
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            now=lambda: FIXED_TIME,
        )
    assert {path.name: path.read_bytes() for path in first.processing_path.iterdir()} == before


@pytest.mark.parametrize("processing_id", ["", ".", "..", "../escape", "a/b", "a\\b"])
def test_unsafe_processing_id_is_rejected_without_target(
    tmp_path: Path, processing_id: str
) -> None:
    store, bundle, scenario, ess_root, _, _ = _published_capture(tmp_path)
    with pytest.raises(EssProcessingPersistenceError):
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id=processing_id,
            now=lambda: FIXED_TIME,
        )
    processed = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "processed"
    assert not list(processed.rglob("processing_*"))


def test_processing_receipt_contains_no_scenario_truth_fields(tmp_path: Path) -> None:
    *_, processing = _publish_processing(tmp_path)
    receipt = json.loads((processing.processing_path / "processing_receipt.json").read_bytes())
    assert "integer_latency_samples" not in receipt
    assert "linear_gain" not in receipt
    assert "expected_latency" not in receipt
    assert "expected_gain" not in receipt


def test_processing_receipt_closes_source_timing_latency_and_safety_audit(
    tmp_path: Path,
) -> None:
    *_, capture, processing = _publish_processing(tmp_path)
    receipt = processing.receipt
    assert receipt.source_output_wav_sha256 == capture.receipt.output_wav_sha256
    assert receipt.source_input_wav_sha256 == capture.receipt.input_wav_sha256
    assert receipt.source_output_raw_float32_sha256 == (capture.receipt.output_raw_float32_sha256)
    assert receipt.source_input_raw_float32_sha256 == (capture.receipt.input_raw_float32_sha256)
    assert receipt.candidate_lag_min == 0
    assert receipt.candidate_lag_max == 544
    assert receipt.lag_convention == "positive_input_lags_output"
    assert receipt.deconvolution_time_origin == ("reference_deconvolution_unique_absolute_peak")
    assert receipt.ir_raw_definition == "input_deconvolution_from_reference_peak"
    assert receipt.phase_unwrap_axis == "frequency_last_axis"
    assert receipt.matched_correlation_absolute == pytest.approx(1.0)
    assert receipt.estimated_latency_seconds == pytest.approx(37 / 48000)
    assert receipt.deconvolution_fft_length == 32768
    assert receipt.hardware_ready is False
    assert receipt.full_duplex_verified is False
    assert receipt.shared_clock_verified is False
    assert receipt.channel_mapping_verified is False
    assert receipt.calibration_file_verified is False
    assert receipt.calibration_applied is False
    assert receipt.absolute_spl_calibrated is False
    assert receipt.electrical_loopback_available is False


def test_dev0401r2_processing_receipt_versions_and_transfer_semantics_are_explicit(
    tmp_path: Path,
) -> None:
    *_, processing = _publish_processing(tmp_path)
    receipt = processing.receipt.model_dump(mode="json")
    assert receipt["schema_version"] == "1.1.0"
    assert receipt["algorithm_version"] == "1.1.0"
    assert receipt["transfer_estimator_id"] == "complex_spectral_ratio"
    assert receipt["transfer_raw_definition"] == ("rfft(input_after_pre)/rfft(output_after_pre)")
    assert receipt["transfer_aligned_definition"] == (
        "rfft(zero_fill_advance(input_after_pre,estimated_latency_samples))/rfft(output_after_pre)"
    )
    assert receipt["spectral_division_threshold_formula"] == (
        "max_abs_reference_spectrum*float64_epsilon*reference_sample_count"
    )
    assert receipt["spectral_division_below_threshold_policy"] == (
        "zero_where_reference_at_or_below_threshold"
    )


def test_dev0401r2_processing_receipt_requires_every_transfer_provenance_field(
    tmp_path: Path,
) -> None:
    *_, processing = _publish_processing(tmp_path)
    payload = processing.receipt.model_dump(mode="python")
    fields = {
        "transfer_estimator_id",
        "transfer_raw_definition",
        "transfer_aligned_definition",
        "spectral_division_threshold_formula",
        "spectral_division_below_threshold_policy",
    }
    for field in fields:
        incomplete = dict(payload)
        del incomplete[field]
        with pytest.raises(ValidationError):
            EssProcessingReceipt.model_validate(incomplete)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "1.0.0"),
        ("algorithm_version", "1.0.0"),
        ("transfer_estimator_id", "spectral_ratio"),
        ("transfer_raw_definition", "rfft(output_after_pre)/rfft(input_after_pre)"),
        ("transfer_aligned_definition", "circular_shift_then_ratio"),
        ("spectral_division_threshold_formula", "absolute_epsilon"),
        ("spectral_division_below_threshold_policy", "nan_below_threshold"),
    ],
)
def test_dev0401r2_processing_receipt_rejects_old_versions_and_wrong_transfer_literals(
    tmp_path: Path, field: str, value: str
) -> None:
    *_, processing = _publish_processing(tmp_path)
    payload = processing.receipt.model_dump(mode="python")
    payload[field] = value
    with pytest.raises(ValidationError):
        EssProcessingReceipt.model_validate(payload)


def test_dev0401r2_processing_receipt_rejects_extra_fields(tmp_path: Path) -> None:
    *_, processing = _publish_processing(tmp_path)
    payload = processing.receipt.model_dump(mode="python")
    payload["transfer_implementation_note"] = "unversioned"
    with pytest.raises(ValidationError):
        EssProcessingReceipt.model_validate(payload)


def test_dev0401r2_validator_rejects_old_algorithm_receipt_with_recomputed_sidecar_read_only(
    tmp_path: Path,
) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    receipt_path = processing.processing_path / "processing_receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["schema_version"] = "1.0.0"
    receipt["algorithm_version"] = "1.0.0"
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    _rewrite_sidecar(receipt_path, processing.processing_path / "processing_receipt.sha256")
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked


def _rewrite_sidecar(path: Path, sidecar: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="ascii", newline="\n")


def _processing_event_files(store: ImmutableSessionStore) -> list[Path]:
    session = store.session_path(DataOrigin.SYNTHETIC, "capture-session")
    return sorted((session / "events").glob("*_processing_created.json"))


def _ensure_processing_event(
    store: ImmutableSessionStore, processing: PublishedEssProcessing
) -> Path:
    existing = _processing_event_files(store)
    if existing:
        assert len(existing) == 1
        return existing[0]
    record_path = processing.processing_path / "processing_record.json"
    record = json.loads(record_path.read_bytes())
    return store.append_event(
        DataOrigin.SYNTHETIC,
        "capture-session",
        "processing_created",
        {
            "schema_version": "1.0.0",
            "processing_id": "processing-1",
            "source_run_id": "capture-1",
            "created_at": record["created_at"],
            "processing_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
            "processing_receipt_sha256": processing.receipt_sha256,
        },
    )


def _session_file_bytes(store: ImmutableSessionStore) -> dict[str, bytes]:
    session = store.session_path(DataOrigin.SYNTHETIC, "capture-session")
    return {
        path.relative_to(session).as_posix(): path.read_bytes()
        for path in session.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    ("sidecar_name", "mutation"),
    [
        ("processing_arrays.npz.sha256", "extra-newline"),
        ("processing_receipt.sha256", "trailing-whitespace"),
        ("processing_arrays.npz.sha256", "crlf"),
        ("processing_arrays.npz.sha256", "duplicate-record"),
        ("processing_arrays.npz.sha256", "wrong-filename"),
        ("processing_arrays.npz.sha256", "non-ascii"),
        ("processing_arrays.npz.sha256", "missing"),
        ("processing_arrays.npz.sha256", "directory"),
    ],
)
def test_validator_rejects_noncanonical_sidecar_bytes_read_only(
    tmp_path: Path, sidecar_name: str, mutation: str
) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    path = processing.processing_path / sidecar_name
    original = path.read_bytes()
    if mutation == "extra-newline":
        path.write_bytes(original + b"\n")
    elif mutation == "trailing-whitespace":
        path.write_bytes(original[:-1] + b"  \n")
    elif mutation == "crlf":
        path.write_bytes(original.replace(b"\n", b"\r\n"))
    elif mutation == "duplicate-record":
        path.write_bytes(original + original)
    elif mutation == "wrong-filename":
        path.write_bytes(original.replace(b"processing_arrays.npz", b"wrong.bin"))
    elif mutation == "non-ascii":
        path.write_bytes(original[:-1] + "é\n".encode())
    elif mutation == "missing":
        path.unlink()
    else:
        path.unlink()
        path.mkdir()
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked
    if mutation == "directory":
        assert path.is_dir()
    elif mutation == "missing":
        assert not path.exists()


@pytest.mark.parametrize("marker", [b"done\n", b"complete"])
def test_validator_rejects_noncanonical_completion_marker_read_only(
    tmp_path: Path, marker: bytes
) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    (processing.processing_path / "PROCESSING_COMPLETE").write_bytes(marker)
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked


def test_validator_rejects_completion_marker_directory_read_only(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    marker = processing.processing_path / "PROCESSING_COMPLETE"
    marker.unlink()
    marker.mkdir()
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert marker.is_dir()
    assert _session_file_bytes(store) == attacked


def test_validator_rejects_canonical_record_created_at_tamper_read_only(
    tmp_path: Path,
) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    record_path = processing.processing_path / "processing_record.json"
    record = json.loads(record_path.read_bytes())
    record["created_at"] = "2031-02-03T04:05:07+00:00"
    tampered_record = ProcessingRecord.model_validate_json(canonical_json_bytes(record))
    record_path.write_bytes(canonical_json_bytes(tampered_record.model_dump(mode="json")))
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked


def test_validator_rejects_missing_processing_audit_event_read_only(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    _ensure_processing_event(store, processing).unlink()
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("processing_record_sha256", "0" * 64),
        ("processing_receipt_sha256", "0" * 64),
        ("created_at", "2031-02-03T04:05:07+00:00"),
        ("processing_id", "other-processing"),
        ("source_run_id", "other-run"),
        ("session_id", "other-session"),
        ("data_origin", "real"),
    ],
)
def test_validator_rejects_processing_audit_event_tamper_read_only(
    tmp_path: Path, field: str, value: str
) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    event_path = _ensure_processing_event(store, processing)
    event = json.loads(event_path.read_bytes())
    event[field] = value
    event_path.write_bytes(canonical_json_bytes(event))
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked


def test_validator_rejects_duplicate_processing_audit_event_read_only(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    event_path = _ensure_processing_event(store, processing)
    event = json.loads(event_path.read_bytes())
    store.append_event(
        DataOrigin.SYNTHETIC,
        "capture-session",
        "processing_created",
        {
            key: value
            for key, value in event.items()
            if key not in {"event", "sequence", "session_id", "data_origin"}
        },
    )
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked


@pytest.mark.parametrize("mutation", ["extra", "noncanonical", "filename-sequence"])
def test_validator_rejects_malformed_processing_audit_envelope_read_only(
    tmp_path: Path, mutation: str
) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    event_path = _ensure_processing_event(store, processing)
    if mutation == "filename-sequence":
        event_path = event_path.rename(event_path.with_name("999999_processing_created.json"))
    else:
        event = json.loads(event_path.read_bytes())
        if mutation == "extra":
            event["unexpected"] = True
            event_path.write_bytes(canonical_json_bytes(event))
        else:
            event_path.write_bytes(event_path.read_bytes() + b"\n")
    attacked = _session_file_bytes(store)
    with pytest.raises(EssProcessingPersistenceError):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert _session_file_bytes(store) == attacked


def test_receipt_descriptors_cover_and_hash_every_npz_array(tmp_path: Path) -> None:
    *_, processing = _publish_processing(tmp_path)
    arrays = load_deterministic_npz(
        (processing.processing_path / "processing_arrays.npz").read_bytes()
    )
    assert set(processing.receipt.array_descriptors) == set(arrays)
    assert len(arrays) == 21
    for name, array in arrays.items():
        descriptor = processing.receipt.array_descriptors[name]
        assert descriptor.shape == array.shape
        assert descriptor.dtype == str(array.dtype)
        assert descriptor.raw_sha256 == hashlib.sha256(array.tobytes(order="C")).hexdigest()


def test_processing_payloads_are_byte_deterministic_across_roots(tmp_path: Path) -> None:
    first = _publish_processing(tmp_path / "first")[-1]
    second = _publish_processing(tmp_path / "second")[-1]
    for name in {
        "processing_arrays.npz",
        "processing_arrays.npz.sha256",
        "processing_receipt.json",
        "processing_receipt.sha256",
        "processing_metadata.json",
    }:
        assert (first.processing_path / name).read_bytes() == (
            second.processing_path / name
        ).read_bytes()


def test_dev0401r2_fixed_identity_processing_golden_hashes(tmp_path: Path) -> None:
    processing = _fixed_identity_processing(tmp_path)
    expected = {
        "processing_arrays.npz": (
            "e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89"
        ),
        "processing_arrays.npz.sha256": (
            "f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902"
        ),
        "processing_receipt.json": (
            "25616c6e2d42413243eb8e14cd099d01e69e736c29ffcce5cdd413e97841ad5f"
        ),
        "processing_receipt.sha256": (
            "38ef680d07fbc88ca7f2d59bba10866439fe2db80b95b34bcea7eec202830e63"
        ),
        "processing_metadata.json": (
            "daa1c08780c9381604f08be14a268bcb7a539844622096de588c5c020c2a04cb"
        ),
    }
    assert {
        name: hashlib.sha256((processing.processing_path / name).read_bytes()).hexdigest()
        for name in expected
    } == expected


@pytest.mark.parametrize("tamper", ["arrays", "receipt", "metadata", "record", "extra"])
def test_validator_rejects_processing_tamper_read_only(tmp_path: Path, tamper: str) -> None:
    store, bundle, scenario, ess_root, _, _, processing = _publish_processing(tmp_path)
    root = processing.processing_path
    if tamper == "arrays":
        path = root / "processing_arrays.npz"
        payload = bytearray(path.read_bytes())
        payload[-1] ^= 1
        path.write_bytes(payload)
        _rewrite_sidecar(path, root / "processing_arrays.npz.sha256")
    elif tamper == "receipt":
        path = root / "processing_receipt.json"
        value = json.loads(path.read_bytes())
        value["estimated_latency_samples"] += 1
        path.write_bytes(
            (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        )
        _rewrite_sidecar(path, root / "processing_receipt.sha256")
    elif tamper == "metadata":
        path = root / "processing_metadata.json"
        value = json.loads(path.read_bytes())
        value["hardware_io_performed"] = True
        path.write_bytes(
            (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        )
    elif tamper == "record":
        path = root / "processing_record.json"
        value = json.loads(path.read_bytes())
        value["result_marker"] = "tampered"
        path.write_bytes(
            (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        )
    else:
        path = root / "extra.bin"
        path.write_bytes(b"extra")
    tampered = path.read_bytes()
    with pytest.raises((EssProcessingPersistenceError, ValidationError, ValueError)):
        validate_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
        )
    assert path.read_bytes() == tampered


def test_processing_cli_complete_workflow_has_required_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store, _, _, ess_root, _, _ = _published_capture(tmp_path)
    synthetic_root = store.roots.synthetic
    bundle_args = [
        "--project-root",
        str(PROJECT_ROOT),
        "--audio",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "--protocol",
        "config/protocols/stage4_four_node_states.yaml",
        "--synthetic-root",
        str(synthetic_root),
        "--session-id",
        "capture-session",
        "--source-run-id",
        "capture-1",
        "--processing-id",
        "cli-processing",
        "--scenario",
        "tests/fixtures/audio/virtual_duplex_development.yaml",
        "--ess-artifact-root",
        str(ess_root),
    ]
    cli.main(["process-simulated-capture", *bundle_args])
    generated = capsys.readouterr().out
    cli.main(["validate-simulated-processing", *bundle_args])
    validated = capsys.readouterr().out
    for output in (generated, validated):
        assert "SYNTHETIC_ONLY" in output
        assert "OFFLINE_PROCESSING_ONLY" in output
        assert "NO_HARDWARE_AUDIO_IO_PERFORMED" in output
        assert "NOT_AN_EXPERIMENTAL_RESULT" in output
        assert "latency_samples=37" in output
        assert "ir_peak_index=37" in output


@pytest.mark.parametrize(
    "forbidden", ["--real-root", "--expected-latency", "--expected-gain", "--device"]
)
def test_processing_cli_rejects_forbidden_authority_options(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "process-simulated-capture",
                "--protocol",
                "config/protocols/stage4_four_node_states.yaml",
                "--synthetic-root",
                "synthetic",
                "--session-id",
                "session",
                "--source-run-id",
                "capture",
                "--processing-id",
                "processing",
                "--scenario",
                "scenario.yaml",
                "--ess-artifact-root",
                "ess",
                forbidden,
                "1",
            ]
        )


def test_concurrent_processing_publication_has_at_most_one_success(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _ = _published_capture(tmp_path)

    def publish() -> object:
        return publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="concurrent",
            now=lambda: FIXED_TIME,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(publish) for _ in range(2)]
    successes = [future.result() for future in futures if future.exception() is None]
    failures = [future.exception() for future in futures if future.exception() is not None]
    assert len(successes) == 1
    assert len(failures) == 1
    root = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "processed"
    assert len(list(root.rglob("PROCESSING_COMPLETE"))) == 1
    assert not list(root.rglob("*.publish.lock"))
    assert not list(root.rglob("*.staging-*"))


def test_processing_staging_failure_cleans_owned_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, bundle, scenario, ess_root, _, _ = _published_capture(tmp_path)

    def fail_receipt(path: str | Path, payload: bytes) -> None:
        if Path(path).name == "processing_receipt.json":
            raise OSError("injected processing staging failure")
        atomic_write_bytes(path, payload)

    monkeypatch.setattr("acoustic_ladder.storage.store.atomic_write_bytes", fail_receipt)
    with pytest.raises(EssProcessingPersistenceError, match="published=false"):
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="failure",
            now=lambda: FIXED_TIME,
        )
    root = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "processed"
    assert not list(root.rglob("processing_failure"))
    assert not list(root.rglob("*.publish.lock"))
    assert not list(root.rglob("*.staging-*"))


def test_missing_source_run_completion_is_rejected_without_processing(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, capture = _published_capture(tmp_path)
    (capture.run_path / "RUN_COMPLETE").unlink()
    with pytest.raises(StorageError, match="missing or incomplete"):
        publish_ess_processing(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="must-not-publish",
            now=lambda: FIXED_TIME,
        )
    processed = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "processed"
    assert not list(processed.rglob("processing_must-not-publish"))
