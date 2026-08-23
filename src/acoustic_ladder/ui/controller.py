"""Display-independent controller for the fake-only development demo wizard."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.pilot_capture import (
    CancellationToken,
    CaptureState,
    PilotCaptureEngine,
    PilotCaptureError,
    PilotCaptureRequest,
    PilotCaptureResult,
)
from acoustic_ladder.audio.pilot_capture_backends import FakeFullDuplexBackend
from acoustic_ladder.ui.plans import DemoCondition, DemoPlan
from acoustic_ladder.ui.session_state import (
    DemoSessionStateError,
    DemoSessionStateStore,
    demo_plan_sha256,
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_CAPTURE_FILE_NAMES = frozenset(
    {"captured_input.wav", "output_reference.wav", "run.json", "qc.json"}
)


class WizardError(RuntimeError):
    """Raised when an operator action violates the demo workflow."""


class WizardRecoveryError(WizardError):
    """Raised when saved demo progress cannot be trusted."""


class WizardState(StrEnum):
    WAITING_USER_ASSEMBLY = "waiting_user_assembly"
    READY = "ready"
    RUNNING_REPEAT_1 = "running_repeat_1"
    RUNNING_REPEAT_2 = "running_repeat_2"
    CONDITION_COMPLETE = "condition_complete"
    BETWEEN_REPEATS = "between_repeats"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    ERROR = "error"
    ALL_COMPLETE = "all_complete"


class Confirmation(StrEnum):
    ASSEMBLY_COMPLETE = "assembly_complete"
    HEADPHONES_OFF = "headphones_off"
    PLACEMENT_CORRECT = "placement_correct"


@dataclass(frozen=True)
class WizardSnapshot:
    session_id: str
    mode: str
    state: WizardState
    condition_index: int
    condition_count: int
    completed_repeat_count: int
    total_repeat_count: int
    condition: DemoCondition
    confirmations: dict[Confirmation, bool]
    can_start: bool
    error_message: str
    last_capture_summary: str


class _ValidatedRecoveryState(TypedDict):
    condition_index: int
    repeat_count: int
    completed_conditions: list[str]
    state: WizardState
    resume_state: WizardState | None
    confirmations: dict[Confirmation, bool]


class FakeDemoCaptureRunner:
    """Narrow adapter from wizard repeat tasks to the DEV-07.01 fake capture core."""

    backend_type = "fake_full_duplex"

    def __init__(
        self,
        output_samples: NDArray[np.float32],
        *,
        backend_factory: Callable[[int, DemoCondition], FakeFullDuplexBackend] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._output_samples = np.ascontiguousarray(output_samples, dtype=np.float32)
        self._backend_factory = backend_factory or (
            lambda _repeat, _condition: FakeFullDuplexBackend(
                fixed_delay_samples=1, linear_gain=0.5
            )
        )
        self._now = now or (lambda: datetime.now(UTC))

    def capture_repeat(
        self,
        *,
        condition: DemoCondition,
        repeat_index: int,
        target: Path,
        run_id: str,
        cancellation: CancellationToken,
    ) -> PilotCaptureResult:
        request = PilotCaptureRequest(
            run_id=run_id,
            output_samples=self._output_samples,
            block_size_frames=256,
            started_at_utc=self._now(),
        )
        return PilotCaptureEngine().capture(
            request,
            target,
            self._backend_factory(repeat_index, condition),
            cancellation=cancellation,
        )


class ExperimentWizardController:
    """Own demo workflow state while remaining independent from Tk widgets."""

    def __init__(
        self,
        *,
        plan: DemoPlan,
        runner: FakeDemoCaptureRunner,
        session_id: str,
        session_root: Path,
        now: Callable[[], datetime] | None = None,
        _persist_initial: bool = True,
    ) -> None:
        if plan.mode != "development_demo" or not plan.conditions:
            raise WizardError("wizard requires a non-empty development_demo plan")
        if runner.backend_type != "fake_full_duplex":
            raise WizardError("wizard accepts only the fake full-duplex backend")
        resolved_root = session_root.resolve()
        self._validate_session_location(session_id, resolved_root)
        if _persist_initial and resolved_root.exists():
            raise WizardError("new demo session directory already exists; recover it explicitly")
        self.plan = plan
        self.runner = runner
        self.session_id = session_id
        self.session_root = resolved_root
        self._now = now or (lambda: datetime.now(UTC))
        self._state_store = DemoSessionStateStore(self.session_root)
        self.state = WizardState.WAITING_USER_ASSEMBLY
        self.condition_index = 0
        self.completed_repeat_count = 0
        self._confirmations = dict.fromkeys(Confirmation, False)
        self._completed_condition_ids: list[str] = []
        self._error_message = ""
        self._last_capture_summary = "尚无 fake capture 结果"
        self._resume_state: WizardState | None = None
        self._pause_requested = False
        self._lock = RLock()
        self._current_cancellation: CancellationToken | None = None
        if _persist_initial:
            self._persist()

    @staticmethod
    def _validate_session_location(session_id: str, session_root: Path) -> None:
        if (
            not _SAFE_IDENTIFIER.fullmatch(session_id)
            or session_id in {".", ".."}
            or session_root.name != session_id
        ):
            raise WizardError("demo session_id and session directory must be safe and identical")
        parts = tuple(part.casefold() for part in session_root.parts)
        if not any(
            parts[index : index + 2] == ("development", "demo") for index in range(len(parts) - 1)
        ):
            raise WizardError("demo session must be stored below a development/demo root")

    def _state_payload(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "session_id": self.session_id,
            "mode": self.plan.mode,
            "current_stage": self.plan.conditions[self.condition_index].stage,
            "current_condition_index": self.condition_index,
            "current_repeat": self.completed_repeat_count,
            "completed_conditions": list(self._completed_condition_ids),
            "controller_state": self.state.value,
            "resume_state": self._resume_state.value if self._resume_state else None,
            "confirmations": {
                confirmation.value: value for confirmation, value in self._confirmations.items()
            },
            "demo_data_root": str(self.session_root.parent),
            "last_updated_at": self._now().isoformat(),
            "plan_sha256": demo_plan_sha256(self.plan),
        }

    def _persist(self) -> None:
        if self.state in {WizardState.RUNNING_REPEAT_1, WizardState.RUNNING_REPEAT_2}:
            return
        try:
            self._state_store.write(self._state_payload())
        except DemoSessionStateError as exc:
            raise WizardError(str(exc)) from exc

    @classmethod
    def recover(
        cls,
        *,
        plan: DemoPlan,
        runner: FakeDemoCaptureRunner,
        session_id: str,
        session_root: Path,
        now: Callable[[], datetime] | None = None,
    ) -> ExperimentWizardController:
        resolved_root = session_root.resolve()
        cls._validate_session_location(session_id, resolved_root)
        try:
            payload = DemoSessionStateStore(resolved_root).read()
            validated = cls._validate_recovery_payload(
                payload, plan=plan, session_id=session_id, session_root=resolved_root
            )
        except (DemoSessionStateError, KeyError, TypeError, ValueError) as exc:
            raise WizardRecoveryError(f"saved demo state was rejected: {exc}") from exc
        controller = cls(
            plan=plan,
            runner=runner,
            session_id=session_id,
            session_root=resolved_root,
            now=now,
            _persist_initial=False,
        )
        controller.condition_index = validated["condition_index"]
        controller.completed_repeat_count = validated["repeat_count"]
        controller._completed_condition_ids = validated["completed_conditions"]
        controller.state = validated["state"]
        controller._resume_state = validated["resume_state"]
        controller._confirmations = validated["confirmations"]
        if controller.state in {WizardState.CANCELLED, WizardState.ERROR}:
            controller.state = (
                WizardState.BETWEEN_REPEATS
                if controller.completed_repeat_count
                else WizardState.READY
                if all(controller._confirmations.values())
                else WizardState.WAITING_USER_ASSEMBLY
            )
        return controller

    @staticmethod
    def _validate_recovery_payload(
        payload: dict[str, object],
        *,
        plan: DemoPlan,
        session_id: str,
        session_root: Path,
    ) -> _ValidatedRecoveryState:
        required = {
            "schema_version",
            "session_id",
            "mode",
            "current_stage",
            "current_condition_index",
            "current_repeat",
            "completed_conditions",
            "controller_state",
            "resume_state",
            "confirmations",
            "demo_data_root",
            "last_updated_at",
            "plan_sha256",
        }
        missing = required - payload.keys()
        if missing:
            raise ValueError(f"missing fields: {sorted(missing)}")
        if payload["schema_version"] != "1.0.0":
            raise ValueError("unsupported schema_version")
        if payload["session_id"] != session_id or payload["mode"] != plan.mode:
            raise ValueError("session identity does not match")
        if Path(str(payload["demo_data_root"])).resolve() != session_root.parent:
            raise ValueError("demo data root does not match")
        if payload["plan_sha256"] != demo_plan_sha256(plan):
            raise ValueError("demo plan hash does not match")
        condition_index = payload["current_condition_index"]
        repeat_count = payload["current_repeat"]
        if (
            isinstance(condition_index, bool)
            or not isinstance(condition_index, int)
            or not 0 <= condition_index < len(plan.conditions)
        ):
            raise ValueError("current_condition_index is invalid")
        if (
            isinstance(repeat_count, bool)
            or not isinstance(repeat_count, int)
            or not 0 <= repeat_count <= plan.repeat_count
        ):
            raise ValueError("current_repeat is invalid")
        if payload["current_stage"] != plan.conditions[condition_index].stage:
            raise ValueError("current stage does not match condition")
        completed = payload["completed_conditions"]
        if not isinstance(completed, list) or not all(
            isinstance(condition_id, str) for condition_id in completed
        ):
            raise ValueError("completed_conditions must be a string list")
        completed_count = (
            len(plan.conditions)
            if payload["controller_state"] == WizardState.ALL_COMPLETE.value
            else condition_index
        )
        expected = [condition.condition_id for condition in plan.conditions[:completed_count]]
        if completed != expected:
            raise ValueError("completed condition prefix is invalid")
        try:
            state = WizardState(str(payload["controller_state"]))
        except ValueError as exc:
            raise ValueError("controller_state is invalid") from exc
        if state in {WizardState.RUNNING_REPEAT_1, WizardState.RUNNING_REPEAT_2}:
            raise ValueError("running state is not a recoverable boundary")
        raw_resume = payload["resume_state"]
        resume_state = None if raw_resume is None else WizardState(str(raw_resume))
        if state is WizardState.PAUSED and resume_state not in {
            WizardState.WAITING_USER_ASSEMBLY,
            WizardState.READY,
            WizardState.BETWEEN_REPEATS,
        }:
            raise ValueError("paused state has no valid resume boundary")
        raw_confirmations = payload["confirmations"]
        if not isinstance(raw_confirmations, dict):
            raise ValueError("confirmations must be an object")
        confirmations: dict[Confirmation, bool] = {}
        for confirmation in Confirmation:
            value = raw_confirmations.get(confirmation.value)
            if not isinstance(value, bool):
                raise ValueError("confirmation values must be booleans")
            confirmations[confirmation] = value
        completed_repeats = {
            (index, repeat)
            for index in range(completed_count)
            for repeat in range(1, plan.repeat_count + 1)
        }
        if state is not WizardState.ALL_COMPLETE:
            completed_repeats.update(
                (condition_index, repeat) for repeat in range(1, repeat_count + 1)
            )
        for index, repeat in completed_repeats:
            bundle = session_root / "captures" / f"condition_{index + 1:03d}" / f"repeat_{repeat}"
            if (
                not bundle.is_dir()
                or {entry.name for entry in bundle.iterdir()} != _CAPTURE_FILE_NAMES
            ):
                raise ValueError("saved repeat does not have a complete fake capture bundle")
        return {
            "condition_index": condition_index,
            "repeat_count": repeat_count,
            "completed_conditions": list(completed),
            "state": state,
            "resume_state": resume_state,
            "confirmations": confirmations,
        }

    def snapshot(self) -> WizardSnapshot:
        return WizardSnapshot(
            session_id=self.session_id,
            mode=self.plan.mode,
            state=self.state,
            condition_index=self.condition_index,
            condition_count=len(self.plan.conditions),
            completed_repeat_count=self.completed_repeat_count,
            total_repeat_count=self.plan.repeat_count,
            condition=self.plan.conditions[self.condition_index],
            confirmations=dict(self._confirmations),
            can_start=self.state is WizardState.READY,
            error_message=self._error_message,
            last_capture_summary=self._last_capture_summary,
        )

    def set_confirmation(self, confirmation: Confirmation, value: bool) -> WizardSnapshot:
        if self.state not in {
            WizardState.WAITING_USER_ASSEMBLY,
            WizardState.READY,
        }:
            raise WizardError("confirmations can change only while waiting for assembly")
        self._confirmations[confirmation] = value
        self.state = (
            WizardState.READY
            if all(self._confirmations.values())
            else WizardState.WAITING_USER_ASSEMBLY
        )
        self._persist()
        return self.snapshot()

    def request_pause(self) -> WizardSnapshot:
        if self.state in {
            WizardState.RUNNING_REPEAT_1,
            WizardState.RUNNING_REPEAT_2,
        }:
            self._pause_requested = True
            return self.snapshot()
        if self.state not in {
            WizardState.WAITING_USER_ASSEMBLY,
            WizardState.READY,
            WizardState.BETWEEN_REPEATS,
        }:
            raise WizardError("pause is allowed only at a workflow boundary")
        self._resume_state = self.state
        self.state = WizardState.PAUSED
        self._persist()
        return self.snapshot()

    def resume(self) -> WizardSnapshot:
        if self.state is not WizardState.PAUSED or self._resume_state is None:
            raise WizardError("wizard is not paused")
        target = self._resume_state
        self._resume_state = None
        self.state = target
        self._persist()
        return self.snapshot()

    def emergency_stop(self) -> WizardSnapshot:
        with self._lock:
            cancellation = self._current_cancellation
            if cancellation is None:
                self.state = WizardState.CANCELLED
                self._persist()
            else:
                cancellation.cancel()
            return self.snapshot()

    def run_current_condition(self) -> WizardSnapshot:
        if self.state not in {
            WizardState.READY,
            WizardState.BETWEEN_REPEATS,
        }:
            raise WizardError("current condition is not ready to run")
        condition = self.plan.conditions[self.condition_index]
        for repeat_index in range(self.completed_repeat_count + 1, self.plan.repeat_count + 1):
            self.state = (
                WizardState.RUNNING_REPEAT_1 if repeat_index == 1 else WizardState.RUNNING_REPEAT_2
            )
            cancellation = CancellationToken()
            target = (
                self.session_root
                / "captures"
                / f"condition_{self.condition_index + 1:03d}"
                / f"repeat_{repeat_index}"
            )
            try:
                self._current_cancellation = cancellation
                result = self.runner.capture_repeat(
                    condition=condition,
                    repeat_index=repeat_index,
                    target=target,
                    run_id=(f"{self.session_id}-c{self.condition_index + 1:03d}-r{repeat_index}"),
                    cancellation=cancellation,
                )
            except PilotCaptureError as exc:
                self.state = (
                    WizardState.CANCELLED
                    if exc.state is CaptureState.CANCELLED
                    else WizardState.ERROR
                )
                self._error_message = str(exc)
                self._persist()
                return self.snapshot()
            finally:
                self._current_cancellation = None
            self.completed_repeat_count = repeat_index
            self._last_capture_summary = (
                f"重复 {repeat_index}/{self.plan.repeat_count} 完成: "
                f"{result.bundle_path.name} ({result.state.value})"
            )
            self.state = WizardState.BETWEEN_REPEATS
            self._persist()
            if repeat_index < self.plan.repeat_count and self._pause_requested:
                self._pause_requested = False
                self._resume_state = WizardState.BETWEEN_REPEATS
                self.state = WizardState.PAUSED
                self._persist()
                return self.snapshot()
        self.state = WizardState.CONDITION_COMPLETE
        self._completed_condition_ids.append(condition.condition_id)
        if self.condition_index + 1 == len(self.plan.conditions):
            self.state = WizardState.ALL_COMPLETE
        else:
            self.condition_index += 1
            self.completed_repeat_count = 0
            self._confirmations = dict.fromkeys(Confirmation, False)
            self.state = WizardState.WAITING_USER_ASSEMBLY
        self._persist()
        return self.snapshot()

    def save_state(self) -> None:
        """Persist the current safe boundary before a normal UI exit."""
        self._persist()
