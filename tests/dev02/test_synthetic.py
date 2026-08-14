from __future__ import annotations

import copy

import numpy as np
import pytest

from acoustic_ladder.config.models import SyntheticConfig
from acoustic_ladder.domain.models import NodeState
from acoustic_ladder.synthetic.generator import (
    SyntheticGenerationError,
    SyntheticResult,
    generate_synthetic_arrays,
    manifest_round_trip_delays_s,
    validate_npz_metadata,
)


def test_same_seed_and_indices_produce_identical_npz_bytes(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> None:
    first = generate_synthetic_arrays(manifest, synthetic_config, blocked_states)
    second = generate_synthetic_arrays(manifest, synthetic_config, blocked_states)
    assert first.npz_bytes == second.npz_bytes
    assert first.artifact.sha256 == second.artifact.sha256


def test_different_seed_changes_output_bytes(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> None:
    changed = synthetic_config.model_copy(update={"random_seed": synthetic_config.random_seed + 1})
    first = generate_synthetic_arrays(manifest, synthetic_config, blocked_states)
    second = generate_synthetic_arrays(manifest, changed, blocked_states)
    assert first.npz_bytes != second.npz_bytes


def test_node_delays_are_computed_from_manifest(
    manifest: dict[str, object], synthetic_config: SyntheticConfig
) -> None:
    delays = manifest_round_trip_delays_s(manifest, synthetic_config.speed_of_sound.value_m_s)
    architecture = manifest["architecture"]
    assert isinstance(architecture, dict)
    nodes = architecture["nodes"]
    assert isinstance(nodes, list)
    node = next(item for item in nodes if isinstance(item, dict) and item.get("id") == "N1")
    position = node["position"]
    assert isinstance(position, dict)
    position_mm = float(position["value"])
    assert delays["N1"] == pytest.approx(
        2 * position_mm / 1000.0 / synthetic_config.speed_of_sound.value_m_s
    )


def test_modified_manifest_position_changes_delay_without_code_change(
    manifest: dict[str, object], synthetic_config: SyntheticConfig
) -> None:
    changed = copy.deepcopy(manifest)
    architecture = changed["architecture"]
    assert isinstance(architecture, dict)
    nodes = architecture["nodes"]
    assert isinstance(nodes, list)
    first = nodes[0]
    assert isinstance(first, dict)
    position = first["position"]
    assert isinstance(position, dict)
    position["value"] = 999.0
    original = manifest_round_trip_delays_s(manifest, synthetic_config.speed_of_sound.value_m_s)
    modified = manifest_round_trip_delays_s(changed, synthetic_config.speed_of_sound.value_m_s)
    assert modified[str(first["id"])] != original[str(first["id"])]
    assert modified[str(first["id"])] == pytest.approx(
        2 * 0.999 / synthetic_config.speed_of_sound.value_m_s
    )


def test_arrays_are_channel_first_typed_finite_and_match_metadata(
    generated_result: SyntheticResult,
) -> None:
    result = generated_result
    assert result.outputs.shape == (1, 12000)
    assert result.inputs.shape == (1, 12000)
    assert result.synthetic_ir.shape[:2] == (1, 1)
    assert result.outputs.dtype == result.inputs.dtype == result.synthetic_ir.dtype == np.float32
    assert np.isfinite(result.outputs).all()
    assert np.isfinite(result.inputs).all()
    assert np.isfinite(result.synthetic_ir).all()
    validate_npz_metadata(result.npz_bytes, result.metadata)


def test_metadata_shape_or_dtype_mismatch_is_rejected(
    generated_result: SyntheticResult,
) -> None:
    result = generated_result
    metadata = copy.deepcopy(result.metadata)
    arrays = metadata["arrays"]
    assert isinstance(arrays, dict)
    outputs = arrays["outputs"]
    assert isinstance(outputs, dict)
    outputs["shape"] = [99, 99]
    with pytest.raises(SyntheticGenerationError, match="shape metadata mismatch"):
        validate_npz_metadata(result.npz_bytes, metadata)


def test_synthetic_metadata_has_origin_guard_and_no_claims(
    generated_result: SyntheticResult,
) -> None:
    result = generated_result
    assert result.metadata["data_origin"] == "synthetic"
    assert result.metadata["run_mode"] == "development"
    assert result.metadata["formal_eligible"] is False
    assert result.metadata["marker"] == "NOT_EXPERIMENTAL_RESULT"
    assert result.metadata["claims"] == []
    text = str(result.metadata).lower()
    assert "accuracy" not in text
    assert "experimental conclusion" not in text


def test_session_and_reassembly_drift_can_be_disabled(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> None:
    disabled = synthetic_config.model_copy(update={"session_drift": 0.0, "reassembly_drift": 0.0})
    result = generate_synthetic_arrays(
        manifest, disabled, blocked_states, session_index=7, reassembly_index=11
    )
    assert result.metadata["drift_factors"] == {"session": 1.0, "reassembly": 1.0}


def test_noise_level_can_be_disabled_without_changing_excitation_or_ir(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> None:
    silent_noise = synthetic_config.model_copy(update={"noise_level": 0.0})
    with_noise = generate_synthetic_arrays(manifest, synthetic_config, blocked_states)
    without_noise = generate_synthetic_arrays(manifest, silent_noise, blocked_states)
    np.testing.assert_array_equal(with_noise.outputs, without_noise.outputs)
    np.testing.assert_array_equal(with_noise.synthetic_ir, without_noise.synthetic_ir)
    assert not np.array_equal(with_noise.inputs, without_noise.inputs)


def test_all_blk_states_generate_only_direct_baseline_ir(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> None:
    result = generate_synthetic_arrays(manifest, synthetic_config, blocked_states)
    assert result.synthetic_ir[0, 0, 0] != 0
    assert np.count_nonzero(result.synthetic_ir[0, 0, 1:]) == 0
    weights = result.metadata["node_weights"]
    assert isinstance(weights, dict)
    assert set(weights.values()) == {0.0}


def test_unknown_module_is_rejected(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> None:
    changed = dict(blocked_states)
    original = changed["N1"]
    changed["N1"] = original.model_copy(update={"module_id": "UNKNOWN"})
    with pytest.raises(SyntheticGenerationError, match="unknown modules"):
        generate_synthetic_arrays(manifest, synthetic_config, changed)


def test_incomplete_node_state_map_is_rejected(
    manifest: dict[str, object],
    synthetic_config: SyntheticConfig,
    blocked_states: dict[str, NodeState],
) -> None:
    changed = dict(blocked_states)
    changed.pop("N1")
    with pytest.raises(SyntheticGenerationError, match="must be complete"):
        generate_synthetic_arrays(manifest, synthetic_config, changed)
