from __future__ import annotations

import hashlib
import inspect
import json
import math
import shutil
import struct
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from acoustic_ladder import cli
from acoustic_ladder.audio.context_validation import validate_audio_context_bundle
from acoustic_ladder.audio.ess import (
    EssError,
    MissingEssFieldsError,
    generate_ess,
    raw_float32_bytes,
    spec_from_audio_config,
    theoretical_frequency,
    theoretical_phase,
)
from acoustic_ladder.audio.excitation_models import (
    EssArtifactMetadata,
    EssSignalSpec,
    round_half_up_samples,
)
from acoustic_ladder.audio.excitation_persistence import (
    METADATA_NAME,
    METADATA_SIDECAR_NAME,
    SAFETY_MARKER,
    WAV_NAME,
    WAV_SIDECAR_NAME,
    EssArtifactError,
    decode_ieee_float32_wav,
    encode_ieee_float32_wav,
    publish_offline_ess_artifact,
    validate_offline_ess_artifact,
)
from acoustic_ladder.config.bundle import LoadedConfig, canonical_json_bytes, load_config
from acoustic_ladder.config.models import AudioConfig
from acoustic_ladder.config.schema import ALL_GENERATED_SCHEMA_MODELS, check_schemas
from tests.conftest import REPO_ROOT

FIXTURE_REFERENCE = "tests/fixtures/audio/ess_offline_development.yaml"
FIXTURE = REPO_ROOT / FIXTURE_REFERENCE
FORMAL = REPO_ROOT / "config/audio/default_1x1_ess.yaml"
INVENTORY_REFERENCE = "reference/audio/inventory/DEV-03.01_audio_inventory.json"
CONTEXT_REFERENCE = "reference/audio/inventory/DEV-03.02_inventory_capture_context.json"
HARDWARE_REFERENCE = "reference/audio/hardware_setup.provisional.json"
INVENTORY = REPO_ROOT / INVENTORY_REFERENCE
CONTEXT = REPO_ROOT / CONTEXT_REFERENCE
HARDWARE = REPO_ROOT / HARDWARE_REFERENCE
SUMMARY = REPO_ROOT / "reference/audio/inventory/DEV-03.02_audio_inventory_summary.md"
PREFLIGHT = REPO_ROOT / "reference/audio/inventory/DEV-03.02_contextual_preflight_report.json"


def _load_development(path: Path = FIXTURE, *, project_root: Path = REPO_ROOT) -> LoadedConfig:
    return load_config("audio", path, project_root=project_root)


def _spec() -> EssSignalSpec:
    loaded = _load_development()
    assert isinstance(loaded.model, AudioConfig)
    return spec_from_audio_config(loaded.model)


def _spec_data() -> dict[str, object]:
    return _spec().model_dump(mode="python")


def _publish(tmp_path: Path, artifact_id: str = "fixture") -> tuple[LoadedConfig, Path]:
    loaded = _load_development()
    receipt = publish_offline_ess_artifact(tmp_path, artifact_id, loaded)
    return loaded, receipt.artifact_root


def _rewrite_sidecar(path: Path, sidecar: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="ascii", newline="\n")


