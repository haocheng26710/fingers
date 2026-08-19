"""Load and resolve a strict Stage 1 development condition plan."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder.audio.condition_plan_models import (
    DevelopmentConditionDefinition,
    DevelopmentConditionPlan,
    ResolvedConditionBinding,
)
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import (
    ProtocolConfig,
    StateDefinition,
    manifest_module_ids,
    manifest_nodes,
)
from acoustic_ladder.config.yaml_loader import ConfigYamlError, load_yaml_mapping
from acoustic_ladder.domain.models import NodeState, RunMode
from acoustic_ladder.domain.paths import validate_relative_path


class ConditionPlanError(ValueError):
    """Raised when a development plan cannot bind to the verified Stage 1 inputs."""


@dataclass(frozen=True)
class LoadedDevelopmentConditionPlan:
    model: DevelopmentConditionPlan
    source_path: Path
    project_root: Path
    original_relative_path: str
    original_bytes: bytes
    normalized_bytes: bytes
    original_sha256: str
    normalized_sha256: str
    source_protocol_reference: str
    source_protocol_raw_sha256: str
    source_protocol_normalized_sha256: str
    device_manifest_sha256: str
    bindings: tuple[ResolvedConditionBinding, ...]

    def binding(self, condition_id: str) -> ResolvedConditionBinding:
        matches = [item for item in self.bindings if item.condition_id == condition_id]
        if len(matches) != 1:
            raise ConditionPlanError(f"expected one resolved condition: {condition_id!r}")
        return matches[0]


def _project_relative(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    root = project_root.resolve()
    if not resolved.is_relative_to(root):
        raise ConditionPlanError(f"condition plan is outside project root: {path}")
    return validate_relative_path(resolved.relative_to(root).as_posix())


def _node_state(node_id: str, definition: StateDefinition, plan_id: str) -> NodeState:
    return NodeState(
        node_id=node_id,
        state_id=definition.state_id,
        module_id=definition.module_id,
        state_type=definition.state_type,
        discrete_label=definition.discrete_label,
        continuous_value=definition.continuous_value,
        unit=definition.unit,
        loading_direction=definition.loading_direction,
        proxy_state=definition.proxy_state,
        provenance=f"development_condition_plan:{plan_id}",
        notes=definition.notes,
    )


def _resolve(
    plan: DevelopmentConditionPlan,
    condition: DevelopmentConditionDefinition,
    protocol: ProtocolConfig,
    bundle: LoadedBundle,
) -> ResolvedConditionBinding:
    nodes = manifest_nodes(bundle.manifest)
    modules = manifest_module_ids(bundle.manifest)
    by_module = {definition.module_id: definition for definition in protocol.state_definitions}
    if "BLK" not in by_module:
        raise ConditionPlanError("Stage 1 protocol has no BLK state definition")
    if condition.selected_node is not None and condition.selected_node not in nodes:
        raise ConditionPlanError(f"condition contains unknown node: {condition.selected_node}")
    if condition.selected_module is not None:
        if condition.selected_module not in modules:
            raise ConditionPlanError(
                f"condition contains module absent from manifest: {condition.selected_module}"
            )
        if condition.selected_module not in protocol.allowed_modules:
            raise ConditionPlanError(
                f"condition contains module outside Stage 1 protocol: {condition.selected_module}"
            )
        if condition.selected_module not in by_module:
            raise ConditionPlanError(
                f"condition has no Stage 1 state definition: {condition.selected_module}"
            )
        if condition.selected_module == "BLK":
            raise ConditionPlanError("single-bridge candidate cannot select BLK")
    selected_definition = (
        by_module[condition.selected_module]
        if condition.selected_module is not None
        else by_module["BLK"]
    )
    states = {
        node_id: _node_state(
            node_id,
            selected_definition if node_id == condition.selected_node else by_module["BLK"],
            plan.condition_plan_id,
        )
        for node_id in nodes
    }
    return ResolvedConditionBinding(
        condition_id=condition.condition_id,
        condition_role=condition.condition_role,
        resolved_node_states=states,
        non_blk_node_count=sum(state.module_id != "BLK" for state in states.values()),
    )


def load_development_condition_plan(
    path: str | Path,
    *,
    project_root: str | Path,
    bundle: LoadedBundle,
) -> LoadedDevelopmentConditionPlan:
    """Bind a development fixture plan to the active verified Stage 1 bundle."""

    source = Path(path)
    root = Path(project_root)
    try:
        original = source.read_bytes()
        payload = load_yaml_mapping(source)
        model = DevelopmentConditionPlan.model_validate_json(
            json.dumps(payload, ensure_ascii=False, allow_nan=False)
        )
    except (OSError, UnicodeError, ConfigYamlError, ValidationError, ValueError) as exc:
        raise ConditionPlanError(f"invalid development condition plan {source}: {exc}") from exc
    protocol_loaded = bundle.configs.get("protocol")
    if protocol_loaded is None or not isinstance(protocol_loaded.model, ProtocolConfig):
        raise ConditionPlanError("condition plan requires an active ProtocolConfig")
    protocol = protocol_loaded.model
    if (
        protocol.experiment_stage != 1
        or protocol.execution_ready
        or protocol.run_mode is not RunMode.FORMAL
        or protocol.max_active_bridges != 1
        or protocol.boundary_conditions.tx_near != "speaker"
        or protocol.boundary_conditions.rx_near != "microphone"
        or protocol.boundary_conditions.tx_far != "closed"
        or protocol.boundary_conditions.rx_far != "closed"
        or protocol.boundary_conditions.unselected_nodes != "BLK"
    ):
        raise ConditionPlanError("condition plan requires the verified Stage 1 draft boundary")
    if model.source_protocol_reference != protocol_loaded.snapshot.original_relative_path:
        raise ConditionPlanError(
            "condition plan source protocol does not match the active bundle ProtocolConfig"
        )
    normalized = canonical_json_bytes(model.model_dump(mode="json"))
    bindings = tuple(_resolve(model, item, protocol, bundle) for item in model.conditions)
    return LoadedDevelopmentConditionPlan(
        model=model,
        source_path=source.resolve(),
        project_root=root.resolve(),
        original_relative_path=_project_relative(source, root),
        original_bytes=original,
        normalized_bytes=normalized,
        original_sha256=hashlib.sha256(original).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        source_protocol_reference=model.source_protocol_reference,
        source_protocol_raw_sha256=protocol_loaded.snapshot.original_sha256,
        source_protocol_normalized_sha256=protocol_loaded.snapshot.normalized_sha256,
        device_manifest_sha256=bundle.receipt.device_manifest_sha256,
        bindings=bindings,
    )
