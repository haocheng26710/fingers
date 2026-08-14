# DEV-02.01 completion report

## Result

Status: `PASSED` locally before commit. DEV-02.01 adds strict configuration contracts, stable domain records, immutable file storage, synthetic/real isolation, a transparent deterministic synthetic generator, CLI commands, eight generated Schemas, documentation and 66 new tests. It does not begin DEV-03.01.

Baseline and Git target:

- baseline: `06d77b39acc9f609617a4e216647dc3f6c590a1d`
- repository: `https://github.com/haocheng26710/fingers.git`
- branch: `main`
- planned subject: `DEV-02.01: add config, immutable storage, and synthetic data`

No unproduced commit SHA is recorded here.

## Created and modified files

- Added layered YAML drafts under `config/audio/`, `config/protocols/`, `config/analysis/` and `config/synthetic/`.
- Added `src/acoustic_ladder/config/`, `domain/`, `storage/`, `synthetic/`, the unified `cli.py` and `__main__.py`.
- Added eight model-generated files under `schemas/` without changing `device_manifest.schema.json`.
- Added 66 tests under `tests/dev02/`.
- Added four architecture documents, `data/README.md`, this report and the exact archived DEV-02.01 prompt.
- Updated `.gitattributes`, README, `pyproject.toml`, `uv.lock`, and appended only the DEV-02.01 implementation-log section. The DEV-02 prompt is marked binary so Git stores the attached original bytes without line-ending normalization.

## Configuration system

Safe ruamel.yaml loading rejects duplicate keys and custom tags. Strict Pydantic v2 models reject unknown fields and inappropriate coercion while preserving explicit field paths. Each layer retains original bytes/path/SHA256 and canonical sorted-JSON SHA256. The bundle verifies the manifest sidecar, protocol manifest reference and digest, records normalized layer hashes, and excludes load time from its content hash.

Audio is generically N+M but formal mode requires exactly one TX-speaker output and one RX-microphone input. Unconfirmed backend/device/channel/timing/gain fields remain null and `hardware_ready` remains false. Stage 1–4 files are non-executable formal drafts with closed far ends and BLK unselected nodes. Stage 4 follows the supplied manifest recommendation dynamically. Analysis features, normalization, final cross-validation and thresholds remain null.

Direct dependencies added and locked were NumPy 2.5.2, Pydantic 2.13.4 and ruamel.yaml 0.18.17. Relevant locked transitives are pydantic-core 2.46.4, annotated-types 0.8.0, typing-inspection 0.4.4 and ruamel.yaml.clib 0.2.15.

## Domain and storage invariants

The stable records are DataOrigin, RunMode, NodeState, SessionRecord, ReassemblyRecord, MeasurementRunRecord, ArtifactRef and ConfigSnapshot. Data origin is independent from run mode. Synthetic runs are forced to development mode, are never formal eligible and require `NOT_EXPERIMENTAL_RESULT`. Persistent paths are portable relative paths only.

Synthetic and real roots must be distinct and non-overlapping. Synthetic-only writers reject real records. Sessions and runs are assembled in same-filesystem staging directories; files are create-only atomic publications, and an existing ID fails. Required snapshots, records, artifacts and completion markers are written before the staging directory is renamed into place. Pre-publication failure removes staging. Events are numbered create-only files. Validation checks session/run identity, reassembly membership, complete manifest node maps, artifact size/SHA256 and all completion markers.

## Synthetic algorithm and actual example

Node delays are read from manifest geometry and computed as `2*x/c`. Relative module coupling is `scale * (aperture/max_aperture)^2 * exp(-loss * round_trip_distance)`. BLK supplies no delayed node contribution; a configured direct baseline remains. SeedSequence controls excitation, noise and session/reassembly drift. Arrays are channel-first, finite, float32 by default and stored as deterministic NPZ plus explicit JSON metadata.

The default config uses seed 20260814, 48 kHz, 0.25 s, assumed 343 m/s, baseline coupling 0.05, loss 0.4/m, module scale 0.15, noise 0.001, session drift 0.01, reassembly drift 0.02 and 1+1 channels. The assumption and all physical limitations are persisted.

An actual CLI example was generated outside the repository at the operating-system temporary root with session `example001`, reassembly `reassembly001`, run `run001`, and override `N1=B40`. Session and run validation passed. `synthetic_arrays.npz` was 97,244 bytes with SHA256 `908a2c01ca652390cd7ddcf055c608b3339dedfbcbcc1724dc4e06010bef333a`. No example data was placed in the repository or real root.

## Commands and verification results

Principal commands actually run from the repository root:

