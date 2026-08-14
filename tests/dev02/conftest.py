from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from acoustic_ladder.config.bundle import LoadedBundle, load_bundle
from acoustic_ladder.config.models import SyntheticConfig, manifest_nodes
from acoustic_ladder.domain.models import (
    DataOrigin,
    LoadingDirection,
    MeasurementRunRecord,
    NodeState,
    ReassemblyRecord,
    RunMode,
    SessionRecord,
)
from acoustic_ladder.storage.store import DataRoots, ImmutableSessionStore
from acoustic_ladder.synthetic.generator import SyntheticResult, generate_synthetic_arrays

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "config" / "devices" / "device_manifest.provisional.json"
SIDECAR_PATH = REPO_ROOT / "config" / "devices" / "device_manifest.provisional.sha256"
FIXED_TIME = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def manifest() -> dict[str, object]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="session")
def loaded_bundle() -> LoadedBundle:
    return load_bundle(
        project_root=REPO_ROOT,
        manifest_path=MANIFEST_PATH,
        manifest_sidecar_path=SIDECAR_PATH,
        audio_path=REPO_ROOT / "config" / "audio" / "default_1x1_ess.yaml",
        protocol_path=REPO_ROOT / "config" / "protocols" / "stage4_four_node_states.yaml",
        analysis_path=REPO_ROOT / "config" / "analysis" / "default.yaml",
        synthetic_path=REPO_ROOT / "config" / "synthetic" / "default.yaml",
        now=lambda: FIXED_TIME,
    )


@pytest.fixture(scope="session")
def synthetic_config(loaded_bundle: LoadedBundle) -> SyntheticConfig:
    model = loaded_bundle.configs["synthetic"].model
    assert isinstance(model, SyntheticConfig)
    return model


@pytest.fixture()
def blocked_states(manifest: dict[str, object]) -> dict[str, NodeState]:
    return {
        node_id: NodeState(
            node_id=node_id,
            state_id="synthetic_BLK",
            module_id="BLK",
            state_type="synthetic_discrete_module",
            discrete_label="BLK",
            continuous_value=None,
            unit=None,
            loading_direction=LoadingDirection.NOT_APPLICABLE,
            proxy_state=False,
            provenance="test fixture",
            notes="NOT_EXPERIMENTAL_RESULT",
        )
        for node_id in manifest_nodes(manifest)
    }


@pytest.fixture()
def store(tmp_path: Path) -> ImmutableSessionStore:
    return ImmutableSessionStore(
        DataRoots(synthetic=tmp_path / "synthetic", real=tmp_path / "real")
    )


def session_record(
    session_id: str = "s001", origin: DataOrigin = DataOrigin.SYNTHETIC
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        session_schema_version="1.0.0",
        created_at=FIXED_TIME,
        data_origin=origin,
        run_mode=RunMode.DEVELOPMENT if origin is DataOrigin.SYNTHETIC else RunMode.FORMAL,
        operator=None,
        device_manifest_reference="manifest/device_manifest.provisional.json",
        config_bundle_reference="protocol/config_bundle.json",
        reassembly_ids=["r001"],
        run_ids=[],
        immutable_status="immutable",
        notes="test session",
    )


def reassembly_record(session_id: str = "s001") -> ReassemblyRecord:
    return ReassemblyRecord(
        reassembly_id="r001",
        session_id=session_id,
        sequence_index=0,
        created_at=FIXED_TIME,
        assembly_description="synthetic fixture assembly",
        operator_confirmation=False,
        related_run_ids=[],
    )


def synthetic_result(
    manifest: dict[str, object],
    config: SyntheticConfig,
    states: dict[str, NodeState],
    run_id: str = "run001",
) -> SyntheticResult:
    return generate_synthetic_arrays(
        manifest,
        config,
        states,
        artifact_path=f"raw/run_{run_id}/synthetic_arrays.npz",
    )


@pytest.fixture()
def generated_result(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> SyntheticResult:
    return synthetic_result(manifest, synthetic_config, blocked_states)


def run_record(
    result: SyntheticResult,
    states: dict[str, NodeState],
    bundle: LoadedBundle,
    run_id: str = "run001",
) -> MeasurementRunRecord:
    return MeasurementRunRecord(
        run_id=run_id,
        session_id="s001",
        reassembly_id="r001",
        protocol_id="stage4_four_node_states",
        measurement_order=0,
        data_origin=DataOrigin.SYNTHETIC,
        run_mode=RunMode.DEVELOPMENT,
        formal_eligible=False,
        node_states=states,
        created_at=FIXED_TIME,
        started_at=FIXED_TIME,
        completed_at=FIXED_TIME,
        config_hashes={
            **bundle.receipt.normalized_config_hashes,
            "bundle": bundle.receipt.bundle_content_sha256,
        },
        artifacts=[result.artifact],
        backend="transparent-delay-model-v1",
        software_version="0.1.0",
        status="complete",
        failure_reason=None,
        result_marker="NOT_EXPERIMENTAL_RESULT",
        notes="no experimental conclusion",
    )
