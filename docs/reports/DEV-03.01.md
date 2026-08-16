# DEV-03.01 completion report

## Outcome

- Software implementation: **PASS**
- Actual read-only inventory capture: **PASS**
- Device binding: `needs_operator_confirmation`
- `hardware_ready`: `false`
- Playback, recording or stream opening: **none**
- DEV-03.02 work: **not started**

The implementation is based on `3e075956727fcbfe2c0b57588cbef6ee34440136`. Before modification, local `main`, local `origin/main` and GitHub `main` matched that commit, the origin URL was correct, the worktree was clean and no project instruction file was present.

## Implemented boundary

The new `acoustic_ladder.audio` package contains strict Pydantic hardware/inventory/preflight models, an injectable inventory protocol, lazy `SoundDeviceInventoryBackend`, deterministic `FakeInventoryBackend`, normalization, conservative preflight and create-only canonical JSON/sidecar persistence. The production adapter calls only version queries, `query_hostapis`, `query_devices`, `check_input_settings` and `check_output_settings`.

Audio configuration now references the provisional hardware setup and actual inventory while preserving null backend/device/candidate/channel selections, formal 1+1, `config_status=draft` and `hardware_ready=false`. Three generated schemas were added; all eleven generated schemas match their models.

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

The following table reproduces the capability-bearing device records returned by sounddevice. Replacement characters are preserved exactly as returned; they are not guessed or repaired. User-defined Bluetooth suffixes on indices 21/22 were deterministically redacted to prevent a personal friendly name from entering the artifact, and both redactions are recorded in `warnings`. `I/O` is maximum input/output channels. `48k` is the separate mono float32 check for the supported direction.

| Index | Host API | Device name | I/O | 48k |
|---:|---|---|---:|---|
| 0 | MME | Microsoft ����ӳ���� - Input | 2/0 | input PASS |
| 1 | MME | ������˷� (AMD Audio Device) | 2/0 | input PASS |
| 2 | MME | Microsoft ����ӳ���� - Output | 0/2 | output PASS |
| 3 | MME | ���� (Senary Audio) | 0/6 | output PASS |
| 4 | MME | ������ (Senary Audio) | 0/6 | output PASS |
| 5 | Windows DirectSound | ������������������ | 2/0 | input PASS |
| 6 | Windows DirectSound | ������˷� (AMD Audio Device) | 2/0 | input PASS |
| 7 | Windows DirectSound | �������������� | 0/2 | output PASS |
| 8 | Windows DirectSound | ���� (Senary Audio) | 0/6 | output PASS |
| 9 | Windows DirectSound | ������ (Senary Audio) | 0/6 | output PASS |
| 10 | Windows WASAPI | ������ (Senary Audio) | 0/2 | output PASS |
| 11 | Windows WASAPI | ���� (Senary Audio) | 0/2 | output PASS |
| 12 | Windows WASAPI | ������˷� (AMD Audio Device) | 2/0 | input PASS |
| 13 | Windows WDM-KS | Output 1 (Senary Audio headphone) | 0/2 | output PASS |
| 14 | Windows WDM-KS | Output 2 (Senary Audio headphone) | 0/6 | output PASS |
| 15 | Windows WDM-KS | Input (Senary Audio headphone) | 2/0 | input PASS |
| 16 | Windows WDM-KS | Output 1 (Senary Audio output) | 0/2 | output PASS |
| 17 | Windows WDM-KS | Output 2 (Senary Audio output) | 0/6 | output PASS |
| 18 | Windows WDM-KS | Input (Senary Audio output) | 2/0 | input PASS |
| 19 | Windows WDM-KS | ��˷� (Senary Audio capture) | 2/0 | input PASS |
| 20 | Windows WDM-KS | ������˷� (AMDAfdInstall Wave Microphone - 0) | 2/0 | input PASS |
| 21 | Windows WDM-KS | ���� (`bthhfenum` Hands-Free; redacted user-defined suffix) | 0/1 | output FAIL: `PortAudioError -9997` |
| 22 | Windows WDM-KS | ���� (`bthhfenum` Hands-Free; redacted user-defined suffix) | 1/0 | input FAIL: `PortAudioError -9997` |
| 23 | Windows WDM-KS | ���� () | 0/2 | output FAIL: `PortAudioError -9997` |

Twenty-one separate directional checks passed and three returned `Invalid sample rate [PaErrorCode -9997]`. These checks do not establish simultaneous duplex operation.

No enumerated input name unambiguously matched `iMM-6C`, `USB Audio Device` or `CM6542`; therefore there is no identified iMM-6C input candidate. No output can be identified as the iMM-6C line/headphone output. All output-capable indices are retained for operator review: `2, 3, 4, 7, 8, 9, 10, 11, 13, 14, 16, 17, 21, 23`. Input and output are not confirmed as the same index or physical interface.

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

Commands actually used are recorded in `docs/IMPLEMENTATION_LOG.md`. No required acceptance check was omitted. Prohibited playback, recording, stream opening, ESS generation, latency/clock measurement, calibration, DSP, protocol execution, CAD change and DEV-03.02 work were intentionally not performed because they are outside this step.

## Remaining operator work

An operator must identify the iMM-6C input and headphone/line output indices, choose and confirm the host API, confirm physical connections and input/output channel indices, and later provide and hash the microphone calibration file. Subsequent work must separately validate full duplex, shared clock, channel mapping and any calibration claims. Device indices are valid only within this inventory snapshot.

Git submission and remote verification occur after this report is frozen. Their actual result is reported by Git history and the final task response; this document does not invent a self-referential commit SHA.
