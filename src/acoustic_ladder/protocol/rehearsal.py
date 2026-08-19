"""Create-only, offline development protocol rehearsal ledger."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.protocol.planning import LoadedDevelopmentProtocolPlanSpec
from acoustic_ladder.protocol.planning_models import (
    CompiledDevelopmentProtocolPlan,
    PublishedDevelopmentProtocolPlan,
)
from acoustic_ladder.protocol.planning_persistence import (
    DevelopmentProtocolPlanStore,
    ProtocolPlanPersistenceError,
    validate_development_protocol_plan,
)
from acoustic_ladder.protocol.rehearsal_models import (
    REHEARSAL_SAFETY_MARKER,
    ZERO_EVENT_SHA256,
    ProtocolRehearsalCompletion,
    ProtocolRehearsalConcurrencyToken,
    ProtocolRehearsalEvent,
    ProtocolRehearsalManifest,
    ProtocolRehearsalRecord,
    ProtocolRehearsalStatus,
    ProtocolRehearsalTransitionCommand,
    ProtocolRehearsalWorkOrder,
)
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes

INITIALIZED_NAME = "REHEARSAL_INITIALIZED"
INITIALIZED_BYTES = b"initialized\n"
BASE_NAMES = frozenset(
    {
        "protocol_rehearsal_manifest.json",
        "protocol_rehearsal_manifest.sha256",
        "protocol_rehearsal_record.json",
        "protocol_rehearsal_record.sha256",
        INITIALIZED_NAME,
        "events",
    }
)
COMPLETION_NAME = "protocol_rehearsal_completion.json"
COMPLETION_SIDECAR_NAME = "protocol_rehearsal_completion.sha256"
COMPLETE_MARKER_NAME = "PROTOCOL_REHEARSAL_COMPLETE"
COMPLETE_MARKER_BYTES = b"complete\n"
COMPLETION_NAMES = frozenset({COMPLETION_NAME, COMPLETION_SIDECAR_NAME, COMPLETE_MARKER_NAME})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_EVENT_FILE = re.compile(r"^event_([0-9]{8})\.(json|sha256)$")


@dataclass(frozen=True)
class _ReplayState:
    rehearsal_state: str
    phase: str | None
    cursor: int
    event_sequence: int
    head_sha256: str
    requirements_presented: bool


class ProtocolRehearsalError(StorageError):
    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(message)
        self.published = published


def _identifier(value: str, label: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None or value in {".", ".."}:
        raise ProtocolRehearsalError(
            f"{label} must be a safe ASCII identifier: {value!r}", published=False
        )
    return value


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _reject_reparse_entries(root: Path) -> None:
    for entry in root.iterdir():
        if _is_reparse_point(entry):
            raise ProtocolRehearsalError(
                f"rehearsal envelope contains a symlink or reparse point: {entry.name}",
                published=True,
            )
    events = root / "events"
    if events.is_dir():
        for entry in events.iterdir():
            if _is_reparse_point(entry):
                raise ProtocolRehearsalError(
                    f"rehearsal ledger contains a symlink or reparse point: {entry.name}",
                    published=True,
                )


def _false_state() -> dict[str, object]:
    return {
        "development_rehearsal": True,
        "requirements_presented_for_rehearsal": False,
        "physical_operator_confirmation_performed": False,
        "operator_confirmation_status": "pending",
        "protocol_execution_performed": False,
        "measurement_performed": False,
        "hardware_io_performed": False,
        "hardware_ready": False,
        "formal_eligible": False,
        "experimental_result": False,
        "safety_marker": REHEARSAL_SAFETY_MARKER,
    }


class DevelopmentProtocolRehearsalStore:
    """Single-purpose rehearsal root with no real/synthetic/session axis."""

    def __init__(self, development_rehearsal_root: str | Path) -> None:
        self.root = Path(development_rehearsal_root).resolve()

    def rehearsal_path(self, rehearsal_id: str) -> Path:
        _identifier(rehearsal_id, "rehearsal_id")
        parent = (self.root / "rehearsals").resolve()
        target = (parent / f"rehearsal_{rehearsal_id}").resolve()
        if target.parent != parent or not target.is_relative_to(self.root):
            raise ProtocolRehearsalError("rehearsal path escapes development root", published=False)
        return target

    def initialize(
        self,
        *,
        rehearsal_id: str,
        manifest_bytes: bytes,
        record_bytes: bytes,
    ) -> Path:
        target = self.rehearsal_path(rehearsal_id)
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ProtocolRehearsalError("protocol rehearsal already exists", published=False)
        lock = parent / f".{rehearsal_id}.initialize.lock"
        descriptor: int | None = None
        staging: Path | None = None
        published = False
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if target.exists():
                raise ProtocolRehearsalError("protocol rehearsal already exists", published=False)
            staging = Path(tempfile.mkdtemp(prefix=f".{rehearsal_id}.staging-", dir=parent))
            manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
            record_sha = hashlib.sha256(record_bytes).hexdigest()
            atomic_write_bytes(staging / "protocol_rehearsal_manifest.json", manifest_bytes)
            atomic_write_bytes(
                staging / "protocol_rehearsal_manifest.sha256",
                _sidecar(manifest_sha, "protocol_rehearsal_manifest.json"),
            )
            atomic_write_bytes(staging / "protocol_rehearsal_record.json", record_bytes)
            atomic_write_bytes(
                staging / "protocol_rehearsal_record.sha256",
                _sidecar(record_sha, "protocol_rehearsal_record.json"),
            )
            atomic_write_bytes(staging / INITIALIZED_NAME, INITIALIZED_BYTES)
            (staging / "events").mkdir()
            os.rename(staging, target)
            published = True
            return target
        except FileExistsError as exc:
            raise ProtocolRehearsalError(
                "protocol rehearsal initialization is already in progress", published=False
            ) from exc
        except ProtocolRehearsalError:
            raise
        except Exception as exc:
            raise ProtocolRehearsalError(str(exc), published=published) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)
            if not published and staging is not None and staging.exists():
                shutil.rmtree(staging)


def _work_orders(
    published: PublishedDevelopmentProtocolPlan,
) -> list[ProtocolRehearsalWorkOrder]:
    plan = published.plan
    conditions = {condition.condition_id: condition for condition in plan.condition_matrix}
    work_orders: list[ProtocolRehearsalWorkOrder] = []
    for session in plan.session_slots:
        for reassembly in session.reassembly_slots:
            for block in reassembly.condition_blocks:
                condition = conditions[block.condition_id]
                for measurement in block.measurements:
                    core: dict[str, object] = {
                        "work_order_schema_version": "1.0.0",
                        "plan_id": plan.plan_id,
                        "compiled_plan_sha256": published.plan_sha256,
                        "protocol_plan_receipt_sha256": published.receipt_sha256,
                        "experiment_stage": plan.experiment_stage,
                        "global_planned_ordinal": measurement.global_planned_ordinal,
                        "session_local_measurement_order": (
                            measurement.session_local_measurement_order
                        ),
                        "session_index": measurement.session_index,
                        "reassembly_index": measurement.reassembly_index,
                        "condition_block_order": measurement.condition_block_order,
                        "canonical_condition_index": block.canonical_condition_index,
                        "continuous_repeat_index": measurement.continuous_repeat_index,
                        "condition_id": condition.condition_id,
                        "condition_role": condition.condition_role,
                        "condition_label": condition.condition_label,
                        "condition_node_state_sha256": condition.node_state_sha256,
                        "node_states": condition.node_states,
                        "selected_nodes": condition.selected_nodes,
                        "selected_modules": condition.selected_modules,
                        "operator_confirmation_requirements": (
                            condition.operator_confirmation_requirements
                        ),
                        "operator_confirmation_status": "pending",
                        "development_rehearsal": True,
                        "requirements_presented_for_rehearsal": False,
                        "physical_operator_confirmation_performed": False,
                        "protocol_execution_performed": False,
                        "measurement_performed": False,
                        "hardware_io_performed": False,
                        "hardware_ready": False,
                        "formal_eligible": False,
                        "experimental_result": False,
                        "safety_marker": REHEARSAL_SAFETY_MARKER,
                    }
                    digest_core = {
                        **core,
                        "node_states": {
                            key: value.model_dump(mode="json")
                            for key, value in condition.node_states.items()
                        },
                    }
                    work_orders.append(
                        ProtocolRehearsalWorkOrder.model_validate(
                            {
                                **core,
                                "work_order_sha256": hashlib.sha256(
                                    canonical_json_bytes(digest_core)
                                ).hexdigest(),
                            }
                        )
                    )
    return work_orders


def _manifest(
    rehearsal_id: str,
    published: PublishedDevelopmentProtocolPlan,
    work_orders: list[ProtocolRehearsalWorkOrder],
) -> ProtocolRehearsalManifest:
    plan = published.plan
    aggregate = hashlib.sha256(
        canonical_json_bytes([order.work_order_sha256 for order in work_orders])
    ).hexdigest()
    return ProtocolRehearsalManifest.model_validate(
        {
            "schema_version": "1.0.0",
            "rehearsal_id": rehearsal_id,
            "plan_id": plan.plan_id,
            "plan_spec_id": plan.plan_spec_id,
            "plan_spec_reference": plan.plan_spec_reference,
            "plan_spec_raw_sha256": plan.plan_spec_raw_sha256,
            "plan_spec_normalized_sha256": plan.plan_spec_normalized_sha256,
            "protocol_id": plan.protocol_id,
            "protocol_version": plan.protocol_version,
            "protocol_reference": plan.protocol_reference,
            "protocol_raw_sha256": plan.protocol_raw_sha256,
            "protocol_normalized_sha256": plan.protocol_normalized_sha256,
            "experiment_stage": plan.experiment_stage,
            "manifest_sha256": plan.manifest_sha256,
            "model_package_sha256": plan.model_package_sha256,
            "bundle_content_sha256": plan.bundle_content_sha256,
            "compiled_plan_sha256": published.plan_sha256,
            "protocol_plan_receipt_sha256": published.receipt_sha256,
            "condition_matrix_sha256": plan.condition_matrix_sha256,
            "schedule_sha256": plan.schedule_sha256,
            "condition_count": plan.condition_count,
            "planned_measurement_count": plan.planned_measurement_count,
            "session_count": plan.session_count,
            "reassemblies_per_session": plan.reassemblies_per_session,
            "continuous_repeats_per_condition": plan.continuous_repeats_per_condition,
            "randomization_enabled": plan.randomization_enabled,
            "randomization_algorithm_id": plan.randomization_algorithm_id,
            "randomization_algorithm_version": plan.randomization_algorithm_version,
            "random_seed": plan.random_seed,
            "ordered_work_order_sha256": aggregate,
            **_false_state(),
        }
    )


def _record(
    rehearsal_id: str,
    manifest_sha256: str,
    created_at: datetime,
) -> ProtocolRehearsalRecord:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProtocolRehearsalError("rehearsal time must be timezone-aware", published=False)
    return ProtocolRehearsalRecord.model_validate(
        {
            "schema_version": "1.0.0",
            "rehearsal_id": rehearsal_id,
            "rehearsal_relative_path": f"rehearsals/rehearsal_{rehearsal_id}",
            "created_at": created_at,
            "manifest_sha256": manifest_sha256,
            "immutable_status": "initialized",
            **_false_state(),
        }
    )


def _validated_plan(
    *,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
) -> PublishedDevelopmentProtocolPlan:
    try:
        return validate_development_protocol_plan(
            store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id
        )
    except ProtocolPlanPersistenceError as exc:
        raise ProtocolRehearsalError(str(exc), published=False) from exc


def _transition(state: _ReplayState, action: str, total: int) -> _ReplayState:
    if action == "present-requirements":
        if state.rehearsal_state != "active" or state.phase != "awaiting_requirements_presentation":
            raise ProtocolRehearsalError(
                "requirements cannot be presented in this state", published=False
            )
        return _ReplayState(
            "active",
            "requirements_presented",
            state.cursor,
            state.event_sequence + 1,
            state.head_sha256,
            True,
        )
    if action == "claim":
        if state.rehearsal_state != "active" or state.phase != "requirements_presented":
            raise ProtocolRehearsalError(
                "work order cannot be claimed in this state", published=False
            )
        return _ReplayState(
            "active", "claimed", state.cursor, state.event_sequence + 1, state.head_sha256, True
        )
    if action == "mark-rehearsed":
        if state.rehearsal_state != "active" or state.phase != "claimed":
            raise ProtocolRehearsalError(
                "work order cannot be rehearsed in this state", published=False
            )
        cursor = state.cursor + 1
        if cursor > total:
            raise ProtocolRehearsalError("rehearsal cursor exceeds the plan", published=False)
        complete = cursor == total
        return _ReplayState(
            "complete" if complete else "active",
            None if complete else "awaiting_requirements_presentation",
            cursor,
            state.event_sequence + 1,
            state.head_sha256,
            False,
        )
    if action == "pause":
        if state.rehearsal_state != "active" or state.phase not in {
            "awaiting_requirements_presentation",
            "requirements_presented",
        }:
            raise ProtocolRehearsalError("rehearsal cannot pause in this state", published=False)
        return _ReplayState(
            "paused",
            state.phase,
            state.cursor,
            state.event_sequence + 1,
            state.head_sha256,
            state.requirements_presented,
        )
    if action == "resume":
        if state.rehearsal_state != "paused" or state.phase not in {
            "awaiting_requirements_presentation",
            "requirements_presented",
        }:
            raise ProtocolRehearsalError("rehearsal cannot resume in this state", published=False)
        return _ReplayState(
            "active",
            state.phase,
            state.cursor,
            state.event_sequence + 1,
            state.head_sha256,
            state.requirements_presented,
        )
    if action == "mark-failed":
        if state.rehearsal_state != "active" or state.phase != "claimed":
            raise ProtocolRehearsalError("work order cannot fail in this state", published=False)
        return _ReplayState(
            "failed", "failed", state.cursor, state.event_sequence + 1, state.head_sha256, True
        )
    if action == "retry":
        if state.rehearsal_state != "failed" or state.phase != "failed":
            raise ProtocolRehearsalError("work order cannot retry in this state", published=False)
        return _ReplayState(
            "active",
            "awaiting_requirements_presentation",
            state.cursor,
            state.event_sequence + 1,
            state.head_sha256,
            False,
        )
    if action == "abort":
        if state.rehearsal_state in {"aborted", "complete"}:
            raise ProtocolRehearsalError("terminal rehearsal cannot be aborted", published=False)
        return _ReplayState(
            "aborted",
            state.phase,
            state.cursor,
            state.event_sequence + 1,
            state.head_sha256,
            state.requirements_presented,
        )
    raise ProtocolRehearsalError(f"unsupported rehearsal action: {action}", published=False)


def _event_type(action: str) -> str:
    return {
        "present-requirements": "requirements_presented",
        "claim": "work_order_claimed",
        "mark-rehearsed": "work_order_rehearsed",
        "pause": "rehearsal_paused",
        "resume": "rehearsal_resumed",
        "mark-failed": "work_order_failed",
        "retry": "work_order_retry_requested",
        "abort": "rehearsal_aborted",
    }[action]


def _action(event_type: str) -> str:
    return {
        "requirements_presented": "present-requirements",
        "work_order_claimed": "claim",
        "work_order_rehearsed": "mark-rehearsed",
        "rehearsal_paused": "pause",
        "rehearsal_resumed": "resume",
        "work_order_failed": "mark-failed",
        "work_order_retry_requested": "retry",
        "rehearsal_aborted": "abort",
    }[event_type]


def _expected_event(
    *,
    rehearsal_id: str,
    plan: CompiledDevelopmentProtocolPlan,
    state: _ReplayState,
    work_order: ProtocolRehearsalWorkOrder,
    command: ProtocolRehearsalTransitionCommand,
    recorded_at: datetime,
    total: int,
) -> tuple[ProtocolRehearsalEvent, _ReplayState]:
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ProtocolRehearsalError("rehearsal event time must be timezone-aware", published=False)
    after = _transition(state, command.action, total)
    safety = {
        **_false_state(),
        "requirements_presented_for_rehearsal": after.requirements_presented,
    }
    event = ProtocolRehearsalEvent.model_validate(
        {
            "schema_version": "1.0.0",
            "rehearsal_id": rehearsal_id,
            "event_sequence": state.event_sequence + 1,
            "event_type": _event_type(command.action),
            "previous_event_sha256": state.head_sha256,
            "plan_id": plan.plan_id,
            "compiled_plan_sha256": work_order.compiled_plan_sha256,
            "current_work_order_sha256": work_order.work_order_sha256,
            "rehearsal_actor_id": command.rehearsal_actor_id,
            "before_rehearsal_state": state.rehearsal_state,
            "after_rehearsal_state": after.rehearsal_state,
            "before_work_order_phase": state.phase,
            "after_work_order_phase": after.phase,
            "derived_cursor_before": state.cursor,
            "derived_cursor_after": after.cursor,
            "reason_code": command.reason_code,
            "detail": command.detail,
            "recorded_at": recorded_at,
            **safety,
        }
    )
    return event, after


def _replay_events(
    *,
    root: Path,
    rehearsal_id: str,
    plan: CompiledDevelopmentProtocolPlan,
    orders: list[ProtocolRehearsalWorkOrder],
) -> _ReplayState:
    events_root = root / "events"
    if not events_root.is_dir():
        raise ProtocolRehearsalError("rehearsal events entry is not a directory", published=True)
    entries = list(events_root.iterdir())
    if any(not item.is_file() for item in entries):
        raise ProtocolRehearsalError("rehearsal event ledger contains a non-file", published=True)
    pairs: dict[int, set[str]] = {}
    for item in entries:
        match = _EVENT_FILE.fullmatch(item.name)
        if match is None:
            raise ProtocolRehearsalError(
                "rehearsal event ledger contains an extra file", published=True
            )
        pairs.setdefault(int(match.group(1)), set()).add(match.group(2))
    if sorted(pairs) != list(range(1, len(pairs) + 1)) or any(
        extensions != {"json", "sha256"} for extensions in pairs.values()
    ):
        raise ProtocolRehearsalError("rehearsal event sequence is incomplete", published=True)
    state = _ReplayState(
        "active", "awaiting_requirements_presentation", 0, 0, ZERO_EVENT_SHA256, False
    )
    for sequence in sorted(pairs):
        filename = f"event_{sequence:08d}.json"
        event_bytes = (events_root / filename).read_bytes()
        digest = hashlib.sha256(event_bytes).hexdigest()
        if (events_root / f"event_{sequence:08d}.sha256").read_bytes() != _sidecar(
            digest, filename
        ):
            raise ProtocolRehearsalError("non-canonical rehearsal event sidecar", published=True)
        event = ProtocolRehearsalEvent.model_validate_json(event_bytes)
        if event_bytes != canonical_json_bytes(event.model_dump(mode="json")):
            raise ProtocolRehearsalError("rehearsal event JSON is not canonical", published=True)
        if event.event_sequence != sequence or event.previous_event_sha256 != state.head_sha256:
            raise ProtocolRehearsalError("rehearsal event hash chain is invalid", published=True)
        if state.cursor >= len(orders):
            raise ProtocolRehearsalError(
                "event exists after terminal rehearsal state", published=True
            )
        order = orders[state.cursor]
        try:
            action = _action(event.event_type)
        except KeyError as exc:
            raise ProtocolRehearsalError("unsupported event type", published=True) from exc
        command = ProtocolRehearsalTransitionCommand.model_validate(
            {
                "action": action,
                "rehearsal_actor_id": event.rehearsal_actor_id,
                "expected_event_sequence": state.event_sequence,
                "expected_head_sha256": state.head_sha256,
                "expected_current_work_order_sha256": order.work_order_sha256,
                "reason_code": event.reason_code,
                "detail": event.detail,
            }
        )
        try:
            expected, after = _expected_event(
                rehearsal_id=rehearsal_id,
                plan=plan,
                state=state,
                work_order=order,
                command=command,
                recorded_at=event.recorded_at,
                total=len(orders),
            )
        except ProtocolRehearsalError as exc:
            raise ProtocolRehearsalError(str(exc), published=True) from exc
        if event != expected:
            raise ProtocolRehearsalError("rehearsal event replay mismatch", published=True)
        state = _ReplayState(
            after.rehearsal_state,
            after.phase,
            after.cursor,
            sequence,
            digest,
            after.requirements_presented,
        )
    return state


def _status(
    rehearsal_id: str,
    orders: list[ProtocolRehearsalWorkOrder],
    state: _ReplayState,
) -> ProtocolRehearsalStatus:
    order = orders[state.cursor] if state.cursor < len(orders) else None
    current_sha = order.work_order_sha256 if order is not None else ZERO_EVENT_SHA256
    safety = {
        **_false_state(),
        "requirements_presented_for_rehearsal": state.requirements_presented,
    }
    return ProtocolRehearsalStatus.model_validate(
        {
            "rehearsal_id": rehearsal_id,
            "rehearsal_state": state.rehearsal_state,
            "current_work_order_phase": state.phase,
            "current_work_order": order,
            "cursor": state.cursor,
            "total_work_order_count": len(orders),
            "rehearsed_work_order_count": state.cursor,
            "concurrency_token": {
                "rehearsal_id": rehearsal_id,
                "event_sequence": state.event_sequence,
                "head_event_sha256": state.head_sha256,
                "current_work_order_sha256": current_sha,
            },
            **safety,
        }
    )


def _event_digests(events_root: Path) -> list[str]:
    json_files = sorted(events_root.glob("event_????????.json"))
    return [hashlib.sha256(path.read_bytes()).hexdigest() for path in json_files]


def _completion(
    *,
    rehearsal_id: str,
    published: PublishedDevelopmentProtocolPlan,
    state: _ReplayState,
    event_digests: list[str],
) -> ProtocolRehearsalCompletion:
    return ProtocolRehearsalCompletion.model_validate(
        {
            "schema_version": "1.0.0",
            "rehearsal_id": rehearsal_id,
            "plan_id": published.plan.plan_id,
            "compiled_plan_sha256": published.plan_sha256,
            "protocol_plan_receipt_sha256": published.receipt_sha256,
            "schedule_sha256": published.plan.schedule_sha256,
            "expected_work_order_count": published.plan.planned_measurement_count,
            "rehearsed_work_order_count": state.cursor,
            "final_event_sequence": state.event_sequence,
            "final_event_sha256": state.head_sha256,
            "ordered_event_aggregate_sha256": hashlib.sha256(
                canonical_json_bytes(event_digests)
            ).hexdigest(),
            "completion_state": "complete",
            **_false_state(),
        }
    )


def _publish_completion(root: Path, completion: ProtocolRehearsalCompletion) -> None:
    payload = canonical_json_bytes(completion.model_dump(mode="json"))
    digest = hashlib.sha256(payload).hexdigest()
    staging = Path(tempfile.mkdtemp(prefix=".completion.staging-", dir=root))
    published: list[Path] = []
    try:
        atomic_write_bytes(staging / COMPLETION_NAME, payload)
        atomic_write_bytes(staging / COMPLETION_SIDECAR_NAME, _sidecar(digest, COMPLETION_NAME))
        atomic_write_bytes(staging / COMPLETE_MARKER_NAME, COMPLETE_MARKER_BYTES)
        for filename in (COMPLETION_NAME, COMPLETION_SIDECAR_NAME, COMPLETE_MARKER_NAME):
            target = root / filename
            os.link(staging / filename, target)
            published.append(target)
    except FileExistsError as exc:
        raise ProtocolRehearsalError("rehearsal completion already exists", published=True) from exc
    finally:
        if len(published) != 3:
            for path in published:
                path.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=False)


def _validate_completion(
    *,
    root: Path,
    rehearsal_id: str,
    published: PublishedDevelopmentProtocolPlan,
    state: _ReplayState,
) -> None:
    payload = (root / COMPLETION_NAME).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if (root / COMPLETION_SIDECAR_NAME).read_bytes() != _sidecar(digest, COMPLETION_NAME):
        raise ProtocolRehearsalError("non-canonical rehearsal completion sidecar", published=True)
    if (root / COMPLETE_MARKER_NAME).read_bytes() != COMPLETE_MARKER_BYTES:
        raise ProtocolRehearsalError("non-canonical rehearsal completion marker", published=True)
    stored = ProtocolRehearsalCompletion.model_validate_json(payload)
    expected = _completion(
        rehearsal_id=rehearsal_id,
        published=published,
        state=state,
        event_digests=_event_digests(root / "events"),
    )
    if stored != expected or payload != canonical_json_bytes(expected.model_dump(mode="json")):
        raise ProtocolRehearsalError("rehearsal completion replay mismatch", published=True)


def initialize_protocol_rehearsal(
    *,
    store: DevelopmentProtocolRehearsalStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    rehearsal_id: str,
    now: Callable[[], datetime],
) -> ProtocolRehearsalStatus:
    _identifier(rehearsal_id, "rehearsal_id")
    published = _validated_plan(plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id)
    orders = _work_orders(published)
    manifest = _manifest(rehearsal_id, published, orders)
    manifest_bytes = canonical_json_bytes(manifest.model_dump(mode="json"))
    record = _record(rehearsal_id, hashlib.sha256(manifest_bytes).hexdigest(), now())
    store.initialize(
        rehearsal_id=rehearsal_id,
        manifest_bytes=manifest_bytes,
        record_bytes=canonical_json_bytes(record.model_dump(mode="json")),
    )
    return read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id=plan_id,
        rehearsal_id=rehearsal_id,
    )


def read_protocol_rehearsal_status(
    *,
    store: DevelopmentProtocolRehearsalStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    rehearsal_id: str,
) -> ProtocolRehearsalStatus:
    published = _validated_plan(plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id)
    root = store.rehearsal_path(rehearsal_id)
    try:
        names = {item.name for item in root.iterdir()} if root.is_dir() else set()
        if not root.is_dir() or names not in {BASE_NAMES, BASE_NAMES | COMPLETION_NAMES}:
            raise ProtocolRehearsalError(
                "protocol rehearsal must contain the exact initialized envelope",
                published=root.exists(),
            )
        _reject_reparse_entries(root)
        if (root / INITIALIZED_NAME).read_bytes() != INITIALIZED_BYTES:
            raise ProtocolRehearsalError("non-canonical rehearsal marker", published=True)
        manifest_bytes = (root / "protocol_rehearsal_manifest.json").read_bytes()
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        if (root / "protocol_rehearsal_manifest.sha256").read_bytes() != _sidecar(
            manifest_sha, "protocol_rehearsal_manifest.json"
        ):
            raise ProtocolRehearsalError("non-canonical rehearsal manifest sidecar", published=True)
        record_bytes = (root / "protocol_rehearsal_record.json").read_bytes()
        record_sha = hashlib.sha256(record_bytes).hexdigest()
        if (root / "protocol_rehearsal_record.sha256").read_bytes() != _sidecar(
            record_sha, "protocol_rehearsal_record.json"
        ):
            raise ProtocolRehearsalError("non-canonical rehearsal record sidecar", published=True)
        stored_manifest = ProtocolRehearsalManifest.model_validate_json(manifest_bytes)
        stored_record = ProtocolRehearsalRecord.model_validate_json(record_bytes)
        orders = _work_orders(published)
        expected_manifest = _manifest(rehearsal_id, published, orders)
        if manifest_bytes != canonical_json_bytes(expected_manifest.model_dump(mode="json")):
            raise ProtocolRehearsalError("rehearsal manifest replay mismatch", published=True)
        expected_record = _record(rehearsal_id, manifest_sha, stored_record.created_at)
        if record_bytes != canonical_json_bytes(expected_record.model_dump(mode="json")):
            raise ProtocolRehearsalError("rehearsal record replay mismatch", published=True)
        if stored_manifest != expected_manifest or stored_record != expected_record:
            raise ProtocolRehearsalError("rehearsal base semantic mismatch", published=True)
        state = _replay_events(
            root=root,
            rehearsal_id=rehearsal_id,
            plan=published.plan,
            orders=orders,
        )
        if state.rehearsal_state == "complete":
            if names != BASE_NAMES | COMPLETION_NAMES:
                raise ProtocolRehearsalError("completed rehearsal lacks completion", published=True)
            _validate_completion(
                root=root,
                rehearsal_id=rehearsal_id,
                published=published,
                state=state,
            )
        elif names != BASE_NAMES:
            raise ProtocolRehearsalError(
                "non-complete rehearsal contains a completion artifact", published=True
            )
    except ProtocolRehearsalError:
        raise
    except (OSError, ValidationError, ValueError) as exc:
        raise ProtocolRehearsalError(str(exc), published=root.exists()) from exc
    return _status(rehearsal_id, orders, state)


def _publish_event_pair(events_root: Path, sequence: int, event_bytes: bytes) -> None:
    filename = f"event_{sequence:08d}.json"
    sidecar_name = f"event_{sequence:08d}.sha256"
    digest = hashlib.sha256(event_bytes).hexdigest()
    staging = Path(tempfile.mkdtemp(prefix=f".event-{sequence:08d}.staging-", dir=events_root))
    body_published = False
    sidecar_published = False
    try:
        atomic_write_bytes(staging / filename, event_bytes)
        atomic_write_bytes(staging / sidecar_name, _sidecar(digest, filename))
        os.link(staging / filename, events_root / filename)
        body_published = True
        os.link(staging / sidecar_name, events_root / sidecar_name)
        sidecar_published = True
    except FileExistsError as exc:
        raise ProtocolRehearsalError(
            "rehearsal event sequence already exists", published=False
        ) from exc
    finally:
        if body_published != sidecar_published:
            if body_published:
                (events_root / filename).unlink(missing_ok=True)
            if sidecar_published:
                (events_root / sidecar_name).unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=False)


def apply_protocol_rehearsal_transition(
    *,
    store: DevelopmentProtocolRehearsalStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    rehearsal_id: str,
    command: ProtocolRehearsalTransitionCommand,
    token: ProtocolRehearsalConcurrencyToken,
    now: Callable[[], datetime],
) -> ProtocolRehearsalStatus:
    root = store.rehearsal_path(rehearsal_id)
    lock = root.parent / f".{rehearsal_id}.transition.lock"
    descriptor: int | None = None
    event_published = False
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        status = read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id=plan_id,
            rehearsal_id=rehearsal_id,
        )
        actual = status.concurrency_token
        if token.rehearsal_id != rehearsal_id or token != actual:
            raise ProtocolRehearsalError(
                "stale or foreign rehearsal concurrency token", published=False
            )
        if (
            command.expected_event_sequence != actual.event_sequence
            or command.expected_head_sha256 != actual.head_event_sha256
            or command.expected_current_work_order_sha256 != actual.current_work_order_sha256
        ):
            raise ProtocolRehearsalError(
                "transition command expectations are stale", published=False
            )
        if status.current_work_order is None:
            raise ProtocolRehearsalError(
                "terminal rehearsal cannot accept transitions", published=False
            )
        published_plan = _validated_plan(
            plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id
        )
        orders = _work_orders(published_plan)
        state = _ReplayState(
            status.rehearsal_state,
            status.current_work_order_phase,
            status.cursor,
            actual.event_sequence,
            actual.head_event_sha256,
            status.requirements_presented_for_rehearsal,
        )
        event, after = _expected_event(
            rehearsal_id=rehearsal_id,
            plan=published_plan.plan,
            state=state,
            work_order=status.current_work_order,
            command=command,
            recorded_at=now(),
            total=len(orders),
        )
        event_bytes = canonical_json_bytes(event.model_dump(mode="json"))
        _publish_event_pair(
            root / "events",
            event.event_sequence,
            event_bytes,
        )
        event_published = True
        if after.rehearsal_state == "complete":
            final_state = _ReplayState(
                after.rehearsal_state,
                after.phase,
                after.cursor,
                event.event_sequence,
                hashlib.sha256(event_bytes).hexdigest(),
                after.requirements_presented,
            )
            _publish_completion(
                root,
                _completion(
                    rehearsal_id=rehearsal_id,
                    published=published_plan,
                    state=final_state,
                    event_digests=_event_digests(root / "events"),
                ),
            )
        return read_protocol_rehearsal_status(
            store=store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id=plan_id,
            rehearsal_id=rehearsal_id,
        )
    except FileExistsError as exc:
        raise ProtocolRehearsalError(
            "protocol rehearsal transition is already in progress", published=False
        ) from exc
    except ProtocolRehearsalError as exc:
        if event_published and not exc.published:
            raise ProtocolRehearsalError(str(exc), published=True) from exc
        raise
    except Exception as exc:
        raise ProtocolRehearsalError(str(exc), published=event_published) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink(missing_ok=True)


def validate_protocol_rehearsal(
    *,
    store: DevelopmentProtocolRehearsalStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    rehearsal_id: str,
) -> ProtocolRehearsalStatus:
    return read_protocol_rehearsal_status(
        store=store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id=plan_id,
        rehearsal_id=rehearsal_id,
    )


__all__ = [
    "DevelopmentProtocolRehearsalStore",
    "ProtocolRehearsalError",
    "apply_protocol_rehearsal_transition",
    "initialize_protocol_rehearsal",
    "read_protocol_rehearsal_status",
    "validate_protocol_rehearsal",
]
