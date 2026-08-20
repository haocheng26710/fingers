# DEV-06.01R report

## Result and scope

DEV-06.01R closes the analysis-envelope self-authority defect found after DEV-06.01. The change is limited to validated source completion-time capability, persisted analysis audit models, acyclic receipt binding, read-only replay validation, generated schemas, affected CLI output, tests and documentation. The 344 rows, 16 features, 24 grouped folds, baseline math, processing/QC kernels and exact 15-file envelope are unchanged. No model fit, prediction, classification, interaction analysis, threshold application, real hardware access or DEV-06.02 work occurred.

## Reproduction and diagnosis

The RED used the public Stage 1–4 double-root workflow. It published a complete envelope, saved metadata/record bytes, changed both `created_at` values to the same canonical aware UTC value `2026-08-21T11:00:00Z`, left the five core payloads, receipt, receipt sidecar and completion marker unchanged, and invoked `validate_synthetic_measurement_matrix(...)`. The baseline validator accepted the tamper. Command/result:

`python -m pytest tests/dev05/test_synthetic_protocol_execution_full.py --basetemp=.d601rred -q` → `1 failed in 967.83s (16:07)`, `Failed: DID NOT RAISE AnalysisPersistenceError` at line 207.

Root cause: validator parsed the candidate metadata and passed its `created_at` back into `_payloads(...)`; metadata and record were not receipt-bound, while their reverse receipt references would have created a hash cycle. A tampered file therefore supplied its own expected replay input.

## Fix design

After complete source-execution replay, `ValidatedAnalysisExecution` now carries typed completion time, canonical UTC completion time and completion SHA256. `ValidatedSyntheticAnalysisSources` keeps canonical completion times in stage order and derives:

- `analysis_evidence_time = max(verified completion UTC instants)`;
- basis `latest_verified_execution_completion_utc`;
- derivation version `1.0.0`.

The public compute API no longer accepts `now`; runtime wall-clock time cannot affect persisted bytes. Evidence time is reproducible source time, not publication time or a trusted timestamp.

The version 1.1 construction is one-way:

`validated sources → core payloads + metadata + record → metadata/record SHA256 → receipt → receipt sidecar`

Metadata and record no longer contain `receipt_sha256`. Receipt schema/algorithm 1.1 bind both file hashes, ordered source aggregate and source-derived time/basis/version. Source binding 1.1 records every canonical UTC execution completion. Metadata/record are 1.1. Old 1.0 envelopes are rejected and require regeneration; no in-place migration exists.

Validator checks the exact 15 names, fully replays sources, derives expected time only from verified completions, recomputes all rows/features/folds/core/metadata/record/receipt/sidecar bytes, and compares each file. It reads no candidate metadata/record/receipt field as authority for expected time, path or state, and performs no repair or cleanup.

## Deterministic evidence

The real double-root run produced these four canonical completion times:

- Stage 1: `2026-08-20T11:00:00Z`, completion SHA256 `226fbd5967f4fa2b30da3d131a1b72bf1f902b6cd9f46409fcc6f14667018f69`;
- Stage 2: `2026-08-20T11:00:00Z`, `4188d4031892d1a3977644e5a47e2a2208d2c2d9cc1e1e775e6eb28a66557602`;
- Stage 3: `2026-08-20T11:00:00Z`, `4bde33065fcbc4748b2670094f04837a878715c2ddbae6056eebb3da1803fb8d`;
- Stage 4: `2026-08-20T11:00:00Z`, `c12df24c10bf6d22c77a020b8c19ccc43c4580dfb1b679f4a322693c727ca70f`.

The derived evidence time is `2026-08-20T11:00:00Z`; basis is `latest_verified_execution_completion_utc`. New envelope hashes are:

- source binding: `202547ac4d9b5c6ec8a5aa08c66bc55ed084d66c0089f60debd27e1ef4c931a0`;
- metadata: `12a577c0479c798f02289c6705704441ce737aae50a8b00d7d9974346460d1ee`;
- record: `0fb337d16da433674926a5bc9a741f95c6871261f45cdda8b1e0c3808dcc6b73`;
- receipt: `49421dd32099b229581f01415e00968f5655d7eaf25113d5c4d56fd35a9198bf`;
- receipt sidecar file: `f82f9649761fd41a85271f7e6853eae45f13cfc2970a7b342794635a92652047`.

