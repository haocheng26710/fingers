"""Recoverable synthetic-only execution of replay-validated development plans."""

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

from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    LoadedConditionedVirtualCaptureScenario,
    load_conditioned_virtual_capture_scenario,
)
from acoustic_ladder.audio.excitation_persistence import (
    EssArtifactError,
    validate_offline_ess_artifact,
)
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.domain.models import DataOrigin, ReassemblyRecord, RunMode, SessionRecord
from acoustic_ladder.protocol.plan_bound_capture import (
    PlanBoundSyntheticCaptureError,
    PublishedPlanBoundSyntheticCapture,
    publish_plan_bound_synthetic_capture,
    validate_plan_bound_synthetic_capture,
    validate_plan_bound_synthetic_capture_binding,
)
from acoustic_ladder.protocol.planning import LoadedDevelopmentProtocolPlanSpec
from acoustic_ladder.protocol.planning_models import PublishedDevelopmentProtocolPlan
from acoustic_ladder.protocol.planning_persistence import (
    DevelopmentProtocolPlanStore,
    ProtocolPlanPersistenceError,
    validate_development_protocol_plan,
)
from acoustic_ladder.protocol.synthetic_execution_models import (
    EXECUTION_SAFETY_MARKER,
    ZERO_EVENT_SHA256,
    SyntheticProtocolExecutionCompletion,
    SyntheticProtocolExecutionConcurrencyToken,
    SyntheticProtocolExecutionControl,
    SyntheticProtocolExecutionEvent,
    SyntheticProtocolExecutionManifest,
    SyntheticProtocolExecutionRecord,
    SyntheticProtocolExecutionStatus,
    SyntheticProtocolWorkOrder,
)
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes
from acoustic_ladder.storage.store import ImmutableSessionStore

INITIALIZED_NAME = "SYNTHETIC_EXECUTION_INITIALIZED"
INITIALIZED_BYTES = b"initialized\n"
MANIFEST_NAME = "synthetic_execution_manifest.json"
MANIFEST_SIDECAR_NAME = "synthetic_execution_manifest.sha256"
RECORD_NAME = "synthetic_execution_record.json"
RECORD_SIDECAR_NAME = "synthetic_execution_record.sha256"
BASE_NAMES = frozenset(
    {
        MANIFEST_NAME,
        MANIFEST_SIDECAR_NAME,
        RECORD_NAME,
        RECORD_SIDECAR_NAME,
        INITIALIZED_NAME,
        "events",
    }
)
COMPLETION_NAME = "synthetic_execution_completion.json"
COMPLETION_SIDECAR_NAME = "synthetic_execution_completion.sha256"
COMPLETE_MARKER_NAME = "SYNTHETIC_EXECUTION_COMPLETE"
COMPLETE_MARKER_BYTES = b"complete\n"
COMPLETION_NAMES = frozenset({COMPLETION_NAME, COMPLETION_SIDECAR_NAME, COMPLETE_MARKER_NAME})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_EVENT_FILE = re.compile(r"^event_([0-9]{8})\.(json|sha256)$")


@dataclass(frozen=True)
class _ReplayState:
    execution_state: str
    cursor: int
    event_sequence: int
    head_sha256: str
    successful_run_ids: tuple[str, ...]
    event_digests: tuple[str, ...]


class SyntheticProtocolExecutionError(StorageError):
    """Execution failure with explicit cross-root publication state."""

    def __init__(
        self,
        message: str,
        *,
        capture_published: bool = False,
        ledger_event_published: bool = False,
        completion_published: bool = False,
    ) -> None:
        super().__init__(message)
        self.capture_published = capture_published
        self.ledger_event_published = ledger_event_published
        self.completion_published = completion_published


