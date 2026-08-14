# Synthetic interface data

The generator is a transparent deterministic interface fixture, not a formal ESS, deconvolution, real acoustic simulator or experiment. It reads node positions and module target apertures from the verified device manifest. For node position `x` metres and configured speed-of-sound assumption `c`, delay is `2*x/c`. A non-BLK module contributes

`module_effect_scale * (aperture / maximum_aperture)^2 * exp(-propagation_loss_per_m * 2*x)`.

BLK contributes no delayed node weight; `baseline_coupling` supplies a simple direct baseline. Configurable Gaussian noise and multiplicative session/reassembly drift use an explicit NumPy SeedSequence derived from seed and indices. The default `343 m/s` is labelled as an assumption, not an environmental measurement.

Arrays are channel-first: `outputs[n_output_channels, n_samples]`, `inputs[n_input_channels, n_samples]`, and `synthetic_ir[n_input_channels, n_output_channels, n_ir_samples]`. The default is 1+1 and float32. NPZ entries are sorted with fixed ZIP metadata so identical inputs produce identical bytes. JSON metadata records seed, generator version, formulas, parameters, shapes/dtypes, per-node delays/weights, drift factors, `data_origin: synthetic`, `formal_eligible: false`, an empty claims list and `NOT_EXPERIMENTAL_RESULT`.

From a clean checkout, install the frozen environment and run the two synthetic commands in README using a fresh system-temporary root, then run `validate-session` and `validate-run`. Reusing a session or run ID intentionally fails.

Limitations are explicit: no complete waveguide modes, real end reflections, print roughness, leakage, speaker/microphone response or real nonlinearities. The output cannot validate real separability, structural effectiveness, classification performance or any experimental conclusion.
