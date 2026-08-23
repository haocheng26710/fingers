import numpy as np

from acoustic_ladder.audio.ess_processing import EssProcessingResult
from acoustic_ladder.audio.microphone_calibration import (
    MicrophoneCalibration,
    apply_microphone_calibration,
)


def _processing_result() -> EssProcessingResult:
    frequency = np.array([0.0, 20.0, 100.0, 1_000.0, 20_000.0, 24_000.0])
    phase = np.array([0.2, -0.4, 0.7, -1.2, 2.4, -2.8])
    transfer = 2.0 * np.exp(1j * phase)

    def cube(value: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(value.reshape(1, 1, -1))

    arrays = {
        "frequency_hz": frequency,
        "transfer_raw_real": cube(transfer.real),
        "transfer_raw_imag": cube(transfer.imag),
        "transfer_aligned_real": cube(transfer.real),
        "transfer_aligned_imag": cube(transfer.imag),
        "magnitude_raw_linear": cube(np.abs(transfer)),
        "magnitude_raw_db": cube(20.0 * np.log10(np.abs(transfer))),
        "magnitude_aligned_linear": cube(np.abs(transfer)),
        "magnitude_aligned_db": cube(20.0 * np.log10(np.abs(transfer))),
        "phase_raw_rad": cube(phase),
        "phase_aligned_rad": cube(phase),
    }
    return EssProcessingResult(
        arrays=arrays,
        inverse_fft_length=1,
        deconvolution_fft_length=1,
        transfer_fft_length=10,
        reference_peak_index=0,
        inverse_pre_normalization_peak=1.0,
        inverse_normalization_factor=1.0,
        inverse_post_normalization_peak=1.0,
        estimated_latency_samples=0,
        latency_correlation_coefficient=1.0,
        ir_raw_dominant_peak_index=0,
        ir_raw_dominant_peak_value=1.0,
    )


def _calibration() -> MicrophoneCalibration:
    frequency = np.array([20.0, 100.0, 1_000.0, 20_000.0])
    correction = np.array([-1.0, -1.0, 2.0, 2.0])
    return MicrophoneCalibration(
        original_filename="fixture.txt",
        sha256="0" * 64,
        sensitivity_1khz_db=-36.2,
        frequency_hz=frequency,
        correction_db=correction,
        frequency_min_hz=20.0,
        frequency_max_hz=20_000.0,
        point_count=4,
        interpolation="linear_in_log10_frequency",
        sign_convention="add_correction_db_to_measured_magnitude_db",
    )


def test_amplitude_calibration_is_derived_non_mutating_and_phase_preserving() -> None:
    raw = _processing_result()
    before = {name: value.tobytes() for name, value in raw.arrays.items()}

    result = apply_microphone_calibration(raw, _calibration())

    correction = np.array([0.0, -1.0, -1.0, 2.0, 2.0, 0.0])
    valid = np.array([False, True, True, True, True, False])
    raw_transfer = raw.arrays["transfer_raw_real"] + 1j * raw.arrays["transfer_raw_imag"]
    calibrated = (
        result.arrays["transfer_raw_calibrated_real"]
        + 1j * result.arrays["transfer_raw_calibrated_imag"]
    )
    expected = raw_transfer * np.where(valid, 10.0 ** (correction / 20.0), 1.0)
    np.testing.assert_allclose(calibrated, expected.reshape(1, 1, -1))
    np.testing.assert_allclose(np.angle(calibrated), raw.arrays["phase_raw_rad"])
    assert np.array_equal(result.arrays["calibration_valid"], valid)
    assert np.array_equal(result.arrays["calibration_correction_db"], correction)
    assert result.uncalibrated is raw
    assert {name: value.tobytes() for name, value in raw.arrays.items()} == before