def _identifier(value: str, label: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None or value in {".", ".."} or len(value) > 32:
        raise SyntheticProtocolExecutionError(
            f"{label} must be a safe ASCII identifier of at most 32 characters"
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
            raise SyntheticProtocolExecutionError(
                f"execution envelope contains a symlink or reparse point: {entry.name}"
            )
    events = root / "events"
    if events.is_dir():
        for entry in events.iterdir():
            if _is_reparse_point(entry):
                raise SyntheticProtocolExecutionError(
                    f"execution ledger contains a symlink or reparse point: {entry.name}"
                )


def _false_state() -> dict[str, object]:
    return {
        "development_synthetic_run": True,
        "data_origin": "synthetic",
        "physical_operator_confirmation_performed": False,
        "operator_confirmation_status": "pending",
        "formal_protocol_execution_performed": False,
        "measurement_performed": False,
        "hardware_io_performed": False,
        "playback_performed": False,
        "recording_performed": False,
        "hardware_ready": False,
        "full_duplex_verified": False,
        "shared_clock_verified": False,
        "channel_mapping_verified": False,
        "calibration_file_verified": False,
        "calibration_applied": False,
        "absolute_spl_calibrated": False,
        "formal_eligible": False,
        "experimental_result": False,
        "safety_marker": EXECUTION_SAFETY_MARKER,
    }


class DevelopmentSyntheticProtocolExecutionStore:
    """Independent create-only development execution ledger root."""

    def __init__(self, development_execution_root: str | Path) -> None:
        self.root = Path(development_execution_root).resolve()

    def execution_path(self, execution_id: str) -> Path:
        _identifier(execution_id, "execution_id")
        parent = (self.root / "executions").resolve()
        target = (parent / f"execution_{execution_id}").resolve()
        if target.parent != parent or not target.is_relative_to(self.root):
            raise SyntheticProtocolExecutionError("execution path escapes development root")
        return target

    def initialize(self, *, execution_id: str, manifest_bytes: bytes, record_bytes: bytes) -> Path:
        target = self.execution_path(execution_id)
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise SyntheticProtocolExecutionError("synthetic execution already exists")
        lock = parent / f".{execution_id}.initialize.lock"
        descriptor: int | None = None
        staging: Path | None = None
        published = False
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if target.exists():
                raise SyntheticProtocolExecutionError("synthetic execution already exists")
            staging = Path(tempfile.mkdtemp(prefix=f".{execution_id}.staging-", dir=parent))
            manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
            record_sha = hashlib.sha256(record_bytes).hexdigest()
            atomic_write_bytes(staging / MANIFEST_NAME, manifest_bytes)
            atomic_write_bytes(
                staging / MANIFEST_SIDECAR_NAME, _sidecar(manifest_sha, MANIFEST_NAME)
            )
            atomic_write_bytes(staging / RECORD_NAME, record_bytes)
            atomic_write_bytes(staging / RECORD_SIDECAR_NAME, _sidecar(record_sha, RECORD_NAME))
            atomic_write_bytes(staging / INITIALIZED_NAME, INITIALIZED_BYTES)
            (staging / "events").mkdir()
            os.rename(staging, target)
            published = True
            return target
        except FileExistsError as exc:
            raise SyntheticProtocolExecutionError(
                "synthetic execution initialization is already in progress"
            ) from exc
        except SyntheticProtocolExecutionError:
            raise
        except Exception as exc:
            raise SyntheticProtocolExecutionError(str(exc)) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)
            if not published and staging is not None and staging.exists():
                shutil.rmtree(staging)


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
        raise SyntheticProtocolExecutionError(str(exc)) from exc


def _validated_sources(
    *,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
) -> object:
    try:
        current = load_conditioned_virtual_capture_scenario(
            scenario.source_path, project_root=scenario.project_root
        )
        if current != scenario:
            raise SyntheticProtocolExecutionError(
                "synthetic scenario differs from its loaded provenance"
            )
        return validate_offline_ess_artifact(ess_artifact_root, bundle.configs["audio"])
    except (EssArtifactError, OSError, ValueError) as exc:
        raise SyntheticProtocolExecutionError(str(exc)) from exc


def _work_orders(
    execution_id: str, published: PublishedDevelopmentProtocolPlan
) -> list[SyntheticProtocolWorkOrder]:
    plan = published.plan
    conditions = {condition.condition_id: condition for condition in plan.condition_matrix}
    result: list[SyntheticProtocolWorkOrder] = []
    for session in plan.session_slots:
        for reassembly in session.reassembly_slots:
            for block in reassembly.condition_blocks:
                condition = conditions[block.condition_id]
                for measurement in block.measurements:
                    prefix = f"sx_{execution_id}"
                    core: dict[str, object] = {
                        "schema_version": "1.0.0",
                        "execution_id": execution_id,
                        "plan_id": plan.plan_id,
                        "compiled_plan_sha256": published.plan_sha256,
                        "protocol_plan_receipt_sha256": published.receipt_sha256,
                        "schedule_sha256": plan.schedule_sha256,
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
                        "session_id": f"{prefix}_s{measurement.session_index:02d}",
                        "reassembly_id": (
                            f"{prefix}_s{measurement.session_index:02d}"
                            f"_r{measurement.reassembly_index:02d}"
                        ),
                        "run_id": f"{prefix}_w{measurement.global_planned_ordinal:06d}",
                        "capture_id": f"{prefix}_w{measurement.global_planned_ordinal:06d}",
                        "operator_confirmation_status": "pending",
                        "run_mode": "development",
                        "protocol_execution_performed": False,
                        **_false_state(),
                    }
                    digest_core = {
                        **core,
                        "node_states": {
                            key: value.model_dump(mode="json")
                            for key, value in condition.node_states.items()
                        },
                    }
                    result.append(
                        SyntheticProtocolWorkOrder.model_validate(
                            {
                                **core,
                                "work_order_sha256": hashlib.sha256(
                                    canonical_json_bytes(digest_core)
                                ).hexdigest(),
                            }
                        )
                    )
    return result


def _manifest(
    *,
    execution_id: str,
    published: PublishedDevelopmentProtocolPlan,
    work_orders: list[SyntheticProtocolWorkOrder],
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess: object,
) -> SyntheticProtocolExecutionManifest:
    from acoustic_ladder.audio.excitation_persistence import EssArtifactReceipt

    if not isinstance(ess, EssArtifactReceipt):
        raise SyntheticProtocolExecutionError("invalid ESS validation receipt")
    plan = published.plan
    return SyntheticProtocolExecutionManifest.model_validate(
        {
            "schema_version": "1.0.0",
            "execution_id": execution_id,
            "plan_id": plan.plan_id,
            "plan_spec_id": plan.plan_spec_id,
            "experiment_stage": plan.experiment_stage,
            "compiled_plan_sha256": published.plan_sha256,
            "protocol_plan_receipt_sha256": published.receipt_sha256,
            "schedule_sha256": plan.schedule_sha256,
            "condition_matrix_sha256": plan.condition_matrix_sha256,
            "bundle_content_sha256": bundle.receipt.bundle_content_sha256,
            "device_manifest_sha256": bundle.receipt.device_manifest_sha256,
            "scenario_reference": scenario.original_relative_path,
            "scenario_raw_sha256": scenario.original_sha256,
            "scenario_normalized_sha256": scenario.normalized_sha256,
            "source_ess_artifact_id": ess.artifact_id,
            "source_ess_metadata_sha256": ess.metadata_sha256,
            "source_ess_wav_sha256": ess.wav_sha256,
            "source_ess_raw_float32_sha256": ess.raw_float32_sha256,
            "synthetic_config_normalized_sha256": (
                bundle.receipt.snapshots["synthetic_config"].normalized_sha256
            ),
            "expected_work_order_count": len(work_orders),
            "ordered_work_order_sha256": hashlib.sha256(
                canonical_json_bytes([item.work_order_sha256 for item in work_orders])
            ).hexdigest(),
            "run_mode": "development",
            **_false_state(),
        }
    )


def _record(
    execution_id: str, manifest_sha256: str, created_at: datetime
) -> SyntheticProtocolExecutionRecord:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise SyntheticProtocolExecutionError("execution time must be timezone-aware")
    return SyntheticProtocolExecutionRecord.model_validate(
        {
            "schema_version": "1.0.0",
            "execution_id": execution_id,
            "execution_relative_path": f"executions/execution_{execution_id}",
            "created_at": created_at,
            "manifest_sha256": manifest_sha256,
            "immutable_status": "initialized",
            "development_synthetic_run": True,
            "data_origin": "synthetic",
            "run_mode": "development",
            **_false_state(),
        }
    )


def _assert_roots_are_independent(
    *,
    store: DevelopmentSyntheticProtocolExecutionStore,
    session_store: ImmutableSessionStore,
    plan_store: DevelopmentProtocolPlanStore,
) -> None:
    roots = [
        store.root,
        session_store.roots.synthetic.resolve(),
        session_store.roots.real.resolve(),
        plan_store.root,
    ]
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if left == right or left.is_relative_to(right) or right.is_relative_to(left):
                raise SyntheticProtocolExecutionError(
                    "execution, plan, synthetic and real roots must be non-overlapping"
                )


def _read_base(
    root: Path,
) -> tuple[
    SyntheticProtocolExecutionManifest,
    SyntheticProtocolExecutionRecord,
    frozenset[str],
]:
    try:
        names = frozenset(entry.name for entry in root.iterdir()) if root.is_dir() else frozenset()
        if not root.is_dir() or names not in {BASE_NAMES, BASE_NAMES | COMPLETION_NAMES}:
            raise SyntheticProtocolExecutionError("execution base envelope is not exact")
        _reject_reparse_entries(root)
        if (root / INITIALIZED_NAME).read_bytes() != INITIALIZED_BYTES:
            raise SyntheticProtocolExecutionError("execution initialized marker is invalid")
        if not (root / "events").is_dir():
            raise SyntheticProtocolExecutionError("execution events entry is not a directory")
        manifest_bytes = (root / MANIFEST_NAME).read_bytes()
        record_bytes = (root / RECORD_NAME).read_bytes()
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        record_digest = hashlib.sha256(record_bytes).hexdigest()
        if (root / MANIFEST_SIDECAR_NAME).read_bytes() != _sidecar(manifest_digest, MANIFEST_NAME):
            raise SyntheticProtocolExecutionError("execution manifest sidecar is invalid")
        if (root / RECORD_SIDECAR_NAME).read_bytes() != _sidecar(record_digest, RECORD_NAME):
            raise SyntheticProtocolExecutionError("execution record sidecar is invalid")
        manifest = SyntheticProtocolExecutionManifest.model_validate_json(manifest_bytes)
        record = SyntheticProtocolExecutionRecord.model_validate_json(record_bytes)
        if manifest_bytes != canonical_json_bytes(manifest.model_dump(mode="json")):
            raise SyntheticProtocolExecutionError("execution manifest is not canonical")
        if record_bytes != canonical_json_bytes(record.model_dump(mode="json")):
            raise SyntheticProtocolExecutionError("execution record is not canonical")
        if record.manifest_sha256 != manifest_digest:
            raise SyntheticProtocolExecutionError("execution record does not bind manifest")
        return manifest, record, names
    except SyntheticProtocolExecutionError:
        raise
    except (OSError, ValidationError, ValueError) as exc:
        raise SyntheticProtocolExecutionError(str(exc)) from exc


def _status(
    execution_id: str,
    work_orders: list[SyntheticProtocolWorkOrder],
    state: _ReplayState,
    *,
    recovery_kind: str | None = None,
) -> SyntheticProtocolExecutionStatus:
    current = work_orders[state.cursor] if state.cursor < len(work_orders) else None
    current_sha = current.work_order_sha256 if current is not None else ZERO_EVENT_SHA256
    recovery_run_id = current.run_id if recovery_kind == "capture" and current else None
    effective_state = "recovery_required" if recovery_kind is not None else state.execution_state
    return SyntheticProtocolExecutionStatus.model_validate(
        {
            "execution_id": execution_id,
            "execution_state": effective_state,
            "current_work_order": current,
            "cursor": state.cursor,
            "total_work_order_count": len(work_orders),
            "successful_work_order_count": state.cursor,
            "concurrency_token": {
                "execution_id": execution_id,
                "event_sequence": state.event_sequence,
                "head_event_sha256": state.head_sha256,
                "current_work_order_sha256": current_sha,
                "cursor": state.cursor,
                "recovery_run_id": recovery_run_id,
            },
            "recovery_kind": recovery_kind,
            "synthetic_capture_performed": state.cursor > 0 or recovery_kind == "capture",
            "run_mode": "development",
            **_false_state(),
        }
    )


def _capture_for_event(
    *,
    session_store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    work_order: SyntheticProtocolWorkOrder,
    semantic_replay: bool = False,
) -> PublishedPlanBoundSyntheticCapture:
    try:
        if not semantic_replay:
            return validate_plan_bound_synthetic_capture_binding(
                store=session_store, work_order=work_order
            )
        return validate_plan_bound_synthetic_capture(
            store=session_store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            work_order=work_order,
        )
    except (PlanBoundSyntheticCaptureError, StorageError) as exc:
        raise SyntheticProtocolExecutionError(str(exc), capture_published=True) from exc


def _expected_event(
    *,
    execution_id: str,
    published: PublishedDevelopmentProtocolPlan,
    work_order: SyntheticProtocolWorkOrder,
    state: _ReplayState,
    event_type: str,
    actor_id: str,
    reason_code: str | None,
    recorded_at: datetime,
    capture: PublishedPlanBoundSyntheticCapture | None,
    total: int,
) -> tuple[SyntheticProtocolExecutionEvent, _ReplayState]:
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise SyntheticProtocolExecutionError("execution event time must be timezone-aware")
    before = state.execution_state
    cursor_after = state.cursor
    after = before
    if event_type == "work_order_succeeded":
        if before != "active" or capture is None:
            raise SyntheticProtocolExecutionError("work order cannot succeed in this state")
        cursor_after += 1
        if cursor_after > total:
            raise SyntheticProtocolExecutionError("execution cursor exceeds plan")
        after = "complete" if cursor_after == total else "active"
    elif event_type == "work_order_failed":
        if before != "active" or capture is not None or reason_code is None:
            raise SyntheticProtocolExecutionError("work order cannot fail in this state")
        after = "failed"
    elif event_type == "work_order_retry_requested":
        if before != "failed" or capture is not None or reason_code is not None:
            raise SyntheticProtocolExecutionError("work order cannot retry in this state")
        after = "active"
    elif event_type == "execution_paused":
        if before != "active" or capture is not None or reason_code is not None:
            raise SyntheticProtocolExecutionError("execution cannot pause in this state")
        after = "paused"
    elif event_type == "execution_resumed":
        if before != "paused" or capture is not None or reason_code is not None:
            raise SyntheticProtocolExecutionError("execution cannot resume in this state")
        after = "active"
    elif event_type == "execution_aborted":
        if before in {"aborted", "complete"} or capture is not None or reason_code is None:
            raise SyntheticProtocolExecutionError("execution cannot abort in this state")
        after = "aborted"
    else:
        raise SyntheticProtocolExecutionError(f"unsupported execution event: {event_type}")
    success = event_type == "work_order_succeeded"
    event = SyntheticProtocolExecutionEvent.model_validate(
        {
            "schema_version": "1.0.0",
            "execution_id": execution_id,
            "event_sequence": state.event_sequence + 1,
            "event_type": event_type,
            "previous_event_sha256": state.head_sha256,
            "plan_id": published.plan.plan_id,
            "compiled_plan_sha256": published.plan_sha256,
            "protocol_plan_receipt_sha256": published.receipt_sha256,
            "work_order_sha256": work_order.work_order_sha256,
            "actor_id": actor_id,
            "before_state": before,
            "after_state": after,
            "cursor_before": state.cursor,
            "cursor_after": cursor_after,
            "session_id": work_order.session_id if success else None,
            "reassembly_id": work_order.reassembly_id if success else None,
            "run_id": work_order.run_id if success else None,
            "capture_receipt_sha256": capture.receipt_sha256 if capture else None,
            "run_record_sha256": capture.run_record_sha256 if capture else None,
            "ordered_artifact_sha256": capture.ordered_artifact_sha256 if capture else None,
            "reason_code": reason_code,
            "recorded_at": recorded_at,
            "synthetic_capture_performed": success,
            "run_mode": "development",
            **_false_state(),
        }
    )
    successful = state.successful_run_ids + ((work_order.run_id,) if success else ())
    return event, _ReplayState(
        after,
        cursor_after,
        state.event_sequence + 1,
        state.head_sha256,
        successful,
        state.event_digests,
    )


def _publish_event_pair(root: Path, event: SyntheticProtocolExecutionEvent) -> str:
    events = root / "events"
    sequence = event.event_sequence
    filename = f"event_{sequence:08d}.json"
    sidecar_name = f"event_{sequence:08d}.sha256"
    event_bytes = canonical_json_bytes(event.model_dump(mode="json"))
    digest = hashlib.sha256(event_bytes).hexdigest()
    staging = Path(tempfile.mkdtemp(prefix=f".event-{sequence:08d}.staging-", dir=events))
    published: list[Path] = []
    try:
        atomic_write_bytes(staging / filename, event_bytes)
        atomic_write_bytes(staging / sidecar_name, _sidecar(digest, filename))
        for name in (filename, sidecar_name):
            target = events / name
            os.link(staging / name, target)
            published.append(target)
    except FileExistsError as exc:
        raise SyntheticProtocolExecutionError("execution event sequence already exists") from exc
    finally:
        if len(published) != 2:
            for target in published:
                target.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=False)
    return digest


