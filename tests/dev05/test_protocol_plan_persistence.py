import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

import acoustic_ladder.protocol.planning_persistence as persistence_module
from acoustic_ladder import cli
from acoustic_ladder.config.bundle import canonical_json_bytes, load_bundle
from acoustic_ladder.config.schema import export_schemas
from acoustic_ladder.protocol.planning import load_development_protocol_plan_spec
from acoustic_ladder.protocol.planning_persistence import (
    PROTOCOL_PLAN_FILE_NAMES,
    DevelopmentProtocolPlanStore,
    ProtocolPlanPersistenceError,
    publish_development_protocol_plan,
    validate_development_protocol_plan,
)

PROJECT_ROOT = Path(__file__).parents[2]
FIXED_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _inputs(stage: int = 1):
    names = {
        1: "stage1_single_bridge.yaml",
        2: "stage2_single_node_proxy_states.yaml",
        3: "stage3_two_node_interaction.yaml",
        4: "stage4_four_node_states.yaml",
    }
    bundle = load_bundle(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=PROJECT_ROOT / "config/devices/device_manifest.provisional.sha256",
        audio_path=PROJECT_ROOT / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=PROJECT_ROOT / "config/protocols" / names[stage],
        analysis_path=PROJECT_ROOT / "config/analysis/default.yaml",
        synthetic_path=PROJECT_ROOT / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    spec = load_development_protocol_plan_spec(
        PROJECT_ROOT / f"tests/fixtures/protocol/stage{stage}_protocol_plan.development.yaml",
        project_root=PROJECT_ROOT,
        bundle=bundle,
    )
    return bundle, spec


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _isolated_inputs(root: Path, *, spec_replacements: tuple[tuple[str, str], ...] = ()):
    relatives = (
        "config/devices/device_manifest.provisional.json",
        "config/devices/device_manifest.provisional.sha256",
        "config/protocols/stage1_single_bridge.yaml",
        "config/analysis/default.yaml",
        "config/synthetic/default.yaml",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
    )
    for relative in relatives:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / relative, target)
    spec_path = root / "tests/fixtures/protocol/stage1_protocol_plan.development.yaml"
    spec_text = spec_path.read_text(encoding="utf-8")
    for old, new in spec_replacements:
        spec_text = spec_text.replace(old, new)
    spec_path.write_text(spec_text, encoding="utf-8")
    bundle = load_bundle(
        project_root=root,
        manifest_path=root / "config/devices/device_manifest.provisional.json",
        manifest_sidecar_path=root / "config/devices/device_manifest.provisional.sha256",
        audio_path=root / "tests/fixtures/audio/ess_offline_development.yaml",
        protocol_path=root / "config/protocols/stage1_single_bridge.yaml",
        analysis_path=root / "config/analysis/default.yaml",
        synthetic_path=root / "config/synthetic/default.yaml",
        now=lambda: FIXED_TIME,
    )
    spec = load_development_protocol_plan_spec(
        spec_path,
        project_root=root,
        bundle=bundle,
    )
    return bundle, spec


def test_publish_and_read_only_validate_exact_seven_file_plan(tmp_path: Path) -> None:
    bundle, spec = _inputs()
    development_root = tmp_path / "development-plans"
    store = DevelopmentProtocolPlanStore(development_root)

    published = publish_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-published",
        now=lambda: FIXED_TIME,
    )
    before = {
        path.relative_to(development_root).as_posix(): path.read_bytes()
        for path in development_root.rglob("*")
        if path.is_file()
    }
    validated = validate_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="stage1-published",
    )
    after = {
        path.relative_to(development_root).as_posix(): path.read_bytes()
        for path in development_root.rglob("*")
        if path.is_file()
    }

    assert {path.name for path in published.plan_path.iterdir()} == PROTOCOL_PLAN_FILE_NAMES
    assert validated.receipt == published.receipt
    assert before == after
    assert published.receipt.condition_count == 19
    assert published.receipt.planned_measurement_count == 152
    assert published.receipt.protocol_execution_performed is False
    assert published.receipt.hardware_io_performed is False
    assert published.receipt.formal_eligible is False
    assert published.receipt.experimental_result is False
    assert not list(development_root.rglob("session_*"))
    assert not list(development_root.rglob("run_*"))
    assert not list(development_root.rglob("events"))
    assert not (tmp_path / "real").exists()


