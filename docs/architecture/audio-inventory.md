# Read-only audio inventory and preflight

DEV-03.01 separates hardware facts, a machine-specific enumeration snapshot and a conservative preflight decision. DEV-03.02 adds `AudioInventoryCaptureContext` so later operator facts can qualify an immutable capture, plus `ContextualAudioPreflightReport` for interpretation without rewriting the original snapshot. All persisted inputs are linked by repository-relative reference and SHA256.

## Safety boundary

`SoundDeviceInventoryBackend` imports sounddevice lazily. Its public operations are limited to version queries, `query_hostapis`, `query_devices`, `check_input_settings` and `check_output_settings`. No playback, recording or stream constructor exists in the audio package. A format-check success means only that PortAudio accepted one direction's proposed settings; it is not a duplex, clock, latency or channel-routing validation.

`FakeInventoryBackend` supplies deterministic metadata and capability results for tests without importing sounddevice or touching hardware. Production exceptions from a format check become an unsupported capability record with the original exception type/message; enumeration and initialization failures remain explicit project exceptions.

## Identity and candidates

`snapshot_device_index` is explicitly scoped as `single_inventory_snapshot`; it is not a persistent device ID. Default devices are mapped to records from the same snapshot. Candidate matching is permitted only when the capture context says the experimental hardware was connected, and a name match never confirms a device, host API, physical interface, clock or channel.

The operator later confirmed that the iMM-6C, CHU II and fixture were disconnected during DEV-03.01 capture. Its role is therefore `development_host_baseline_without_experimental_hardware`: every endpoint is interpreted as `not_experimental_hardware`, both candidate lists are empty, candidate status is `not_applicable_hardware_disconnected`, and binding/confirmation are `deferred_until_hardware_connection`. No current device, Host API or channel needs selection. All readiness and calibration claims remain false.

## Name encoding and generated reports

The verified inventory JSON is authoritative for names and contains correct UTF-8 Chinese. DEV-03.01's console/transcription path damaged some displayed names; evidence does not identify the exact terminal, code-page or tool layer. `audio-list` now emits names as ASCII-only JSON strings marked `DEVICE_NAME_ENCODING=JSON_ASCII_ESCAPED`, allowing standard JSON decoding to restore the original Unicode.

`audio-inventory-summary` loads the inventory only after sidecar verification and renders device rows directly from the parsed model. Markdown backslashes, pipes and line breaks are escaped deterministically; output is UTF-8 with LF endings and a create-only SHA256 sidecar. Console output is never reparsed as a name source.

## Persistence and privacy

Inventory JSON uses canonical sorted UTF-8 serialization and create-only atomic publication. Its SHA256 sidecar is verified before loading. The snapshot records no username, hostname, environment variable or local absolute path. It necessarily preserves the device names returned by PortAudio because those names are required to audit the enumeration.

The hardware record deliberately has no invented calibration path, digest, serial number or measurement. The known calibration-file availability is recorded separately from application; without the file and digest, `microphone_calibration_applied` must remain false. Without an acoustic calibrator or electrical loopback, absolute SPL calibration and electrical loopback availability also remain false.

## Semantic audit closure

`audio-context-validate` now verifies more than each file against its own sidecar. It strictly parses the hardware setup, validates every persisted reference as a repository-relative path, checks all cross-file references and hashes, regenerates the inventory summary byte for byte, then reconstructs the contextual preflight using its persisted `generated_at` and compares the complete model. Consequently, changing a device name, summary, hardware record, reference, or any member of a swapped bundle remains detectable even if an attacker recalculates the modified file's sidecar.

This validation is read-only and does not instantiate the inventory backend. Candidate lists remain empty, binding and confirmation remain deferred, and every readiness/calibration field remains false.
