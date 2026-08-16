"""Create-only persistence and hash verification for audio artifacts."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError

from acoustic_ladder.audio.errors import AudioPersistenceError
from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes, sha256_bytes


def persist_audio_artifact(path: str | Path, sidecar: str | Path, model: BaseModel) -> str:
    payload = canonical_json_bytes(model.model_dump(mode="json"))
    return persist_bytes_with_sidecar(path, sidecar, payload)


def persist_bytes_with_sidecar(path: str | Path, sidecar: str | Path, payload: bytes) -> str:
    digest = sha256_bytes(payload)
    try:
        atomic_write_bytes(path, payload)
        atomic_write_bytes(sidecar, f"{digest}  {Path(path).name}\n".encode("ascii"))
    except StorageError as exc:
        raise AudioPersistenceError(str(exc)) from exc
    return digest


def verify_bytes_sidecar(path: str | Path, sidecar: str | Path) -> str:
    digest = sha256_bytes(Path(path).read_bytes())
    words = Path(sidecar).read_text(encoding="ascii").split()
    if not words or words[0].lower() != digest:
        raise AudioPersistenceError(f"SHA256 mismatch for {path}")
    return digest


def load_audio_artifact[AudioArtifact: BaseModel](
    path: str | Path, sidecar: str | Path, model_type: type[AudioArtifact]
) -> tuple[AudioArtifact, str]:
    payload = Path(path).read_bytes()
    digest = verify_bytes_sidecar(path, sidecar)
    try:
        return model_type.model_validate_json(payload), digest
    except ValidationError as exc:
        raise AudioPersistenceError(f"invalid audio artifact {path}: {exc}") from exc