def test_validator_rejects_current_manifest_tamper_without_writing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    bundle, spec = _isolated_inputs(project)
    store = DevelopmentProtocolPlanStore(tmp_path / "plans")
    publish_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="manifest-bound",
        now=lambda: FIXED_TIME,
    )
    manifest = project / "config/devices/device_manifest.provisional.json"
    original = manifest.read_bytes()
    manifest.write_bytes(original + b"\n")
    before = _tree_hash(store.root)

    with pytest.raises(ProtocolPlanPersistenceError, match="manifest"):
        validate_development_protocol_plan(
            store=store,
            bundle=bundle,
            spec=spec,
            plan_id="manifest-bound",
        )

    assert _tree_hash(store.root) == before
    manifest.write_bytes(original)
    validate_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="manifest-bound",
    )


def test_compile_and_validate_cli_emit_receipt_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    common = [
        "--project-root",
        str(PROJECT_ROOT),
        "--protocol",
        "config/protocols/stage1_single_bridge.yaml",
        "--audio",
        "tests/fixtures/audio/ess_offline_development.yaml",
        "--plan-spec",
        "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        "--development-plan-root",
        str(tmp_path / "plans"),
        "--plan-id",
        "cli-stage1",
    ]
    cli.main(["protocol-plan-compile", *common])
    compiled = capsys.readouterr().out
    cli.main(["protocol-plan-validate", *common])
    validated = capsys.readouterr().out

    for output in (compiled, validated):
        assert "PASS development protocol plan" in output
        assert "plan_id=cli-stage1" in output
        assert "experiment_stage=1" in output
        assert "condition_count=19" in output
        assert "planned_measurement_count=152" in output
        assert "protocol_execution_performed=false" in output
        assert "hardware_io_performed=false" in output
        assert "formal_eligible=false" in output
        assert "experimental_result=false" in output
        assert "DEVELOPMENT_PLAN_ONLY" in output
        assert "PROTOCOL_NOT_EXECUTED" in output
        assert "OPERATOR_CONFIRMATION_PENDING" in output
        assert "NO_HARDWARE_AUDIO_IO_PERFORMED" in output
        assert "NOT_AN_EXPERIMENTAL_RESULT" in output


def test_active_protocol_plan_models_are_exported(tmp_path: Path) -> None:
    exported = {path.name for path in export_schemas(tmp_path)}

    assert {
        "development_protocol_plan_spec.schema.json",
        "compiled_protocol_plan.schema.json",
        "protocol_plan_receipt.schema.json",
        "protocol_plan_record.schema.json",
    }.issubset(exported)


@pytest.mark.parametrize(
    "filename",
    [
        "compiled_protocol_plan.json",
        "compiled_protocol_plan.sha256",
        "protocol_plan_receipt.json",
        "protocol_plan_receipt.sha256",
        "protocol_plan_metadata.json",
        "protocol_plan_record.json",
        "PROTOCOL_PLAN_COMPLETE",
    ],
)
def test_validator_rejects_byte_tamper_without_writing_and_recovers(
    tmp_path: Path, filename: str
) -> None:
    bundle, spec = _inputs()
    store = DevelopmentProtocolPlanStore(tmp_path / "plans")
    published = publish_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="tamper",
        now=lambda: FIXED_TIME,
    )
    target = published.plan_path / filename
    original = target.read_bytes()
    target.write_bytes(original + b"\r\n")
    before = _tree_hash(store.root)

    with pytest.raises(ProtocolPlanPersistenceError):
        validate_development_protocol_plan(store=store, bundle=bundle, spec=spec, plan_id="tamper")

    assert _tree_hash(store.root) == before
    target.write_bytes(original)
    validate_development_protocol_plan(store=store, bundle=bundle, spec=spec, plan_id="tamper")


def test_validator_rejects_missing_and_extra_files(tmp_path: Path) -> None:
    bundle, spec = _inputs()
    store = DevelopmentProtocolPlanStore(tmp_path / "plans")
    published = publish_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="envelope",
        now=lambda: FIXED_TIME,
    )
    sidecar = published.plan_path / "protocol_plan_receipt.sha256"
    original = sidecar.read_bytes()
    sidecar.unlink()
    with pytest.raises(ProtocolPlanPersistenceError, match="seven-file"):
        validate_development_protocol_plan(
            store=store, bundle=bundle, spec=spec, plan_id="envelope"
        )
    sidecar.write_bytes(original)
    extra = published.plan_path / "unexpected.bin"
    extra.write_bytes(b"unexpected")
    with pytest.raises(ProtocolPlanPersistenceError, match="seven-file"):
        validate_development_protocol_plan(
            store=store, bundle=bundle, spec=spec, plan_id="envelope"
        )


