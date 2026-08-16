from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from acoustic_ladder.audio.backend import FakeInventoryBackend, RawRecord
from acoustic_ladder.audio.errors import AudioInventoryError
from acoustic_ladder.audio.inventory import collect_inventory

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def test_backend_construction_does_not_load_sounddevice() -> None:
    from acoustic_ladder.audio.backend import SoundDeviceInventoryBackend

    calls: list[str] = []

    def loader(name: str) -> object:
        calls.append(name)
        raise AssertionError("must remain lazy")

    SoundDeviceInventoryBackend(loader)
    assert calls == []


def test_sounddevice_format_error_is_recorded_as_unsupported() -> None:
    from acoustic_ladder.audio.backend import SoundDeviceInventoryBackend

    class Module:
        def check_input_settings(self, **values: object) -> None:
            del values
            raise RuntimeError("Invalid sample rate")

    backend = SoundDeviceInventoryBackend(lambda name: Module())
    supported, error_type, message = backend.check_format("input", 4, 1, 48000)
    assert supported is False
    assert error_type == "RuntimeError"
    assert message == "Invalid sample rate"


def test_host_api_is_normalized(fake_backend: FakeInventoryBackend) -> None:
    api = collect_inventory(fake_backend, now=NOW).host_apis[0]
    assert api.host_api_index == 0
    assert api.name == "Windows WASAPI"
    assert api.device_count == 3
    assert api.default_input_device_index == 0


def test_directional_devices_are_explicit(fake_backend: FakeInventoryBackend) -> None:
    devices = collect_inventory(fake_backend, now=NOW).devices
    assert (devices[0].supports_input, devices[0].supports_output) == (True, False)
    assert (devices[1].supports_input, devices[1].supports_output) == (False, True)
    assert (devices[2].supports_input, devices[2].supports_output) == (True, True)


def test_empty_device_list_is_rejected(raw_host_apis: Sequence[RawRecord]) -> None:
    backend = FakeInventoryBackend(host_apis=raw_host_apis, devices=[])
    with pytest.raises(AudioInventoryError, match="no devices"):
        collect_inventory(backend, now=NOW)


def test_empty_host_api_list_is_rejected(raw_devices: Sequence[RawRecord]) -> None:
    backend = FakeInventoryBackend(host_apis=[], devices=raw_devices)
    with pytest.raises(AudioInventoryError, match="no host APIs"):
        collect_inventory(backend, now=NOW)


def test_non_ascii_device_name_is_preserved(fake_backend: FakeInventoryBackend) -> None:
    assert collect_inventory(fake_backend, now=NOW).devices[0].name == "iMM-6C 麦克风"


def test_missing_latency_becomes_null_with_warning(
    raw_host_apis: Sequence[RawRecord], raw_devices: Sequence[RawRecord]
) -> None:
    changed = [dict(device) for device in raw_devices]
    changed[0].pop("default_low_input_latency")
    snapshot = collect_inventory(
        FakeInventoryBackend(host_apis=raw_host_apis, devices=changed), now=NOW
    )
    assert snapshot.devices[0].default_low_input_latency_s is None
    assert any("normalized to null" in warning for warning in snapshot.warnings)


def test_direction_without_channels_has_null_latency(fake_backend: FakeInventoryBackend) -> None:
    devices = collect_inventory(fake_backend, now=NOW).devices
    assert devices[0].default_low_output_latency_s is None
    assert devices[1].default_low_input_latency_s is None


@pytest.mark.parametrize(
    ("field", "value"), [("max_input_channels", -1), ("max_output_channels", -2)]
)
def test_negative_channel_count_is_rejected(
    raw_host_apis: Sequence[RawRecord],
    raw_devices: Sequence[RawRecord],
    field: str,
    value: int,
) -> None:
    changed = [dict(device) for device in raw_devices]
    changed[0][field] = value
    with pytest.raises(AudioInventoryError, match=field):
        collect_inventory(FakeInventoryBackend(host_apis=raw_host_apis, devices=changed), now=NOW)


