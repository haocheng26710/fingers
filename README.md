# Acoustic Ladder

本仓库当前实现到 `DEV-03.04`：除模型包、配置、不可变存储、synthetic 接口数据和只读音频清单外，现提供严格的离线 ESS 开发夹具，以及基于显式状态机和确定性虚拟全双工后端的软件采集执行内核。DEV-03.04 只生成、持久化和语义重放验证 synthetic 原始采集，不增加真实硬件接入或后续实验功能。

当前状态固定为：

- `model_status = provisional`
- `physical_print_status = actual_printed`
- `calibration_status = applied`
- `release_role = calibrated_printed_candidate`

本项目不会导入或执行 ZIP 内 Python，也不会解压或重建 CAD。DEV-03.03 的 ESS 和 DEV-03.04 的虚拟采集只生成离线软件测试产物，绝不播放、录音、打开音频流或枚举新设备；-20 dBFS 测试值不是听力安全级别。`virtual_duplex_scheduler_exercised=true` 只表示软件调度器被执行，不表示 `full_duplex_verified=true`。项目仍不包含真实音频采集、正式 ESS 参数、反卷积/DSP、协议矩阵执行、分类器、界面或最终几何锁定。

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

## DEV-03 只读音频清单与预检

以下命令只枚举 host API/设备元数据，并用 `check_input_settings`、`check_output_settings` 分别检查 48 kHz、float32、单通道格式。它们不打开流：

```powershell
uv --cache-dir .uv-cache run acoustic-ladder audio-list
uv --cache-dir .uv-cache run acoustic-ladder audio-inventory --output reference/audio/inventory/DEV-03.01_audio_inventory.json --sidecar reference/audio/inventory/DEV-03.01_audio_inventory.sha256
uv --cache-dir .uv-cache run acoustic-ladder audio-preflight --inventory reference/audio/inventory/DEV-03.01_audio_inventory.json --inventory-sidecar reference/audio/inventory/DEV-03.01_audio_inventory.sha256 --hardware-setup reference/audio/hardware_setup.provisional.json --output reference/audio/inventory/DEV-03.01_preflight_report.json
uv --cache-dir .uv-cache run acoustic-ladder audio-validate --inventory reference/audio/inventory/DEV-03.01_audio_inventory.json --inventory-sidecar reference/audio/inventory/DEV-03.01_audio_inventory.sha256 --preflight reference/audio/inventory/DEV-03.01_preflight_report.json
```

`audio-list` 的默认设备名格式为 ASCII-only JSON string，并输出 `DEVICE_NAME_ENCODING=JSON_ASCII_ESCAPED`；标准 JSON 解码可无损恢复 Unicode 名称。所有命令均输出 `NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED`。

用户后来确认 DEV-03.01 枚举时 iMM-6C、竹 2 和实验装置均未连接。原 inventory 是 `development_host_baseline_without_experimental_hardware`，其中任何索引都不是实验设备候选，当前无需选择设备、Host API 或通道。绑定状态为 `deferred_until_hardware_connection`，`hardware_ready=false`。以下命令只读取并解释已有文件，不进行新枚举：

```powershell
uv --cache-dir .uv-cache run acoustic-ladder audio-inventory-summary --inventory reference/audio/inventory/DEV-03.01_audio_inventory.json --inventory-sidecar reference/audio/inventory/DEV-03.01_audio_inventory.sha256 --context reference/audio/inventory/DEV-03.02_inventory_capture_context.json --context-sidecar reference/audio/inventory/DEV-03.02_inventory_capture_context.sha256 --output reference/audio/inventory/DEV-03.02_audio_inventory_summary.md --output-sidecar reference/audio/inventory/DEV-03.02_audio_inventory_summary.sha256
uv --cache-dir .uv-cache run acoustic-ladder audio-context-validate --inventory reference/audio/inventory/DEV-03.01_audio_inventory.json --inventory-sidecar reference/audio/inventory/DEV-03.01_audio_inventory.sha256 --context reference/audio/inventory/DEV-03.02_inventory_capture_context.json --context-sidecar reference/audio/inventory/DEV-03.02_inventory_capture_context.sha256 --summary reference/audio/inventory/DEV-03.02_audio_inventory_summary.md --summary-sidecar reference/audio/inventory/DEV-03.02_audio_inventory_summary.sha256 --contextual-preflight reference/audio/inventory/DEV-03.02_contextual_preflight_report.json --contextual-preflight-sidecar reference/audio/inventory/DEV-03.02_contextual_preflight_report.sha256
```