def test_duplicate_and_concurrent_publish_never_overwrite(tmp_path: Path) -> None:
    bundle, spec = _inputs()
    store = DevelopmentProtocolPlanStore(tmp_path / "plans")

    def publish() -> str:
        try:
            result = publish_development_protocol_plan(
                store=store,
                bundle=bundle,
                spec=spec,
                plan_id="concurrent",
                now=lambda: FIXED_TIME,
            )
            return result.plan_sha256
        except ProtocolPlanPersistenceError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: publish(), range(2)))
    assert outcomes.count("rejected") == 1
    assert len([outcome for outcome in outcomes if outcome != "rejected"]) == 1
    target = store.plan_path("concurrent")
    original = {path.name: path.read_bytes() for path in target.iterdir()}
    with pytest.raises(ProtocolPlanPersistenceError):
        publish_development_protocol_plan(
            store=store,
            bundle=bundle,
            spec=spec,
            plan_id="concurrent",
            now=lambda: FIXED_TIME,
        )
    assert {path.name: path.read_bytes() for path in target.iterdir()} == original
    assert not list(target.parent.glob("*.lock"))
    assert not list(target.parent.glob("*.staging-*"))


def test_failed_staging_cleans_only_owned_transients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, spec = _inputs()
    store = DevelopmentProtocolPlanStore(tmp_path / "plans")

    def fail_write(path: str | Path, payload: bytes) -> None:
        raise OSError(f"injected write failure: {path} ({len(payload)} bytes)")

    monkeypatch.setattr(persistence_module, "atomic_write_bytes", fail_write)
    with pytest.raises(ProtocolPlanPersistenceError) as failure:
        publish_development_protocol_plan(
            store=store,
            bundle=bundle,
            spec=spec,
            plan_id="staging-failure",
            now=lambda: FIXED_TIME,
        )
    assert failure.value.published is False
    assert not store.plan_path("staging-failure").exists()
    assert not list((store.root / "plans").glob("*.lock"))
    assert not list((store.root / "plans").glob("*.staging-*"))


@pytest.mark.parametrize("plan_id", ["", ".", "..", "../escape", "a/b", "a\\b", "C:drive"])
def test_unsafe_plan_ids_are_rejected_without_root_creation(tmp_path: Path, plan_id: str) -> None:
    bundle, spec = _inputs()
    root = tmp_path / "must-not-exist"
    with pytest.raises((ProtocolPlanPersistenceError, ValueError)):
        publish_development_protocol_plan(
            store=DevelopmentProtocolPlanStore(root),
            bundle=bundle,
            spec=spec,
            plan_id=plan_id,
            now=lambda: FIXED_TIME,
        )
    assert not root.exists()


def test_measurement_limit_rejects_before_development_root_creation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    bundle, spec = _isolated_inputs(
        project,
        spec_replacements=(("max_planned_measurements: 1000", "max_planned_measurements: 151"),),
    )
    root = tmp_path / "must-not-exist"

    with pytest.raises(ProtocolPlanPersistenceError, match="exceeds"):
        publish_development_protocol_plan(
            store=DevelopmentProtocolPlanStore(root),
            bundle=bundle,
            spec=spec,
            plan_id="over-limit",
            now=lambda: FIXED_TIME,
        )

    assert not root.exists()


@pytest.mark.parametrize(
    "relative",
    [
        "tests/fixtures/protocol/stage1_protocol_plan.development.yaml",
        "config/protocols/stage1_single_bridge.yaml",
        "config/devices/device_manifest.provisional.json",
        "config/devices/device_manifest.provisional.sha256",
    ],
)
def test_validator_rejects_changed_or_missing_sources_and_recovers(
    tmp_path: Path, relative: str
) -> None:
    project = tmp_path / "project"
    bundle, spec = _isolated_inputs(project)
    store = DevelopmentProtocolPlanStore(tmp_path / "plans")
    publish_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="source-bound",
        now=lambda: FIXED_TIME,
    )
    target = project / relative
    original = target.read_bytes()
    target.unlink()
    before = _tree_hash(store.root)

    with pytest.raises(ProtocolPlanPersistenceError):
        validate_development_protocol_plan(
            store=store, bundle=bundle, spec=spec, plan_id="source-bound"
        )

    assert _tree_hash(store.root) == before
    target.write_bytes(original)
    validate_development_protocol_plan(
        store=store, bundle=bundle, spec=spec, plan_id="source-bound"
    )


