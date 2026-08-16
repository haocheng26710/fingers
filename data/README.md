# Data roots

Do not commit generated sessions here. Runtime synthetic and real data must use separate, non-overlapping roots supplied by the operator. The synthetic CLI accepts only `--synthetic-root` and cannot select a real root.

For reproducible interface testing, use a fresh directory under the operating-system temporary directory as shown in the repository README. A session/run ID is immutable once published; validation recomputes artifact hashes and rejects incomplete or tampered data.

DEV-03.03 offline ESS fixtures follow the same separation rule but are not sessions or real data. Supply a dedicated temporary `development-root`; each artifact ID is create-only and its WAV/metadata bundle is regenerated during validation. Never point the development fixture command at a real-data root. Offline fixtures are not measurements, formal inputs, or authorized playback material.
