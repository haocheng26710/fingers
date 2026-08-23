"""Atomic mutable recovery state for development-demo wizard sessions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from acoustic_ladder.config.bundle import canonical_json_bytes
from acoustic_ladder.ui.plans import DemoPlan


class DemoSessionStateError(RuntimeError):
    """Raised when mutable demo state cannot be safely read or written."""


def demo_plan_sha256(plan: DemoPlan) -> str:
    payload = {
        "conditions": [
            {
                "condition_id": condition.condition_id,
                "condition_label": condition.condition_label,
                "nodes": [
                    {"module_id": node.module_id, "node_id": node.node_id}
                    for node in condition.nodes
                ],
                "stage": condition.stage,
            }
            for condition in plan.conditions
        ],
        "mode": plan.mode,
        "repeat_count": plan.repeat_count,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


class DemoSessionStateStore:
    """Read and atomically replace one mutable `session_state.json`."""

    def __init__(self, session_root: Path) -> None:
        self.session_root = session_root
        self.path = session_root / "session_state.json"

    def write(self, payload: dict[str, object]) -> None:
        self.session_root.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".session_state.",
                suffix=".tmp",
                dir=self.session_root,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(canonical_json_bytes(payload))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except OSError as exc:
            raise DemoSessionStateError(f"could not update demo session state: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read(self) -> dict[str, object]:
        try:
            raw = self.path.read_bytes()
            value = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DemoSessionStateError(f"demo session state is unreadable: {exc}") from exc
        if not isinstance(value, dict):
            raise DemoSessionStateError("demo session state must be a JSON object")
        return value
