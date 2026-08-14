# Domain model

The persistent hierarchy is Session → Reassembly → MeasurementRun → ArtifactRef. A SessionRecord fixes origin, mode, manifest/config references and immutable identity. ReassemblyRecord describes an assembly boundary and related runs. MeasurementRunRecord carries a complete node-state map, timing, config hashes, backend, status and artifact references. ArtifactRef contains only a portable relative path, digest, byte size, format, optional shape/dtype, creator and immutable flag.

DataOrigin is only `synthetic` or `real`. RunMode is an independent axis: `formal`, `diagnostic` or `development`. The model therefore cannot conflate diagnostic intent with data provenance. Every synthetic run must be development mode, must have `formal_eligible: false`, and must carry `NOT_EXPERIMENTAL_RESULT`.

NodeState is intentionally generic: node/state/module IDs, state type, optional discrete label, optional continuous value plus unit, loading direction, proxy flag and provenance/notes. Continuous value and unit appear together or remain null. It is not coupled to a future loading mechanism.

All domain models reject unknown fields. Persistent paths reject absolute paths, `..`, empty/current-directory components and Windows/POSIX escape forms. Machine-specific absolute paths are never serialized.