Unchanged core hashes are ordered source aggregate `39640ff09910541ba09f56e08a388ce161602d6dbc867a7eecb850745db96893`, row index `229c3f96d7976c9a95adbe7847a4f0d88e947f722d5cd63b3fd31f3b548c5d78`, feature schema `3d7858e931dd8938b9ebc269d0f84a5f3fae1a685cd150e66f083dfd76bd27c1`, split plan `02e606080c599d6ea3ae5563a6a9a80f6603af87f862e46b6dd50eccb799df1b`, and 1,126,675,730-byte NPZ `9529e178c2a719ad473137681fc209ef3597f1a538c682dd0e4f5d40d9387a93`.

The normal 15-file tree digest before and after read-only validation was `992168040f04cddc0b20ebd27d9a630bc984248201ead12b024112ca599dc056`. Every attack separately asserted identical pre/post file names, bytes, tree digest, size and `mtime_ns`, no lock/staging, and an unchanged second root.

## Attack matrix and tests

The existing double-root test now runs 24 unique public-validator attacks without a third matrix. Eight time attacks cover metadata-only, record-only, consistent double tamper, equivalent instant with different offset, naïve/invalid time, basis change and inconsistent pair. Nine state attacks cover all requested safety/status/path/aggregate fields. Hash requirements cover metadata/record single and double changes, recomputed metadata/record hashes, recomputed receipt sidecar, old 1.0 receipt, missing/extra fields and swapped hashes. Even a fully internally rehashed metadata/record/receipt/sidecar forgery is rejected by source-derived full replay.

Results:

- original DEV-06.01 ten-test acceptance-set equivalent: 7 source tests + 1 full double-root + 2 schema selectors, all passed;
- new fast contract tests: `4 passed` (plus the existing full test's 24 attack scenarios);
- complete attack double-root selector: `1 passed in 1444.44s (24:04)`;
- DEV-05.03R/R2 publication/cleanup regression: `27 passed in 93.04s`;
- all DEV-05: `223 passed in 2533.42s (42:13)`;
- all DEV-04: `290 passed in 171.60s (2:51)`;
- four locked/golden selectors: `4 passed in 876.73s (14:36)`;
- complete suite: `896 passed in 2799.00s (46:39)`, versus the 892-test baseline.

Final cleanup/report-time Ruff format checked 192 files and lint passed, strict mypy passed for 76 source files, generated schema consistency passed with 49 active/50 total schema files, and `git diff --check` passed. A first schema check correctly reported four stale/missing files; export fixed them. One subsequently mistyped pytest schema selector produced no tests and was not counted; the corrected two selectors passed.

## Prompt, protection and cleanup

The prompt archive is byte-identical to the attachment: 23,557 bytes, SHA256 `9486cb0709c8fa783a2e081e6c7537244a32e8012453c8626530f66189082996`, `SequenceEqual=True`. The implementation-log 218,309-byte frozen prefix remains `4bf6de9eeb37166837cb0b939c4824f3ca435dc3af684408b85b6f8ff1876276`; the older 202,796-byte prefix remains `af4412e920ab2204b4e136f828976d47b328e0b18408751aaa625a47bdd54f57`.

Protected ZIP/manifest/inventory/context/summary/contextual-preflight/hardware SHA256 values remain, respectively, `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`, `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`, `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`, `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`, `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`, `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`, `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`. Locked ESS WAV/metadata/raw remain `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`, `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`, `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`.

Suppression, U+FFFD, secrets, machine paths and new real-audio API scans were empty. Thirteen verified workspace-local `.d601*` roots were removed with `REMAINING=0`; no other path was deleted.

## Files and limitations

Principal code changes are `analysis/models.py`, `analysis/source_validation.py`, `analysis/persistence.py`, CLI/schema registry, four generated analysis schemas, the existing full integration test and a new fast envelope-contract test. README, data README and the two analysis/storage architecture documents describe the 1.1 contract.

SHA256 remains an internal integrity mechanism, not a signature, trusted timestamp or external witness. Source execution completion validation retains its existing execution-level time contract. This step makes analysis full replay non-self-referential; it does not introduce a trustworthy wall-clock publication time. No model, prediction, classification, threshold, real-device enumeration/I/O, playback, recording, stream, calibration, SPL verification or DEV-06.02 capability was implemented.