@pytest.mark.parametrize(
    "forbidden",
    [
        "--condition",
        "--node-state",
        "--measurement-order",
        "--permutation",
        "--real-root",
        "--device-index",
        "--host-api",
        "--channel",
        "--threshold",
        "--decision",
    ],
)
def test_protocol_plan_cli_has_no_forbidden_authority(forbidden: str) -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "protocol-plan-compile",
                "--protocol",
                "protocol.yaml",
                "--plan-spec",
                "plan.yaml",
                "--development-plan-root",
                "plans",
                "--plan-id",
                "plan",
                forbidden,
                "forbidden",
            ]
        )


@pytest.mark.parametrize(
    "attack",
    [
        "missing_node_state",
        "condition_identity",
        "selected_node",
        "measurement_order",
        "measurement_count",
        "random_seed",
        "randomization_algorithm",
        "receipt_state",
        "metadata_state",
        "record_state",
    ],
)
def test_validator_rejects_canonical_semantic_attacks(tmp_path: Path, attack: str) -> None:
    bundle, spec = _inputs()
    store = DevelopmentProtocolPlanStore(tmp_path / "plans")
    published = publish_development_protocol_plan(
        store=store,
        bundle=bundle,
        spec=spec,
        plan_id="semantic-attack",
        now=lambda: FIXED_TIME,
    )
    root = published.plan_path
    plan_path = root / "compiled_protocol_plan.json"
    receipt_path = root / "protocol_plan_receipt.json"
    metadata_path = root / "protocol_plan_metadata.json"
    record_path = root / "protocol_plan_record.json"
    originals = {path: path.read_bytes() for path in root.iterdir() if path.is_file()}

    if attack in {
        "missing_node_state",
        "condition_identity",
        "selected_node",
        "measurement_order",
        "measurement_count",
        "random_seed",
        "randomization_algorithm",
    }:
        value = json.loads(plan_path.read_bytes())
        if attack == "missing_node_state":
            value["condition_matrix"][0]["node_states"].pop(
                next(iter(value["condition_matrix"][0]["node_states"]))
            )
        elif attack == "condition_identity":
            value["condition_matrix"][0]["condition_label"] = "tampered"
        elif attack == "selected_node":
            value["condition_matrix"][1]["selected_nodes"] = []
        elif attack == "measurement_order":
            value["session_slots"][0]["reassembly_slots"][0]["condition_blocks"][0]["measurements"][
                0
            ]["global_planned_ordinal"] = 999
        elif attack == "measurement_count":
            value["planned_measurement_count"] += 1
        elif attack == "random_seed":
            value["random_seed"] = "tampered-seed"
        else:
            value["randomization_algorithm_version"] = "9.9.9"
        payload = canonical_json_bytes(value)
        plan_path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        (root / "compiled_protocol_plan.sha256").write_bytes(
            f"{digest}  compiled_protocol_plan.json\n".encode("ascii")
        )
    elif attack == "receipt_state":
        value = json.loads(receipt_path.read_bytes())
        value["operator_confirmation_status"] = "confirmed"
        payload = canonical_json_bytes(value)
        receipt_path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        (root / "protocol_plan_receipt.sha256").write_bytes(
            f"{digest}  protocol_plan_receipt.json\n".encode("ascii")
        )
    elif attack == "metadata_state":
        value = json.loads(metadata_path.read_bytes())
        value["experimental_result"] = True
        metadata_path.write_bytes(canonical_json_bytes(value))
    else:
        value = json.loads(record_path.read_bytes())
        value["hardware_io_performed"] = True
        record_path.write_bytes(canonical_json_bytes(value))

    before = _tree_hash(store.root)
    with pytest.raises(ProtocolPlanPersistenceError):
        validate_development_protocol_plan(
            store=store, bundle=bundle, spec=spec, plan_id="semantic-attack"
        )
    assert _tree_hash(store.root) == before
    for path, payload in originals.items():
        path.write_bytes(payload)
    validate_development_protocol_plan(
        store=store, bundle=bundle, spec=spec, plan_id="semantic-attack"
    )


