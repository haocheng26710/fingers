from __future__ import annotations

import hashlib
import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from acoustic_ladder import cli
from acoustic_ladder.audio.ess_processing_models import PublishedEssProcessing
from acoustic_ladder.audio.ess_processing_persistence import publish_ess_processing
from acoustic_ladder.audio.provisional_qc_models import (
    ProvisionalQcReceipt,
    PublishedProvisionalQc,
)
from acoustic_ladder.audio.provisional_qc_persistence import (
    QC_COMPLETE_BYTES,
    QC_FILE_NAMES,
    ProvisionalQcPersistenceError,
    publish_provisional_qc,
    validate_provisional_qc,
)
from acoustic_ladder.audio.virtual_capture_models import LoadedVirtualCaptureScenario
from acoustic_ladder.audio.virtual_capture_persistence import publish_virtual_capture
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.config.schema import ALL_GENERATED_SCHEMA_MODELS, check_schemas
from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes
from acoustic_ladder.storage.store import ImmutableSessionStore
from tests.dev03.test_virtual_capture import FIXED_TIME, PROJECT_ROOT
from tests.dev04.test_ess_processing_persistence import (
    _fixed_identity_processing,
    _publish_processing,
)

QcSetup = tuple[
    ImmutableSessionStore,
    LoadedBundle,
    LoadedVirtualCaptureScenario,
    Path,
    Path,
    PublishedEssProcessing,
    PublishedProvisionalQc,
]


def _publish_qc(tmp_path: Path, qc_id: str = "qc-1") -> QcSetup:
    store, bundle, scenario, ess_root, real_root, _, processing = _publish_processing(tmp_path)
    qc = publish_provisional_qc(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-1",
        qc_id=qc_id,
        now=lambda: FIXED_TIME,
    )
    return store, bundle, scenario, ess_root, real_root, processing, qc


def test_qc_publisher_api_cannot_accept_arrays_truth_thresholds_or_real_paths() -> None:
    parameters = set(inspect.signature(publish_provisional_qc).parameters)
    assert parameters == {
        "store",
        "bundle",
        "scenario",
        "ess_artifact_root",
        "session_id",
        "source_run_id",
        "processing_id",
        "qc_id",
        "now",
    }
    assert not {
        "waveforms",
        "processing_arrays",
        "metrics",
        "expected_latency",
        "expected_gain",
        "threshold",
        "decision",
        "real_root",
    }.intersection(parameters)


def test_qc_publication_creates_exact_seven_file_envelope(tmp_path: Path) -> None:
    *_, qc = _publish_qc(tmp_path)
    assert {entry.name for entry in qc.qc_path.iterdir()} == QC_FILE_NAMES
    assert (qc.qc_path / "QC_COMPLETE").read_bytes() == QC_COMPLETE_BYTES
    assert qc.receipt.metric_computation_status == "complete"
    assert qc.receipt.evaluation_status == "provisional_metrics_only"
    assert qc.receipt.decision_status == "not_evaluated"
    assert qc.receipt.thresholds_applied is False
    assert qc.receipt.qc_threshold is None
    assert qc.receipt.threshold_source is None
    assert qc.receipt.formal_eligible is False
    assert qc.receipt.experimental_result is False
    assert qc.receipt.hardware_ready is False


def test_qc_publication_is_synthetic_confined_and_processing_bound(tmp_path: Path) -> None:
    store, _, _, _, real_root, processing, qc = _publish_qc(tmp_path)
    expected = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "qc"
        / "run_capture-1"
        / "processing_processing-1"
        / "qc_qc-1"
    )
    assert qc.qc_path == expected
    assert qc.receipt.source_processing_receipt_sha256 == processing.receipt_sha256
    assert qc.receipt.source_processing_arrays_sha256 == processing.arrays_sha256
    assert not real_root.exists()


def test_qc_publication_appends_canonical_hash_bound_event(tmp_path: Path) -> None:
    store, _, _, _, _, _, qc = _publish_qc(tmp_path)
    events = sorted(
        (store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "events").glob(
            "*_qc_created.json"
        )
    )
    assert len(events) == 1
    raw = events[0].read_bytes()
    event = json.loads(raw)
    assert raw == canonical_json_bytes(event)
    assert event["source_run_id"] == "capture-1"
    assert event["processing_id"] == "processing-1"
    assert event["qc_id"] == "qc-1"
    assert (
        event["qc_record_sha256"]
        == hashlib.sha256((qc.qc_path / "qc_record.json").read_bytes()).hexdigest()
    )
    assert event["qc_metrics_sha256"] == qc.metrics_sha256
    assert event["qc_receipt_sha256"] == qc.receipt_sha256


