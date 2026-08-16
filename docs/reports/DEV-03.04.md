# DEV-03.04 completion report

## Outcome

- Software implementation: **PASS**
- Baseline: `fcaf4f7bbac2778c21888d8e8bc4676b2350e926`
- Original suite retained: `277` tests
- DEV-03.04 regression tests added: `64`
- Full suite: `341 passed in 9.11s`
- Generated Schema count: `17`
- Hardware enumeration, playback, recording, and stream opening: **none**
- `hardware_ready=false`, `full_duplex_verified=false`, `shared_clock_verified=false`, `channel_mapping_verified=false`

Before modification, branch `main`, local HEAD, `origin/main`, and GitHub `main` all matched the baseline; the worktree was clean, the origin URL was correct, and no project-level instruction file was present. The original CRLF prompt was copied byte-for-byte and marked binary; source/archive SHA256 is `b8eb1acef887592402cf6b21ccfcce75be5c589aa6ef3736745ac4db42cb68cd`.

Git submission is intentionally pending in this committed report because a commit cannot contain its own final SHA. The final task response and remote Git history provide the actual commit/push result.

## Implementation and authority boundary

The implementation adds strict `VirtualCaptureScenario`/`VirtualCaptureReceipt` models, a provenance-carrying `LoadedVirtualCaptureScenario`, an explicit `CaptureStateMachine`, a narrow injected `CaptureBackend` protocol, the only executable `VirtualDuplexBackend`, a block-wise `VirtualCaptureEngine`, synthetic-only publication, and a read-only capture-specific semantic validator.

The public publisher accepts `LoadedBundle`, the loaded scenario, a validated ESS artifact root, synthetic identifiers, measurement order, and an outer run-record clock. It does not accept `DataOrigin`, a real root, ESS spec, waveform, separate hashes, receipt fields, latency, gain, device, Host API, or channel. It validates the stored session bundle against the supplied bundle before execution, derives ESS facts from the bundle audio config, and calls the existing ESS validator.

Successful publication reuses `ImmutableSessionStore.create_synthetic_run`, `MeasurementRunRecord`, `ArtifactRef`, same-session staging, create-only publication, synthetic/real separation, canonical JSON, SHA256 sidecars, and the existing canonical IEEE-float32 WAV codec. The eight referenced payloads are copied ESS metadata and sidecar, output-reference WAV and sidecar, simulated-input WAV and sidecar, and capture receipt and sidecar. Failure or abort occurs before publication and leaves no run or staging directory.

The validator checks the exact file set, session/run/reassembly identity, every ArtifactRef, all sidecars, canonical receipt bytes, stored manifest/config snapshots, full bundle hashes, scenario hashes, source ESS metadata/config identity, decoded WAVs, raw hashes, run record fields, and all safety flags. It regenerates the ESS and re-executes every block, then compares samples, canonical WAV bytes, block/state traces, counters, and the complete derived receipt. A regression modifies a WAV, recomputes its sidecar, and updates both affected ArtifactRefs; semantic replay still rejects it.

## State machine, scenario, and execution

The successful state order is exactly `created -> prepared -> armed -> running -> completed`; each transition has a continuous one-based sequence, reason, sample cursor, and completed-block count. `failed`, `aborted`, and `completed` are terminal. Tests cover every declared failed/aborted source state, invalid jumps, repeated completion, early completion, unhandled status, and backwards cursor.

The nominal fixture is strict, development-only, non-formal and non-experimental:

- Scenario raw SHA256: `74eefa7181d739272726fd59472ae0cd766ec7a8a9391b9a566f0031d6a81ab2`
- Scenario normalized SHA256: `cd5b82148d5fb88ea1fd86737510504030bca219ebe61de018b0f0b00bf90dbe`
- Block size: `256` frames
- Integer delay: `37` samples
- Capture tail: `64` samples
- Linear gain: `0.5`
- Relation: `y[k] = 0.5 * x[k-37]`, with out-of-range samples equal to zero

The engine performs actual block exchanges; it does not create a whole input array and fabricate a trace. It supports `short_input_block`, `dropout`, `clipping`, `backend_error`, and `abort_requested`, validates the zero-based fault block against the derived plan, converts backend errors to project diagnostics, and separately rejects non-finite input. Short input is not padded and status is not ignored.

## Deterministic software demonstration

The required CLI workflow ran twice from two exact, prechecked-absent system temporary roots: generate/validate development ESS, create synthetic session, simulate capture, validate capture, revalidate session, and validate run. Both roots were then individually removed after verifying their resolved parent was the system temporary directory; both were confirmed absent.