def _write_canonical(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def _context_copy(tmp_path: Path) -> dict[str, Path]:
    sources = {
        "inventory": INVENTORY,
        "inventory_sidecar": INVENTORY.with_suffix(".sha256"),
        "context": CONTEXT,
        "context_sidecar": CONTEXT.with_suffix(".sha256"),
        "summary": SUMMARY,
        "summary_sidecar": SUMMARY.with_suffix(".sha256"),
        "preflight": PREFLIGHT,
        "preflight_sidecar": PREFLIGHT.with_suffix(".sha256"),
        "hardware": HARDWARE,
    }
    copied: dict[str, Path] = {}
    for name, source in sources.items():
        target = tmp_path / source.name
        shutil.copy2(source, target)
        copied[name] = target
    return copied


def _validate_context(paths: dict[str, Path]) -> None:
    validate_audio_context_bundle(
        inventory_path=paths["inventory"],
        inventory_sidecar_path=paths["inventory_sidecar"],
        context_path=paths["context"],
        context_sidecar_path=paths["context_sidecar"],
        summary_path=paths["summary"],
        summary_sidecar_path=paths["summary_sidecar"],
        contextual_preflight_path=paths["preflight"],
        contextual_preflight_sidecar_path=paths["preflight_sidecar"],
        hardware_setup_path=paths["hardware"],
        inventory_reference=INVENTORY_REFERENCE,
        context_reference=CONTEXT_REFERENCE,
        hardware_setup_reference=HARDWARE_REFERENCE,
    )


def test_formal_audio_config_keeps_all_ess_completion_fields_null() -> None:
    loaded = load_config("audio", FORMAL, project_root=REPO_ROOT)
    assert isinstance(loaded.model, AudioConfig)
    assert loaded.model.ess_duration_s is None
    assert loaded.model.pre_silence_s is None
    assert loaded.model.post_silence_s is None
    assert loaded.model.ess_fade_in_s is None
    assert loaded.model.ess_fade_out_s is None
    assert loaded.model.ess_digital_peak_dbfs is None
    assert loaded.model.hardware_ready is False


def test_formal_config_rejection_lists_every_missing_ess_field() -> None:
    loaded = load_config("audio", FORMAL, project_root=REPO_ROOT)
    assert isinstance(loaded.model, AudioConfig)
    with pytest.raises(MissingEssFieldsError) as caught:
        spec_from_audio_config(loaded.model)
    for field in (
        "ess_duration_s",
        "pre_silence_s",
        "post_silence_s",
        "ess_fade_in_s",
        "ess_fade_out_s",
        "ess_digital_peak_dbfs",
    ):
        assert field in str(caught.value)


def test_development_fixture_extracts_complete_strict_spec() -> None:
    spec = _spec()
    assert spec.sample_rate_hz == 48000
    assert spec.start_frequency_hz == 300.0
    assert spec.end_frequency_hz == 10000.0
    assert spec.sweep_duration_s == 0.25
    assert spec.digital_peak_dbfs == -20.0


def test_development_fixture_has_explicit_false_safety_flags() -> None:
    loaded = _load_development()
    assert isinstance(loaded.model, AudioConfig)
    assert loaded.model.playback_authorized is False
    assert loaded.model.formal_eligible is False
    assert loaded.model.experimental_result is False
    assert loaded.model.hardware_ready is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sample_rate_hz", 0),
        ("start_frequency_hz", 0.0),
        ("end_frequency_hz", 300.0),
        ("end_frequency_hz", 24000.0),
        ("sweep_duration_s", 0.0),
        ("pre_silence_s", -0.1),
        ("post_silence_s", -0.1),
        ("fade_in_s", -0.1),
        ("fade_out_s", -0.1),
        ("digital_peak_dbfs", 0.01),
        ("output_channel_count", 2),
        ("output_dtype", "float64"),
        ("playback_authorized", True),
        ("formal_eligible", True),
        ("experimental_result", True),
        ("start_frequency_hz", math.nan),
        ("end_frequency_hz", math.inf),
        ("sweep_duration_s", "0.25"),
    ],
)
def test_strict_spec_rejects_invalid_field(field: str, value: object) -> None:
    data = _spec_data()
    data[field] = value
    with pytest.raises(ValidationError):
        EssSignalSpec.model_validate(data)


def test_spec_rejects_fades_longer_than_sweep() -> None:
    data = _spec_data()
    data.update({"fade_in_s": 0.2, "fade_out_s": 0.2})
    with pytest.raises(ValidationError, match="fade durations"):
        EssSignalSpec.model_validate(data)


@pytest.mark.parametrize("field", ["fade_in_s", "fade_out_s"])
def test_spec_rejects_nonzero_fade_below_two_samples(field: str) -> None:
    data = _spec_data()
    data[field] = 1 / 48000
    with pytest.raises(ValidationError, match="at least two samples"):
        EssSignalSpec.model_validate(data)


def test_spec_rejects_unknown_field() -> None:
    data = _spec_data()
    data["device_index"] = 7
    with pytest.raises(ValidationError):
        EssSignalSpec.model_validate(data)


@pytest.mark.parametrize(
    ("seconds", "rate", "expected"),
    [(0.0, 10, 0), (0.04, 10, 0), (0.05, 10, 1), (0.15, 10, 2)],
)
def test_sample_count_uses_round_half_up(seconds: float, rate: int, expected: int) -> None:
    assert round_half_up_samples(seconds, rate) == expected