def test_qc_validator_replays_exact_metrics_read_only(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, published = _publish_qc(tmp_path)
    before = {
        path.relative_to(published.qc_path).as_posix(): path.read_bytes()
        for path in published.qc_path.iterdir()
    }
    validated = validate_provisional_qc(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-1",
        qc_id="qc-1",
    )
    after = {
        path.relative_to(published.qc_path).as_posix(): path.read_bytes()
        for path in published.qc_path.iterdir()
    }
    assert validated.metrics == published.metrics
    assert validated.receipt == published.receipt
    assert before == after


def test_duplicate_qc_composite_identity_is_create_only(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, qc = _publish_qc(tmp_path)
    before = {path.name: path.read_bytes() for path in qc.qc_path.iterdir()}
    with pytest.raises(ProvisionalQcPersistenceError, match="already exists"):
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="qc-1",
            now=lambda: FIXED_TIME,
        )
    assert {path.name: path.read_bytes() for path in qc.qc_path.iterdir()} == before


def test_qc_event_failure_reports_published_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, bundle, scenario, ess_root, _, _, _ = _publish_processing(tmp_path)

    def fail_event(
        origin: DataOrigin,
        session_id: str,
        event: str,
        payload: dict[str, object],
    ) -> Path:
        raise StorageError("injected QC event failure")

    monkeypatch.setattr(store, "append_event", fail_event)
    with pytest.raises(
        ProvisionalQcPersistenceError, match="injected QC event failure; published=true"
    ):
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="event-failure",
            now=lambda: FIXED_TIME,
        )
    target = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "qc"
        / "run_capture-1"
        / "processing_processing-1"
        / "qc_event-failure"
    )
    assert target.is_dir()
    assert {path.name for path in target.iterdir()} == QC_FILE_NAMES


def test_qc_receipt_is_strict_and_rejects_wrong_provisional_states(tmp_path: Path) -> None:
    *_, qc = _publish_qc(tmp_path)
    payload = qc.receipt.model_dump()
    payload["thresholds_applied"] = True
    payload["unexpected"] = "forbidden"
    with pytest.raises(ValidationError):
        ProvisionalQcReceipt.model_validate(payload)


@pytest.mark.parametrize("qc_id", ["", ".", "..", "../escape", "a/b", "a\\b"])
def test_unsafe_qc_identity_is_rejected_without_external_artifacts(
    tmp_path: Path, qc_id: str
) -> None:
    store, bundle, scenario, ess_root, _, _, _ = _publish_processing(tmp_path)
    with pytest.raises((ProvisionalQcPersistenceError, StorageError, ValueError)):
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id=qc_id,
            now=lambda: FIXED_TIME,
        )
    qc_root = store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "qc"
    assert not any(path.name.startswith("qc_") for path in qc_root.rglob("*"))


