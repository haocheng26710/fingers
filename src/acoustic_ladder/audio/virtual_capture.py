"""Deterministic block-wise virtual capture execution; no hardware audio APIs."""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.virtual_capture_backend import (
    BackendBlockResult,
    CaptureBackend,
    VirtualDuplexBackend,
)
from acoustic_ladder.audio.virtual_capture_models import (
    BlockTraceRecord,
    CaptureDiagnostics,
    CaptureFaultCounters,
    CaptureState,
    CaptureTransitionError,
    StateTransitionRecord,
    VirtualCaptureExecutionError,
    VirtualCaptureResult,
    VirtualCaptureScenario,
)


class CaptureStateMachine:
    """Explicit capture lifecycle with deterministic sample-clock transitions."""

    _TERMINAL: ClassVar[frozenset[CaptureState]] = frozenset(
        {CaptureState.COMPLETED, CaptureState.FAILED, CaptureState.ABORTED}
    )
    _ALLOWED: ClassVar[dict[CaptureState, frozenset[CaptureState]]] = {
        CaptureState.CREATED: frozenset(
            {CaptureState.PREPARED, CaptureState.FAILED, CaptureState.ABORTED}
        ),
        CaptureState.PREPARED: frozenset(
            {CaptureState.ARMED, CaptureState.FAILED, CaptureState.ABORTED}
        ),
        CaptureState.ARMED: frozenset(
            {CaptureState.RUNNING, CaptureState.FAILED, CaptureState.ABORTED}
        ),
        CaptureState.RUNNING: frozenset(
            {CaptureState.COMPLETED, CaptureState.FAILED, CaptureState.ABORTED}
        ),
        CaptureState.COMPLETED: frozenset(),
        CaptureState.FAILED: frozenset(),
        CaptureState.ABORTED: frozenset(),
    }

    def __init__(self, *, expected_sample_count: int) -> None:
        if expected_sample_count <= 0:
            raise CaptureTransitionError("expected_sample_count must be positive")
        self.expected_sample_count = expected_sample_count
        self.state = CaptureState.CREATED
        self.transitions: list[StateTransitionRecord] = []

    def transition(
        self,
        target: CaptureState,
        reason: str,
        *,
        sample_cursor: int = 0,
        completed_block_count: int = 0,
    ) -> StateTransitionRecord:
        if self.state in self._TERMINAL:
            raise CaptureTransitionError(f"cannot transition from terminal state {self.state}")
        if target not in self._ALLOWED[self.state]:
            raise CaptureTransitionError(
                f"illegal capture state transition: {self.state} -> {target}"
            )
        if not reason:
            raise CaptureTransitionError("transition reason must be non-empty")
        if sample_cursor < 0 or completed_block_count < 0:
            raise CaptureTransitionError("transition counters cannot be negative")
        if self.transitions and sample_cursor < self.transitions[-1].sample_cursor:
            raise CaptureTransitionError("transition sample cursor cannot move backwards")
        record = StateTransitionRecord(
            sequence=len(self.transitions) + 1,
            from_state=self.state,
            to_state=target,
            reason=reason,
            sample_cursor=sample_cursor,
            completed_block_count=completed_block_count,
        )
        self.transitions.append(record)
        self.state = target
        return record

    def complete(
        self,
        *,
        sample_cursor: int,
        completed_block_count: int,
        has_unhandled_status: bool = False,
    ) -> StateTransitionRecord:
        if sample_cursor != self.expected_sample_count:
            raise CaptureTransitionError(
                "cannot complete before sample cursor reaches expected sample count"
            )
        if has_unhandled_status:
            raise CaptureTransitionError("cannot complete with unhandled backend status")
        return self.transition(
            CaptureState.COMPLETED,
            "all planned samples exchanged",
            sample_cursor=sample_cursor,
            completed_block_count=completed_block_count,
        )


