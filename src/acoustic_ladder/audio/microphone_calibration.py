"""Strict amplitude-only microphone calibration and pilot-bundle processing."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.ess_processing import (
    EssProcessingResult,
    ProcessingArray,
    process_ess_waveforms,
)
from acoustic_ladder.audio.excitation_persistence import (
    EssArtifactError,
    decode_ieee_float32_wav,
)
from acoustic_ladder.storage.io import sha256_bytes

Float64Array = NDArray[np.float64]

_HEADER = re.compile(r"^\*1000Hz[ \t]+([^ \t]+)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MicrophoneCalibrationError(ValueError):
    """A calibration or bundle-domain error with source location context."""

    def __init__(self, path: Path, line_number: int | None, code: str, detail: str) -> None:
        location = f"{path}:{line_number}" if line_number is not None else str(path)
        super().__init__(f"{location}: {code}: {detail}")
        self.path = path
        self.line_number = line_number
        self.code = code


@dataclass(frozen=True)
class MicrophoneCalibration:
    original_filename: str
    sha256: str
    sensitivity_1khz_db: float
    frequency_hz: Float64Array
    correction_db: Float64Array
    frequency_min_hz: float
    frequency_max_hz: float
    point_count: int
    interpolation: str
    sign_convention: str


def _finite_float(path: Path, line_number: int, token: str, label: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise MicrophoneCalibrationError(
            path, line_number, "invalid_float", f"{label} is not a floating-point number"
        ) from exc
    if not math.isfinite(value):
        raise MicrophoneCalibrationError(path, line_number, "non_finite", f"{label} must be finite")
    return 0.0 if value == 0.0 else value


def load_dayton_calibration(path: str | Path, *, expected_sha256: str) -> MicrophoneCalibration:
    """Load a hash-bound Dayton two-column calibration file without rewriting it."""

    source = Path(path)
    normalized_digest = expected_sha256.lower()
    if _SHA256.fullmatch(normalized_digest) is None:
        raise MicrophoneCalibrationError(
            source, None, "invalid_expected_sha256", "expected SHA256 must be 64 hex digits"
        )
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise MicrophoneCalibrationError(source, None, "read_error", str(exc)) from exc
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != normalized_digest:
        raise MicrophoneCalibrationError(
            source,
            None,
            "sha256_mismatch",
            f"expected {normalized_digest}, got {actual_digest}",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        line_number = payload[: exc.start].count(b"\n") + 1
        raise MicrophoneCalibrationError(
            source, line_number, "encoding", "file must be ASCII or UTF-8"
        ) from exc
    numbered = [(index, line) for index, line in enumerate(text.splitlines(), 1) if line.strip()]
    if not numbered:
        raise MicrophoneCalibrationError(source, 1, "missing_header", "file is empty")
    header_line, header = numbered[0]
    match = _HEADER.fullmatch(header)
    if match is None:
        raise MicrophoneCalibrationError(
            source, header_line, "malformed_header", "expected '*1000Hz <finite float>'"
        )
    sensitivity = _finite_float(source, header_line, match.group(1), "1 kHz sensitivity")
    frequencies: list[float] = []
    corrections: list[float] = []
    previous = 0.0
    for line_number, line in numbered[1:]:
        columns = line.split()
        if len(columns) != 2:
            raise MicrophoneCalibrationError(
                source, line_number, "column_count", "data line must contain exactly two columns"
            )
        frequency = _finite_float(source, line_number, columns[0], "frequency")
        correction = _finite_float(source, line_number, columns[1], "correction")
        if frequency <= 0:
            raise MicrophoneCalibrationError(
                source, line_number, "non_positive_frequency", "frequency must be greater than zero"
            )
        if frequency <= previous:
            code = "duplicate_frequency" if frequency == previous else "non_increasing_frequency"
            raise MicrophoneCalibrationError(
                source, line_number, code, "frequencies must be strictly increasing"
            )
        frequencies.append(frequency)
        corrections.append(correction)
        previous = frequency
    if not frequencies:
        raise MicrophoneCalibrationError(source, header_line, "missing_data", "no data points")
    if frequencies[0] > 500.0 or frequencies[-1] < 8_000.0:
        raise MicrophoneCalibrationError(
            source, None, "analysis_band_not_covered", "calibration must cover 500-8000 Hz"
        )
    frequency_array = np.ascontiguousarray(frequencies, dtype=np.float64)
    correction_array = np.ascontiguousarray(corrections, dtype=np.float64)
    frequency_array.flags.writeable = False
    correction_array.flags.writeable = False
    return MicrophoneCalibration(
        original_filename=source.name,
        sha256=actual_digest,
        sensitivity_1khz_db=sensitivity,
        frequency_hz=frequency_array,
        correction_db=correction_array,
        frequency_min_hz=float(frequency_array[0]),
        frequency_max_hz=float(frequency_array[-1]),
        point_count=frequency_array.size,
        interpolation="linear_in_log10_frequency",
        sign_convention="add_correction_db_to_measured_magnitude_db",
    )


def interpolate_calibration(
    calibration: MicrophoneCalibration,
    target_frequencies_hz: NDArray[np.generic],
) -> tuple[Float64Array, NDArray[np.bool_]]:
    """Linearly interpolate dB corrections on log10 frequency without extrapolation.

    Dayton points are approximately log-frequency spaced, and acoustic response is normally
    interpreted on a log-frequency axis; dB correction values themselves remain linear.
    """

    targets = np.asarray(target_frequencies_hz, dtype=np.float64)
    if targets.ndim != 1 or not bool(np.isfinite(targets).all()):
        raise MicrophoneCalibrationError(
            Path(calibration.original_filename),
            None,
            "invalid_target_frequencies",
            "targets must be a finite one-dimensional array",
        )
    correction = np.zeros_like(targets)
    valid = (targets >= calibration.frequency_min_hz) & (targets <= calibration.frequency_max_hz)
    if bool(valid.any()):
        correction[valid] = np.interp(
            np.log10(targets[valid]),
            np.log10(calibration.frequency_hz),
            calibration.correction_db,
        )
    return np.ascontiguousarray(correction), np.ascontiguousarray(valid)


@dataclass(frozen=True)
class CalibratedEssProcessingResult:
    """Amplitude-calibrated derivatives alongside untouched ESS processing evidence."""

    uncalibrated: EssProcessingResult
    arrays: dict[str, ProcessingArray]


def _transfer_cube(result: EssProcessingResult, variant: str) -> NDArray[np.complex128]:
    real = np.asarray(result.arrays[f"transfer_{variant}_real"], dtype=np.float64)
    imaginary = np.asarray(result.arrays[f"transfer_{variant}_imag"], dtype=np.float64)
    frequency = result.arrays["frequency_hz"]
    expected_shape = (1, 1, frequency.size)
    if real.shape != expected_shape or imaginary.shape != expected_shape:
        raise MicrophoneCalibrationError(
            Path("<processing>"),
            None,
            "invalid_transfer_shape",
            f"{variant} transfer must have shape {expected_shape}",
        )
    transfer = real + 1j * imaginary
    if not bool(np.isfinite(transfer).all()):
        raise MicrophoneCalibrationError(
            Path("<processing>"), None, "non_finite_transfer", "transfer must be finite"
        )
    return np.ascontiguousarray(transfer, dtype=np.complex128)


def apply_microphone_calibration(
    result: EssProcessingResult, calibration: MicrophoneCalibration
) -> CalibratedEssProcessingResult:
    """Add amplitude-only calibrated derivatives without mutating raw processing arrays."""

    frequency = np.asarray(result.arrays["frequency_hz"], dtype=np.float64)
    correction, valid = interpolate_calibration(calibration, frequency)
    scale = np.where(valid, np.power(10.0, correction / 20.0), 1.0)
    scale_cube = scale.reshape(1, 1, -1)
    floor = np.finfo(np.float64).tiny
    derived: dict[str, ProcessingArray] = {
        "calibration_correction_db": correction,
        "calibration_valid": valid,
    }
    for variant in ("raw", "aligned"):
        uncalibrated = _transfer_cube(result, variant)
        calibrated = np.ascontiguousarray(uncalibrated * scale_cube)
        magnitude = np.ascontiguousarray(np.abs(calibrated), dtype=np.float64)
        derived[f"transfer_{variant}_calibrated_real"] = np.ascontiguousarray(
            calibrated.real, dtype=np.float64
        )
        derived[f"transfer_{variant}_calibrated_imag"] = np.ascontiguousarray(
            calibrated.imag, dtype=np.float64
        )
        derived[f"magnitude_{variant}_calibrated_linear"] = magnitude
        derived[f"magnitude_{variant}_calibrated_db"] = np.ascontiguousarray(
            20.0 * np.log10(np.maximum(magnitude, floor)), dtype=np.float64
        )
        derived[f"phase_{variant}_calibrated_rad"] = np.ascontiguousarray(
            result.arrays[f"phase_{variant}_rad"], dtype=np.float64
        )
    if any(
        not bool(np.isfinite(array).all()) for array in derived.values() if array.dtype != np.bool_
    ):
        raise MicrophoneCalibrationError(
            Path("<processing>"), None, "non_finite_calibrated", "derived arrays must be finite"
        )
    return CalibratedEssProcessingResult(uncalibrated=result, arrays=derived)


@dataclass(frozen=True)
class PilotBundleProcessingSpec:
    sample_rate_hz: int
    sweep_sample_count: int
    pre_silence_sample_count: int
    start_frequency_hz: float
    end_frequency_hz: float
    analysis_lower_hz: float
    analysis_upper_hz: float
    smoothing_enabled: bool = False


@dataclass(frozen=True)
class MicrophoneCalibrationReceipt:
    microphone_calibration_applied: bool
    calibration_filename: str
    calibration_sha256: str
    calibration_point_count: int
    calibration_frequency_min_hz: float
    calibration_frequency_max_hz: float
    calibration_interpolation: str
    calibration_sign_convention: str
    phase_calibrated: bool
    absolute_spl_calibrated: bool


@dataclass(frozen=True)
class PilotBundleProcessingResult:
    bundle_path: Path
    uncalibrated: EssProcessingResult
    calibrated_arrays: dict[str, ProcessingArray]
    receipt: MicrophoneCalibrationReceipt


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MicrophoneCalibrationError(path, None, "invalid_json", str(exc)) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MicrophoneCalibrationError(path, None, "invalid_json", "expected a JSON object")
    return value


def _required_string(payload: dict[str, object], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise MicrophoneCalibrationError(path, None, "invalid_run_field", f"{key} must be a string")
    return value


def process_pilot_capture_bundle(
    bundle_path: str | Path,
    calibration: MicrophoneCalibration,
    *,
    spec: PilotBundleProcessingSpec,
) -> PilotBundleProcessingResult:
    """Validate a DEV-07.01 bundle and derive raw plus amplitude-calibrated ESS results."""

    bundle = Path(bundle_path).resolve()
    required = {"captured_input.wav", "output_reference.wav", "run.json", "qc.json"}
    if not bundle.is_dir():
        raise MicrophoneCalibrationError(
            bundle, None, "missing_bundle", "bundle directory is missing"
        )
    missing = sorted(name for name in required if not (bundle / name).is_file())
    if missing:
        raise MicrophoneCalibrationError(
            bundle, None, "missing_bundle_file", f"missing required files: {missing}"
        )
    run_path = bundle / "run.json"
    run = _read_json_object(run_path)
    if _required_string(run, "final_state", run_path) != "completed":
        raise MicrophoneCalibrationError(
            run_path, None, "capture_not_completed", "capture final_state must be completed"
        )
    if run.get("sample_rate_hz") != 48_000 or spec.sample_rate_hz != 48_000:
        raise MicrophoneCalibrationError(
            run_path, None, "invalid_sample_rate", "capture and processing must use 48000 Hz"
        )
    if run.get("channel_count_input") != 1 or run.get("channel_count_output") != 1:
        raise MicrophoneCalibrationError(
            run_path, None, "invalid_channel_count", "capture input and output must be mono"
        )
    sample_count = run.get("sample_count")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
        raise MicrophoneCalibrationError(
            run_path, None, "invalid_sample_count", "sample_count must be a positive integer"
        )
    captured_path = bundle / "captured_input.wav"
    output_path = bundle / "output_reference.wav"
    try:
        captured_bytes = captured_path.read_bytes()
        output_bytes = output_path.read_bytes()
    except OSError as exc:
        raise MicrophoneCalibrationError(bundle, None, "bundle_read_error", str(exc)) from exc
    expected_input = _required_string(run, "captured_input_wav_sha256", run_path)
    expected_output = _required_string(run, "output_reference_wav_sha256", run_path)
    if sha256_bytes(captured_bytes) != expected_input:
        raise MicrophoneCalibrationError(
            captured_path,
            None,
            "wav_sha256_mismatch",
            "captured input hash does not match run.json",
        )
    if sha256_bytes(output_bytes) != expected_output:
        raise MicrophoneCalibrationError(
            output_path,
            None,
            "wav_sha256_mismatch",
            "output reference hash does not match run.json",
        )
    try:
        captured, captured_rate = decode_ieee_float32_wav(captured_bytes)
        output, output_rate = decode_ieee_float32_wav(output_bytes)
    except EssArtifactError as exc:
        raise MicrophoneCalibrationError(bundle, None, "invalid_wav", str(exc)) from exc
    if captured_rate != 48_000 or output_rate != 48_000:
        raise MicrophoneCalibrationError(
            bundle, None, "invalid_sample_rate", "both WAV files must use 48000 Hz"
        )
    if captured.shape != output.shape or captured.shape != (1, sample_count):
        raise MicrophoneCalibrationError(
            bundle, None, "invalid_sample_shape", "WAV shapes must be mono and match sample_count"
        )
    if not bool(np.isfinite(captured).all()) or not bool(np.isfinite(output).all()):
        raise MicrophoneCalibrationError(
            bundle, None, "non_finite_wav", "WAV samples must be finite"
        )
    qc = _read_json_object(bundle / "qc.json")
    if qc.get("complete_capture") is not True:
        raise MicrophoneCalibrationError(
            bundle / "qc.json",
            None,
            "incomplete_capture",
            "structural QC must mark capture complete",
        )
    if not (
        calibration.frequency_min_hz <= spec.analysis_lower_hz
        and calibration.frequency_max_hz >= spec.analysis_upper_hz
    ):
        raise MicrophoneCalibrationError(
            Path(calibration.original_filename),
            None,
            "analysis_band_not_covered",
            "calibration does not cover the requested analysis band",
        )
    raw = process_ess_waveforms(
        output,
        captured,
        sample_rate_hz=spec.sample_rate_hz,
        sweep_sample_count=spec.sweep_sample_count,
        pre_silence_sample_count=spec.pre_silence_sample_count,
        start_frequency_hz=spec.start_frequency_hz,
        end_frequency_hz=spec.end_frequency_hz,
        analysis_lower_hz=spec.analysis_lower_hz,
        analysis_upper_hz=spec.analysis_upper_hz,
        smoothing_enabled=spec.smoothing_enabled,
    )
    calibrated = apply_microphone_calibration(raw, calibration)
    receipt = MicrophoneCalibrationReceipt(
        microphone_calibration_applied=True,
        calibration_filename=calibration.original_filename,
        calibration_sha256=calibration.sha256,
        calibration_point_count=calibration.point_count,
        calibration_frequency_min_hz=calibration.frequency_min_hz,
        calibration_frequency_max_hz=calibration.frequency_max_hz,
        calibration_interpolation=calibration.interpolation,
        calibration_sign_convention=calibration.sign_convention,
        phase_calibrated=False,
        absolute_spl_calibrated=False,
    )
    return PilotBundleProcessingResult(
        bundle_path=bundle,
        uncalibrated=raw,
        calibrated_arrays=calibrated.arrays,
        receipt=receipt,
    )