```powershell
uv --cache-dir .uv-cache lock --python 3.12
uv --cache-dir .uv-cache sync --all-groups --frozen
uv --cache-dir .uv-cache run python -m acoustic_ladder export-schemas --output-dir schemas
uv --cache-dir .uv-cache run acoustic-ladder validate-config audio config/audio/default_1x1_ess.yaml --project-root .
uv --cache-dir .uv-cache run acoustic-ladder validate-bundle --project-root . --protocol config/protocols/stage4_four_node_states.yaml
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
uv --cache-dir .uv-cache run acoustic-ladder create-synthetic-session --project-root . --protocol config/protocols/stage4_four_node_states.yaml --synthetic-root <temporary-synthetic-root> --session-id example001 --reassembly-id reassembly001
uv --cache-dir .uv-cache run acoustic-ladder generate-synthetic-run --project-root . --protocol config/protocols/stage4_four_node_states.yaml --synthetic-root <temporary-synthetic-root> --session-id example001 --reassembly-id reassembly001 --run-id run001 --node-state N1=B40
uv --cache-dir .uv-cache run acoustic-ladder validate-session --synthetic-root <temporary-synthetic-root> --session-id example001
uv --cache-dir .uv-cache run acoustic-ladder validate-run --synthetic-root <temporary-synthetic-root> --session-id example001 --run-id run001
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
uv --cache-dir .uv-cache run pytest tests/unit tests/integration -q
uv --cache-dir .uv-cache run pytest tests/dev02 -q
uv --cache-dir .uv-cache run pytest -q
git diff --check
```

Final closeout results:

- original DEV-01 tests: 43 passed in 0.33 s
- new DEV-02 tests: 66 passed in 1.37 s
- complete suite: 109 passed in 1.78 s
- skips/xfails/type-ignore/noqa suppression scan: no matches
- formatting: 49 files already formatted
- Ruff: all checks passed
- strict mypy: no issues in 36 source files
- Schema consistency: PASS for all eight exports
- Git whitespace diff: PASS

The first new-test execution intentionally surfaced real issues: strict mypy reported CLI branch-variable type reuse plus imprecisely typed test kwargs, and pytest reported 60 passed/2 failed because one error-message regex used the wrong case and a test hardcoded an incorrect N1 position. Variables/kwargs were typed explicitly, the message assertion was corrected, and the delay test now reads the test manifest. Earlier static checks also found an unused import, redundant casts, a literal typing issue, a long line and NumPy scalar typing; each was corrected without ignores. Later contract tightening increased the final new-test count from 62 to 66. The first staged whitespace check then found four YAML EOF blank lines and intentional Markdown hard-break spaces in the exact prompt source; the YAML blanks were removed and the prompt was stored as binary. Its index blob and attachment blob both equal `5ebd6d2684f8137363b2a9b6735a439bffb4265b`, and the repeated staged check passed.

## DEV-01.01 byte regression

`git diff --exit-code` against the baseline reported no change for all ten protected files. SHA256 results remained:

- V1.3 ZIP: `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest: `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- sidecar: `56451970acb5505fc2bdb59eeabf8ccb099ba89537d208be95cfda39fd18b99e`
- device Schema: `1d375b22cd0d94fd22b9ae869d833cece9b05b7013e9a2b1409c380ff5ffe75b`
- package audit/review: `735823bb92f5aef9c897fdbf67fe1c9c3b6962ed8e423d7949f37c5ab4103c29` / `16d5c7df0b6b634715071d1b257e022df67e90ba3865fda0c9f643450e3c24d`
- calibration JSON/Markdown: `f2e7f2877bb3ead60d83c0fdcbbf92d7390bc2a6a6bf54b91d2558e2fa86c167` / `bbf3843be4a2b0ce7206567905bfb5b1b6716293ed659092ba00134e33369ad3`
- DEV-01 prompt/report: `875e66f45c4a6c2810cb23ca3032517cb4e09d81938d60f6a1759ed0975e6c2e` / `a11412c2acca963002b8dc6f1823a939dd0c9609552ccd6a3ba34d0a76f0386b`

The implementation-log diff contains only the appended DEV-02.01 section; the DEV-01.01 section is unchanged.

## Limits, exclusions and next interfaces

This step does not enumerate sound cards, play/record audio, implement formal ESS, latency calibration, deconvolution, impulse responses, transfer functions, formal QC, matrix generation, protocol execution, models, cross-validation, UI, database, CAD changes, geometry lock or experiment-ready status. The synthetic approximation excludes full waveguide modes, real end reflections, roughness, leakage, transducer response and nonlinearities. It cannot establish real acoustic validity or separability.

DEV-03.01 can reuse strict `load_config`/`load_bundle`, generated model Schemas, the Session/Reassembly/Run/Artifact contracts, `ImmutableSessionStore`, channel-first NPZ validation and explicit provenance guards. No DEV-03.01 work was performed.
