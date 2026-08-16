"""Narrow hardware-independent interface and deterministic virtual duplex backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.virtual_capture_models import FaultMode, VirtualCaptureScenario


class VirtualBackendError(RuntimeError):
    """Raised by the deterministic virtual backend at an injected fault."""


@dataclass(frozen=True)
class BackendBlockResult:
    input_block: NDArray[np.float32]
    status_flags: tuple[str, ...] = ()


class CaptureBackend(Protocol):
    def prepare(self, *, sample_rate_hz: int, total_frame_count: int) -> None: ...

    def arm(self) -> None: ...

    def exchange_block(
        self, output_block: NDArray[np.float32], *, frame_count: int, block_index: int
    ) -> BackendBlockResult: ...

    def close(self) -> None: ...

    def abort(self) -> None: ...


class VirtualDuplexBackend:
    """Block-wise exact integer delay and gain; never touches an audio device."""

    def __init__(self, scenario: VirtualCaptureScenario) -> None:
        self.scenario = scenario
        self._delay = np.zeros((1, scenario.integer_latency_samples), dtype=np.float32)
        self._prepared = False
        self._armed = False
        self._closed = False

    def prepare(self, *, sample_rate_hz: int, total_frame_count: int) -> None:
        if sample_rate_hz <= 0 or total_frame_count <= 0 or self._prepared:
            raise VirtualBackendError("invalid or repeated virtual backend preparation")
        self._prepared = True

    def arm(self) -> None:
        if not self._prepared or self._armed or self._closed:
            raise VirtualBackendError("virtual backend cannot be armed in its current state")
        self._armed = True

    def exchange_block(
        self, output_block: NDArray[np.float32], *, frame_count: int, block_index: int
    ) -> BackendBlockResult:
        if not self._armed or self._closed:
            raise VirtualBackendError("virtual backend is not armed")
        if output_block.shape != (1, frame_count) or output_block.dtype != np.float32:
            raise VirtualBackendError("virtual backend requires [1,n] float32 output blocks")
        combined = np.concatenate((self._delay, output_block), axis=1)
        input_block = np.ascontiguousarray(
            combined[:, :frame_count] * np.float32(self.scenario.linear_gain),
            dtype=np.float32,
        )
        latency = self.scenario.integer_latency_samples
        self._delay = np.ascontiguousarray(combined[:, frame_count : frame_count + latency])
        if block_index != self.scenario.fault_block_index:
            return BackendBlockResult(input_block)
        mode = self.scenario.fault_mode
        if mode is FaultMode.SHORT_INPUT_BLOCK:
            return BackendBlockResult(input_block[:, :-1])
        if mode is FaultMode.DROPOUT:
            return BackendBlockResult(input_block, ("dropout",))
        if mode is FaultMode.CLIPPING:
            clipped = input_block.copy()
            clipped[0, 0] = np.float32(1.25)
            return BackendBlockResult(clipped, ("clipping",))
        if mode is FaultMode.BACKEND_ERROR:
            raise VirtualBackendError("injected deterministic backend error")
        if mode is FaultMode.ABORT_REQUESTED:
            return BackendBlockResult(input_block, ("abort_requested",))
        return BackendBlockResult(input_block)

    def close(self) -> None:
        self._closed = True

    def abort(self) -> None:
        self._closed = True
