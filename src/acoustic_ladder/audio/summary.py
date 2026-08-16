"""Deterministic Markdown rendering from verified audio inventory models."""

from __future__ import annotations

from acoustic_ladder.audio.models import AudioInventoryCaptureContext, AudioInventorySnapshot


def _markdown_cell(value: object) -> str:
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\r", "<br>")
        .replace("\n", "<br>")
    )


def render_inventory_summary(
    snapshot: AudioInventorySnapshot,
    *,
    inventory_reference: str,
    inventory_sha256: str,
    context: AudioInventoryCaptureContext | None = None,
    context_reference: str | None = None,
    context_sha256: str | None = None,
) -> bytes:
    """Render names from the parsed model, never from console output."""

    if any("\ufffd" in device.name for device in snapshot.devices):
        raise ValueError("inventory contains U+FFFD and cannot be summarized")
    lines = [
        "# Audio inventory summary",
        "",
        f"- Inventory: `{_markdown_cell(inventory_reference)}`",
        f"- Inventory SHA256: `{inventory_sha256}`",
        f"- Captured at: `{snapshot.captured_at.isoformat()}`",
    ]
    if context is not None:
        if context_reference is None or context_sha256 is None:
            raise ValueError("context reference and SHA256 are required with context")
        if context.inventory_sha256 != inventory_sha256:
            raise ValueError("context does not reference the supplied inventory SHA256")
        lines.extend(
            [
                f"- Capture context: `{_markdown_cell(context_reference)}`",
                f"- Capture context SHA256: `{context_sha256}`",
                f"- Inventory role: `{context.inventory_role}`",
                "- Experimental input hardware connected: `false`",
                "- Experimental output hardware connected: `false`",
                "- Experimental fixture connected: `false`",
                f"- Device binding: `{context.candidate_binding_status}`",
                "",
                "> The experimental input, output and fixture were not connected during this "
                "capture. Existing endpoints are not experimental hardware and must not be bound.",
            ]
        )
    lines.extend(
        [
            "",
            "## Host APIs",
            "",
            "| Index | Name | Device count | Default input | Default output |",
            "|---:|---|---:|---:|---:|",
        ]
    )
    for host_api in snapshot.host_apis:
        lines.append(
            "| "
            f"{host_api.host_api_index} | {_markdown_cell(host_api.name)} | "
            f"{host_api.device_count} | {host_api.default_input_device_index} | "
            f"{host_api.default_output_device_index} |"
        )
    lines.extend(
        [
            "",
            "## Devices",
            "",
            "Device names below come directly from the verified inventory model.",
            "",
            "| Index | Host API | Device name | Input channels | Output channels |",
            "|---:|---|---|---:|---:|",
        ]
    )
    for device in snapshot.devices:
        lines.append(
            "| "
            f"{device.snapshot_device_index} | {_markdown_cell(device.host_api_name)} | "
            f"{_markdown_cell(device.name)} | {device.max_input_channels} | "
            f"{device.max_output_channels} |"
        )
    lines.extend(
        [
            "",
            "`NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED`",
            "",
        ]
    )
    rendered = "\n".join(lines)
    if "\ufffd" in rendered:
        raise ValueError("rendered summary contains U+FFFD")
    return rendered.encode("utf-8")
