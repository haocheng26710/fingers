# Acoustic Ladder

本仓库当前只实现 `DEV-01.01`：安全接入实际打印的 Acoustic Ladder V1.3 模型包，审计字段来源，保存用户确认校准记录，并生成仍为 provisional 的 device manifest。

当前状态固定为：

- `model_status = provisional`
- `physical_print_status = actual_printed`
- `calibration_status = applied`
- `release_role = calibrated_printed_candidate`

本项目不会导入或执行 ZIP 内 Python，也不会解压或重建 CAD。它不包含音频采集、ESS、信号处理、实验协议、分类器、界面或最终几何锁定。

## 环境安装

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。依赖由 `uv.lock` 锁定：

```powershell
uv --cache-dir .uv-cache sync --all-groups --frozen
```

## 输入

仓库内真实包：

```text
reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip
```

预期且实际计算的 SHA256：

```text
1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b
```

## 可复现命令

以下命令均从仓库根目录运行。

规范化用户校准记录：

```powershell
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package normalize-calibration reference/calibration/V1_3_user_calibration_record.json --output-json reference/calibration/V1_3_user_calibration_record.json --output-markdown reference/calibration/V1_3_user_calibration_record.md
```

审查真实 ZIP：

```powershell
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package inspect reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip --calibration reference/calibration/V1_3_user_calibration_record.json --output reference/model_reviews/V1_3_package_audit.json
```

生成 provisional manifest 和稳定哈希：

```powershell
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package generate reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip --calibration reference/calibration/V1_3_user_calibration_record.json --output config/devices/device_manifest.provisional.json --sidecar config/devices/device_manifest.provisional.sha256
```

验证 Schema 与 sidecar：

```powershell
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package validate config/devices/device_manifest.provisional.json --schema schemas/device_manifest.schema.json --sidecar config/devices/device_manifest.provisional.sha256
```

单独重新计算 sidecar：

```powershell
uv --cache-dir .uv-cache run python -m acoustic_ladder.model_package hash config/devices/device_manifest.provisional.json --sidecar config/devices/device_manifest.provisional.sha256
```

单元测试、真实包集成测试、完整测试与静态检查：

```powershell
uv --cache-dir .uv-cache run pytest tests/unit
uv --cache-dir .uv-cache run pytest tests/integration
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
```

manifest 是 UTF-8、稳定键排序、LF 换行的确定性 JSON，不包含本机绝对路径、随机时间或临时值。包审查 JSON 包含真实扫描时间，因此审查文件本身不承诺字节确定性。
