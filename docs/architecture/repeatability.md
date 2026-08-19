# Synthetic provisional repeatability contract

DEV-04.03 compares a continuous set of already published synthetic captures. It supports only members from one session and one reassembly with distinct, consecutive `measurement_order` values. It does not bind protocol conditions, assign BLK or any other baseline, calculate a baseline difference, apply a threshold, issue pass/fail or drift decisions, use calibration/SPL, perform hardware audio I/O, or create an experimental result.

## Authority and provenance

The public publisher and validator accept an injected store, the original validated bundle/scenario/ESS source, a session ID, repeat-set ID, and repeated `(source_run_id, processing_id, qc_id)` identities. They accept no waveform, array, arbitrary WAV/NPZ or output path, precomputed metric, caller measurement order/reassembly, condition, baseline role, truth, threshold, decision, real root, device, channel, Host API or calibration input.

For every identity, the implementation calls the existing virtual-capture, ESS-processing and provisional-QC replay validators. It then reads only the validated captured-input WAV and canonical processing NPZ. Reassembly and measurement order come from the capture receipt; latency comes from the processing receipt. Members must share bundle/device hashes, AudioConfig and AnalysisConfig provenance, virtual scenario, ESS source, processing/QC versions, sample/timing/FFT/IR dimensions and exact analysis-band mask. Input order is ignored and canonical order is derived from consecutive measurement orders. A source run may occur only once.

The receipt binds every normalized member identity and its capture/processing/arrays/QC hashes, the common provenance, dimensions and mask digest, the repeatability metrics digest, fixed algorithm/formula identifiers and strict safety states. Its member-list digest is recomputed from the canonical normalized provenance list. DEV-04.03R receipt and repeatability algorithm versions are `1.1.0`; processing remains `1.1.0`, provisional QC remains `1.0.0`, and the unchanged repeatability metrics schema remains `1.0.0`.

The `1.1.0` state contract is explicit and strict: `decision_status` is the generic processing-pipeline decision state, while `repeatability_decision` is this layer's explicit repeatability-decision state; both are currently fixed to `not_evaluated` and cannot diverge. Baseline is not assigned, its role is `not_assigned`, and selection is `deferred_until_protocol_binding`; no baseline difference or protocol-condition binding was performed; drift is not evaluated and has no decision; thresholds were not applied and their value/source are null. The same constructor supplies receipt, record and metadata state, so the three immutable representations cannot silently diverge. Old `1.0.0` repeatability artifacts are rejected by the new validator and must be regenerated.

Before loading members or creating any repeatability parent, staging directory or lock, both public paths require the active AnalysisConfig model to match its loaded normalized provenance and require `baseline_selection_rule`, `qc_threshold`, `effect_threshold`, `drift_threshold` and `classification_pass_threshold` all to be null. This is an authority boundary, not an implementation of selection or decision logic.

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

CLI structured state is rendered from the published or replay-validated receipt. Safety markers summarize those same receipt literals; CLI `PASS` means only software publication/validation success and never repeatability, QC, drift or experimental success.

The envelope and event provide project-internal integrity and audit binding only. They have no digital signature, external witness or trusted timestamp and do not claim resistance to coordinated rewriting of every mutually bound file or to every concurrent TOCTOU actor.

## Condition-aware extension and baseline-difference layer

Condition-aware captures pass through the existing processing and QC algorithms unchanged. Repeatability still uses `provisional_continuous_repeatability_metrics` version `1.1.0`; only its provenance envelope is versioned to condition-aware receipt `1.2.0`. That receipt adds condition-plan and Stage 1 protocol hashes, condition ID/role, the complete resolved node-state map and digest, and the verified non-BLK count. Members must share the same condition, reassembly, plan, protocol, scenario, bundle, ESS, processing/QC versions and continuous measurement order. The legacy `1.1.0` receipt bytes and validation path remain unchanged.

Source repeatability remains no-baseline, no-threshold and no-drift-decision evidence. Baseline assignment occurs only in the separate baseline-difference layer after two condition-aware repeat sets have both passed full replay. Their roles are derived from receipts: exactly one source must be an all-BLK reference and exactly one a single-bridge candidate, on different reassemblies with no shared run.

For raw and aligned complex transfer separately, the comparison stores arithmetic means `B` and `C`, additive difference `C-B`, stable ratio `C/B`, magnitude-dB difference, wrapped phase difference and phase unwrapped independently within each contiguous valid segment. Division-invalid ratio/phase values are zero with explicit bool masks. Raw and aligned IR means and differences are also stored. All persisted numeric arrays are finite canonical float64; masks are bool. Continuous L2/RMS/peak metrics use explicit null statuses for zero denominators. No smoothing, feature extraction, threshold, effect/classification/drift decision or experimental claim is made.