def _replay_events(
    *,
    root: Path,
    execution_id: str,
    published: PublishedDevelopmentProtocolPlan,
    work_orders: list[SyntheticProtocolWorkOrder],
    session_store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
) -> _ReplayState:
    events_root = root / "events"
    entries = list(events_root.iterdir())
    if any(not entry.is_file() for entry in entries):
        raise SyntheticProtocolExecutionError("execution ledger contains a non-file")
    pairs: dict[int, set[str]] = {}
    for entry in entries:
        match = _EVENT_FILE.fullmatch(entry.name)
        if match is None:
            raise SyntheticProtocolExecutionError("execution ledger contains an extra file")
        pairs.setdefault(int(match.group(1)), set()).add(match.group(2))
    if sorted(pairs) != list(range(1, len(pairs) + 1)) or any(
        extensions != {"json", "sha256"} for extensions in pairs.values()
    ):
        raise SyntheticProtocolExecutionError("execution event sequence is incomplete")
    state = _ReplayState("active", 0, 0, ZERO_EVENT_SHA256, (), ())
    for sequence in sorted(pairs):
        if state.cursor >= len(work_orders):
            raise SyntheticProtocolExecutionError("event exists after terminal execution")
        filename = f"event_{sequence:08d}.json"
        body = (events_root / filename).read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if (events_root / f"event_{sequence:08d}.sha256").read_bytes() != _sidecar(
            digest, filename
        ):
            raise SyntheticProtocolExecutionError("execution event sidecar is invalid")
        event = SyntheticProtocolExecutionEvent.model_validate_json(body)
        if body != canonical_json_bytes(event.model_dump(mode="json")):
            raise SyntheticProtocolExecutionError("execution event is not canonical")
        if event.event_sequence != sequence or event.previous_event_sha256 != state.head_sha256:
            raise SyntheticProtocolExecutionError("execution event hash chain is invalid")
        order = work_orders[state.cursor]
        capture = None
        if event.event_type == "work_order_succeeded":
            capture = _capture_for_event(
                session_store=session_store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess_artifact_root,
                work_order=order,
            )
        expected, after = _expected_event(
            execution_id=execution_id,
            published=published,
            work_order=order,
            state=state,
            event_type=event.event_type,
            actor_id=event.actor_id,
            reason_code=event.reason_code,
            recorded_at=event.recorded_at,
            capture=capture,
            total=len(work_orders),
        )
        if event != expected:
            raise SyntheticProtocolExecutionError("execution event differs from replay")
        state = _ReplayState(
            after.execution_state,
            after.cursor,
            sequence,
            digest,
            after.successful_run_ids,
            (*state.event_digests, digest),
        )
    return state