class VirtualCaptureEngine:
    """Run one virtual full-duplex schedule block by actual block."""

    def execute(
        self,
        excitation: NDArray[np.float32],
        sample_rate_hz: int,
        scenario: VirtualCaptureScenario,
        *,
        backend: CaptureBackend | None = None,
    ) -> VirtualCaptureResult:
        if (
            excitation.ndim != 2
            or excitation.shape[0] != 1
            or excitation.dtype != np.float32
            or not excitation.flags.c_contiguous
            or excitation.shape[1] <= 0
            or not bool(np.isfinite(excitation).all())
        ):
            raise ValueError("excitation must be finite C-contiguous [1,n] float32")
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        capture_count = excitation.shape[1] + scenario.capture_tail_samples
        planned_blocks = math.ceil(capture_count / scenario.block_size_frames)
        if scenario.fault_block_index is not None and scenario.fault_block_index >= planned_blocks:
            diagnostics = CaptureDiagnostics(
                final_state=CaptureState.CREATED,
                error_code="invalid_fault_block_index",
                error_message="fault_block_index is outside planned block range",
                fault_block_index=scenario.fault_block_index,
                completed_block_count=0,
                sample_cursor=0,
                block_trace=(),
                transitions=(),
                fault_counters=self._counters(error=1),
            )
            raise VirtualCaptureExecutionError(diagnostics)
        output = np.zeros((1, capture_count), dtype=np.float32)
        output[:, : excitation.shape[1]] = excitation
        captured = np.zeros_like(output)
        active_backend = backend or VirtualDuplexBackend(scenario)
        machine = CaptureStateMachine(expected_sample_count=capture_count)
        traces: list[BlockTraceRecord] = []
        completed_blocks = 0
        cursor = 0
        counts = {"xrun": 0, "dropout": 0, "short_read": 0, "clipping": 0, "error": 0}
        fault_block: int | None = None

        def fail(code: str, message: str, *, aborted: bool = False) -> VirtualCaptureExecutionError:
            counts["error"] += 1
            target = CaptureState.ABORTED if aborted else CaptureState.FAILED
            if machine.state not in CaptureStateMachine._TERMINAL:
                machine.transition(
                    target,
                    message,
                    sample_cursor=cursor,
                    completed_block_count=completed_blocks,
                )
            try:
                active_backend.abort()
            except Exception as abort_error:
                counts["error"] += 1
                message = (
                    f"{message}; backend abort also failed: "
                    f"{type(abort_error).__name__}: {abort_error}"
                )
            return VirtualCaptureExecutionError(
                CaptureDiagnostics(
                    final_state=target if machine.state is target else machine.state,
                    error_code=code,
                    error_message=message,
                    fault_block_index=fault_block,
                    completed_block_count=completed_blocks,
                    sample_cursor=cursor,
                    block_trace=tuple(traces),
                    transitions=tuple(machine.transitions),
                    fault_counters=self._counters(**counts),
                )
            )

        try:
            active_backend.prepare(sample_rate_hz=sample_rate_hz, total_frame_count=capture_count)
            machine.transition(CaptureState.PREPARED, "backend prepared")
            active_backend.arm()
            machine.transition(CaptureState.ARMED, "backend armed")
            machine.transition(CaptureState.RUNNING, "block exchange started")
            for block_index in range(planned_blocks):
                fault_block = block_index
                start = block_index * scenario.block_size_frames
                frames = min(scenario.block_size_frames, capture_count - start)
                output_block = np.ascontiguousarray(output[:, start : start + frames])
                try:
                    response = active_backend.exchange_block(
                        output_block, frame_count=frames, block_index=block_index
                    )
                except Exception as exc:
                    traces.append(
                        self._trace(block_index, start, frames, frames, 0, ["backend_error"])
                    )
                    raise fail("backend_error", str(exc)) from exc
                self._check_response_type(response)
                flags = list(response.status_flags)
                actual_input = (
                    response.input_block.shape[1] if response.input_block.ndim == 2 else 0
                )
                traces.append(
                    self._trace(
                        block_index, start, frames, output_block.shape[1], actual_input, flags
                    )
                )
                if "abort_requested" in flags:
                    raise fail("abort_requested", "virtual backend requested abort", aborted=True)
                if "dropout" in flags:
                    counts["dropout"] += 1
                    raise fail("dropout", "virtual backend reported dropout")
                if response.input_block.shape != (1, frames):
                    counts["short_read"] += 1
                    raise fail("short_input_block", "virtual backend returned a short input block")
                if response.input_block.dtype != np.float32:
                    raise fail("invalid_input_dtype", "virtual backend input dtype is not float32")
                if not bool(np.isfinite(response.input_block).all()):
                    raise fail("non_finite_input", "virtual backend returned non-finite input")
                if "clipping" in flags or bool(np.any(np.abs(response.input_block) > 1.0)):
                    counts["clipping"] += 1
                    raise fail("clipping", "virtual backend returned clipped input")
                unknown_flags = sorted(set(flags) - {"abort_requested", "dropout", "clipping"})
                if unknown_flags:
                    counts["xrun"] += 1
                    raise fail("backend_status", f"unhandled backend status: {unknown_flags}")
                captured[:, start : start + frames] = response.input_block
                cursor += frames
                completed_blocks += 1
            active_backend.close()
            machine.complete(sample_cursor=cursor, completed_block_count=completed_blocks)
        except VirtualCaptureExecutionError:
            raise
        except Exception as exc:
            raise fail("backend_error", str(exc)) from exc
        return VirtualCaptureResult(
            output_samples=np.ascontiguousarray(output),
            input_samples=np.ascontiguousarray(captured),
            capture_sample_count=capture_count,
            planned_block_count=planned_blocks,
            actual_block_count=completed_blocks,
            last_block_frame_count=traces[-1].requested_frame_count,
            block_trace=tuple(traces),
            transitions=tuple(machine.transitions),
            fault_counters=self._counters(**counts),
            final_state=machine.state,
            all_finite=bool(np.isfinite(output).all() and np.isfinite(captured).all()),
        )

    @staticmethod
    def _trace(
        block_index: int,
        start: int,
        requested: int,
        output_count: int,
        input_count: int,
        flags: list[str],
    ) -> BlockTraceRecord:
        return BlockTraceRecord(
            sequence=block_index + 1,
            start_frame=start,
            requested_frame_count=requested,
            output_frame_count=output_count,
            input_frame_count=input_count,
            status_flags=flags,
        )

    @staticmethod
    def _check_response_type(response: BackendBlockResult) -> None:
        if not isinstance(response, BackendBlockResult):
            raise TypeError("capture backend returned an invalid block result")

    @staticmethod
    def _counters(
        *,
        xrun: int = 0,
        dropout: int = 0,
        short_read: int = 0,
        clipping: int = 0,
        error: int = 0,
    ) -> CaptureFaultCounters:
        return CaptureFaultCounters(
            xrun_count=xrun,
            dropout_count=dropout,
            short_read_count=short_read,
            clipping_count=clipping,
            error_count=error,
        )
