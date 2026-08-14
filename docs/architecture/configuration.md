# Configuration architecture

DEV-02.01 separates five independently attributable inputs. `device_manifest` is the verified provisional physical-device description; `audio_config` contains acquisition-interface intent; `protocol_config` describes a stage draft without executing a matrix; `analysis_config` preserves downstream analysis decisions; and optional `synthetic_config` controls interface-test generation only.

YAML is loaded with ruamel.yaml's safe, pure loader. Duplicate keys and custom tags are rejected before Pydantic v2 validates strict types and forbids unknown fields. Errors include field paths. Unknown hardware identifiers, timing/gain values, protocol repeat counts, analysis features and decision thresholds remain `null`.

Each ConfigSnapshot records the repository-relative source path, SHA256 of the original bytes, SHA256 of canonical sorted JSON, and validation status. The bundle additionally records the verified manifest SHA256 and a content digest over normalized layer hashes. `loaded_at` is timezone-aware provenance but is deliberately excluded from the content digest. Protocol manifest reference and digest must match the manifest actually loaded.

AudioConfig can represent N outputs and M inputs at the type level. The formal-mode validator narrows that general representation to exactly one `TX_speaker` output and one `RX_microphone` input, with no diagnostic reference channel. The present draft leaves hardware fields null and therefore has `hardware_ready: false`.

All Stage 1–4 protocol files are formal-mode drafts with closed far ends, BLK at unselected nodes and `execution_ready: false`. Stage 4 resolves its selected nodes at load time from the supplied manifest recommendation; neither node positions nor the recommended list are embedded in Python. No measurement matrix or randomization engine exists in this step.

The eight committed JSON Schemas are exported directly from active Pydantic models. Run `acoustic-ladder export-schemas --output-dir schemas --check` to detect drift.