def _completion(
    *,
    execution_id: str,
    published: PublishedDevelopmentProtocolPlan,
    state: _ReplayState,
    completed_at: datetime,
) -> SyntheticProtocolExecutionCompletion:
    return SyntheticProtocolExecutionCompletion.model_validate(
        {
            "schema_version": "1.0.0",
            "execution_id": execution_id,
            "plan_id": published.plan.plan_id,
            "compiled_plan_sha256": published.plan_sha256,
            "protocol_plan_receipt_sha256": published.receipt_sha256,
            "schedule_sha256": published.plan.schedule_sha256,
            "expected_work_order_count": published.plan.planned_measurement_count,
            "completed_work_order_count": state.cursor,
            "final_event_sequence": state.event_sequence,
            "final_event_sha256": state.head_sha256,
            "ordered_successful_run_sha256": hashlib.sha256(
                canonical_json_bytes(list(state.successful_run_ids))
            ).hexdigest(),
            "ordered_event_sha256": hashlib.sha256(
                canonical_json_bytes(list(state.event_digests))
            ).hexdigest(),
            "completed_at": completed_at,
            "completion_state": "complete",
            "synthetic_capture_performed": True,
            "run_mode": "development",
            **_false_state(),
        }
    )


def _publish_completion(root: Path, completion: SyntheticProtocolExecutionCompletion) -> None:
    body = canonical_json_bytes(completion.model_dump(mode="json"))
    digest = hashlib.sha256(body).hexdigest()
    staging = Path(tempfile.mkdtemp(prefix=".completion.staging-", dir=root))
    published: list[Path] = []
    try:
        atomic_write_bytes(staging / COMPLETION_NAME, body)
        atomic_write_bytes(staging / COMPLETION_SIDECAR_NAME, _sidecar(digest, COMPLETION_NAME))
        atomic_write_bytes(staging / COMPLETE_MARKER_NAME, COMPLETE_MARKER_BYTES)
        for name in (COMPLETION_NAME, COMPLETION_SIDECAR_NAME, COMPLETE_MARKER_NAME):
            target = root / name
            os.link(staging / name, target)
            published.append(target)
    finally:
        if len(published) != 3:
            for target in published:
                target.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=False)


