"""Strict development-only measurement-matrix specification loading."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from acoustic_ladder.config.bundle import canonical_json_bytes, load_config
from acoustic_ladder.config.models import AnalysisConfig
from acoustic_ladder.config.yaml_loader import load_yaml_mapping
from acoustic_ladder.domain.paths import validate_relative_path

FEATURE_IDS = (
    "raw_complex_additive_symmetric_relative_l2",
    "aligned_complex_additive_symmetric_relative_l2",
    "raw_magnitude_difference_rms_db",
    "aligned_magnitude_difference_rms_db",
    "raw_magnitude_difference_maximum_absolute_db",
    "aligned_magnitude_difference_maximum_absolute_db",
    "raw_phase_difference_rms_rad",
    "aligned_phase_difference_rms_rad",
    "raw_phase_difference_maximum_absolute_rad",
    "aligned_phase_difference_maximum_absolute_rad",
    "raw_ir_difference_symmetric_nrmse",
    "aligned_ir_difference_symmetric_nrmse",
    "raw_ir_difference_absolute_peak",
    "aligned_ir_difference_absolute_peak",
    "raw_ir_difference_peak_index",
    "aligned_ir_difference_peak_index",
)
SPLIT_STRATEGIES = ("leave_one_session_out", "leave_one_reassembly_out")


class AnalysisSpecError(ValueError):
    """Raised when a development analysis spec is unsafe or differs from its source."""


class DevelopmentAnalysisMatrixSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    schema_version: Literal["1.0.0"]
    matrix_schema_version: Literal["1.0.0"]
    spec_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    analysis_config_reference: str
    analysis_config_raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_config_normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_origin: Literal["synthetic"]
    run_mode: Literal["development"]
    formal_analysis_config: Literal[False]
    analysis_lower_hz: float = Field(gt=0)
    analysis_upper_hz: float = Field(gt=0)
    smoothing_enabled: Literal[False]
    feature_ids: list[str]
    baseline_reference_policy: Literal["same_stage_session_reassembly_all_blk_leave_one_repeat_out"]
    split_strategies: list[Literal["leave_one_session_out", "leave_one_reassembly_out"]]
    scalar_dtype: Literal["float64"]
    random_seed: None
    decision_thresholds: dict[str, float]
    model_id: None
    classification_pass_threshold: None
    day_group: None
    day_group_status: Literal["trusted_day_identity_unavailable"]
    formal_eligible: Literal[False]
    experimental_result: Literal[False]

    @model_validator(mode="after")
    def development_contract_is_fixed(self) -> DevelopmentAnalysisMatrixSpec:
        if self.analysis_lower_hz >= self.analysis_upper_hz:
            raise ValueError("analysis band must be ordered")
        if self.feature_ids != list(FEATURE_IDS):
            raise ValueError("feature_ids must match the versioned DEV-06.01 order")
        if self.split_strategies != list(SPLIT_STRATEGIES):
            raise ValueError("split_strategies must match the fixed grouped strategies")
        if self.decision_thresholds:
            raise ValueError("development analysis spec forbids decision thresholds")
        validate_relative_path(self.analysis_config_reference)
        return self


@dataclass(frozen=True)
class LoadedDevelopmentAnalysisMatrixSpec:
    model: DevelopmentAnalysisMatrixSpec
    source_path: Path
    project_root: Path
    original_bytes: bytes
    normalized_bytes: bytes
    raw_sha256: str
    normalized_sha256: str
    analysis_config_raw_sha256: str
    analysis_config_normalized_sha256: str


def load_development_analysis_matrix_spec(
    path: str | Path, *, project_root: str | Path
) -> LoadedDevelopmentAnalysisMatrixSpec:
    root = Path(project_root).resolve()
    source = Path(path).resolve()
    if not source.is_relative_to(root):
        raise AnalysisSpecError("analysis spec path is outside project root")
    raw = source.read_bytes()
    try:
        model = DevelopmentAnalysisMatrixSpec.model_validate(load_yaml_mapping(source))
    except (OSError, ValueError, ValidationError) as exc:
        raise AnalysisSpecError(f"invalid development analysis spec: {exc}") from exc
    analysis_path = (root / model.analysis_config_reference).resolve()
    if not analysis_path.is_relative_to(root):
        raise AnalysisSpecError("analysis config path escapes project root")
    try:
        loaded_analysis = load_config("analysis", analysis_path, project_root=root)
    except Exception as exc:
        raise AnalysisSpecError(f"cannot validate source analysis config: {exc}") from exc
    if not isinstance(loaded_analysis.model, AnalysisConfig):
        raise AnalysisSpecError("source analysis config has the wrong model")
    actual_raw = hashlib.sha256(loaded_analysis.original_bytes).hexdigest()
    actual_normalized = hashlib.sha256(loaded_analysis.normalized_bytes).hexdigest()
    if (
        model.analysis_config_raw_sha256 != actual_raw
        or model.analysis_config_normalized_sha256 != actual_normalized
    ):
        raise AnalysisSpecError("analysis config provenance differs from the development spec")
    analysis = loaded_analysis.model
    if (
        analysis.smoothing.enabled
        or analysis.baseline_selection_rule is not None
        or analysis.features is not None
        or analysis.normalization is not None
        or analysis.cross_validation_strategy is not None
        or analysis.random_seed is not None
        or any(value is not None for value in analysis.decision_gates.model_dump().values())
    ):
        raise AnalysisSpecError("source analysis config contains forbidden decided analysis state")
    if (
        model.analysis_lower_hz != analysis.analysis_band.lower_hz
        or model.analysis_upper_hz != analysis.analysis_band.upper_hz
    ):
        raise AnalysisSpecError("development analysis band differs from source analysis config")
    normalized = canonical_json_bytes(model.model_dump(mode="json"))
    return LoadedDevelopmentAnalysisMatrixSpec(
        model=model,
        source_path=source,
        project_root=root,
        original_bytes=raw,
        normalized_bytes=normalized,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        analysis_config_raw_sha256=actual_raw,
        analysis_config_normalized_sha256=actual_normalized,
    )


__all__ = [
    "FEATURE_IDS",
    "SPLIT_STRATEGIES",
    "AnalysisSpecError",
    "DevelopmentAnalysisMatrixSpec",
    "LoadedDevelopmentAnalysisMatrixSpec",
    "load_development_analysis_matrix_spec",
]
