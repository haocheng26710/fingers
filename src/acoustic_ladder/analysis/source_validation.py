"""One-shot replay validation for plan-bound synthetic analysis sources."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    LoadedConditionedVirtualCaptureScenario,
)
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.protocol.plan_bound_capture import (
    PublishedPlanBoundSyntheticCapture,
    validate_plan_bound_synthetic_capture_binding,
)
from acoustic_ladder.protocol.planning import LoadedDevelopmentProtocolPlanSpec
from acoustic_ladder.protocol.planning_persistence import DevelopmentProtocolPlanStore
from acoustic_ladder.protocol.synthetic_execution import (
    COMPLETION_NAME,
    MANIFEST_NAME,
    DevelopmentSyntheticProtocolExecutionStore,
    derive_synthetic_protocol_work_orders,
    validate_synthetic_protocol_execution,
)
from acoustic_ladder.protocol.synthetic_execution_models import (
    SyntheticProtocolExecutionCompletion,
    SyntheticProtocolWorkOrder,
)
from acoustic_ladder.storage.store import ImmutableSessionStore

from .spec import LoadedDevelopmentAnalysisMatrixSpec


class AnalysisSourceError(ValueError):
    """Raised when execution sources cannot authorize an analysis matrix."""


ANALYSIS_EVIDENCE_TIME_BASIS: Literal["latest_verified_execution_completion_utc"] = (
    "latest_verified_execution_completion_utc"
)
ANALYSIS_EVIDENCE_TIME_DERIVATION_VERSION: Literal["1.0.0"] = "1.0.0"


def derive_latest_verified_execution_completion_utc(
    completion_times: tuple[datetime, ...],
) -> tuple[tuple[datetime, ...], datetime]:
    """Normalize verified completion instants to UTC and select the latest."""

    if not completion_times:
        raise AnalysisSourceError("analysis requires at least one verified completion time")
    normalized: list[datetime] = []
    for completed_at in completion_times:
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise AnalysisSourceError("source execution completed_at must be timezone-aware")
        normalized.append(completed_at.astimezone(UTC))
    completed_at_utc = tuple(normalized)
    return completed_at_utc, max(completed_at_utc)


@dataclass(frozen=True)
class AnalysisExecutionSource:
    store: DevelopmentSyntheticProtocolExecutionStore
    session_store: ImmutableSessionStore
    plan_store: DevelopmentProtocolPlanStore
    bundle: LoadedBundle
    spec: LoadedDevelopmentProtocolPlanSpec
    plan_id: str
    execution_id: str
    scenario: LoadedConditionedVirtualCaptureScenario
    ess_artifact_root: str | Path


@dataclass(frozen=True)
class ValidatedAnalysisRowSource:
    work_order: SyntheticProtocolWorkOrder
    capture: PublishedPlanBoundSyntheticCapture


@dataclass(frozen=True)
class ValidatedAnalysisExecution:
    source: AnalysisExecutionSource
    stage: int
    execution_manifest_sha256: str
    execution_completion_sha256: str
    execution_completed_at: datetime
    execution_completed_at_utc: datetime
    rows: tuple[ValidatedAnalysisRowSource, ...]


@dataclass(frozen=True)
class ValidatedSyntheticAnalysisSources:
    analysis_spec: LoadedDevelopmentAnalysisMatrixSpec
    executions: tuple[ValidatedAnalysisExecution, ...]
    rows: tuple[ValidatedAnalysisRowSource, ...]
    ordered_source_aggregate_sha256: str
    execution_completed_at_utc: tuple[datetime, ...]
    analysis_evidence_time: datetime
    analysis_evidence_time_basis: Literal["latest_verified_execution_completion_utc"]
    analysis_evidence_time_derivation_version: Literal["1.0.0"]


def _validate_one(source: AnalysisExecutionSource) -> ValidatedAnalysisExecution:
    root = source.store.execution_path(source.execution_id)
    parent = root.parent
    forbidden = (
        parent / f".{source.execution_id}.transition.lock",
        parent / f".{source.execution_id}.initialize.lock",
    )
    if any(path.exists() for path in forbidden):
        raise AnalysisSourceError("source execution retains a mutation lock")
    if any(parent.glob(f".{source.execution_id}.staging-*")):
        raise AnalysisSourceError("source execution retains staging content")
    if source.session_store.roots.real.exists():
        raise AnalysisSourceError("analysis sources require an absent real data root")
    try:
        status = validate_synthetic_protocol_execution(
            store=source.store,
            session_store=source.session_store,
            plan_store=source.plan_store,
            bundle=source.bundle,
            spec=source.spec,
            plan_id=source.plan_id,
            execution_id=source.execution_id,
            scenario=source.scenario,
            ess_artifact_root=source.ess_artifact_root,
        )
        work_orders = derive_synthetic_protocol_work_orders(
            plan_store=source.plan_store,
            bundle=source.bundle,
            spec=source.spec,
            plan_id=source.plan_id,
            execution_id=source.execution_id,
        )
    except Exception as exc:
        raise AnalysisSourceError(f"source execution is not complete and valid: {exc}") from exc
    if (
        status.execution_state != "complete"
        or status.recovery_kind is not None
        or status.cursor != status.total_work_order_count
        or status.successful_work_order_count != status.total_work_order_count
        or len(work_orders) != status.total_work_order_count
    ):
        raise AnalysisSourceError("source execution must be complete with no recovery state")
    if any(
        (
            status.hardware_io_performed,
            status.playback_performed,
            status.recording_performed,
            status.formal_protocol_execution_performed,
            status.measurement_performed,
            status.experimental_result,
        )
    ):
        raise AnalysisSourceError("source execution contains forbidden hardware or formal state")
    rows: list[ValidatedAnalysisRowSource] = []
    for work_order in work_orders:
        try:
            capture = validate_plan_bound_synthetic_capture_binding(
                store=source.session_store, work_order=work_order
            )
        except Exception as exc:
            ordinal = work_order.global_planned_ordinal
            raise AnalysisSourceError(
                f"source run differs from plan work order {ordinal}: {exc}"
            ) from exc
        rows.append(ValidatedAnalysisRowSource(work_order, capture))
    expected_by_session: dict[str, set[str]] = {}
    for row in rows:
        expected_by_session.setdefault(row.work_order.session_id, set()).add(
            f"run_{row.work_order.run_id}"
        )
    actual_sessions = {
        path.name.removeprefix("session_")
        for path in source.session_store.roots.synthetic.glob("session_*")
        if path.is_dir()
    }
    if actual_sessions != set(expected_by_session):
        raise AnalysisSourceError("source sessions contain missing, extra or foreign identities")
    for session_id, expected_runs in expected_by_session.items():
        raw = source.session_store.session_path(DataOrigin.SYNTHETIC, session_id) / "raw"
        actual_runs = {path.name for path in raw.iterdir() if path.is_dir()}
        if actual_runs != expected_runs:
            raise AnalysisSourceError("source runs contain missing, extra or foreign identities")
    stage = work_orders[0].experiment_stage
    if any(row.work_order.experiment_stage != stage for row in rows):
        raise AnalysisSourceError("one execution cannot mix experiment stages")
    completion_bytes = (root / COMPLETION_NAME).read_bytes()
    completion = SyntheticProtocolExecutionCompletion.model_validate_json(completion_bytes)
    completed_at = completion.completed_at
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise AnalysisSourceError("source execution completed_at must be timezone-aware")
    completed_at_utc = completed_at.astimezone(UTC)
    return ValidatedAnalysisExecution(
        source=source,
        stage=stage,
        execution_manifest_sha256=hashlib.sha256((root / MANIFEST_NAME).read_bytes()).hexdigest(),
        execution_completion_sha256=hashlib.sha256(completion_bytes).hexdigest(),
        execution_completed_at=completed_at,
        execution_completed_at_utc=completed_at_utc,
        rows=tuple(rows),
    )


def validate_synthetic_analysis_sources(
    *,
    sources: list[AnalysisExecutionSource] | tuple[AnalysisExecutionSource, ...],
    analysis_spec: LoadedDevelopmentAnalysisMatrixSpec,
) -> ValidatedSyntheticAnalysisSources:
    """Replay each execution once and return a process-local typed capability."""

    if not sources:
        raise AnalysisSourceError("analysis requires at least one completed execution")
    executions = tuple(
        sorted((_validate_one(source) for source in sources), key=lambda item: item.stage)
    )
    stages = [execution.stage for execution in executions]
    if len(stages) != len(set(stages)):
        raise AnalysisSourceError("analysis sources contain duplicate stages")
    rows = tuple(
        sorted(
            (row for execution in executions for row in execution.rows),
            key=lambda row: (
                row.work_order.experiment_stage,
                row.work_order.global_planned_ordinal,
            ),
        )
    )
    aggregate = hashlib.sha256(
        canonical_json_bytes(
            [
                {
                    "stage": execution.stage,
                    "execution_id": execution.source.execution_id,
                    "manifest_sha256": execution.execution_manifest_sha256,
                    "completion_sha256": execution.execution_completion_sha256,
                    "ordered_work_order_sha256": hashlib.sha256(
                        canonical_json_bytes(
                            [row.work_order.work_order_sha256 for row in execution.rows]
                        )
                    ).hexdigest(),
                }
                for execution in executions
            ]
        )
    ).hexdigest()
    completed_at_utc, evidence_time = derive_latest_verified_execution_completion_utc(
        tuple(execution.execution_completed_at for execution in executions)
    )
    return ValidatedSyntheticAnalysisSources(
        analysis_spec=analysis_spec,
        executions=executions,
        rows=rows,
        ordered_source_aggregate_sha256=aggregate,
        execution_completed_at_utc=completed_at_utc,
        analysis_evidence_time=evidence_time,
        analysis_evidence_time_basis=ANALYSIS_EVIDENCE_TIME_BASIS,
        analysis_evidence_time_derivation_version=ANALYSIS_EVIDENCE_TIME_DERIVATION_VERSION,
    )


__all__ = [
    "ANALYSIS_EVIDENCE_TIME_BASIS",
    "ANALYSIS_EVIDENCE_TIME_DERIVATION_VERSION",
    "AnalysisExecutionSource",
    "AnalysisSourceError",
    "ValidatedAnalysisExecution",
    "ValidatedAnalysisRowSource",
    "ValidatedSyntheticAnalysisSources",
    "derive_latest_verified_execution_completion_utc",
    "validate_synthetic_analysis_sources",
]