def _validate_completion(
    *,
    root: Path,
    execution_id: str,
    published: PublishedDevelopmentProtocolPlan,
    state: _ReplayState,
) -> None:
    body = (root / COMPLETION_NAME).read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if (root / COMPLETION_SIDECAR_NAME).read_bytes() != _sidecar(digest, COMPLETION_NAME):
        raise SyntheticProtocolExecutionError("execution completion sidecar is invalid")
    if (root / COMPLETE_MARKER_NAME).read_bytes() != COMPLETE_MARKER_BYTES:
        raise SyntheticProtocolExecutionError("execution completion marker is invalid")
    stored = SyntheticProtocolExecutionCompletion.model_validate_json(body)
    expected = _completion(
        execution_id=execution_id,
        published=published,
        state=state,
        completed_at=stored.completed_at,
    )
    if stored != expected or body != canonical_json_bytes(expected.model_dump(mode="json")):
        raise SyntheticProtocolExecutionError("execution completion differs from replay")


def _ensure_session(
    *,
    session_store: ImmutableSessionStore,
    bundle: LoadedBundle,
    work_orders: list[SyntheticProtocolWorkOrder],
    current: SyntheticProtocolWorkOrder,
    now: Callable[[], datetime],
) -> None:
    path = session_store.session_path(DataOrigin.SYNTHETIC, current.session_id)
    session_orders = [item for item in work_orders if item.session_id == current.session_id]
    reassembly_ids = list(dict.fromkeys(item.reassembly_id for item in session_orders))
    if path.exists():
        stored = session_store.validate_session(DataOrigin.SYNTHETIC, current.session_id)
        if (
            stored.reassembly_ids != reassembly_ids
            or stored.data_origin is not DataOrigin.SYNTHETIC
        ):
            raise SyntheticProtocolExecutionError("existing synthetic session identity mismatch")
        return
    timestamp = now()
    session = SessionRecord(
        session_id=current.session_id,
        session_schema_version="1.0.0",
        created_at=timestamp,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        operator=None,
        device_manifest_reference="manifest/device_manifest.provisional.json",
        config_bundle_reference="protocol/config_bundle.json",
        reassembly_ids=reassembly_ids,
        run_ids=[],
        immutable_status="immutable",
        notes="Development synthetic protocol execution; not a physical measurement.",
    )
    reassemblies = [
        ReassemblyRecord(
            reassembly_id=reassembly_id,
            session_id=current.session_id,
            sequence_index=index,
            created_at=timestamp,
            assembly_description="Plan-derived development synthetic reassembly.",
            operator_confirmation=False,
            related_run_ids=[],
        )
        for index, reassembly_id in enumerate(reassembly_ids)
    ]
    try:
        session_store.create_synthetic_session(session, reassemblies, bundle)
    except Exception as exc:
        raise SyntheticProtocolExecutionError(str(exc)) from exc


