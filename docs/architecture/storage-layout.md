# Immutable storage layout

Synthetic and real roots are injected separately and must be distinct, non-overlapping paths. The synthetic-only API rejects real records and the synthetic CLI exposes no real-root option.

Each session is published as `session_<id>/` with `manifest/`, `protocol/`, `raw/`, `processed/`, `qc/`, `features/`, `models/`, `reports/`, `events/`, `session_record.json` and `SESSION_COMPLETE`. Raw and canonical normalized config snapshots are copied under `protocol/config/`; the verified manifest and sidecar are copied under `manifest/`.

Runs live at `raw/run_<id>/` and contain `run_record.json`, synthetic metadata/arrays when applicable, and `RUN_COMPLETE`. Files are create-only: bytes first go to a same-directory temporary file, are flushed, then are published without replacing an existing target. Session and run directories are built under same-filesystem staging names and renamed only after required files and completion marker exist. Any pre-publication failure removes staging, so no completed-looking target remains.

Existing session IDs, run IDs, artifacts and numbered event files fail rather than overwrite. Events use monotonically numbered create-only JSON files. Artifact validation confines the relative path to the selected session and recomputes byte size and SHA256. Session validation also validates every completed run and referenced artifact.

The immutable session record is not rewritten when a run is appended; the append-only event ledger and immutable run records capture that evolution. Callers that know a planned run set may place it in the initial SessionRecord.
