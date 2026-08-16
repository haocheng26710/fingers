"""Strict contracts for read-only audio inventory and hardware preflight."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Direction = Literal["input", "output"]


class AudioModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HostApiRecord(AudioModel):
    host_api_index: int = Field(ge=0)
    name: str = Field(min_length=1)
    device_indices: list[int]
    device_count: int = Field(ge=0)
    default_input_device_index: int | None = Field(ge=0)
    default_output_device_index: int | None = Field(ge=0)


class AudioDeviceRecord(AudioModel):
    snapshot_device_index: int = Field(ge=0)
    device_index_scope: Literal["single_inventory_snapshot"]
    name: str = Field(min_length=1)
    host_api_index: int = Field(ge=0)
    host_api_name: str = Field(min_length=1)
    max_input_channels: int = Field(ge=0)
    max_output_channels: int = Field(ge=0)
    default_sample_rate_hz: float = Field(gt=0)
    default_low_input_latency_s: float | None = Field(ge=0)
    default_low_output_latency_s: float | None = Field(ge=0)
    default_high_input_latency_s: float | None = Field(ge=0)
    default_high_output_latency_s: float | None = Field(ge=0)
    is_default_input: bool
    is_default_output: bool
    supports_input: bool
    supports_output: bool

    @model_validator(mode="after")
    def latency_matches_direction(self) -> AudioDeviceRecord:
        input_values = (self.default_low_input_latency_s, self.default_high_input_latency_s)
        output_values = (self.default_low_output_latency_s, self.default_high_output_latency_s)
        if self.max_input_channels == 0 and any(value is not None for value in input_values):
            raise ValueError("input latency must be null when no input channels exist")
        if self.max_output_channels == 0 and any(value is not None for value in output_values):
            raise ValueError("output latency must be null when no output channels exist")
        if self.supports_input != (self.max_input_channels > 0):
            raise ValueError("supports_input must match max_input_channels")
        if self.supports_output != (self.max_output_channels > 0):
            raise ValueError("supports_output must match max_output_channels")
        return self


class FormatCapabilityResult(AudioModel):
    device_index: int = Field(ge=0)
    direction: Direction
    channels: Literal[1]
    sample_rate_hz: Literal[48000]
    dtype: Literal["float32"]
    check_method: Literal["check_input_settings", "check_output_settings"]
    supported: bool
    error_type: str | None
    error_message: str | None

    @model_validator(mode="after")
    def failure_has_error(self) -> FormatCapabilityResult:
        if self.supported and (self.error_type is not None or self.error_message is not None):
            raise ValueError("supported capability cannot contain an error")
        if not self.supported and not self.error_type:
            raise ValueError("unsupported capability requires error_type")
        return self


class OperatingSystemRecord(AudioModel):
    system: str = Field(min_length=1)
    release: str = Field(min_length=1)
    version: str = Field(min_length=1)
    machine: str = Field(min_length=1)


class InventoryProvenance(AudioModel):
    backend: Literal["sounddevice"]
    backend_version: str = Field(min_length=1)
    portaudio_version: int = Field(ge=0)
    portaudio_version_text: str = Field(min_length=1)
    operating_system: OperatingSystemRecord
    python_version: str = Field(min_length=1)


class AudioInventorySnapshot(AudioModel):
    schema_version: Literal["1.0.0"]
    snapshot_id: str = Field(min_length=1)
    captured_at: AwareDatetime
    provenance: InventoryProvenance
    host_apis: list[HostApiRecord]
    devices: list[AudioDeviceRecord]
    default_input_device_index: int | None = Field(ge=0)
    default_output_device_index: int | None = Field(ge=0)
    capability_results: list[FormatCapabilityResult]
    warnings: list[str]
    safety_marker: Literal["NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED"]

    @model_validator(mode="after")
    def inventory_references_are_consistent(self) -> AudioInventorySnapshot:
        api_indices = {api.host_api_index for api in self.host_apis}
        if len(api_indices) != len(self.host_apis):
            raise ValueError("host API indices must be unique")
        device_indices = {device.snapshot_device_index for device in self.devices}
        if len(device_indices) != len(self.devices):
            raise ValueError("device indices must be unique")
        for device in self.devices:
            if device.host_api_index not in api_indices:
                raise ValueError("device references an unknown host API")
        for default in (self.default_input_device_index, self.default_output_device_index):
            if default is not None and default not in device_indices:
                raise ValueError("default device is absent from inventory")
        return self


class TransducerRecord(AudioModel):
    role: Literal["TX", "RX"]
    brand: str = Field(min_length=1)
    model: str = Field(min_length=1)
    transducer_type: str = Field(min_length=1)
    connection: str = Field(min_length=1)


class HardwareSetupRecord(AudioModel):
    schema_version: Literal["1.0.0"]
    record_status: Literal["provisional"]
    output_transducer: TransducerRecord
    input_transducer: TransducerRecord
    interface_model: str = Field(min_length=1)
    operator_reported_shared_interface: bool
    amplifier_used: bool
    microphone_connection: str = Field(min_length=1)
    microphone_calibration_file_available: bool
    microphone_calibration_reference: str | None
    microphone_calibration_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    microphone_calibration_applied: bool
    acoustic_calibrator_available: bool
    absolute_spl_calibrated: bool
    electrical_loopback_available: bool
    exact_physical_connection_pending_confirmation: bool
    source_urls: list[str]
    notes: list[str]

    @model_validator(mode="after")
    def calibration_claims_are_evidenced(self) -> HardwareSetupRecord:
        if self.output_transducer.role != "TX" or self.input_transducer.role != "RX":
            raise ValueError("hardware transducer roles must be TX output and RX input")
        reference_pair = (
            self.microphone_calibration_reference,
            self.microphone_calibration_sha256,
        )
        if (reference_pair[0] is None) != (reference_pair[1] is None):
            raise ValueError("calibration reference and SHA256 must appear together")
        if self.microphone_calibration_applied and reference_pair[0] is None:
            raise ValueError("applied calibration requires a referenced, hashed file")
        if self.absolute_spl_calibrated and not self.acoustic_calibrator_available:
            raise ValueError("absolute SPL calibration requires an acoustic calibrator")
        return self


class AudioPreflightReport(AudioModel):
    schema_version: Literal["1.0.0"]
    generated_at: AwareDatetime
    inventory_reference: str = Field(min_length=1)
    inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hardware_setup_reference: str = Field(min_length=1)
    hardware_setup_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    software_inventory_status: Literal["complete"]
    input_candidate_device_indices: list[int]
    output_candidate_device_indices: list[int]
    input_candidate_status: Literal["candidate_found", "no_candidate_found"]
    output_candidate_status: Literal["candidate_found", "no_candidate_found"]
    operator_confirmation_status: Literal["needs_operator_confirmation"]
    separate_input_format_check: list[FormatCapabilityResult]
    separate_output_format_check: list[FormatCapabilityResult]
    hardware_ready: Literal[False]
    full_duplex_verified: Literal[False]
    shared_clock_verified: Literal[False]
    channel_mapping_verified: Literal[False]
    calibration_file_verified: Literal[False]
    absolute_spl_calibrated: Literal[False]
    blockers: list[str]
    warnings: list[str]
    safety_marker: Literal["NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED"]


def utc_timestamp(value: datetime) -> str:
    """Return a stable UTC timestamp for identifiers without leaking local identity."""

    return value.strftime("%Y%m%dT%H%M%SZ")
