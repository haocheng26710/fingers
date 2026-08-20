import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from acoustic_ladder.analysis.models import (
    AnalysisMetadata,
    AnalysisReceipt,
    AnalysisRecord,
    provisional_state,
)
from acoustic_ladder.analysis.source_validation import (
    AnalysisSourceError,
    derive_latest_verified_execution_completion_utc,
)
from acoustic_ladder.config.bundle import canonical_json_bytes

EVIDENCE_TIME = datetime(2026, 8, 20, 11, 0, tzinfo=UTC)
TIME_BASIS = "latest_verified_execution_completion_utc"
SHA256 = "0" * 64


def test_receipt_binds_metadata_and_record_without_a_hash_cycle() -> None:
    state = provisional_state()
    common = {
        **state,
        "schema_version": "1.1.0",
        "analysis_id": "matrix",
        "analysis_evidence_time": EVIDENCE_TIME,
        "analysis_evidence_time_basis": TIME_BASIS,
        "ordered_source_aggregate_sha256": SHA256,
    }
    metadata = AnalysisMetadata.model_validate(common)
    record = AnalysisRecord.model_validate(
        {
            **common,
            "analysis_relative_path": "analyses/analysis_matrix",
            "immutable_status": "complete",
        }
    )
    metadata_payload = metadata.model_dump(mode="json")
    record_payload = record.model_dump(mode="json")
    assert "receipt_sha256" not in metadata_payload
    assert "receipt_sha256" not in record_payload
    metadata_sha256 = hashlib.sha256(canonical_json_bytes(metadata_payload)).hexdigest()
    record_sha256 = hashlib.sha256(canonical_json_bytes(record_payload)).hexdigest()

    receipt = AnalysisReceipt.model_validate(
        {
            **state,
            "schema_version": "1.1.0",
            "algorithm_id": "plan_bound_synthetic_measurement_matrix",
            "algorithm_version": "1.1.0",
            "analysis_id": "matrix",
            "analysis_source_binding_sha256": SHA256,
            "measurement_row_index_sha256": SHA256,
            "feature_schema_sha256": SHA256,
            "split_plan_sha256": SHA256,
            "measurement_matrix_npz_sha256": SHA256,
            "analysis_metadata_sha256": metadata_sha256,
            "analysis_record_sha256": record_sha256,
            "ordered_source_aggregate_sha256": SHA256,
            "analysis_evidence_time": EVIDENCE_TIME,
            "analysis_evidence_time_basis": TIME_BASIS,
            "analysis_evidence_time_derivation_version": "1.0.0",
            "feature_count": 16,
            "split_fold_count": 24,
        }
    )

    assert receipt.analysis_metadata_sha256 == metadata_sha256
    assert receipt.analysis_record_sha256 == record_sha256
    assert receipt.analysis_evidence_time == EVIDENCE_TIME


def test_latest_verified_completion_is_compared_as_a_utc_instant() -> None:
    plus_two = timezone(timedelta(hours=2))
    completion_times = (
        datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        datetime(2026, 8, 20, 13, 0, tzinfo=plus_two),
        datetime(2026, 8, 20, 10, 30, tzinfo=UTC),
        datetime(2026, 8, 20, 5, 0, tzinfo=timezone(timedelta(hours=-5))),
    )

    normalized, evidence_time = derive_latest_verified_execution_completion_utc(completion_times)

    assert normalized == (
        datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
        datetime(2026, 8, 20, 10, 30, tzinfo=UTC),
        datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )
    assert evidence_time == datetime(2026, 8, 20, 11, 0, tzinfo=UTC)


def test_evidence_time_derivation_rejects_naive_or_empty_inputs() -> None:
    with pytest.raises(AnalysisSourceError, match="at least one"):
        derive_latest_verified_execution_completion_utc(())
    with pytest.raises(AnalysisSourceError, match="timezone-aware"):
        derive_latest_verified_execution_completion_utc((datetime(2026, 8, 20, 11, 0),))


def test_version_1_0_analysis_models_require_regeneration() -> None:
    with pytest.raises(ValidationError):
        AnalysisMetadata.model_validate(
            {
                **provisional_state(),
                "schema_version": "1.0.0",
                "analysis_id": "old",
                "created_at": EVIDENCE_TIME,
                "receipt_sha256": SHA256,
            }
        )
