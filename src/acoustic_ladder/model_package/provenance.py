"""Priority-aware field selection that never hides conflicting candidates."""

from __future__ import annotations

import json
from typing import Any

from acoustic_ladder.model_package.models import JsonObject, JsonValue, SourceCandidate


def source_reference(candidate: SourceCandidate) -> JsonObject:
    """Convert a source candidate to the manifest provenance shape."""

    return {
        "source_type": candidate.source_type,
        "source_filename": candidate.source_filename,
        "locator": candidate.locator,
        "parameter_kind": candidate.parameter_kind,
        "unit": candidate.unit,
        "confirmation_status": candidate.confirmation_status,
    }


def _stable(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def resolve_value(
    field: str, candidates: list[SourceCandidate]
) -> tuple[JsonValue, JsonObject | None]:
    """Choose the highest-priority candidate and return an explicit conflict if needed."""

    if not candidates:
        raise ValueError(f"No source candidates supplied for {field}")
    ordered = sorted(candidates, key=lambda item: item.priority)
    selected = ordered[0]
    alternatives = [item for item in ordered[1:] if _stable(item.value) != _stable(selected.value)]
    if not alternatives:
        return selected.value, None
    conflict: JsonObject = {
        "field": field,
        "resolution": "selected_by_declared_source_priority",
        "selected": {
            "value": selected.value,
            "priority": selected.priority,
            **source_reference(selected),
        },
        "alternatives": [
            {
                "value": item.value,
                "priority": item.priority,
                **source_reference(item),
            }
            for item in alternatives
        ],
    }
    return selected.value, conflict


def ref(
    source_type: str,
    source_filename: str,
    locator: str,
    parameter_kind: str,
    unit: str | None,
    confirmation_status: str,
) -> JsonObject:
    """Build a field provenance record without introducing a candidate value."""

    return {
        "source_type": source_type,
        "source_filename": source_filename,
        "locator": locator,
        "parameter_kind": parameter_kind,
        "unit": unit,
        "confirmation_status": confirmation_status,
    }


def json_compatible(value: Any) -> JsonValue:
    """Type-narrow data loaded from JSON after it has been parsed."""

    return value