@pytest.mark.parametrize(
    "tamper",
    [
        "metrics",
        "metrics_sidecar",
        "receipt",
        "receipt_sidecar",
        "metadata",
        "completion",
        "record",
        "record_timestamp",
        "event",
        "extra",
    ],
)
def test_qc_validator_rejects_tampering_without_writeback(tmp_path: Path, tamper: str) -> None:
    store, bundle, scenario, ess_root, _, _, qc = _publish_qc(tmp_path)
    if tamper == "metrics":
        path = qc.qc_path / "qc_metrics.json"
        payload = json.loads(path.read_bytes())
        payload["estimated_latency_samples"] += 1
        path.write_bytes(canonical_json_bytes(payload))
    elif tamper == "metrics_sidecar":
        path = qc.qc_path / "qc_metrics.sha256"
        path.write_bytes(b"0" * 64 + b"  qc_metrics.json\n")
    elif tamper == "receipt":
        path = qc.qc_path / "qc_receipt.json"
        payload = json.loads(path.read_bytes())
        payload["hardware_ready"] = True
        path.write_bytes(canonical_json_bytes(payload))
    elif tamper == "receipt_sidecar":
        path = qc.qc_path / "qc_receipt.sha256"
        path.write_bytes(b"0" * 64 + b"  qc_receipt.json\n")
    elif tamper == "metadata":
        path = qc.qc_path / "qc_metadata.json"
        payload = json.loads(path.read_bytes())
        payload["formal_eligible"] = True
        path.write_bytes(canonical_json_bytes(payload))
    elif tamper == "completion":
        path = qc.qc_path / "QC_COMPLETE"
        path.write_bytes(b"tampered\n")
    elif tamper == "record":
        path = qc.qc_path / "qc_record.json"
        payload = json.loads(path.read_bytes())
        payload["decision_status"] = "pass"
        path.write_bytes(canonical_json_bytes(payload))
    elif tamper == "record_timestamp":
        path = qc.qc_path / "qc_record.json"
        payload = json.loads(path.read_bytes())
        payload["created_at"] = "2030-01-01T00:00:00Z"
        path.write_bytes(canonical_json_bytes(payload))
    elif tamper == "event":
        path = next(
            (store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "events").glob(
                "*_qc_created.json"
            )
        )
        payload = json.loads(path.read_bytes())
        payload["qc_metrics_sha256"] = "0" * 64
        path.write_bytes(canonical_json_bytes(payload))
    else:
        path = qc.qc_path / "extra.bin"
        path.write_bytes(b"extra")
    tampered = path.read_bytes()
    with pytest.raises((ProvisionalQcPersistenceError, ValidationError, ValueError)):
        validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="qc-1",
        )
    assert path.read_bytes() == tampered


def test_same_qc_id_is_allowed_for_distinct_processing_identity(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, first = _publish_qc(tmp_path, "shared")
    publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-2",
        now=lambda: FIXED_TIME,
    )
    second = publish_provisional_qc(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-1",
        processing_id="processing-2",
        qc_id="shared",
        now=lambda: FIXED_TIME,
    )
    assert first.qc_path != second.qc_path
    for processing_id in ("processing-1", "processing-2"):
        validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id=processing_id,
            qc_id="shared",
        )


def test_same_processing_and_qc_ids_are_allowed_for_distinct_source_runs(
    tmp_path: Path,
) -> None:
    store, bundle, scenario, ess_root, _, _, first = _publish_qc(tmp_path, "shared")
    publish_virtual_capture(
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
    publish_ess_processing(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-2",
        processing_id="processing-1",
        now=lambda: FIXED_TIME + timedelta(seconds=1),
    )
    second = publish_provisional_qc(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_root,
        session_id="capture-session",
        source_run_id="capture-2",
        processing_id="processing-1",
        qc_id="shared",
        now=lambda: FIXED_TIME + timedelta(seconds=1),
    )
    assert first.qc_path != second.qc_path
    for source_run_id in ("capture-1", "capture-2"):
        validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id=source_run_id,
            processing_id="processing-1",
            qc_id="shared",
        )


def test_concurrent_qc_publication_has_at_most_one_success(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, _ = _publish_processing(tmp_path)

    def publish() -> object:
        return publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="concurrent",
            now=lambda: FIXED_TIME,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(publish) for _ in range(2)]
    successes = [future.result() for future in futures if future.exception() is None]
    failures = [future.exception() for future in futures if future.exception() is not None]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], ProvisionalQcPersistenceError)


def test_qc_staging_failure_cleans_only_its_staging_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, bundle, scenario, ess_root, _, _, _ = _publish_processing(tmp_path)
    original = atomic_write_bytes

    def fail_receipt(path: str | Path, data: bytes) -> None:
        if Path(path).name == "qc_receipt.json":
            raise StorageError("injected staging failure")
        original(path, data)

    monkeypatch.setattr("acoustic_ladder.storage.store.atomic_write_bytes", fail_receipt)
    with pytest.raises(ProvisionalQcPersistenceError, match="published=false"):
        publish_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="staging-failure",
            now=lambda: FIXED_TIME,
        )
    parent = (
        store.session_path(DataOrigin.SYNTHETIC, "capture-session")
        / "qc"
        / "run_capture-1"
        / "processing_processing-1"
    )
    assert not (parent / "qc_staging-failure").exists()
    assert not any("staging-failure" in path.name for path in parent.iterdir())


