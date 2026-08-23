# DEV-07.02 Report — Minimal Tkinter experiment wizard UI

## Result

The implementation provides a visible Chinese Tkinter development-demo wizard backed only by `FakeFullDuplexBackend`. It does not enumerate, connect, select, or open a real audio device and does not play, record, or calibrate audio.

## UI and responsibility boundary

- The persistent top area shows the project, `模拟演练 / FAKE BACKEND` mode, the exact no-hardware warning, Stage, Session, demo Reassembly, condition/repeat, and overall progress.
- Six node boxes display the canonical N1–N6 module IDs read from compiled conditions, with short BLK/B28/B32/B40 descriptions.
- Separate `[用户操作]` and `[程序执行]` sections expose three per-condition confirmations, controller state, last fake result, error, next action, and start/pause/resume/emergency/exit controls.
- `ExperimentWizardController` owns confirmation gates, two-repeat execution, condition advancement, pause boundaries, cancellation, errors, and recovery. `ExperimentWizardWindow` owns widgets and main-thread updates; capture runs on one worker thread and returns through a queue polled by `after()`.

## Plan and persistence

- Formal preview values are derived by the existing Stage 1–4 compiler: 19/4/4/16 conditions, 152/32/32/128 sweeps, 172 assembly confirmations, and 344 total sweeps.
- The executable plan is explicitly `development_demo`: three differing Stage 1 conditions and two repeats each, for six fake sweeps. No 344-sweep run was performed.
- Demo bytes are confined below `development/demo/<session-id>/`, which is ignored by Git. Each successful repeat reuses the DEV-07.01 create-only four-file bundle.
- Mutable `session_state.json` is atomically replaced from a same-directory temporary file. Recovery validates identity, data root, plan hash, fields, completed-condition prefix, confirmation types, and a safe controller boundary. Corrupt, incomplete, mismatched, or unexpected existing state is rejected without overwrite.
- A normal close saves a safe state. Closing during capture requests DEV-07.01 cancellation and waits for the worker to end before destroying the window.

## Start command

```powershell
uv run --frozen python -m acoustic_ladder.ui
```

Pass `--session-id <ID>` to select an existing demo and choose whether to resume it. An existing session is never silently replaced.

## Actual validation

- TDD was used for plan projection, confirmation gating, two-repeat execution, first/second failure, pause, deferred pause, emergency cancellation, recovery, state safety, and UI contracts. The first tests failed for missing APIs before their corresponding implementations were added.
- Authoritative directed pytest command covered 20 new DEV-07.02 tests, three selected DEV-07.01 fake/cancellation/create-only tests, four Stage condition compiler tests, and the four-parameter schedule test: `31 passed in 4.59s`.
- After suppression-free punctuation lint fixes, the affected UI contract subset passed again: `4 passed in 0.47s`.
- Tk smoke created a hidden window, built all widgets, called `update_idletasks()`, saved the safe state, and destroyed the window: `PASS Tk widget build smoke`. It did not start capture.
- Module entry help completed with exit 0: `uv run --frozen python -m acoustic_ladder.ui --help`.
- Ruff format check: `18 files already formatted`.
- Ruff lint initially reported import order, Chinese ambiguous punctuation, and one long line. Import/punctuation/layout were corrected without suppression; final result: `All checks passed!`.
- Strict mypy: `Success: no issues found in 6 source files`.
- An early `python -m pytest` used the system interpreter and failed collection because the package was not installed there; the locked `uv run --frozen pytest` command then passed. A PowerShell wildcard passed literally to pytest also produced `file or directory not found`; explicit paths were used thereafter.
- Pytest emitted the existing `.pytest_cache` permission warning, but all directed tests completed successfully. Task-local `.d702-*` test and GUI-smoke directories were resolved, scope-checked, and removed.
- Final review found that a reopened session cancelled during window close would otherwise remain terminal. Recovery now verifies every state-claimed repeat has the exact DEV-07.01 four-file bundle and maps a verified cancelled/error boundary back to `ready` or `between_repeats`; the directly affected emergency/recovery/state-safety set passed `8 passed in 1.85s`. Focused format/lint/mypy remained clean.

The full pytest suite, Schema consistency, 344-sweep rehearsal, 1.13 GB matrix generation, Stage 1–4 full analysis, and historical golden suite were intentionally not run, as required by DEV-07.02. No Schema changed.

## Known limits

This is a development rehearsal UI, not a real-hardware UI. It has no device discovery or selection, Host API/channel binding, real Stream, playback, recording, calibration/SPL, frozen playback level, formal QC thresholds, installer, or formal experiment authorization. Recovery is intentionally schema-1.0 only and has no migration framework. No experimental result or paper conclusion is produced.
