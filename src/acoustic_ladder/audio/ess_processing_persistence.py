"""Synthetic-only immutable publication and replay validation for offline ESS processing."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import ValidationError

from acoustic_ladder.audio.ess_processing import EssProcessingResult, process_ess_waveforms
from acoustic_ladder.audio.ess_processing_models import (
    SAFETY_MARKER,
    EssProcessingReceipt,
    ProcessingArrayDescriptor,
    ProcessingRecord,
    PublishedEssProcessing,
)
from acoustic_ladder.audio.excitation_persistence import (
    WAV_NAME,
    EssArtifactReceipt,
    decode_ieee_float32_wav,
    validate_offline_ess_artifact,
)
from acoustic_ladder.audio.virtual_capture_models import LoadedVirtualCaptureScenario
from acoustic_ladder.audio.virtual_capture_persistence import (
    INPUT_WAV,
    OUTPUT_WAV,
    PublishedVirtualCapture,
    validate_virtual_capture,
)
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.storage.io import StorageError, safe_identifier, sha256_bytes
from acoustic_ladder.storage.npz import deterministic_npz_bytes, load_deterministic_npz
from acoustic_ladder.storage.store import ImmutableSessionStore

ARRAYS_NAME = "processing_arrays.npz"
ARRAYS_SIDECAR = "processing_arrays.npz.sha256"
RECEIPT_NAME = "processing_receipt.json"
RECEIPT_SIDECAR = "processing_receipt.sha256"
METADATA_NAME = "processing_metadata.json"
RECORD_NAME = "processing_record.json"
COMPLETE_NAME = "PROCESSING_COMPLETE"
PROCESSING_FILE_NAMES = frozenset(
    {
        ARRAYS_NAME,
        ARRAYS_SIDECAR,
        RECEIPT_NAME,
        RECEIPT_SIDECAR,
        METADATA_NAME,
        RECORD_NAME,
        COMPLETE_NAME,
    }
)
_ASCII_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]+$")


class EssProcessingPersistenceError(StorageError):
    """Processing publication/validation error with an explicit publication state."""

    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(f"{message}; published={str(published).lower()}")
        self.published = published


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _metadata(receipt_sha256: str) -> dict[str, object]:
    return {
        "data_origin": "synthetic",
        "experimental_result": False,
        "formal_eligible": False,
        "hardware_io_performed": False,
        "processing_receipt_sha256": receipt_sha256,
        "run_mode": "development",
        "safety_marker": SAFETY_MARKER,
    }


def _raw_array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _descriptors(result: EssProcessingResult) -> dict[str, ProcessingArrayDescriptor]:
    descriptors: dict[str, ProcessingArrayDescriptor] = {}
    for name, array in sorted(result.arrays.items()):
        dtype: Literal["float64", "int64", "bool"]
        if array.dtype == np.dtype(np.float64):
            dtype = "float64"
        elif array.dtype == np.dtype(np.int64):
            dtype = "int64"
        elif array.dtype == np.dtype(np.bool_):
            dtype = "bool"
        else:
            raise EssProcessingPersistenceError(
                f"unsupported processing array dtype: {array.dtype}", published=False
            )
        descriptors[name] = ProcessingArrayDescriptor(
            name=name,
            dtype=dtype,
            shape=array.shape,
            raw_sha256=_raw_array_sha256(array),
        )
    return descriptors


def _analysis(bundle: LoadedBundle) -> tuple[AnalysisConfig, str, str, str]:
    loaded = bundle.configs.get("analysis")
    if loaded is None or not isinstance(loaded.model, AnalysisConfig):
        raise EssProcessingPersistenceError(
            "processing requires a loaded analysis configuration", published=False
        )
    return (
        loaded.model,
        loaded.snapshot.original_relative_path,
        loaded.snapshot.original_sha256,
        loaded.snapshot.normalized_sha256,
    )


def _compute(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    source_run_id: str,
) -> tuple[EssProcessingResult, PublishedVirtualCapture, EssArtifactReceipt]:
    capture = validate_virtual_capture(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        run_id=source_run_id,
    )
    ess = validate_offline_ess_artifact(ess_artifact_root, bundle.configs["audio"])
    run_path = capture.run_path
    output, output_rate = decode_ieee_float32_wav((run_path / OUTPUT_WAV).read_bytes())
    captured, input_rate = decode_ieee_float32_wav((run_path / INPUT_WAV).read_bytes())
    source_wav, source_rate = decode_ieee_float32_wav(
        (Path(ess_artifact_root) / WAV_NAME).read_bytes()
    )
    if output_rate != input_rate or output_rate != source_rate:
        raise EssProcessingPersistenceError("source sample rates disagree", published=False)
    if not np.array_equal(output[:, : source_wav.shape[1]], source_wav):
        raise EssProcessingPersistenceError(
            "capture output reference does not begin with validated ESS", published=False
        )
    analysis, _, _, _ = _analysis(bundle)
    timing = ess.metadata.timing
    spec = ess.metadata.spec
    result = process_ess_waveforms(
        output,
        captured,
        sample_rate_hz=source_rate,
        sweep_sample_count=timing.sweep_sample_count,
        pre_silence_sample_count=timing.pre_silence_sample_count,
        start_frequency_hz=spec.start_frequency_hz,
        end_frequency_hz=spec.end_frequency_hz,
        analysis_lower_hz=analysis.analysis_band.lower_hz,
        analysis_upper_hz=analysis.analysis_band.upper_hz,
        smoothing_enabled=analysis.smoothing.enabled,
    )
    return result, capture, ess


def _receipt(
    *,
    processing_id: str,
    session_id: str,
    source_run_id: str,
    bundle: LoadedBundle,
    result: EssProcessingResult,
    capture: PublishedVirtualCapture,
    ess: EssArtifactReceipt,
    arrays_sha256: str,
) -> EssProcessingReceipt:
    # Runtime objects have already passed their strict public validators in _compute.
    capture_receipt = capture.receipt
    ess_receipt = ess
    analysis, reference, raw_hash, normalized_hash = _analysis(bundle)
    timing = ess_receipt.metadata.timing
    arrays = result.arrays
    return EssProcessingReceipt(
        schema_version="1.0.0",
        processing_id=processing_id,
        source_run_id=source_run_id,
        session_id=session_id,
        data_origin="synthetic",
        run_mode="development",
        source_capture_receipt_sha256=capture.receipt_sha256,
        source_output_wav_sha256=capture_receipt.output_wav_sha256,
        source_input_wav_sha256=capture_receipt.input_wav_sha256,
        source_output_raw_float32_sha256=capture_receipt.output_raw_float32_sha256,
        source_input_raw_float32_sha256=capture_receipt.input_raw_float32_sha256,
        source_capture_scenario_reference=capture_receipt.scenario_reference,
        source_capture_scenario_raw_sha256=capture_receipt.scenario_raw_sha256,
        source_capture_scenario_normalized_sha256=capture_receipt.scenario_normalized_sha256,
        source_ess_artifact_id=ess_receipt.artifact_id,
        source_ess_metadata_sha256=ess_receipt.metadata_sha256,
        source_ess_wav_sha256=ess_receipt.wav_sha256,
        source_ess_raw_float32_sha256=ess_receipt.raw_float32_sha256,
        bundle_content_sha256=bundle.receipt.bundle_content_sha256,
        device_manifest_sha256=bundle.receipt.device_manifest_sha256,
        config_snapshots=bundle.receipt.snapshots,
        analysis_config_reference=reference,
        analysis_config_raw_sha256=raw_hash,
        analysis_config_normalized_sha256=normalized_hash,
        algorithm_id="offline_ess_deconvolution_transfer",
        algorithm_version="1.0.0",
        inverse_formula_id="farina_exponential_sweep_amplitude_compensation",
        inverse_filter_formula="s[N-1-n]*exp(-ln(f_end/f_start)*n/N)",
        convolution_method="full_linear_rfft_power_of_two",
        latency_method="normalized_full_sweep_matched_correlation",
        lag_convention="positive_input_lags_output",
        alignment_method="zero_fill_no_circular_wrap",
        deconvolution_time_origin="reference_deconvolution_unique_absolute_peak",
        ir_raw_definition="input_deconvolution_from_reference_peak",
        phase_unwrap_axis="frequency_last_axis",
        sample_rate_hz=ess_receipt.metadata.sample_rate_hz,
        sweep_sample_count=timing.sweep_sample_count,
        pre_silence_sample_count=timing.pre_silence_sample_count,
        post_silence_sample_count=timing.post_silence_sample_count,
        source_output_sample_count=capture_receipt.output_shape[1],
        source_input_sample_count=capture_receipt.input_shape[1],
        output_after_pre_sample_count=arrays["reference_deconvolution"].size
        - arrays["inverse_filter"].size
        + 1,
        input_after_pre_sample_count=arrays["input_deconvolution"].size
        - arrays["inverse_filter"].size
        + 1,
        inverse_filter_sample_count=arrays["inverse_filter"].size,
        reference_deconvolution_sample_count=arrays["reference_deconvolution"].size,
        input_deconvolution_sample_count=arrays["input_deconvolution"].size,
        ir_sample_count=arrays["ir_raw"].shape[-1],
        inverse_fft_length=result.inverse_fft_length,
        deconvolution_fft_length=result.deconvolution_fft_length,
        transfer_fft_length=result.transfer_fft_length,
        frequency_bin_count=arrays["frequency_hz"].size,
        reference_peak_index=result.reference_peak_index,
        inverse_pre_normalization_peak=result.inverse_pre_normalization_peak,
        inverse_normalization_factor=result.inverse_normalization_factor,
        inverse_post_normalization_peak=result.inverse_post_normalization_peak,
        estimated_latency_samples=result.estimated_latency_samples,
        estimated_latency_seconds=(
            result.estimated_latency_samples / ess_receipt.metadata.sample_rate_hz
        ),
        matched_correlation_signed=result.latency_correlation_coefficient,
        matched_correlation_absolute=abs(result.latency_correlation_coefficient),
        candidate_lag_min=0,
        candidate_lag_max=(
            arrays["input_deconvolution"].size
            - arrays["inverse_filter"].size
            + 1
            - timing.sweep_sample_count
        ),
        ir_dominant_peak_index=result.ir_raw_dominant_peak_index,
        ir_dominant_peak_value=result.ir_raw_dominant_peak_value,
        analysis_band_lower_hz=analysis.analysis_band.lower_hz,
        analysis_band_upper_hz=analysis.analysis_band.upper_hz,
        smoothing_enabled=False,
        db_floor_strategy="numpy_float64_tiny_before_log10",
        array_descriptors=_descriptors(result),
        processing_arrays_npz_sha256=arrays_sha256,
        create_only=True,
        immutable=True,
        hardware_io_performed=False,
        playback_performed=False,
        recording_performed=False,
        hardware_ready=False,
        full_duplex_verified=False,
        shared_clock_verified=False,
        channel_mapping_verified=False,
        calibration_file_verified=False,
        calibration_applied=False,
        absolute_spl_calibrated=False,
        electrical_loopback_available=False,
        formal_eligible=False,
        experimental_result=False,
        safety_marker=SAFETY_MARKER,
    )


def _identifier(value: str, label: str) -> None:
    if _ASCII_IDENTIFIER.fullmatch(value) is None or value in {".", ".."}:
        raise EssProcessingPersistenceError(f"unsafe {label}: {value!r}", published=False)
    safe_identifier(value, label)


def publish_ess_processing(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    source_run_id: str,
    processing_id: str,
    now: Callable[[], datetime],
) -> PublishedEssProcessing:
    """Replay-validate a synthetic capture, compute, and create-only publish processing."""

    result, capture, ess = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        source_run_id=source_run_id,
    )
    _identifier(processing_id, "processing_id")
    arrays_bytes = deterministic_npz_bytes(result.arrays)
    arrays_digest = sha256_bytes(arrays_bytes)
    receipt = _receipt(
        processing_id=processing_id,
        session_id=session_id,
        source_run_id=source_run_id,
        bundle=bundle,
        result=result,
        capture=capture,
        ess=ess,
        arrays_sha256=arrays_digest,
    )
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    receipt_digest = sha256_bytes(receipt_bytes)
    timestamp = now()
    record = ProcessingRecord(
        schema_version="1.0.0",
        processing_id=processing_id,
        session_id=session_id,
        source_run_id=source_run_id,
        created_at=timestamp,
        status="complete",
        processing_receipt_sha256=receipt_digest,
        data_origin="synthetic",
        run_mode="development",
        formal_eligible=False,
        experimental_result=False,
        result_marker="NOT_AN_EXPERIMENTAL_RESULT",
    )
    session = store.session_path(DataOrigin.SYNTHETIC, session_id)
    target = session / "processed" / f"run_{source_run_id}" / f"processing_{processing_id}"
    try:
        path = store.create_synthetic_processing(
            session_id=session_id,
            source_run_id=source_run_id,
            processing_id=processing_id,
            artifact_payloads={
                ARRAYS_NAME: arrays_bytes,
                ARRAYS_SIDECAR: _sidecar(arrays_digest, ARRAYS_NAME),
                RECEIPT_NAME: receipt_bytes,
                RECEIPT_SIDECAR: _sidecar(receipt_digest, RECEIPT_NAME),
            },
            metadata=_metadata(receipt_digest),
            record=record,
        )
    except Exception as exc:
        published = (target / COMPLETE_NAME).is_file()
        raise EssProcessingPersistenceError(str(exc), published=published) from exc
    return PublishedEssProcessing(path, receipt, receipt_digest, arrays_digest, timestamp)


def _verify_sidecar(root: Path, filename: str, sidecar: str) -> str:
    digest = sha256_bytes((root / filename).read_bytes())
    try:
        words = (root / sidecar).read_text(encoding="ascii").split()
    except (OSError, UnicodeError) as exc:
        raise EssProcessingPersistenceError(str(exc), published=True) from exc
    if words != [digest, filename]:
        raise EssProcessingPersistenceError(
            f"invalid SHA256 sidecar for {filename}", published=True
        )
    return digest


def validate_ess_processing(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    source_run_id: str,
    processing_id: str,
) -> PublishedEssProcessing:
    """Read-only byte and semantic replay validation of completed ESS processing."""

    result, capture, ess = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        source_run_id=source_run_id,
    )
    _identifier(processing_id, "processing_id")
    root = (
        store.session_path(DataOrigin.SYNTHETIC, session_id)
        / "processed"
        / f"run_{source_run_id}"
        / f"processing_{processing_id}"
    )
    if not root.is_dir() or {entry.name for entry in root.iterdir()} != PROCESSING_FILE_NAMES:
        raise EssProcessingPersistenceError(
            "processing directory does not contain exactly the required files", published=True
        )
    arrays_digest = _verify_sidecar(root, ARRAYS_NAME, ARRAYS_SIDECAR)
    receipt_digest = _verify_sidecar(root, RECEIPT_NAME, RECEIPT_SIDECAR)
    try:
        receipt = EssProcessingReceipt.model_validate_json((root / RECEIPT_NAME).read_bytes())
        record = ProcessingRecord.model_validate_json((root / RECORD_NAME).read_bytes())
    except ValidationError as exc:
        raise EssProcessingPersistenceError(str(exc), published=True) from exc
    if (root / RECEIPT_NAME).read_bytes() != canonical_json_bytes(receipt.model_dump(mode="json")):
        raise EssProcessingPersistenceError("processing receipt is not canonical", published=True)
    if (root / RECORD_NAME).read_bytes() != canonical_json_bytes(record.model_dump(mode="json")):
        raise EssProcessingPersistenceError("processing record is not canonical", published=True)
    arrays_bytes = deterministic_npz_bytes(result.arrays)
    expected_arrays_digest = sha256_bytes(arrays_bytes)
    expected_receipt = _receipt(
        processing_id=processing_id,
        session_id=session_id,
        source_run_id=source_run_id,
        bundle=bundle,
        result=result,
        capture=capture,
        ess=ess,
        arrays_sha256=expected_arrays_digest,
    )
    expected_receipt_bytes = canonical_json_bytes(expected_receipt.model_dump(mode="json"))
    expected_receipt_digest = sha256_bytes(expected_receipt_bytes)
    if (root / ARRAYS_NAME).read_bytes() != arrays_bytes:
        raise EssProcessingPersistenceError("processing arrays differ from replay", published=True)
    stored_arrays = load_deterministic_npz((root / ARRAYS_NAME).read_bytes())
    if set(stored_arrays) != set(result.arrays) or any(
        not np.array_equal(stored_arrays[name], result.arrays[name]) for name in result.arrays
    ):
        raise EssProcessingPersistenceError("processing array semantics differ", published=True)
    if receipt != expected_receipt or receipt_digest != expected_receipt_digest:
        raise EssProcessingPersistenceError(
            "processing receipt differs from replay", published=True
        )
    if (root / METADATA_NAME).read_bytes() != canonical_json_bytes(
        _metadata(expected_receipt_digest)
    ):
        raise EssProcessingPersistenceError("processing metadata differs", published=True)
    expected_record = ProcessingRecord(
        schema_version="1.0.0",
        processing_id=processing_id,
        session_id=session_id,
        source_run_id=source_run_id,
        created_at=record.created_at,
        status="complete",
        processing_receipt_sha256=expected_receipt_digest,
        data_origin="synthetic",
        run_mode="development",
        formal_eligible=False,
        experimental_result=False,
        result_marker="NOT_AN_EXPERIMENTAL_RESULT",
    )
    if record != expected_record:
        raise EssProcessingPersistenceError("processing record differs", published=True)
    if arrays_digest != expected_arrays_digest or not (root / COMPLETE_NAME).is_file():
        raise EssProcessingPersistenceError(
            "processing digest or completion differs", published=True
        )
    return PublishedEssProcessing(
        root,
        receipt,
        receipt_digest,
        arrays_digest,
        record.created_at,
    )
