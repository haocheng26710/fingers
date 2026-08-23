from __future__ import annotations

import pytest

from tests.dev03.audio_api_guard import (
    assert_production_audio_api_guard,
    inspect_audio_api_calls,
)

PILOT_BACKEND = "src/acoustic_ladder/audio/pilot_capture_backends.py"


def _capture(
    body: str,
    *,
    class_name: str = "SoundDeviceFullDuplexBackend",
    method_name: str = "capture",
) -> str:
    indented = "\n".join(f"        {line}" for line in body.splitlines())
    return f"class {class_name}:\n    def {method_name}(self):\n{indented}\n"


def test_guard_allows_only_the_two_exact_pilot_capture_calls() -> None:
    result = inspect_audio_api_calls(
        {PILOT_BACKEND: _capture("module.Stream()\nfinished.wait(1.0)")}
    )

    assert result.violations == ()
    assert [(call.receiver, call.attribute) for call in result.allowed] == [
        ("module", "Stream"),
        ("finished", "wait"),
    ]


@pytest.mark.parametrize(
    ("path", "source", "attribute"),
    [
        ("src/acoustic_ladder/audio/other.py", _capture("module.Stream()"), "Stream"),
        (PILOT_BACKEND, _capture("other.Stream()"), "Stream"),
        (PILOT_BACKEND, _capture("module.Stream()", class_name="OtherBackend"), "Stream"),
        (PILOT_BACKEND, _capture("module.Stream()", method_name="other"), "Stream"),
        (PILOT_BACKEND, _capture("sounddevice.play()"), "play"),
        (PILOT_BACKEND, _capture("sounddevice.rec()"), "rec"),
        (PILOT_BACKEND, _capture("sounddevice.playrec()"), "playrec"),
        (PILOT_BACKEND, _capture("sounddevice.InputStream()"), "InputStream"),
        (PILOT_BACKEND, _capture("other.wait()"), "wait"),
    ],
)
def test_guard_rejects_calls_outside_the_exact_allowlist(
    path: str, source: str, attribute: str
) -> None:
    result = inspect_audio_api_calls({path: source})

    assert result.allowed == ()
    assert len(result.violations) == 1
    assert result.violations[0].attribute == attribute


@pytest.mark.parametrize(
    "attribute",
    ["RawStream", "OutputStream", "RawInputStream", "RawOutputStream"],
)
def test_guard_keeps_all_other_stream_constructors_globally_forbidden(
    attribute: str,
) -> None:
    result = inspect_audio_api_calls({PILOT_BACKEND: _capture(f"sounddevice.{attribute}()")})

    assert [call.attribute for call in result.violations] == [attribute]


def test_guard_diagnostic_reports_file_attribute_and_line() -> None:
    path = "src/acoustic_ladder/audio/unapproved.py"
    result = inspect_audio_api_calls({path: "\n\nsounddevice.play()\n"})

    assert result.violations[0].describe() == (
        "src/acoustic_ladder/audio/unapproved.py:3: forbidden audio API call sounddevice.play"
    )


def test_guard_count_mismatch_reports_each_authorized_location() -> None:
    source = _capture("module.Stream()\nmodule.Stream()\nfinished.wait(1.0)")

    with pytest.raises(AssertionError) as caught:
        assert_production_audio_api_guard({PILOT_BACKEND: source})

    message = str(caught.value)
    assert f"{PILOT_BACKEND}:3:" in message
    assert "module.Stream" in message
