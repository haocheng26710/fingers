# DEV-03.01 completion report

## Outcome

- Software implementation: **PASS**
- Actual read-only inventory capture: **PASS**
- Device binding, after DEV-03.02 context correction: `deferred_until_hardware_connection`
- `hardware_ready`: `false`
- Playback, recording or stream opening: **none**

> **DEV-03.02 correction:** The operator later confirmed that the iMM-6C, CHU II and experimental fixture were all disconnected during this capture. The inventory is therefore a `development_host_baseline_without_experimental_hardware`. None of its device indices represents or may be bound to experimental hardware. The original inventory bytes, hash, format checks and read-only capture facts remain valid. See the [capture context](../../reference/audio/inventory/DEV-03.02_inventory_capture_context.json) and the [model-generated inventory summary](../../reference/audio/inventory/DEV-03.02_audio_inventory_summary.md).

The implementation is based on `3e075956727fcbfe2c0b57588cbef6ee34440136`. Before modification, local `main`, local `origin/main` and GitHub `main` matched that commit, the origin URL was correct, the worktree was clean and no project instruction file was present.

## Implemented boundary

The new `acoustic_ladder.audio` package contains strict Pydantic hardware/inventory/preflight models, an injectable inventory protocol, lazy `SoundDeviceInventoryBackend`, deterministic `FakeInventoryBackend`, normalization, conservative preflight and create-only canonical JSON/sidecar persistence. The production adapter calls only version queries, `query_hostapis`, `query_devices`, `check_input_settings` and `check_output_settings`.

Audio configuration now references the provisional hardware setup and actual inventory while preserving null backend/device/candidate/channel selections, formal 1+1, `config_status=draft` and `hardware_ready=false`. Three generated schemas were added; all eleven generated schemas matched their models at DEV-03.01 completion.

The committed hardware setup records the user-confirmed MOONDROP CHU II / 竹 2 and Dayton Audio iMM-6C facts. Calibration-file reference/digest remain null, calibration is not applied, no acoustic calibrator is available, absolute SPL is not calibrated, electrical loopback is unavailable and the exact connection remains pending confirmation. Manufacturer sources are descriptive only and are not treated as measurements.

## Actual inventory

Capture time: `2026-08-16T16:49:47.574426Z`.

