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

After fading, the active sweep is normalized by `10 ** (digital_peak_dbfs/20) / pre_normalization_peak`, then cast to float32. No DC removal, noise, implicit gain, or secondary normalization occurs. Metadata records the target and actual peak, pre-normalization peak, normalization factor, RMS, crest factor, mean/DC, min/max, and finite status.

The in-memory result is C-contiguous NumPy float32 with channel-first shape `[1, total_sample_count]`. Raw sample identity is the SHA256 of channel-first little-endian IEEE float32 bytes.

## WAV and metadata

`excitation.wav` is deterministic RIFF/WAVE with format tag 3 (IEEE float), one channel, the specification's sample rate, 32 bits per sample, a `fact` chunk, and no timestamps or host metadata. Its reader restores `[1, n] float32`; validation requires sample-by-sample equality with a fresh deterministic generation and byte equality with the canonical writer.

`excitation.metadata.json` is canonical sorted UTF-8 JSON with LF termination. It contains only repository-relative configuration provenance, both configuration hashes, the complete parsed specification, timing/counts, metrics, raw/WAV hashes, writer identity, fixed false safety flags, and `OFFLINE_GENERATION_ONLY_NOT_AUTHORIZED_FOR_PLAYBACK`. It contains no time, random UUID, username, host, absolute path, device index, Host API, channel binding, gain claim, or calibration claim. Both files have stable SHA256 sidecars.

## Create-only publication

An artifact ID accepts only ASCII letters, digits, hyphens, and underscores. The final path is one direct child of the explicitly supplied development root. All four files are first written and fsynced in a same-parent staging directory, internally validated, and then renamed as a complete directory under a create-only publication lock. Existing targets are never removed or overwritten; failure cleans only the staging directory created by that call.

Python does not expose a cross-platform no-replace directory rename primitive. On Windows the same-parent rename rejects an existing directory; on other platforms the cooperative lock plus immediate existence check provides the implemented best-effort boundary. The post-publication bundle is immediately revalidated. This is not claimed as an absolute atomicity guarantee against non-cooperating filesystem actors.

The current development fixture uses 48 kHz, 300–10,000 Hz, 0.25 s sweep, 0.01 s pre/post silence, 0.005 s fades, and -20 dBFS solely for automated tests. Those values are not copied into the incomplete formal configuration and are not safe-listening guidance.
