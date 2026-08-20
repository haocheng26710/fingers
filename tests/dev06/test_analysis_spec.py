from pathlib import Path

from acoustic_ladder.analysis.spec import load_development_analysis_matrix_spec

PROJECT_ROOT = Path(__file__).parents[2]


def test_development_analysis_spec_is_synthetic_threshold_free_and_source_bound() -> None:
    loaded = load_development_analysis_matrix_spec(
        PROJECT_ROOT / "config/analysis/development_measurement_matrix.yaml",
        project_root=PROJECT_ROOT,
    )

    assert loaded.model.data_origin == "synthetic"
    assert loaded.model.run_mode == "development"
    assert loaded.model.formal_analysis_config is False
    assert loaded.model.smoothing_enabled is False
    assert loaded.model.feature_ids == [
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
    ]
    assert loaded.model.split_strategies == [
        "leave_one_session_out",
        "leave_one_reassembly_out",
    ]
    assert loaded.model.random_seed is None
    assert loaded.model.decision_thresholds == {}
    assert loaded.model.model_id is None
    assert loaded.model.day_group_status == "trusted_day_identity_unavailable"
    assert loaded.analysis_config_raw_sha256 == loaded.model.analysis_config_raw_sha256
    assert (
        loaded.analysis_config_normalized_sha256 == loaded.model.analysis_config_normalized_sha256
    )
