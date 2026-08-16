"""Conservative, non-streaming audio preflight evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

from acoustic_ladder.audio.models import (
    AudioInventorySnapshot,
    AudioPreflightReport,
    HardwareSetupRecord,
)

_INPUT_HINTS = ("imm-6c", "imm 6c", "usb audio device", "cm6542")


def _candidate_indices(snapshot: AudioInventorySnapshot, *, input_device: bool) -> list[int]:
    result: list[int] = []
    for device in snapshot.devices:
        channels = device.max_input_channels if input_device else device.max_output_channels
        if channels <= 0:
            continue
        if input_device:
            lowered = device.name.casefold()
            if not any(hint in lowered for hint in _INPUT_HINTS):
                continue
        result.append(device.snapshot_device_index)
    return result


def build_preflight_report(
    snapshot: AudioInventorySnapshot,
    hardware: HardwareSetupRecord,
    *,
    inventory_reference: str,
    inventory_sha256: str,
    hardware_setup_reference: str,
    hardware_setup_sha256: str,
    now: datetime | None = None,
) -> AudioPreflightReport:
    input_candidates = _candidate_indices(snapshot, input_device=True)
    output_candidates = _candidate_indices(snapshot, input_device=False)
    blockers = [
        "operator must confirm exact input and output device indices",
        "full duplex operation has not been tested",
        "shared clock operation has not been validated",
        "physical channel mapping has not been confirmed",
        "microphone calibration has not been applied",
        "absolute SPL has not been calibrated",
    ]
    warnings = list(snapshot.warnings)
    if not input_candidates:
        blockers.append("no input device name matched the provisional iMM-6C hints")
    if not output_candidates:
        blockers.append("no output-capable device was enumerated")
    if hardware.exact_physical_connection_pending_confirmation:
        blockers.append("exact physical connection remains pending confirmation")
    if not hardware.electrical_loopback_available:
        warnings.append("electrical loopback is unavailable")
    return AudioPreflightReport(
        schema_version="1.0.0",
        generated_at=now or datetime.now(UTC),
        inventory_reference=inventory_reference,
        inventory_sha256=inventory_sha256,
        hardware_setup_reference=hardware_setup_reference,
        hardware_setup_sha256=hardware_setup_sha256,
        software_inventory_status="complete",
        input_candidate_device_indices=input_candidates,
        output_candidate_device_indices=output_candidates,
        input_candidate_status="candidate_found" if input_candidates else "no_candidate_found",
        output_candidate_status="candidate_found" if output_candidates else "no_candidate_found",
        operator_confirmation_status="needs_operator_confirmation",
        separate_input_format_check=[
            result for result in snapshot.capability_results if result.direction == "input"
        ],
        separate_output_format_check=[
            result for result in snapshot.capability_results if result.direction == "output"
        ],
        hardware_ready=False,
        full_duplex_verified=False,
        shared_clock_verified=False,
        channel_mapping_verified=False,
        calibration_file_verified=False,
        absolute_spl_calibrated=False,
        blockers=blockers,
        warnings=warnings,
        safety_marker="NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED",
    )
