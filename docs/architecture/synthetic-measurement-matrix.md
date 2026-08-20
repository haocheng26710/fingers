# Plan-bound synthetic measurement matrix

DEV-06.01 turns four completed, replay-valid Stage 1–4 development executions into one deterministic offline analysis dataset. It consumes protocol results but never executes a work order, changes an execution ledger, selects a real root or performs hardware I/O.

## Source authority and rows

Each public compute/validate call establishes one process-local validated-source capability per execution. Every source execution must be complete, have no recovery or mutation/staging state, contain exactly the plan-derived sessions/runs, and retain all synthetic/formal/hardware safety flags. The capability is not persisted as reusable authority. Processing then reuses the existing ESS deconvolution, raw/aligned transfer/IR and provisional QC kernels once per row.

The capability also carries each replay-validated execution completion time and completion SHA256. Completion times must be timezone-aware, are normalized to UTC instants and remain in canonical stage order. `analysis_evidence_time` is their maximum; its fixed basis is `latest_verified_execution_completion_utc` and derivation version is `1.0.0`. This is reproducible source evidence time, not the actual publication time or a trusted timestamp. The public compute API has no `now` parameter, so runtime wall-clock time cannot affect persisted bytes.

The complete fixture has 344 rows: Stage 1 152, Stage 2 32, Stage 3 32 and Stage 4 128. Row IDs bind stage, execution, global ordinal and work-order hash. The row index preserves the complete NodeState map/digest, selected-node order and derived state/module/loading labels, plan coordinates, run/capture identities, source hashes, QC metadata and fixed non-experimental state. Stage 2 remains proxy-labelled. Stage 3/4 state vectors come from validated NodeState in plan-selected order; node/module lists are not hard-coded.

## Baselines, arrays and features

A baseline group is exactly `(stage, session_id, reassembly_id)`. Its two all-BLK continuous repeats are the only reference members. Candidate rows use their arithmetic mean; each all-BLK row excludes itself and uses the other repeat. No reference crosses a session, reassembly or stage.

The deterministic NPZ retains raw/aligned complex transfer components, linear magnitude, wrapped and contiguous-unwrapped phase, raw/aligned IR, all-BLK means, additive and stable-ratio differences, magnitude/phase/IR differences and validity masks. `feature_matrix` is finite float64 with the 16 columns declared in `feature_schema.json`; IDs/labels/groups/QC metrics are metadata, not feature columns. No PCA, automatic feature selection or normalization fitting occurs.

## Leakage-resistant splits

Splits are independent per stage. Leave-one-session-out holds out all reassemblies/conditions/repeats of one session. Leave-one-reassembly-out uses the composite stage/session/reassembly identity and keeps every condition/repeat together. The fixture yields 8 session folds and 16 reassembly folds. Each row is test exactly once per strategy; train/test row and group intersections are empty. Fold order is canonical and independent of source enumeration.

## Immutable publication and limits

The exact 15-file envelope is documented in `storage-layout.md`. JSON is canonical, NPZ ZIP metadata is fixed, and payloads contain no absolute temporary roots. Version 1.1 construction is acyclic: verified sources determine time/core/metadata/record; their hashes then determine the receipt and receipt sidecar. The receipt binds metadata and record SHA256, while metadata and record contain no receipt SHA. Publication is create-only under a separate synthetic analysis root.

Validation first checks the exact envelope, fully replays the four sources, derives evidence time from their verified completions, recomputes all 344 rows, 16 features, 24 folds and every expected byte, then compares all 15 files. No metadata, record or receipt field supplies an expected time, path or state. Validation performs no cleanup, recovery or repair; consistent metadata/record changes remain rejectable even if an attacker also recomputes receipt hashes and its sidecar. Old 1.0 envelopes are rejected and must be regenerated rather than migrated in place.

Receipt state is `provisional_measurement_matrix_only`, `not_evaluated`, zero excluded rows and `SYNTHETIC_MEASUREMENT_MATRIX_NOT_AN_EXPERIMENTAL_RESULT`. Hashes are internal replay-integrity evidence, not digital signatures, external witnesses or trusted timestamps. Feature extraction being true means only that deterministic development columns were generated. No model fit, prediction, classification, interaction analysis, threshold, formal QC decision, physical significance, separability claim or experimental conclusion is implemented. No device enumeration, stream, playback, recording, calibration or SPL verification occurs. DEV-06.02 is not implemented.