def test_four_stage_two_root_public_flow_is_byte_deterministic(tmp_path: Path) -> None:
    outputs: list[dict[str, dict[str, bytes]]] = []
    for root_name in ("root-a", "root-b"):
        root_outputs: dict[str, dict[str, bytes]] = {}
        store = DevelopmentProtocolPlanStore(tmp_path / root_name)
        for stage in range(1, 5):
            bundle, spec = _inputs(stage)
            published = publish_development_protocol_plan(
                store=store,
                bundle=bundle,
                spec=spec,
                plan_id=f"stage{stage}-golden",
                now=lambda: FIXED_TIME,
            )
            validate_development_protocol_plan(
                store=store,
                bundle=bundle,
                spec=spec,
                plan_id=f"stage{stage}-golden",
            )
            root_outputs[f"stage{stage}"] = {
                path.name: path.read_bytes() for path in published.plan_path.iterdir()
            }
        outputs.append(root_outputs)
        assert not list(store.root.rglob("session_*"))
        assert not list(store.root.rglob("run_*"))
        assert not list(store.root.rglob("events"))
        assert not (tmp_path / root_name / "real").exists()

    assert outputs[0] == outputs[1]
    core_names = (
        "compiled_protocol_plan.json",
        "compiled_protocol_plan.sha256",
        "protocol_plan_receipt.json",
        "protocol_plan_receipt.sha256",
        "protocol_plan_metadata.json",
    )
    expected_sha256 = {
        "stage1": (
            "62fcb88144e84ef564053b61d4d40f30f8bd7d034953da3c2431488b8acdfce2",
            "e9e0928cad4b18d4fb7bee0b6893c02c276c99149d89ecf9f24bd366422530f9",
            "ed533234107927fb1c40b3860fa94e607a58cd2597deffd23b73bfa4c3f08ce9",
            "6da6a79003f4b47bdd092f55d6cbb53631dfbce757f88c9fceb19e60cdd9ae4d",
            "08a4d84c0348981b98be23fb9c9dfe4d03d1a82084aa6c8323e5ed156d55ca3c",
        ),
        "stage2": (
            "fdd49fe9901f7ad7f7febb8f441a39d8e7b16bc98db0c7fc6a7b6f5e48f39fe8",
            "9cc88d4c1a22a6171811ab33313465c5f006b079944662d1b3e9c1c1133b056a",
            "35c97bfdb4814ad9557cb07f75d7e5dd6d1170c97e0e3d67173758c8ffcd5c65",
            "890b293766b567d1113a7190921b97bda22a9f81e63585cac71612c452d58956",
            "8878b6f778d4ce7788c050f305672ff215ec465d72000792109553de0ad1c559",
        ),
        "stage3": (
            "685a6ac37018c40b80ce9cdf89fc6e338180d82581120f41173dcd64e9339ff4",
            "8d08daeb184301ef2f28eb21f5dc0a8d6612bc5330deb319a5396d78047443ea",
            "2fc3becd26466d281d6f5ee4073dd9df36e2960a9e196101f3cee79b1d7ec577",
            "e787b8bc1f98fe3ef871c706195a6676ba7e15c7d7547d32da0c8710fa80be26",
            "f4baec90065f8328bf0a91b5a5a7dea10f8ea48c631d3f7935ad752aca24cdb9",
        ),
        "stage4": (
            "45dd7267da0c5fa30aecaf9f19a1d619622404aa3fd696a399817683aa807716",
            "18065d504b352d39d27841ca5075f11102ef003cdb946b8e37eb9ade6bfcf2e6",
            "c98886c429804ea9849675e510ab74ed5fac88112c5e0c0f5b9a9c9335dc9025",
            "e6975efc90c7db98fca320e1eabafee3889a511fd2e17ac52205db40f46373ab",
            "fdd37037644e7fa908973f3934b1171a3a3af634048ef0342e259f0b790aa266",
        ),
    }
    assert {
        stage: tuple(hashlib.sha256(payloads[name]).hexdigest() for name in core_names)
        for stage, payloads in outputs[0].items()
    } == expected_sha256
