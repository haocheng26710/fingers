"""Canonical JSON, safe paths and same-filesystem atomic no-overwrite writes."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.domain.paths import validate_relative_path


class StorageError(RuntimeError):
    """Base error for immutable storage operations."""


def safe_identifier(value: str, label: str) -> str:
    if not value or any(not (character.isalnum() or character in "-_.") for character in value):
        raise StorageError(f"{label} contains unsafe characters: {value!r}")
    if value in {".", ".."}:
        raise StorageError(f"{label} cannot be {value!r}")
    return value


def confined_path(root: str | Path, relative: str) -> Path:
    """Resolve a portable relative path and prove it remains inside root."""

    try:
        portable = validate_relative_path(relative)
    except ValueError as exc:
        raise StorageError(str(exc)) from exc
    resolved_root = Path(root).resolve()
    target = (resolved_root / Path(*portable.split("/"))).resolve()
    if not target.is_relative_to(resolved_root):
        raise StorageError(f"path escapes storage root: {relative}")
    return target


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Atomically publish a new file and fail if the destination already exists."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise StorageError(f"immutable target already exists: {target}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise StorageError(f"immutable target already exists: {target}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_json(path: str | Path, value: object) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))
