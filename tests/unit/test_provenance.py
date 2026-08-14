from acoustic_ladder.model_package.models import SourceCandidate
from acoustic_ladder.model_package.provenance import resolve_value, source_reference


def _candidate(value: str, priority: int, filename: str) -> SourceCandidate:
    return SourceCandidate(
        value=value,
        priority=priority,
        source_type="test",
        source_filename=filename,
        locator="/value",
        parameter_kind="source",
        unit=None,
        confirmation_status="confirmed",
    )


def test_field_source_record_contains_required_fields() -> None:
    source = source_reference(_candidate("round", 1, "params_calibrated_v1_3.json"))
    assert source == {
        "source_type": "test",
        "source_filename": "params_calibrated_v1_3.json",
        "locator": "/value",
        "parameter_kind": "source",
        "unit": None,
        "confirmation_status": "confirmed",
    }


def test_v1_3_priority_wins_and_conflict_is_not_silent() -> None:
    value, conflict = resolve_value(
        "/architecture/main_tube/lumen_shape",
        [
            _candidate("teardrop", 3, "derived_acoustics_v1.json"),
            _candidate("round", 1, "params_calibrated_v1_3.json"),
        ],
    )
    assert value == "round"
    assert conflict is not None
    assert conflict["resolution"] == "selected_by_declared_source_priority"


def test_equal_candidates_do_not_create_false_conflict() -> None:
    value, conflict = resolve_value(
        "/calibration/offset",
        [_candidate("-0.14", 1, "package.json"), _candidate("-0.14", 2, "user.json")],
    )
    assert value == "-0.14"
    assert conflict is None


def test_formal_bom_priority_over_source_bom() -> None:
    value, conflict = resolve_value(
        "/bill_of_materials/wedge_L",
        [_candidate("1", 5, "source/bom.py"), _candidate("0", 3, "BOM_calibrated_v1_3.csv")],
    )
    assert value == "0"
    assert conflict is not None