- Python: `3.12.4`
- sounddevice: `0.5.5`
- PortAudio: `1246976`, `PortAudio V19.7.0-devel, revision unknown`
- Host APIs: `0 MME` (5 devices), `1 Windows DirectSound` (5), `2 Windows WASAPI` (3), `3 Windows WDM-KS` (11)
- Default input snapshot index: `1`
- Default output snapshot index: `3`
- Inventory SHA256: `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

The inventory JSON is authoritative for device names and contains correct UTF-8 Chinese. Name corruption occurred after inventory construction in the console-output, decoding or manual-transcription path; available evidence does not identify the exact terminal, code-page or tool layer. It was inaccurate to attribute the corrupted report text to sounddevice. The table below is corrected from the verified inventory model; the generated summary is the maintained source for the complete device table.

| Index | Host API | Device name | I/O | 48k |
|---:|---|---|---:|---|
| 0 | MME | Microsoft 声音映射器 - Input | 2/0 | input PASS |
| 1 | MME | 阵列麦克风 (AMD Audio Device) | 2/0 | input PASS |
| 2 | MME | Microsoft 声音映射器 - Output | 0/2 | output PASS |
| 3 | MME | 耳机 (Senary Audio) | 0/6 | output PASS |
| 4 | MME | 扬声器 (Senary Audio) | 0/6 | output PASS |
| 5 | Windows DirectSound | 主声音捕获驱动程序 | 2/0 | input PASS |
| 6 | Windows DirectSound | 阵列麦克风 (AMD Audio Device) | 2/0 | input PASS |
| 7 | Windows DirectSound | 主声音驱动程序 | 0/2 | output PASS |
| 8 | Windows DirectSound | 耳机 (Senary Audio) | 0/6 | output PASS |
| 9 | Windows DirectSound | 扬声器 (Senary Audio) | 0/6 | output PASS |
| 10 | Windows WASAPI | 扬声器 (Senary Audio) | 0/2 | output PASS |
| 11 | Windows WASAPI | 耳机 (Senary Audio) | 0/2 | output PASS |
| 12 | Windows WASAPI | 阵列麦克风 (AMD Audio Device) | 2/0 | input PASS |
| 13 | Windows WDM-KS | Output 1 (Senary Audio headphone) | 0/2 | output PASS |
| 14 | Windows WDM-KS | Output 2 (Senary Audio headphone) | 0/6 | output PASS |
| 15 | Windows WDM-KS | Input (Senary Audio headphone) | 2/0 | input PASS |
| 16 | Windows WDM-KS | Output 1 (Senary Audio output) | 0/2 | output PASS |
| 17 | Windows WDM-KS | Output 2 (Senary Audio output) | 0/6 | output PASS |
| 18 | Windows WDM-KS | Input (Senary Audio output) | 2/0 | input PASS |
| 19 | Windows WDM-KS | 麦克风 (Senary Audio capture) | 2/0 | input PASS |
| 20 | Windows WDM-KS | 阵列麦克风 (AMDAfdInstall Wave Microphone - 0) | 2/0 | input PASS |
| 21 | Windows WDM-KS | 耳机 (`bthhfenum` Hands-Free; redacted user-defined suffix) | 0/1 | output FAIL: `PortAudioError -9997` |
| 22 | Windows WDM-KS | 耳机 (`bthhfenum` Hands-Free; redacted user-defined suffix) | 1/0 | input FAIL: `PortAudioError -9997` |
| 23 | Windows WDM-KS | 耳机 () | 0/2 | output FAIL: `PortAudioError -9997` |

Twenty-one separate directional checks passed and three returned `Invalid sample rate [PaErrorCode -9997]`. These checks do not establish simultaneous duplex operation.

Because the experimental hardware was disconnected, candidate matching is not applicable. Senary Audio, AMD, Bluetooth and every other captured endpoint are development-host endpoints, not experimental candidates. No current index, Host API or channel requires operator selection. Binding is deferred until the complete experimental hardware is connected and a new inventory is captured.

## Failures encountered and corrected

- The first dependency commands using uv's default user cache failed because that cache path could not be initialized. Workspace `.uv-cache` was used thereafter.
- The first sandboxed lock/sync attempt could not reach the package index. The approved network retry locked and installed sounddevice `0.5.5`, cffi `2.1.1` and pycparser `3.0`.
- Early Ruff/mypy checks found import order, a modern generic declaration and one Literal inference issue; these were corrected without suppression.
- The first DEV-03 suite run was `31 passed, 2 failed`: strict Python validation rejected serialized datetime strings. Loading was changed to Pydantic's JSON validation path; the suite then passed.
- The first real `audio-list` reached device 21 but aborted because an expected unsupported-format `PortAudioError` was classified as an infrastructure failure. A regression test was added and format-check exceptions are now persisted as `supported=false` with type/message. Full software gates were rerun before the successful capture.

## Verification

- DEV-01 tests: `43 passed in 0.61s`
- DEV-02.01 tests: `66 passed in 1.39s`
- DEV-02.02 tests: `23 passed in 1.86s`
- New DEV-03.01 tests: `36 passed in 0.33s`
- Full suite: `168 passed in 3.67s`
- Ruff format: `66 files already formatted`
- Ruff lint: PASS
- strict mypy: `Success: no issues found in 48 source files`
- Schema consistency: PASS, 11 generated schemas
- `git diff --check`: PASS
- skip/xfail/noqa/type-ignore scan: no matches
- forbidden audio-call AST scan: no matches
- synthetic session → run → validate-session → validate-run smoke: PASS; verified workspace-local temporary tree removed
- actual inventory sidecar and preflight validation: PASS
- protected-file diff: no changes
- protected ZIP SHA256: `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- protected manifest SHA256: `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

Commands actually used are recorded in `docs/IMPLEMENTATION_LOG.md`. No required DEV-03.01 acceptance check was omitted. Prohibited playback, recording, stream opening, ESS generation, latency/clock measurement, calibration, DSP, protocol execution and CAD change were not performed.

## Remaining operator work

No index, Host API or channel from this baseline should be selected. After the iMM-6C, CHU II and fixture are connected in a later authorized step, an operator must capture a new inventory and then identify the input/output endpoints, Host API, physical connections and channels. The microphone calibration file must still be provided and hashed. Full duplex, shared clock, channel mapping and calibration claims remain unverified.

Git submission and remote verification for DEV-03.01 are recorded by Git history. DEV-03.02 changes only the confirmed context and report interpretation; it does not alter the original capture artifacts.
