# Offline ESS excitation contract

DEV-03.03 provides a deterministic software fixture for mathematics, persistence, schema, and CLI testing. It is not a measurement, formal experiment parameter, hearing-safety recommendation, calibration signal, or playback authorization. Every specification and artifact fixes `usage_scope=development_fixture`, `playback_authorized=false`, `formal_eligible=false`, `experimental_result=false`, and `hardware_ready=false`. The implementation imports no playback/recording API and does not enumerate or bind devices.

## Signal and sampling

For start frequency `f0`, end frequency `f1`, ratio `r=f1/f0`, sample rate `fs`, rounded sweep count `N`, and actual duration `T=N/fs`, the continuous phase is:

```text
phi(t) = 2*pi*f0*T/ln(r) * (exp(t*ln(r)/T) - 1)
x(t) = sin(phi(t))
t[n] = n/fs, n = 0, ..., N-1
```

The theoretical instantaneous frequency is `f0` at `t=0` and `f1` at the boundary `t=T`. The last stored sample is at `T-1/fs`, so its instantaneous frequency is below, not exactly equal to, `f1`.

Every non-negative duration is converted with `floor(seconds*fs+0.5)`. Metadata records requested duration, derived count, actual `count/fs`, and the error for sweep, silence, and fade fields. A nonzero fade must contain at least two samples. Half-cosine fades use inclusive endpoints: fade-in starts at exactly zero and fade-out ends at exactly zero. They affect only the active sweep; pre/post silence remains exact zero.

The rounded sweep count must also be at least two. This is a derived sample-count constraint rather than an arbitrary minimum number of seconds: zero samples cannot form a signal, and one sample is only `t=0`, where this sweep is zero. Because this relationship and the float32 rule below are runtime numeric/cross-field constraints, they remain Pydantic model validators rather than hand-written JSON Schema conditions.

After fading, the active sweep is normalized by `10 ** (digital_peak_dbfs/20) / pre_normalization_peak`, then cast to float32. No DC removal, noise, implicit gain, or secondary normalization occurs. Metadata records the target and actual peak, pre-normalization peak, normalization factor, RMS, crest factor, mean/DC, min/max, and finite status.

The target amplitude must be finite, positive, and remain positive after conversion to NumPy float32. This follows the actual float32 representation boundary instead of imposing an unexplained fixed minimum dBFS. The generator defensively repeats the target check and rejects non-finite/non-positive normalization, float32 peak, RMS, or crest factor with `EssError`; raw division-by-zero and non-finite metadata are not allowed. A mathematical 0 dBFS development spec remains expressible but is still not authorized for playback or claimed safe.

The in-memory result is C-contiguous NumPy float32 with channel-first shape `[1, total_sample_count]`. Raw sample identity is the SHA256 of channel-first little-endian IEEE float32 bytes.

## WAV and metadata

`excitation.wav` is deterministic RIFF/WAVE with format tag 3 (IEEE float), one channel, the specification's sample rate, 32 bits per sample, a `fact` chunk, and no timestamps or host metadata. Its reader restores `[1, n] float32`; validation requires sample-by-sample equality with a fresh deterministic generation and byte equality with the canonical writer.

`excitation.metadata.json` is canonical sorted UTF-8 JSON with LF termination. It contains only repository-relative configuration provenance, both configuration hashes, the complete parsed specification, timing/counts, metrics, raw/WAV hashes, writer identity, fixed false safety flags, and `OFFLINE_GENERATION_ONLY_NOT_AUTHORIZED_FOR_PLAYBACK`. It contains no time, random UUID, username, host, absolute path, device index, Host API, channel binding, gain claim, or calibration claim. Both files have stable SHA256 sidecars.

## Create-only publication

An artifact ID accepts only ASCII letters, digits, hyphens, and underscores. The final path is one direct child of the explicitly supplied development root. All four files are first written and fsynced in a same-parent staging directory, internally validated, and then renamed as a complete directory under a create-only publication lock. Existing targets are never removed or overwritten; failure cleans only the staging directory created by that call.

Python does not expose a cross-platform no-replace directory rename primitive. On Windows the same-parent rename rejects an existing directory; on other platforms the cooperative lock plus immediate existence check provides the implemented best-effort boundary. The post-publication bundle is immediately revalidated. This is not claimed as an absolute atomicity guarantee against non-cooperating filesystem actors.

The current development fixture uses 48 kHz, 300–10,000 Hz, 0.25 s sweep, 0.01 s pre/post silence, 0.005 s fades, and -20 dBFS solely for automated tests. Those values are not copied into the incomplete formal configuration and are not safe-listening guidance.

## Mathematical and persistence authority boundaries

`generate_ess(spec)` is a pure mathematical API. It accepts one explicit strict `EssSignalSpec` because it neither accepts nor records a configuration hash.

The public persistence APIs are different: `publish_offline_ess_artifact(development_root, artifact_id, loaded)` and `validate_offline_ess_artifact(artifact_root, loaded)` accept only a `LoadedConfig` as their configuration fact source. Each verifies that it is an audio configuration and internally calls `spec_from_audio_config(loaded.model)` before creating a root, staging directory, lock, or output. The CLI passes only that loaded configuration. Internal staging validation can receive the already-derived spec through a private function, but no caller-facing API can supply a second specification.

Once metadata declares source configuration hashes, its specification must equal the specification derived from that same loaded configuration. Validation regenerates the WAV from that derived specification, associates the raw hash with the decoded WAV, and rejects a metadata/config mismatch even if the modified metadata sidecar is recomputed.

DEV-03.03R adds an independent eight-sample reference calculated once with Python `Decimal` at 80-digit precision, an explicit 75-digit pi constant, Decimal `ln`/`exp`, and a separately implemented Taylor-series sine. The hard-coded phase, instantaneous-frequency, normalized float32 vector, and raw hash are checked at runtime without using production code to create the expected values. The original development fixture remains byte-identical at WAV `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`, metadata `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`, and raw float32 `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`.
