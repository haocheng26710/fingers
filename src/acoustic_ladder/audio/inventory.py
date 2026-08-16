"""Normalize a read-only backend inventory into an auditable snapshot."""

from __future__ import annotations

import platform
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from acoustic_ladder.audio.backend import InventoryBackend, RawRecord
from acoustic_ladder.audio.errors import AudioInventoryError
from acoustic_ladder.audio.models import (
    AudioDeviceRecord,
    AudioInventorySnapshot,
    Direction,
    FormatCapabilityResult,
    HostApiRecord,
    InventoryProvenance,
    OperatingSystemRecord,
    utc_timestamp,
)


def _required_text(record: RawRecord, key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AudioInventoryError(f"{context} has invalid {key}")
    return value


def _privacy_safe_device_name(record: RawRecord, context: str, warnings: list[str]) -> str:
    name = _required_text(record, "name", context)
    if re.search(r"(?i)(?:[a-z]:[\\/]|/(?:home|users)/)", name):
        warnings.append(f"{context}: device name containing an absolute path was redacted")
        return "[REDACTED_DEVICE_NAME_CONTAINING_ABSOLUTE_PATH]"
    if "bthhfenum.sys" in name.casefold() and re.search(r";\s*\([^)]*\)", name):
        warnings.append(f"{context}: user-defined Bluetooth endpoint suffix was redacted")
        return re.sub(r";\s*\([^)]*\)", ";([REDACTED_USER_DEFINED_DEVICE_NAME])", name)
    return name


def _required_int(record: RawRecord, key: str, context: str, *, minimum: int = 0) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AudioInventoryError(f"{context} has invalid {key}")
    return value


def _required_rate(record: RawRecord, context: str) -> float:
    value = record.get("default_samplerate")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise AudioInventoryError(f"{context} has invalid default_samplerate")
    return float(value)


def _latency(
    record: RawRecord,
    key: str,
    *,
    available: bool,
    context: str,
    warnings: list[str],
) -> float | None:
    if not available:
        return None
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        warnings.append(f"{context}: {key} unavailable or invalid; normalized to null")
        return None
    return float(value)


def _default_index(
    default_record: RawRecord | None,
    devices: Sequence[RawRecord],
    direction: Direction,
    warnings: list[str],
) -> int | None:
    if default_record is None:
        warnings.append(f"default {direction} device unavailable")
        return None
    matches = [index for index, record in enumerate(devices) if record == default_record]
    if len(matches) != 1:
        warnings.append(f"default {direction} device could not be mapped uniquely")
        return None
    return matches[0]


def collect_inventory(
    backend: InventoryBackend,
    *,
    now: datetime | None = None,
    os_record: OperatingSystemRecord | None = None,
) -> AudioInventorySnapshot:
    """Enumerate metadata and check mono 48 kHz float32 support without opening streams."""

    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        raise AudioInventoryError("inventory timestamp must be timezone-aware")
    raw_host_apis = backend.query_host_apis()
    raw_devices = backend.query_devices()
    if not raw_host_apis:
        raise AudioInventoryError("audio backend returned no host APIs")
    if not raw_devices:
        raise AudioInventoryError("audio backend returned no devices")
    if any(not isinstance(record, Mapping) for record in raw_host_apis):
        raise AudioInventoryError("host API inventory contains a non-mapping record")
    if any(not isinstance(record, Mapping) for record in raw_devices):
        raise AudioInventoryError("device inventory contains a non-mapping record")

    warnings: list[str] = []
    default_input = _default_index(
        backend.query_default_device("input"), raw_devices, "input", warnings
    )
    default_output = _default_index(
        backend.query_default_device("output"), raw_devices, "output", warnings
    )
    host_apis: list[HostApiRecord] = []
    for index, record in enumerate(raw_host_apis):
        devices_value = record.get("devices")
        if not isinstance(devices_value, Sequence) or isinstance(devices_value, (str, bytes)):
            raise AudioInventoryError(f"host API {index} has invalid devices")
        device_indices: list[int] = []
        for device_index in devices_value:
            if isinstance(device_index, bool) or not isinstance(device_index, int):
                raise AudioInventoryError(f"host API {index} has invalid device index")
            if device_index < 0 or device_index >= len(raw_devices):
                raise AudioInventoryError(f"host API {index} references absent device")
            device_indices.append(device_index)
        api_default_input = record.get("default_input_device")
        api_default_output = record.get("default_output_device")
        host_apis.append(
            HostApiRecord(
                host_api_index=index,
                name=_required_text(record, "name", f"host API {index}"),
                device_indices=device_indices,
                device_count=len(device_indices),
                default_input_device_index=(
                    int(api_default_input)
                    if isinstance(api_default_input, int)
                    and not isinstance(api_default_input, bool)
                    and api_default_input >= 0
                    else None
                ),
                default_output_device_index=(
                    int(api_default_output)
                    if isinstance(api_default_output, int)
                    and not isinstance(api_default_output, bool)
                    and api_default_output >= 0
                    else None
                ),
            )
        )

    devices: list[AudioDeviceRecord] = []
    capabilities: list[FormatCapabilityResult] = []
    for index, record in enumerate(raw_devices):
        context = f"device {index}"
        input_channels = _required_int(record, "max_input_channels", context)
        output_channels = _required_int(record, "max_output_channels", context)
        host_api_index = _required_int(record, "hostapi", context)
        if host_api_index >= len(host_apis):
            raise AudioInventoryError(f"{context} references absent host API")
        devices.append(
            AudioDeviceRecord(
                snapshot_device_index=index,
                device_index_scope="single_inventory_snapshot",
                name=_privacy_safe_device_name(record, context, warnings),
                host_api_index=host_api_index,
                host_api_name=host_apis[host_api_index].name,
                max_input_channels=input_channels,
                max_output_channels=output_channels,
                default_sample_rate_hz=_required_rate(record, context),
                default_low_input_latency_s=_latency(
                    record,
                    "default_low_input_latency",
                    available=input_channels > 0,
                    context=context,
                    warnings=warnings,
                ),
                default_low_output_latency_s=_latency(
                    record,
                    "default_low_output_latency",
                    available=output_channels > 0,
                    context=context,
                    warnings=warnings,
                ),
                default_high_input_latency_s=_latency(
                    record,
                    "default_high_input_latency",
                    available=input_channels > 0,
                    context=context,
                    warnings=warnings,
                ),
                default_high_output_latency_s=_latency(
                    record,
                    "default_high_output_latency",
                    available=output_channels > 0,
                    context=context,
                    warnings=warnings,
                ),
                is_default_input=index == default_input,
                is_default_output=index == default_output,
                supports_input=input_channels > 0,
                supports_output=output_channels > 0,
            )
        )
        directions: list[Direction] = []
        if input_channels:
            directions.append("input")
        if output_channels:
            directions.append("output")
        for direction in directions:
            supported, error_type, error_message = backend.check_format(direction, index, 1, 48000)
            method: Literal["check_input_settings", "check_output_settings"]
            if direction == "input":
                method = "check_input_settings"
            else:
                method = "check_output_settings"
            capabilities.append(
                FormatCapabilityResult(
                    device_index=index,
                    direction=direction,
                    channels=1,
                    sample_rate_hz=48000,
                    dtype="float32",
                    check_method=method,
                    supported=supported,
                    error_type=error_type,
                    error_message=error_message,
                )
            )

    pa_number, pa_text = backend.portaudio_version()
    system = os_record or OperatingSystemRecord(
        system=platform.system() or "unknown",
        release=platform.release() or "unknown",
        version=platform.version() or "unknown",
        machine=platform.machine() or "unknown",
    )
    return AudioInventorySnapshot(
        schema_version="1.0.0",
        snapshot_id=f"audio-inventory-{utc_timestamp(generated_at.astimezone(UTC))}",
        captured_at=generated_at,
        provenance=InventoryProvenance(
            backend="sounddevice",
            backend_version=backend.backend_version(),
            portaudio_version=pa_number,
            portaudio_version_text=pa_text,
            operating_system=system,
            python_version=platform.python_version() or sys.version.split()[0],
        ),
        host_apis=host_apis,
        devices=devices,
        default_input_device_index=default_input,
        default_output_device_index=default_output,
        capability_results=capabilities,
        warnings=warnings,
        safety_marker="NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED",
    )