@pytest.mark.parametrize(
    ("sidecar_name", "payload_name"),
    [("qc_metrics.sha256", "qc_metrics.json"), ("qc_receipt.sha256", "qc_receipt.json")],
)
@pytest.mark.parametrize(
    "form", ["wrong_digest", "uppercase", "one_space", "wrong_name", "crlf", "no_newline"]
)
def test_both_qc_sidecars_reject_every_noncanonical_form(
    tmp_path: Path, sidecar_name: str, payload_name: str, form: str
) -> None:
    store, bundle, scenario, ess_root, _, _, qc = _publish_qc(tmp_path)
    digest = hashlib.sha256((qc.qc_path / payload_name).read_bytes()).hexdigest()
    if form == "wrong_digest":
        sidecar_bytes = f"{'0' * 64}  {payload_name}\n".encode()
    elif form == "uppercase":
        sidecar_bytes = f"{digest.upper()}  {payload_name}\n".encode()
    elif form == "one_space":
        sidecar_bytes = f"{digest} {payload_name}\n".encode()
    elif form == "wrong_name":
        sidecar_bytes = f"{digest}  wrong.json\n".encode()
    elif form == "crlf":
        sidecar_bytes = f"{digest}  {payload_name}\r\n".encode()
    else:
        sidecar_bytes = f"{digest}  {payload_name}".encode()
    sidecar = qc.qc_path / sidecar_name
    sidecar.write_bytes(sidecar_bytes)
    tampered = sidecar.read_bytes()
    with pytest.raises(ProvisionalQcPersistenceError, match="sidecar"):
        validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="qc-1",
        )
    assert sidecar.read_bytes() == tampered


@pytest.mark.parametrize("tamper", ["identity", "sequence", "noncanonical", "extra", "missing"])
def test_qc_event_envelope_attacks_are_rejected_without_repair(tmp_path: Path, tamper: str) -> None:
    store, bundle, scenario, ess_root, _, _, _ = _publish_qc(tmp_path)
    event_path = next(
        (store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "events").glob(
            "*_qc_created.json"
        )
    )
    payload = json.loads(event_path.read_bytes())
    if tamper == "identity":
        payload["qc_id"] = "other"
        event_path.write_bytes(canonical_json_bytes(payload))
    elif tamper == "sequence":
        payload["sequence"] += 1
        event_path.write_bytes(canonical_json_bytes(payload))
    elif tamper == "noncanonical":
        event_path.write_bytes(b" " + canonical_json_bytes(payload))
    elif tamper == "extra":
        payload["extra"] = True
        event_path.write_bytes(canonical_json_bytes(payload))
    else:
        event_path.unlink()
    before = event_path.read_bytes() if event_path.exists() else None
    with pytest.raises(ProvisionalQcPersistenceError):
        validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="qc-1",
        )
    after = event_path.read_bytes() if event_path.exists() else None
    assert after == before


@pytest.mark.parametrize("tamper", ["incomplete", "arrays"])
def test_qc_validator_rejects_invalid_source_processing_without_qc_writeback(
    tmp_path: Path, tamper: str
) -> None:
    store, bundle, scenario, ess_root, _, processing, qc = _publish_qc(tmp_path)
    qc_before = {path.name: path.read_bytes() for path in qc.qc_path.iterdir()}
    if tamper == "incomplete":
        target = processing.processing_path / "PROCESSING_COMPLETE"
        target.unlink()
    else:
        target = processing.processing_path / "processing_arrays.npz"
        target.write_bytes(target.read_bytes() + b"tampered")
    target_before = target.read_bytes() if target.exists() else None
    with pytest.raises(ProvisionalQcPersistenceError):
        validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="qc-1",
        )
    assert (target.read_bytes() if target.exists() else None) == target_before
    assert {path.name: path.read_bytes() for path in qc.qc_path.iterdir()} == qc_before


