# Acoustic Ladder

本仓库当前实现到 `DEV-02.01`：在 DEV-01.01 的 V1.3 模型包审计与 provisional device manifest 基础上，提供严格分层配置、领域记录、不可覆盖文件存储，以及仅供接口测试的确定性 synthetic 数据。

当前状态固定为：

- `model_status = provisional`
- `physical_print_status = actual_printed`
- `calibration_status = applied`
- `release_role = calibrated_printed_candidate`

本项目不会导入或执行 ZIP 内 Python，也不会解压或重建 CAD。它仍不包含真实音频采集、正式 ESS、信号处理、协议矩阵执行、分类器、界面或最终几何锁定。synthetic 输出不是实验结果，不能证明真实结构有效。

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

## DEV-02 配置与 Schema

验证单层、完整 bundle、显示规范化哈希并核对已提交 Schema：

```powershell
uv --cache-dir .uv-cache run acoustic-ladder validate-config audio config/audio/default_1x1_ess.yaml --project-root .
uv --cache-dir .uv-cache run acoustic-ladder validate-bundle --project-root . --protocol config/protocols/stage4_four_node_states.yaml
uv --cache-dir .uv-cache run acoustic-ladder config-hash analysis config/analysis/default.yaml --project-root .
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
```

配置加载使用安全 YAML、拒绝重复键/自定义 tag/未知字段，并同时记录原文件哈希与稳定规范化 JSON 哈希。正式 AudioConfig 必须恰好 1 输出 + 1 输入；底层数组与类型仍可表达 N+M。

## Synthetic 存储示例

以下命令使用系统临时目录，synthetic CLI 没有 real 根目录参数。它创建完整 session、一个标记为 `NOT_EXPERIMENTAL_RESULT` 的 run，并验证 session、run 与 artifact：

```powershell
$syntheticRoot = Join-Path $env:TEMP 'acoustic-ladder-dev02-example\synthetic'
uv --cache-dir .uv-cache run acoustic-ladder create-synthetic-session --project-root . --protocol config/protocols/stage4_four_node_states.yaml --synthetic-root $syntheticRoot --session-id example001 --reassembly-id reassembly001
uv --cache-dir .uv-cache run acoustic-ladder generate-synthetic-run --project-root . --protocol config/protocols/stage4_four_node_states.yaml --synthetic-root $syntheticRoot --session-id example001 --reassembly-id reassembly001 --run-id run001 --node-state N1=B40
uv --cache-dir .uv-cache run acoustic-ladder validate-session --synthetic-root $syntheticRoot --session-id example001
uv --cache-dir .uv-cache run acoustic-ladder validate-run --synthetic-root $syntheticRoot --session-id example001 --run-id run001
```

`verify-artifact` 接受 session 根目录及单个 ArtifactRef JSON：

```powershell
uv --cache-dir .uv-cache run acoustic-ladder verify-artifact --session-root <session-root> --artifact-ref <artifact-ref.json>
```

代码层事件追加接口固定为 `append_event(DataOrigin, session_id, event, payload)`；session 路径只能由已注入的 synthetic/real 根推导，调用者不能提供任意文件系统路径。事件名只接受安全 ASCII 标识字符，系统事件字段不可由 payload 覆盖。

详细契约见 `docs/architecture/`；数据根目录政策见 `data/README.md`。

单元测试、真实包集成测试、完整测试与静态检查：

```powershell
uv --cache-dir .uv-cache run pytest tests/unit
uv --cache-dir .uv-cache run pytest tests/integration
uv --cache-dir .uv-cache run pytest tests/dev02
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
```

manifest 是 UTF-8、稳定键排序、LF 换行的确定性 JSON，不包含本机绝对路径、随机时间或临时值。包审查 JSON 包含真实扫描时间，因此审查文件本身不承诺字节确定性。
