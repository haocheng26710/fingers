"""Plan-derived measurement identities and leak-free BLK reference membership."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from acoustic_ladder.domain.models import NodeState
from acoustic_ladder.protocol.synthetic_execution_models import SyntheticProtocolWorkOrder

SAFE_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


class MeasurementIdentity(BaseModel):
    """Immutable labels derived from one replay-validated protocol work order."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    row_id: str = Field(pattern=SAFE_ID_PATTERN)
    work_order_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_id: str = Field(pattern=SAFE_ID_PATTERN)
    experiment_stage: Literal[1, 2, 3, 4]
    global_planned_ordinal: int = Field(gt=0)
    session_local_measurement_order: int = Field(gt=0)
    session_index: int = Field(gt=0)
    reassembly_index: int = Field(gt=0)
    condition_block_order: int = Field(gt=0)
    canonical_condition_index: int = Field(gt=0)
    session_id: str = Field(pattern=SAFE_ID_PATTERN)
    reassembly_id: str = Field(pattern=SAFE_ID_PATTERN)
    run_id: str = Field(pattern=SAFE_ID_PATTERN)
    capture_id: str = Field(pattern=SAFE_ID_PATTERN)
    condition_id: str = Field(pattern=SAFE_ID_PATTERN)
    condition_role: str
    condition_label: str
    condition_node_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    node_states: dict[str, NodeState]
    session_group_id: str = Field(pattern=SAFE_ID_PATTERN)
    reassembly_group_id: str = Field(pattern=SAFE_ID_PATTERN)
    baseline_group_id: str = Field(pattern=SAFE_ID_PATTERN)
    selected_node_ids: tuple[str, ...]
    selected_state_ids: tuple[str, ...]
    selected_module_ids: tuple[str, ...]
    loading_directions: tuple[str, ...]
    repeat_kind: Literal["continuous_repeat"]
    continuous_repeat_index: int = Field(gt=0)
    proxy_state: bool
    is_all_blk: bool


def _identity(work_order: SyntheticProtocolWorkOrder) -> MeasurementIdentity:
    selected_states = tuple(work_order.node_states[node] for node in work_order.selected_nodes)
    derived_modules = tuple(state.module_id for state in selected_states)
    if derived_modules != tuple(work_order.selected_modules):
        raise ValueError("selected module labels differ from plan-derived NodeState order")
    stage = work_order.experiment_stage
    session_group = f"stage_{stage}_{work_order.session_id}"
    reassembly_group = f"{session_group}_{work_order.reassembly_id}"
    return MeasurementIdentity(
        row_id=(
            f"row_s{stage}_{work_order.execution_id}_w"
            f"{work_order.global_planned_ordinal:06d}_{work_order.work_order_sha256[:12]}"
        ),
        work_order_sha256=work_order.work_order_sha256,
        execution_id=work_order.execution_id,
        experiment_stage=stage,
        global_planned_ordinal=work_order.global_planned_ordinal,
        session_local_measurement_order=work_order.session_local_measurement_order,
        session_index=work_order.session_index,
        reassembly_index=work_order.reassembly_index,
        condition_block_order=work_order.condition_block_order,
        canonical_condition_index=work_order.canonical_condition_index,
        session_id=work_order.session_id,
        reassembly_id=work_order.reassembly_id,
        run_id=work_order.run_id,
        capture_id=work_order.capture_id,
        condition_id=work_order.condition_id,
        condition_role=work_order.condition_role,
        condition_label=work_order.condition_label,
        condition_node_state_sha256=work_order.condition_node_state_sha256,
        node_states=work_order.node_states,
        session_group_id=session_group,
        reassembly_group_id=reassembly_group,
        baseline_group_id=reassembly_group,
        selected_node_ids=tuple(work_order.selected_nodes),
        selected_state_ids=tuple(state.state_id for state in selected_states),
        selected_module_ids=derived_modules,
        loading_directions=tuple(state.loading_direction.value for state in selected_states),
        repeat_kind="continuous_repeat",
        continuous_repeat_index=work_order.continuous_repeat_index,
        proxy_state=any(state.proxy_state for state in selected_states),
        is_all_blk=all(state.module_id == "BLK" for state in work_order.node_states.values()),
    )


def derive_measurement_identities(
    work_orders: Sequence[SyntheticProtocolWorkOrder],
) -> tuple[MeasurementIdentity, ...]:
    """Derive canonical row labels without hard-coding node or condition matrices."""

    identities = tuple(
        sorted(
            (_identity(work_order) for work_order in work_orders),
            key=lambda row: (
                row.experiment_stage,
                row.execution_id,
                row.global_planned_ordinal,
            ),
        )
    )
    row_ids = [row.row_id for row in identities]
    if not identities:
        raise ValueError("analysis source contains no measurement work orders")
    if len(set(row_ids)) != len(row_ids):
        raise ValueError("measurement row identities are not unique")
    return identities


def build_baseline_reference_map(
    rows: Sequence[MeasurementIdentity],
) -> dict[str, tuple[str, ...]]:
    """Bind every row to all-BLK repeats in its own stage/session/reassembly group."""

    groups: dict[str, list[MeasurementIdentity]] = defaultdict(list)
    for row in rows:
        groups[row.baseline_group_id].append(row)
    references: dict[str, tuple[str, ...]] = {}
    for group_id in sorted(groups):
        group = sorted(groups[group_id], key=lambda row: row.row_id)
        stages = {row.experiment_stage for row in group}
        sessions = {row.session_id for row in group}
        reassemblies = {row.reassembly_id for row in group}
        if len(stages) != 1 or len(sessions) != 1 or len(reassemblies) != 1:
            raise ValueError("baseline group crosses a stage, session, or reassembly boundary")
        baseline_ids = tuple(row.row_id for row in group if row.is_all_blk)
        if len(baseline_ids) < 2:
            raise ValueError(f"baseline group {group_id} has fewer than two all-BLK repeats")
        for row in group:
            members = tuple(row_id for row_id in baseline_ids if row_id != row.row_id)
            if not members:
                raise ValueError(f"row {row.row_id} has no leak-free BLK reference member")
            references[row.row_id] = members
    return dict(sorted(references.items()))
