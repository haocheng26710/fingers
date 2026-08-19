# Deterministic virtual capture contract

DEV-03.04 provides the software execution boundary needed before any real audio backend can be considered. Its only executable backend is `VirtualDuplexBackend`; the new modules do not import `sounddevice`, enumerate devices, bind channels, open streams, sleep for audio time, play, or record.

## Authority and safety boundary

The public publisher accepts a validated `LoadedBundle`, `LoadedVirtualCaptureScenario`, validated offline ESS artifact location, existing synthetic session/reassembly IDs, run ID, measurement order, and injected time provider for the outer run record. It has no `DataOrigin`, real-root, waveform, ESS spec, precomputed hash, receipt, latency, gain, device, Host API, or channel parameter. The audio config inside the bundle is the ESS fact source; the source artifact must pass the existing deterministic ESS validator before execution. A `Loaded*` type name is not itself a trust proof. A loaded scenario retains its resolved source path and project root, and the persistence boundary re-establishes the source-bytes-to-model chain: publication and validation re-read that exact in-project file through the safe loader and require the current raw bytes/hash, parsed strict model, canonical normalized bytes/hash, and project-relative reference to match the loaded object. A deleted, moved, externally relocated, modified, or forged source is rejected before execution or staging.

Every persisted receipt fixes synthetic/development/non-formal/non-experimental status and the marker `SYNTHETIC_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT`. It also carries the non-negative `measurement_order` supplied to the run publisher; the outer run record must carry the same value. Hardware I/O, playback, recording, hardware readiness, duplex/clock/channel verification, calibration and absolute SPL fields are all false. The receipt contains no wall-clock time, random UUID, local identity or absolute path. `virtual_duplex_scheduler_exercised=true` is software evidence only and does not imply `full_duplex_verified=true`.

## State machine and block execution

The successful state sequence is exactly:

```text
created -> prepared -> armed -> running -> completed
```

`failed`, `aborted`, and `completed` are terminal. Invalid jumps, repeated completion, completion before the planned sample cursor, and completion with an unhandled backend status raise dedicated errors. Each real transition records a one-based sequence, from/to states, reason, sample cursor, and completed block count. The sample cursor is the deterministic audio clock; no wall-clock value appears in the receipt.

The injected `CaptureBackend` protocol is limited to `prepare`, `arm`, `exchange_block`, `close`, and `abort`, using channel-first `[1,n]` NumPy float32 blocks and explicit frame counts. The virtual backend keeps delay state across block boundaries. For output reference `x` and simulated input `y`:

```text
y[k] = linear_gain * x[k - integer_latency_samples]
```

Out-of-range input is exact zero. Output is the validated ESS followed by `capture_tail_samples` exact zeros. No noise, DC removal, normalization, FFT, deconvolution or acoustic-transfer claim is added.

The nominal development fixture yields 12960 ESS samples, 64 tail samples, 13024 capture samples, 51 actual 256-frame exchanges and a 224-frame last block. Each block trace records sequence, start, requested/output/input counts and status flags; intervals must be consecutive with no gap, overlap or fabricated block.

## Fault handling

The scenario supports `short_input_block`, `dropout`, `clipping`, `backend_error`, and `abort_requested` at an explicit zero-based block index. The index must lie inside the derived block plan. Short input is never padded, status is never ignored, clipped or non-finite input fails, backend exceptions become project errors, and abort remains distinct from failure. Diagnostics retain final state, block, cursor, completed blocks, traces, counters and the original reason. Execution occurs before run publication, so these outcomes create neither `RUN_COMPLETE` nor a completed run directory.

## Immutable payload and validation

A successful run reuses `ImmutableSessionStore.create_synthetic_run` and contains these eight referenced payloads:

```text
excitation.metadata.json
excitation.metadata.sha256
output_reference.wav
output_reference.wav.sha256
simulated_input.wav
simulated_input.wav.sha256
capture_receipt.json
capture_receipt.sha256
```

The outer store also writes `synthetic_metadata.json`, `run_record.json`, and `RUN_COMPLETE`. `synthetic_metadata.json` is an exact canonical four-field envelope derived from the capture receipt digest; changed values, missing or extra fields, and alternate byte serialization are invalid. Neither this envelope nor the run record is accepted as an unverified side-channel fact. All JSON is canonical sorted UTF-8 with LF termination; WAV uses the existing canonical mono IEEE-float32 writer. All payloads have `ArtifactRef` records and sidecars. Publication uses the store's same-session staging and create-only rename; an existing run is never replaced.

The capture validator is read-only. It validates session/run identity and every `ArtifactRef`, requires the exact file set, verifies sidecars and canonical JSON, and compares both the stored manifest and its exact sidecar bytes/digest/filename to the supplied bundle. It validates the source ESS against the loaded audio config, regenerates the ESS, re-executes every virtual block, compares samples and canonical WAV bytes, and rebuilds hashes, traces, counters, and the receipt. Finally it reconstructs the complete expected run envelope: identities, protocol, receipt measurement order, fixed synthetic/development semantics, exact BLK node states, config hashes, artifact references, backend/version/status/null failure/result marker/notes, and the single aware capture timestamp contract. Rehashing modified content does not make it valid.

The existing store publishes a run directory before appending the cross-directory `run_created` event. A post-publication event failure therefore leaves an immutable completed run; the wrapper reports `published=true` and does not delete it. Before publication it reports `published=false` and only store-owned staging is cleaned. This is the actual coordination boundary and is not a claim of absolute multi-file atomicity against non-cooperating filesystem actors.

The injected wall-clock capture time remains only in the outer run record. It is intentionally absent from the deterministic capture payload and is not an audio-device clock, shared-clock observation, latency measurement, or other hardware timing evidence; separate runs may therefore have different outer run-record bytes while all eight capture payloads remain byte-identical.

## Condition-aware development backend

DEV-04.04 adds a separate `deterministic_conditioned_virtual_duplex` scenario and public publisher. It retains the block scheduler, exact run envelope, create-only publication and no-hardware boundary, but replaces the legacy fixed gain/delay response with a causal FIR derived by the existing synthetic generator from the verified manifest and the condition plan's complete resolved node-state map. The scenario contains scheduling/tail controls only; it cannot provide response arrays, thresholds, device selection or hardware authority.

The condition-aware receipt binds the plan and source Stage 1 protocol by repository-relative reference plus raw/normalized SHA256, the condition ID/role, every resolved `NodeState`, manifest-derived node delays and weights, the synthetic IR digest, ESS provenance and all scheduler traces. The run record carries the identical node-state map. Replay reloads the plan from its bound source, revalidates the stored bundle/run and recomputes every payload. All-BLK and single-bridge responses are therefore different because of manifest/module inputs, not hard-coded condition IDs; the result remains synthetic and is not experimental detectability evidence.
