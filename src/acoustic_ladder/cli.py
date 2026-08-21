"""Auditable configuration, storage, synthetic, and offline-audio CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder import __version__
from acoustic_ladder.analysis.models import AnalysisSourceBinding
from acoustic_ladder.analysis.persistence import (
    SyntheticMeasurementMatrixStore,
    compute_synthetic_measurement_matrix,
    validate_synthetic_measurement_matrix,
)
from acoustic_ladder.analysis.report_export import export_research_report
from acoustic_ladder.analysis.research import run_research_analysis
from acoustic_ladder.analysis.source_validation import AnalysisExecutionSource
from acoustic_ladder.analysis.spec import load_development_analysis_matrix_spec
from acoustic_ladder.audio.backend import SoundDeviceInventoryBackend
from acoustic_ladder.audio.baseline_difference_models import RepeatabilitySourceIdentity
from acoustic_ladder.audio.baseline_difference_persistence import (
    publish_provisional_baseline_difference,
    validate_provisional_baseline_difference,
)
from acoustic_ladder.audio.condition_plan import load_development_condition_plan
from acoustic_ladder.audio.conditioned_virtual_capture import (
    load_conditioned_virtual_capture_scenario,
    publish_conditioned_virtual_capture,
    validate_conditioned_virtual_capture,
)
from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    LoadedConditionedVirtualCaptureScenario,
)
from acoustic_ladder.audio.context_validation import validate_audio_context_bundle
from acoustic_ladder.audio.ess_processing_persistence import (
    CaptureScenario,
    publish_ess_processing,
    validate_ess_processing,
)
from acoustic_ladder.audio.excitation_persistence import (
    SAFETY_MARKER,
    publish_offline_ess_artifact,
    validate_offline_ess_artifact,
)
from acoustic_ladder.audio.inventory import collect_inventory
from acoustic_ladder.audio.models import (
    AudioInventoryCaptureContext,
    AudioInventorySnapshot,
    AudioPreflightReport,
    HardwareSetupRecord,
)
from acoustic_ladder.audio.persistence import (
    load_audio_artifact,
    persist_audio_artifact,
    persist_bytes_with_sidecar,
)
from acoustic_ladder.audio.preflight import (
    build_contextual_preflight_report,
    build_preflight_report,
)
from acoustic_ladder.audio.provisional_qc_persistence import (
    publish_provisional_qc,
    validate_provisional_qc,
)
from acoustic_ladder.audio.repeatability_models import RepeatabilityMemberIdentity
from acoustic_ladder.audio.repeatability_persistence import (
    publish_provisional_repeatability,
    validate_provisional_repeatability,
)
from acoustic_ladder.audio.summary import render_inventory_summary
from acoustic_ladder.audio.virtual_capture_models import (
    LoadedVirtualCaptureScenario,
    load_virtual_capture_scenario,
)
from acoustic_ladder.audio.virtual_capture_persistence import (
    publish_virtual_capture,
    validate_virtual_capture,
)
from acoustic_ladder.config.bundle import LoadedBundle, load_bundle, load_config
from acoustic_ladder.config.models import ProtocolConfig, SyntheticConfig, manifest_nodes
from acoustic_ladder.config.schema import check_schemas, export_schemas
from acoustic_ladder.domain.models import (
    ArtifactRef,
    DataOrigin,
    LoadingDirection,
    MeasurementRunRecord,
    NodeState,
    ReassemblyRecord,
    RunMode,
    SessionRecord,
)
from acoustic_ladder.protocol.planning import load_development_protocol_plan_spec
from acoustic_ladder.protocol.planning_persistence import (
    DevelopmentProtocolPlanStore,
    publish_development_protocol_plan,
    validate_development_protocol_plan,
)
from acoustic_ladder.protocol.rehearsal import (
    DevelopmentProtocolRehearsalStore,
    apply_protocol_rehearsal_transition,
    initialize_protocol_rehearsal,
    read_protocol_rehearsal_status,
    validate_protocol_rehearsal,
)
from acoustic_ladder.protocol.rehearsal_models import (
    ProtocolRehearsalConcurrencyToken,
    ProtocolRehearsalTransitionCommand,
)
from acoustic_ladder.protocol.synthetic_execution import (
    DevelopmentSyntheticProtocolExecutionStore,
    apply_synthetic_protocol_execution_control,
    execute_next_synthetic_protocol_work_order,
    initialize_synthetic_protocol_execution,
    read_synthetic_protocol_execution_status,
    recover_current_synthetic_protocol_work_order,
    validate_synthetic_protocol_execution,
)
from acoustic_ladder.protocol.synthetic_execution_models import (
    SyntheticProtocolExecutionConcurrencyToken,
    SyntheticProtocolExecutionControl,
)
from acoustic_ladder.storage.io import atomic_write_bytes
from acoustic_ladder.storage.store import (
    DataRoots,
    ImmutableSessionStore,
    read_json_object,
    verify_artifact,
)
from acoustic_ladder.synthetic.generator import generate_synthetic_arrays, validate_npz_metadata


def _now() -> datetime:
    return datetime.now(UTC)


def _repeatability_member(value: str) -> RepeatabilityMemberIdentity:
    parts = value.split(":")
    if len(parts) != 3 or any(not part for part in parts):
        raise argparse.ArgumentTypeError(
            "repeatability member must be SOURCE_RUN_ID:PROCESSING_ID:QC_ID"
        )
    try:
        return RepeatabilityMemberIdentity(
            source_run_id=parts[0], processing_id=parts[1], qc_id=parts[2]
        )
    except ValidationError as exc:
        raise argparse.ArgumentTypeError(f"invalid repeatability member: {exc}") from exc


def _add_bundle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--manifest", default="config/devices/device_manifest.provisional.json")
    parser.add_argument(
        "--manifest-sidecar", default="config/devices/device_manifest.provisional.sha256"
    )
    parser.add_argument("--audio", default="config/audio/default_1x1_ess.yaml")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--analysis", default="config/analysis/default.yaml")
    parser.add_argument("--synthetic", default="config/synthetic/default.yaml")


def _load_bundle(args: argparse.Namespace) -> LoadedBundle:
    root = Path(args.project_root).resolve()
    return load_bundle(
        project_root=root,
        manifest_path=root / args.manifest,
        manifest_sidecar_path=root / args.manifest_sidecar,
        audio_path=root / args.audio,
        protocol_path=root / args.protocol,
        analysis_path=root / args.analysis,
        synthetic_path=root / args.synthetic if args.synthetic else None,
        now=_now,
    )


def _synthetic_store(synthetic_root: str | Path) -> ImmutableSessionStore:
    root = Path(synthetic_root).resolve()
    unavailable_real_root = root.parent / ".real_root_unavailable_to_synthetic_cli"
    return ImmutableSessionStore(DataRoots(synthetic=root, real=unavailable_real_root))


def _loaded_capture_scenario(args: argparse.Namespace, project_root: Path) -> CaptureScenario:
    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        scenario_path = project_root / scenario_path
    if getattr(args, "condition_plan", None):
        return load_conditioned_virtual_capture_scenario(scenario_path, project_root=project_root)
    return load_virtual_capture_scenario(scenario_path, project_root=project_root)


def _audio_backend() -> SoundDeviceInventoryBackend:
    return SoundDeviceInventoryBackend()


def _audio_safety_marker() -> None:
    print("NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED")


def _analysis_sources(args: argparse.Namespace) -> tuple[AnalysisExecutionSource, ...]:
    root = Path(args.project_root).resolve()
    fields = (
        args.protocol,
        args.plan_spec,
        args.development_plan_root,
        args.development_execution_root,
        args.source_synthetic_root,
        args.execution_id,
        args.plan_id,
        args.ess_artifact_root,
    )
    if any(len(values) != 4 for values in fields):
        raise ValueError("analysis matrix requires exactly four values for every stage source")
    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        scenario_path = root / scenario_path
    scenario = load_conditioned_virtual_capture_scenario(scenario_path, project_root=root)
    sources: list[AnalysisExecutionSource] = []
    for index in range(4):
        bundle = load_bundle(
            project_root=root,
            manifest_path=root / args.manifest,
            manifest_sidecar_path=root / args.manifest_sidecar,
            audio_path=root / args.audio,
            protocol_path=root / args.protocol[index],
            analysis_path=root / args.analysis,
            synthetic_path=root / args.synthetic,
            now=_now,
        )
        spec = load_development_protocol_plan_spec(
            root / args.plan_spec[index], project_root=root, bundle=bundle
        )
        synthetic_root = Path(args.source_synthetic_root[index]).resolve()
        sources.append(
            AnalysisExecutionSource(
                store=DevelopmentSyntheticProtocolExecutionStore(
                    Path(args.development_execution_root[index]).resolve()
                ),
                session_store=ImmutableSessionStore(
                    DataRoots(
                        synthetic=synthetic_root,
                        real=synthetic_root.parent / ".real_root_unavailable_to_analysis_cli",
                    )
                ),
                plan_store=DevelopmentProtocolPlanStore(
                    Path(args.development_plan_root[index]).resolve()
                ),
                bundle=bundle,
                spec=spec,
                plan_id=args.plan_id[index],
                execution_id=args.execution_id[index],
                scenario=scenario,
                ess_artifact_root=Path(args.ess_artifact_root[index]).resolve(),
            )
        )
    return tuple(sources)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acoustic-ladder")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-config")
    validate.add_argument("kind", choices=("audio", "protocol", "analysis", "synthetic"))
    validate.add_argument("path")
    validate.add_argument("--project-root", default=".")
    validate.add_argument("--manifest", default="config/devices/device_manifest.provisional.json")

    bundle = commands.add_parser("validate-bundle")
    _add_bundle_arguments(bundle)

    config_hash = commands.add_parser("config-hash")
    config_hash.add_argument("kind", choices=("audio", "protocol", "analysis", "synthetic"))
    config_hash.add_argument("path")
    config_hash.add_argument("--project-root", default=".")
    config_hash.add_argument(
        "--manifest", default="config/devices/device_manifest.provisional.json"
    )

    schemas = commands.add_parser("export-schemas")
    schemas.add_argument("--output-dir", default="schemas")
    schemas.add_argument("--check", action="store_true")

    for command_name in ("protocol-plan-compile", "protocol-plan-validate"):
        protocol_plan = commands.add_parser(command_name)
        _add_bundle_arguments(protocol_plan)
        protocol_plan.add_argument("--plan-spec", required=True)
        protocol_plan.add_argument("--development-plan-root", required=True)
        protocol_plan.add_argument("--plan-id", required=True)

    for command_name in (
        "protocol-rehearsal-init",
        "protocol-rehearsal-status",
        "protocol-rehearsal-step",
        "protocol-rehearsal-validate",
    ):
        rehearsal = commands.add_parser(command_name)
        _add_bundle_arguments(rehearsal)
        rehearsal.add_argument("--plan-spec", required=True)
        rehearsal.add_argument("--development-plan-root", required=True)
        rehearsal.add_argument("--plan-id", required=True)
        rehearsal.add_argument("--development-rehearsal-root", required=True)
        rehearsal.add_argument("--rehearsal-id", required=True)
        if command_name == "protocol-rehearsal-step":
            rehearsal.add_argument(
                "--action",
                required=True,
                choices=(
                    "present-requirements",
                    "claim",
                    "mark-rehearsed",
                    "mark-failed",
                    "retry",
                    "pause",
                    "resume",
                    "abort",
                ),
            )
            rehearsal.add_argument("--actor-id", required=True)
            rehearsal.add_argument("--expected-event-sequence", required=True, type=int)
            rehearsal.add_argument("--expected-head-sha256", required=True)
            rehearsal.add_argument("--expected-work-order-sha256", required=True)
            rehearsal.add_argument("--reason-code")
            rehearsal.add_argument("--detail")

    execution_commands = (
        "synthetic-protocol-execution-init",
        "synthetic-protocol-execution-status",
        "synthetic-protocol-execution-execute-next",
        "synthetic-protocol-execution-pause",
        "synthetic-protocol-execution-resume",
        "synthetic-protocol-execution-retry",
        "synthetic-protocol-execution-recover-current",
        "synthetic-protocol-execution-abort",
        "synthetic-protocol-execution-validate",
    )
    for command_name in execution_commands:
        execution = commands.add_parser(command_name)
        _add_bundle_arguments(execution)
        execution.add_argument("--plan-spec", required=True)
        execution.add_argument("--development-plan-root", required=True)
        execution.add_argument("--plan-id", required=True)
        execution.add_argument("--development-execution-root", required=True)
        execution.add_argument("--synthetic-root", required=True)
        execution.add_argument("--execution-id", required=True)
        execution.add_argument("--scenario", required=True)
        execution.add_argument("--ess-artifact-root", required=True)
        if command_name not in {
            "synthetic-protocol-execution-init",
            "synthetic-protocol-execution-status",
            "synthetic-protocol-execution-validate",
        }:
            execution.add_argument("--actor-id", required=True)
            execution.add_argument("--expected-event-sequence", required=True, type=int)
            execution.add_argument("--expected-head-sha256", required=True)
            execution.add_argument("--expected-work-order-sha256", required=True)
            execution.add_argument("--expected-cursor", required=True, type=int)
            execution.add_argument("--expected-recovery-run-id")
        if command_name == "synthetic-protocol-execution-abort":
            execution.add_argument("--reason-code", required=True)

    for command_name in ("analysis-matrix-compute", "analysis-matrix-validate"):
        matrix = commands.add_parser(command_name)
        matrix.add_argument("--project-root", default=".")
        matrix.add_argument("--manifest", default="config/devices/device_manifest.provisional.json")
        matrix.add_argument(
            "--manifest-sidecar", default="config/devices/device_manifest.provisional.sha256"
        )
        matrix.add_argument("--audio", required=True)
        matrix.add_argument("--analysis", default="config/analysis/default.yaml")
        matrix.add_argument("--synthetic", default="config/synthetic/default.yaml")
        matrix.add_argument("--protocol", action="append", required=True)
        matrix.add_argument("--plan-spec", action="append", required=True)
        matrix.add_argument("--development-plan-root", action="append", required=True)
        matrix.add_argument("--development-execution-root", action="append", required=True)
        matrix.add_argument("--source-synthetic-root", action="append", required=True)
        matrix.add_argument("--execution-id", action="append", required=True)
        matrix.add_argument("--plan-id", action="append", required=True)
        matrix.add_argument("--ess-artifact-root", action="append", required=True)
        matrix.add_argument("--scenario", required=True)
        matrix.add_argument("--development-analysis-spec", required=True)
        matrix.add_argument("--analysis-root", required=True)
        matrix.add_argument("--analysis-id", required=True)

    research = commands.add_parser("research-analyze")
    research.add_argument("--analysis-dir", required=True)
    research.add_argument("--output-dir", required=True)
    research.add_argument("--random-seed", type=int, default=602)

    report = commands.add_parser("research-report-export")
    report.add_argument("--research-output-dir", required=True)
    report.add_argument("--output-dir", required=True)

    session = commands.add_parser("create-synthetic-session")
    _add_bundle_arguments(session)
    session.add_argument("--synthetic-root", required=True)
    session.add_argument("--session-id", required=True)
    session.add_argument("--reassembly-id", required=True)

    run = commands.add_parser("generate-synthetic-run")
    _add_bundle_arguments(run)
    run.add_argument("--synthetic-root", required=True)
    run.add_argument("--session-id", required=True)
    run.add_argument("--reassembly-id", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--measurement-order", type=int, default=0)
    run.add_argument("--node-state", action="append", default=[])
    run.add_argument("--session-index", type=int, default=0)
    run.add_argument("--reassembly-index", type=int, default=0)

    validate_session = commands.add_parser("validate-session")
    validate_session.add_argument("--synthetic-root", required=True)
    validate_session.add_argument("--session-id", required=True)

    validate_run = commands.add_parser("validate-run")
    validate_run.add_argument("--synthetic-root", required=True)
    validate_run.add_argument("--session-id", required=True)
    validate_run.add_argument("--run-id", required=True)

    artifact = commands.add_parser("verify-artifact")
    artifact.add_argument("--session-root", required=True)
    artifact.add_argument("--artifact-ref", required=True)

    commands.add_parser("audio-list")

    inventory = commands.add_parser("audio-inventory")
    inventory.add_argument("--output", required=True)
    inventory.add_argument("--sidecar", required=True)

    preflight = commands.add_parser("audio-preflight")
    preflight.add_argument("--inventory", required=True)
    preflight.add_argument("--inventory-sidecar", required=True)
    preflight.add_argument("--hardware-setup", required=True)
    preflight.add_argument("--output", required=True)
    preflight.add_argument(
        "--inventory-reference",
        default="reference/audio/inventory/DEV-03.01_audio_inventory.json",
    )
    preflight.add_argument(
        "--hardware-setup-reference",
        default="reference/audio/hardware_setup.provisional.json",
    )

    audio_validate = commands.add_parser("audio-validate")
    audio_validate.add_argument("--inventory", required=True)
    audio_validate.add_argument("--inventory-sidecar", required=True)
    audio_validate.add_argument("--preflight", required=True)

    contextual = commands.add_parser("audio-contextual-preflight")
    contextual.add_argument("--inventory", required=True)
    contextual.add_argument("--inventory-sidecar", required=True)
    contextual.add_argument("--context", required=True)
    contextual.add_argument("--context-sidecar", required=True)
    contextual.add_argument("--hardware-setup", required=True)
    contextual.add_argument("--output", required=True)
    contextual.add_argument("--output-sidecar", required=True)
    contextual.add_argument(
        "--inventory-reference",
        default="reference/audio/inventory/DEV-03.01_audio_inventory.json",
    )
    contextual.add_argument(
        "--context-reference",
        default="reference/audio/inventory/DEV-03.02_inventory_capture_context.json",
    )
    contextual.add_argument(
        "--hardware-setup-reference",
        default="reference/audio/hardware_setup.provisional.json",
    )

    summary = commands.add_parser("audio-inventory-summary")
    summary.add_argument("--inventory", required=True)
    summary.add_argument("--inventory-sidecar", required=True)
    summary.add_argument("--context", required=True)
    summary.add_argument("--context-sidecar", required=True)
    summary.add_argument("--output", required=True)
    summary.add_argument("--output-sidecar", required=True)
    summary.add_argument(
        "--inventory-reference",
        default="reference/audio/inventory/DEV-03.01_audio_inventory.json",
    )
    summary.add_argument(
        "--context-reference",
        default="reference/audio/inventory/DEV-03.02_inventory_capture_context.json",
    )

    context_validate = commands.add_parser("audio-context-validate")
    context_validate.add_argument("--inventory", required=True)
    context_validate.add_argument("--inventory-sidecar", required=True)
    context_validate.add_argument("--context", required=True)
    context_validate.add_argument("--context-sidecar", required=True)
    context_validate.add_argument("--summary", required=True)
    context_validate.add_argument("--summary-sidecar", required=True)
    context_validate.add_argument("--contextual-preflight", required=True)
    context_validate.add_argument("--contextual-preflight-sidecar", required=True)
    context_validate.add_argument("--project-root", default=".")
    context_validate.add_argument(
        "--hardware-setup", default="reference/audio/hardware_setup.provisional.json"
    )
    context_validate.add_argument(
        "--inventory-reference",
        default="reference/audio/inventory/DEV-03.01_audio_inventory.json",
    )
    context_validate.add_argument(
        "--context-reference",
        default="reference/audio/inventory/DEV-03.02_inventory_capture_context.json",
    )
    context_validate.add_argument(
        "--hardware-setup-reference",
        default="reference/audio/hardware_setup.provisional.json",
    )

    ess_generate = commands.add_parser("ess-generate-offline")
    ess_generate.add_argument("--project-root", default=".")
    ess_generate.add_argument("--audio-config", required=True)
    ess_generate.add_argument("--development-root", required=True)
    ess_generate.add_argument("--artifact-id", required=True)

    ess_validate = commands.add_parser("ess-validate-offline")
    ess_validate.add_argument("--project-root", default=".")
    ess_validate.add_argument("--audio-config", required=True)
    ess_validate.add_argument("--artifact-root", required=True)

    simulate_capture = commands.add_parser("simulate-duplex-capture")
    _add_bundle_arguments(simulate_capture)
    simulate_capture.add_argument("--synthetic-root", required=True)
    simulate_capture.add_argument("--session-id", required=True)
    simulate_capture.add_argument("--reassembly-id", required=True)
    simulate_capture.add_argument("--run-id", required=True)
    simulate_capture.add_argument("--measurement-order", type=int, default=0)
    simulate_capture.add_argument("--scenario", required=True)
    simulate_capture.add_argument("--ess-artifact-root", required=True)

    conditioned_capture = commands.add_parser("simulate-conditioned-capture")
    _add_bundle_arguments(conditioned_capture)
    conditioned_capture.add_argument("--synthetic-root", required=True)
    conditioned_capture.add_argument("--session-id", required=True)
    conditioned_capture.add_argument("--reassembly-id", required=True)
    conditioned_capture.add_argument("--run-id", required=True)
    conditioned_capture.add_argument("--measurement-order", type=int, default=0)
    conditioned_capture.add_argument("--scenario", required=True)
    conditioned_capture.add_argument("--condition-plan", required=True)
    conditioned_capture.add_argument("--condition-id", required=True)
    conditioned_capture.add_argument("--ess-artifact-root", required=True)

    conditioned_validate = commands.add_parser("validate-conditioned-capture")
    _add_bundle_arguments(conditioned_validate)
    conditioned_validate.add_argument("--synthetic-root", required=True)
    conditioned_validate.add_argument("--session-id", required=True)
    conditioned_validate.add_argument("--run-id", required=True)
    conditioned_validate.add_argument("--scenario", required=True)
    conditioned_validate.add_argument("--condition-plan", required=True)
    conditioned_validate.add_argument("--ess-artifact-root", required=True)

    validate_capture = commands.add_parser("validate-simulated-capture")
    _add_bundle_arguments(validate_capture)
    validate_capture.add_argument("--synthetic-root", required=True)
    validate_capture.add_argument("--session-id", required=True)
    validate_capture.add_argument("--run-id", required=True)
    validate_capture.add_argument("--scenario", required=True)
    validate_capture.add_argument("--ess-artifact-root", required=True)

    for command_name in ("process-simulated-capture", "validate-simulated-processing"):
        processing = commands.add_parser(command_name)
        _add_bundle_arguments(processing)
        processing.add_argument("--synthetic-root", required=True)
        processing.add_argument("--session-id", required=True)
        processing.add_argument("--source-run-id", required=True)
        processing.add_argument("--processing-id", required=True)
        processing.add_argument("--scenario", required=True)
        processing.add_argument("--ess-artifact-root", required=True)
        processing.add_argument("--condition-plan")
    for command_name in ("qc-compute", "qc-validate"):
        qc = commands.add_parser(command_name)
        _add_bundle_arguments(qc)
        qc.add_argument("--synthetic-root", required=True)
        qc.add_argument("--session-id", required=True)
        qc.add_argument("--source-run-id", required=True)
        qc.add_argument("--processing-id", required=True)
        qc.add_argument("--qc-id", required=True)
        qc.add_argument("--scenario", required=True)
        qc.add_argument("--ess-artifact-root", required=True)
        qc.add_argument("--condition-plan")
    for command_name in ("repeatability-compute", "repeatability-validate"):
        repeatability = commands.add_parser(command_name)
        _add_bundle_arguments(repeatability)
        repeatability.add_argument("--synthetic-root", required=True)
        repeatability.add_argument("--session-id", required=True)
        repeatability.add_argument("--repeat-set-id", required=True)
        repeatability.add_argument(
            "--member", action="append", type=_repeatability_member, required=True
        )
        repeatability.add_argument("--scenario", required=True)
        repeatability.add_argument("--ess-artifact-root", required=True)
        repeatability.add_argument("--condition-plan")
    for command_name in ("baseline-difference-compute", "baseline-difference-validate"):
        comparison = commands.add_parser(command_name)
        _add_bundle_arguments(comparison)
        comparison.add_argument("--synthetic-root", required=True)
        comparison.add_argument("--session-id", required=True)
        comparison.add_argument("--comparison-id", required=True)
        comparison.add_argument("--scenario", required=True)
        comparison.add_argument("--condition-plan", required=True)
        comparison.add_argument("--ess-artifact-root", required=True)
        comparison.add_argument("--baseline-repeat-set-id", required=True)
        comparison.add_argument(
            "--baseline-member", action="append", type=_repeatability_member, required=True
        )
        comparison.add_argument("--candidate-repeat-set-id", required=True)
        comparison.add_argument(
            "--candidate-member", action="append", type=_repeatability_member, required=True
        )
    return parser


def _manifest_for_config(root: Path, relative: str) -> dict[str, object]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("device manifest must be a JSON object")
    return value


def _all_blocked_states(manifest: dict[str, object], overrides: list[str]) -> dict[str, NodeState]:
    modules = {node_id: "BLK" for node_id in manifest_nodes(manifest)}
    for override in overrides:
        try:
            node_id, module_id = override.split("=", 1)
        except ValueError as exc:
            raise ValueError(f"node state must be NODE=MODULE: {override}") from exc
        if node_id not in modules:
            raise ValueError(f"unknown node in --node-state: {node_id}")
        modules[node_id] = module_id
    return {
        node_id: NodeState(
            node_id=node_id,
            state_id=f"synthetic_{module_id}",
            module_id=module_id,
            state_type="synthetic_discrete_module",
            discrete_label=module_id,
            continuous_value=None,
            unit=None,
            loading_direction=LoadingDirection.NOT_APPLICABLE,
            proxy_state=False,
            provenance="CLI synthetic interface fixture",
            notes="NOT_EXPERIMENTAL_RESULT",
        )
        for node_id, module_id in modules.items()
    }


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.command == "research-analyze":
        published = run_research_analysis(
            args.analysis_dir,
            args.output_dir,
            seed=args.random_seed,
        )
        print(
            f"PASS synthetic provisional research analysis: output_path={published.output_path} "
            f"analysis_id={published.summary['analysis_id']} "
            f"fold_count={published.receipt['fold_count']} hardware_io_performed=false "
            "experimental_result=false"
        )
        return
    if args.command == "research-report-export":
        published_report = export_research_report(
            args.research_output_dir,
            args.output_dir,
        )
        print(
            "PASS synthetic provisional research report: "
            f"output_path={published_report.output_path} "
            "figures=4 formats=png,svg hardware_io_performed=false "
            "experimental_result=false"
        )
        return
    if args.command.startswith("synthetic-protocol-execution-"):
        project_root = Path(args.project_root).resolve()
        execution_bundle = _load_bundle(args)
        spec_path = Path(args.plan_spec)
        if not spec_path.is_absolute():
            spec_path = project_root / spec_path
        execution_spec = load_development_protocol_plan_spec(
            spec_path,
            project_root=project_root,
            bundle=execution_bundle,
        )
        scenario_path = Path(args.scenario)
        if not scenario_path.is_absolute():
            scenario_path = project_root / scenario_path
        execution_scenario = load_conditioned_virtual_capture_scenario(
            scenario_path, project_root=project_root
        )
        execution_store = DevelopmentSyntheticProtocolExecutionStore(
            args.development_execution_root
        )
        execution_session_store = _synthetic_store(args.synthetic_root)
        execution_plan_store = DevelopmentProtocolPlanStore(args.development_plan_root)
        common = {
            "store": execution_store,
            "session_store": execution_session_store,
            "plan_store": execution_plan_store,
            "bundle": execution_bundle,
            "spec": execution_spec,
            "plan_id": args.plan_id,
            "execution_id": args.execution_id,
            "scenario": execution_scenario,
            "ess_artifact_root": args.ess_artifact_root,
        }
        suffix = args.command.removeprefix("synthetic-protocol-execution-")
        if suffix == "init":
            execution_status = initialize_synthetic_protocol_execution(**common, now=_now)
        elif suffix == "status":
            execution_status = read_synthetic_protocol_execution_status(**common)
        elif suffix == "validate":
            execution_status = validate_synthetic_protocol_execution(**common)
        else:
            execution_token = SyntheticProtocolExecutionConcurrencyToken(
                execution_id=args.execution_id,
                event_sequence=args.expected_event_sequence,
                head_event_sha256=args.expected_head_sha256,
                current_work_order_sha256=args.expected_work_order_sha256,
                cursor=args.expected_cursor,
                recovery_run_id=args.expected_recovery_run_id,
            )
            if suffix == "execute-next":
                execution_status = execute_next_synthetic_protocol_work_order(
                    **common,
                    concurrency_token=execution_token,
                    actor_id=args.actor_id,
                    now=_now,
                )
            elif suffix == "recover-current":
                execution_status = recover_current_synthetic_protocol_work_order(
                    **common,
                    concurrency_token=execution_token,
                    actor_id=args.actor_id,
                    now=_now,
                )
            else:
                execution_command = SyntheticProtocolExecutionControl(
                    action=suffix,
                    actor_id=args.actor_id,
                    expected_event_sequence=args.expected_event_sequence,
                    expected_head_sha256=args.expected_head_sha256,
                    expected_current_work_order_sha256=args.expected_work_order_sha256,
                    expected_cursor=args.expected_cursor,
                    reason_code=(args.reason_code if suffix == "abort" else None),
                )
                execution_status = apply_synthetic_protocol_execution_control(
                    **common,
                    command=execution_command,
                    concurrency_token=execution_token,
                    now=_now,
                )
        execution_output_token = execution_status.concurrency_token
        current = execution_status.current_work_order
        print(
            "PASS development synthetic protocol execution: "
            f"execution_id={execution_status.execution_id} "
            f"state={execution_status.execution_state} cursor={execution_status.cursor} "
            f"total_work_order_count={execution_status.total_work_order_count} "
            f"event_sequence={execution_output_token.event_sequence} "
            f"head_event_sha256={execution_output_token.head_event_sha256} "
            f"current_work_order_sha256={execution_output_token.current_work_order_sha256} "
            f"current_ordinal={current.global_planned_ordinal if current else 'none'} "
            f"recovery_kind={execution_status.recovery_kind or 'none'}"
        )
        print("data_origin=synthetic")
        print("development_synthetic_run=true")
        print("physical_operator_confirmation_performed=false")
        print("formal_protocol_execution_performed=false")
        print("measurement_performed=false")
        print("hardware_io_performed=false")
        print("playback_performed=false")
        print("recording_performed=false")
        print("formal_eligible=false")
        print("experimental_result=false")
        print(f"safety_marker={execution_status.safety_marker}")
        return
    if args.command in {
        "protocol-rehearsal-init",
        "protocol-rehearsal-status",
        "protocol-rehearsal-step",
        "protocol-rehearsal-validate",
    }:
        project_root = Path(args.project_root).resolve()
        rehearsal_bundle = _load_bundle(args)
        rehearsal_spec_path = Path(args.plan_spec)
        if not rehearsal_spec_path.is_absolute():
            rehearsal_spec_path = project_root / rehearsal_spec_path
        rehearsal_spec = load_development_protocol_plan_spec(
            rehearsal_spec_path,
            project_root=project_root,
            bundle=rehearsal_bundle,
        )
        rehearsal_store = DevelopmentProtocolRehearsalStore(args.development_rehearsal_root)
        rehearsal_plan_store = DevelopmentProtocolPlanStore(args.development_plan_root)
        common = {
            "store": rehearsal_store,
            "plan_store": rehearsal_plan_store,
            "bundle": rehearsal_bundle,
            "spec": rehearsal_spec,
            "plan_id": args.plan_id,
            "rehearsal_id": args.rehearsal_id,
        }
        if args.command == "protocol-rehearsal-init":
            rehearsal_status = initialize_protocol_rehearsal(**common, now=_now)
            label = "PASS development protocol rehearsal initialization"
        elif args.command == "protocol-rehearsal-status":
            rehearsal_status = read_protocol_rehearsal_status(**common)
            label = "PASS development protocol rehearsal status"
        elif args.command == "protocol-rehearsal-validate":
            rehearsal_status = validate_protocol_rehearsal(**common)
            label = "PASS development protocol rehearsal validation"
        else:
            command = ProtocolRehearsalTransitionCommand.model_validate(
                {
                    "action": args.action,
                    "rehearsal_actor_id": args.actor_id,
                    "expected_event_sequence": args.expected_event_sequence,
                    "expected_head_sha256": args.expected_head_sha256,
                    "expected_current_work_order_sha256": (args.expected_work_order_sha256),
                    "reason_code": args.reason_code,
                    "detail": args.detail,
                }
            )
            rehearsal_token = ProtocolRehearsalConcurrencyToken(
                rehearsal_id=args.rehearsal_id,
                event_sequence=args.expected_event_sequence,
                head_event_sha256=args.expected_head_sha256,
                current_work_order_sha256=args.expected_work_order_sha256,
            )
            rehearsal_status = apply_protocol_rehearsal_transition(
                **common, command=command, token=rehearsal_token, now=_now
            )
            label = "PASS development protocol rehearsal transition"
        rehearsal_output_token = rehearsal_status.concurrency_token
        print(
            f"{label}: rehearsal_id={rehearsal_status.rehearsal_id} "
            f"state={rehearsal_status.rehearsal_state} "
            f"phase={rehearsal_status.current_work_order_phase} "
            f"cursor={rehearsal_status.cursor} "
            f"total_work_order_count={rehearsal_status.total_work_order_count} "
            f"event_sequence={rehearsal_output_token.event_sequence} "
            f"head_event_sha256={rehearsal_output_token.head_event_sha256} "
            f"current_work_order_sha256={rehearsal_output_token.current_work_order_sha256}"
        )
        print("development_rehearsal=true")
        print(
            "requirements_presented_for_rehearsal="
            f"{str(rehearsal_status.requirements_presented_for_rehearsal).lower()}"
        )
        print("physical_operator_confirmation_performed=false")
        print("operator_confirmation_status=pending")
        print("protocol_execution_performed=false")
        print("measurement_performed=false")
        print("hardware_io_performed=false")
        print("hardware_ready=false")
        print("formal_eligible=false")
        print("experimental_result=false")
        print(f"safety_marker={rehearsal_status.safety_marker}")
        return
    if args.command in {"protocol-plan-compile", "protocol-plan-validate"}:
        project_root = Path(args.project_root).resolve()
        plan_bundle = _load_bundle(args)
        spec_path = Path(args.plan_spec)
        if not spec_path.is_absolute():
            spec_path = project_root / spec_path
        plan_spec = load_development_protocol_plan_spec(
            spec_path,
            project_root=project_root,
            bundle=plan_bundle,
        )
        plan_store = DevelopmentProtocolPlanStore(args.development_plan_root)
        arguments = {
            "store": plan_store,
            "bundle": plan_bundle,
            "spec": plan_spec,
            "plan_id": args.plan_id,
        }
        if args.command == "protocol-plan-compile":
            protocol_plan = publish_development_protocol_plan(**arguments, now=_now)
            label = "PASS development protocol plan compile"
        else:
            protocol_plan = validate_development_protocol_plan(**arguments)
            label = "PASS development protocol plan validation"
        plan_receipt = protocol_plan.receipt
        print(
            f"{label}: plan_path={protocol_plan.plan_path} plan_id={plan_receipt.plan_id} "
            f"experiment_stage={plan_receipt.experiment_stage} "
            f"condition_count={plan_receipt.condition_count} "
            f"planned_measurement_count={plan_receipt.planned_measurement_count} "
            f"session_count={plan_receipt.session_count} "
            f"reassemblies_per_session={plan_receipt.reassemblies_per_session} "
            "continuous_repeats_per_condition="
            f"{plan_receipt.continuous_repeats_per_condition} "
            f"randomization_algorithm={plan_receipt.randomization_algorithm_id}:"
            f"{plan_receipt.randomization_algorithm_version} "
            f"plan_sha256={protocol_plan.plan_sha256} "
            f"receipt_sha256={protocol_plan.receipt_sha256}"
        )
        print("protocol_execution_performed=false")
        print("hardware_io_performed=false")
        print("formal_eligible=false")
        print("experimental_result=false")
        print(f"safety_marker={plan_receipt.safety_marker}")
        print("DEVELOPMENT_PLAN_ONLY")
        print("PROTOCOL_NOT_EXECUTED")
        print("OPERATOR_CONFIRMATION_PENDING")
        print("NO_HARDWARE_AUDIO_IO_PERFORMED")
        print("NOT_AN_EXPERIMENTAL_RESULT")
        return
    if args.command == "audio-list":
        snapshot = collect_inventory(_audio_backend(), now=_now())
        print("DEVICE_NAME_ENCODING=JSON_ASCII_ESCAPED")
        for host_api in snapshot.host_apis:
            print(
                f"HOST_API {host_api.host_api_index}: "
                f"{json.dumps(host_api.name, ensure_ascii=True)} "
                f"({host_api.device_count} devices)"
            )
        for device in snapshot.devices:
            print(
                f"DEVICE {device.snapshot_device_index}: "
                f"{json.dumps(device.name, ensure_ascii=True)} "
                f"[host_api={device.host_api_index}, input={device.max_input_channels}, "
                f"output={device.max_output_channels}]"
            )
        _audio_safety_marker()
        return
    if args.command == "audio-inventory":
        snapshot = collect_inventory(_audio_backend(), now=_now())
        digest = persist_audio_artifact(args.output, args.sidecar, snapshot)
        print(f"PASS audio inventory: {digest}")
        _audio_safety_marker()
        return
    if args.command == "audio-preflight":
        snapshot, inventory_digest = load_audio_artifact(
            args.inventory, args.inventory_sidecar, AudioInventorySnapshot
        )
        hardware_bytes = Path(args.hardware_setup).read_bytes()
        try:
            hardware = HardwareSetupRecord.model_validate_json(hardware_bytes)
        except ValidationError as exc:
            raise ValueError(f"invalid hardware setup: {exc}") from exc
        hardware_digest = hashlib.sha256(hardware_bytes).hexdigest()
        report = build_preflight_report(
            snapshot,
            hardware,
            inventory_reference=args.inventory_reference,
            inventory_sha256=inventory_digest,
            hardware_setup_reference=args.hardware_setup_reference,
            hardware_setup_sha256=hardware_digest,
            now=_now(),
        )
        atomic_write_bytes(
            args.output,
            (
                json.dumps(
                    report.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8"),
        )
        print(f"PASS audio preflight: {args.output}")
        _audio_safety_marker()
        return
    if args.command == "audio-validate":
        snapshot, digest = load_audio_artifact(
            args.inventory, args.inventory_sidecar, AudioInventorySnapshot
        )
        del snapshot
        report = AudioPreflightReport.model_validate_json(Path(args.preflight).read_bytes())
        if report.inventory_sha256 != digest:
            raise ValueError("preflight inventory SHA256 does not match inventory")
        print(f"PASS audio artifacts: {digest}")
        _audio_safety_marker()
        return
    if args.command == "audio-contextual-preflight":
        snapshot, inventory_digest = load_audio_artifact(
            args.inventory, args.inventory_sidecar, AudioInventorySnapshot
        )
        context, context_digest = load_audio_artifact(
            args.context, args.context_sidecar, AudioInventoryCaptureContext
        )
        hardware_bytes = Path(args.hardware_setup).read_bytes()
        hardware = HardwareSetupRecord.model_validate_json(hardware_bytes)
        contextual_report = build_contextual_preflight_report(
            snapshot,
            hardware,
            context,
            inventory_reference=args.inventory_reference,
            inventory_sha256=inventory_digest,
            capture_context_reference=args.context_reference,
            capture_context_sha256=context_digest,
            hardware_setup_reference=args.hardware_setup_reference,
            hardware_setup_sha256=hashlib.sha256(hardware_bytes).hexdigest(),
            now=_now(),
        )
        digest = persist_audio_artifact(args.output, args.output_sidecar, contextual_report)
        print(f"PASS contextual audio preflight: {digest}")
        _audio_safety_marker()
        return
    if args.command == "audio-inventory-summary":
        snapshot, inventory_digest = load_audio_artifact(
            args.inventory, args.inventory_sidecar, AudioInventorySnapshot
        )
        context, context_digest = load_audio_artifact(
            args.context, args.context_sidecar, AudioInventoryCaptureContext
        )
        rendered = render_inventory_summary(
            snapshot,
            inventory_reference=args.inventory_reference,
            inventory_sha256=inventory_digest,
            context=context,
            context_reference=args.context_reference,
            context_sha256=context_digest,
        )
        digest = persist_bytes_with_sidecar(args.output, args.output_sidecar, rendered)
        print(f"PASS audio inventory summary: {digest}")
        _audio_safety_marker()
        return
    if args.command == "audio-context-validate":
        project_root = Path(args.project_root).resolve()
        hardware_path = Path(args.hardware_setup)
        if not hardware_path.is_absolute():
            hardware_path = project_root / hardware_path
        context_receipt = validate_audio_context_bundle(
            inventory_path=args.inventory,
            inventory_sidecar_path=args.inventory_sidecar,
            context_path=args.context,
            context_sidecar_path=args.context_sidecar,
            summary_path=args.summary,
            summary_sidecar_path=args.summary_sidecar,
            contextual_preflight_path=args.contextual_preflight,
            contextual_preflight_sidecar_path=args.contextual_preflight_sidecar,
            hardware_setup_path=hardware_path,
            inventory_reference=args.inventory_reference,
            context_reference=args.context_reference,
            hardware_setup_reference=args.hardware_setup_reference,
        )
        print(f"PASS audio context artifacts: summary={context_receipt.summary_sha256}")
        _audio_safety_marker()
        return
    if args.command in {"ess-generate-offline", "ess-validate-offline"}:
        project_root = Path(args.project_root).resolve()
        loaded = load_config(
            "audio",
            project_root / args.audio_config,
            project_root=project_root,
        )
        if args.command == "ess-generate-offline":
            ess_receipt = publish_offline_ess_artifact(
                args.development_root, args.artifact_id, loaded
            )
            print(
                "PASS offline ESS: "
                f"artifact_id={ess_receipt.artifact_id} wav_sha256={ess_receipt.wav_sha256} "
                f"metadata_sha256={ess_receipt.metadata_sha256} "
                f"raw_float32_sha256={ess_receipt.raw_float32_sha256}"
            )
        else:
            ess_receipt = validate_offline_ess_artifact(args.artifact_root, loaded)
            print(
                "PASS offline ESS validation: "
                f"artifact_id={ess_receipt.artifact_id} wav_sha256={ess_receipt.wav_sha256} "
                f"metadata_sha256={ess_receipt.metadata_sha256}"
            )
        print(SAFETY_MARKER)
        return
    if args.command in {"simulate-conditioned-capture", "validate-conditioned-capture"}:
        project_root = Path(args.project_root).resolve()
        loaded_bundle = _load_bundle(args)
        loaded_scenario = _loaded_capture_scenario(args, project_root)
        if not isinstance(loaded_scenario, LoadedConditionedVirtualCaptureScenario):
            raise ValueError("conditioned capture requires a conditioned scenario")
        capture_store = _synthetic_store(args.synthetic_root)
        if args.command == "simulate-conditioned-capture":
            plan_path = Path(args.condition_plan)
            if not plan_path.is_absolute():
                plan_path = project_root / plan_path
            loaded_plan = load_development_condition_plan(
                plan_path, project_root=project_root, bundle=loaded_bundle
            )
            conditioned_capture_result = publish_conditioned_virtual_capture(
                store=capture_store,
                bundle=loaded_bundle,
                scenario=loaded_scenario,
                condition_plan=loaded_plan,
                condition_id=args.condition_id,
                ess_artifact_root=args.ess_artifact_root,
                session_id=args.session_id,
                reassembly_id=args.reassembly_id,
                run_id=args.run_id,
                measurement_order=args.measurement_order,
                now=_now,
            )
            label = "PASS conditioned synthetic capture"
        else:
            conditioned_capture_result = validate_conditioned_virtual_capture(
                store=capture_store,
                bundle=loaded_bundle,
                scenario=loaded_scenario,
                ess_artifact_root=args.ess_artifact_root,
                session_id=args.session_id,
                run_id=args.run_id,
            )
            label = "PASS conditioned synthetic capture validation"
        conditioned_receipt = conditioned_capture_result.receipt
        print(
            f"{label}: capture_id={conditioned_receipt.capture_id} "
            f"run_id={conditioned_receipt.run_id} "
            f"condition_id={conditioned_receipt.condition_id} "
            f"condition_role={conditioned_receipt.condition_role} "
            f"reassembly_id={conditioned_receipt.reassembly_id} "
            f"receipt_sha256={conditioned_capture_result.receipt_sha256}"
        )
        print("SYNTHETIC_ONLY")
        print("PROTOCOL_CONDITION_BINDING_ONLY")
        print("NO_HARDWARE_AUDIO_IO_PERFORMED")
        print("NOT_AN_EXPERIMENTAL_RESULT")
        return
    if args.command in {"simulate-duplex-capture", "validate-simulated-capture"}:
        project_root = Path(args.project_root).resolve()
        loaded_bundle = _load_bundle(args)
        loaded_scenario = _loaded_capture_scenario(args, project_root)
        if not isinstance(loaded_scenario, LoadedVirtualCaptureScenario):
            raise ValueError("legacy capture command requires a legacy virtual scenario")
        capture_store = _synthetic_store(args.synthetic_root)
        if args.command == "simulate-duplex-capture":
            capture = publish_virtual_capture(
                store=capture_store,
                bundle=loaded_bundle,
                scenario=loaded_scenario,
                ess_artifact_root=args.ess_artifact_root,
                session_id=args.session_id,
                reassembly_id=args.reassembly_id,
                run_id=args.run_id,
                measurement_order=args.measurement_order,
                now=_now,
            )
            label = "PASS simulated duplex capture"
        else:
            capture = validate_virtual_capture(
                store=capture_store,
                bundle=loaded_bundle,
                scenario=loaded_scenario,
                ess_artifact_root=args.ess_artifact_root,
                session_id=args.session_id,
                run_id=args.run_id,
            )
            label = "PASS simulated capture validation"
        receipt = capture.receipt
        print(
            f"{label}: capture_id={receipt.capture_id} run_id={receipt.run_id} "
            f"sample_count={receipt.capture_sample_count} "
            f"block_count={receipt.actual_block_count} "
            f"output_wav_sha256={receipt.output_wav_sha256} "
            f"simulated_input_wav_sha256={receipt.input_wav_sha256} "
            f"receipt_sha256={capture.receipt_sha256} "
            f"final_state={receipt.final_state}"
        )
        print("SYNTHETIC_ONLY")
        print("NO_HARDWARE_AUDIO_IO_PERFORMED")
        print("NOT_AN_EXPERIMENTAL_RESULT")
        return
    if args.command in {"process-simulated-capture", "validate-simulated-processing"}:
        project_root = Path(args.project_root).resolve()
        loaded_bundle = _load_bundle(args)
        loaded_scenario = _loaded_capture_scenario(args, project_root)
        processing_store = _synthetic_store(args.synthetic_root)
        arguments = {
            "store": processing_store,
            "bundle": loaded_bundle,
            "scenario": loaded_scenario,
            "ess_artifact_root": args.ess_artifact_root,
            "session_id": args.session_id,
            "source_run_id": args.source_run_id,
            "processing_id": args.processing_id,
        }
        if args.command == "process-simulated-capture":
            processed = publish_ess_processing(**arguments, now=_now)
            label = "PASS simulated offline processing"
        else:
            processed = validate_ess_processing(**arguments)
            label = "PASS simulated processing validation"
        processing_receipt = processed.receipt
        print(
            f"{label}: processing_id={processing_receipt.processing_id} "
            f"source_run_id={processing_receipt.source_run_id} "
            f"latency_samples={processing_receipt.estimated_latency_samples} "
            f"correlation={processing_receipt.matched_correlation_signed} "
            f"ir_peak_index={processing_receipt.ir_dominant_peak_index} "
            f"ir_peak_value={processing_receipt.ir_dominant_peak_value} "
            f"arrays_sha256={processed.arrays_sha256} "
            f"receipt_sha256={processed.receipt_sha256} "
            f"sample_rate_hz={processing_receipt.sample_rate_hz} "
            f"fft_length={processing_receipt.transfer_fft_length} "
            f"frequency_bin_count={processing_receipt.frequency_bin_count}"
        )
        print("SYNTHETIC_ONLY")
        print("OFFLINE_PROCESSING_ONLY")
        print("NO_HARDWARE_AUDIO_IO_PERFORMED")
        print("NOT_AN_EXPERIMENTAL_RESULT")
        return
    if args.command in {"qc-compute", "qc-validate"}:
        project_root = Path(args.project_root).resolve()
        loaded_bundle = _load_bundle(args)
        loaded_scenario = _loaded_capture_scenario(args, project_root)
        arguments = {
            "store": _synthetic_store(args.synthetic_root),
            "bundle": loaded_bundle,
            "scenario": loaded_scenario,
            "ess_artifact_root": args.ess_artifact_root,
            "session_id": args.session_id,
            "source_run_id": args.source_run_id,
            "processing_id": args.processing_id,
            "qc_id": args.qc_id,
        }
        if args.command == "qc-compute":
            qc = publish_provisional_qc(**arguments, now=_now)
            label = "PASS provisional offline QC"
        else:
            qc = validate_provisional_qc(**arguments)
            label = "PASS provisional QC validation"
        metrics = qc.metrics
        qc_receipt = qc.receipt
        print(
            f"{label}: qc_id={qc_receipt.qc_id} processing_id={qc_receipt.processing_id} "
            f"source_run_id={qc_receipt.source_run_id} "
            f"qc_path={qc.qc_path} "
            f"latency_samples={metrics.estimated_latency_samples} "
            f"correlation={metrics.matched_correlation_signed} "
            f"input_snr_proxy_db={metrics.input_pre_silence_snr_proxy_db} "
            f"input_snr_proxy_status={metrics.input_pre_silence_snr_proxy_status} "
            f"ir_peak_ratio={metrics.ir_peak_to_second_peak_ratio} "
            f"spectral_valid_fraction={metrics.spectral_division_valid_fraction_in_band} "
            f"metrics_sha256={qc.metrics_sha256} receipt_sha256={qc.receipt_sha256}"
        )
        print(f"metric_computation_status={qc_receipt.metric_computation_status}")
        print(f"evaluation_status={qc_receipt.evaluation_status}")
        print(f"qc_decision={qc_receipt.decision_status}")
        print("thresholds_applied=false")
        print("formal_eligible=false")
        print("experimental_result=false")
        print(f"safety_marker={qc_receipt.safety_marker}")
        print("SYNTHETIC_ONLY")
        print("PROVISIONAL_METRICS_ONLY")
        print("THRESHOLDS_NOT_APPLIED")
        print("NO_HARDWARE_AUDIO_IO_PERFORMED")
        print("NOT_AN_EXPERIMENTAL_RESULT")
        return
    if args.command in {"repeatability-compute", "repeatability-validate"}:
        project_root = Path(args.project_root).resolve()
        loaded_bundle = _load_bundle(args)
        loaded_scenario = _loaded_capture_scenario(args, project_root)
        arguments = {
            "store": _synthetic_store(args.synthetic_root),
            "bundle": loaded_bundle,
            "scenario": loaded_scenario,
            "ess_artifact_root": args.ess_artifact_root,
            "session_id": args.session_id,
            "repeat_set_id": args.repeat_set_id,
            "members": args.member,
        }
        if args.command == "repeatability-compute":
            repeatability = publish_provisional_repeatability(**arguments, now=_now)
            label = "PASS provisional repeatability"
        else:
            repeatability = validate_provisional_repeatability(**arguments)
            label = "PASS provisional repeatability validation"
        repeat_metrics = repeatability.metrics
        repeat_receipt = repeatability.receipt
        print(
            f"{label}: repeat_set_id={repeat_receipt.repeat_set_id} "
            f"reassembly_id={repeat_receipt.reassembly_id} "
            f"member_count={repeat_metrics.member_count} "
            f"pair_count={repeat_metrics.pair_count} "
            f"measurement_order={repeat_metrics.measurement_order_min}:"
            f"{repeat_metrics.measurement_order_max} "
            f"latency_span_samples={repeat_metrics.latency_span_samples} "
            f"ir_correlation_min={repeat_metrics.ir_correlation_min} "
            f"ir_correlation_mean={repeat_metrics.ir_correlation_mean} "
            f"complex_transfer_relative_l2_mean="
            f"{repeat_metrics.complex_transfer_relative_l2_mean} "
            f"complex_transfer_relative_l2_max="
            f"{repeat_metrics.complex_transfer_relative_l2_max} "
            f"magnitude_rmse_db_mean={repeat_metrics.magnitude_rmse_db_mean} "
            f"magnitude_rmse_db_max={repeat_metrics.magnitude_rmse_db_max} "
            f"phase_rms_defined_count={repeat_metrics.phase_rms_rad_defined_count} "
            f"phase_rms_mean={repeat_metrics.phase_rms_rad_mean} "
            f"phase_rms_max={repeat_metrics.phase_rms_rad_max} "
            f"metrics_sha256={repeatability.metrics_sha256} "
            f"receipt_sha256={repeatability.receipt_sha256}"
        )
        print(f"evaluation_status={repeat_receipt.evaluation_status}")
        print(f"decision_status={repeat_receipt.decision_status}")
        print(f"repeatability_decision={repeat_receipt.repeatability_decision}")
        print(f"baseline_assigned={str(repeat_receipt.baseline_assigned).lower()}")
        print(f"baseline_role={repeat_receipt.baseline_role}")
        print(f"baseline_selection_status={repeat_receipt.baseline_selection_status}")
        print(
            "baseline_difference_computed="
            f"{str(repeat_receipt.baseline_difference_computed).lower()}"
        )
        print(f"drift_evaluated={str(repeat_receipt.drift_evaluated).lower()}")
        print(f"drift_decision={repeat_receipt.drift_decision}")
        print(f"thresholds_applied={str(repeat_receipt.thresholds_applied).lower()}")
        print(f"repeatability_threshold={json.dumps(repeat_receipt.repeatability_threshold)}")
        print(f"threshold_source={json.dumps(repeat_receipt.threshold_source)}")
        print(f"safety_marker={repeat_receipt.safety_marker}")
        print("SYNTHETIC_ONLY")
        print("PROVISIONAL_REPEATABILITY_METRICS_ONLY")
        print("REPEATABILITY_NOT_EVALUATED")
        print("THRESHOLDS_NOT_APPLIED")
        print("BASELINE_NOT_ASSIGNED")
        print("BASELINE_SELECTION_DEFERRED_UNTIL_PROTOCOL_BINDING")
        print("NO_BASELINE_DIFFERENCE_COMPUTED")
        print("DRIFT_NOT_EVALUATED")
        print("NO_HARDWARE_AUDIO_IO_PERFORMED")
        print("NOT_AN_EXPERIMENTAL_RESULT")
        return
    if args.command in {"baseline-difference-compute", "baseline-difference-validate"}:
        project_root = Path(args.project_root).resolve()
        loaded_bundle = _load_bundle(args)
        loaded_scenario = _loaded_capture_scenario(args, project_root)
        if not isinstance(loaded_scenario, LoadedConditionedVirtualCaptureScenario):
            raise ValueError("baseline difference requires a conditioned scenario")
        plan_path = Path(args.condition_plan)
        if not plan_path.is_absolute():
            plan_path = project_root / plan_path
        loaded_plan = load_development_condition_plan(
            plan_path, project_root=project_root, bundle=loaded_bundle
        )
        arguments = {
            "store": _synthetic_store(args.synthetic_root),
            "bundle": loaded_bundle,
            "scenario": loaded_scenario,
            "condition_plan": loaded_plan,
            "ess_artifact_root": args.ess_artifact_root,
            "session_id": args.session_id,
            "comparison_id": args.comparison_id,
            "source_a": RepeatabilitySourceIdentity(
                repeat_set_id=args.baseline_repeat_set_id,
                members=args.baseline_member,
            ),
            "source_b": RepeatabilitySourceIdentity(
                repeat_set_id=args.candidate_repeat_set_id,
                members=args.candidate_member,
            ),
        }
        if args.command == "baseline-difference-compute":
            comparison = publish_provisional_baseline_difference(**arguments, now=_now)
            label = "PASS provisional baseline difference"
        else:
            comparison = validate_provisional_baseline_difference(**arguments)
            label = "PASS provisional baseline difference validation"
        comparison_receipt = comparison.receipt
        print(
            f"{label}: comparison_path={comparison.comparison_path} "
            f"arrays_sha256={comparison.arrays_sha256} "
            f"metrics_sha256={comparison.metrics_sha256} "
            f"receipt_sha256={comparison.receipt_sha256} "
            f"baseline_condition_id={comparison_receipt.baseline_source.condition_id} "
            f"candidate_condition_id={comparison_receipt.candidate_source.condition_id} "
            f"baseline_reassembly_id={comparison_receipt.baseline_source.reassembly_id} "
            f"candidate_reassembly_id={comparison_receipt.candidate_source.reassembly_id} "
            f"baseline_member_count={len(comparison_receipt.baseline_source.members)} "
            f"candidate_member_count={len(comparison_receipt.candidate_source.members)} "
            f"analysis_bin_count={comparison_receipt.analysis_band_bin_count} "
            f"raw_valid_bin_count={comparison_receipt.ratio_valid_bin_count['raw']} "
            f"aligned_valid_bin_count={comparison_receipt.ratio_valid_bin_count['aligned']}"
        )
        print(f"baseline_selection_status={comparison_receipt.baseline_selection_status}")
        print(
            "baseline_difference_computed="
            f"{str(comparison_receipt.baseline_difference_computed).lower()}"
        )
        print(f"decision_status={comparison_receipt.decision_status}")
        print(f"thresholds_applied={str(comparison_receipt.thresholds_applied).lower()}")
        print(f"hardware_io_performed={str(comparison_receipt.hardware_io_performed).lower()}")
        print(f"formal_eligible={str(comparison_receipt.formal_eligible).lower()}")
        print(f"experimental_result={str(comparison_receipt.experimental_result).lower()}")
        print(f"safety_marker={comparison_receipt.safety_marker}")
        print("SYNTHETIC_ONLY")
        print("PROVISIONAL_BASELINE_DIFFERENCE_METRICS_ONLY")
        print("PROTOCOL_CONDITION_BINDING_ONLY")
        print("BASELINE_SELECTED_FROM_VERIFIED_ALL_BLK_CONDITION")
        print("DECISION_NOT_EVALUATED")
        print("THRESHOLDS_NOT_APPLIED")
        print("NO_HARDWARE_AUDIO_IO_PERFORMED")
        print("NOT_AN_EXPERIMENTAL_RESULT")
        return
    if args.command in {"analysis-matrix-compute", "analysis-matrix-validate"}:
        project_root = Path(args.project_root).resolve()
        matrix_spec_path = Path(args.development_analysis_spec)
        if not matrix_spec_path.is_absolute():
            matrix_spec_path = project_root / matrix_spec_path
        matrix_spec = load_development_analysis_matrix_spec(
            matrix_spec_path, project_root=project_root
        )
        sources = _analysis_sources(args)
        matrix_store = SyntheticMeasurementMatrixStore(Path(args.analysis_root).resolve())
        arguments = {
            "store": matrix_store,
            "sources": sources,
            "analysis_spec": matrix_spec,
            "analysis_id": args.analysis_id,
        }
        if args.command == "analysis-matrix-compute":
            published_matrix = compute_synthetic_measurement_matrix(**arguments)
            label = "PASS synthetic analysis matrix"
        else:
            published_matrix = validate_synthetic_measurement_matrix(**arguments)
            label = "PASS synthetic analysis matrix validation"
        matrix_receipt = published_matrix.receipt
        binding = AnalysisSourceBinding.model_validate_json(
            (Path(published_matrix.analysis_path) / "analysis_source_binding.json").read_bytes()
        )
        print(
            f"{label}: analysis_path={published_matrix.analysis_path} "
            f"analysis_id={published_matrix.analysis_id} "
            f"source_execution_ids={','.join(item.execution_id for item in binding.executions)} "
            "source_execution_completion_sha256="
            f"{','.join(item.execution_completion_sha256 for item in binding.executions)} "
            f"row_count={matrix_receipt.measurement_row_count} "
            f"stage_counts=152,32,32,128 feature_count={matrix_receipt.feature_count} "
            "split_strategies=leave_one_session_out,leave_one_reassembly_out "
            "fold_counts=8,16 "
            f"source_binding_sha256={matrix_receipt.analysis_source_binding_sha256} "
            f"row_index_sha256={matrix_receipt.measurement_row_index_sha256} "
            f"feature_schema_sha256={matrix_receipt.feature_schema_sha256} "
            f"split_plan_sha256={matrix_receipt.split_plan_sha256} "
            f"matrix_npz_sha256={matrix_receipt.measurement_matrix_npz_sha256} "
            f"metadata_sha256={matrix_receipt.analysis_metadata_sha256} "
            f"record_sha256={matrix_receipt.analysis_record_sha256} "
            f"receipt_sha256={published_matrix.receipt_sha256}"
        )
        print(f"analysis_evidence_time={matrix_receipt.analysis_evidence_time.isoformat()}")
        print(f"analysis_evidence_time_basis={matrix_receipt.analysis_evidence_time_basis}")
        print(f"rows_excluded={matrix_receipt.rows_excluded}")
        print(f"thresholds_applied={str(matrix_receipt.thresholds_applied).lower()}")
        print(f"model_fit_performed={str(matrix_receipt.model_fit_performed).lower()}")
        print(f"classification_performed={str(matrix_receipt.classification_performed).lower()}")
        print(f"hardware_io_performed={str(matrix_receipt.hardware_io_performed).lower()}")
        print(f"formal_eligible={str(matrix_receipt.formal_eligible).lower()}")
        print(f"experimental_result={str(matrix_receipt.experimental_result).lower()}")
        print(f"safety_marker={matrix_receipt.safety_marker}")
        return
    if args.command in {"validate-config", "config-hash"}:
        root = Path(args.project_root).resolve()
        manifest = _manifest_for_config(root, args.manifest)
        loaded = load_config(
            args.kind,
            root / args.path,
            project_root=root,
            manifest=manifest,
        )
        if args.command == "config-hash":
            print(loaded.snapshot.normalized_sha256)
        else:
            print(f"PASS {args.kind}: {loaded.snapshot.normalized_sha256}")
        return
    if args.command == "validate-bundle":
        loaded_bundle = _load_bundle(args)
        print(f"PASS bundle: {loaded_bundle.receipt.bundle_content_sha256}")
        return
    if args.command == "export-schemas":
        if args.check:
            check_schemas(args.output_dir)
            print("PASS schema consistency")
        else:
            paths = export_schemas(args.output_dir)
            print(f"PASS exported {len(paths)} schemas")
        return
    if args.command == "create-synthetic-session":
        loaded_bundle = _load_bundle(args)
        now = _now()
        session = SessionRecord(
            session_id=args.session_id,
            session_schema_version="1.0.0",
            created_at=now,
            data_origin=DataOrigin.SYNTHETIC,
            run_mode=RunMode.DEVELOPMENT,
            operator=None,
            device_manifest_reference="manifest/device_manifest.provisional.json",
            config_bundle_reference="protocol/config_bundle.json",
            reassembly_ids=[args.reassembly_id],
            run_ids=[],
            immutable_status="immutable",
            notes="Synthetic interface-test session; not experimental data.",
        )
        reassembly = ReassemblyRecord(
            reassembly_id=args.reassembly_id,
            session_id=args.session_id,
            sequence_index=0,
            created_at=now,
            assembly_description="Synthetic initial assembly state",
            operator_confirmation=False,
            related_run_ids=[],
        )
        path = _synthetic_store(args.synthetic_root).create_synthetic_session(
            session, [reassembly], loaded_bundle
        )
        print(f"PASS synthetic session: {path}")
        return
    if args.command == "generate-synthetic-run":
        loaded_bundle = _load_bundle(args)
        synthetic_loaded = loaded_bundle.configs["synthetic"]
        protocol_loaded = loaded_bundle.configs["protocol"]
        assert isinstance(synthetic_loaded.model, SyntheticConfig)
        assert isinstance(protocol_loaded.model, ProtocolConfig)
        states = _all_blocked_states(loaded_bundle.manifest, args.node_state)
        artifact_path = f"raw/run_{args.run_id}/synthetic_arrays.npz"
        result = generate_synthetic_arrays(
            loaded_bundle.manifest,
            synthetic_loaded.model,
            states,
            session_index=args.session_index,
            reassembly_index=args.reassembly_index,
            artifact_path=artifact_path,
        )
        validate_npz_metadata(result.npz_bytes, result.metadata)
        now = _now()
        run_record = MeasurementRunRecord(
            run_id=args.run_id,
            session_id=args.session_id,
            reassembly_id=args.reassembly_id,
            protocol_id=protocol_loaded.model.protocol_id,
            measurement_order=args.measurement_order,
            data_origin=DataOrigin.SYNTHETIC,
            run_mode=RunMode.DEVELOPMENT,
            formal_eligible=False,
            node_states=states,
            created_at=now,
            started_at=now,
            completed_at=now,
            config_hashes={
                **loaded_bundle.receipt.normalized_config_hashes,
                "bundle": loaded_bundle.receipt.bundle_content_sha256,
            },
            artifacts=[result.artifact],
            backend=synthetic_loaded.model.generator_version,
            software_version=__version__,
            status="complete",
            failure_reason=None,
            result_marker="NOT_EXPERIMENTAL_RESULT",
            notes="Synthetic interface-test run only; contains no experimental conclusion.",
        )
        path = _synthetic_store(args.synthetic_root).create_synthetic_run(
            run_record,
            {"synthetic_arrays.npz": result.npz_bytes},
            result.metadata,
        )
        print(f"PASS synthetic run: {path}")
        return
    if args.command == "validate-session":
        session_record_loaded = _synthetic_store(args.synthetic_root).validate_session(
            DataOrigin.SYNTHETIC, args.session_id
        )
        print(f"PASS session: {session_record_loaded.session_id}")
        return
    if args.command == "validate-run":
        run_record_loaded = _synthetic_store(args.synthetic_root).validate_run(
            DataOrigin.SYNTHETIC, args.session_id, args.run_id
        )
        print(f"PASS run: {run_record_loaded.run_id}")
        return
    if args.command == "verify-artifact":
        artifact = ArtifactRef.model_validate(read_json_object(args.artifact_ref))
        path = verify_artifact(args.session_root, artifact)
        print(f"PASS artifact: {path}")
        return
    raise AssertionError(f"unhandled command: {args.command}")
