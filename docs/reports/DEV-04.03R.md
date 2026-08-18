# DEV-04.03R implementation report

## Outcome boundary

DEV-04.03R closes two independently reproduced contract gaps in synthetic provisional repeatability evidence: immutable receipts did not contain every state printed by the CLI, and the public publisher/validator did not reject decision authority already present in the active AnalysisConfig. The change does not alter repeatability mathematics, pair enumeration, member ordering, capture/ESS/processing/QC mathematics, or create any baseline, threshold, drift, acoustic or experimental conclusion.

The verified starting point was `main` at `074abae69216672aa7a8410640c5ba79118c6f44`, identical locally, in `origin/main`, and at GitHub. The remote was `https://github.com/haocheng26710/fingers.git`, the worktree was clean, and no repository-level agent instruction file existed. The baseline suite reported `576 passed in 97.59s`; 22 generated Schemas were consistent, 23 Schema files existed in total, and strict mypy passed 77 source files.

## TDD reproduction and repair

The TDD sequence first added public-interface tests that failed because `baseline_role` was null, `baseline_selection_status`, `drift_decision`, and `repeatability_decision` were absent, a non-null injected drift threshold was accepted and published, and CLI output could not be reconstructed from the stored receipt. Production code was changed only after each RED was observed. Additional attacks cover every configured baseline/decision field, strict state parsing, old versions, CLI compute/validate consistency, immutable state/hash bindings, and read-only recovery.

`ProvisionalRepeatabilityReceipt` and its algorithm are now `1.1.0`. Receipt and `RepeatabilityRecord` inherit one strict fixed state model: decisions and drift are `not_evaluated`; thresholds are false/null; baseline is not assigned, has role `not_assigned`, and selection is deferred until protocol binding; baseline difference and protocol binding are false. One typed state constructor supplies receipt, record, and metadata. Both public paths reject an AnalysisConfig unless its active model exactly matches the loaded normalized bytes/hash and all of `baseline_selection_rule`, `qc_threshold`, `effect_threshold`, `drift_threshold`, and `classification_pass_threshold` are null. This gate runs before member replay and before creation of any repeatability parent, staging directory, or lock.

The CLI renders structured state from the publisher/validator result receipt. Its safety markers agree with those fields, including `DRIFT_NOT_EVALUATED`. CLI `PASS` means only software publication or validation success.

## Immutable and deterministic evidence

The metrics model and Schema remain `1.0.0`. The deterministic three-member, three-pair replay produced identical five payloads under two independent roots, including reversed caller member order in the second root. The protected hashes remain:

- metrics: `730872025244fb847b6ed9937865017b9563cb030865fb8bac193ea0cd2928b3`
- metrics sidecar: `2581bdb2b036e87035e5f0da5e45c93d173b4e75d84eb71b4279b6a76853a6c8`

The new `1.1.0` deterministic hashes are:

- receipt: `916b67b54bc1f4ec59176ce57a6160d6de0c7a8c68c902a4597283d5f5a27f60`
- receipt sidecar: `99dda95fa7705b43bab13328b4491166b8aebe426433f421c02aee07a0444a98`
- metadata: `474e96ddf753bc07ac7189ed380173c6ecbd7af5a69a42600b7e1fc095aa3d6d`

They replace the DEV-04.03 `1.0.0` references `bb4253…`, `d5f3ad…`, and `bb6fea…`. Old `1.0.0` receipt/algorithm artifacts are rejected and must be regenerated. The event field set remains schema `1.0.0`, while its record and receipt hashes bind the new bytes.

Receipt state, metadata state, record state, receipt sidecar, and event receipt/record hash attacks all fail validation without writeback. Each target is restored byte-for-byte and validation then passes. No real root is created.

## Verification and limitations

The prompt was archived byte-for-byte at SHA256 `1e2e29ed8a6204b9fcd4b7299d6b589732ee197e63444600ae6752d5c32de6ff`. The append-only log prefix is 121382 bytes at SHA256 `9793a4f6c1517edf2b67c863fff7943acd80cbe6d3b8ddbdd9f40d749470b7c8`. Schema export reported 22 generated files and consistency PASS; 23 total Schema files remain, and the pre/post metrics Schema SHA256 is `0c046ea5e3c8f9d660f88c935509a58c2bb73a138946e3cd8ec697a072f2ed81`.

Intermediate failures are retained in the implementation log: the five intentional REDs; two Windows path-length failures fixed only by shortening test identifiers; one Ruff regex-literal finding fixed with an explicit raw string; and one accidental system-PATH static-check invocation whose Ruff executable was absent and whose older mypy produced unrelated errors, followed by the correct `.venv` checks.

The completed repeatability group is 48/48, compared with the original 23 tests, for 25 added regressions. The first complete post-change suite is `601 passed in 142.51s`, preserving all original 576. Ruff format reported 123 files unchanged, lint passed after the regex fix, strict mypy passed 77 source files, Schema consistency passed at 22 generated / 23 total, and `git diff --check` passed. There are no skip/skipif/xfail markers or new noqa/type-ignore suppressions. Changed files contain no U+FFFD, secret/local-identity pattern, or real-audio API addition. Historical prompts/reports, config, fixtures, reference data, and `repeatability.py` have no diff from the baseline. The tracked transient scan found only the legitimate dependency lock `uv.lock`; no generated media, cache, staging, task lock, or temporary output is staged.

The V1.3 ZIP, manifest, inventory, capture context, summary, contextual preflight, and hardware hashes were directly recalculated as `1bf3cc17…`, `bd69f273…`, `8a68d714…`, `10472424…`, `84879af2…`, `e4767864…`, and `013fd2b1…`, matching the protected values. The complete suite also re-exercised locked ESS, DEV-04.01R2 processing, and DEV-04.02 QC goldens. All explicitly created pytest roots were resolved to their expected parents and removed; the first escalated system-temp removal used a different Windows identity and was denied, while the original sandbox identity removed the same three exact paths successfully, after which all four task roots were confirmed absent.

No production audio inventory command was run. No device was enumerated, selected, connected, played, recorded, or opened as a Stream; no calibration file, SPL, electrical loopback, shared-clock test, baseline selection/difference, threshold application, repeatability/drift PASS/FAIL, feature extraction, classifier, cross-validation, protocol engine, DEV-04.04, or real-data root was introduced. Events still have no digital signature, external witness, or trusted timestamp.

After this report and the implementation log were present, the final pre-commit gate reported: Ruff format `123 files already formatted`, Ruff lint PASS, strict mypy `Success: no issues found in 77 source files`, 22-Schema consistency PASS, `git diff --check` PASS, and `601 passed in 114.10s`. Its exact workspace temporary root was resolved, removed, and confirmed absent. Commit and push were still conditional on a fresh remote-baseline check and therefore were not pre-recorded here.
