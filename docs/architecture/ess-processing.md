# Synthetic offline ESS processing contract

DEV-04.01/DEV-04.01R/DEV-04.01R2 process only an already completed, semantically replay-validated DEV-03.04 virtual capture. It is a development software fixture, not a formal experiment, acoustic measurement, hardware timing observation, calibration result, or playback/recording action. Every receipt fixes `data_origin=synthetic`, `run_mode=development`, `formal_eligible=false`, `experimental_result=false`, `hardware_io_performed=false`, and `SYNTHETIC_OFFLINE_ESS_PROCESSING_NOT_AN_EXPERIMENTAL_RESULT`.

## Authority boundary

`publish_ess_processing` accepts an injected `ImmutableSessionStore`, `LoadedBundle`, `LoadedVirtualCaptureScenario`, ESS artifact root, session/source-run/processing identifiers, and an outer record clock. Its first semantic operation is `validate_virtual_capture`, which re-establishes the session, run, bundle, scenario source, ESS, WAV, receipt and run-envelope chain. The processing API accepts no array, waveform path, expected latency/gain, precomputed inverse/IR/transfer/hash/receipt, `DataOrigin`, real root, device, Host API, channel, calibration or hardware readiness parameter.

After source validation, the implementation reads canonical output-reference/input WAVs, revalidates the ESS artifact, proves the output starts with that ESS, and derives sweep frequencies/sample timing from ESS metadata. Analysis limits and disabled smoothing come only from the loaded AnalysisConfig. The nominal scenario's declared `integer_latency_samples` and `linear_gain` are not mathematical inputs or copied truth fields in the processing receipt.

## Mathematics

All calculations use finite C-contiguous float64 arrays. Shared pre-silence is removed before processing. For an active sweep `s` of length `N` and `R=ln(f_end/f_start)`, the unnormalized inverse is:

```text
q0[n] = s[N-1-n] * exp(-R*n/N)
```

Every convolution is full linear convolution implemented with an `rfft/irfft` length equal to the next power of two at least as long as the full result, then cropped to the exact linear length. The unique maximum-absolute reference-deconvolution sample must be finite and nonzero. The inverse is scaled by its signed reference peak so that the same peak becomes positive one; the receipt records the pre-peak, signed factor, post-peak, index, lengths and FFT method.

Latency uses normalized matched correlation of the complete active sweep against every full-overlap window of input-after-pre-silence. Partial-overlap lags are excluded; a non-finite, zero, or tied absolute maximum is rejected. Positive lag means the captured input follows the output. The signed correlation coefficient is retained.

Full reference and input deconvolutions are preserved with sample/second axes relative to the reference peak. `ir_raw` begins at the reference peak and remains unchanged. `ir_aligned` advances by measured latency using zero fill, never `np.roll` or circular wrap. The dominant raw-IR peak index/value is reported from the computed waveform.

Raw and aligned transfer functions use a common power-of-two `rfft` length. Raw transfer is the complex spectral ratio of input-after-pre-silence to output-after-pre-silence. Aligned transfer uses the same denominator and a captured input advanced by measured latency with zero fill. Spectral division is performed only where the reference spectrum exceeds the float64 roundoff threshold `max(abs(reference_spectrum)) * eps * reference_sample_count`; other bins are zero, and the configured analysis band must retain the ESS energy needed by its oracle. This ratio makes an identity capture unity magnitude and zero phase instead of retaining the finite ESS inverse's sidelobe response. It does not alter the inverse, full deconvolutions, raw IR, or aligned IR.

The processing receipt schema and processing algorithm versions are both `1.1.0`. Strict required literals identify the estimator as `complex_spectral_ratio`, spell out the raw and zero-fill-aligned `rfft(input)/rfft(output)` definitions, record the exact float64 threshold formula, and state that bins at or below that threshold are zero. These are processing-receipt versions only: the ESS excitation algorithm and processing event/record schemas remain `1.0.0`.

The archive stores real/imaginary transfer components, linear/dB magnitudes, wrapped/unwrapped radians, frequency, and the inclusive AnalysisConfig band mask. dB uses `max(magnitude, np.finfo(np.float64).tiny)` before `20*log10`; no smoothing is applied.

## Deterministic arrays and immutable publication

The deterministic NPZ writer is shared with the older synthetic generator. It sorts array names, uses `.npy` with `allow_pickle=false`, fixed 1980 ZIP timestamps, stored compression and fixed file mode. Object arrays, unsafe names, non-contiguous arrays and non-finite float/complex arrays are rejected. The 21-array contract includes inverse/reference/input deconvolution, relative axes, raw/aligned IRs, frequency, raw/aligned complex transfer components, magnitudes, phases and analysis mask. IR/transfer quantities are channel-first `[1,1,n]`; frequency/mask are `[n]`; only relative samples are int64 and the mask is bool.

Publication is create-only under `processed/run_<source_run_id>/processing_<processing_id>/`. It writes deterministic arrays and receipt with SHA256 sidecars, a fixed canonical metadata envelope, an outer timestamped processing record, and completion marker through same-session staging. Existing targets or publication races fail without replacement. The outer record time is deliberately excluded from cross-root deterministic payload claims.

After the seven-file directory is published, the publisher appends one root-confined `processing_created` session event. Its strict canonical envelope binds the session, source run, processing ID, record creation time, SHA256 of the actual canonical `processing_record.json` bytes, and processing receipt SHA256. If event append fails, the immutable processing remains published and the caller receives `EssProcessingPersistenceError` with `published=true`; the operation is not reported as an overall success.

## Read-only replay validation

`validate_ess_processing` first revalidates the source virtual capture, then requires the exact processing file set, exact byte-canonical sidecars, canonical JSON, and exact `PROCESSING_COMPLETE == b"complete\n"`. It rereads source WAV/ESS/config facts, recomputes all mathematics and all 21 arrays, rebuilds descriptors, NPZ bytes, receipt and metadata, and compares them byte-for-byte.

The validator also requires exactly one `processing_created` event matching the session-local composite identity `(source_run_id, processing_id)`. The same processing ID may therefore occur under different source runs, while duplicate events for the same composite identity remain invalid. It strictly validates canonical JSON, filename/JSON sequence, event/session/origin identity, payload fields, record hash, receipt hash and event time. The independently stored event time supplies the expected `ProcessingRecord.created_at`; the record is not allowed to validate its own time. Missing, duplicate, malformed, noncanonical or mismatched events are rejected. Legacy DEV-04.01 processing without this event, and receipts before schema/algorithm `1.1.0`, must be regenerated. Validation never repairs, rewrites or removes a failed artifact.

This event provides project-internal integrity and audit binding only. Because the event and processing files have no digital signature, external append-only witness, trusted timestamp or external read-only log, coordinated modification of all bound files by a malicious actor is outside the claim. This contract is not cryptographic authenticity or cryptographic immutability.

For the nominal development fixture, tests assert waveform-derived latency `37` samples, raw-IR dominant index `37`, and dominant value within `1e-6` of `0.5`. These values are fixture oracles in tests/reports only, not algorithm inputs, production constants, measurements, or hearing-safety guidance.
