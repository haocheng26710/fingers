# Read-only audio inventory and preflight

DEV-03.01 separates hardware facts, a machine-specific enumeration snapshot and a conservative preflight decision. `HardwareSetupRecord` contains only user-confirmed transducer/interface facts and official descriptive sources. `AudioInventorySnapshot` contains one sounddevice/PortAudio enumeration with timezone-aware provenance, OS/Python/backend versions, host APIs, devices, defaults and separate mono 48 kHz float32 checks. `AudioPreflightReport` links both inputs by repository-relative reference and SHA256.

## Safety boundary

`SoundDeviceInventoryBackend` imports sounddevice lazily. Its public operations are limited to version queries, `query_hostapis`, `query_devices`, `check_input_settings` and `check_output_settings`. No playback, recording or stream constructor exists in the audio package. A format-check success means only that PortAudio accepted one direction's proposed settings; it is not a duplex, clock, latency or channel-routing validation.

`FakeInventoryBackend` supplies deterministic metadata and capability results for tests without importing sounddevice or touching hardware. Production exceptions from a format check become an unsupported capability record with the original exception type/message; enumeration and initialization failures remain explicit project exceptions.

## Identity and candidates

`snapshot_device_index` is explicitly scoped as `single_inventory_snapshot`; it is not a persistent device ID. Default devices are mapped to records from the same snapshot. Names resembling iMM-6C, USB Audio Device or CM6542 may be listed as input candidates, while output-capable devices remain candidates for operator review. Name matching never confirms a device, host API, physical interface, clock or channel.

The committed DEV-03.01 capture did not expose an unambiguous iMM-6C/CM6542 name. Consequently its preflight report is `needs_operator_confirmation`. The report fixes full-duplex, shared-clock, channel-map, calibration-file, absolute-SPL and hardware-ready claims to false.

## Persistence and privacy

Inventory JSON uses canonical sorted UTF-8 serialization and create-only atomic publication. Its SHA256 sidecar is verified before loading. The snapshot records no username, hostname, environment variable or local absolute path. It necessarily preserves the device names returned by PortAudio because those names are required to audit the enumeration.

The hardware record deliberately has no invented calibration path, digest, serial number or measurement. The known calibration-file availability is recorded separately from application; without the file and digest, `microphone_calibration_applied` must remain false. Without an acoustic calibrator or electrical loopback, absolute SPL calibration and electrical loopback availability also remain false.
