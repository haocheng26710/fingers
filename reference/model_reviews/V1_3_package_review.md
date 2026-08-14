# Acoustic Ladder V1.3 Package Review

## Review identity

- Sequence: `DEV-01.01`
- Package: `Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip`
- Computed SHA256: `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- Decision: accepted as a `calibrated_printed_candidate` for a provisional manifest only
- Execution policy: every ZIP entry was read as data; none of the 12 packaged Python files was imported or executed; no CAD was rebuilt

The machine-readable evidence, including all 85 entry paths, compressed and uncompressed sizes, per-entry SHA256 values, categories, required flags, read results and path-safety flags, is in `V1_3_package_audit.json`.

## Safety and completeness

- Absolute paths: none
- Parent traversal paths: none
- Duplicate normalized paths: none
- Unreadable entries: none
- Missing required reports or sources: none
- Formal part types: 22
- STL files: 22
- part STEP files: 22
- assembly STEP files: 4
- print batches: 8
- calibration coupon files: 0
- Package completeness report: PASS
- Printability audit: PASS
- Full mechanical validation: 254 PASS, 0 WARNING, 0 FAIL

All required JSON files parsed as JSON objects. Both BOM files and the UTF-8-SIG print-batch CSV parsed successfully. The audit records their keys, columns and row counts.

## Active source selection

The active geometry is `Acoustic Ladder V1.3 Calibrated Round Main Tube`. `V1.2 equal-area round main tube` is retained only as `source_geometry` history. Active values come from `params_calibrated_v1_3.json`, `calibration_applied_v1_3.json`, the calibrated BOM and other V1.3 reports according to the declared priority order.

Verified active facts include:

- 400 mm total acoustic length; two 200 mm segments; 20 mm TX/RX centre spacing
- round lumen diameter `5.0657870100038425 mm`
- node positions N1–N6 at `50, 105, 165, 235, 310, 360 mm`
- stage-four suggestion N1, N3, N4 and N6
- B40/B32/B28 target apertures `4.0/3.2/2.8 mm`
- B40/B32/B28 CAD-compensated apertures `4.15/3.35/2.95 mm`
- all post-print aperture measurements remain `null`
- BLK residual dead-cavity length `0.45 mm`; BLK means closed, never open
- calibrated module/joint/end offsets `0.00/-0.14/-0.08 mm`
- acoustic-hole compensation `+0.15 mm`; slider clearance `0.20 mm` per side
- selected wedge M with `0.00 mm` preload offset

## Explicit conflicts

1. `BOM_WEDGE_QUANTITY_CONFLICT`: the calibrated BOM specifies M/L/H quantities `4/0/0`; `source/bom.py` specifies `4/1/1`. The calibrated BOM wins by declared priority.
2. `ACTIVE_LUMEN_LABEL_CONFLICT`: `derived_acoustics_v1.json` retains the historical field label `main_teardrop`; the V1.3 source geometry identifies the active lumen as round. The historical label never changes the active shape.

## Retained warnings

1. `DERIVED_FIELD_NAME_MAIN_TEARDROP`
2. `LEGACY_REPORT_TITLES`
3. `SOURCE_BOM_WEDGE_QUANTITY_MISMATCH`
4. `MISSING_ACOUSTIC_CALCS_SOURCE`
5. `MISSING_BUILD_V1_SOURCE`
6. `CAD_REBUILD_ENVIRONMENT_NOT_LOCKED`
7. `RAW_CALIBRATION_MEASUREMENTS_MISSING`
8. `ACTUAL_PRINT_FIELDS_INCOMPLETE`
9. `LEAK_AND_SPECTRAL_TESTS_UNRECORDED`

These warnings do not block a provisional manifest, but they do block treating the ZIP as a complete, version-locked CAD rebuild environment or treating the device as experiment-ready.

## Missing information

The package omits `source/acoustic_calcs.py`, `source/build_v1.py`, a locked CAD rebuild environment and raw coupon measurements. The user record intentionally preserves unknown printer, material, slicer, process, environment, measurement-tool, post-processing, leak-test and spectral-repeatability fields as explicit `null` values. They are carried into the manifest `missing_information` list.

## Review conclusion

The package is internally consistent for ingestion and matches its completeness, printability and mechanical-validation summaries. It is suitable as the only active V1.3 package source for `device_manifest.provisional.json`. It is not a geometry lock, an experiment-ready declaration or permission to execute/rebuild package source.
