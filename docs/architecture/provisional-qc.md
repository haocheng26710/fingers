# Synthetic provisional offline QC contract

DEV-04.02 adds deterministic quality evidence for an already completed and replay-valid synthetic ESS processing artifact. It does not evaluate a formal threshold, emit pass/fail, certify hardware, use calibration, perform audio I/O, or create an experimental result. Every receipt fixes `metric_computation_status=complete`, `evaluation_status=provisional_metrics_only`, `decision_status=not_evaluated`, `thresholds_applied=false`, `qc_threshold=null`, `threshold_source=null`, all hardware/calibration/formal/experimental flags false, and `SYNTHETIC_PROVISIONAL_QC_METRICS_NOT_AN_EXPERIMENTAL_RESULT`.

## Authority and provenance

`publish_provisional_qc` accepts an injected store, validated bundle and scenario, ESS artifact root, session/source-run/processing/QC identifiers, and an outer record clock. Its first provenance gate is `validate_ess_processing`, which transitively revalidates the source virtual capture and ESS and recomputes every processing array. Only then does QC load the validated capture WAVs and canonical processing NPZ. The API has no waveform, array, metrics, expected latency/gain, threshold, decision, arbitrary output path, real root, device, channel or calibration parameter. A non-null AnalysisConfig `qc_threshold` is rejected.

The receipt binds all four identities; source capture receipt, processing receipt and processing-array hashes; processing schema/algorithm versions; bundle and device-manifest hashes; AnalysisConfig reference/raw/normalized hashes; QC metrics hash; algorithm and formula identifiers; state literals; create-only/immutable flags; and safety flags. Metrics and receipt schemas and the QC algorithm are version `1.0.0`.

## Fixed metrics

Waveforms are finite mono `[1,N]` arrays converted to float64. Output reference and captured input each record full count, absolute peak, full RMS, active-sweep RMS, optional pre-silence RMS, and digital-boundary clip count/fraction where `abs(sample) >= 1.0`. Active and pre slices come only from validated processing timing. An absent pre-silence has null RMS with `pre_silence_absent`.

The input pre-silence SNR proxy is `20*log10(active_sweep_rms/pre_silence_rms)` only when both operands are positive. Otherwise the value is null with exactly one of `pre_silence_absent`, `zero_pre_silence_rms`, or `zero_active_sweep_rms`; no epsilon or infinity is invented. This is a normalized development proxy, not formal acoustic SNR.

Latency samples/seconds and signed/absolute correlation come from the replay-validated processing receipt and are cross-checked through the processing replay. From `ir_raw[0,0,:]`, QC verifies the receipt's dominant index/value, removes that index, and reports the second-largest absolute sample and optional dominant/second ratio. A one-sample IR or zero second peak produces a null ratio with a fixed reason. From `reference_deconvolution`, it removes the unique absolute peak and reports off-peak RMS plus an optional peak/RMS ratio, again using fixed null reasons for no samples or a zero denominator.

Spectral coverage recomputes `rfft(output_after_pre, n=transfer_fft_length)` and the processing formula `max(abs(reference_spectrum))*float64_epsilon*reference_sample_count`. A bin is valid only when its magnitude is strictly above that threshold. Counts and fractions are restricted to the stored analysis-band mask; an empty band is rejected. Raw/aligned complex transfer finite counts require both real and imaginary parts finite in-band. Strict model validators tie every optional value to its status and every fraction to its counts; JSON cannot contain NaN or infinity.

## Immutable publication and read-only validation

The store derives `qc/run_<source_run_id>/processing_<processing_id>/qc_<qc_id>/` under the injected synthetic session. Publication is create-only, uses a same-filesystem staging directory and cooperative lock, and produces exactly seven files: canonical metrics and receipt with strict SHA256 sidecars, fixed metadata, an outer timestamped record, and exact `QC_COMPLETE == b"complete\n"`. Timestamped record/event bytes are excluded from deterministic cross-root payload claims.

After directory publication, one root-confined `qc_created` event binds `(source_run_id, processing_id, qc_id)`, creation time, and canonical record/metrics/receipt hashes. The same QC ID may be reused under a different source-run or processing identity; the exact composite may not be duplicated. Event failure reports `published=true` and does not delete the completed immutable directory.

`validate_provisional_qc` is read-only. It revalidates processing, recomputes metrics, rebuilds receipt/metadata/record expectations, requires the exact file set, canonical JSON, strict sidecars and completion bytes, and requires exactly one strict canonical matching event. Missing, extra, malformed, old-version, noncanonical, hash-mismatched, state-inconsistent or replay-different content is rejected without repair.

The envelope and session event provide project-internal integrity and audit binding only. They have no digital signature, external append-only witness or trusted timestamp, so coordinated rewriting of every mutually bound file by a malicious actor is outside the claim.
