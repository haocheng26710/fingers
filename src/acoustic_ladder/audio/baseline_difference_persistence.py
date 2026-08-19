"""Immutable publication and replay validation for synthetic baseline differences."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from acoustic_ladder.audio.baseline_difference import (
    BaselineDifferenceError,
    BaselineDifferenceKernelMember,
    ProvisionalBaselineDifferenceMetrics,
    ProvisionalBaselineDifferenceResult,
    compute_provisional_baseline_difference,
)
from acoustic_ladder.audio.baseline_difference_models import (
    BASELINE_DIFFERENCE_SAFETY_MARKER,
    BaselineDifferenceConditionBinding,
    BaselineDifferenceCreatedEvent,
    BaselineDifferenceRecord,
    BaselineDifferenceSourceProvenance,
    ProvisionalBaselineDifferenceReceipt,
    PublishedProvisionalBaselineDifference,
    RepeatabilitySourceIdentity,
    baseline_difference_state,
)
from acoustic_ladder.audio.condition_plan import (
    LoadedDevelopmentConditionPlan,
    load_development_condition_plan,
)
from acoustic_ladder.audio.conditioned_virtual_capture_models import (
    LoadedConditionedVirtualCaptureScenario,
)
from acoustic_ladder.audio.ess_processing_persistence import ARRAYS_NAME as PROCESSING_ARRAYS_NAME
from acoustic_ladder.audio.repeatability_models import (
    ConditionedProvisionalRepeatabilityReceipt,
    PublishedProvisionalRepeatability,
)
from acoustic_ladder.audio.repeatability_persistence import validate_provisional_repeatability
from acoustic_ladder.config.bundle import LoadedBundle, canonical_json_bytes
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.domain.models import DataOrigin
from acoustic_ladder.storage.io import StorageError, safe_identifier, sha256_bytes
from acoustic_ladder.storage.npz import deterministic_npz_bytes, load_deterministic_npz
from acoustic_ladder.storage.store import ImmutableSessionStore

CONDITION_BINDING_NAME = "condition_binding.json"
CONDITION_BINDING_SIDECAR = "condition_binding.sha256"
ARRAYS_NAME = "baseline_difference_arrays.npz"
ARRAYS_SIDECAR = "baseline_difference_arrays.npz.sha256"
METRICS_NAME = "baseline_difference_metrics.json"
METRICS_SIDECAR = "baseline_difference_metrics.sha256"
RECEIPT_NAME = "baseline_difference_receipt.json"
RECEIPT_SIDECAR = "baseline_difference_receipt.sha256"
METADATA_NAME = "baseline_difference_metadata.json"
RECORD_NAME = "baseline_difference_record.json"
COMPLETE_NAME = "BASELINE_DIFFERENCE_COMPLETE"
COMPLETE_BYTES = b"complete\n"
EVENT_NAME = "baseline_difference_created"
BASELINE_DIFFERENCE_FILE_NAMES = frozenset(
    {
        CONDITION_BINDING_NAME,
        CONDITION_BINDING_SIDECAR,
        ARRAYS_NAME,
        ARRAYS_SIDECAR,
        METRICS_NAME,
        METRICS_SIDECAR,
        RECEIPT_NAME,
        RECEIPT_SIDECAR,
        METADATA_NAME,
        RECORD_NAME,
        COMPLETE_NAME,
    }
)
_ASCII_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]+$")


class BaselineDifferencePersistenceError(StorageError):
    """Baseline-difference failure with explicit immutable publication state."""

    def __init__(self, message: str, *, published: bool) -> None:
        super().__init__(f"{message}; published={str(published).lower()}")
        self.published = published


@dataclass(frozen=True)
class _LoadedSource:
    published: PublishedProvisionalRepeatability
    receipt: ConditionedProvisionalRepeatabilityReceipt
    provenance: BaselineDifferenceSourceProvenance
    kernels: tuple[BaselineDifferenceKernelMember, ...]


@dataclass(frozen=True)
class _ComputedComparison:
    result: ProvisionalBaselineDifferenceResult
    baseline: _LoadedSource
    candidate: _LoadedSource
    binding: BaselineDifferenceConditionBinding


def _identifier(value: str, label: str) -> None:
    if _ASCII_IDENTIFIER.fullmatch(value) is None or value in {".", ".."}:
        raise BaselineDifferencePersistenceError(f"unsafe {label}: {value!r}", published=False)
    safe_identifier(value, label)


def _sidecar(digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("ascii")


def _analysis_gate(bundle: LoadedBundle) -> AnalysisConfig:
    loaded = bundle.configs.get("analysis")
    if loaded is None or not isinstance(loaded.model, AnalysisConfig):
        raise BaselineDifferencePersistenceError(
            "baseline difference requires an active AnalysisConfig", published=False
        )
    analysis = loaded.model
    forbidden = {
        "baseline_selection_rule": analysis.baseline_selection_rule,
        "features": analysis.features,
        "normalization": analysis.normalization,
        "cross_validation_strategy": analysis.cross_validation_strategy,
        "qc_threshold": analysis.decision_gates.qc_threshold,
        "effect_threshold": analysis.decision_gates.effect_threshold,
        "drift_threshold": analysis.decision_gates.drift_threshold,
        "classification_pass_threshold": analysis.decision_gates.classification_pass_threshold,
    }
    active = [name for name, value in forbidden.items() if value is not None]
    if analysis.smoothing.enabled:
        active.insert(0, "smoothing.enabled")
    if active:
        raise BaselineDifferencePersistenceError(
            f"baseline difference requires disabled/null AnalysisConfig fields: {active}",
            published=False,
        )
    normalized = canonical_json_bytes(analysis.model_dump(mode="json"))
    if normalized != loaded.normalized_bytes or sha256_bytes(normalized) != (
        loaded.snapshot.normalized_sha256
    ):
        raise BaselineDifferencePersistenceError(
            "active AnalysisConfig differs from normalized provenance", published=False
        )
    return analysis


def _current_plan(
    plan: LoadedDevelopmentConditionPlan, bundle: LoadedBundle
) -> LoadedDevelopmentConditionPlan:
    try:
        current = load_development_condition_plan(
            plan.source_path, project_root=plan.project_root, bundle=bundle
        )
    except (OSError, ValueError) as exc:
        raise BaselineDifferencePersistenceError(
            f"condition plan provenance cannot be reloaded: {exc}", published=False
        ) from exc
    if (
        current.original_bytes != plan.original_bytes
        or current.normalized_bytes != plan.normalized_bytes
        or current.original_sha256 != plan.original_sha256
        or current.normalized_sha256 != plan.normalized_sha256
    ):
        raise BaselineDifferencePersistenceError(
            "loaded condition plan differs from current source", published=False
        )
    return current


def _kernel_member(
    store: ImmutableSessionStore,
    session_id: str,
    member: object,
    measurement_order: int,
) -> BaselineDifferenceKernelMember:
    from acoustic_ladder.audio.repeatability_models import RepeatabilityMemberIdentity

    if not isinstance(member, RepeatabilityMemberIdentity):
        raise BaselineDifferencePersistenceError("invalid repeatability member", published=False)
    path = (
        store.session_path(DataOrigin.SYNTHETIC, session_id)
        / "processed"
        / f"run_{member.source_run_id}"
        / f"processing_{member.processing_id}"
        / PROCESSING_ARRAYS_NAME
    )
    try:
        arrays = load_deterministic_npz(path.read_bytes())
        return BaselineDifferenceKernelMember(
            measurement_order=measurement_order,
            frequency_hz=arrays["frequency_hz"],
            analysis_band_mask=arrays["analysis_band_mask"],
            transfer_raw_real=arrays["transfer_raw_real"],
            transfer_raw_imag=arrays["transfer_raw_imag"],
            transfer_aligned_real=arrays["transfer_aligned_real"],
            transfer_aligned_imag=arrays["transfer_aligned_imag"],
            ir_raw=arrays["ir_raw"],
            ir_aligned=arrays["ir_aligned"],
        )
    except (OSError, KeyError, ValueError) as exc:
        raise BaselineDifferencePersistenceError(
            f"cannot load validated processing arrays: {exc}", published=False
        ) from exc


def _load_source(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    ess_artifact_root: str | Path,
    session_id: str,
    source: RepeatabilitySourceIdentity,
) -> _LoadedSource:
    try:
        published = validate_provisional_repeatability(
            store=store,
            bundle=bundle,
            scenario=scenario,
            ess_artifact_root=ess_artifact_root,
            session_id=session_id,
            repeat_set_id=source.repeat_set_id,
            members=source.members,
        )
    except (OSError, ValueError, StorageError) as exc:
        raise BaselineDifferencePersistenceError(str(exc), published=False) from exc
    if not isinstance(published.receipt, ConditionedProvisionalRepeatabilityReceipt):
        raise BaselineDifferencePersistenceError(
            "baseline difference requires condition-aware repeatability evidence",
            published=False,
        )
    receipt = published.receipt
    provenance = BaselineDifferenceSourceProvenance(
        reassembly_id=receipt.reassembly_id,
        repeat_set_id=receipt.repeat_set_id,
        condition_id=receipt.condition_id,
        condition_role=receipt.condition_role,
        resolved_node_states=receipt.resolved_node_states,
        resolved_node_states_sha256=receipt.resolved_node_states_sha256,
        non_blk_node_count=receipt.non_blk_node_count,
        members=receipt.members,
        normalized_member_list_sha256=receipt.normalized_member_list_sha256,
        repeatability_metrics_sha256=published.metrics_sha256,
        repeatability_receipt_sha256=published.receipt_sha256,
    )
    kernels = tuple(
        _kernel_member(
            store,
            session_id,
            item.identity,
            item.measurement_order,
        )
        for item in receipt.members
    )
    return _LoadedSource(published, receipt, provenance, kernels)


def _compatibility_key(receipt: ConditionedProvisionalRepeatabilityReceipt) -> tuple[object, ...]:
    return (
        receipt.bundle_content_sha256,
        receipt.device_manifest_sha256,
        receipt.audio_config_reference,
        receipt.audio_config_raw_sha256,
        receipt.audio_config_normalized_sha256,
        receipt.analysis_config_reference,
        receipt.analysis_config_raw_sha256,
        receipt.analysis_config_normalized_sha256,
        receipt.virtual_scenario_reference,
        receipt.virtual_scenario_raw_sha256,
        receipt.virtual_scenario_normalized_sha256,
        receipt.source_ess_artifact_id,
        receipt.source_ess_metadata_sha256,
        receipt.source_ess_wav_sha256,
        receipt.source_ess_raw_float32_sha256,
        receipt.processing_schema_version,
        receipt.processing_algorithm_id,
        receipt.processing_algorithm_version,
        receipt.qc_schema_version,
        receipt.qc_algorithm_id,
        receipt.qc_algorithm_version,
        receipt.repeatability_algorithm_id,
        receipt.repeatability_algorithm_version,
        receipt.sample_rate_hz,
        receipt.transfer_fft_length,
        receipt.frequency_bin_count,
        receipt.ir_sample_count,
        receipt.analysis_band_bin_count,
        receipt.analysis_band_mask_sha256,
        receipt.protocol_id,
        receipt.condition_plan_id,
        receipt.condition_plan_reference,
        receipt.condition_plan_raw_sha256,
        receipt.condition_plan_normalized_sha256,
        receipt.source_protocol_reference,
        receipt.source_protocol_raw_sha256,
        receipt.source_protocol_normalized_sha256,
    )


def _compute(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    condition_plan: LoadedDevelopmentConditionPlan,
    ess_artifact_root: str | Path,
    session_id: str,
    comparison_id: str,
    source_a: RepeatabilitySourceIdentity,
    source_b: RepeatabilitySourceIdentity,
) -> _ComputedComparison:
    _identifier(session_id, "session_id")
    _identifier(comparison_id, "comparison_id")
    _analysis_gate(bundle)
    plan = _current_plan(condition_plan, bundle)
    first = _load_source(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        source=source_a,
    )
    second = _load_source(
        store=store,
        bundle=bundle,
        scenario=scenario,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        source=source_b,
    )
    if first.receipt.repeat_set_id == second.receipt.repeat_set_id:
        raise BaselineDifferencePersistenceError("source repeat sets must differ", published=False)
    if first.receipt.reassembly_id == second.receipt.reassembly_id:
        raise BaselineDifferencePersistenceError("source reassemblies must differ", published=False)
    first_runs = {member.identity.source_run_id for member in first.receipt.members}
    second_runs = {member.identity.source_run_id for member in second.receipt.members}
    if first_runs & second_runs:
        raise BaselineDifferencePersistenceError("source repeat sets share runs", published=False)
    if _compatibility_key(first.receipt) != _compatibility_key(second.receipt):
        raise BaselineDifferencePersistenceError(
            "source repeatability contexts are incompatible", published=False
        )
    if (
        first.receipt.condition_plan_raw_sha256 != plan.original_sha256
        or first.receipt.condition_plan_normalized_sha256 != plan.normalized_sha256
        or first.receipt.source_protocol_raw_sha256 != plan.source_protocol_raw_sha256
        or first.receipt.source_protocol_normalized_sha256 != plan.source_protocol_normalized_sha256
    ):
        raise BaselineDifferencePersistenceError(
            "source repeatability does not bind the selected condition plan", published=False
        )
    by_role = {first.receipt.condition_role: first, second.receipt.condition_role: second}
    if set(by_role) != {"all_blk_reference", "single_bridge_candidate"}:
        raise BaselineDifferencePersistenceError(
            "comparison requires exactly one all-BLK and one single-bridge source",
            published=False,
        )
    baseline = by_role["all_blk_reference"]
    candidate = by_role["single_bridge_candidate"]
    try:
        result = compute_provisional_baseline_difference(baseline.kernels, candidate.kernels)
    except (BaselineDifferenceError, ValidationError) as exc:
        raise BaselineDifferencePersistenceError(str(exc), published=False) from exc
    binding = BaselineDifferenceConditionBinding(
        schema_version="1.0.0",
        session_id=session_id,
        comparison_id=comparison_id,
        condition_plan_id=plan.model.condition_plan_id,
        condition_plan_reference=plan.original_relative_path,
        condition_plan_raw_sha256=plan.original_sha256,
        condition_plan_normalized_sha256=plan.normalized_sha256,
        source_protocol_reference=plan.source_protocol_reference,
        source_protocol_raw_sha256=plan.source_protocol_raw_sha256,
        source_protocol_normalized_sha256=plan.source_protocol_normalized_sha256,
        baseline_source=baseline.provenance,
        candidate_source=candidate.provenance,
        protocol_condition_binding_performed=True,
        protocol_execution_performed=False,
    )
    return _ComputedComparison(result, baseline, candidate, binding)


def _receipt(
    *,
    computed: _ComputedComparison,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    session_id: str,
    comparison_id: str,
    binding_sha256: str,
    arrays_sha256: str,
    metrics_sha256: str,
) -> ProvisionalBaselineDifferenceReceipt:
    source = computed.baseline.receipt
    mask = computed.result.arrays["analysis_band_mask"]
    mask_digest = sha256_bytes(np.ascontiguousarray(mask).tobytes(order="C"))
    return ProvisionalBaselineDifferenceReceipt(
        schema_version="1.0.0",
        algorithm_id="provisional_all_blk_baseline_complex_difference",
        algorithm_version="1.0.0",
        session_id=session_id,
        comparison_id=comparison_id,
        data_origin="synthetic",
        run_mode="development",
        baseline_source=computed.baseline.provenance,
        candidate_source=computed.candidate.provenance,
        condition_binding_sha256=binding_sha256,
        condition_plan_reference=computed.binding.condition_plan_reference,
        condition_plan_raw_sha256=computed.binding.condition_plan_raw_sha256,
        condition_plan_normalized_sha256=computed.binding.condition_plan_normalized_sha256,
        source_protocol_reference=computed.binding.source_protocol_reference,
        source_protocol_raw_sha256=computed.binding.source_protocol_raw_sha256,
        source_protocol_normalized_sha256=computed.binding.source_protocol_normalized_sha256,
        bundle_content_sha256=source.bundle_content_sha256,
        device_manifest_sha256=source.device_manifest_sha256,
        config_snapshots=bundle.receipt.snapshots,
        scenario_reference=scenario.original_relative_path,
        scenario_raw_sha256=scenario.original_sha256,
        scenario_normalized_sha256=scenario.normalized_sha256,
        source_ess_artifact_id=source.source_ess_artifact_id,
        source_ess_metadata_sha256=source.source_ess_metadata_sha256,
        source_ess_wav_sha256=source.source_ess_wav_sha256,
        source_ess_raw_float32_sha256=source.source_ess_raw_float32_sha256,
        sample_rate_hz=source.sample_rate_hz,
        transfer_fft_length=source.transfer_fft_length,
        frequency_bin_count=source.frequency_bin_count,
        ir_sample_count=source.ir_sample_count,
        analysis_band_bin_count=source.analysis_band_bin_count,
        analysis_band_mask_sha256=mask_digest,
        processing_algorithm_id=source.processing_algorithm_id,
        processing_algorithm_version=source.processing_algorithm_version,
        qc_algorithm_id=source.qc_algorithm_id,
        qc_algorithm_version=source.qc_algorithm_version,
        repeatability_algorithm_id=source.repeatability_algorithm_id,
        repeatability_algorithm_version=source.repeatability_algorithm_version,
        denominator_floor_formula_id=(
            "max_baseline_magnitude_times_float64_epsilon_times_frequency_count_or_tiny"
        ),
        denominator_floor=computed.result.denominator_floor,
        ratio_valid_bin_count=computed.result.ratio_valid_bin_count,
        ratio_invalid_bin_count=computed.result.ratio_invalid_bin_count,
        invalid_bin_output_policy="ratio_and_phase_zero_with_validity_masks",
        phase_unwrap_rule="unwrap_each_contiguous_valid_segment_without_crossing_gaps",
        arrays_sha256=arrays_sha256,
        metrics_sha256=metrics_sha256,
        **baseline_difference_state(),
        create_only=True,
        immutable=True,
        safety_marker=BASELINE_DIFFERENCE_SAFETY_MARKER,
    )


def _metadata(
    receipt: ProvisionalBaselineDifferenceReceipt, receipt_sha256: str
) -> dict[str, object]:
    return {
        **baseline_difference_state(),
        "data_origin": "synthetic",
        "run_mode": "development",
        "comparison_id": receipt.comparison_id,
        "condition_binding_sha256": receipt.condition_binding_sha256,
        "arrays_sha256": receipt.arrays_sha256,
        "metrics_sha256": receipt.metrics_sha256,
        "receipt_sha256": receipt_sha256,
        "safety_marker": BASELINE_DIFFERENCE_SAFETY_MARKER,
    }


def _target(store: ImmutableSessionStore, session_id: str, comparison_id: str) -> Path:
    return (
        store.session_path(DataOrigin.SYNTHETIC, session_id)
        / "processed"
        / "baseline_differences"
        / f"comparison_{comparison_id}"
    )


def publish_provisional_baseline_difference(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    condition_plan: LoadedDevelopmentConditionPlan,
    ess_artifact_root: str | Path,
    session_id: str,
    comparison_id: str,
    source_a: RepeatabilitySourceIdentity,
    source_b: RepeatabilitySourceIdentity,
    now: Callable[[], datetime],
) -> PublishedProvisionalBaselineDifference:
    """Validate both sources, derive roles, compute, and create-only publish."""

    computed = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=condition_plan,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        comparison_id=comparison_id,
        source_a=source_a,
        source_b=source_b,
    )
    binding_bytes = canonical_json_bytes(computed.binding.model_dump(mode="json"))
    binding_digest = sha256_bytes(binding_bytes)
    arrays_bytes = deterministic_npz_bytes(computed.result.arrays)
    arrays_digest = sha256_bytes(arrays_bytes)
    metrics_bytes = canonical_json_bytes(computed.result.metrics.model_dump(mode="json"))
    metrics_digest = sha256_bytes(metrics_bytes)
    receipt = _receipt(
        computed=computed,
        bundle=bundle,
        scenario=scenario,
        session_id=session_id,
        comparison_id=comparison_id,
        binding_sha256=binding_digest,
        arrays_sha256=arrays_digest,
        metrics_sha256=metrics_digest,
    )
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json"))
    receipt_digest = sha256_bytes(receipt_bytes)
    timestamp = now()
    record = BaselineDifferenceRecord(
        schema_version="1.0.0",
        session_id=session_id,
        comparison_id=comparison_id,
        created_at=timestamp,
        status="complete",
        condition_binding_sha256=binding_digest,
        arrays_sha256=arrays_digest,
        metrics_sha256=metrics_digest,
        receipt_sha256=receipt_digest,
        baseline_member_list_sha256=receipt.baseline_source.normalized_member_list_sha256,
        candidate_member_list_sha256=receipt.candidate_source.normalized_member_list_sha256,
        data_origin="synthetic",
        run_mode="development",
        **baseline_difference_state(),
        safety_marker=BASELINE_DIFFERENCE_SAFETY_MARKER,
    )
    record_bytes = canonical_json_bytes(record.model_dump(mode="json"))
    target = _target(store, session_id, comparison_id)
    try:
        path = store.create_synthetic_baseline_difference(
            session_id=session_id,
            comparison_id=comparison_id,
            artifact_payloads={
                CONDITION_BINDING_NAME: binding_bytes,
                CONDITION_BINDING_SIDECAR: _sidecar(binding_digest, CONDITION_BINDING_NAME),
                ARRAYS_NAME: arrays_bytes,
                ARRAYS_SIDECAR: _sidecar(arrays_digest, ARRAYS_NAME),
                METRICS_NAME: metrics_bytes,
                METRICS_SIDECAR: _sidecar(metrics_digest, METRICS_NAME),
                RECEIPT_NAME: receipt_bytes,
                RECEIPT_SIDECAR: _sidecar(receipt_digest, RECEIPT_NAME),
            },
            metadata=_metadata(receipt, receipt_digest),
            record=record,
        )
        store.append_event(
            DataOrigin.SYNTHETIC,
            session_id,
            EVENT_NAME,
            {
                "schema_version": "1.0.0",
                "comparison_id": comparison_id,
                "baseline_reassembly_id": receipt.baseline_source.reassembly_id,
                "baseline_repeat_set_id": receipt.baseline_source.repeat_set_id,
                "candidate_reassembly_id": receipt.candidate_source.reassembly_id,
                "candidate_repeat_set_id": receipt.candidate_source.repeat_set_id,
                "condition_binding_sha256": binding_digest,
                "arrays_sha256": arrays_digest,
                "metrics_sha256": metrics_digest,
                "receipt_sha256": receipt_digest,
                "record_sha256": sha256_bytes(record_bytes),
                "baseline_member_list_sha256": (
                    receipt.baseline_source.normalized_member_list_sha256
                ),
                "candidate_member_list_sha256": (
                    receipt.candidate_source.normalized_member_list_sha256
                ),
                "created_at": record.model_dump(mode="json")["created_at"],
            },
        )
    except Exception as exc:
        published = (target / COMPLETE_NAME).is_file()
        raise BaselineDifferencePersistenceError(str(exc), published=published) from exc
    return PublishedProvisionalBaselineDifference(
        path,
        computed.result.metrics,
        receipt,
        binding_digest,
        arrays_digest,
        metrics_digest,
        receipt_digest,
        timestamp,
    )


def _verify_sidecar(root: Path, filename: str, sidecar: str) -> str:
    try:
        payload = (root / filename).read_bytes()
        actual = (root / sidecar).read_bytes()
    except OSError as exc:
        raise BaselineDifferencePersistenceError(str(exc), published=True) from exc
    digest = sha256_bytes(payload)
    if actual != _sidecar(digest, filename):
        raise BaselineDifferencePersistenceError(
            f"invalid SHA256 sidecar for {filename}", published=True
        )
    return digest


def _validated_event(
    *,
    store: ImmutableSessionStore,
    session_id: str,
    comparison_id: str,
    record: BaselineDifferenceRecord,
    record_bytes: bytes,
    receipt: ProvisionalBaselineDifferenceReceipt,
) -> BaselineDifferenceCreatedEvent:
    events = store.session_path(DataOrigin.SYNTHETIC, session_id) / "events"
    matches: list[BaselineDifferenceCreatedEvent] = []
    for path in sorted(events.glob(f"*_{EVENT_NAME}.json")):
        try:
            raw = path.read_bytes()
            event = BaselineDifferenceCreatedEvent.model_validate_json(raw)
        except (OSError, ValidationError) as exc:
            raise BaselineDifferencePersistenceError(
                f"invalid {EVENT_NAME} event: {exc}", published=True
            ) from exc
        if raw != canonical_json_bytes(event.model_dump(mode="json")) or path.name != (
            f"{event.sequence:06d}_{EVENT_NAME}.json"
        ):
            raise BaselineDifferencePersistenceError(
                f"noncanonical {EVENT_NAME} event", published=True
            )
        if event.comparison_id == comparison_id:
            matches.append(event)
    if len(matches) != 1:
        raise BaselineDifferencePersistenceError(
            f"expected exactly one matching {EVENT_NAME} event", published=True
        )
    event = matches[0]
    expected = (
        event.session_id == session_id
        and event.data_origin == "synthetic"
        and event.created_at == record.created_at
        and event.baseline_reassembly_id == receipt.baseline_source.reassembly_id
        and event.baseline_repeat_set_id == receipt.baseline_source.repeat_set_id
        and event.candidate_reassembly_id == receipt.candidate_source.reassembly_id
        and event.candidate_repeat_set_id == receipt.candidate_source.repeat_set_id
        and event.condition_binding_sha256 == record.condition_binding_sha256
        and event.arrays_sha256 == record.arrays_sha256
        and event.metrics_sha256 == record.metrics_sha256
        and event.receipt_sha256 == record.receipt_sha256
        and event.record_sha256 == sha256_bytes(record_bytes)
        and event.baseline_member_list_sha256 == record.baseline_member_list_sha256
        and event.candidate_member_list_sha256 == record.candidate_member_list_sha256
    )
    if not expected:
        raise BaselineDifferencePersistenceError(
            f"{EVENT_NAME} event binding differs", published=True
        )
    return event


def validate_provisional_baseline_difference(
    *,
    store: ImmutableSessionStore,
    bundle: LoadedBundle,
    scenario: LoadedConditionedVirtualCaptureScenario,
    condition_plan: LoadedDevelopmentConditionPlan,
    ess_artifact_root: str | Path,
    session_id: str,
    comparison_id: str,
    source_a: RepeatabilitySourceIdentity,
    source_b: RepeatabilitySourceIdentity,
) -> PublishedProvisionalBaselineDifference:
    """Read-only byte and semantic replay of a completed comparison."""

    computed = _compute(
        store=store,
        bundle=bundle,
        scenario=scenario,
        condition_plan=condition_plan,
        ess_artifact_root=ess_artifact_root,
        session_id=session_id,
        comparison_id=comparison_id,
        source_a=source_a,
        source_b=source_b,
    )
    root = _target(store, session_id, comparison_id)
    if not root.is_dir() or {entry.name for entry in root.iterdir()} != (
        BASELINE_DIFFERENCE_FILE_NAMES
    ):
        raise BaselineDifferencePersistenceError(
            "baseline-difference directory does not contain exactly the required files",
            published=True,
        )
    binding_digest = _verify_sidecar(root, CONDITION_BINDING_NAME, CONDITION_BINDING_SIDECAR)
    arrays_digest = _verify_sidecar(root, ARRAYS_NAME, ARRAYS_SIDECAR)
    metrics_digest = _verify_sidecar(root, METRICS_NAME, METRICS_SIDECAR)
    receipt_digest = _verify_sidecar(root, RECEIPT_NAME, RECEIPT_SIDECAR)
    binding_bytes = (root / CONDITION_BINDING_NAME).read_bytes()
    arrays_bytes = (root / ARRAYS_NAME).read_bytes()
    metrics_bytes = (root / METRICS_NAME).read_bytes()
    receipt_bytes = (root / RECEIPT_NAME).read_bytes()
    record_bytes = (root / RECORD_NAME).read_bytes()
    try:
        binding = BaselineDifferenceConditionBinding.model_validate_json(binding_bytes)
        metrics = ProvisionalBaselineDifferenceMetrics.model_validate_json(metrics_bytes)
        receipt = ProvisionalBaselineDifferenceReceipt.model_validate_json(receipt_bytes)
        record = BaselineDifferenceRecord.model_validate_json(record_bytes)
    except ValidationError as exc:
        raise BaselineDifferencePersistenceError(str(exc), published=True) from exc
    for label, raw, model in (
        ("condition binding", binding_bytes, binding),
        ("metrics", metrics_bytes, metrics),
        ("receipt", receipt_bytes, receipt),
        ("record", record_bytes, record),
    ):
        if raw != canonical_json_bytes(model.model_dump(mode="json")):
            raise BaselineDifferencePersistenceError(
                f"baseline-difference {label} is not canonical", published=True
            )
    event = _validated_event(
        store=store,
        session_id=session_id,
        comparison_id=comparison_id,
        record=record,
        record_bytes=record_bytes,
        receipt=receipt,
    )
    expected_binding_bytes = canonical_json_bytes(computed.binding.model_dump(mode="json"))
    expected_binding_digest = sha256_bytes(expected_binding_bytes)
    expected_arrays_bytes = deterministic_npz_bytes(computed.result.arrays)
    expected_arrays_digest = sha256_bytes(expected_arrays_bytes)
    expected_metrics_bytes = canonical_json_bytes(computed.result.metrics.model_dump(mode="json"))
    expected_metrics_digest = sha256_bytes(expected_metrics_bytes)
    expected_receipt = _receipt(
        computed=computed,
        bundle=bundle,
        scenario=scenario,
        session_id=session_id,
        comparison_id=comparison_id,
        binding_sha256=expected_binding_digest,
        arrays_sha256=expected_arrays_digest,
        metrics_sha256=expected_metrics_digest,
    )
    expected_receipt_bytes = canonical_json_bytes(expected_receipt.model_dump(mode="json"))
    expected_receipt_digest = sha256_bytes(expected_receipt_bytes)
    expected_record = BaselineDifferenceRecord(
        schema_version="1.0.0",
        session_id=session_id,
        comparison_id=comparison_id,
        created_at=event.created_at,
        status="complete",
        condition_binding_sha256=expected_binding_digest,
        arrays_sha256=expected_arrays_digest,
        metrics_sha256=expected_metrics_digest,
        receipt_sha256=expected_receipt_digest,
        baseline_member_list_sha256=(
            expected_receipt.baseline_source.normalized_member_list_sha256
        ),
        candidate_member_list_sha256=(
            expected_receipt.candidate_source.normalized_member_list_sha256
        ),
        data_origin="synthetic",
        run_mode="development",
        **baseline_difference_state(),
        safety_marker=BASELINE_DIFFERENCE_SAFETY_MARKER,
    )
    expected_record_bytes = canonical_json_bytes(expected_record.model_dump(mode="json"))
    if binding != computed.binding or binding_bytes != expected_binding_bytes:
        raise BaselineDifferencePersistenceError(
            "condition binding differs from replay", published=True
        )
    if arrays_bytes != expected_arrays_bytes or arrays_digest != expected_arrays_digest:
        raise BaselineDifferencePersistenceError(
            "baseline-difference arrays differ", published=True
        )
    if metrics != computed.result.metrics or metrics_bytes != expected_metrics_bytes:
        raise BaselineDifferencePersistenceError(
            "baseline-difference metrics differ", published=True
        )
    if receipt != expected_receipt or receipt_bytes != expected_receipt_bytes:
        raise BaselineDifferencePersistenceError(
            "baseline-difference receipt differs", published=True
        )
    if record != expected_record or record_bytes != expected_record_bytes:
        raise BaselineDifferencePersistenceError(
            "baseline-difference record differs", published=True
        )
    if (root / METADATA_NAME).read_bytes() != canonical_json_bytes(
        _metadata(expected_receipt, expected_receipt_digest)
    ):
        raise BaselineDifferencePersistenceError(
            "baseline-difference metadata differs", published=True
        )
    if (
        binding_digest != expected_binding_digest
        or metrics_digest != expected_metrics_digest
        or receipt_digest != expected_receipt_digest
        or (root / COMPLETE_NAME).read_bytes() != COMPLETE_BYTES
    ):
        raise BaselineDifferencePersistenceError(
            "baseline-difference digest or completion contract differs", published=True
        )
    return PublishedProvisionalBaselineDifference(
        root,
        metrics,
        receipt,
        binding_digest,
        arrays_digest,
        metrics_digest,
        receipt_digest,
        event.created_at,
    )


__all__ = [
    "BASELINE_DIFFERENCE_FILE_NAMES",
    "BaselineDifferencePersistenceError",
    "publish_provisional_baseline_difference",
    "validate_provisional_baseline_difference",
]
