# V1.3 User-Confirmed Calibration Record

- Source type: `user_confirmed_measurement_record`
- Confirmation date: `2026-08-14`
- Confirmation time: `null` (not provided)
- Rule: user-confirmed facts only; every unknown remains explicit `null`.

## Module dry-seal interface

```json
{
  "applied_parameter": "MODULE_DRY_SEAL_DIAMETRAL_INTERFERENCE",
  "applied_value_mm": 0.0,
  "conclusion": "0.00 mm 公头与母座配合合适。",
  "coupon": "ALV1_coupon_module_dry_seal_print.stl",
  "selected_offset_mm": 0.0
}
```

## End dry-seal interface

```json
{
  "applied_parameter": "END_DRY_SEAL_DIAMETRAL_INTERFERENCE",
  "applied_value_mm": -0.08,
  "coupon": "ALV1_coupon_end_dry_seal_print.stl",
  "observations": [
    "原公头无法完全插到底。",
    "-0.04 mm 公头仍无法插到底。",
    "-0.08 mm 公头配合比较合适。"
  ],
  "selected_offset_mm": -0.08
}
```

## Split-joint dry-seal interface

```json
{
  "applied_parameter": "JOINT_DRY_SEAL_DIAMETRAL_INTERFERENCE",
  "applied_value_mm": -0.14,
  "corrected_socket_coupon": "ALV1_coupon_split_joint_socket_corrected_keyed_vented_print.stl",
  "key_height_mm": 1.0,
  "key_slot_radial_center_mm": 4.7,
  "key_slot_radial_height_mm": 1.6,
  "key_slot_width_mm": 1.0,
  "key_width_mm": 0.8,
  "observations": [
    "原校准件母座缺少匹配键槽，旧公头不能正确装配。",
    "修正版母座增加防转键槽和排气孔。",
    "-0.12 mm 公头末端仍然很紧，难以拔出。",
    "用户实测认为折中的 -0.14 mm 最适配。"
  ],
  "selected_offset_mm": -0.14
}
```

## Bridge and acoustic-hole compensation

```json
{
  "applied_parameter": "FDM_ACOUSTIC_HOLE_COMPENSATION",
  "applied_value_mm": 0.15,
  "conclusion": "当前孔径已经足够准确。",
  "coupon": "ALV1_coupon_bridge_holes_print.stl",
  "measured_diameters_mm": [
    null,
    null,
    null,
    null,
    null
  ],
  "target_diameters_mm": [
    2.8,
    3.2,
    4.0,
    4.2,
    5.0
  ]
}
```

## Slider and wedge

```json
{
  "applied_parameter": "SUPPORT_GUIDE_CLEARANCE_PER_SIDE",
  "coupons": [
    "ALV1_coupon_slider_A_base_print.stl",
    "ALV1_coupon_slider_B_slider_print.stl",
    "ALV1_coupon_slider_C_wedge_set_LMH_print.stl"
  ],
  "guide_clearance_per_side_mm": 0.2,
  "observations": [
    "A 与 B 能够正常适配。",
    "滑块能够在导轨内使用。",
    "L/M/H 中选择 M 楔块。"
  ],
  "selected_wedge": "M",
  "selected_wedge_preload_offset_mm": 0.0
}
```

## Actual print record

This is distinct from the package design recommendation below.

