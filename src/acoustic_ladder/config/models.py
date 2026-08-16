"""Pydantic v2 contracts for audio, protocol, analysis and synthetic configuration."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from acoustic_ladder.domain.models import LoadingDirection, RunMode
from acoustic_ladder.domain.paths import validate_relative_path


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConfigStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"


class AudioDeviceRef(StrictConfigModel):
    device_id: str | None
    device_name: str | None


class AudioChannel(StrictConfigModel):
    channel_index: int | None = Field(ge=0)
    role: Literal["TX_speaker", "RX_microphone", "diagnostic_reference"]


class AudioConfig(StrictConfigModel):
    schema_version: str
    config_id: str
    config_status: ConfigStatus
    run_mode: RunMode
    audio_backend: str | None
    hardware_setup_reference: str
    inventory_snapshot_reference: str | None
    input_candidate_device_index: int | None = Field(ge=0)
    output_candidate_device_index: int | None = Field(ge=0)
    host_api_candidate_index: int | None = Field(ge=0)
    operator_confirmation_status: Literal["needs_operator_confirmation", "confirmed"]
    output_device: AudioDeviceRef
    input_device: AudioDeviceRef
    output_channels: list[AudioChannel]
    input_channels: list[AudioChannel]
    sample_rate_hz: int = Field(gt=0)
    ess_start_frequency_hz: float = Field(gt=0)
    ess_end_frequency_hz: float = Field(gt=0)
    ess_duration_s: float | None = Field(gt=0)
    pre_silence_s: float | None = Field(ge=0)
    post_silence_s: float | None = Field(ge=0)
    output_gain_db: float | None
    input_gain_db: float | None
    hardware_ready: bool
    notes: list[str]

    @field_validator("hardware_setup_reference", "inventory_snapshot_reference")
    @classmethod
    def audio_references_are_relative(cls, value: str | None) -> str | None:
        return validate_relative_path(value) if value is not None else None

    @model_validator(mode="after")
    def validate_audio_contract(self) -> AudioConfig:
        if self.ess_start_frequency_hz >= self.ess_end_frequency_hz:
            raise ValueError("ess_start_frequency_hz must be below ess_end_frequency_hz")
        if self.ess_end_frequency_hz >= self.sample_rate_hz / 2:
            raise ValueError("ess_end_frequency_hz must be below Nyquist")
        roles = [channel.role for channel in self.output_channels + self.input_channels]
        if len(roles) != len(set(roles)):
            raise ValueError("audio channel roles must be unique")
        if self.run_mode is RunMode.FORMAL:
            if len(self.output_channels) != 1 or len(self.input_channels) != 1:
                raise ValueError(
                    "formal audio configuration requires exactly one output and one input"
                )
            if self.output_channels[0].role != "TX_speaker":
                raise ValueError("formal output role must be TX_speaker")
            if self.input_channels[0].role != "RX_microphone":
                raise ValueError("formal input role must be RX_microphone")
        readiness_values = (
            self.audio_backend,
            self.output_device.device_id,
            self.output_device.device_name,
            self.input_device.device_id,
            self.input_device.device_name,
            self.ess_duration_s,
            self.pre_silence_s,
            self.post_silence_s,
            self.output_gain_db,
            self.input_gain_db,
            self.inventory_snapshot_reference,
            self.input_candidate_device_index,
            self.output_candidate_device_index,
            self.host_api_candidate_index,
            *[channel.channel_index for channel in self.output_channels + self.input_channels],
        )
        if self.hardware_ready and any(value is None for value in readiness_values):
            raise ValueError("hardware_ready cannot be true while a hardware field is null")
        if self.hardware_ready and self.operator_confirmation_status != "confirmed":
            raise ValueError("hardware_ready requires operator confirmation")
        return self


class BoundaryConditions(StrictConfigModel):
    tx_near: Literal["speaker"]
    rx_near: Literal["microphone"]
    tx_far: Literal["closed"]
    rx_far: Literal["closed"]
    unselected_nodes: Literal["BLK"]


class StateDefinition(StrictConfigModel):
    state_id: str
    module_id: str
    state_type: str
    discrete_label: str | None
    continuous_value: float | None
    unit: str | None
    loading_direction: LoadingDirection
    proxy_state: bool
    notes: str | None

    @model_validator(mode="after")
    def value_and_unit_match(self) -> StateDefinition:
        if (self.continuous_value is None) != (self.unit is None):
            raise ValueError("continuous_value and unit must both be present or both be null")
        return self


class ProtocolConfig(StrictConfigModel):
    schema_version: str
    protocol_id: str
    protocol_version: str
    experiment_stage: Literal[1, 2, 3, 4]
    config_status: ConfigStatus
    execution_ready: bool
    device_manifest_reference: str
    device_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_mode: RunMode
    boundary_conditions: BoundaryConditions
    allowed_modules: list[str]
    selected_nodes: list[str] | None
    selection_source: Literal["operator_selection", "manifest_recommendation"]
    state_definitions: list[StateDefinition]
    continuous_labels: list[str] | None
    allowed_loading_directions: list[LoadingDirection]
    repeats: int | None = Field(gt=0)
    reassemblies: int | None = Field(gt=0)
    sessions: int | None = Field(gt=0)
    randomization_enabled: bool
    random_seed: int | None
    operator_confirmation_requirements: list[str]
    proxy_experiment: bool
    max_active_bridges: int | None = Field(gt=0)
    binary_node_count: int | None = Field(gt=0)
    state_labels: list[str]
    notes: list[str]

    @field_validator("device_manifest_reference")
    @classmethod
    def manifest_reference_is_relative(cls, value: str) -> str:
        return validate_relative_path(value)

    @model_validator(mode="after")
    def validate_protocol_draft(self) -> ProtocolConfig:
        if self.run_mode is not RunMode.FORMAL:
            raise ValueError("stage 1-4 protocol drafts must use formal run_mode")
        if self.execution_ready:
            raise ValueError("DEV-02.01 protocol drafts cannot be execution ready")
        if len(self.allowed_modules) != len(set(self.allowed_modules)):
            raise ValueError("allowed_modules cannot contain duplicates")
        if self.selected_nodes is not None and len(self.selected_nodes) != len(
            set(self.selected_nodes)
        ):
            raise ValueError("selected_nodes cannot contain duplicates")
        state_ids = [state.state_id for state in self.state_definitions]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("state definitions cannot contain duplicate state IDs")
        if self.experiment_stage == 1 and self.max_active_bridges != 1:
            raise ValueError("stage 1 requires max_active_bridges = 1")
        if self.experiment_stage == 2 and not self.proxy_experiment:
            raise ValueError("stage 2 must be marked as a proxy experiment")
        if self.experiment_stage == 3:
            if self.binary_node_count != 2:
                raise ValueError("stage 3 requires two binary nodes")
            if set(self.state_labels) != {"00", "10", "01", "11"}:
                raise ValueError("stage 3 must express 00, 10, 01 and 11")
        if self.experiment_stage == 4 and self.selection_source != "manifest_recommendation":
            raise ValueError("stage 4 must select nodes from the manifest recommendation")
        return self


class FrequencyBand(StrictConfigModel):
    lower_hz: float = Field(gt=0)
    upper_hz: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> FrequencyBand:
        if self.lower_hz >= self.upper_hz:
            raise ValueError("analysis lower_hz must be below upper_hz")
        return self


class SmoothingConfig(StrictConfigModel):
    enabled: bool
    method: str | None
    parameter: float | None

    @model_validator(mode="after")
    def disabled_has_no_parameters(self) -> SmoothingConfig:
        if not self.enabled and (self.method is not None or self.parameter is not None):
            raise ValueError("disabled smoothing must not invent method or parameter")
        return self


class DecisionGates(StrictConfigModel):
    qc_threshold: float | None
    effect_threshold: float | None
    drift_threshold: float | None
    classification_pass_threshold: float | None


class AnalysisConfig(StrictConfigModel):
    schema_version: str
    config_id: str
    config_status: ConfigStatus
    analysis_band: FrequencyBand
    smoothing: SmoothingConfig
    baseline_selection_rule: str | None
    features: list[str] | None
    normalization: str | None
    grouping_candidates: list[Literal["session", "reassembly", "day"]]
    cross_validation_strategy: str | None
    model_order: list[
        Literal["template_correlation", "ridge", "logistic_regression", "LDA", "random_forest"]
    ]
    random_seed: int | None
    decision_gates: DecisionGates
    notes: list[str]

    @field_validator("grouping_candidates", "model_order")
    @classmethod
    def list_values_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("configuration list values must be unique")
        return value


class SpeedOfSoundAssumption(StrictConfigModel):
    value_m_s: float = Field(gt=0)
    source: str
    assumption_not_measurement: Literal[True]


class SyntheticConfig(StrictConfigModel):
    schema_version: str
    config_id: str
    config_status: ConfigStatus
    generator_version: str
    random_seed: int
    sample_rate_hz: int = Field(gt=0)
    duration_s: float = Field(gt=0)
    speed_of_sound: SpeedOfSoundAssumption
    baseline_coupling: float = Field(ge=0)
    propagation_loss_per_m: float = Field(ge=0)
    module_effect_scale: float = Field(ge=0)
    noise_level: float = Field(ge=0)
    session_drift: float = Field(ge=0)
    reassembly_drift: float = Field(ge=0)
    output_channel_count: int = Field(gt=0)
    input_channel_count: int = Field(gt=0)
    output_dtype: Literal["float32", "float64"]
    notes: list[str]
    physical_limitations: list[str]


ConfigModel = AudioConfig | ProtocolConfig | AnalysisConfig | SyntheticConfig


def manifest_nodes(manifest: dict[str, object]) -> dict[str, float]:
    """Read node positions from a supplied manifest; no active positions are hardcoded."""

    try:
        architecture = manifest["architecture"]
        assert isinstance(architecture, dict)
        nodes = architecture["nodes"]
        assert isinstance(nodes, list)
        result: dict[str, float] = {}
        for node in nodes:
            assert isinstance(node, dict)
            position = node["position"]
            assert isinstance(position, dict)
            result[str(node["id"])] = float(position["value"])
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid manifest node structure: {exc}") from exc
    return result


def manifest_module_ids(manifest: dict[str, object]) -> set[str]:
    try:
        modules = manifest["modules"]
        assert isinstance(modules, list)
        return {str(module["id"]) for module in modules if isinstance(module, dict)}
    except (AssertionError, KeyError, TypeError) as exc:
        raise ValueError(f"invalid manifest module structure: {exc}") from exc


def resolve_protocol_against_manifest(
    protocol: ProtocolConfig, manifest: dict[str, object]
) -> ProtocolConfig:
    """Validate nodes/modules and resolve stage-four recommendations from the manifest."""

    nodes = manifest_nodes(manifest)
    modules = manifest_module_ids(manifest)
    unknown_modules = sorted(set(protocol.allowed_modules) - modules)
    if unknown_modules:
        raise ValueError(f"protocol contains modules absent from manifest: {unknown_modules}")
    state_modules = {state.module_id for state in protocol.state_definitions}
    unallowed_state_modules = sorted(state_modules - set(protocol.allowed_modules))
    if unallowed_state_modules:
        raise ValueError(
            "protocol state definitions use modules outside allowed_modules: "
            f"{unallowed_state_modules}"
        )
    selected = protocol.selected_nodes
    if protocol.experiment_stage == 4:
        try:
            stage_four = manifest["stage_four"]
            assert isinstance(stage_four, dict)
            recommendation = stage_four["recommended_nodes"]
            assert isinstance(recommendation, list)
            selected = [str(node) for node in recommendation]
        except (AssertionError, KeyError, TypeError) as exc:
            raise ValueError(f"invalid manifest stage-four recommendation: {exc}") from exc
    if selected is not None:
        if len(selected) != len(set(selected)):
            raise ValueError("resolved selected_nodes cannot contain duplicates")
        unknown_nodes = sorted(set(selected) - nodes.keys())
        if unknown_nodes:
            raise ValueError(f"protocol contains nodes absent from manifest: {unknown_nodes}")
    return protocol.model_copy(update={"selected_nodes": selected})
