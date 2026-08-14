# DEV-01.01 Completion Report

## Identity and result

- Sequence: `DEV-01.01`
- Name: V1.3 model-package ingestion, provenance audit and provisional device manifest
- Final implementation status: `PASSED`
- Scope: model-package ingestion, calibration-record normalization, provenance, provisional manifest, Schema, CLI, tests and documentation only

## Input and hashes

- Original input: `D:\Firefly\Desktop\毕业论文相关\双管—直接管道\Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip`
- Repository copy: `reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip`
- Original computed SHA256: `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- Repository-copy computed SHA256: `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- Cross-check: both match the supplied expected value

The ZIP remains intact in the repository. No STL, STEP or assembly file was duplicated outside it. Every entry was read directly through the ZIP API; packaged Python was never imported or executed.

## Created and modified files

- Project: `.gitattributes`, `.gitignore`, `.python-version`, `README.md`, `pyproject.toml`, `uv.lock`
- Package code: `src/acoustic_ladder/` and `src/acoustic_ladder/model_package/`
- Schema and output: `schemas/device_manifest.schema.json`, `config/devices/device_manifest.provisional.json`, `config/devices/device_manifest.provisional.sha256`
- References: original ZIP, `reference/model_reviews/V1_3_package_audit.json`, `reference/model_reviews/V1_3_package_review.md`, and both calibration-record formats
- Records: `docs/IMPLEMENTATION_LOG.md`, `docs/prompts/DEV-01.01.md`, this report
- Tests: `tests/unit/`, `tests/integration/`, and test support files

No `device_manifest.lock.json`, raw experimental data, credentials, virtual environment, cache or extracted CAD duplicate is included.

## Actual environment and dependencies

- Windows / PowerShell
- Git `2.55.0.windows.3`
- Python `3.12.4`
- uv `0.11.6`
- `jsonschema 4.26.0`
- `pytest 9.1.1`
- `ruff 0.16.3`
- `mypy 1.20.2`
- `types-jsonschema 4.26.0.20260518`

Dependencies are locked in `uv.lock`. A workspace-local `.uv-cache` was used because the user-level uv cache path could not be initialized in this environment.

## Commands actually run

The initial Git, directory, remote and ZIP checks are recorded verbatim in `docs/IMPLEMENTATION_LOG.md`. The implementation and acceptance commands were:

```powershell
git init -b main
git remote add origin https://github.com/haocheng26710/fingers.git
git ls-remote --heads --tags https://github.com/haocheng26710/fingers.git
Get-FileHash -Algorithm SHA256 -LiteralPath '<original-zip>'
Copy-Item -LiteralPath '<original-zip>' -Destination 'reference\model_packages\Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip'
Get-FileHash -Algorithm SHA256 -LiteralPath 'reference\model_packages\Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip'
uv --cache-dir .uv-cache lock --python 3.12
uv --cache-dir .uv-cache sync --all-groups --frozen
uv --cache-dir .uv-cache run ruff format .
uv --cache-dir .uv-cache run python -m compileall -q src
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package normalize-calibration reference/calibration/V1_3_user_calibration_record.json --output-json reference/calibration/V1_3_user_calibration_record.json --output-markdown reference/calibration/V1_3_user_calibration_record.md
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package inspect reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip --calibration reference/calibration/V1_3_user_calibration_record.json --output reference/model_reviews/V1_3_package_audit.json
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package generate reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip --calibration reference/calibration/V1_3_user_calibration_record.json --output config/devices/device_manifest.provisional.json --sidecar config/devices/device_manifest.provisional.sha256
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package validate config/devices/device_manifest.provisional.json --schema schemas/device_manifest.schema.json --sidecar config/devices/device_manifest.provisional.sha256
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package hash config/devices/device_manifest.provisional.json --sidecar config/devices/device_manifest.provisional.sha256
uv --cache-dir .uv-cache run pytest tests/unit
uv --cache-dir .uv-cache run pytest tests/integration
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
git diff --check
```

Three corrected setup/check failures were retained rather than hidden: the default uv cache path could not be initialized, the first `uv sync` found that `README.md` had not yet been created, and the first staged `git diff --check` found three extra EOF blank lines. The cache was explicitly redirected into the ignored `.uv-cache`, the required README was created, and the EOF whitespace was corrected before the final gate. `gh auth status` could not run because `gh` is not installed; Git itself is used for push and remote verification.