- Final state/origin/mode: `completed / synthetic / development`
- ESS/capture samples: `12960 / 13024`
- Planned/actual blocks: `51 / 51`
- Last block: `224` frames
- Output/input: `[1,13024] float32`, C-contiguous and finite
- Integer delay/gain: `37 / 0.5`
- Output raw float32 SHA256: `51531aedf7b6d253085315bf2ffd1efc7c760de363bc68565756ed5b2c2b3621`
- Input raw float32 SHA256: `284c6bd0d320dfd0d1a97015d80e0bcc6aff3b49d9a2befbe68e55b5ef550b81`
- Output WAV SHA256: `1aea497f8868d1f2e187b2ed1f80efd7b05e4c0a6084f1901dcc425180bdb508`
- Simulated-input WAV SHA256: `51d68378a916f82e9080cba276c8c5dfb386ffd19f4fb3c0b3dd9e9d594222b1`
- Capture receipt SHA256: `a58351bc1efc50cb40263f78949f923d5358c90f701e1b63f4b33281cba80480`
- `formal_eligible=false`, `experimental_result=false`, `hardware_io_performed=false`, `playback_performed=false`, `recording_performed=false`, `hardware_ready=false`
- Cleanup: ESS root absent; synthetic root absent

A separate formal-config negative created a session whose stored bundle used `config/audio/default_1x1_ess.yaml`, then attempted capture with the validated development ESS source. It exited nonzero with `published=false`, listed `ess_duration_s`, `pre_silence_s`, `post_silence_s`, `ess_fade_in_s`, `ess_fade_out_s`, and `ess_digital_peak_dbfs`, created no run, supplied no defaults, and cleaned its exact temporary roots.

## Tests and static verification

The first TDD run contained only the nominal scenario loader test and failed during collection with `ModuleNotFoundError: acoustic_ladder.audio.virtual_capture_models`; implementation was added only after that RED evidence. Subsequent slices covered scenario, state machine, engine/faults, immutable persistence/semantic tampering, and CLI.

- DEV-01: `43 passed in 0.60s`
- DEV-02.01: `66 passed in 1.72s`
- DEV-02.02: `23 passed in 1.84s`
- DEV-03.01: `36 passed in 0.46s`
- DEV-03.02: `24 passed in 0.54s`
- DEV-03.03/03.03R: `85 passed in 1.38s`
- DEV-03.04: `64 passed in 3.30s`
- Full suite: `341 passed in 9.11s`
- Frozen dependency sync: `Checked 29 packages`
- Ruff format: `89 files already formatted`
- Ruff lint: PASS
- strict mypy: `Success: no issues found in 60 source files`
- Schema consistency: PASS; `17` model-generated schemas
- `git diff --check`: PASS
- skip/xfail/noqa/type-ignore scan: no source/test matches
- U+FFFD scan on corrected surfaces: no matches
- forbidden-audio AST regression and direct new-source text scan: PASS
- tracked WAV/FLAC/NPY/NPZ: none
- staging/publication-lock/cache/virtual-environment worktree status: none
- implementation-log baseline prefix and protected baseline diff: PASS

The first broad local-identity scan reported a pre-existing adversarial Windows private-path string in `tests/dev03/test_inventory.py`. This is a deliberate privacy-rejection fixture, not persisted output or a current-machine identity. A targeted scan of every DEV-03.04 source/test/document surface found no local path, username, or identity.

## Protected hashes

- ZIP: `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- Manifest: `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- Inventory: `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- Capture context: `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- Summary: `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- Contextual preflight: `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- Hardware setup: `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`
- ESS golden WAV: `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- ESS golden metadata: `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- ESS golden raw float32: `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

## Files and limitations

New files are the four `virtual_capture*` modules, nominal scenario fixture, DEV-03.04 test module, two generated schemas, architecture document, prompt archive, and this report. Modified files are `.gitattributes`, `README.md`, `data/README.md`, CLI, schema registry, the prior schema-count assertion, and the append-only implementation log. Protected audio/config/model/history inputs are unchanged.

No real hardware, inventory, device, Host API, channel, stream, playback, recording, calibration file, SPL, loopback, real latency/clock, inverse filter, deconvolution, DSP, formal protocol, CAD, DEV-03.05, or DEV-04 work was accessed or performed. The virtual latency/gain are fixture values, not acoustic measurements or safety guidance. Output-reference WAV is scheduled software output, not playback evidence; simulated-input WAV is software output, not microphone audio.

The existing store publishes the immutable run directory before appending the cross-directory `run_created` event. If that later event append fails, the wrapper truthfully reports `published=true` and does not delete the published run. Before publication it reports `published=false` and only owned staging is cleaned. This is not an absolute multi-file atomicity claim against non-cooperating filesystem actors.

本步骤只完成确定性虚拟采集执行内核。`virtual_duplex_scheduler_exercised=true` 不等于 `full_duplex_verified=true`。没有连接、枚举、播放、录制或验证任何真实音频硬件。
