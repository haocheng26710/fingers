"""Top-level DEV-02.01 CLI for configuration, storage and synthetic interface data."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder import __version__
from acoustic_ladder.audio.backend import SoundDeviceInventoryBackend
from acoustic_ladder.audio.inventory import collect_inventory
from acoustic_ladder.audio.models import (
    AudioInventorySnapshot,
    AudioPreflightReport,
    HardwareSetupRecord,
)
from acoustic_ladder.audio.persistence import load_audio_artifact, persist_audio_artifact
from acoustic_ladder.audio.preflight import build_preflight_report
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


def _audio_backend() -> SoundDeviceInventoryBackend:
    return SoundDeviceInventoryBackend()


def _audio_safety_marker() -> None:
    print("NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED")


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
    if args.command == "audio-list":
        snapshot = collect_inventory(_audio_backend(), now=_now())
        for host_api in snapshot.host_apis:
            print(
                f"HOST_API {host_api.host_api_index}: {host_api.name} "
                f"({host_api.device_count} devices)"
            )
        for device in snapshot.devices:
            print(
                f"DEVICE {device.snapshot_device_index}: {device.name} "
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
