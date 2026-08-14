"""Safe YAML input with duplicate-key and custom-tag rejection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.constructor import ConstructorError, DuplicateKeyError
from ruamel.yaml.parser import ParserError
from ruamel.yaml.scanner import ScannerError


class ConfigYamlError(ValueError):
    """Raised for unsafe or malformed YAML."""


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    """Load a plain mapping with no duplicate keys or executable/custom tags."""

    yaml = YAML(typ="safe", pure=True)
    yaml.allow_duplicate_keys = False
    try:
        data: Any = yaml.load(Path(path).read_text(encoding="utf-8-sig"))
    except (
        OSError,
        UnicodeDecodeError,
        ConstructorError,
        DuplicateKeyError,
        ParserError,
        ScannerError,
    ) as exc:
        raise ConfigYamlError(f"cannot safely load YAML {path}: {exc}") from exc
    if not isinstance(data, dict) or any(not isinstance(key, str) for key in data):
        raise ConfigYamlError(f"YAML root must be a string-keyed mapping: {path}")
    return {str(key): value for key, value in data.items()}
