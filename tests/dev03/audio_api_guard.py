from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass

_PILOT_BACKEND = "src/acoustic_ladder/audio/pilot_capture_backends.py"
_ALWAYS_FORBIDDEN = frozenset(
    {
        "play",
        "rec",
        "playrec",
        "RawStream",
        "InputStream",
        "OutputStream",
        "RawInputStream",
        "RawOutputStream",
    }
)


@dataclass(frozen=True)
class AudioApiCall:
    path: str
    line: int
    class_name: str | None
    function_name: str | None
    receiver: str | None
    attribute: str

    def describe(self) -> str:
        receiver = f"{self.receiver}." if self.receiver is not None else ""
        return f"{self.path}:{self.line}: forbidden audio API call {receiver}{self.attribute}"


@dataclass(frozen=True)
class AudioApiGuardResult:
    allowed: tuple[AudioApiCall, ...]
    violations: tuple[AudioApiCall, ...]


class _CallVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path.replace("\\", "/")
        self.class_name: str | None = None
        self.function_name: str | None = None
        self.allowed: list[AudioApiCall] = []
        self.violations: list[AudioApiCall] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        previous = self.class_name
        self.class_name = node.name
        self.generic_visit(node)
        self.class_name = previous

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.function_name
        self.function_name = node.name
        self.generic_visit(node)
        self.function_name = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        attribute: str | None = None
        receiver: str | None = None
        if isinstance(node.func, ast.Name):
            attribute = node.func.id
        elif isinstance(node.func, ast.Attribute):
            attribute = node.func.attr
            if isinstance(node.func.value, ast.Name):
                receiver = node.func.value.id
        if attribute is not None:
            call = AudioApiCall(
                path=self.path,
                line=node.lineno,
                class_name=self.class_name,
                function_name=self.function_name,
                receiver=receiver,
                attribute=attribute,
            )
            if self._is_authorized(call):
                self.allowed.append(call)
            elif attribute in _ALWAYS_FORBIDDEN or attribute in {"Stream", "wait"}:
                self.violations.append(call)
        self.generic_visit(node)

    @staticmethod
    def _is_authorized(call: AudioApiCall) -> bool:
        common = (
            call.path.endswith(_PILOT_BACKEND)
            and call.class_name == "SoundDeviceFullDuplexBackend"
            and call.function_name == "capture"
        )
        return common and (
            (call.receiver, call.attribute) == ("module", "Stream")
            or (call.receiver, call.attribute) == ("finished", "wait")
        )


def inspect_audio_api_calls(sources: Mapping[str, str]) -> AudioApiGuardResult:
    allowed: list[AudioApiCall] = []
    violations: list[AudioApiCall] = []
    for path, source in sorted(sources.items()):
        visitor = _CallVisitor(path)
        visitor.visit(ast.parse(source, filename=path))
        allowed.extend(visitor.allowed)
        violations.extend(visitor.violations)
    return AudioApiGuardResult(tuple(allowed), tuple(violations))


def assert_production_audio_api_guard(sources: Mapping[str, str]) -> None:
    result = inspect_audio_api_calls(sources)
    messages = [call.describe() for call in result.violations]
    allowed_points = [(call.receiver, call.attribute) for call in result.allowed]
    expected = [("module", "Stream"), ("finished", "wait")]
    if sorted(allowed_points) != sorted(expected):
        locations = [
            f"{call.path}:{call.line}: {call.receiver}.{call.attribute}" for call in result.allowed
        ]
        messages.append(
            "authorized audio API call count mismatch: "
            f"expected exactly {expected!r}, found {locations!r}"
        )
    assert not messages, "\n".join(messages)
