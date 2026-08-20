# DEV-06.01 implementation report

## Result and scope

DEV-06.01 implements a plan-bound, synthetic-only offline measurement matrix over completed Stage 1–4 protocol executions. It does not execute a protocol, train a model, predict, classify, apply thresholds, decide QC, access audio hardware or implement DEV-06.02.

The starting commit was `e8edafac3e78f1ddff76818d2c0a3e1031f79a40` on `main`; local HEAD, `origin/main` and GitHub main matched, the worktree was clean, the remote was `https://github.com/haocheng26710/fingers.git`, and no project `AGENTS.md`/`CLAUDE.md`/`CODEX.md`/`.agents`/`.codex` instruction was present. The prompt archive is byte-identical at 38,674 bytes with SHA256 `731683abb9c3fb983c39c462f420d06c9e76d3666e85e9681008de0fb561ef54`. The frozen 202,796-byte implementation-log prefix remains SHA256 `af4412e920ab2204b4e136f828976d47b328e0b18408751aaa625a47bdd54f57`.

## Public contracts

New public capabilities are:

- `load_development_analysis_matrix_spec`;
- `validate_synthetic_analysis_sources` and its process-local typed capability;
- `process_validated_analysis_row`;
- `derive_measurement_identities`, `build_baseline_reference_map`, `build_grouped_split_plan`;
- `compute_analysis_row_features`, `assemble_measurement_arrays`, `compute_measurement_matrix`;
- `SyntheticMeasurementMatrixStore`, `compute_synthetic_measurement_matrix`, and read-only `validate_synthetic_measurement_matrix`;
- CLI `analysis-matrix-compute` and `analysis-matrix-validate`.

Seven strict generated schemas were added: development analysis spec, analysis source binding, measurement row, feature column schema, split fold, split plan and analysis receipt. The generated registry now contains 47 models and the committed schema directory contains 48 files including the historical manifest schema.

## Rows, references, features and splits

The complete matrix has exactly 344 rows: Stage 1 152, Stage 2 32, Stage 3 32 and Stage 4 128. Row identity binds the source execution, plan-derived work order and global ordinal. Row metadata includes all plan coordinates, complete NodeState map/digest, selected-node-order state/module/loading labels, source run/capture and execution hashes, QC metrics and baseline metrics. No rows are excluded.

Each baseline group is exactly `(stage, session_id, reassembly_id)` and contains two all-BLK continuous repeats. Candidate rows use the arithmetic mean of those repeats; an all-BLK row excludes itself and uses the other repeat. There are 16 such composite groups across four stages. No baseline crosses a stage, session or reassembly.

The versioned feature order is the 16 IDs required by the prompt: raw/aligned complex additive symmetric relative L2; raw/aligned magnitude RMS and maximum absolute dB; raw/aligned phase RMS and maximum absolute radians; raw/aligned IR symmetric NRMSE, absolute peak and peak index. `feature_matrix` is finite float64. Full raw/aligned source, baseline, additive/ratio, magnitude/phase/IR difference arrays and masks remain in the deterministic NPZ; row labels and QC metrics are not feature columns.

The split plan contains 24 stage-local folds: eight leave-one-session-out and sixteen leave-one-reassembly-out. Each row is test exactly once per strategy; train/test row and group intersections are empty. Reversing source or row enumeration leaves canonical output unchanged.

## Immutable envelope and full replay

The exact 15 files are:

1. `analysis_source_binding.json` and `.sha256`;
2. `measurement_row_index.json` and `.sha256`;
3. `feature_schema.json` and `.sha256`;
4. `split_plan.json` and `.sha256`;
5. `measurement_matrix.npz` and `.npz.sha256`;
6. `analysis_receipt.json` and `.sha256`;
7. `analysis_metadata.json`;
8. `analysis_record.json`;
9. `ANALYSIS_COMPLETE`.

Publication derives the target under an injected synthetic analysis root, uses a safe ID, same-filesystem staging, a create-only lock, no-replace rename and completion-last ordering. Complete/partial targets and stale locks are rejected. Cleanup errors are normalized without swallowing `BaseException`. Validation creates no root, lock or staging, performs no repair/cleanup, revalidates all four executions/captures, recomputes all 344 processing/QC rows, references, features, splits and canonical payloads, and compares every byte.

The complete double-root fixture produced the following stable hashes before the intentional right-root tamper test:

- ordered source aggregate: `39640ff09910541ba09f56e08a388ce161602d6dbc867a7eecb850745db96893`;
- source binding: `38bf3c2cde3b8f49b08e7952aa63135ea6c272298738e51dc6af79726c367699`;
- row index: `229c3f96d7976c9a95adbe7847a4f0d88e947f722d5cd63b3fd31f3b548c5d78`;
- feature schema: `3d7858e931dd8938b9ebc269d0f84a5f3fae1a685cd150e66f083dfd76bd27c1`;
- split plan: `02e606080c599d6ea3ae5563a6a9a80f6603af87f862e46b6dd50eccb799df1b`;
- matrix NPZ: `9529e178c2a719ad473137681fc209ef3597f1a538c682dd0e4f5d40d9387a93`;
- receipt: `1051a137bbe8108ab1ba7d448a049d3310454c1f54384eb2a780a98856f28cc6`.

Both roots had 15 matching names; source-binding and the 1,126,675,730-byte NPZ hashes matched. The test also proves both full validators preserve their trees, repeated compute cannot replace a winner, a stale lock is retained, and a tampered receipt is rejected after full replay.

## TDD and verification

The implementation used vertical RED→GREEN. Missing analysis/spec/source/adapter/feature/identity/split/matrix/persistence/validator capabilities first failed collection or the intended public behavior. A legitimate Stage 1 all-BLK row exposed an incorrect test assumption that selected nodes must be non-empty; the row model was corrected to preserve both the complete NodeState map and the legitimately empty selected subset. Ruff initially reported seven unformatted files and 24 lint findings; strict mypy initially reported 41 type errors. These were fixed without suppression. Two misspelled schema selectors and one PowerShell scan quoting command failed and were not counted as passed.

Actual successful highlights:

- DEV-06 unit group: `10 passed in 16.17s`;
- DEV-06 plus active-schema selectors: `12 passed in 15.16s`;
- complete Stage 1–4 double-root compute/validate, initial: `1 passed in 867.95s (14:27)`;
- enhanced double-root existing/stale/tamper run: `1 passed in 830.36s (13:50)`;
- ESS/processing/QC golden plus complete rehearsal hashes: `4 passed in 880.22s (14:40)`;
- full suite: `892 passed in 2533.53s (42:13)`, versus the 882-test starting baseline;
- after the final explicit Windows symlink/reparse-root rejection hardening, DEV-06 was `10 passed in 19.25s` and the full suite was rerun as `892 passed in 2469.87s (41:09)`; this latter run is the final production-code result;
- Ruff format: 197 files formatted; Ruff lint PASS;
- strict mypy: 76 source files PASS;
- schema consistency PASS; `git diff --check` PASS;
- changed/new test suppression scan, U+FFFD, local absolute-path, credential/secret and added real-audio API scans: zero hits.

The full command history and failed intermediate commands are recorded in `docs/IMPLEMENTATION_LOG.md`. No test used skip, xfail, warning suppression, noqa or type-ignore.

## Protected evidence

Direct SHA256 recomputation preserved:

- V1.3 ZIP `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`;
- provisional manifest `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`;
- inventory `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`;
- capture context `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`;
- summary `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`;
- contextual preflight `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`;
- hardware setup `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`.

Locked tests preserved ESS WAV/metadata/raw SHA256 `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0` / `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a` / `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`, plus existing processing/QC/rehearsal locked evidence.

## Files and limitations

Principal additions are `config/analysis/development_measurement_matrix.yaml`, `src/acoustic_ladder/analysis/*`, seven schemas, `tests/dev06/*`, the extended complete synthetic-execution test, CLI/schema registry changes, prompt/report/log and the new architecture document. Historical schema-count assertions changed only mechanically from 40/41 to 47/48.

Known limits: this is development synthetic evidence only; trusted day grouping is unavailable; the uncompressed full-array NPZ is about 1.13 GB; complete validation is intentionally expensive; the create-only lock is a local filesystem coordination mechanism, not a distributed lease; hashes are not signatures, external witnesses or trusted timestamps. The store explicitly rejects a supplied Windows reparse/symlink root and any reparse entry in a completed envelope. There is no model, prediction, classification, interaction analysis, threshold, real QC decision, hardware/calibration/SPL result or physical/experimental claim. DEV-06.02 is not implemented.

Commit and push are intentionally not pre-recorded in this report; they occur only after the final clean-worktree and remote-baseline gates.
