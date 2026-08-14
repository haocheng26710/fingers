"""Small typed models shared by the package-ingestion modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

type JsonScalar = bool | int | float | str | None
type JsonValue = Any
type JsonObject = dict[str, Any]


@dataclass(frozen=True)
class SourceCandidate:
    """One candidate value and its field-level provenance."""

    value: JsonValue
    priority: int
    source_type: str
    source_filename: str
    locator: str
    parameter_kind: str
    unit: str | None
    confirmation_status: str


def measurement(value: JsonScalar, unit: str) -> JsonObject:
    """Represent a required measurement whose value may explicitly be null."""

    return {"value": value, "unit": unit}
