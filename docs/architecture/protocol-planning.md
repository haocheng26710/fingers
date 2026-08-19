# Development protocol planning

DEV-05.01 compiles the verified provisional V1.3 manifest, one Stage 1–4 formal draft `ProtocolConfig`, and a strict development fixture spec into an immutable plan. It never executes that plan. Formal repeats, reassemblies, sessions and random seed remain unknown; `execution_ready`, hardware I/O, formal eligibility and experimental-result states remain false.

## Authority and derivation

The public loader accepts one repository-relative development spec and an already validated bundle. The compiler accepts that loaded spec, bundle and a safe plan ID. It does not accept conditions, NodeState values, measurement order, permutations, direct output paths, real roots, devices, channels, waveforms, thresholds, decisions, features or classifications. Before every compile or replay it rereads the manifest and sidecar, every bundle config, the source protocol and the plan spec, verifying raw and canonical provenance.

Every condition contains all manifest nodes. The unique protocol-defined BLK state fills every unselected node. Stage 1 produces one all-BLK baseline and every non-BLK state at every manifest node. Stage 2 applies all proxy state definitions to exactly one development-selected node. Stage 3 normalizes two selected nodes to manifest order and binds configured `00/10/01/11` labels. Stage 4 rejects spec-selected nodes and uses the manifest recommendation resolved by `ProtocolConfig`; empty labels are expanded by four-bit ascending binary enumeration. Production compiler code contains no current node list, bridge-module list or Stage 4 recommendation.

## Hierarchy and deterministic order

The hierarchy is `session → reassembly → condition block → continuous repeat`. Every reassembly contains the complete condition multiset. Repeats remain adjacent inside their condition block. The total is checked before schedule materialization and before any filesystem creation:

`condition_count × session_count × reassemblies_per_session × continuous_repeats_per_condition`.

When randomization is enabled, `sha256_ranked_condition_blocks` version `1.0.0` hashes canonical material containing its ID/version, development seed, protocol/spec/stage, session, reassembly and condition identity. Sorting by digest then condition ID is independent of Python or NumPy PRNG state. Disabling randomization requires a null seed and preserves canonical matrix order.

The committed development fixtures use 2 sessions, 2 reassemblies, 2 repeats and `dev0501-test-seed-v1`. Their 19/4/4/16 conditions produce 152/32/32/128 measurements. These are software-test values, not experiment recommendations.

## Immutable envelope and replay

`DevelopmentProtocolPlanStore` manages only `<development-root>/plans/plan_<id>/`. Its seven files are canonical compiled plan and sidecar, canonical receipt and sidecar, deterministic metadata, an aware-time outer record and the fixed completion marker. Publication is create-only with an exclusive cooperative lock, same-filesystem staging and atomic no-replace rename. It creates no session event because a plan is not a measurement session.

The validator rebuilds the matrix, hierarchy, SHA256-ranked order, plan, receipt, metadata and record; requires the exact file set and canonical sidecars/marker; and compares deterministic payloads byte-for-byte without writing. This is project-internal integrity evidence, not a signature, external witness or trusted timestamp.

## Research boundary

Operator confirmation remains pending. Stage 2 states are fixed-aperture proxies, not continuous deformation. Stage 3 does not calculate interaction residuals. Stage 4 does not perform classification. A planning CLI `PASS` means only compilation or replay succeeded. No real audio device is enumerated or opened, no calibration is applied, no protocol is executed and no experimental conclusion is produced.

DEV-05.02 consumes only a successfully replay-validated published plan and derives ordered rehearsal work orders directly from its `session_slots`; it does not alter the plan or rerandomize conditions. Plan publication and rehearsal publication remain separate roots and contracts. See `protocol-rehearsal.md`.
