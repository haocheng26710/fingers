"""Strict deterministic contracts for development-only virtual duplex capture."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.config.yaml_loader import load_yaml_mapping
from acoustic_ladder.domain.models import ConfigSnapshot
from acoustic_ladder.domain.paths import validate_relative_path

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class VirtualCaptureError(RuntimeError):
    """Base error for virtual capture configuration and execution."""


class VirtualScenarioError(VirtualCaptureError):
    """Raised when a development virtual-duplex scenario is invalid."""


class CaptureTransitionError(VirtualCaptureError):
    """Raised when a capture state transition violates the state machine."""


class VirtualCaptureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class FaultMode(StrEnum):
    NONE = "none"
    SHORT_INPUT_BLOCK = "short_input_block"
    DROPOUT = "dropout"
    CLIPPING = "clipping"
    BACKEND_ERROR = "backend_error"
    ABORT_REQUESTED = "abort_requested"


class CaptureState(StrEnum):
    CREATED = "created"
    PREPARED = "prepared"
    ARMED = "armed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class VirtualCaptureScenario(VirtualCaptureModel):
    schema_version: Literal["1.0.0"]
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    usage_scope: Literal["development_fixture"]
    backend_id: Literal["deterministic_virtual_duplex"]
    backend_version: Literal["1.0.0"]
    block_size_frames: int = Field(gt=0)
    integer_latency_samples: int = Field(ge=0)
    capture_tail_samples: int = Field(ge=0)
    linear_gain: float = Field(gt=0)
    fault_mode: FaultMode
    fault_block_index: int | None = Field(ge=0)
    hardware_io_authorized: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]

    @model_validator(mode="after")
    def validate_scenario_boundaries(self) -> VirtualCaptureScenario:
        if self.capture_tail_samples < self.integer_latency_samples:
            raise ValueError("capture_tail_samples must cover integer_latency_samples")
        if self.fault_mode is FaultMode.NONE and self.fault_block_index is not None:
            raise ValueError("fault_block_index must be null when fault_mode is none")
        if self.fault_mode is not FaultMode.NONE and self.fault_block_index is None:
            raise ValueError("fault_block_index is required for an injected fault")
        return self


@dataclass(frozen=True)
class LoadedVirtualCaptureScenario:
    model: VirtualCaptureScenario
    original_relative_path: str
    original_bytes: bytes
    normalized_bytes: bytes
    original_sha256: str
    normalized_sha256: str


class BlockTraceRecord(VirtualCaptureModel):
    sequence: int = Field(gt=0)
    start_frame: int = Field(ge=0)
    requested_frame_count: int = Field(gt=0)
    output_frame_count: int = Field(ge=0)
    input_frame_count: int = Field(ge=0)
    status_flags: list[str]


class StateTransitionRecord(VirtualCaptureModel):
    sequence: int = Field(gt=0)
    from_state: CaptureState
    to_state: CaptureState
    reason: str
    sample_cursor: int = Field(ge=0)
    completed_block_count: int = Field(ge=0)


class CaptureFaultCounters(VirtualCaptureModel):
    xrun_count: int = Field(ge=0)
    dropout_count: int = Field(ge=0)
    short_read_count: int = Field(ge=0)
    clipping_count: int = Field(ge=0)
    error_count: int = Field(ge=0)


@dataclass(frozen=True)
class CaptureDiagnostics:
    final_state: CaptureState
    error_code: str
    error_message: str
    fault_block_index: int | None
    completed_block_count: int
    sample_cursor: int
    block_trace: tuple[BlockTraceRecord, ...]
    transitions: tuple[StateTransitionRecord, ...]
    fault_counters: CaptureFaultCounters


class VirtualCaptureExecutionError(VirtualCaptureError):
    """Execution failure with deterministic state/sample diagnostics."""

    def __init__(self, diagnostics: CaptureDiagnostics) -> None:
        super().__init__(
            f"{diagnostics.error_code}: {diagnostics.error_message}; "
            f"published=false; block={diagnostics.fault_block_index}"
        )
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class VirtualCaptureResult:
    output_samples: NDArray[np.float32]
    input_samples: NDArray[np.float32]
    capture_sample_count: int
    planned_block_count: int
    actual_block_count: int
    last_block_frame_count: int
    block_trace: tuple[BlockTraceRecord, ...]
    transitions: tuple[StateTransitionRecord, ...]
    fault_counters: CaptureFaultCounters
    final_state: CaptureState
    all_finite: bool


class VirtualCaptureReceipt(VirtualCaptureModel):
    schema_version: Literal["1.0.0"]
    capture_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    run_id: str
    session_id: str
    reassembly_id: str
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    backend_id: Literal["deterministic_virtual_duplex"]
    backend_version: Literal["1.0.0"]
    scenario_reference: str
    scenario_raw_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario_normalized_sha256: str = Field(pattern=SHA256_PATTERN)
    bundle_content_sha256: str = Field(pattern=SHA256_PATTERN)
    device_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    config_snapshots: dict[str, ConfigSnapshot]
    protocol_id: str
    protocol_execution_performed: Literal[False]
    source_ess_artifact_id: str
    source_ess_metadata_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    source_ess_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    ess_sample_count: int = Field(gt=0)
    capture_tail_sample_count: int = Field(ge=0)
    capture_sample_count: int = Field(gt=0)
    planned_output_sample_count: int = Field(gt=0)
    actual_output_sample_count: int = Field(gt=0)
    planned_input_sample_count: int = Field(gt=0)
    actual_input_sample_count: int = Field(gt=0)
    block_size_frames: int = Field(gt=0)
    planned_block_count: int = Field(gt=0)
    actual_block_count: int = Field(gt=0)
    last_block_frame_count: int = Field(gt=0)
    integer_latency_samples: int = Field(ge=0)
    linear_gain: float = Field(gt=0)
    output_shape: tuple[Literal[1], int]
    input_shape: tuple[Literal[1], int]
    output_dtype: Literal["float32"]
    input_dtype: Literal["float32"]
    output_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    input_raw_float32_sha256: str = Field(pattern=SHA256_PATTERN)
    output_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    input_wav_sha256: str = Field(pattern=SHA256_PATTERN)
    block_trace: list[BlockTraceRecord]
    state_transition_trace: list[StateTransitionRecord]
    fault_counters: CaptureFaultCounters
    final_state: Literal["completed"]
    all_finite: Literal[True]
    create_only: Literal[True]
    immutable: Literal[True]
    virtual_duplex_scheduler_exercised: Literal[True]
    hardware_io_performed: Literal[False]
    playback_performed: Literal[False]
    recording_performed: Literal[False]
    hardware_ready: Literal[False]
    full_duplex_verified: Literal[False]
    shared_clock_verified: Literal[False]
    channel_mapping_verified: Literal[False]
    calibration_file_verified: Literal[False]
    calibration_applied: Literal[False]
    absolute_spl_calibrated: Literal[False]
    electrical_loopback_available: Literal[False]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]
    safety_marker: Literal["SYNTHETIC_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT"]

    @model_validator(mode="after")
    def validate_completed_capture(self) -> VirtualCaptureReceipt:
        validate_relative_path(self.scenario_reference)
        expected_snapshots = {
            "device_manifest",
            "audio_config",
            "protocol_config",
            "analysis_config",
            "synthetic_config",
        }
        if set(self.config_snapshots) != expected_snapshots:
            raise ValueError("capture receipt must contain all five configuration snapshots")
        counts = {
            self.capture_sample_count,
            self.planned_output_sample_count,
            self.actual_output_sample_count,
            self.planned_input_sample_count,
            self.actual_input_sample_count,
            self.output_shape[1],
            self.input_shape[1],
        }
        if len(counts) != 1:
            raise ValueError("capture sample counts and shapes must agree")
        if self.ess_sample_count + self.capture_tail_sample_count != self.capture_sample_count:
            raise ValueError("ESS and tail sample counts do not form capture count")
        if self.actual_block_count != self.planned_block_count:
            raise ValueError("completed capture must execute every planned block")
        if len(self.block_trace) != self.actual_block_count:
            raise ValueError("actual block count must match block trace")
        cursor = 0
        for sequence, block in enumerate(self.block_trace, start=1):
            if block.sequence != sequence or block.start_frame != cursor:
                raise ValueError("block trace must be continuous and sequential")
            if (
                block.requested_frame_count != block.output_frame_count
                or block.requested_frame_count != block.input_frame_count
                or block.status_flags
            ):
                raise ValueError("completed block trace contains a count mismatch or status")
            cursor += block.requested_frame_count
        if cursor != self.capture_sample_count:
            raise ValueError("completed block trace does not cover capture samples")
        if self.block_trace[-1].requested_frame_count != self.last_block_frame_count:
            raise ValueError("last block frame count does not match trace")
        states = [CaptureState.CREATED] + [
            transition.to_state for transition in self.state_transition_trace
        ]
        if states != [
            CaptureState.CREATED,
            CaptureState.PREPARED,
            CaptureState.ARMED,
            CaptureState.RUNNING,
            CaptureState.COMPLETED,
        ]:
            raise ValueError("completed capture state order is invalid")
        for sequence, transition in enumerate(self.state_transition_trace, start=1):
            if transition.sequence != sequence:
                raise ValueError("state transition sequence must be continuous")
        if any(self.fault_counters.model_dump().values()):
            raise ValueError("completed capture cannot contain fault counters")
        return self


def load_virtual_capture_scenario(
    path: str | Path, *, project_root: str | Path
) -> LoadedVirtualCaptureScenario:
    """Load one strict scenario and bind its provenance to the project tree."""

    scenario_path = Path(path).resolve()
    root = Path(project_root).resolve()
    if not scenario_path.is_relative_to(root):
        raise VirtualScenarioError("virtual capture scenario must be inside project root")
    relative = validate_relative_path(scenario_path.relative_to(root).as_posix())
    try:
        original = scenario_path.read_bytes()
        mapping = load_yaml_mapping(scenario_path)
        model = VirtualCaptureScenario.model_validate_json(
            json.dumps(mapping, ensure_ascii=False, allow_nan=False)
        )
    except (OSError, ValueError) as exc:
        raise VirtualScenarioError(f"invalid virtual capture scenario {relative}: {exc}") from exc
    normalized = canonical_json_bytes(model.model_dump(mode="json"))
    return LoadedVirtualCaptureScenario(
        model=model,
        original_relative_path=relative,
        original_bytes=original,
        normalized_bytes=normalized,
        original_sha256=hashlib.sha256(original).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
    )