def test_qc_cli_complete_workflow_has_required_safety_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store, _, _, ess_root, _, _, _ = _publish_processing(tmp_path)
    args = [
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
        "--source-run-id",
        "capture-1",
        "--processing-id",
        "processing-1",
        "--qc-id",
        "cli-qc",
        "--scenario",
        "tests/fixtures/audio/virtual_duplex_development.yaml",
        "--ess-artifact-root",
        str(ess_root),
    ]
    cli.main(["qc-compute", *args])
    generated = capsys.readouterr().out
    cli.main(["qc-validate", *args])
    validated = capsys.readouterr().out
    for output in (generated, validated):
        assert "SYNTHETIC_ONLY" in output
        assert "PROVISIONAL_METRICS_ONLY" in output
        assert "THRESHOLDS_NOT_APPLIED" in output
        assert "NO_HARDWARE_AUDIO_IO_PERFORMED" in output
        assert "NOT_AN_EXPERIMENTAL_RESULT" in output
        assert "input_snr_proxy_status=zero_pre_silence_rms" in output
        assert "qc_decision=not_evaluated" in output
        assert "thresholds_applied=false" in output
        assert "formal_eligible=false" in output
        assert "experimental_result=false" in output
        assert "safety_marker=SYNTHETIC_PROVISIONAL_QC_METRICS_NOT_AN_EXPERIMENTAL_RESULT" in output


@pytest.mark.parametrize(
    "forbidden",
    [
        "--real-root",
        "--wav",
        "--npz",
        "--expected-latency",
        "--threshold",
        "--decision",
        "--device",
    ],
)
def test_qc_cli_rejects_forbidden_authority_options(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "qc-compute",
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
                "--qc-id",
                "qc",
                "--scenario",
                "scenario.yaml",
                "--ess-artifact-root",
                "ess",
                forbidden,
                "1",
            ]
        )


def test_provisional_qc_schemas_are_generated_from_active_models() -> None:
    assert len(ALL_GENERATED_SCHEMA_MODELS) == 20
    assert "provisional_qc_metrics.schema.json" in ALL_GENERATED_SCHEMA_MODELS
    assert "provisional_qc_receipt.schema.json" in ALL_GENERATED_SCHEMA_MODELS
    check_schemas(PROJECT_ROOT / "schemas")
    assert len(list((PROJECT_ROOT / "schemas").glob("*.schema.json"))) == 21


def test_publisher_rejects_non_null_analysis_qc_threshold(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, _ = _publish_processing(tmp_path)
    loaded = bundle.configs["analysis"]
    assert isinstance(loaded.model, AnalysisConfig)
    analysis = loaded.model.model_copy(
        update={
            "decision_gates": loaded.model.decision_gates.model_copy(update={"qc_threshold": 0.5})
        }
    )
    modified = replace(
        bundle,
        configs={**bundle.configs, "analysis": replace(loaded, model=analysis)},
    )
    with pytest.raises(ProvisionalQcPersistenceError, match="non-null qc_threshold"):
        publish_provisional_qc(
            store=store,
            bundle=modified,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="threshold-refused",
            now=lambda: FIXED_TIME,
        )


def test_duplicate_composite_qc_event_is_rejected_without_qc_writeback(tmp_path: Path) -> None:
    store, bundle, scenario, ess_root, _, _, qc = _publish_qc(tmp_path)
    before = {path.name: path.read_bytes() for path in qc.qc_path.iterdir()}
    event_path = next(
        (store.session_path(DataOrigin.SYNTHETIC, "capture-session") / "events").glob(
            "*_qc_created.json"
        )
    )
    event = json.loads(event_path.read_bytes())
    store.append_event(
        DataOrigin.SYNTHETIC,
        "capture-session",
        "qc_created",
        {
            key: value
            for key, value in event.items()
            if key not in {"event", "sequence", "session_id", "data_origin"}
        },
    )
    with pytest.raises(ProvisionalQcPersistenceError, match="exactly one matching"):
        validate_provisional_qc(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_root,
            session_id="capture-session",
            source_run_id="capture-1",
            processing_id="processing-1",
            qc_id="qc-1",
        )
    assert {path.name: path.read_bytes() for path in qc.qc_path.iterdir()} == before


def test_qc_deterministic_payloads_match_across_independent_roots(tmp_path: Path) -> None:
    *_, first = _publish_qc(tmp_path / "first")
    *_, second = _publish_qc(tmp_path / "second")
    deterministic_names = (
        "qc_metrics.json",
        "qc_metrics.sha256",
        "qc_receipt.json",
        "qc_receipt.sha256",
        "qc_metadata.json",
    )
    for name in deterministic_names:
        assert (first.qc_path / name).read_bytes() == (second.qc_path / name).read_bytes()


def test_dev0401r2_processing_payload_hashes_remain_protected(tmp_path: Path) -> None:
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
    for name, digest in expected.items():
        assert (
            hashlib.sha256((processing.processing_path / name).read_bytes()).hexdigest() == digest
        )
