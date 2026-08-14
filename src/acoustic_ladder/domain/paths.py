"""Portable repository/session-relative path validation."""

from pathlib import PurePosixPath, PureWindowsPath


def validate_relative_path(value: str) -> str:
    """Reject absolute, traversal and empty persistent paths."""

    if not value or "\x00" in value:
        raise ValueError("path must be a non-empty relative path")
    portable = value.replace("\\", "/")
    if (
        portable.startswith("/")
        or PureWindowsPath(value).is_absolute()
        or PurePosixPath(portable).is_absolute()
    ):
        raise ValueError("absolute paths are forbidden in persistent records")
    parts = PurePosixPath(portable).parts
    if ".." in parts:
        raise ValueError("parent traversal is forbidden in persistent records")
    if any(part in {"", "."} for part in parts):
        raise ValueError("path contains an empty or current-directory component")
    return PurePosixPath(*parts).as_posix()
