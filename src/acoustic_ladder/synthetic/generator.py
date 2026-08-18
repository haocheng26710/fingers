"""Simple non-experimental delay/coupling model driven by manifest geometry."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.config.models import SyntheticConfig, manifest_nodes
from acoustic_ladder.domain.models import ArtifactRef, NodeState
from acoustic_ladder.storage.io import sha256_bytes
from acoustic_ladder.storage.npz import deterministic_npz_bytes

FloatArray = NDArray[np.float32] | NDArray[np.float64]


class SyntheticGenerationError(ValueError):
    """Raised when manifest/state/config inputs cannot form a transparent synthetic run."""


@dataclass(frozen=True)
class SyntheticResult:
    outputs: FloatArray
    inputs: FloatArray
    synthetic_ir: FloatArray
    metadata: dict[str, object]
    npz_bytes: bytes
    artifact: ArtifactRef


def _manifest_modules(manifest: dict[str, object]) -> dict[str, float | None]:
    try:
        raw_modules = manifest["modules"]
        assert isinstance(raw_modules, list)
        modules: dict[str, float | None] = {}
        for raw in raw_modules:
            assert isinstance(raw, dict)
            module_id = str(raw["id"])
            if module_id == "BLK":
                modules[module_id] = None
            else:
                aperture = raw["target_aperture"]
                assert isinstance(aperture, dict)
                modules[module_id] = float(aperture["value"])
        return modules
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        raise SyntheticGenerationError(f"invalid manifest modules: {exc}") from exc


def manifest_round_trip_delays_s(
    manifest: dict[str, object], speed_of_sound_m_s: float
) -> dict[str, float]:
    """Compute 2*x/c from supplied manifest node positions."""

    return {
        node_id: 2.0 * position_mm / 1000.0 / speed_of_sound_m_s
        for node_id, position_mm in manifest_nodes(manifest).items()
    }


def generate_synthetic_arrays(
    manifest: dict[str, object],
    config: SyntheticConfig,
    node_states: dict[str, NodeState],
    *,
    session_index: int = 0,
    reassembly_index: int = 0,
    artifact_path: str = "raw/run_synthetic/synthetic_arrays.npz",
) -> SyntheticResult:
    """Generate channel-first arrays; never a real acoustic result or formal ESS."""

    nodes = manifest_nodes(manifest)
    if set(node_states) != set(nodes):
        missing = sorted(set(nodes) - set(node_states))
        extra = sorted(set(node_states) - set(nodes))
        raise SyntheticGenerationError(
            f"node-state map must be complete: missing={missing}, extra={extra}"
        )
    modules = _manifest_modules(manifest)
    unknown_modules = sorted({state.module_id for state in node_states.values()} - modules.keys())
    if unknown_modules:
        raise SyntheticGenerationError(f"unknown modules: {unknown_modules}")
    dtype = np.dtype(config.output_dtype)
    sample_count = round(config.sample_rate_hz * config.duration_s)
    if sample_count <= 0:
        raise SyntheticGenerationError("synthetic duration produces no samples")
    delays_s = manifest_round_trip_delays_s(manifest, config.speed_of_sound.value_m_s)
    delay_samples = {
        node_id: round(delay * config.sample_rate_hz) for node_id, delay in delays_s.items()
    }
    ir_sample_count = max(delay_samples.values(), default=0) + 33
    seed_sequence = np.random.SeedSequence([config.random_seed, session_index, reassembly_index])
    rng = np.random.default_rng(seed_sequence)
    outputs = rng.normal(0.0, 0.1, size=(config.output_channel_count, sample_count)).astype(dtype)
    synthetic_ir = np.zeros(
        (config.input_channel_count, config.output_channel_count, ir_sample_count),
        dtype=dtype,
    )
    synthetic_ir[:, :, 0] = config.baseline_coupling
    aperture_values = [value for value in modules.values() if value is not None]
    reference_aperture = max(aperture_values, default=1.0)
    node_weights: dict[str, float] = {}
    for node_id, state in node_states.items():
        aperture = modules[state.module_id]
        if aperture is None:
            node_weights[node_id] = 0.0
            continue
        travel_m = 2.0 * nodes[node_id] / 1000.0
        weight = (
            config.module_effect_scale
            * (aperture / reference_aperture) ** 2
            * math.exp(-config.propagation_loss_per_m * travel_m)
        )
        node_weights[node_id] = weight
        synthetic_ir[:, :, delay_samples[node_id]] += weight
    session_factor = 1.0 + rng.normal(0.0, config.session_drift)
    reassembly_factor = 1.0 + rng.normal(0.0, config.reassembly_drift)
    synthetic_ir *= session_factor * reassembly_factor
    inputs = np.zeros((config.input_channel_count, sample_count), dtype=dtype)
    for input_index in range(config.input_channel_count):
        for output_index in range(config.output_channel_count):
            convolved = np.convolve(
                outputs[output_index].astype(np.float64),
                synthetic_ir[input_index, output_index].astype(np.float64),
                mode="full",
            )[:sample_count]
            inputs[input_index] += convolved.astype(dtype)
    if config.noise_level > 0:
        noise = np.asarray(rng.normal(0.0, config.noise_level, size=inputs.shape), dtype=dtype)
        inputs += noise
    arrays: dict[str, FloatArray] = {
        "inputs": inputs,
        "outputs": outputs,
        "synthetic_ir": synthetic_ir,
    }
    if any(not np.isfinite(array).all() for array in arrays.values()):
        raise SyntheticGenerationError("synthetic arrays contain non-finite values")
    npz_bytes = deterministic_npz_bytes(arrays)
    metadata: dict[str, object] = {
        "marker": "NOT_EXPERIMENTAL_RESULT",
        "data_origin": "synthetic",
        "run_mode": "development",
        "formal_eligible": False,
        "generator_version": config.generator_version,
        "random_seed": config.random_seed,
        "session_index": session_index,
        "reassembly_index": reassembly_index,
        "model": "transparent_round_trip_delay_and_relative_aperture_coupling",
        "formula": {
            "node_delay": "2 * node_position_m / speed_of_sound_m_s",
            "module_weight": (
                "scale * (target_aperture / max_aperture)^2 * exp(-loss * round_trip_distance_m)"
            ),
        },
        "node_delays_s": delays_s,
        "node_delay_samples": delay_samples,
        "node_weights": node_weights,
        "drift_factors": {
            "session": session_factor,
            "reassembly": reassembly_factor,
        },
        "arrays": {
            name: {"shape": list(array.shape), "dtype": str(array.dtype)}
            for name, array in arrays.items()
        },
        "parameters": config.model_dump(mode="json"),
        "physical_limitations": config.physical_limitations,
        "claims": [],
    }
    artifact = ArtifactRef(
        artifact_type="synthetic_channel_first_arrays",
        path=artifact_path,
        sha256=sha256_bytes(npz_bytes),
        byte_size=len(npz_bytes),
        format="application/x-npz",
        shape=None,
        dtype=None,
        created_by=config.generator_version,
        immutable=True,
    )
    return SyntheticResult(outputs, inputs, synthetic_ir, metadata, npz_bytes, artifact)


def validate_npz_metadata(npz_bytes: bytes, metadata: dict[str, object]) -> None:
    """Reject metadata whose channel-first shapes/dtypes disagree with the NPZ arrays."""

    try:
        declared = metadata["arrays"]
        assert isinstance(declared, dict)
        with np.load(io.BytesIO(npz_bytes), allow_pickle=False) as archive:
            if set(archive.files) != set(declared):
                raise SyntheticGenerationError("NPZ arrays and metadata names differ")
            for name in archive.files:
                array = archive[name]
                item = declared[name]
                assert isinstance(item, dict)
                if list(array.shape) != item.get("shape"):
                    raise SyntheticGenerationError(f"shape metadata mismatch for {name}")
                if str(array.dtype) != item.get("dtype"):
                    raise SyntheticGenerationError(f"dtype metadata mismatch for {name}")
                if not np.isfinite(array).all():
                    raise SyntheticGenerationError(f"non-finite values in {name}")
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, SyntheticGenerationError):
            raise
        raise SyntheticGenerationError(f"invalid synthetic metadata: {exc}") from exc
