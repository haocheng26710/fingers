# DEV-06.03 report

## Result and scope

DEV-06.03 adds a static, synthetic-only export layer for DEV-06.02 research results. The public `acoustic_ladder.analysis.export_research_report` entry and `research-report-export` CLI validate the six-file research result directory and publish one new, create-only ten-file report directory. They do not retrain Stage 4, rebuild the measurement matrix, replay processing, or access audio hardware.

The input gate requires all six files, exact CSV columns, non-empty labels, positive counts, finite numeric values, consistent feature sets and stage row counts, matching synthetic/development/provisional identity, and the DEV-06.02 receipt hash bindings. Stage 2 computed and missing-continuous-label representations are mutually exclusive; a missing-label result containing fabricated trend fields is rejected. Existing output directories are rejected before publication.

## Exported report

Matplotlib uses the non-interactive `Agg` backend. Each of the following is emitted as a 300 DPI PNG and an SVG, with English labels and a visible `SYNTHETIC / PROVISIONAL` mark:

- `stage1_effects`: a zero-centered heatmap of node/bridge-state mean feature differences relative to matched BLK.
- `stage2_proxy`: descriptive proxy-state means when the continuous label is absent, with the title `Proxy / no continuous label`; only a result that actually contains computed OLS trends uses the slope chart.
- `stage3_interactions`: a zero-centered node-pair by feature interaction-residual heatmap.
- `stage4_confusion_matrix`: deterministic-class-order out-of-fold confusion matrices by the existing session and reassembly strategies, explicitly labelled as a synthetic development fixture.

The directory also contains `analysis_summary.md` and `report_manifest.json`. The Markdown records Stage 1–4 summaries, Stage 2 label availability, Stage 4 model parameters and per-strategy metrics, relative figure links, and the non-experimental boundary. The manifest binds the input research receipt hash, lists the generated files and runtime versions, and fixes `synthetic=true`, `provisional=true`, and `experimental_result=false`. No image sidecars or new Schema were introduced.

`matplotlib>=3.9,<4` is a direct dependency; the lock resolved Matplotlib 3.11.1. The exporter directs Matplotlib's cache to a task-safe temporary location before importing the library, avoiding dependence on a writable user profile cache.

## Tests and checks

Six new tests cover a successful small DEV-06.02 fixture export, all four PNG/SVG pairs and Markdown/manifest fields, missing required input, missing required CSV columns, the Stage 2 missing-label no-fabrication branch, existing-output rejection, and the CLI smoke path. The final combined targeted command ran those six tests together with the seven directly related DEV-06.02 tests: `13 passed in 6.54s`.

Changed-file Ruff format reported 4 files already formatted, Ruff lint passed, and strict mypy passed for 4 affected source/test files. `git diff --check` passed and the prohibited skip/xfail/noqa/type-ignore scan found 0 matches. Schema consistency was not run because no Schema or Schema registry changed.

The Stage 6 complete suite was run exactly once with the short `--basetemp=.d603all`: `909 passed in 2948.71s (0:49:08)`. It includes `test_synthetic_protocol_execution_full.py`, whose public matrix path asserts 344 rows and validates the complete synthetic measurement matrix. Per the prompt, no separate 344-row smoke and no second 1.13 GB matrix were generated. The short pytest root and task dependency cache were verified as direct workspace children and removed after the run.

Visual inspection of task-local fixture exports found the first Stage 4 multi-panel layout too tight. The layout was corrected with a wider canvas, square axes, wrapped strategy titles and a shared colorbar; regenerated Stage 1–4 and missing-label Stage 2 images were inspected before their temporary directories were removed. This was visual QA of synthetic fixtures only, not an experiment.

## Readiness and limitations

Stage 6 software workflow is complete and the project now waits for explicit real-hardware connection and authorization. The exporter reproduces feature IDs from DEV-06.02, but that result contract does not persist feature units, so it does not invent units. The complete suite covers construction and validation of the 344-row matrix, while the static exporter itself is exercised with the small deterministic fixture and is not separately run against a retained full DEV-06.02 output directory.

All reported values remain synthetic, development and provisional. Fixture accuracy is not device performance, and this work produces no formal experimental or acoustic conclusion. No real audio device was accessed, enumerated, connected, played, recorded, calibrated or otherwise operated.
