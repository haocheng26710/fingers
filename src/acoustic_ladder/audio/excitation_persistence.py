"""Create-only publication and strict validation for offline ESS artifact bundles."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from acoustic_ladder.audio.ess import GeneratedEss, generate_ess, raw_float32_bytes
from acoustic_ladder.audio.excitation_models import EssArtifactMetadata, EssSignalSpec
from acoustic_ladder.config.bundle import LoadedConfig, canonical_json_bytes
from acoustic_ladder.config.models import AudioConfig
from acoustic_ladder.storage.io import StorageError, sha256_bytes

WAV_NAME = "excitation.wav"
WAV_SIDECAR_NAME = "excitation.wav.sha256"
METADATA_NAME = "excitation.metadata.json"
METADATA_SIDECAR_NAME = "excitation.metadata.sha256"
SAFETY_MARKER: Literal["OFFLINE_GENERATION_ONLY_NOT_AUTHORIZED_FOR_PLAYBACK"] = (
    "OFFLINE_GENERATION_ONLY_NOT_AUTHORIZED_FOR_PLAYBACK"
)
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class EssArtifactError(StorageError):
    """Raised when an offline excitation artifact violates its storage contract."""


@dataclass(frozen=True)
class EssArtifactReceipt:
    artifact_root: Path
    artifact_id: str
    wav_sha256: str
    metadata_sha256: str
    raw_float32_sha256: str
    metadata: EssArtifactMetadata


def validate_artifact_id(artifact_id: str) -> str:
    if not _ARTIFACT_ID.fullmatch(artifact_id):
        raise EssArtifactError(
            "artifact_id must contain only ASCII letters, digits, hyphens, and underscores"
        )
    return artifact_id


def encode_ieee_float32_wav(samples: NDArray[np.float32], sample_rate_hz: int) -> bytes:
    """Encode canonical mono WAVE_FORMAT_IEEE_FLOAT bytes without metadata or timestamps."""

    if samples.dtype != np.float32 or samples.ndim != 2 or samples.shape[0] != 1:
        raise EssArtifactError("WAV input must have shape [1, n] and dtype float32")
    sample_bytes = samples[0].astype("<f4", copy=False).tobytes(order="C")
    frame_count = samples.shape[1]
    fmt = struct.pack("<HHIIHH", 3, 1, sample_rate_hz, sample_rate_hz * 4, 4, 32)
    fact = struct.pack("<I", frame_count)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"fact" + struct.pack("<I", len(fact)) + fact
    chunks += b"data" + struct.pack("<I", len(sample_bytes)) + sample_bytes
    return bytes(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)


def decode_ieee_float32_wav(payload: bytes) -> tuple[NDArray[np.float32], int]:
    """Strictly decode mono IEEE float32 WAV into channel-first samples."""

    if len(payload) < 12 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise EssArtifactError("invalid RIFF/WAVE header")
    if struct.unpack_from("<I", payload, 4)[0] != len(payload) - 8:
        raise EssArtifactError("WAV RIFF size does not match file length")
    offset = 12
    fmt: tuple[int, int, int, int, int, int] | None = None
    fact_count: int | None = None
    data: bytes | None = None
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise EssArtifactError("truncated WAV chunk header")
        chunk_id = payload[offset : offset + 4]
        size = struct.unpack_from("<I", payload, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(payload):
            raise EssArtifactError("truncated WAV chunk")
        chunk = payload[start:end]
        if chunk_id == b"fmt ":
            if fmt is not None or len(chunk) != 16:
                raise EssArtifactError("WAV must contain one canonical 16-byte fmt chunk")
            fmt = struct.unpack("<HHIIHH", chunk)
        elif chunk_id == b"fact":
            if fact_count is not None or len(chunk) != 4:
                raise EssArtifactError("WAV must contain one canonical fact chunk")
            fact_count = struct.unpack("<I", chunk)[0]
        elif chunk_id == b"data":
            if data is not None:
                raise EssArtifactError("WAV contains multiple data chunks")
            data = chunk
        else:
            raise EssArtifactError(f"unsupported WAV chunk: {chunk_id!r}")
        offset = end + (size % 2)
    if fmt is None or fact_count is None or data is None:
        raise EssArtifactError("WAV is missing fmt, fact, or data chunk")
    audio_format, channels, rate, byte_rate, block_align, bits = fmt
    if (audio_format, channels, byte_rate, block_align, bits) != (3, 1, rate * 4, 4, 32):
        raise EssArtifactError("WAV must be mono IEEE float32 with canonical layout")
    if len(data) % 4 or fact_count != len(data) // 4:
        raise EssArtifactError("WAV fact count or float32 data length is inconsistent")
    flat = np.frombuffer(data, dtype="<f4").astype(np.float32, copy=True)
    return np.ascontiguousarray(flat.reshape(1, -1)), rate


def _sidecar_bytes(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _verify_sidecar(path: Path, sidecar: Path) -> str:
    payload = path.read_bytes()
    digest = sha256_bytes(payload)
    try:
        words = sidecar.read_text(encoding="ascii").split()
    except (OSError, UnicodeError) as exc:
        raise EssArtifactError(f"cannot read sidecar {sidecar.name}: {exc}") from exc
    if words != [digest, path.name]:
        raise EssArtifactError(f"invalid SHA256 sidecar for {path.name}")
    return digest


def _write_staged(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _metadata(
    *,
    artifact_id: str,
    loaded: LoadedConfig,
    spec: EssSignalSpec,
    generated: GeneratedEss,
    wav_sha256: str,
) -> EssArtifactMetadata:
    return EssArtifactMetadata(
        schema_version="1.0.0",
        artifact_id=artifact_id,
        artifact_origin=spec.artifact_origin,
        artifact_role=spec.artifact_role,
        algorithm_id=spec.algorithm_id,
        algorithm_version=spec.algorithm_version,
        source_audio_config_reference=loaded.snapshot.original_relative_path,
        source_audio_config_sha256=loaded.snapshot.original_sha256,
        source_audio_config_normalized_sha256=loaded.snapshot.normalized_sha256,
        spec=spec,
        sample_rate_hz=spec.sample_rate_hz,
        channel_count=1,
        dtype="float32",
        shape=(1, generated.timing.total_sample_count),
        timing=generated.timing,
        metrics=generated.metrics,
        raw_float32_sha256=generated.raw_float32_sha256,
        wav_sha256=wav_sha256,
        wav_writer="acoustic_ladder_ieee_float_wav",
        wav_writer_version="1.0.0",
        memory_layout="channel_first_c_contiguous",
        fade_window="half_cosine_inclusive_endpoints",
        sample_rounding="floor_seconds_times_rate_plus_0.5",
        playback_authorized=False,
        formal_eligible=False,
        experimental_result=False,
        hardware_ready=False,
        safety_marker=SAFETY_MARKER,
    )


def _validate_loaded_audio(loaded: LoadedConfig) -> AudioConfig:
    if loaded.kind != "audio" or not isinstance(loaded.model, AudioConfig):
        raise EssArtifactError("offline ESS validation requires a loaded audio configuration")
    return loaded.model


def validate_offline_ess_artifact(
    artifact_root: str | Path,
    loaded: LoadedConfig,
    spec: EssSignalSpec,
    *,
    require_directory_identity: bool = True,
) -> EssArtifactReceipt:
    """Read-only, cross-file validation including deterministic regeneration."""

    _validate_loaded_audio(loaded)
    root = Path(artifact_root)
    if not root.is_dir():
        raise EssArtifactError(f"artifact root is not a directory: {root}")
    expected_names = {WAV_NAME, WAV_SIDECAR_NAME, METADATA_NAME, METADATA_SIDECAR_NAME}
    actual_names = {entry.name for entry in root.iterdir()}
    if actual_names != expected_names:
        raise EssArtifactError(
            "artifact directory does not contain exactly the four required files"
        )
    wav_path = root / WAV_NAME
    metadata_path = root / METADATA_NAME
    wav_digest = _verify_sidecar(wav_path, root / WAV_SIDECAR_NAME)
    metadata_digest = _verify_sidecar(metadata_path, root / METADATA_SIDECAR_NAME)
    metadata_bytes = metadata_path.read_bytes()
    try:
        metadata = EssArtifactMetadata.model_validate_json(metadata_bytes)
    except ValueError as exc:
        raise EssArtifactError(f"invalid ESS metadata: {exc}") from exc
    if metadata_bytes != canonical_json_bytes(metadata.model_dump(mode="json")):
        raise EssArtifactError("ESS metadata is not canonical JSON")
    validate_artifact_id(metadata.artifact_id)
    if require_directory_identity and root.name != metadata.artifact_id:
        raise EssArtifactError("artifact directory name does not match metadata artifact_id")
    if metadata.source_audio_config_reference != loaded.snapshot.original_relative_path:
        raise EssArtifactError("metadata audio config reference does not match loaded config")
    if metadata.source_audio_config_sha256 != loaded.snapshot.original_sha256:
        raise EssArtifactError("metadata original audio config SHA256 does not match")
    if metadata.source_audio_config_normalized_sha256 != loaded.snapshot.normalized_sha256:
        raise EssArtifactError("metadata normalized audio config SHA256 does not match")
    if metadata.spec != spec:
        raise EssArtifactError("metadata ESS specification does not match loaded config")
    wav_bytes = wav_path.read_bytes()
    if metadata.wav_sha256 != wav_digest:
        raise EssArtifactError("metadata WAV SHA256 does not match WAV")
    samples, rate = decode_ieee_float32_wav(wav_bytes)
    if rate != spec.sample_rate_hz:
        raise EssArtifactError("WAV sample rate does not match ESS specification")
    regenerated = generate_ess(spec)
    if not np.array_equal(samples, regenerated.samples):
        raise EssArtifactError("WAV samples do not match deterministic ESS regeneration")
    if wav_bytes != encode_ieee_float32_wav(regenerated.samples, spec.sample_rate_hz):
        raise EssArtifactError("WAV bytes do not match the canonical writer output")
    if metadata.raw_float32_sha256 != hashlib.sha256(raw_float32_bytes(samples)).hexdigest():
        raise EssArtifactError("metadata raw float32 SHA256 does not match WAV samples")
    expected_metadata = _metadata(
        artifact_id=metadata.artifact_id,
        loaded=loaded,
        spec=spec,
        generated=regenerated,
        wav_sha256=wav_digest,
    )
    if metadata != expected_metadata:
        raise EssArtifactError("metadata derived values do not match deterministic regeneration")
    return EssArtifactReceipt(
        artifact_root=root,
        artifact_id=metadata.artifact_id,
        wav_sha256=wav_digest,
        metadata_sha256=metadata_digest,
        raw_float32_sha256=metadata.raw_float32_sha256,
        metadata=metadata,
    )


def publish_offline_ess_artifact(
    development_root: str | Path,
    artifact_id: str,
    loaded: LoadedConfig,
    spec: EssSignalSpec,
) -> EssArtifactReceipt:
    """Stage, verify, and create-only publish a complete offline development bundle."""

    validate_artifact_id(artifact_id)
    _validate_loaded_audio(loaded)
    root = Path(development_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / artifact_id).resolve()
    if not target.is_relative_to(root) or target.parent != root:
        raise EssArtifactError("artifact path escapes the development root")
    if target.exists():
        raise EssArtifactError(f"immutable artifact directory already exists: {artifact_id}")
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact_id}.staging-", dir=root))
    published = False
    lock_path = root / f".{artifact_id}.publish.lock"
    lock_descriptor: int | None = None
    try:
        generated = generate_ess(spec)
        wav_bytes = encode_ieee_float32_wav(generated.samples, spec.sample_rate_hz)
        wav_digest = sha256_bytes(wav_bytes)
        metadata = _metadata(
            artifact_id=artifact_id,
            loaded=loaded,
            spec=spec,
            generated=generated,
            wav_sha256=wav_digest,
        )
        metadata_bytes = canonical_json_bytes(metadata.model_dump(mode="json"))
        metadata_digest = sha256_bytes(metadata_bytes)
        _write_staged(staging / WAV_NAME, wav_bytes)
        _write_staged(staging / WAV_SIDECAR_NAME, _sidecar_bytes(wav_digest, WAV_NAME))
        _write_staged(staging / METADATA_NAME, metadata_bytes)
        _write_staged(
            staging / METADATA_SIDECAR_NAME,
            _sidecar_bytes(metadata_digest, METADATA_NAME),
        )
        validate_offline_ess_artifact(staging, loaded, spec, require_directory_identity=False)
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        if target.exists():
            raise EssArtifactError(f"immutable artifact directory already exists: {artifact_id}")
        staging.rename(target)
        published = True
        receipt = validate_offline_ess_artifact(target, loaded, spec)
        return receipt
    except FileExistsError as exc:
        raise EssArtifactError(
            f"artifact publication is already in progress: {artifact_id}"
        ) from exc
    except OSError as exc:
        raise EssArtifactError(f"could not publish offline ESS artifact: {exc}") from exc
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
            lock_path.unlink(missing_ok=True)
        if not published and staging.exists():
            shutil.rmtree(staging)