## Test and static-check results

- Unit tests: `30 passed`, no skip or xfail
- Real-package integration tests: `13 passed`, no skip or xfail
- Complete suite: `43 passed`, no skip or xfail
- Format check: `20 files already formatted`
- Lint: `All checks passed!`
- Strict type check: `Success: no issues found in 15 source files`
- Manifest Schema and sidecar validation: PASS
- Determinism: two independent manifest generations produced identical bytes and SHA256 in the integration suite
- Malicious/error fixtures: missing entries, malformed JSON, malformed CSV, traversal, absolute paths, normalized duplicates, conflicts and sidecar tampering all rejected as expected

No required acceptance check was skipped.

## Real-package audit summary

- ZIP entries: 85; all readable
- Unsafe paths or normalized duplicates: none
- Required files: all present and parsed
- Python sources read as non-executable data: 12
- Formal parts / STL / part STEP / assembly STEP / batches / coupons: `22 / 22 / 22 / 4 / 8 / 0`
- Package completeness: PASS
- Printability: PASS
- Mechanical validation: `254 PASS / 0 WARNING / 0 FAIL`
- Active geometry: V1.3 calibrated round main tube
- Historical source geometry: V1.2 equal-area round main tube

## Manifest summary

- File: `config/devices/device_manifest.provisional.json`
- Stable SHA256: `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- State: provisional, actual printed, calibration applied, calibrated printed candidate
- Geometry locked: false
- Experiment ready: false
- Active lumen: round
- Formal channels: one output and one input
- Boundary conditions: TX near speaker, RX near microphone, both far ends closed, BLK required at every unused node

The manifest uses sorted-key UTF-8 JSON with LF termination. It contains no machine absolute path, scan timestamp or random value. The Schema requires nullable measurements as present fields, distinguishes target/CAD/measured apertures and rejects an inconsistent locked/provisional state.

## Conflicts, warnings and missing information

Two conflicts are explicit and resolved by declared priority:

1. Calibrated BOM M/L/H quantities `4/0/0` override `source/bom.py` quantities `4/1/1`.
2. Active round geometry overrides the historical derived field label `main_teardrop`; that historical field is never used as the active lumen shape.

Nine retained warning codes cover the historical field/title names, BOM mismatch, missing `acoustic_calcs.py` and `build_v1.py`, missing locked CAD environment, missing raw calibration measurements, incomplete actual print information, and unrecorded leak/spectral-repeatability tests. Full evidence appears in the audit and review files.

All user-declared unknown values are explicit `null` in the calibration JSON and corresponding manifest structures, including all five acoustic-hole measurements. They also appear as JSON Pointers in `missing_information`.

## Calibration normalization and manufacturing separation

The machine record preserves source type `user_confirmed_measurement_record`, date `2026-08-14`, a null confirmation time, all coupons, observations and selected values. The Markdown record is generated from and faithfully includes that normalized JSON content.

Package recommendations (`0.4 mm` nozzle, `PLA/PLA+`, `0.16–0.20 mm` layer height and 5 walls) are stored only under `design_recommendation`. They never populate the null `actual_print_setting` fields.

## Known limits and explicitly unimplemented work

The packaged source is insufficient for version-locked CAD reconstruction, raw measurements are absent, and leak/spectral-repeatability validation is unknown. The manifest is therefore provisional.

This sequence did not implement audio enumeration/capture, ESS, audio calibration, deconvolution, impulse response, transfer functions, QC, phase 1–4 protocols, synthetic experiments, feature extraction, models, UI, database, deployment, repository renaming or geometry locking.

## Interfaces available to the next sequence

- `inspect_archive(...)` for safe package audit
- `load_calibration_record(...)` and CLI normalization
- `generate_manifest(...)` and canonical `write_manifest(...)`
- Schema/sidecar validation and sidecar recomputation
- documented CLI commands under `python -m acoustic_ladder.model_package`

## Git target

- Remote: `https://github.com/haocheng26710/fingers.git`
- Branch: `main`
- Planned commit subject: `DEV-01.01: ingest V1.3 package and create provisional manifest`

The actual commit SHA and post-push remote verification are intentionally reported in the execution response, not fabricated inside the commit that would need to name itself.