@pytest.mark.parametrize("rate", [0, -1.0, "48000"])
def test_invalid_sample_rate_is_rejected(
    raw_host_apis: Sequence[RawRecord], raw_devices: Sequence[RawRecord], rate: object
) -> None:
    changed = [dict(device) for device in raw_devices]
    changed[0]["default_samplerate"] = rate
    with pytest.raises(AudioInventoryError, match="default_samplerate"):
        collect_inventory(FakeInventoryBackend(host_apis=raw_host_apis, devices=changed), now=NOW)


def test_unmapped_default_device_produces_clear_warning(
    raw_host_apis: Sequence[RawRecord], raw_devices: Sequence[RawRecord]
) -> None:
    backend = FakeInventoryBackend(
        host_apis=raw_host_apis, devices=raw_devices, default_input_index=99
    )
    snapshot = collect_inventory(backend, now=NOW)
    assert snapshot.default_input_device_index is None
    assert "default input device unavailable" in snapshot.warnings


def test_input_and_output_format_checks_are_separate(fake_backend: FakeInventoryBackend) -> None:
    results = collect_inventory(fake_backend, now=NOW).capability_results
    assert [(item.device_index, item.direction) for item in results] == [
        (0, "input"),
        (1, "output"),
        (2, "input"),
        (2, "output"),
    ]
    assert all(item.channels == 1 and item.sample_rate_hz == 48000 for item in results)
    assert results[-1].supported is False


def test_snapshot_indices_are_explicitly_ephemeral(fake_backend: FakeInventoryBackend) -> None:
    snapshot = collect_inventory(fake_backend, now=NOW)
    assert {device.device_index_scope for device in snapshot.devices} == {
        "single_inventory_snapshot"
    }


def test_snapshot_timestamp_has_timezone(fake_backend: FakeInventoryBackend) -> None:
    assert collect_inventory(fake_backend, now=NOW).captured_at.utcoffset() is not None


def test_naive_timestamp_is_rejected(fake_backend: FakeInventoryBackend) -> None:
    with pytest.raises(AudioInventoryError, match="timezone-aware"):
        collect_inventory(fake_backend, now=datetime(2026, 8, 16))


def test_snapshot_contains_no_identity_or_absolute_path(fake_backend: FakeInventoryBackend) -> None:
    payload = collect_inventory(fake_backend, now=NOW).model_dump_json().casefold()
    assert "username" not in payload
    assert "hostname" not in payload
    assert ":\\users\\" not in payload
    assert "c:/users/" not in payload


def test_device_name_absolute_path_is_redacted(
    raw_host_apis: Sequence[RawRecord], raw_devices: Sequence[RawRecord]
) -> None:
    changed = [dict(device) for device in raw_devices]
    changed[0]["name"] = r"Microphone C:\Users\Alice\private"
    snapshot = collect_inventory(
        FakeInventoryBackend(host_apis=raw_host_apis, devices=changed), now=NOW
    )
    assert snapshot.devices[0].name == "[REDACTED_DEVICE_NAME_CONTAINING_ABSOLUTE_PATH]"
    assert "Alice" not in snapshot.model_dump_json()


def test_bluetooth_user_suffix_is_redacted(
    raw_host_apis: Sequence[RawRecord], raw_devices: Sequence[RawRecord]
) -> None:
    changed = [dict(device) for device in raw_devices]
    changed[0]["name"] = "Endpoint (@System32\\drivers\\bthhfenum.sys; (Alice's Earphones))"
    snapshot = collect_inventory(
        FakeInventoryBackend(host_apis=raw_host_apis, devices=changed), now=NOW
    )
    assert "Alice" not in snapshot.devices[0].name
    assert "REDACTED_USER_DEFINED_DEVICE_NAME" in snapshot.devices[0].name