def test_generation_is_channel_first_float32_and_contiguous() -> None:
    result = generate_ess(_spec())
    assert result.samples.shape == (1, 12960)
    assert result.samples.dtype == np.float32
    assert result.samples.flags.c_contiguous


def test_generation_sample_counts_and_actual_durations_are_recorded() -> None:
    timing = generate_ess(_spec()).timing
    assert timing.sweep_sample_count == 12000
    assert timing.pre_silence_sample_count == 480
    assert timing.post_silence_sample_count == 480
    assert timing.fade_in_sample_count == 240
    assert timing.fade_out_sample_count == 240
    assert timing.actual_sweep_duration_s == 0.25


def test_pre_and_post_silence_are_exact_zero() -> None:
    result = generate_ess(_spec())
    assert np.count_nonzero(result.samples[:, :480]) == 0
    assert np.count_nonzero(result.samples[:, -480:]) == 0


def test_fade_endpoints_are_exact_zero() -> None:
    result = generate_ess(_spec())
    active = result.samples[0, 480:-480]
    assert active[0] == np.float32(0)
    assert active[-1] == np.float32(0)


def test_zero_length_fades_generate_without_division_by_zero() -> None:
    data = _spec_data()
    data.update({"fade_in_s": 0.0, "fade_out_s": 0.0})
    result = generate_ess(EssSignalSpec.model_validate(data))
    assert np.isfinite(result.samples).all()


def test_actual_peak_matches_minus_twenty_dbfs_target() -> None:
    result = generate_ess(_spec())
    assert result.metrics.target_linear_peak == pytest.approx(0.1)
    assert result.metrics.actual_peak == pytest.approx(0.1, abs=2e-8)
    assert np.max(np.abs(result.samples)) <= 1.0


def test_metrics_match_float32_output_without_dc_removal() -> None:
    result = generate_ess(_spec())
    samples = result.samples
    assert result.metrics.rms == float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    assert result.metrics.mean_dc == float(np.mean(samples, dtype=np.float64))
    assert result.metrics.minimum == float(np.min(samples))
    assert result.metrics.maximum == float(np.max(samples))


def test_all_generated_values_and_metrics_are_finite() -> None:
    result = generate_ess(_spec())
    assert np.isfinite(result.samples).all()
    numeric = result.metrics.model_dump(mode="python")
    assert all(math.isfinite(value) for value in numeric.values() if isinstance(value, float))


def test_same_spec_is_bitwise_deterministic() -> None:
    first = generate_ess(_spec())
    second = generate_ess(_spec())
    assert np.array_equal(first.samples, second.samples)
    assert first.raw_float32_sha256 == second.raw_float32_sha256
    assert first.metrics == second.metrics


def test_raw_hash_uses_canonical_little_endian_float32_bytes() -> None:
    result = generate_ess(_spec())
    assert (
        result.raw_float32_sha256
        == hashlib.sha256(result.samples.astype("<f4", copy=False).tobytes(order="C")).hexdigest()
    )
    assert raw_float32_bytes(result.samples) == result.samples[0].astype("<f4").tobytes()


def test_theoretical_frequency_has_declared_continuous_boundaries() -> None:
    spec = _spec()
    duration = round_half_up_samples(spec.sweep_duration_s, spec.sample_rate_hz) / 48000
    assert theoretical_frequency(spec, 0.0) == pytest.approx(300.0)
    assert theoretical_frequency(spec, duration) == pytest.approx(10000.0)


def test_last_discrete_sample_frequency_is_below_end_frequency() -> None:
    spec = _spec()
    last_time = (round_half_up_samples(spec.sweep_duration_s, 48000) - 1) / 48000
    assert theoretical_frequency(spec, last_time) < spec.end_frequency_hz


def test_wav_is_mono_ieee_float32_with_expected_rate() -> None:
    result = generate_ess(_spec())
    wav = encode_ieee_float32_wav(result.samples, 48000)
    assert wav[0:4] == b"RIFF"
    assert struct.unpack_from("<H", wav, 20)[0] == 3
    assert struct.unpack_from("<H", wav, 22)[0] == 1
    assert struct.unpack_from("<I", wav, 24)[0] == 48000
    assert struct.unpack_from("<H", wav, 34)[0] == 32


