# Development protocol rehearsal ledger

DEV-05.02 is a development-only, offline state-machine rehearsal of an already published DEV-05.01 plan. It is neither protocol execution nor a measurement. Every persisted manifest, record, event, completion, work order and returned status keeps `development_rehearsal=true`, physical operator confirmation pending, and all protocol-execution, measurement, hardware-I/O, readiness, formal-eligibility and experimental-result flags false. No audio device, calibration, session, run, waveform, processing, QC, threshold, decision or classification is part of this contract. DEV-05.03 is not implemented.

## Authority and work orders

Initialization, read, transition and validation first invoke the public DEV-05.01 plan validator. That validator rereads the current manifest and sidecar, bundle configuration, formal draft protocol, development plan spec, compiled plan, sidecars, receipt, metadata, record, exact seven-file envelope and completion marker. A changed source or plan therefore makes an existing rehearsal fail closed; it is never silently rebound.

Work orders are derived only by walking the validated compiled plan's `session → reassembly → condition block → measurement` hierarchy. They bind plan/receipt identities, stage, global and local order, session/reassembly/block/repeat indices, condition identity and role, full NodeState map, selected nodes/modules, operator requirements and safety state. Their SHA256 covers canonical deterministic core bytes and excludes paths, clocks, process/thread identity and caller data. No PRNG is called and the schedule is not rerandomized.

## State machine

An initialized ledger is `active` at cursor zero with phase `awaiting_requirements_presentation`. The normal path is `present-requirements → claim → mark-rehearsed`; only the final action advances the cursor. The next order returns to awaiting presentation, and only the last order produces `complete` plus the completion envelope.

Pause is allowed only while awaiting or after requirements presentation, and resume restores that phase. A claimed order can become failed with a safe reason code; retry keeps the same cursor and work-order identity but requires requirements to be presented again. Abort records a safe reason and is terminal. Claimed work cannot pause, failed/paused work cannot advance, and aborted/complete ledgers accept no further transition.

Transition commands carry only an action, safe actor, expected event sequence, expected head hash, expected current work-order hash, and failure/abort detail where applicable. The complete concurrency token also binds the rehearsal ID. Under the exclusive transition lock, the store revalidates the plan and full ledger before checking the token, so concurrent requests can publish at most one next event and the loser is stale/unpublished.

## Immutable envelope and recovery

The store owns `<development-rehearsal-root>/rehearsals/rehearsal_<id>/`. Initialization uses a same-filesystem staging directory, exclusive create-only lock and no-replace directory rename. The exact base contains manifest/record JSON and canonical SHA256 sidecars, `REHEARSAL_INITIALIZED` with fixed bytes, and `events/`. Safe ID validation, resolved containment and symlink/junction/reparse rejection prevent caller-selected escape paths.

Each transition publishes canonical `event_<eight-digit-sequence>.json` and its sidecar create-only. Sequences start at one and are continuous. An event binds the previous canonical event SHA256, current plan and work-order, actor, before/after state and phase, cursor, reason/detail, injected aware time and safety flags. No mutable current-state file exists; status is reconstructed by strict replay. Controlled pre-publication failures remove only their owned staging/lock and leave no half pair. If a full event has already been published and a later outer step fails, the error reports `published=true` and preserves that event.

Completion exists only after every planned work order is rehearsed. It binds expected/rehearsed counts, final sequence/head, the ordered aggregate of every event digest, plan/receipt/schedule hashes, completion state and safety flags. `read_protocol_rehearsal_status` and `validate_protocol_rehearsal` are read-only: they create no lock, repair no bytes, and verify the exact file/type set, fixed markers, strict canonical models, sidecars, current plan binding, event sequence/hash chain/state replay, work-order derivation and completion.

## Integrity boundary

The local SHA256 chain is project-internal tamper evidence, not a digital signature, external witness, non-repudiation mechanism or trusted timestamp. It detects modifications, deletions, insertions and reorderings that are referenced by a later event or completion. Without an external witness, deletion of the last unreferenced tail of an active ledger cannot be proven externally. Injected aware times make deterministic tests possible but are not trusted time.
