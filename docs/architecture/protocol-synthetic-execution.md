# Development synthetic protocol execution

DEV-05.03 consumes a replay-validated DEV-05.01 compiled plan and runs its Stage 1–4 development fixture entirely through deterministic software. It does not convert any formal draft to execution-ready status and does not treat DEV-05.02 rehearsal as operator confirmation or hardware authorization.

## Authority and deterministic identity

The public API accepts an execution ID, actor, full concurrency token, validated plan/spec/bundle/scenario/ESS sources, independent development roots and an aware clock. It never accepts a condition, NodeState, session/reassembly/measurement ordinal, run/capture ID, artifact digest, waveform, IR, gain, latency, real root, device, channel or experimental decision.

Work orders traverse compiled `session_slots → reassembly_slots → condition_blocks → measurements`. Each canonical order binds plan/receipt/schedule hashes, stage, global and local coordinates, condition identity/role, complete NodeState map and digest, selected nodes/modules and pending operator requirements. IDs are deterministic:

- session: `sx_<execution-id>_s<two-digit-session>`;
- reassembly: `sx_<execution-id>_s<session>_r<two-digit-reassembly>`;
- run and capture: `sx_<execution-id>_w<six-digit-global-ordinal>`.

No path, process, thread, machine, username, UUID or current time contributes to these identities. Execution IDs are safe ASCII identifiers of at most 32 characters.

## Plan-bound capture

The plan-bound capture layer revalidates the synthetic scenario and ESS artifact, requires mono float32 at the configured sample rate, and calls the existing synthetic generator with the full plan-derived NodeState map plus session/reassembly indices. Its manifest-derived IR drives the existing causal block-wise FIR backend and `VirtualCaptureEngine`. The output reference and simulated input are stored as IEEE float32 WAV with SHA256 sidecars.

The strict capture receipt binds execution, plan, plan receipt, schedule, work-order, condition, NodeState, deterministic storage identities, bundle/manifest/protocol/synthetic config, scenario, ESS, synthetic IR, delays/weights, waveform hashes and block/state traces. The run record repeats the complete NodeState and config/work-order hashes. Both fast transition validation and full semantic replay require the exact immutable run envelope; full validation regenerates the IR, virtual capture, WAV, receipt and run record byte-for-byte.

This is a synthetic capture, not playback, recording, physical measurement, hardware full duplex or formal protocol execution. Every persisted contract keeps the corresponding flags false and uses `SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT`.

## Ledger and state machine

`DevelopmentSyntheticProtocolExecutionStore` owns only `<development-root>/executions/execution_<id>/`. Its initialized envelope contains canonical manifest/record pairs and sidecars, `SYNTHETIC_EXECUTION_INITIALIZED == b"initialized\n"`, and `events/`. Authority is reconstructed from that base plus continuous create-only `event_<eight-digit-sequence>.json/.sha256` pairs; there is no mutable `current.json`.

States are `active`, `paused`, `failed`, `recovery_required`, `aborted` and `complete`. A validated success advances exactly one cursor. Pause blocks capture; retry keeps the same work order; abort/complete are terminal. A complete execution adds canonical completion/sidecar and `SYNTHETIC_EXECUTION_COMPLETE == b"complete\n"`, binding counts, final event head and ordered run/event aggregates.

Every mutation takes an exclusive per-execution transition lock, performs plan/base/event/run replay before comparing the full token, then publishes. Concurrent init, execute and recovery therefore have at most one create-only winner; losers cannot advance the next order. Initialization, control, recovery and execute-next share one lock lifecycle: descriptor close and lock unlink are independent fallible I/O operations, both are attempted, and either failure is returned as a domain error rather than a raw filesystem exception.

## Cross-root recovery

The session/run tree and execution ledger cannot be committed atomically together. The coordinator uses deterministic run IDs and explicit adoption:

1. no run: execute and publish normally;
2. complete run without success event: read-only status returns capture `recovery_required`; explicit recovery fully replays it and appends exactly one success event;
3. partial, foreign, identity-mismatched or tampered run: fail closed without adoption or repair;
4. success event with missing/tampered run: read/status/validate reject;
5. final success without completion: status returns completion `recovery_required`; explicit recovery publishes only the validated completion.

Errors separately report `capture_published`, `ledger_event_published` and `completion_published`. These are persisted-state claims at the instant the exception returns, not in-memory records that a publisher was called or returned. A field is true only when a narrow read-only probe proves the complete target: semantic capture/run replay for capture, full ledger replay with the target event as the verified head for an event, and complete public status/ledger/run/envelope replay plus exact target comparison for completion. A private normalized-evidence state distinguishes a completed persistent probe from an ordinary domain error even when all three public booleans are false, so a previous in-memory `True` can never overwrite an unproven result. A publication helper may finish its create-only files and then raise; that case reports true. A missing sidecar, partial/non-canonical file, mismatched target or failed probe reports false and says the state was not proven. Valid capture/event publications that existed before explicit recovery are still reported true.

The probe never writes, deletes, cleans, completes or repairs storage. Original ordinary exceptions remain the error cause, while `KeyboardInterrupt`, `SystemExit` and other `BaseException` values are not swallowed. Lock acquisition is a separate boundary, so only failure to acquire an existing transition lock is reported as concurrency; a publisher's later `FileExistsError` is evaluated as a publication failure. If close or unlink fails after a mutation, the final publication booleans are probed again from durable storage and the error records both the mutation and cleanup facts. An unlink failure leaves the actual lock in place for audit; status and validation do not remove it, and later mutations are rejected. There is no automatic stale-lock takeover, force deletion or permission repair. Control events never claim capture or completion publication for that control operation. Read-only entry points create no roots, locks, staging, events, completion or capture and never repair bytes.

## Development fixture result and limits

The committed plans derive 152/32/32/128 work orders for Stage 1–4. The full acceptance test executes all 344 orders in each of two independent roots and compares canonical execution/session/capture trees byte-for-byte. These counts, repeats, reassemblies, sessions and seed are software fixtures, not formal protocol recommendations. Stage 2 remains a proxy-state exercise; Stage 3 produces no interaction residual; Stage 4 performs no classification. The hash chain is internal integrity evidence, not a signature, external witness or trusted timestamp.
