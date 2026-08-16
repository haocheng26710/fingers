"""Semantic audit closure for the persisted DEV-03.02 audio context bundle."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder.audio.models import (
    AudioInventoryCaptureContext,
    AudioInventorySnapshot,
    ContextualAudioPreflightReport,
    HardwareSetupRecord,
)
from acoustic_ladder.audio.persistence import (
    load_audio_artifact,
    verify_bytes_sidecar,
)
from acoustic_ladder.audio.preflight import build_contextual_preflight_report
from acoustic_ladder.audio.summary import render_inventory_summary
from acoustic_ladder.domain.paths import validate_relative_path


@dataclass(frozen=True)
class AudioContextValidationReceipt:
    inventory_sha256: str
    context_sha256: str
    summary_sha256: str
    contextual_preflight_sha256: str
    hardware_setup_sha256: str


def validate_audio_context_bundle(
    *,
    inventory_path: str | Path,
    inventory_sidecar_path: str | Path,
    context_path: str | Path,
    context_sidecar_path: str | Path,
    summary_path: str | Path,
    summary_sidecar_path: str | Path,
    contextual_preflight_path: str | Path,
    contextual_preflight_sidecar_path: str | Path,
    hardware_setup_path: str | Path,
    inventory_reference: str,
    context_reference: str,
    hardware_setup_reference: str,
) -> AudioContextValidationReceipt:
    """Verify hashes, references, and byte-exact deterministic reconstructions."""

    inventory_reference = validate_relative_path(inventory_reference)
    context_reference = validate_relative_path(context_reference)
    hardware_setup_reference = validate_relative_path(hardware_setup_reference)
    snapshot, inventory_digest = load_audio_artifact(
        inventory_path, inventory_sidecar_path, AudioInventorySnapshot
    )
    context, context_digest = load_audio_artifact(
        context_path, context_sidecar_path, AudioInventoryCaptureContext
    )
    summary_digest = verify_bytes_sidecar(summary_path, summary_sidecar_path)
    report, report_digest = load_audio_artifact(
        contextual_preflight_path,
        contextual_preflight_sidecar_path,
        ContextualAudioPreflightReport,
    )
    hardware_bytes = Path(hardware_setup_path).read_bytes()
    try:
        hardware = HardwareSetupRecord.model_validate_json(hardware_bytes)
    except ValidationError as exc:
        raise ValueError(f"invalid hardware setup: {exc}") from exc
    hardware_digest = hashlib.sha256(hardware_bytes).hexdigest()
    if context.inventory_reference != inventory_reference:
        raise ValueError("capture context inventory reference does not match")
    if context.inventory_sha256 != inventory_digest:
        raise ValueError("capture context inventory SHA256 does not match inventory")
    expected_references = (
        (report.inventory_reference, inventory_reference, "inventory"),
        (report.capture_context_reference, context_reference, "capture context"),
        (report.hardware_setup_reference, hardware_setup_reference, "hardware setup"),
    )
    for recorded, expected, label in expected_references:
        validate_relative_path(recorded)
        if recorded != expected:
            raise ValueError(f"contextual preflight {label} reference does not match")
    expected_hashes = (
        (report.inventory_sha256, inventory_digest, "inventory"),
        (report.capture_context_sha256, context_digest, "capture context"),
        (report.hardware_setup_sha256, hardware_digest, "hardware setup"),
    )
    for recorded, expected, label in expected_hashes:
        if recorded != expected:
            raise ValueError(f"contextual preflight {label} SHA256 does not match")
    expected_summary = render_inventory_summary(
        snapshot,
        inventory_reference=inventory_reference,
        inventory_sha256=inventory_digest,
        context=context,
        context_reference=context_reference,
        context_sha256=context_digest,
    )
    if Path(summary_path).read_bytes() != expected_summary:
        raise ValueError("audio inventory summary is not the byte-exact deterministic rendering")
    expected_report = build_contextual_preflight_report(
        snapshot,
        hardware,
        context,
        inventory_reference=inventory_reference,
        inventory_sha256=inventory_digest,
        capture_context_reference=context_reference,
        capture_context_sha256=context_digest,
        hardware_setup_reference=hardware_setup_reference,
        hardware_setup_sha256=hardware_digest,
        now=report.generated_at,
    )
    if report != expected_report:
        raise ValueError("contextual preflight is not the deterministic reconstructed model")
    return AudioContextValidationReceipt(
        inventory_sha256=inventory_digest,
        context_sha256=context_digest,
        summary_sha256=summary_digest,
        contextual_preflight_sha256=report_digest,
        hardware_setup_sha256=hardware_digest,
    )
