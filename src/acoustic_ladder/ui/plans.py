"""Project existing Stage 1-4 compiled plans into wizard-safe read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from acoustic_ladder.config.bundle import load_bundle
from acoustic_ladder.protocol.planning import (
    compile_development_protocol_plan,
    load_development_protocol_plan_spec,
)
from acoustic_ladder.protocol.planning_models import CompiledDevelopmentProtocolPlan

_PROTOCOL_FILES = {
    1: "stage1_single_bridge.yaml",
    2: "stage2_single_node_proxy_states.yaml",
    3: "stage3_two_node_interaction.yaml",
    4: "stage4_four_node_states.yaml",
}
_LOAD_TIME = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class StagePlanPreview:
    stage: int
    condition_count: int
    sweep_count: int
    assembly_confirmation_count: int


@dataclass(frozen=True)
class FormalPlanPreview:
    stages: tuple[StagePlanPreview, ...]
    total_assembly_confirmations: int
    total_sweeps: int


@dataclass(frozen=True)
class DemoNode:
    node_id: str
    module_id: str


@dataclass(frozen=True)
class DemoCondition:
    stage: int
    condition_id: str
    condition_label: str
    nodes: tuple[DemoNode, ...]


@dataclass(frozen=True)
class DemoPlan:
    mode: str
    repeat_count: int
    conditions: tuple[DemoCondition, ...]

    @property
    def sweep_count(self) -> int:
        return len(self.conditions) * self.repeat_count


@dataclass(frozen=True)
class WizardPlans:
    formal_preview: FormalPlanPreview
    demo_plan: DemoPlan


def _compile_stage(project_root: Path, stage: int) -> CompiledDevelopmentProtocolPlan:
    protocol_name = _PROTOCOL_FILES[stage]
    bundle = load_bundle(
        project_root=project_root,
        manifest_path=project_root / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=(project_root / "config/devices/device_manifest.provisional.sha256"),
        audio_path=project_root / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=project_root / "config/protocols" / protocol_name,
        analysis_path=project_root / "config/analysis/default.yaml",
        synthetic_path=project_root / "config/synthetic/default.yaml",
        now=lambda: _LOAD_TIME,
    )
    spec = load_development_protocol_plan_spec(
        project_root / f"tests/fixtures/protocol/stage{stage}_protocol_plan.development.yaml",
        project_root=project_root,
        bundle=bundle,
    )
    return compile_development_protocol_plan(
        bundle=bundle,
        spec=spec,
        plan_id=f"wizard-preview-stage{stage}",
    )


def load_wizard_plans(project_root: str | Path) -> WizardPlans:
    """Compile the existing development fixtures and derive the formal preview counts."""

    root = Path(project_root).resolve()
    compiled = tuple(_compile_stage(root, stage) for stage in sorted(_PROTOCOL_FILES))
    previews = tuple(
        StagePlanPreview(
            stage=plan.experiment_stage,
            condition_count=plan.condition_count,
            sweep_count=plan.planned_measurement_count,
            assembly_confirmation_count=(
                plan.condition_count * plan.session_count * plan.reassemblies_per_session
            ),
        )
        for plan in compiled
    )
    demo_conditions = tuple(
        DemoCondition(
            stage=condition.experiment_stage,
            condition_id=condition.condition_id,
            condition_label=condition.condition_label,
            nodes=tuple(
                DemoNode(node_id=node_id, module_id=state.module_id)
                for node_id, state in condition.node_states.items()
            ),
        )
        for condition in compiled[0].condition_matrix[:3]
    )
    return WizardPlans(
        formal_preview=FormalPlanPreview(
            stages=previews,
            total_assembly_confirmations=sum(
                stage.assembly_confirmation_count for stage in previews
            ),
            total_sweeps=sum(stage.sweep_count for stage in previews),
        ),
        demo_plan=DemoPlan(mode="development_demo", repeat_count=2, conditions=demo_conditions),
    )