```json
{
  "build_plate": "Bambu Textured PEI Plate",
  "calibration_test_date": null,
  "environment": {
    "humidity_percent": null,
    "temperature_c": null
  },
  "fit_cycle_counts": {
    "end_interface": null,
    "module_interface": null,
    "split_joint_interface": null
  },
  "material": {
    "batch": null,
    "brand": null,
    "color": null,
    "dried": null,
    "drying_duration_h": null,
    "drying_temperature_c": null,
    "model": null,
    "type": null
  },
  "measurement": {
    "tool": null,
    "tool_accuracy": null
  },
  "operator": null,
  "physical_print_status": "actual_printed",
  "post_processing": {
    "actual_material_removed": null,
    "deburring_tool": null,
    "permitted_principle": "minor_deburring_only",
    "sandpaper_specification": null
  },
  "print_date": null,
  "printer": {
    "brand": "Bambu Lab",
    "firmware_version": null,
    "model": null
  },
  "settings": {
    "automatic_orientation_enabled": null,
    "bed_temperature_c": null,
    "bottom_layers": null,
    "brim_width_mm": null,
    "elephant_foot_compensation_mm": null,
    "first_layer_speed_mm_s": null,
    "flow_ratio": null,
    "infill_pattern": null,
    "infill_percent": null,
    "layer_height_mm": null,
    "line_width_mm": null,
    "nozzle_diameter_mm": null,
    "nozzle_temperature_c": null,
    "other_slicer_settings": null,
    "pressure_advance_or_flow_dynamics": null,
    "print_speed_mm_s": null,
    "seam_position": null,
    "support_settings": null,
    "top_layers": null,
    "wall_count": null
  },
  "slicer": {
    "name": "Bambu Studio",
    "version": null
  },
  "verification": {
    "low_pressure_leak_test": {
      "method": null,
      "performed": null,
      "result": null
    },
    "spectral_repeatability_test": {
      "method": null,
      "performed": null,
      "result": null
    }
  }
}
```

## Design recommendation (not an actual print setting)

```json
{
  "layer_height_range_mm": [
    0.16,
    0.2
  ],
  "material": "PLA/PLA+",
  "nozzle_diameter_mm": 0.4,
  "source": "reports/params_calibrated_v1_3.json",
  "wall_count": 5
}
```

## Required unknown fields

- `/confirmation_time`
- `/actual_print_record/printer/model`
- `/actual_print_record/printer/firmware_version`
- `/actual_print_record/material/type`
- `/actual_print_record/material/brand`
- `/actual_print_record/material/model`
- `/actual_print_record/material/color`
- `/actual_print_record/material/batch`
- `/actual_print_record/material/dried`
- `/actual_print_record/material/drying_temperature_c`
- `/actual_print_record/material/drying_duration_h`
- `/actual_print_record/slicer/version`
- `/actual_print_record/settings/nozzle_diameter_mm`
- `/actual_print_record/settings/layer_height_mm`
- `/actual_print_record/settings/line_width_mm`
- `/actual_print_record/settings/wall_count`
- `/actual_print_record/settings/top_layers`
- `/actual_print_record/settings/bottom_layers`
- `/actual_print_record/settings/infill_percent`
- `/actual_print_record/settings/infill_pattern`
- `/actual_print_record/settings/nozzle_temperature_c`
- `/actual_print_record/settings/bed_temperature_c`
- `/actual_print_record/settings/print_speed_mm_s`
- `/actual_print_record/settings/first_layer_speed_mm_s`
- `/actual_print_record/settings/flow_ratio`
- `/actual_print_record/settings/pressure_advance_or_flow_dynamics`
- `/actual_print_record/settings/elephant_foot_compensation_mm`
- `/actual_print_record/settings/support_settings`
- `/actual_print_record/settings/brim_width_mm`
- `/actual_print_record/settings/seam_position`
- `/actual_print_record/settings/automatic_orientation_enabled`
- `/actual_print_record/settings/other_slicer_settings`
- `/actual_print_record/operator`
- `/actual_print_record/print_date`
- `/actual_print_record/calibration_test_date`
- `/actual_print_record/environment/temperature_c`
- `/actual_print_record/environment/humidity_percent`
- `/actual_print_record/fit_cycle_counts/module_interface`
- `/actual_print_record/fit_cycle_counts/end_interface`
- `/actual_print_record/fit_cycle_counts/split_joint_interface`
- `/actual_print_record/verification/low_pressure_leak_test/performed`
- `/actual_print_record/verification/low_pressure_leak_test/method`
- `/actual_print_record/verification/low_pressure_leak_test/result`
- `/actual_print_record/verification/spectral_repeatability_test/performed`
- `/actual_print_record/verification/spectral_repeatability_test/method`
- `/actual_print_record/verification/spectral_repeatability_test/result`
- `/actual_print_record/measurement/tool`
- `/actual_print_record/measurement/tool_accuracy`
- `/actual_print_record/post_processing/deburring_tool`
- `/actual_print_record/post_processing/sandpaper_specification`
- `/actual_print_record/post_processing/actual_material_removed`

Low-pressure leak and spectral-repeatability testing were not performed or recorded.
No result is inferred.
