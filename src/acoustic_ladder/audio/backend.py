"""Lazy, read-only adapters for audio host API and device metadata."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, cast

from acoustic_ladder.audio.errors import (
    AudioBackendQueryError,
    AudioBackendUnavailable,
)
from acoustic_ladder.audio.models import Direction

RawRecord = Mapping[str, object]


class InventoryBackend(Protocol):
    def backend_version(self) -> str: ...

    def portaudio_version(self) -> tuple[int, str]: ...

    def query_host_apis(self) -> Sequence[RawRecord]: ...

    def query_devices(self) -> Sequence[RawRecord]: ...

    def query_default_device(self, direction: Direction) -> RawRecord | None: ...

    def check_format(
        self, direction: Direction, device_index: int, channels: int, sample_rate_hz: int
    ) -> tuple[bool, str | None, str | None]: ...


class _SoundDeviceModule(Protocol):
    __version__: str

    def get_portaudio_version(self) -> tuple[int, str]: ...

    def query_hostapis(self) -> Sequence[RawRecord]: ...

    def query_devices(self, device: object = None, kind: str | None = None) -> object: ...

    def check_input_settings(
        self, *, device: int, channels: int, dtype: str, samplerate: int
    ) -> None: ...

    def check_output_settings(
        self, *, device: int, channels: int, dtype: str, samplerate: int
    ) -> None: ...


class SoundDeviceInventoryBackend:
    """Expose only metadata enumeration and non-streaming format checks."""

    def __init__(self, module_loader: Callable[[str], object] = importlib.import_module) -> None:
        self._module_loader = module_loader
        self._module: _SoundDeviceModule | None = None

    def _sounddevice(self) -> _SoundDeviceModule:
        if self._module is None:
            try:
                loaded = self._module_loader("sounddevice")
            except (ImportError, OSError) as exc:
                raise AudioBackendUnavailable(f"sounddevice unavailable: {exc}") from exc
            self._module = cast(_SoundDeviceModule, loaded)
        return self._module

    def backend_version(self) -> str:
        return str(self._sounddevice().__version__)

    def portaudio_version(self) -> tuple[int, str]:
        try:
            number, text = self._sounddevice().get_portaudio_version()
            return int(number), str(text)
        except Exception as exc:
            raise AudioBackendQueryError(f"PortAudio version query failed: {exc}") from exc

    def query_host_apis(self) -> Sequence[RawRecord]:
        try:
            return self._sounddevice().query_hostapis()
        except Exception as exc:
            raise AudioBackendQueryError(f"host API enumeration failed: {exc}") from exc

    def query_devices(self) -> Sequence[RawRecord]:
        try:
            result = self._sounddevice().query_devices()
        except Exception as exc:
            raise AudioBackendQueryError(f"device enumeration failed: {exc}") from exc
        if not isinstance(result, Sequence):
            raise AudioBackendQueryError("device enumeration did not return a sequence")
        return cast(Sequence[RawRecord], result)

    def query_default_device(self, direction: Direction) -> RawRecord | None:
        try:
            result = self._sounddevice().query_devices(kind=direction)
        except Exception:
            return None
        return cast(RawRecord, result) if isinstance(result, Mapping) else None

    def check_format(
        self, direction: Direction, device_index: int, channels: int, sample_rate_hz: int
    ) -> tuple[bool, str | None, str | None]:
        try:
            if direction == "input":
                self._sounddevice().check_input_settings(
                    device=device_index,
                    channels=channels,
                    dtype="float32",
                    samplerate=sample_rate_hz,
                )
            else:
                self._sounddevice().check_output_settings(
                    device=device_index,
                    channels=channels,
                    dtype="float32",
                    samplerate=sample_rate_hz,
                )
        except Exception as exc:
            return False, type(exc).__name__, str(exc)
        return True, None, None


class FakeInventoryBackend:
    """Deterministic backend for tests; it never imports or touches audio hardware."""

    def __init__(
        self,
        *,
        host_apis: Sequence[RawRecord],
        devices: Sequence[RawRecord],
        default_input_index: int | None = None,
        default_output_index: int | None = None,
        unsupported: set[tuple[Direction, int]] | None = None,
    ) -> None:
        self.host_apis = host_apis
        self.devices = devices
        self.default_input_index = default_input_index
        self.default_output_index = default_output_index
        self.unsupported = unsupported or set()

    def backend_version(self) -> str:
        return "fake-1.0"

    def portaudio_version(self) -> tuple[int, str]:
        return 190700, "PortAudio fake"

    def query_host_apis(self) -> Sequence[RawRecord]:
        return self.host_apis

    def query_devices(self) -> Sequence[RawRecord]:
        return self.devices

    def query_default_device(self, direction: Direction) -> RawRecord | None:
        index = self.default_input_index if direction == "input" else self.default_output_index
        if index is None or index < 0 or index >= len(self.devices):
            return None
        return self.devices[index]

    def check_format(
        self, direction: Direction, device_index: int, channels: int, sample_rate_hz: int
    ) -> tuple[bool, str | None, str | None]:
        del channels, sample_rate_hz
        if (direction, device_index) in self.unsupported:
            return False, "ValueError", "format unsupported by fake backend"
        return True, None, None