def test_wav_roundtrip_is_sample_exact_channel_first() -> None:
    result = generate_ess(_spec())
    decoded, rate = decode_ieee_float32_wav(encode_ieee_float32_wav(result.samples, 48000))
    assert rate == 48000
    assert decoded.shape == (1, 12960)
    assert decoded.dtype == np.float32
    assert np.array_equal(decoded, result.samples)


def test_publish_creates_exactly_four_files_and_valid_sidecars(tmp_path: Path) -> None:
    loaded, root = _publish(tmp_path)
    assert {path.name for path in root.iterdir()} == {
        WAV_NAME,
        WAV_SIDECAR_NAME,
        METADATA_NAME,
        METADATA_SIDECAR_NAME,
    }
    validate_offline_ess_artifact(root, loaded)


def test_metadata_is_canonical_strict_and_contains_no_timestamp_or_absolute_path(
    tmp_path: Path,
) -> None:
    _, root = _publish(tmp_path)
    payload = (root / METADATA_NAME).read_bytes()
    metadata = EssArtifactMetadata.model_validate_json(payload)
    assert payload == canonical_json_bytes(metadata.model_dump(mode="json"))
    assert str(tmp_path).encode() not in payload
    assert b"generated_at" not in payload
    assert b"device_index" not in payload


def test_two_roots_produce_identical_artifact_file_bytes(tmp_path: Path) -> None:
    loaded = _load_development()
    first = publish_offline_ess_artifact(tmp_path / "one", "same", loaded)
    second = publish_offline_ess_artifact(tmp_path / "two", "same", loaded)
    for name in (WAV_NAME, WAV_SIDECAR_NAME, METADATA_NAME, METADATA_SIDECAR_NAME):
        assert (first.artifact_root / name).read_bytes() == (
            second.artifact_root / name
        ).read_bytes()


def test_existing_artifact_is_not_overwritten(tmp_path: Path) -> None:
    loaded, root = _publish(tmp_path)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    with pytest.raises(EssArtifactError, match="already exists"):
        publish_offline_ess_artifact(tmp_path, "fixture", loaded)
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


@pytest.mark.parametrize("artifact_id", ["", ".", "..", "../escape", "a/b", "a\\b", "C:drive", "é"])
def test_unsafe_artifact_id_is_rejected_without_creating_root(
    tmp_path: Path, artifact_id: str
) -> None:
    development_root = tmp_path / "absent"
    with pytest.raises(EssArtifactError):
        publish_offline_ess_artifact(development_root, artifact_id, _load_development())
    assert not development_root.exists()


