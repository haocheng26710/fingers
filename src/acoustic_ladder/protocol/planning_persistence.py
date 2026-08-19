"""Create-only development protocol-plan publication and read-only replay."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.protocol.planning import (
    LoadedDevelopmentProtocolPlanSpec,
    ProtocolPlanningError,
    compile_development_protocol_plan,
)
from acoustic_ladder.protocol.planning_models import (
    PLAN_SAFETY_MARKER,
    CompiledDevelopmentProtocolPlan,
    ProtocolPlanReceipt,
    ProtocolPlanRecord,
    PublishedDevelopmentProtocolPlan,
)
from acoustic_ladder.storage.io import StorageError, atomic_write_bytes

COMPLETE_NAME = "PROTOCOL_PLAN_COMPLETE"
COMPLETE_BYTES = b"complete\n"
PROTOCOL_PLAN_FILE_NAMES = frozenset(
    {
        "compiled_protocol_plan.json",
        "compiled_protocol_plan.sha256",
        "protocol_plan_receipt.json",
        "protocol_plan_receipt.sha256",
        "protocol_plan_metadata.json",
        "protocol_plan_record.json",
        COMPLETE_NAME,
    }
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


class ProtocolPlanPersistenceError(StorageError):
    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(message)
        self.published = published


def _identifier(value: str, label: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None or value in {".", ".."}:
        raise ProtocolPlanPersistenceError(
            f"{label} must be a safe ASCII identifier: {value!r}", published=False
        )
    return value


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


class DevelopmentProtocolPlanStore:
    """Narrow create-only store with no synthetic/real/session selection axis."""

    def __init__(self, development_plan_root: str | Path) -> None:
        self.root = Path(development_plan_root).resolve()

    def plan_path(self, plan_id: str) -> Path:
        _identifier(plan_id, "plan_id")
        target = (self.root / "plans" / f"plan_{plan_id}").resolve()
        if not target.is_relative_to(self.root) or target.parent != (self.root / "plans").resolve():
            raise ProtocolPlanPersistenceError(
                "plan path escapes development root", published=False
            )
        return target

    def publish(
        self,
        *,
        plan_id: str,
        payloads: dict[str, bytes],
        metadata_bytes: bytes,
        record_bytes: bytes,
    ) -> Path:
        required = {
            "compiled_protocol_plan.json",
            "compiled_protocol_plan.sha256",
            "protocol_plan_receipt.json",
            "protocol_plan_receipt.sha256",
        }
        if set(payloads) != required:
            raise ProtocolPlanPersistenceError(
                "protocol-plan payload set is not exact", published=False
            )
        target = self.plan_path(plan_id)
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ProtocolPlanPersistenceError(
                f"protocol plan already exists: {plan_id}", published=False
            )
        lock = parent / f".{plan_id}.publish.lock"
        descriptor: int | None = None
        staging: Path | None = None
        published = False
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            if target.exists():
                raise ProtocolPlanPersistenceError(
                    f"protocol plan already exists: {plan_id}", published=False
                )
            staging = Path(tempfile.mkdtemp(prefix=f".{plan_id}.staging-", dir=parent))
            for filename, payload in payloads.items():
                atomic_write_bytes(staging / filename, payload)
            atomic_write_bytes(staging / "protocol_plan_metadata.json", metadata_bytes)
            atomic_write_bytes(staging / "protocol_plan_record.json", record_bytes)
            atomic_write_bytes(staging / COMPLETE_NAME, COMPLETE_BYTES)
            os.rename(staging, target)
            published = True
            return target
        except FileExistsError as exc:
            raise ProtocolPlanPersistenceError(
                f"protocol plan publication is already in progress: {plan_id}", published=False
            ) from exc
        except ProtocolPlanPersistenceError:
            raise
        except Exception as exc:
            raise ProtocolPlanPersistenceError(str(exc), published=published) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)
            if not published and staging is not None and staging.exists():
                shutil.rmtree(staging)


def _receipt(plan: CompiledDevelopmentProtocolPlan, plan_sha256: str) -> ProtocolPlanReceipt:
    return ProtocolPlanReceipt(
        schema_version="1.0.0",
        compiler_algorithm_id=plan.compiler_algorithm_id,
        compiler_algorithm_version=plan.compiler_algorithm_version,
        plan_id=plan.plan_id,
        plan_spec_id=plan.plan_spec_id,
        plan_spec_reference=plan.plan_spec_reference,
        plan_spec_raw_sha256=plan.plan_spec_raw_sha256,
        plan_spec_normalized_sha256=plan.plan_spec_normalized_sha256,
        protocol_reference=plan.protocol_reference,
        protocol_raw_sha256=plan.protocol_raw_sha256,
        protocol_normalized_sha256=plan.protocol_normalized_sha256,
        protocol_id=plan.protocol_id,
        protocol_version=plan.protocol_version,
        experiment_stage=plan.experiment_stage,
        manifest_reference=plan.manifest_reference,
        manifest_sha256=plan.manifest_sha256,
        model_package_sha256=plan.model_package_sha256,
        bundle_content_sha256=plan.bundle_content_sha256,
        condition_count=plan.condition_count,
        planned_measurement_count=plan.planned_measurement_count,
        session_count=plan.session_count,
        reassemblies_per_session=plan.reassemblies_per_session,
        continuous_repeats_per_condition=plan.continuous_repeats_per_condition,
        randomization_enabled=plan.randomization_enabled,
        randomization_algorithm_id=plan.randomization_algorithm_id,
        randomization_algorithm_version=plan.randomization_algorithm_version,
        random_seed=plan.random_seed,
        condition_matrix_sha256=plan.condition_matrix_sha256,
        schedule_sha256=plan.schedule_sha256,
        compiled_plan_sha256=plan_sha256,
        all_node_states_complete=True,
        operator_confirmation_required=True,
        operator_confirmation_status="pending",
        development_fixture=True,
        protocol_execution_performed=False,
        hardware_io_performed=False,
        formal_eligible=False,
        experimental_result=False,
        safety_marker=PLAN_SAFETY_MARKER,
    )


def _metadata(receipt: ProtocolPlanReceipt, receipt_sha256: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "plan_id": receipt.plan_id,
        "experiment_stage": receipt.experiment_stage,
        "condition_count": receipt.condition_count,
        "planned_measurement_count": receipt.planned_measurement_count,
        "compiled_plan_sha256": receipt.compiled_plan_sha256,
        "receipt_sha256": receipt_sha256,
        "operator_confirmation_status": "pending",
        "protocol_execution_performed": False,
        "hardware_io_performed": False,
        "formal_eligible": False,
        "experimental_result": False,
        "safety_marker": PLAN_SAFETY_MARKER,
    }


def _record(
    receipt: ProtocolPlanReceipt, receipt_sha256: str, created_at: datetime
) -> ProtocolPlanRecord:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProtocolPlanPersistenceError("publisher time must be timezone-aware", published=False)
    return ProtocolPlanRecord(
        schema_version="1.0.0",
        plan_id=receipt.plan_id,
        plan_relative_path=f"plans/plan_{receipt.plan_id}",
        created_at=created_at,
        compiled_plan_sha256=receipt.compiled_plan_sha256,
        receipt_sha256=receipt_sha256,
        immutable_status="immutable",
        operator_confirmation_status="pending",
        protocol_execution_performed=False,
        hardware_io_performed=False,
        formal_eligible=False,
        experimental_result=False,
        safety_marker=PLAN_SAFETY_MARKER,
    )


def publish_development_protocol_plan(
    *,
    store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
    now: Callable[[], datetime],
) -> PublishedDevelopmentProtocolPlan:
    try:
        plan = compile_development_protocol_plan(bundle=bundle, spec=spec, plan_id=plan_id)
        plan_bytes = canonical_json_bytes(plan.model_dump(mode="json"))
        plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()
        receipt = _receipt(plan, plan_sha256)
        receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
        receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        metadata_bytes = canonical_json_bytes(_metadata(receipt, receipt_sha256))
        record = _record(receipt, receipt_sha256, now())
        record_bytes = canonical_json_bytes(record.model_dump(mode="json"))
        path = store.publish(
            plan_id=plan_id,
            payloads={
                "compiled_protocol_plan.json": plan_bytes,
                "compiled_protocol_plan.sha256": _sidecar(
                    plan_sha256, "compiled_protocol_plan.json"
                ),
                "protocol_plan_receipt.json": receipt_bytes,
                "protocol_plan_receipt.sha256": _sidecar(
                    receipt_sha256, "protocol_plan_receipt.json"
                ),
            },
            metadata_bytes=metadata_bytes,
            record_bytes=record_bytes,
        )
    except ProtocolPlanPersistenceError:
        raise
    except (ProtocolPlanningError, ValidationError, OSError, ValueError) as exc:
        raise ProtocolPlanPersistenceError(str(exc), published=False) from exc
    return PublishedDevelopmentProtocolPlan(
        plan_path=path,
        plan=plan,
        receipt=receipt,
        record=record,
        plan_sha256=plan_sha256,
        receipt_sha256=receipt_sha256,
    )


def _verify_sidecar(root: Path, filename: str, sidecar_name: str) -> str:
    payload = (root / filename).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if (root / sidecar_name).read_bytes() != _sidecar(digest, filename):
        raise ProtocolPlanPersistenceError(f"non-canonical sidecar: {sidecar_name}", published=True)
    return digest


def validate_development_protocol_plan(
    *,
    store: DevelopmentProtocolPlanStore,
    bundle: LoadedBundle,
    spec: LoadedDevelopmentProtocolPlanSpec,
    plan_id: str,
) -> PublishedDevelopmentProtocolPlan:
    root = store.plan_path(plan_id)
    try:
        if not root.is_dir() or {path.name for path in root.iterdir()} != PROTOCOL_PLAN_FILE_NAMES:
            raise ProtocolPlanPersistenceError(
                "protocol plan must contain exactly the seven-file envelope",
                published=root.exists(),
            )
        if (root / COMPLETE_NAME).read_bytes() != COMPLETE_BYTES:
            raise ProtocolPlanPersistenceError("non-canonical completion marker", published=True)
        plan_sha256 = _verify_sidecar(
            root, "compiled_protocol_plan.json", "compiled_protocol_plan.sha256"
        )
        receipt_sha256 = _verify_sidecar(
            root, "protocol_plan_receipt.json", "protocol_plan_receipt.sha256"
        )
        stored_plan = CompiledDevelopmentProtocolPlan.model_validate_json(
            (root / "compiled_protocol_plan.json").read_bytes()
        )
        stored_receipt = ProtocolPlanReceipt.model_validate_json(
            (root / "protocol_plan_receipt.json").read_bytes()
        )
        stored_record = ProtocolPlanRecord.model_validate_json(
            (root / "protocol_plan_record.json").read_bytes()
        )
        expected_plan = compile_development_protocol_plan(bundle=bundle, spec=spec, plan_id=plan_id)
        expected_plan_bytes = canonical_json_bytes(expected_plan.model_dump(mode="json"))
        expected_plan_sha256 = hashlib.sha256(expected_plan_bytes).hexdigest()
        expected_receipt = _receipt(expected_plan, expected_plan_sha256)
        expected_receipt_bytes = canonical_json_bytes(expected_receipt.model_dump(mode="json"))
        expected_receipt_sha256 = hashlib.sha256(expected_receipt_bytes).hexdigest()
        expected_metadata_bytes = canonical_json_bytes(
            _metadata(expected_receipt, expected_receipt_sha256)
        )
        expected_record = _record(
            expected_receipt, expected_receipt_sha256, stored_record.created_at
        )
        expected_record_bytes = canonical_json_bytes(expected_record.model_dump(mode="json"))
        comparisons = {
            "compiled_protocol_plan.json": expected_plan_bytes,
            "protocol_plan_receipt.json": expected_receipt_bytes,
            "protocol_plan_metadata.json": expected_metadata_bytes,
            "protocol_plan_record.json": expected_record_bytes,
        }
        for filename, expected in comparisons.items():
            if (root / filename).read_bytes() != expected:
                raise ProtocolPlanPersistenceError(
                    f"protocol plan replay mismatch: {filename}", published=True
                )
        if plan_sha256 != expected_plan_sha256 or receipt_sha256 != expected_receipt_sha256:
            raise ProtocolPlanPersistenceError("protocol plan digest mismatch", published=True)
        if stored_plan != expected_plan or stored_receipt != expected_receipt:
            raise ProtocolPlanPersistenceError("protocol plan semantic mismatch", published=True)
    except ProtocolPlanPersistenceError:
        raise
    except (OSError, ValidationError, ProtocolPlanningError, ValueError) as exc:
        raise ProtocolPlanPersistenceError(str(exc), published=root.exists()) from exc
    return PublishedDevelopmentProtocolPlan(
        plan_path=root,
        plan=stored_plan,
        receipt=stored_receipt,
        record=stored_record,
        plan_sha256=plan_sha256,
        receipt_sha256=receipt_sha256,
    )


__all__ = [
    "PROTOCOL_PLAN_FILE_NAMES",
    "DevelopmentProtocolPlanStore",
    "ProtocolPlanPersistenceError",
    "publish_development_protocol_plan",
    "validate_development_protocol_plan",
]