def initialize_synthetic_protocol_execution(
    *,
    store: DevelopmentSyntheticProtocolExecutionStore,
    session_store: ImmutableSessionStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    execution_id: str,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    now: Callable[[], datetime],
) -> SyntheticProtocolExecutionStatus:
    _identifier(execution_id, "execution_id")
    _assert_roots_are_independent(store=store, session_store=session_store, plan_store=plan_store)
    published = _validated_plan(plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id)
    ess = _validated_sources(bundle=bundle, scenario=scenario, ess_artifact_root=ess_artifact_root)
    work_orders = _work_orders(execution_id, published)
    manifest = _manifest(
        execution_id=execution_id,
        published=published,
        work_orders=work_orders,
        bundle=bundle,
        scenario=scenario,
        ess=ess,
    )
    manifest_bytes = canonical_json_bytes(manifest.model_dump(mode="json"))
    record = _record(execution_id, hashlib.sha256(manifest_bytes).hexdigest(), now())
    store.initialize(
        execution_id=execution_id,
        manifest_bytes=manifest_bytes,
        record_bytes=canonical_json_bytes(record.model_dump(mode="json")),
    )
    return _status(
        execution_id,
        work_orders,
        _ReplayState("active", 0, 0, ZERO_EVENT_SHA256, (), ()),
    )


def derive_synthetic_protocol_work_orders(
    *,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    execution_id: str,
) -> tuple[SyntheticProtocolWorkOrder, ...]:
    """Replay-validate the plan and expose its immutable derived execution order."""

    _identifier(execution_id, "execution_id")
    published = _validated_plan(plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id)
    return tuple(_work_orders(execution_id, published))


def read_synthetic_protocol_execution_status(
    *,
    store: DevelopmentSyntheticProtocolExecutionStore,
    session_store: ImmutableSessionStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    execution_id: str,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
) -> SyntheticProtocolExecutionStatus:
    _assert_roots_are_independent(store=store, session_store=session_store, plan_store=plan_store)
    published = _validated_plan(plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id)
    ess = _validated_sources(bundle=bundle, scenario=scenario, ess_artifact_root=ess_artifact_root)
    work_orders = _work_orders(execution_id, published)
    root = store.execution_path(execution_id)
    manifest, record, names = _read_base(root)
    expected_manifest = _manifest(
        execution_id=execution_id,
        published=published,
        work_orders=work_orders,
        bundle=bundle,
        scenario=scenario,
        ess=ess,
    )
    expected_manifest_bytes = canonical_json_bytes(expected_manifest.model_dump(mode="json"))
    expected_record = _record(
        execution_id, hashlib.sha256(expected_manifest_bytes).hexdigest(), record.created_at
    )
    if manifest != expected_manifest or record != expected_record:
        raise SyntheticProtocolExecutionError("execution base envelope differs from replay")
    state = _replay_events(
        root=root,
        execution_id=execution_id,
        published=published,
        work_orders=work_orders,
        session_store=session_store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
    )
    recovery_kind: str | None = None
    if state.execution_state == "complete":
        if names == BASE_NAMES:
            recovery_kind = "completion"
        else:
            _validate_completion(
                root=root,
                execution_id=execution_id,
                published=published,
                state=state,
            )
    elif names != BASE_NAMES:
        raise SyntheticProtocolExecutionError(
            "non-complete execution contains completion artifacts"
        )
    if state.execution_state == "active" and state.cursor < len(work_orders):
        current = work_orders[state.cursor]
        run_root = (
            session_store.session_path(DataOrigin.SYNTHETIC, current.session_id)
            / "raw"
            / f"run_{current.run_id}"
        )
        if run_root.exists():
            if not (run_root / "RUN_COMPLETE").is_file():
                raise SyntheticProtocolExecutionError(
                    "current synthetic capture is only partially published",
                    capture_published=False,
                )
            _capture_for_event(
                session_store=session_store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess_artifact_root,
                work_order=current,
                semantic_replay=True,
            )
            recovery_kind = "capture"
    return _status(execution_id, work_orders, state, recovery_kind=recovery_kind)


def _token_matches(
    supplied: SyntheticProtocolExecutionConcurrencyToken,
    actual: SyntheticProtocolExecutionConcurrencyToken,
) -> None:
    if supplied != actual:
        raise SyntheticProtocolExecutionError("stale or foreign execution concurrency token")


