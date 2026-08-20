import numpy as np

from acoustic_ladder.analysis.measurement_identity import MeasurementIdentity
from acoustic_ladder.analysis.measurement_matrix import assemble_measurement_arrays
from acoustic_ladder.audio.baseline_difference import BaselineDifferenceKernelMember
from acoustic_ladder.domain.models import LoadingDirection, NodeState


def _identity(order: int, *, all_blk: bool) -> MeasurementIdentity:
    module = "BLK" if all_blk else "CANDIDATE"
    state = NodeState(
        node_id="dynamic-node",
        state_id=f"state-{module}",
        module_id=module,
        state_type="test",
        discrete_label=module,
        continuous_value=None,
        unit=None,
        loading_direction=LoadingDirection.NOT_APPLICABLE,
        proxy_state=False,
        provenance=None,
        notes=None,
    )
    digest = f"{order:064x}"
    return MeasurementIdentity(
        row_id=f"row-{order}",
        work_order_sha256=digest,
        execution_id="execution",
        experiment_stage=1,
        global_planned_ordinal=order,
        session_local_measurement_order=order,
        session_index=1,
        reassembly_index=1,
        condition_block_order=order,
        canonical_condition_index=order,
        session_id="session",
        reassembly_id="reassembly",
        run_id=f"run-{order}",
        capture_id=f"capture-{order}",
        condition_id=f"condition-{order}",
        condition_role="all_blk_reference" if all_blk else "candidate",
        condition_label=module,
        condition_node_state_sha256=digest,
        node_states={state.node_id: state},
        session_group_id="stage-1-session",
        reassembly_group_id="stage-1-session-reassembly",
        baseline_group_id="stage-1-session-reassembly",
        selected_node_ids=(state.node_id,),
        selected_state_ids=(state.state_id,),
        selected_module_ids=(state.module_id,),
        loading_directions=(state.loading_direction.value,),
        repeat_kind="continuous_repeat",
        continuous_repeat_index=order,
        proxy_state=False,
        is_all_blk=all_blk,
    )


def _member(order: int, value: float) -> BaselineDifferenceKernelMember:
    vector = np.array([[[value, value * 2.0]]], dtype=np.float64)
    return BaselineDifferenceKernelMember(
        measurement_order=order,
        frequency_hz=np.array([100.0, 200.0], dtype=np.float64),
        analysis_band_mask=np.array([True, True]),
        transfer_raw_real=vector,
        transfer_raw_imag=np.zeros_like(vector),
        transfer_aligned_real=np.ascontiguousarray(vector * 2.0),
        transfer_aligned_imag=np.zeros_like(vector),
        ir_raw=np.array([[[value, 0.0]]], dtype=np.float64),
        ir_aligned=np.array([[[value * 2.0, 0.0]]], dtype=np.float64),
    )


def test_matrix_assembly_uses_leave_one_out_and_is_order_invariant() -> None:
    identities = (_identity(1, all_blk=True), _identity(2, all_blk=True))
    candidate = _identity(3, all_blk=False)
    rows = (*identities, candidate)
    members = {
        row.row_id: _member(row.global_planned_ordinal, value)
        for row, value in zip(rows, (1.0, 3.0, 5.0), strict=True)
    }

    result = assemble_measurement_arrays(rows=rows, members=members)

    assert result.row_ids == ("row-1", "row-2", "row-3")
    assert result.baseline_reference_row_ids == {
        "row-1": ("row-2",),
        "row-2": ("row-1",),
        "row-3": ("row-1", "row-2"),
    }
    assert result.arrays["feature_matrix"].shape == (3, 16)
    assert result.arrays["raw_baseline_mean_transfer_real"].shape == (3, 1, 1, 2)
    np.testing.assert_array_equal(
        result.arrays["raw_baseline_mean_transfer_real"][:, 0, 0, 0],
        np.array([3.0, 1.0, 2.0]),
    )
    reversed_result = assemble_measurement_arrays(rows=tuple(reversed(rows)), members=members)
    assert result.row_ids == reversed_result.row_ids
    for name, array in result.arrays.items():
        np.testing.assert_array_equal(array, reversed_result.arrays[name])