该验证会重建 summary 和 contextual preflight，而不是只检查各文件自己的 sidecar；hardware setup、全部仓库相对引用和跨文件哈希也必须一致。

## DEV-03.03 离线 ESS 开发夹具

以下命令只在指定 development root 生成或只读验证四文件 artifact bundle。示例夹具明确为非正式、非实验、未授权播放；命令不会加载设备后端：

```powershell
$developmentRoot = Join-Path $env:TEMP 'acoustic-ladder-offline-ess'
uv --cache-dir .uv-cache run acoustic-ladder ess-generate-offline --project-root . --audio-config tests/fixtures/audio/ess_offline_development.yaml --development-root $developmentRoot --artifact-id dev_fixture
uv --cache-dir .uv-cache run acoustic-ladder ess-validate-offline --project-root . --audio-config tests/fixtures/audio/ess_offline_development.yaml --artifact-root (Join-Path $developmentRoot 'dev_fixture')
```

生成目录只含 `excitation.wav`、其 sidecar、canonical metadata 和其 sidecar；同一配置与 artifact ID 产生逐字节相同的内容。正式 `config/audio/default_1x1_ess.yaml` 的 duration、silence、fade 和 digital peak 仍为 null，因此会明确拒绝生成。这里不提供任何播放命令。

持久化发布与验证 API 只接受已加载的 audio config，并在内部派生 ESS spec；调用者不能另传 peak、duration 或其他 spec 覆盖配置。纯数学 `generate_ess(spec)` 仍接受 strict spec，但它不声明配置哈希。正式参数、硬件状态和 experiment-ready 状态均未改变。

## DEV-03.04 确定性虚拟采集

以下示例在系统临时目录中创建 development-only ESS、synthetic session 和 virtual capture run。两个采集命令都加载完整配置 bundle 与严格场景文件；命令行不能覆盖 ESS spec、block size、整数延迟或线性增益，也没有 real root、设备索引、Host API 或通道参数。

```powershell
$essRoot = Join-Path $env:TEMP 'acoustic-ladder-dev0304-ess'
$syntheticRoot = Join-Path $env:TEMP 'acoustic-ladder-dev0304-synthetic'
$bundle = @('--project-root', '.', '--audio', 'tests/fixtures/audio/ess_offline_development.yaml', '--protocol', 'config/protocols/stage4_four_node_states.yaml')
uv --cache-dir .uv-cache run acoustic-ladder ess-generate-offline --project-root . --audio-config tests/fixtures/audio/ess_offline_development.yaml --development-root $essRoot --artifact-id source_ess
uv --cache-dir .uv-cache run acoustic-ladder create-synthetic-session @bundle --synthetic-root $syntheticRoot --session-id virtual001 --reassembly-id assembly001
uv --cache-dir .uv-cache run acoustic-ladder simulate-duplex-capture @bundle --synthetic-root $syntheticRoot --session-id virtual001 --reassembly-id assembly001 --run-id capture001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
uv --cache-dir .uv-cache run acoustic-ladder validate-simulated-capture @bundle --synthetic-root $syntheticRoot --session-id virtual001 --run-id capture001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
```

正常夹具把 12960 个 ESS samples 加 64 个精确零 tail，以 256-frame blocks 真实推进 51 次，最后一块 224 frames；虚拟输入严格为 `y[k] = 0.5 * x[k-37]`，越界为零。成功 run 包含 output reference、simulated input、源 ESS metadata、strict capture receipt 及各自 sidecar。validator 不只核对哈希，还重新生成 ESS、重放所有 blocks、比较数组与 canonical WAV、重建 trace/receipt，并核对 session 中保存的完整配置来源。

CLI 成功输出 `SYNTHETIC_ONLY`、`NO_HARDWARE_AUDIO_IO_PERFORMED` 和 `NOT_AN_EXPERIMENTAL_RESULT`。这些 WAV 不是播放记录或麦克风录音；场景的 latency/gain 不是实测声学参数。详细边界见 `docs/architecture/virtual-capture.md`。

详细契约见 `docs/architecture/`；数据根目录政策见 `data/README.md`。

单元测试、真实包集成测试、完整测试与静态检查：

```powershell
uv --cache-dir .uv-cache run pytest tests/unit
uv --cache-dir .uv-cache run pytest tests/integration
uv --cache-dir .uv-cache run pytest tests/dev02
uv --cache-dir .uv-cache run pytest tests/dev03
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
```

manifest 是 UTF-8、稳定键排序、LF 换行的确定性 JSON，不包含本机绝对路径、随机时间或临时值。包审查 JSON 包含真实扫描时间，因此审查文件本身不承诺字节确定性。