def test_staging_failure_leaves_no_target_staging_or_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from acoustic_ladder.audio import excitation_persistence

    original = excitation_persistence._write_staged
    calls = 0

    def fail_third(path: Path, payload: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected staging failure")
        original(path, payload)

    monkeypatch.setattr(excitation_persistence, "_write_staged", fail_third)
    with pytest.raises(EssArtifactError, match="could not publish"):
        publish_offline_ess_artifact(tmp_path, "failure", _load_development())
    assert list(tmp_path.iterdir()) == []


def test_wav_tamper_with_recomputed_sidecar_is_rejected(tmp_path: Path) -> None:
    loaded, root = _publish(tmp_path)
    wav = bytearray((root / WAV_NAME).read_bytes())
    wav[-8] ^= 1
    (root / WAV_NAME).write_bytes(wav)
    _rewrite_sidecar(root / WAV_NAME, root / WAV_SIDECAR_NAME)
    with pytest.raises(EssArtifactError):
        validate_offline_ess_artifact(root, loaded)


def test_metadata_tamper_with_recomputed_sidecar_is_rejected(tmp_path: Path) -> None:
    loaded, root = _publish(tmp_path)
    path = root / METADATA_NAME
    value = json.loads(path.read_bytes())
    value["metrics"]["mean_dc"] = value["metrics"]["mean_dc"] + 0.001
    _write_canonical(path, value)
    _rewrite_sidecar(path, root / METADATA_SIDECAR_NAME)
    with pytest.raises(EssArtifactError):
        validate_offline_ess_artifact(root, loaded)


def test_swapped_wav_and_metadata_combination_is_rejected(tmp_path: Path) -> None:
    loaded, first = _publish(tmp_path / "first")
    changed_text = FIXTURE.read_text(encoding="utf-8").replace("-20.0", "-18.0")
    changed_root = tmp_path / "config"
    changed_root.mkdir()
    changed_config = changed_root / "audio.yaml"
    changed_config.write_text(changed_text, encoding="utf-8", newline="\n")
    changed_loaded = _load_development(changed_config, project_root=changed_root)
    assert isinstance(changed_loaded.model, AudioConfig)
    second_receipt = publish_offline_ess_artifact(tmp_path / "second", "fixture", changed_loaded)
    shutil.copy2(second_receipt.artifact_root / WAV_NAME, first / WAV_NAME)
    shutil.copy2(second_receipt.artifact_root / WAV_SIDECAR_NAME, first / WAV_SIDECAR_NAME)
    with pytest.raises(EssArtifactError):
        validate_offline_ess_artifact(first, loaded)


def test_validation_is_read_only(tmp_path: Path) -> None:
    loaded, root = _publish(tmp_path)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    validate_offline_ess_artifact(root, loaded)
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


def test_cli_offline_workflow_never_requests_audio_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden_backend() -> object:
        raise AssertionError("offline ESS must not instantiate the inventory backend")

    monkeypatch.setattr(cli, "_audio_backend", forbidden_backend)
    arguments = [
        "--project-root",
        str(REPO_ROOT),
        "--audio-config",
        FIXTURE_REFERENCE,
    ]
    cli.main(
        [
            "ess-generate-offline",
            *arguments,
            "--development-root",
            str(tmp_path),
            "--artifact-id",
            "cli_fixture",
        ]
    )
    cli.main(
        [
            "ess-validate-offline",
            *arguments,
            "--artifact-root",
            str(tmp_path / "cli_fixture"),
        ]
    )
    output = capsys.readouterr().out
    assert output.count(SAFETY_MARKER) == 2
    assert "PASS offline ESS" in output


def test_schema_export_contains_all_active_models() -> None:
    assert len(ALL_GENERATED_SCHEMA_MODELS) == 47
    check_schemas(REPO_ROOT / "schemas")


def test_committed_context_bundle_passes_semantic_reconstruction(tmp_path: Path) -> None:
    _validate_context(_context_copy(tmp_path))


def test_summary_replacement_with_valid_recomputed_sidecar_is_rejected(tmp_path: Path) -> None:
    paths = _context_copy(tmp_path)
    paths["summary"].write_bytes(paths["summary"].read_bytes() + b"\n")
    _rewrite_sidecar(paths["summary"], paths["summary_sidecar"])
    with pytest.raises(ValueError, match="byte-exact"):
        _validate_context(paths)


def test_summary_device_name_tamper_with_valid_sidecar_is_rejected(tmp_path: Path) -> None:
    paths = _context_copy(tmp_path)
    payload = (
        paths["summary"]
        .read_text(encoding="utf-8")
        .replace("Microsoft 声音映射器 - Input", "Microsoft altered device")
    )
    paths["summary"].write_text(payload, encoding="utf-8", newline="\n")
    _rewrite_sidecar(paths["summary"], paths["summary_sidecar"])
    with pytest.raises(ValueError, match="byte-exact"):
        _validate_context(paths)


def test_hardware_content_tamper_is_rejected(tmp_path: Path) -> None:
    paths = _context_copy(tmp_path)
    value = json.loads(paths["hardware"].read_bytes())
    value["notes"].append("tampered but structurally valid")
    _write_canonical(paths["hardware"], value)
    with pytest.raises(ValueError, match="hardware setup SHA256"):
        _validate_context(paths)


def test_contextual_preflight_hash_tamper_with_valid_sidecar_is_rejected(
    tmp_path: Path,
) -> None:
    paths = _context_copy(tmp_path)
    value = json.loads(paths["preflight"].read_bytes())
    value["inventory_sha256"] = "0" * 64
    _write_canonical(paths["preflight"], value)
    _rewrite_sidecar(paths["preflight"], paths["preflight_sidecar"])
    with pytest.raises(ValueError, match="inventory SHA256"):
        _validate_context(paths)


def test_contextual_preflight_path_tamper_with_valid_sidecar_is_rejected(
    tmp_path: Path,
) -> None:
    paths = _context_copy(tmp_path)
    value = json.loads(paths["preflight"].read_bytes())
    value["capture_context_reference"] = "reference/audio/inventory/other.json"
    _write_canonical(paths["preflight"], value)
    _rewrite_sidecar(paths["preflight"], paths["preflight_sidecar"])
    with pytest.raises(ValueError, match="capture context reference"):
        _validate_context(paths)


def test_swapped_context_combination_with_valid_sidecars_is_rejected(tmp_path: Path) -> None:
    paths = _context_copy(tmp_path)
    value = json.loads(paths["context"].read_bytes())
    value["notes"].append("a different valid context artifact")
    _write_canonical(paths["context"], value)
    _rewrite_sidecar(paths["context"], paths["context_sidecar"])
    with pytest.raises(ValueError, match="capture context SHA256"):
        _validate_context(paths)


def test_public_persistence_apis_have_no_independent_spec_parameter() -> None:
    assert "spec" not in inspect.signature(publish_offline_ess_artifact).parameters
    assert "spec" not in inspect.signature(validate_offline_ess_artifact).parameters


def test_publish_derives_spec_from_loaded_config_before_creating_root(tmp_path: Path) -> None:
    development_root = tmp_path / "not-created"
    receipt = publish_offline_ess_artifact(development_root, "derived", _load_development())
    assert receipt.metadata.spec == _spec()
    assert receipt.metadata.spec.digital_peak_dbfs == -20.0


@pytest.mark.parametrize(
    ("sample_units", "expected_count"),
    [(0.25, 0), (1.0, 1)],
)
def test_spec_rejects_sweep_duration_below_two_rounded_samples(
    sample_units: float, expected_count: int
) -> None:
    data = _spec_data()
    duration_s = sample_units / 48000
    data.update(
        {
            "sweep_duration_s": duration_s,
            "fade_in_s": 0.0,
            "fade_out_s": 0.0,
        }
    )
    assert round_half_up_samples(duration_s, 48000) == expected_count
    with pytest.raises(ValidationError, match="at least two samples"):
        EssSignalSpec.model_validate(data)


def test_spec_accepts_sweep_duration_rounding_to_two_samples() -> None:
    data = _spec_data()
    data.update(
        {
            "sweep_duration_s": 1.5 / 48000,
            "fade_in_s": 0.0,
            "fade_out_s": 0.0,
        }
    )
    spec = EssSignalSpec.model_validate(data)
    assert round_half_up_samples(spec.sweep_duration_s, spec.sample_rate_hz) == 2


def test_spec_rejects_float32_underflowing_digital_peak() -> None:
    data = _spec_data()
    data["digital_peak_dbfs"] = -10000.0
    with pytest.raises(
        ValidationError,
        match="digital peak is not representable as a positive float32 amplitude",
    ):
        EssSignalSpec.model_validate(data)


def test_generator_zero_energy_guard_raises_ess_error_not_zero_division() -> None:
    invalid = _spec().model_copy(update={"digital_peak_dbfs": -10000.0})
    with pytest.raises(EssError, match="positive float32 amplitude"):
        generate_ess(invalid)


def test_explicit_mismatched_spec_is_rejected_by_public_api_before_write(
    tmp_path: Path,
) -> None:
    development_root = tmp_path / "must-not-exist"
    mismatch = _spec().model_copy(update={"digital_peak_dbfs": -18.0})
    public_publish: Callable[..., object] = publish_offline_ess_artifact
    with pytest.raises(TypeError):
        public_publish(development_root, "mismatch", _load_development(), mismatch)
    assert not development_root.exists()


def test_metadata_other_spec_with_recomputed_sidecar_is_rejected_against_config(
    tmp_path: Path,
) -> None:
    loaded, root = _publish(tmp_path)
    metadata_path = root / METADATA_NAME
    value = json.loads(metadata_path.read_bytes())
    value["spec"]["digital_peak_dbfs"] = -18.0
    _write_canonical(metadata_path, value)
    _rewrite_sidecar(metadata_path, root / METADATA_SIDECAR_NAME)
    with pytest.raises(
        EssArtifactError,
        match="ESS specification does not match the loaded audio configuration",
    ):
        validate_offline_ess_artifact(root, loaded)


def test_smallest_positive_float32_peak_can_generate_positive_energy() -> None:
    smallest = float(np.nextafter(np.float32(0), np.float32(1)))
    data = _spec_data()
    data["digital_peak_dbfs"] = 20.0 * math.log10(smallest)
    result = generate_ess(EssSignalSpec.model_validate(data))
    assert result.metrics.actual_peak > 0
    assert result.metrics.rms > 0
    assert math.isfinite(result.metrics.crest_factor)


def test_zero_dbfs_remains_mathematically_valid_without_playback_authorization() -> None:
    data = _spec_data()
    data["digital_peak_dbfs"] = 0.0
    spec = EssSignalSpec.model_validate(data)
    assert spec.digital_peak_dbfs == 0.0
    assert spec.playback_authorized is False


def test_generator_defensively_rejects_zero_rms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(np, "sqrt", lambda value: np.float64(0.0))
    with pytest.raises(EssError, match="zero or non-finite RMS"):
        generate_ess(_spec())


def test_smoke_fixture_golden_hashes_are_unchanged(tmp_path: Path) -> None:
    receipt = publish_offline_ess_artifact(tmp_path, "smoke", _load_development())
    assert receipt.wav_sha256 == "608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0"
    assert (
        receipt.metadata_sha256
        == "e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a"
    )
    assert (
        receipt.raw_float32_sha256
        == "eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca"
    )


def test_independent_high_precision_eight_sample_reference_vector() -> None:
    data = _spec_data()
    data.update(
        {
            "sample_rate_hz": 10,
            "start_frequency_hz": 1.0,
            "end_frequency_hz": 4.0,
            "sweep_duration_s": 0.8,
            "pre_silence_s": 0.0,
            "post_silence_s": 0.0,
            "fade_in_s": 0.0,
            "fade_out_s": 0.0,
            "digital_peak_dbfs": 0.0,
        }
    )
    spec = EssSignalSpec.model_validate(data)
    times = np.arange(8, dtype=np.float64) / 10.0
    expected_phase = np.array(
        [
            0.0,
            0.6860438292707576,
            1.5018920322432546,
            2.472104519980332,
            3.625888113461755,
            4.99797577200327,
            6.629672177948264,
            8.57009715342242,
        ],
        dtype=np.float64,
    )
    expected_frequency = np.array(
        [
            1.0,
            1.189207115002721,
            1.4142135623730951,
            1.681792830507429,
            2.0,
            2.378414230005442,
            2.8284271247461903,
            3.363585661014858,
        ],
        dtype=np.float64,
    )
    expected_float32 = np.array(
        [
            0.0,
            0.6349878311157227,
            1.0,
            0.6220608353614807,
            -0.46669238805770874,
            -0.9617787599563599,
            0.34040331840515137,
            0.7561557292938232,
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(theoretical_phase(spec, times), expected_phase, rtol=1e-15)
    np.testing.assert_allclose(
        [theoretical_frequency(spec, float(time)) for time in times],
        expected_frequency,
        rtol=1e-15,
    )
    result = generate_ess(spec)
    assert np.array_equal(result.samples[0], expected_float32)
    assert result.raw_float32_sha256 == (
        "32b08516c8f9b2d40942764e607077cdc42d638a759318d3bf6534ae5d6d6a68"
    )


def test_formal_cli_rejection_lists_six_fields_and_creates_no_root(
    tmp_path: Path,
) -> None:
    development_root = tmp_path / "formal-must-not-exist"
    with pytest.raises(MissingEssFieldsError) as caught:
        cli.main(
            [
                "ess-generate-offline",
                "--project-root",
                str(REPO_ROOT),
                "--audio-config",
                "config/audio/default_1x1_ess.yaml",
                "--development-root",
                str(development_root),
                "--artifact-id",
                "formal_rejected",
            ]
        )
    for field in (
        "ess_duration_s",
        "pre_silence_s",
        "post_silence_s",
        "ess_fade_in_s",
        "ess_fade_out_s",
        "ess_digital_peak_dbfs",
    ):
        assert field in str(caught.value)
    assert not development_root.exists()
