from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from acoustic_ladder.audio.backend import FakeInventoryBackend, RawRecord


@pytest.fixture
def raw_host_apis() -> Sequence[RawRecord]:
    return [
        {
            "name": "Windows WASAPI",
            "devices": [0, 1, 2],
            "default_input_device": 0,
            "default_output_device": 1,
        }
    ]


@pytest.fixture
def raw_devices() -> Sequence[RawRecord]:
    common: Mapping[str, object] = {
        "hostapi": 0,
        "default_samplerate": 48000.0,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.01,
        "default_high_input_latency": 0.02,
        "default_high_output_latency": 0.02,
    }
    return [
        {
            **common,
            "name": "iMM-6C 麦克风",
            "max_input_channels": 1,
            "max_output_channels": 0,
        },
        {
            **common,
            "name": "USB Audio Device Output",
            "max_input_channels": 0,
            "max_output_channels": 2,
        },
        {
            **common,
            "name": "Duplex Device",
            "max_input_channels": 2,
            "max_output_channels": 2,
        },
    ]


@pytest.fixture
def fake_backend(
    raw_host_apis: Sequence[RawRecord], raw_devices: Sequence[RawRecord]
) -> FakeInventoryBackend:
    return FakeInventoryBackend(
        host_apis=raw_host_apis,
        devices=raw_devices,
        default_input_index=0,
        default_output_index=1,
        unsupported={("output", 2)},
    )
