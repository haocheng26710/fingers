# Synthetic provisional repeatability contract

DEV-04.03 compares a continuous set of already published synthetic captures. It supports only members from one session and one reassembly with distinct, consecutive `measurement_order` values. It does not bind protocol conditions, assign BLK or any other baseline, calculate a baseline difference, apply a threshold, issue pass/fail or drift decisions, use calibration/SPL, perform hardware audio I/O, or create an experimental result.

## Authority and provenance

The public publisher and validator accept an injected store, the original validated bundle/scenario/ESS source, a session ID, repeat-set ID, and repeated `(source_run_id, processing_id, qc_id)` identities. They accept no waveform, array, arbitrary WAV/NPZ or output path, precomputed metric, caller measurement order/reassembly, condition, baseline role, truth, threshold, decision, real root, device, channel, Host API or calibration input.

For every identity, the implementation calls the existing virtual-capture, ESS-processing and provisional-QC replay validators. It then reads only the validated captured-input WAV and canonical processing NPZ. Reassembly and measurement order come from the capture receipt; latency comes from the processing receipt. Members must share bundle/device hashes, AudioConfig and AnalysisConfig provenance, virtual scenario, ESS source, processing/QC versions, sample/timing/FFT/IR dimensions and exact analysis-band mask. Input order is ignored and canonical order is derived from consecutive measurement orders. A source run may occur only once.

The receipt binds every normalized member identity and its capture/processing/arrays/QC hashes, the common provenance, dimensions and mask digest, the repeatability metrics digest, fixed algorithm/formula identifiers and strict safety states. Its member-list digest is recomputed from the canonical normalized provenance list. Schema and repeatability algorithm versions are `1.0.0`; processing remains `1.1.0`, and provisional QC remains `1.0.0`.

## Pair mathematics

All inputs are normalized to contiguous float64/complex128 and checked for shape, finite values and a non-empty common analysis band. Every unique unordered pair is emitted in measurement order, so `pair_count = n*(n-1)/2`.

- Captured-input and aligned-IR correlation use a normalized dot product without epsilon. A zero norm yields null plus a fixed left/right/both reason.
- Signed latency is `latency_j-latency_i`; the absolute delta and member/pair aggregates are recorded.
- IR symmetric NRMSE and in-band complex-transfer relative L2 divide the difference norm by the root-mean-square of the two operand norms. A zero symmetric denominator yields null plus a fixed reason.
- Magnitude RMSE uses `20*log10(max(abs(H), numpy.finfo(float64).tiny))`.
- Phase RMS uses `angle(H_i*conjugate(H_j))` only where both magnitudes are nonzero. Zero valid bins yield null plus a fixed reason; there is no smoothing or new unwrap.

Pair counts, phase fractions and all defined counts/min/mean/max aggregates are cross-validated by strict models. These numbers are representation and repeatability evidence only, not SPL, safety or acceptance criteria.

## Immutable publication and validation

The store derives `qc/repeat_sets/reassembly_<reassembly_id>/repeat_set_<repeat_set_id>/` under the injected synthetic session. Same-filesystem staging, a cooperative create-only lock and final rename publish exactly seven files: canonical metrics and receipt plus strict sidecars, fixed metadata, an outer record and exact `REPEATABILITY_COMPLETE == b"complete\n"`.

After publication, one canonical `repeatability_created` event binds `(reassembly_id, repeat_set_id)`, creation time, record/metrics/receipt hashes and normalized member-list hash. Different reassemblies may reuse a repeat-set ID; matching always uses the composite identity. Event failure leaves the completed directory and reports `published=true`.

Validation is read-only. It replays every member, recomputes every pair and aggregate, rebuilds deterministic payloads, requires the exact file set/canonical JSON/sidecars/completion bytes, derives the record time from exactly one matching event, and never repairs failed data.

The envelope and event provide project-internal integrity and audit binding only. They have no digital signature, external witness or trusted timestamp and do not claim resistance to coordinated rewriting of every mutually bound file or to every concurrent TOCTOU actor.
