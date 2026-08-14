from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate
from pydantic import ValidationError

from acoustic_ladder.cli import main
from acoustic_ladder.config.bundle import LoadedBundle
from acoustic_ladder.config.schema import SCHEMA_MODELS, check_schemas, schema_bytes
from acoustic_ladder.domain.models import (
    ArtifactRef,
    DataOrigin,
    LoadingDirection,
    MeasurementRunRecord,
    NodeState,
    RunMode,
)
from acoustic_ladder.synthetic.generator import SyntheticResult
from tests.dev02.conftest import REPO_ROOT, run_record


def test_node_state_requires_continuous_value_and_unit_together() -> None:
    with pytest.raises(ValidationError, match="both be present or both be null"):
        NodeState(
            node_id="N1",
            state_id="state",
            module_id="B40",
            state_type="generic",
            discrete_label=None,
            continuous_value=1.0,
            unit=None,
            loading_direction=LoadingDirection.LOADING,
            proxy_state=True,
            provenance=None,
            notes=None,
        )


def test_synthetic_run_can_never_be_formal_eligible(
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
    loaded_bundle: LoadedBundle,
) -> None:
    valid = run_record(generated_result, blocked_states, loaded_bundle)
    payload = valid.model_dump(mode="json")
    payload["formal_eligible"] = True
    with pytest.raises(ValidationError, match="never be formal eligible"):
        MeasurementRunRecord.model_validate_json(json.dumps(payload))


def test_synthetic_run_requires_development_and_result_marker(
    generated_result: SyntheticResult,
    blocked_states: dict[str, NodeState],
    loaded_bundle: LoadedBundle,
) -> None:
    valid = run_record(generated_result, blocked_states, loaded_bundle)
    for field, value, message in (
        ("run_mode", RunMode.FORMAL.value, "development"),
        ("result_marker", None, "NOT_EXPERIMENTAL_RESULT"),
    ):
        payload = valid.model_dump(mode="json")
        payload[field] = value
        with pytest.raises(ValidationError, match=message):
            MeasurementRunRecord.model_validate_json(json.dumps(payload))


def test_domain_models_reject_unknown_fields(generated_result: SyntheticResult) -> None:
    payload = generated_result.artifact.model_dump(mode="json")
    payload["unknown"] = "forbidden"
    with pytest.raises(ValidationError, match="Extra inputs"):
        ArtifactRef.model_validate(payload)


def test_all_eight_committed_schemas_match_active_models() -> None:
    assert len(SCHEMA_MODELS) == 8
    check_schemas(REPO_ROOT / "schemas")
    for filename, model in SCHEMA_MODELS.items():
        assert (REPO_ROOT / "schemas" / filename).read_bytes() == schema_bytes(model)


def test_exported_artifact_schema_rejects_unknown_and_missing_fields(
    generated_result: SyntheticResult,
) -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas" / "artifact_ref.schema.json").read_text(encoding="utf-8")
    )
    valid = generated_result.artifact.model_dump(mode="json")
    validate(valid, schema)
    unknown = {**valid, "unknown": True}
    with pytest.raises(JsonSchemaValidationError):
        validate(unknown, schema)
    missing = dict(valid)
    missing.pop("sha256")
    with pytest.raises(JsonSchemaValidationError):
        validate(missing, schema)


def test_cli_config_bundle_hash_and_schema_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(
        [
            "validate-config",
            "audio",
            "config/audio/default_1x1_ess.yaml",
            "--project-root",
            str(REPO_ROOT),
        ]
    )
    assert "PASS audio:" in capsys.readouterr().out
    main(
        [
            "config-hash",
            "analysis",
            "config/analysis/default.yaml",
            "--project-root",
            str(REPO_ROOT),
        ]
    )
    assert len(capsys.readouterr().out.strip()) == 64
    main(
        [
            "validate-bundle",
            "--project-root",
            str(REPO_ROOT),
            "--protocol",
            "config/protocols/stage1_single_bridge.yaml",
        ]
    )
    assert "PASS bundle:" in capsys.readouterr().out
    main(["export-schemas", "--output-dir", str(REPO_ROOT / "schemas"), "--check"])
    assert "PASS schema consistency" in capsys.readouterr().out


def test_cli_synthetic_session_run_validation_and_artifact_verification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    synthetic_root = tmp_path / "synthetic"
    bundle_args = [
        "--project-root",
        str(REPO_ROOT),
        "--protocol",
        "config/protocols/stage4_four_node_states.yaml",
    ]
    main(
        [
            "create-synthetic-session",
            *bundle_args,
            "--synthetic-root",
            str(synthetic_root),
            "--session-id",
            "cli001",
            "--reassembly-id",
            "r001",
        ]
    )
    assert "PASS synthetic session:" in capsys.readouterr().out
    main(
        [
            "generate-synthetic-run",
            *bundle_args,
            "--synthetic-root",
            str(synthetic_root),
            "--session-id",
            "cli001",
            "--reassembly-id",
            "r001",
            "--run-id",
            "run001",
            "--node-state",
            "N1=B40",
        ]
    )
    assert "PASS synthetic run:" in capsys.readouterr().out
    main(
        [
            "validate-session",
            "--synthetic-root",
            str(synthetic_root),
            "--session-id",
            "cli001",
        ]
    )
    assert "PASS session: cli001" in capsys.readouterr().out
    main(
        [
            "validate-run",
            "--synthetic-root",
            str(synthetic_root),
            "--session-id",
            "cli001",
            "--run-id",
            "run001",
        ]
    )
    assert "PASS run: run001" in capsys.readouterr().out

    session = synthetic_root / "session_cli001"
    run_payload = json.loads(
        (session / "raw" / "run_run001" / "run_record.json").read_text(encoding="utf-8")
    )
    artifact_file = tmp_path / "artifact_ref.json"
    artifact_file.write_text(json.dumps(run_payload["artifacts"][0]), encoding="utf-8")
    main(
        [
            "verify-artifact",
            "--session-root",
            str(session),
            "--artifact-ref",
            str(artifact_file),
        ]
    )
    assert "PASS artifact:" in capsys.readouterr().out
    assert not (tmp_path / ".real_root_unavailable_to_synthetic_cli").exists()


def test_data_origin_is_not_used_for_run_mode() -> None:
    assert {item.value for item in DataOrigin} == {"synthetic", "real"}
    assert {item.value for item in RunMode} == {"formal", "diagnostic", "development"}
