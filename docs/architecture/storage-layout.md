# Immutable storage layout

Synthetic and real roots are injected separately and must be distinct, non-overlapping paths. The synthetic-only API rejects real records and the synthetic CLI exposes no real-root option.

Each session is published as `session_<id>/` with `manifest/`, `protocol/`, `raw/`, `processed/`, `qc/`, `features/`, `models/`, `reports/`, `events/`, `session_record.json` and `SESSION_COMPLETE`. Raw and canonical normalized config snapshots are copied under `protocol/config/`; the verified manifest and sidecar are copied under `manifest/`.

Runs live at `raw/run_<id>/` and contain `run_record.json`, synthetic metadata/arrays when applicable, and `RUN_COMPLETE`. Files are create-only: bytes first go to a same-directory temporary file, are flushed, then are published without replacing an existing target. Session and run directories are built under same-filesystem staging names and renamed only after required files and completion marker exist. Any pre-publication failure removes staging, so no completed-looking target remains.

Synthetic ESS processing lives at `processed/run_<source_run_id>/processing_<processing_id>/`. The store derives this path from its injected synthetic root and validated session/source run; callers cannot provide a filesystem target or choose the real root. A processing directory contains only `processing_arrays.npz` and sidecar, `processing_receipt.json` and sidecar, `processing_metadata.json`, `processing_record.json`, and `PROCESSING_COMPLETE`. Publication uses a same-filesystem staging directory plus a cooperative create-only lock; a competing or existing target is never replaced, and only the caller-owned staging/lock is cleaned on failure.

Existing session IDs, run IDs, artifacts and numbered event files fail rather than overwrite. Events use monotonically numbered create-only JSON files. Artifact validation confines the relative path to the selected session and recomputes byte size and SHA256. Session validation also validates every completed run and referenced artifact.

The public event API is `append_event(origin, session_id, event, payload)`. It never accepts a caller-selected session filesystem path: the store derives the resolved session from its injected DataRoots, verifies root containment, `SESSION_COMPLETE`, SessionRecord identity/origin and the resolved events directory before writing. Event names are restricted to ASCII letters, digits, hyphens and underscores. Payloads cannot replace the system-owned `event`, `sequence`, `session_id` or `data_origin` fields. A numbering race fails through the same create-only atomic publication and cannot replace the competing event.

The immutable session record is not rewritten when a run is appended; the append-only event ledger and immutable run records capture that evolution. Callers that know a planned run set may place it in the initial SessionRecord.