def _state_from_verified_status(
    root: Path, status: SyntheticProtocolExecutionStatus
) -> _ReplayState:
    event_paths = sorted((root / "events").glob("event_????????.json"))
    events = [
        SyntheticProtocolExecutionEvent.model_validate_json(path.read_bytes())
        for path in event_paths
    ]
    successful = tuple(
        event.run_id for event in events if event.event_type == "work_order_succeeded"
    )
    if any(run_id is None for run_id in successful):
        raise SyntheticProtocolExecutionError("successful event omitted run identity")
    state = status.execution_state
    if status.recovery_kind == "capture":
        state = "active"
    elif status.recovery_kind == "completion":
        state = "complete"
    return _ReplayState(
        state,
        status.cursor,
        status.concurrency_token.event_sequence,
        status.concurrency_token.head_event_sha256,
        tuple(str(run_id) for run_id in successful),
        tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in event_paths),
    )


def apply_synthetic_protocol_execution_control(
    *,
    store: DevelopmentSyntheticProtocolExecutionStore,
    session_store: ImmutableSessionStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    execution_id: str,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    command: SyntheticProtocolExecutionControl,
    concurrency_token: SyntheticProtocolExecutionConcurrencyToken,
    now: Callable[[], datetime],
) -> SyntheticProtocolExecutionStatus:
    root = store.execution_path(execution_id)
    lock = root.parent / f".{execution_id}.transition.lock"
    descriptor: int | None = None
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        status = read_synthetic_protocol_execution_status(
            store=store,
            session_store=session_store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id=plan_id,
            execution_id=execution_id,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
        )
        _token_matches(concurrency_token, status.concurrency_token)
        token = status.concurrency_token
        if (
            command.expected_event_sequence != token.event_sequence
            or command.expected_head_sha256 != token.head_event_sha256
            or command.expected_current_work_order_sha256 != token.current_work_order_sha256
            or command.expected_cursor != token.cursor
        ):
            raise SyntheticProtocolExecutionError("control expectations are stale")
        if status.recovery_kind is not None or status.current_work_order is None:
            raise SyntheticProtocolExecutionError("recovery or terminal state rejects controls")
        published = _validated_plan(
            plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id
        )
        work_orders = _work_orders(execution_id, published)
        state = _state_from_verified_status(root, status)
        event_type = {
            "pause": "execution_paused",
            "resume": "execution_resumed",
            "retry": "work_order_retry_requested",
            "abort": "execution_aborted",
        }[command.action]
        event, after = _expected_event(
            execution_id=execution_id,
            published=published,
            work_order=work_orders[state.cursor],
            state=state,
            event_type=event_type,
            actor_id=command.actor_id,
            reason_code=command.reason_code,
            recorded_at=now(),
            capture=None,
            total=len(work_orders),
        )
        digest = _publish_event_pair(root, event)
        after = _ReplayState(
            after.execution_state,
            after.cursor,
            event.event_sequence,
            digest,
            after.successful_run_ids,
            (*state.event_digests, digest),
        )
        return _status(execution_id, work_orders, after)
    except FileExistsError as exc:
        raise SyntheticProtocolExecutionError(
            "synthetic execution transition is already in progress"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink(missing_ok=True)


def recover_current_synthetic_protocol_work_order(
    *,
    store: DevelopmentSyntheticProtocolExecutionStore,
    session_store: ImmutableSessionStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    execution_id: str,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    concurrency_token: SyntheticProtocolExecutionConcurrencyToken,
    actor_id: str,
    now: Callable[[], datetime],
) -> SyntheticProtocolExecutionStatus:
    _identifier(actor_id, "actor_id")
    root = store.execution_path(execution_id)
    lock = root.parent / f".{execution_id}.transition.lock"
    descriptor: int | None = None
    event_published = False
    completion_published = False
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        status = read_synthetic_protocol_execution_status(
            store=store,
            session_store=session_store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id=plan_id,
            execution_id=execution_id,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
        )
        _token_matches(concurrency_token, status.concurrency_token)
        if status.execution_state != "recovery_required" or status.recovery_kind is None:
            raise SyntheticProtocolExecutionError("no verified recovery target exists")
        published = _validated_plan(
            plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id
        )
        work_orders = _work_orders(execution_id, published)
        state = _state_from_verified_status(root, status)
        if status.recovery_kind == "capture":
            current = work_orders[state.cursor]
            capture = _capture_for_event(
                session_store=session_store,
                bundle=bundle,
                scenario=scenario,
                ess_artifact_root=ess_artifact_root,
                work_order=current,
                semantic_replay=True,
            )
            event, after = _expected_event(
                execution_id=execution_id,
                published=published,
                work_order=current,
                state=state,
                event_type="work_order_succeeded",
                actor_id=actor_id,
                reason_code=None,
                recorded_at=now(),
                capture=capture,
                total=len(work_orders),
            )
            digest = _publish_event_pair(root, event)
            event_published = True
            state = _ReplayState(
                after.execution_state,
                after.cursor,
                event.event_sequence,
                digest,
                after.successful_run_ids,
                (*after.event_digests, digest),
            )
        if state.execution_state == "complete":
            completion = _completion(
                execution_id=execution_id,
                published=published,
                state=state,
                completed_at=now(),
            )
            _publish_completion(root, completion)
            completion_published = True
        return _status(execution_id, work_orders, state)
    except FileExistsError as exc:
        raise SyntheticProtocolExecutionError(
            "synthetic execution recovery is already in progress",
            ledger_event_published=event_published,
            completion_published=completion_published,
        ) from exc
    except SyntheticProtocolExecutionError as exc:
        if event_published or completion_published:
            raise SyntheticProtocolExecutionError(
                str(exc),
                capture_published=status.recovery_kind == "capture",
                ledger_event_published=event_published,
                completion_published=completion_published,
            ) from exc
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink(missing_ok=True)


def validate_synthetic_protocol_execution(
    *,
    store: DevelopmentSyntheticProtocolExecutionStore,
    session_store: ImmutableSessionStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    execution_id: str,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
) -> SyntheticProtocolExecutionStatus:
    status = read_synthetic_protocol_execution_status(
        store=store,
        session_store=session_store,
        plan_store=plan_store,
        bundle=bundle,
        spec=spec,
        plan_id=plan_id,
        execution_id=execution_id,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
    )
    if status.recovery_kind is not None:
        raise SyntheticProtocolExecutionError(
            "execution requires explicit recovery before validation can pass",
            capture_published=status.recovery_kind == "capture",
            ledger_event_published=status.cursor > 0,
            completion_published=False,
        )
    published = _validated_plan(plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id)
    work_orders = _work_orders(execution_id, published)
    for work_order in work_orders[: status.cursor]:
        _capture_for_event(
            session_store=session_store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            work_order=work_order,
            semantic_replay=True,
        )
    return status


def execute_next_synthetic_protocol_work_order(
    *,
    store: DevelopmentSyntheticProtocolExecutionStore,
    session_store: ImmutableSessionStore,
    plan_store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    execution_id: str,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    concurrency_token: SyntheticProtocolExecutionConcurrencyToken,
    actor_id: str,
    now: Callable[[], datetime],
    fault_injector: Callable[[str], None] | None = None,
) -> SyntheticProtocolExecutionStatus:
    _identifier(actor_id, "actor_id")
    root = store.execution_path(execution_id)
    lock = root.parent / f".{execution_id}.transition.lock"
    descriptor: int | None = None
    capture_published = False
    event_published = False
    completion_published = False
    published: PublishedDevelopmentProtocolPlan | None = None
    work_orders: list[SyntheticProtocolWorkOrder] | None = None
    current: SyntheticProtocolWorkOrder | None = None
    state: _ReplayState | None = None
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        status = read_synthetic_protocol_execution_status(
            store=store,
            session_store=session_store,
            plan_store=plan_store,
            bundle=bundle,
            spec=spec,
            plan_id=plan_id,
            execution_id=execution_id,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
        )
        _token_matches(concurrency_token, status.concurrency_token)
        if status.execution_state != "active" or status.current_work_order is None:
            raise SyntheticProtocolExecutionError(
                "execute-next requires an active non-recovery work order"
            )
        published = _validated_plan(
            plan_store=plan_store, bundle=bundle, spec=spec, plan_id=plan_id
        )
        work_orders = _work_orders(execution_id, published)
        state = _state_from_verified_status(root, status)
        current = work_orders[state.cursor]
        if fault_injector is not None:
            fault_injector("before_session")
        _ensure_session(
            session_store=session_store,
            bundle=bundle,
            work_orders=work_orders,
            current=current,
            now=now,
        )
        if fault_injector is not None:
            fault_injector("after_session_before_capture")
        capture = publish_plan_bound_synthetic_capture(
            store=session_store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            work_order=current,
            now=now,
        )
        capture_published = True
        if fault_injector is not None:
            fault_injector("after_capture_before_event")
        capture = _capture_for_event(
            session_store=session_store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            work_order=current,
            semantic_replay=True,
        )
        event, after = _expected_event(
            execution_id=execution_id,
            published=published,
            work_order=current,
            state=state,
            event_type="work_order_succeeded",
            actor_id=actor_id,
            reason_code=None,
            recorded_at=now(),
            capture=capture,
            total=len(work_orders),
        )
        digest = _publish_event_pair(root, event)
        event_published = True
        after = _ReplayState(
            after.execution_state,
            after.cursor,
            event.event_sequence,
            digest,
            after.successful_run_ids,
            (*state.event_digests, digest),
        )
        if after.execution_state == "complete":
            if fault_injector is not None:
                fault_injector("after_event_before_completion")
            completion = _completion(
                execution_id=execution_id,
                published=published,
                state=after,
                completed_at=now(),
            )
            _publish_completion(root, completion)
            completion_published = True
        return _status(execution_id, work_orders, after)
    except SyntheticProtocolExecutionError as exc:
        if capture_published or event_published or completion_published:
            raise SyntheticProtocolExecutionError(
                str(exc),
                capture_published=capture_published,
                ledger_event_published=event_published,
                completion_published=completion_published,
            ) from exc
        raise
    except PlanBoundSyntheticCaptureError as exc:
        capture_published = capture_published or exc.published
        raise SyntheticProtocolExecutionError(
            str(exc),
            capture_published=capture_published,
            ledger_event_published=event_published,
            completion_published=completion_published,
        ) from exc
    except Exception as exc:
        if (
            not capture_published
            and not event_published
            and published is not None
            and work_orders is not None
            and current is not None
            and state is not None
        ):
            try:
                failure, _ = _expected_event(
                    execution_id=execution_id,
                    published=published,
                    work_order=current,
                    state=state,
                    event_type="work_order_failed",
                    actor_id=actor_id,
                    reason_code="synthetic_capture_failed",
                    recorded_at=now(),
                    capture=None,
                    total=len(work_orders),
                )
                _publish_event_pair(root, failure)
                event_published = True
            except Exception:
                event_published = False
        raise SyntheticProtocolExecutionError(
            str(exc),
            capture_published=capture_published,
            ledger_event_published=event_published,
            completion_published=completion_published,
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
            lock.unlink(missing_ok=True)


__all__ = [
    "DevelopmentSyntheticProtocolExecutionStore",
    "SyntheticProtocolExecutionError",
    "apply_synthetic_protocol_execution_control",
    "derive_synthetic_protocol_work_orders",
    "execute_next_synthetic_protocol_work_order",
    "initialize_synthetic_protocol_execution",
    "read_synthetic_protocol_execution_status",
    "recover_current_synthetic_protocol_work_order",
    "validate_synthetic_protocol_execution",
]
