"""Load and compile deterministic development-only protocol condition matrices."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder.config.bundle import LoadedBundle, LoadedConfig, canonical_json_bytes
from acoustic_ladder.config.models import ProtocolConfig, StateDefinition, manifest_nodes
from acoustic_ladder.config.yaml_loader import ConfigYamlError, load_yaml_mapping
from acoustic_ladder.domain.models import NodeState, RunMode
from acoustic_ladder.domain.paths import validate_relative_path
from acoustic_ladder.protocol.planning_models import (
    PLAN_SAFETY_MARKER,
    CompiledDevelopmentProtocolPlan,
    CompiledProtocolCondition,
    DevelopmentProtocolPlanSpec,
    PlannedMeasurement,
    ProtocolConditionBlock,
    ProtocolReassemblySlot,
    ProtocolSessionSlot,
)
from acoustic_ladder.storage.io import StorageError, safe_identifier


class ProtocolPlanningError(ValueError):
    """A development plan spec or active protocol cannot be compiled safely."""


@dataclass(frozen=True)
class LoadedDevelopmentProtocolPlanSpec:
    model: DevelopmentProtocolPlanSpec
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


def _project_relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ProtocolPlanningError(f"plan spec is outside project root: {path}")
    return validate_relative_path(resolved.relative_to(resolved_root).as_posix())


def _current_protocol(bundle: LoadedBundle) -> tuple[ProtocolConfig, LoadedConfig]:
    loaded = bundle.configs.get("protocol")
    if loaded is None or not isinstance(loaded.model, ProtocolConfig):
        raise ProtocolPlanningError("development planning requires an active ProtocolConfig")
    return loaded.model, loaded


def load_development_protocol_plan_spec(
    path: str | Path,
    *,
    project_root: str | Path,
    bundle: LoadedBundle,
) -> LoadedDevelopmentProtocolPlanSpec:
    source = Path(path)
    root = Path(project_root)
    try:
        original = source.read_bytes()
        payload = load_yaml_mapping(source)
        model = DevelopmentProtocolPlanSpec.model_validate_json(
            json.dumps(payload, ensure_ascii=False, allow_nan=False)
        )
    except (OSError, UnicodeError, ConfigYamlError, ValidationError, ValueError) as exc:
        raise ProtocolPlanningError(
            f"invalid development protocol plan spec {source}: {exc}"
        ) from exc
    protocol, loaded = _current_protocol(bundle)
    del protocol
    if model.source_protocol_reference != loaded.snapshot.original_relative_path:
        raise ProtocolPlanningError("plan spec source protocol does not match the active bundle")
    protocol_path = root.resolve() / Path(*model.source_protocol_reference.split("/"))
    try:
        current_protocol = protocol_path.read_bytes()
    except OSError as exc:
        raise ProtocolPlanningError(f"source protocol is missing: {protocol_path}") from exc
    if hashlib.sha256(current_protocol).hexdigest() != loaded.snapshot.original_sha256:
        raise ProtocolPlanningError("source protocol bytes differ from the active bundle")
    normalized = canonical_json_bytes(model.model_dump(mode="json"))
    return LoadedDevelopmentProtocolPlanSpec(
        model=model,
        source_path=source.resolve(),
        project_root=root.resolve(),
        original_relative_path=_project_relative(source, root),
        original_bytes=original,
        normalized_bytes=normalized,
        original_sha256=hashlib.sha256(original).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        source_protocol_reference=model.source_protocol_reference,
        source_protocol_raw_sha256=loaded.snapshot.original_sha256,
        source_protocol_normalized_sha256=loaded.snapshot.normalized_sha256,
    )


def _node_state(node_id: str, state: StateDefinition, protocol: ProtocolConfig) -> NodeState:
    return NodeState(
        node_id=node_id,
        state_id=state.state_id,
        module_id=state.module_id,
        state_type=state.state_type,
        discrete_label=state.discrete_label,
        continuous_value=state.continuous_value,
        unit=state.unit,
        loading_direction=state.loading_direction,
        proxy_state=state.proxy_state,
        provenance=f"protocol:{protocol.protocol_id}:{protocol.protocol_version}",
        notes=state.notes,
    )


def _condition(
    *,
    protocol: ProtocolConfig,
    condition_id: str,
    role: str,
    label: str,
    selected: list[tuple[str, StateDefinition]],
    node_order: list[str],
    blocked: StateDefinition,
) -> CompiledProtocolCondition:
    selected_by_node = dict(selected)
    states = {
        node_id: _node_state(node_id, selected_by_node.get(node_id, blocked), protocol)
        for node_id in node_order
    }
    state_bytes = canonical_json_bytes(
        {node_id: state.model_dump(mode="json") for node_id, state in states.items()}
    )
    return CompiledProtocolCondition(
        condition_id=condition_id,
        experiment_stage=protocol.experiment_stage,
        condition_role=role,
        condition_label=label,
        selected_nodes=[node_id for node_id, _ in selected],
        selected_modules=[state.module_id for _, state in selected],
        node_states=states,
        node_state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        active_node_count=sum(state.module_id != blocked.module_id for state in states.values()),
        proxy_experiment=protocol.proxy_experiment,
        proxy_state=any(state.proxy_state for _, state in selected),
        source_protocol_reference=protocol.device_manifest_reference,
        source_state_ids=[state.state_id for _, state in selected] or [blocked.state_id],
        operator_confirmation_requirements=protocol.operator_confirmation_requirements,
        operator_confirmation_required=True,
        operator_confirmation_status="pending",
        protocol_execution_performed=False,
        hardware_io_performed=False,
        formal_eligible=False,
        experimental_result=False,
    )


def _validate_common(protocol: ProtocolConfig, node_order: list[str]) -> StateDefinition:
    if (
        protocol.run_mode is not RunMode.FORMAL
        or protocol.execution_ready
        or protocol.boundary_conditions.tx_near != "speaker"
        or protocol.boundary_conditions.rx_near != "microphone"
        or protocol.boundary_conditions.tx_far != "closed"
        or protocol.boundary_conditions.rx_far != "closed"
        or protocol.boundary_conditions.unselected_nodes != "BLK"
    ):
        raise ProtocolPlanningError("active protocol does not satisfy the fixed draft boundary")
    if not node_order or len(node_order) != len(set(node_order)):
        raise ProtocolPlanningError("manifest nodes must be non-empty and unique")
    modules = [state.module_id for state in protocol.state_definitions]
    blocked = [state for state in protocol.state_definitions if state.module_id == "BLK"]
    if len(blocked) != 1:
        raise ProtocolPlanningError("protocol must define exactly one BLK state")
    if len(modules) != len(set(modules)):
        raise ProtocolPlanningError("protocol state modules must be unique")
    if any(state.module_id not in protocol.allowed_modules for state in protocol.state_definitions):
        raise ProtocolPlanningError("state definition is outside allowed_modules")
    labels = [state.discrete_label for state in protocol.state_definitions]
    if len(labels) != len(set(labels)):
        raise ProtocolPlanningError("protocol state labels must be unique")
    return blocked[0]


def _stage1_conditions(
    protocol: ProtocolConfig, node_order: list[str], blocked: StateDefinition
) -> list[CompiledProtocolCondition]:
    if protocol.max_active_bridges != 1:
        raise ProtocolPlanningError("Stage 1 requires max_active_bridges=1")
    conditions = [
        _condition(
            protocol=protocol,
            condition_id="stage1_all_blk",
            role="all_blk_baseline",
            label=blocked.discrete_label or blocked.state_id,
            selected=[],
            node_order=node_order,
            blocked=blocked,
        )
    ]
    for state in protocol.state_definitions:
        if state is blocked:
            continue
        for node_id in node_order:
            conditions.append(
                _condition(
                    protocol=protocol,
                    condition_id=f"stage1_{state.state_id}_{node_id}",
                    role="single_bridge_state",
                    label=f"{node_id}:{state.discrete_label or state.state_id}",
                    selected=[(node_id, state)],
                    node_order=node_order,
                    blocked=blocked,
                )
            )
    return conditions


def _stage2_conditions(
    protocol: ProtocolConfig,
    node_order: list[str],
    blocked: StateDefinition,
    selected_nodes: list[str] | None,
) -> list[CompiledProtocolCondition]:
    if selected_nodes is None or len(selected_nodes) != 1:
        raise ProtocolPlanningError("Stage 2 development spec must select exactly one node")
    selected_node = selected_nodes[0]
    if selected_node not in node_order:
        raise ProtocolPlanningError(
            f"Stage 2 selected node is absent from manifest: {selected_node}"
        )
    if not protocol.proxy_experiment or protocol.max_active_bridges != 1:
        raise ProtocolPlanningError("Stage 2 requires proxy_experiment and max_active_bridges=1")
    return [
        _condition(
            protocol=protocol,
            condition_id=f"stage2_{state.state_id}_{selected_node}",
            role="proxy_state",
            label=f"{selected_node}:{state.discrete_label or state.state_id}",
            selected=[(selected_node, state)],
            node_order=node_order,
            blocked=blocked,
        )
        for state in protocol.state_definitions
    ]


def _binary_states(protocol: ProtocolConfig) -> dict[str, StateDefinition]:
    by_label = {
        state.discrete_label: state
        for state in protocol.state_definitions
        if state.discrete_label is not None
    }
    if set(by_label) != {"0", "1"} or len(protocol.state_definitions) != 2:
        raise ProtocolPlanningError("binary protocol must define exactly labels 0 and 1")
    return {"0": by_label["0"], "1": by_label["1"]}


def _stage3_conditions(
    protocol: ProtocolConfig,
    node_order: list[str],
    blocked: StateDefinition,
    selected_nodes: list[str] | None,
) -> list[CompiledProtocolCondition]:
    if selected_nodes is None or len(selected_nodes) != 2:
        raise ProtocolPlanningError("Stage 3 development spec must select exactly two nodes")
    unknown = sorted(set(selected_nodes) - set(node_order))
    if unknown:
        raise ProtocolPlanningError(f"Stage 3 selected nodes are absent from manifest: {unknown}")
    canonical_nodes = [node_id for node_id in node_order if node_id in selected_nodes]
    if protocol.binary_node_count != 2 or protocol.max_active_bridges != 2:
        raise ProtocolPlanningError("Stage 3 requires two binary nodes and max_active_bridges=2")
    labels = protocol.state_labels
    if (
        len(labels) != 4
        or len(labels) != len(set(labels))
        or set(labels) != {"00", "10", "01", "11"}
        or any(len(label) != 2 or set(label) - {"0", "1"} for label in labels)
    ):
        raise ProtocolPlanningError("Stage 3 state_labels must contain 00/10/01/11 exactly once")
    states = _binary_states(protocol)
    return [
        _condition(
            protocol=protocol,
            condition_id=f"stage3_{label}",
            role="binary_combination",
            label=label,
            selected=[
                (node_id, states[bit]) for node_id, bit in zip(canonical_nodes, label, strict=True)
            ],
            node_order=node_order,
            blocked=blocked,
        )
        for label in labels
    ]


def _stage4_conditions(
    protocol: ProtocolConfig,
    node_order: list[str],
    blocked: StateDefinition,
    spec_selected_nodes: list[str] | None,
) -> list[CompiledProtocolCondition]:
    if spec_selected_nodes is not None:
        raise ProtocolPlanningError("Stage 4 development spec cannot override selected nodes")
    selected_nodes = protocol.selected_nodes
    if (
        protocol.selection_source != "manifest_recommendation"
        or selected_nodes is None
        or len(selected_nodes) != 4
        or len(selected_nodes) != len(set(selected_nodes))
        or protocol.binary_node_count != 4
        or protocol.max_active_bridges != 4
    ):
        raise ProtocolPlanningError("Stage 4 requires four distinct manifest-recommended nodes")
    if any(node_id not in node_order for node_id in selected_nodes):
        raise ProtocolPlanningError("Stage 4 recommendation contains a node absent from manifest")
    states = _binary_states(protocol)
    if protocol.state_labels:
        labels = protocol.state_labels
        expected = {f"{value:04b}" for value in range(16)}
        if len(labels) != 16 or len(labels) != len(set(labels)) or set(labels) != expected:
            raise ProtocolPlanningError("Stage 4 state_labels must enumerate all 16 binary states")
    else:
        labels = [f"{value:04b}" for value in range(16)]
    return [
        _condition(
            protocol=protocol,
            condition_id=f"stage4_{label}",
            role="binary_combination",
            label=label,
            selected=[
                (node_id, states[bit]) for node_id, bit in zip(selected_nodes, label, strict=True)
            ],
            node_order=node_order,
            blocked=blocked,
        )
        for label in labels
    ]


def _ranked_conditions(
    conditions: list[CompiledProtocolCondition],
    *,
    spec: DevelopmentProtocolPlanSpec,
    protocol: ProtocolConfig,
    session_index: int,
    reassembly_index: int,
) -> list[CompiledProtocolCondition]:
    if not spec.randomization_enabled:
        return conditions
    ranked: list[tuple[str, str, CompiledProtocolCondition]] = []
    for condition in conditions:
        material = {
            "algorithm_id": "sha256_ranked_condition_blocks",
            "algorithm_version": "1.0.0",
            "random_seed": spec.random_seed,
            "protocol_id": protocol.protocol_id,
            "plan_spec_id": spec.plan_spec_id,
            "experiment_stage": protocol.experiment_stage,
            "session_index": session_index,
            "reassembly_index": reassembly_index,
            "condition_id": condition.condition_id,
        }
        digest = hashlib.sha256(canonical_json_bytes(material)).hexdigest()
        ranked.append((digest, condition.condition_id, condition))
    return [item[2] for item in sorted(ranked, key=lambda item: (item[0], item[1]))]


def _schedule(
    conditions: list[CompiledProtocolCondition],
    *,
    spec: DevelopmentProtocolPlanSpec,
    protocol: ProtocolConfig,
) -> list[ProtocolSessionSlot]:
    sessions: list[ProtocolSessionSlot] = []
    global_ordinal = 0
    canonical_indices = {
        condition.condition_id: index for index, condition in enumerate(conditions, start=1)
    }
    for session_index in range(1, spec.session_count + 1):
        session_order = 0
        reassemblies: list[ProtocolReassemblySlot] = []
        for reassembly_index in range(1, spec.reassemblies_per_session + 1):
            ordered = _ranked_conditions(
                conditions,
                spec=spec,
                protocol=protocol,
                session_index=session_index,
                reassembly_index=reassembly_index,
            )
            blocks: list[ProtocolConditionBlock] = []
            for block_order, condition in enumerate(ordered, start=1):
                measurements: list[PlannedMeasurement] = []
                for repeat_index in range(1, spec.continuous_repeats_per_condition + 1):
                    global_ordinal += 1
                    session_order += 1
                    measurements.append(
                        PlannedMeasurement(
                            global_planned_ordinal=global_ordinal,
                            session_local_measurement_order=session_order,
                            session_index=session_index,
                            reassembly_index=reassembly_index,
                            condition_block_order=block_order,
                            continuous_repeat_index=repeat_index,
                            condition_id=condition.condition_id,
                            node_states=condition.node_states,
                            operator_confirmation_status="pending",
                            protocol_execution_performed=False,
                            hardware_io_performed=False,
                            formal_eligible=False,
                            experimental_result=False,
                        )
                    )
                blocks.append(
                    ProtocolConditionBlock(
                        condition_block_order=block_order,
                        canonical_condition_index=canonical_indices[condition.condition_id],
                        condition_id=condition.condition_id,
                        measurements=measurements,
                    )
                )
            reassemblies.append(
                ProtocolReassemblySlot(
                    reassembly_index=reassembly_index,
                    condition_blocks=blocks,
                )
            )
        sessions.append(
            ProtocolSessionSlot(session_index=session_index, reassembly_slots=reassemblies)
        )
    return sessions


def _model_package_sha256(bundle: LoadedBundle) -> str:
    try:
        package = bundle.manifest["package"]
        assert isinstance(package, dict)
        digest = package["sha256"]
        assert isinstance(digest, str)
    except (AssertionError, KeyError, TypeError) as exc:
        raise ProtocolPlanningError(f"manifest model-package provenance is invalid: {exc}") from exc
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ProtocolPlanningError("manifest model-package SHA256 is invalid")
    return digest


def _validate_current_sources(
    bundle: LoadedBundle, spec: LoadedDevelopmentProtocolPlanSpec
) -> None:
    manifest_snapshot = bundle.receipt.snapshots.get("device_manifest")
    if manifest_snapshot is None:
        raise ProtocolPlanningError("active bundle has no manifest provenance")
    manifest_path = spec.project_root / Path(*manifest_snapshot.original_relative_path.split("/"))
    sidecar_path = manifest_path.with_suffix(".sha256")
    try:
        current_manifest = manifest_path.read_bytes()
        current_sidecar = sidecar_path.read_bytes()
    except OSError as exc:
        raise ProtocolPlanningError(f"manifest or sidecar source is missing: {exc}") from exc
    if (
        current_manifest != bundle.manifest_bytes
        or hashlib.sha256(current_manifest).hexdigest() != bundle.receipt.device_manifest_sha256
    ):
        raise ProtocolPlanningError("manifest source bytes differ from the loaded provenance")
    if current_sidecar != bundle.manifest_sidecar_bytes:
        raise ProtocolPlanningError("manifest sidecar bytes differ from the loaded provenance")
    try:
        current_spec = spec.source_path.read_bytes()
    except OSError as exc:
        raise ProtocolPlanningError(f"plan spec source is missing: {spec.source_path}") from exc
    if hashlib.sha256(current_spec).hexdigest() != spec.original_sha256:
        raise ProtocolPlanningError("plan spec source bytes differ from the loaded provenance")
    try:
        current_payload = load_yaml_mapping(spec.source_path)
        current_model = DevelopmentProtocolPlanSpec.model_validate_json(
            json.dumps(current_payload, ensure_ascii=False, allow_nan=False)
        )
    except (ConfigYamlError, ValidationError, ValueError) as exc:
        raise ProtocolPlanningError(f"current plan spec cannot be parsed: {exc}") from exc
    if current_model != spec.model:
        raise ProtocolPlanningError("plan spec parsed model differs from the loaded model")
    current_normalized = canonical_json_bytes(current_model.model_dump(mode="json"))
    if (
        current_normalized != spec.normalized_bytes
        or hashlib.sha256(current_normalized).hexdigest() != spec.normalized_sha256
    ):
        raise ProtocolPlanningError("plan spec normalized provenance is inconsistent")
    protocol_path = spec.project_root / Path(*spec.source_protocol_reference.split("/"))
    try:
        current_protocol = protocol_path.read_bytes()
    except OSError as exc:
        raise ProtocolPlanningError(f"source protocol is missing: {protocol_path}") from exc
    if hashlib.sha256(current_protocol).hexdigest() != spec.source_protocol_raw_sha256:
        raise ProtocolPlanningError("source protocol bytes differ from the loaded provenance")
    loaded = bundle.configs.get("protocol")
    if loaded is None or loaded.snapshot.original_sha256 != spec.source_protocol_raw_sha256:
        raise ProtocolPlanningError("active bundle protocol provenance differs from the plan spec")
    for kind, config in bundle.configs.items():
        source_path = spec.project_root / Path(*config.snapshot.original_relative_path.split("/"))
        try:
            source_bytes = source_path.read_bytes()
        except OSError as exc:
            raise ProtocolPlanningError(f"{kind} config source is missing: {source_path}") from exc
        if (
            source_bytes != config.original_bytes
            or hashlib.sha256(source_bytes).hexdigest() != config.snapshot.original_sha256
        ):
            raise ProtocolPlanningError(
                f"{kind} config source bytes differ from the loaded provenance"
            )
        normalized = canonical_json_bytes(config.model.model_dump(mode="json"))
        if (
            normalized != config.normalized_bytes
            or hashlib.sha256(normalized).hexdigest() != config.snapshot.normalized_sha256
        ):
            raise ProtocolPlanningError(f"{kind} config normalized provenance is inconsistent")


def compile_development_protocol_plan(
    *,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
) -> CompiledDevelopmentProtocolPlan:
    try:
        safe_identifier(plan_id, "plan_id")
    except (StorageError, ValueError) as exc:
        raise ProtocolPlanningError(str(exc)) from exc
    _validate_current_sources(bundle, spec)
    protocol, _ = _current_protocol(bundle)
    node_order = list(manifest_nodes(bundle.manifest))
    blocked = _validate_common(protocol, node_order)
    if protocol.experiment_stage == 1:
        if spec.model.selected_nodes is not None:
            raise ProtocolPlanningError("Stage 1 development spec must not select nodes")
        conditions = _stage1_conditions(protocol, node_order, blocked)
    elif protocol.experiment_stage == 2:
        conditions = _stage2_conditions(protocol, node_order, blocked, spec.model.selected_nodes)
    elif protocol.experiment_stage == 3:
        conditions = _stage3_conditions(protocol, node_order, blocked, spec.model.selected_nodes)
    elif protocol.experiment_stage == 4:
        conditions = _stage4_conditions(protocol, node_order, blocked, spec.model.selected_nodes)
    else:
        raise ProtocolPlanningError("this protocol-stage compiler slice is not yet available")
    conditions = [
        condition.model_copy(update={"source_protocol_reference": spec.source_protocol_reference})
        for condition in conditions
    ]
    total = (
        len(conditions)
        * spec.model.session_count
        * spec.model.reassemblies_per_session
        * spec.model.continuous_repeats_per_condition
    )
    if total > spec.model.max_planned_measurements:
        raise ProtocolPlanningError(
            f"planned measurement count {total} exceeds max_planned_measurements "
            f"{spec.model.max_planned_measurements}"
        )
    matrix_bytes = canonical_json_bytes(
        [condition.model_dump(mode="json") for condition in conditions]
    )
    sessions = _schedule(conditions, spec=spec.model, protocol=protocol)
    schedule_bytes = canonical_json_bytes([session.model_dump(mode="json") for session in sessions])
    manifest_snapshot = bundle.receipt.snapshots["device_manifest"]
    return CompiledDevelopmentProtocolPlan(
        schema_version="1.0.0",
        compiler_algorithm_id="development_protocol_matrix_compiler",
        compiler_algorithm_version="1.0.0",
        plan_id=plan_id,
        plan_spec_id=spec.model.plan_spec_id,
        plan_spec_reference=spec.original_relative_path,
        plan_spec_raw_sha256=spec.original_sha256,
        plan_spec_normalized_sha256=spec.normalized_sha256,
        protocol_reference=spec.source_protocol_reference,
        protocol_raw_sha256=spec.source_protocol_raw_sha256,
        protocol_normalized_sha256=spec.source_protocol_normalized_sha256,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        experiment_stage=protocol.experiment_stage,
        manifest_reference=manifest_snapshot.original_relative_path,
        manifest_sha256=bundle.receipt.device_manifest_sha256,
        model_package_sha256=_model_package_sha256(bundle),
        bundle_content_sha256=bundle.receipt.bundle_content_sha256,
        condition_count=len(conditions),
        condition_matrix=conditions,
        condition_matrix_sha256=hashlib.sha256(matrix_bytes).hexdigest(),
        planned_measurement_count=total,
        session_count=spec.model.session_count,
        reassemblies_per_session=spec.model.reassemblies_per_session,
        continuous_repeats_per_condition=spec.model.continuous_repeats_per_condition,
        randomization_enabled=spec.model.randomization_enabled,
        randomization_algorithm_id="sha256_ranked_condition_blocks",
        randomization_algorithm_version="1.0.0",
        random_seed=spec.model.random_seed,
        session_slots=sessions,
        schedule_sha256=hashlib.sha256(schedule_bytes).hexdigest(),
        all_node_states_complete=True,
        operator_confirmation_required=True,
        operator_confirmation_status="pending",
        development_fixture=True,
        protocol_execution_performed=False,
        hardware_io_performed=False,
        formal_eligible=False,
        experimental_result=False,
        safety_marker=PLAN_SAFETY_MARKER,
    )
