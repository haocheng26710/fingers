# DEV-07.03 Report — iMM-6C calibration and pilot-bundle processing

## Result and calibration archive

- Source: `D:\Firefly\Downloads\CMM29939.txt`.
- Repository path: `calibration/microphones/dayton_imm6c/CMM29939.txt`.
- Source and repository copy are byte-equal at 3,205 bytes. Both SHA256 values are `421070EC6D41C1B92CB69F0F5E4E290F9644847D92D52590994A80EA9E17A11E`.
- The exact path has a `.gitattributes` `binary` rule, so Git does not normalize its tabs, decimals, blank line, or line endings and whitespace checks do not reinterpret its CRLF data bytes. No duplicate calibration copy was created.

## Parsing and calibration contract

The strict Dayton loader hash-binds the source, decodes UTF-8/ASCII, parses `*1000Hz -36.2` as sensitivity metadata, and accepts only finite two-column data with positive strictly increasing unique frequencies. Errors are translated into `MicrophoneCalibrationError` with path, source line when applicable, and a stable error code; malformed rows are never skipped.

The archived file contains 256 points from 20.0 to 20,000.0 Hz, correction range -0.5 to +2.2 dB, and fully covers the 500–8,000 Hz project analysis band. The -36.2 dB 1 kHz value remains metadata only.

Correction uses linear interpolation of dB values on `log10(f)`. This matches the approximately logarithmic calibration-point spacing and the usual log-frequency interpretation of acoustic response without high-order spline overshoot. Values outside 20–20,000 Hz are not extrapolated: their mask is false, their correction is zero, and the original transfer value is retained.

The Dayton sign convention is additive: `magnitude_calibrated_db = magnitude_raw_db + correction_db`, and complex transfer values are multiplied by `10 ** (correction_db / 20)`. Raw/aligned transfer, magnitude, phase, IR, and all original `EssProcessingResult` arrays remain untouched. The calibration contains no phase data, so phase is copied unchanged; no minimum-phase inference or time-domain filter is used.

## DEV-07.01 bundle adapter and receipt

`process_pilot_capture_bundle` requires the existing four files, completed run state, run-bound WAV SHA256 values, 48 kHz mono canonical IEEE-float32 WAVs, valid matching sample counts, finite data, and structural `complete_capture=true`. It then calls the existing `process_ess_waveforms` public API and adds only derived calibrated arrays. Cancelled, failed, missing, hash-mismatched, malformed, or incomplete bundles are rejected without modifying their bytes.

The frozen DEV-04.01 `EssProcessingReceipt` is strict, Schema-exported, and protected by historical golden hashes with `calibration_applied: Literal[False]`. Expanding it would require a Schema/version/golden migration outside this prompt. DEV-07.03 therefore returns the permitted minimal equivalent runtime `MicrophoneCalibrationReceipt` containing the requested calibration filename/hash/count/range/interpolation/sign fields plus `microphone_calibration_applied=true`, `phase_calibrated=false`, and `absolute_spl_calibrated=false`. No new Schema or sidecar was added.

The original `captured_input.wav`, `output_reference.wav`, `run.json`, and `qc.json` remain byte-identical before and after successful processing. Provisional structural QC is not upgraded to acoustic PASS/FAIL.

## Actual validation

- TDD tracer RED→GREEN covered missing loader, missing interpolation, missing calibration application, missing bundle adapter, and incorrect UTF-8 error-line reporting. One initial bundle GREEN attempt exposed only a test-fixture field mistake (`GeneratedEss.timing` is direct); the fixture was corrected before the production entry ran.
- Final DEV-07.03 directed set: `25 passed in 0.54s`.
- Six directly related existing WAV/ESS/fake-bundle regressions: `6 passed in 2.11s`.
- Ruff format: `8 files already formatted`.
- Ruff lint: `All checks passed!`.
- Strict mypy: `Success: no issues found in 1 source file`.
- The first staged whitespace check showed that `-text` preserved calibration bytes but still exposed every CRLF line to whitespace interpretation. The exact rule was tightened to `binary`; the final staged `git diff --check` then passed with no output.
- The first PowerShell index byte comparison expanded byte arrays and raised a generic-overload error after already confirming the correct indexed SHA256. Re-running with explicit `byte[]` values confirmed both calibration and prompt index blobs are byte-equal to their sources.
- Pytest emitted the pre-existing permission warning for the ignored root `.pytest_cache`; test results were unaffected.

The complete pytest suite, all DEV-07.02 UI tests, 344-sweep rehearsal, Stage 1–4 full analysis, 1.13 GB matrix, historical golden suite, and Schema consistency were not run. No Schema changed. Final diff/protected-byte/suppression/index/remote checks are performed after documentation is complete and are not pre-claimed here.

## Safety and known limits

No real device was accessed or enumerated, no Stream was opened, and no playback, recording, 94 dB acoustic calibration, or device calibration operation occurred. Absolute SPL is not calibrated and must not be inferred from the -36.2 dB metadata. There is no microphone/device registry, phase calibration, calibration UI, persistent calibrated processing artifact, formal QC threshold, or experiment authorization. Integration with the demo UI remains for DEV-07.04.
