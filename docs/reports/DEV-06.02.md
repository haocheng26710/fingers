# DEV-06.02 report

## Result and scope

DEV-06.02 adds the minimal synthetic-only Stage 1–4 offline research analysis. The public `acoustic_ladder.analysis.run_research_analysis` entry and `research-analyze` CLI read an existing DEV-06.01 envelope and publish exactly six deterministic files into a new, create-only output directory. They load only the persisted `feature_matrix` member and do not replay ESS processing, execute protocols, or regenerate the 1.13 GB matrix.

The input gate checks the exact 15-file envelope, completion marker, receipt/sidecar bindings, analysis identity and synthetic/development state, row/feature/matrix counts, finite feature values, unique row IDs, and fold references. The prevalidated large NPZ digest is reused from the receipt-bound sidecar instead of rehashing the full archive; the loaded feature matrix is still checked for declared shape and finite values.

## Analysis definitions

- Stage 1 derives active node and bridge state from row metadata, then reports count, population standard deviation, feature mean, and mean delta against that row's same-group BLK references. It performs no significance test or threshold decision.
- Stage 2 uses OLS slope and R² only when each Stage 2 row has one explicit finite `NodeState.continuous_value`. Otherwise it emits condition-level proxy counts, means and population standard deviations with `not_computed_missing_continuous_label`; it never parses numbers from condition names. The repository's current Stage 2 protocol has no continuous labels.
- Stage 3 derives the plan-ordered node pair and the 00/10/01/11 states, computes all deltas against 00 BLK, and reports the additive interaction residual without significance testing.
- Stage 4 derives the target from four explicit binary NodeState labels in persisted `selected_node_ids` plan/manifest order. Only measurement feature columns enter scikit-learn multinomial logistic regression (`solver=lbfgs`, `C=1.0`, `max_iter=1000`, fixed seed). Every session/reassembly fold fits mean, safe scale and model on training rows only; missing classes, incomplete strategy coverage or invalid row references fail closed.

## Artifacts and dependency

The output contains only `research_summary.json`, four requested CSV files, and `research_receipt.json`. No model pickle, sidecar, threshold, formal decision, hardware result or extra schema is created. Summary/receipt state is fixed to synthetic/development/provisional and `experimental_result=false`; the receipt records all 15 input file digests, five non-self-referential output digests, row/feature/fold counts and no-hardware/no-formal-experiment state.

`scikit-learn>=1.5,<2` is now a direct dependency; the lock resolved scikit-learn 1.9.0. `scikit-learn-stubs` is a development dependency so strict mypy passes without suppression.

## Tests and checks

Seven new tests cover the requested six behaviors: Stage 1 hand calculation; Stage 2 explicit-continuous and missing-continuous branches; Stage 3 hand calculation; Stage 4 train-only standardization and complete session/reassembly prediction coverage; deterministic repeated publication plus existing-directory rejection; and a successful CLI smoke over a small real 15-file temporary envelope. The small Stage 4 fixture uses four folds and produced accuracy, balanced accuracy and macro-F1 of 1.0 in each fold; those fixture scores are software-test evidence, not research findings.

The workspace contains no complete `measurement_matrix.npz`, so the 344-row smoke was not run and is deferred to Stage 6 as instructed. No automatic test is skipped. The complete test suite was deliberately not run. No Schema model or generated Schema changed, so Schema consistency was not rerun.

Initial tool issues were retained honestly: `uv` could not initialize its user cache, so all later commands used the task-local `.uv-cache-dev0602`; initial strict mypy found missing third-party sklearn typing, resolved by the declared stubs dependency rather than `type: ignore`; initial Ruff found only import/line-format issues, fixed mechanically. Final targeted results and static checks are recorded in `docs/IMPLEMENTATION_LOG.md`.

Final combined targeted pytest was `13 passed in 1.55s` (7 new plus 6 directly related existing tests). Changed-file Ruff format reported 4 files already formatted, Ruff lint passed, strict mypy passed for the 4 affected source/test files, `git diff --check` passed, and the prohibited suppression scan found 0 matches. The verified workspace-local task cache was removed with `remaining=False`.

## Limitations

No full 344-row metric exists in this workspace, so no real Stage 4 fold score is reported. Stage 2's active protocol lacks a trusted continuous label and therefore will use proxy group descriptions. The analyses are descriptive development machinery only: no threshold, hyperparameter search, model selection, real-device access, playback, recording, calibration, formal experiment or acoustic conclusion occurred.
