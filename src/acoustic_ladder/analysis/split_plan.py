"""Deterministic stage-local grouped splits for leakage-resistant offline analysis."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from .measurement_identity import MeasurementIdentity

SplitStrategy = Literal["leave_one_session_out", "leave_one_reassembly_out"]
SPLIT_STRATEGIES: tuple[SplitStrategy, ...] = (
    "leave_one_session_out",
    "leave_one_reassembly_out",
)


class SplitFold(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    fold_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    strategy: SplitStrategy
    experiment_stage: Literal[1, 2, 3, 4]
    held_out_group_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    train_group_ids: tuple[str, ...] = Field(min_length=1)
    test_group_ids: tuple[str, ...] = Field(min_length=1)
    train_row_ids: tuple[str, ...] = Field(min_length=1)
    test_row_ids: tuple[str, ...] = Field(min_length=1)


class SplitPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["1.0.0"]
    algorithm_version: Literal["development_grouped_split_v1"]
    row_count: int = Field(gt=0)
    strategies: tuple[SplitStrategy, ...]
    folds: tuple[SplitFold, ...] = Field(min_length=1)
    random_split_used: Literal[False]
    day_split_used: Literal[False]


def _group_id(row: MeasurementIdentity, strategy: SplitStrategy) -> str:
    if strategy == "leave_one_session_out":
        return row.session_group_id
    return row.reassembly_group_id


def build_grouped_split_plan(rows: Sequence[MeasurementIdentity]) -> SplitPlan:
    """Build canonical leave-one-session/reassembly-out folds independently by stage."""

    canonical_rows = tuple(sorted(rows, key=lambda row: row.row_id))
    if not canonical_rows or len({row.row_id for row in canonical_rows}) != len(canonical_rows):
        raise ValueError("split input must contain unique measurement rows")
    folds: list[SplitFold] = []
    for stage in range(1, 5):
        stage_rows = tuple(row for row in canonical_rows if row.experiment_stage == stage)
        if not stage_rows:
            raise ValueError(f"split input is missing Stage {stage}")
        stage_row_ids = {row.row_id for row in stage_rows}
        for strategy in SPLIT_STRATEGIES:
            group_ids = tuple(sorted({_group_id(row, strategy) for row in stage_rows}))
            if len(group_ids) < 2:
                raise ValueError(f"Stage {stage} has fewer than two {strategy} groups")
            for fold_index, held_out in enumerate(group_ids, start=1):
                test_rows = tuple(
                    row.row_id for row in stage_rows if _group_id(row, strategy) == held_out
                )
                train_rows = tuple(sorted(stage_row_ids.difference(test_rows)))
                train_groups = tuple(group_id for group_id in group_ids if group_id != held_out)
                folds.append(
                    SplitFold(
                        fold_id=f"stage_{stage}_{strategy}_fold_{fold_index:02d}",
                        strategy=strategy,
                        experiment_stage=cast(Literal[1, 2, 3, 4], stage),
                        held_out_group_id=held_out,
                        train_group_ids=train_groups,
                        test_group_ids=(held_out,),
                        train_row_ids=train_rows,
                        test_row_ids=test_rows,
                    )
                )
    return SplitPlan(
        schema_version="1.0.0",
        algorithm_version="development_grouped_split_v1",
        row_count=len(canonical_rows),
        strategies=SPLIT_STRATEGIES,
        folds=tuple(folds),
        random_split_used=False,
        day_split_used=False,
    )
