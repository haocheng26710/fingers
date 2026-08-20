# Acoustic Ladder

本仓库当前实现到 `DEV-05.03`：除模型包、配置、不可变存储、synthetic 接口数据和只读音频清单外，现提供严格的离线 ESS 开发夹具、确定性虚拟全双工采集、离线 ESS processing、provisional QC、repeatability、Stage 1 synthetic baseline difference、阶段 1–4 development-only 协议矩阵编译器、离线协议排练账本，以及由已验证计划驱动的可恢复 synthetic execution 账本。该执行器只生成 development synthetic session/run；不访问真实音频硬件，不执行正式 protocol，不应用阈值或输出实验判决。

当前状态固定为：

- `model_status = provisional`
- `physical_print_status = actual_printed`
- `calibration_status = applied`
- `release_role = calibrated_printed_candidate`

本项目不会导入或执行 ZIP 内 Python，也不会解压或重建 CAD。DEV-03.03 的 ESS、DEV-03.04 的虚拟采集和 DEV-04.01 的反卷积只生成离线软件测试产物，绝不播放、录音、打开音频流或枚举新设备；-20 dBFS 测试值不是听力安全级别。`virtual_duplex_scheduler_exercised=true` 只表示软件调度器被执行，不表示 `full_duplex_verified=true`。项目仍不包含真实音频采集、正式 ESS 参数、协议矩阵执行、分类器、界面或最终几何锁定。

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
uv --cache-dir .uv-cache run acoustic-ladder process-simulated-capture @bundle --synthetic-root $syntheticRoot --session-id virtual001 --source-run-id capture001 --processing-id processing001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
uv --cache-dir .uv-cache run acoustic-ladder validate-simulated-processing @bundle --synthetic-root $syntheticRoot --session-id virtual001 --source-run-id capture001 --processing-id processing001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
uv --cache-dir .uv-cache run acoustic-ladder qc-compute @bundle --synthetic-root $syntheticRoot --session-id virtual001 --source-run-id capture001 --processing-id processing001 --qc-id qc001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
uv --cache-dir .uv-cache run acoustic-ladder qc-validate @bundle --synthetic-root $syntheticRoot --session-id virtual001 --source-run-id capture001 --processing-id processing001 --qc-id qc001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
```

正常夹具把 12960 个 ESS samples 加 64 个精确零 tail，以 256-frame blocks 真实推进 51 次，最后一块 224 frames；虚拟输入严格为 `y[k] = 0.5 * x[k-37]`，越界为零。成功 run 包含 output reference、simulated input、源 ESS metadata、strict capture receipt 及各自 sidecar；receipt 明确记录与 run 一致的非负 `measurement_order`。publisher 和 validator 都会重新读取同一 project-relative 场景来源，并逐项核对当前原始字节、解析模型与规范化结果，因此加载后被修改、删除、移动或伪造的场景会被拒绝。validator 还重新生成 ESS、重放所有 blocks、比较数组与 canonical WAV、重建 trace/receipt，精确核对 synthetic metadata、完整 run envelope，以及 session 中保存的 manifest sidecar 和配置来源。

CLI 成功输出 `SYNTHETIC_ONLY`、`NO_HARDWARE_AUDIO_IO_PERFORMED` 和 `NOT_AN_EXPERIMENTAL_RESULT`。这些 WAV 不是播放记录或麦克风录音；场景的 latency/gain 不是实测声学参数。详细边界见 `docs/architecture/virtual-capture.md`。

## DEV-04.01 synthetic 离线 ESS 处理

`process-simulated-capture` 首先调用 capture 语义重放验证，再从已验证的 output-reference/input WAV、ESS metadata 和当前 AnalysisConfig 派生全部输入。调用者不能传 waveform、预期 latency/gain、预计算 IR/hash/receipt、real root 或设备参数。处理使用 float64、指数补偿逆滤波、完整线性 FFT 卷积、全 sweep 归一化相关延迟、零填充非循环对齐，以及 captured/reference 频谱比得到的 raw/aligned `rfft` 复传递函数；AnalysisConfig 的 500–8000 Hz 只形成 mask，不执行 smoothing。

不可变结果位于 `processed/run_<source_run_id>/processing_<processing_id>/`，包含确定性 NPZ、strict receipt、固定 synthetic metadata、outer processing record、SHA256 sidecar 和 `PROCESSING_COMPLETE`。成功发布后还会追加 `processing_created` session event，绑定 record/receipt hashes 和时间；验证器以 `(source_run_id, processing_id)` 复合身份要求恰好一条匹配，因此不同 source run 可合法重用 processing ID，同一复合身份的重复事件仍被拒绝。Processing receipt 的 schema 和 algorithm 版本均为 `1.1.0`，并用严格字面量记录 raw/aligned 复谱比、分母阈值公式及低阈值置零策略。事件失败会报告 `published=true`，不会删除已发布目录。`validate-simulated-processing` 只读地重新验证 source capture、重做全部数学并逐字节比较产物。该事件只提供项目内部完整性与审计关联，不是数字签名或可信时间戳。名义夹具得到的 37 samples 和约 0.5 是从波形恢复的 development fixture oracle，不是处理 API 输入，也不是声学实测值。详细契约见 `docs/architecture/ess-processing.md`。

## DEV-04.02 provisional 离线 QC

`qc-compute` 首先完整调用 `validate_ess_processing`，再从已验证的 capture WAV、processing NPZ/receipt 和 AnalysisConfig 计算 float64 指标。公开 publisher 只接受 bundle、scenario、ESS 根和四个身份，不接受任意 WAV/NPZ 路径、waveform/array、预计算 metrics、scenario truth、阈值、判决、real root 或设备参数。AnalysisConfig 的 `qc_threshold` 必须为 null。

不可变结果位于 `qc/run_<source_run_id>/processing_<processing_id>/qc_<qc_id>/`，严格包含 metrics/receipt 及各自 SHA256 sidecar、固定 metadata、outer record 和 `QC_COMPLETE` 七个文件。`qc_created` event 绑定 `(source_run_id, processing_id, qc_id)`、record/metrics/receipt hashes 与创建时间；同一 QC ID 可在不同 processing 复合身份下重用，完全重复的复合身份被拒绝。`qc-validate` 只读地重验 processing、重算所有指标并逐字节核对 envelope 与 event。

指标包括 waveform peak/RMS/clip、pre-silence SNR proxy、processing latency/correlation、IR 主次峰比、reference deconvolution off-peak residual 和 analysis-band 谱除法覆盖。固定状态为 `provisional_metrics_only` / `not_evaluated` / `THRESHOLDS_NOT_APPLIED`；零 pre-silence RMS 产生带原因的 null，而不是 Infinity。这些值不是 SPL、安全阈值、正式声学 SNR、硬件质量判决或实验结果。详细契约见 `docs/architecture/provisional-qc.md`。

## DEV-04.03 provisional repeatability

`repeatability-compute` 与 `repeatability-validate` 只接受 synthetic session、repeat-set ID 和可重复的 `--member SOURCE_RUN:PROCESSING:QC`。它们逐成员重放 capture、processing 和 QC，从 capture receipt 派生 reassembly/measurement order，再从已验证 WAV/NPZ 计算全部唯一 pair。调用者不能提供 measurement order、reassembly、waveform/array、任意 WAV/NPZ、预计算 metrics、condition/BLK/baseline、truth、threshold/decision、real root 或硬件/校准参数。

例如，在同一 session 已依次建立 `capture001` 和 `capture002`（measurement order 0、1）及各自的 `processing001` / `qc001` 后：

```powershell
uv --cache-dir .uv-cache run acoustic-ladder repeatability-compute @bundle --synthetic-root $syntheticRoot --session-id virtual001 --repeat-set-id repeatset001 --member capture002:processing001:qc001 --member capture001:processing001:qc001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
uv --cache-dir .uv-cache run acoustic-ladder repeatability-validate @bundle --synthetic-root $syntheticRoot --session-id virtual001 --repeat-set-id repeatset001 --member capture001:processing001:qc001 --member capture002:processing001:qc001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
```

结果严格位于 `qc/repeat_sets/reassembly_<reassembly_id>/repeat_set_<repeat_set_id>/` 的七文件 create-only envelope。DEV-04.03R receipt、algorithm 与 record 为 `1.1.0`，并把 not-evaluated、baseline not assigned/deferred、drift not evaluated 和 threshold false/null 状态写入 receipt、record 与 metadata。CLI 的结构化状态从已发布或已验证 receipt 读取；成功输出的 `PASS` 仅表示软件命令和完整性验证通过。活动 AnalysisConfig 的 baseline selection rule 或任一 decision threshold 非 null 时，publisher 和 validator 都会在创建 repeatability parent/staging/lock 前拒绝；旧 `1.0.0` repeatability artifact 必须重新生成。该 legacy 路径自身仍没有 protocol condition binding、baseline difference、漂移判决、硬件/校准/SPL 或实验结论；DEV-04.04 通过独立版本化 receipt 和新 comparison 层扩展它。事件只提供内部完整性与审计绑定，不是数字签名、外部 witness 或可信时间戳。详细契约见 `docs/architecture/repeatability.md`。

## DEV-04.04 protocol-condition binding 与 BLK baseline difference

`tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml` 是严格的 development-only condition plan：唯一 baseline 为全 BLK，candidate 为一个 manifest node 上的一个 Stage 1 bridge state。`simulate-conditioned-capture` 将该绑定解析为完整 `NodeState` map，并通过纯 synthetic、块调度的虚拟双工后端发布 capture；`--condition-id` 只存在于这一 capture publisher，后续 processing、QC、repeatability 和 comparison 均从已验证 receipt 派生 condition 身份。

```powershell
acoustic-ladder simulate-conditioned-capture @bundle --synthetic-root $syntheticRoot --session-id condition001 --reassembly-id blk-a --run-id blk001 --measurement-order 0 --scenario tests/fixtures/audio/conditioned_virtual_duplex_development.yaml --condition-plan tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml --condition-id all_blk --ess-artifact-root $essRoot
```

每个 condition 的成员完成 processing、QC 和 `repeatability-compute --condition-plan ...` 后，可用两个 repeat-set identity 生成 comparison。参数名便于 CLI 阅读，但 baseline/candidate 角色会从两个 condition-aware repeatability receipt 重新验证并自动归一，不能由调用者伪造。

```powershell
acoustic-ladder baseline-difference-compute @bundle --synthetic-root $syntheticRoot --session-id condition001 --comparison-id blk-vs-n1-b40 --scenario tests/fixtures/audio/conditioned_virtual_duplex_development.yaml --condition-plan tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml --ess-artifact-root $essRoot --baseline-repeat-set-id blk-set --baseline-member blk001:p001:q001 --baseline-member blk002:p002:q002 --candidate-repeat-set-id n1-b40-set --candidate-member b40001:p101:q101 --candidate-member b40002:p102:q102
acoustic-ladder baseline-difference-validate @bundle --synthetic-root $syntheticRoot --session-id condition001 --comparison-id blk-vs-n1-b40 --scenario tests/fixtures/audio/conditioned_virtual_duplex_development.yaml --condition-plan tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml --ess-artifact-root $essRoot --baseline-repeat-set-id blk-set --baseline-member blk001:p001:q001 --baseline-member blk002:p002:q002 --candidate-repeat-set-id n1-b40-set --candidate-member b40001:p101:q101 --candidate-member b40002:p102:q102
```

comparison 位于 `processed/baseline_differences/comparison_<comparison_id>/` 的 exact 11-file create-only envelope。保存 raw/aligned 复传递函数均值、加性差、稳定除法 ratio、分段 phase unwrap、raw/aligned IR 差分与连续指标；invalid bin 为零并另存 mask。这里的 synthetic 非零差分不是实验效应、装置可检测性或统计显著性结论。CLI 的 `PASS` 只表示 compute/validate 软件操作及完整性重放成功。

## DEV-05.01 development 协议计划

四个 `tests/fixtures/protocol/stage*_protocol_plan.development.yaml` 只为软件测试补充 `2 sessions × 2 reassemblies × 2 continuous repeats` 和 seed `dev0501-test-seed-v1`。这些数值不是正式实验建议，正式协议中的 repeats/reassemblies/sessions/seed 仍未确认，`execution_ready=false`。

```powershell
$planRoot = Join-Path $env:TEMP 'acoustic-ladder-dev0501-plans'
acoustic-ladder protocol-plan-compile --project-root . --protocol config/protocols/stage1_single_bridge.yaml --audio tests/fixtures/audio/ess_offline_development.yaml --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example
acoustic-ladder protocol-plan-validate --project-root . --protocol config/protocols/stage1_single_bridge.yaml --audio tests/fixtures/audio/ess_offline_development.yaml --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example
```

当前 fixture 的 condition counts 为 19/4/4/16，planned measurements 为 152/32/32/128。随机化只排列 condition blocks，continuous repeats 始终相邻；算法为 `sha256_ranked_condition_blocks` `1.0.0`。Stage 2 固定孔径只是 proxy，Stage 3 不计算 interaction residual，Stage 4 不执行 classification。operator confirmation 仍为 pending，计划产物不是实验结果。详见 `docs/architecture/protocol-planning.md`。

## DEV-05.02 离线协议排练账本

排练根与 plan、real、synthetic session 根相互独立。`protocol-rehearsal-init` 从已验证 compiled plan 的 `session_slots` 派生全部工作单；`status`/`validate` 只读重放 create-only 事件哈希链；`step` 只接受 action、actor 和上一状态返回的 sequence/head/work-order 并发 token，不能注入 ordinal、condition、NodeState、设备或输出路径。

```powershell
$rehearsalRoot = Join-Path $env:TEMP 'acoustic-ladder-dev0502-rehearsals'
acoustic-ladder protocol-rehearsal-init @bundle --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example --development-rehearsal-root $rehearsalRoot --rehearsal-id stage1-dry-run
acoustic-ladder protocol-rehearsal-status @bundle --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example --development-rehearsal-root $rehearsalRoot --rehearsal-id stage1-dry-run
acoustic-ladder protocol-rehearsal-step @bundle --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example --development-rehearsal-root $rehearsalRoot --rehearsal-id stage1-dry-run --action present-requirements --actor-id offline-runner --expected-event-sequence 0 --expected-head-sha256 <status-head> --expected-work-order-sha256 <status-work-order>
acoustic-ladder protocol-rehearsal-validate @bundle --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example --development-rehearsal-root $rehearsalRoot --rehearsal-id stage1-dry-run
```

正常工作单路径为 `present-requirements → claim → mark-rehearsed`；也支持 pause/resume、mark-failed/retry 和 abort。所有持久化安全状态继续声明未执行协议、未测量、未访问硬件、operator confirmation pending，CLI 的 `PASS` 仅表示软件排练或完整性重放成功。哈希链不是签名、外部 witness 或可信时间戳；活动账本尚未被后续记录引用的最后尾部删除没有外部可证明性。详见 `docs/architecture/protocol-rehearsal.md`。

## DEV-05.03 阶段 1–4 synthetic execution

execution root、plan root 与 synthetic session root 必须相互独立。初始化只派生工作项并发布 immutable base envelope，不创建 session；`execute-next` 每次最多执行当前一项，从 replay-validated compiled plan 派生完整 NodeState、condition、session/reassembly/run/capture ID，使用离线 ESS、manifest/config-derived synthetic IR 和虚拟双工调度发布一个 create-only run。调用者不能提供 condition、ordinal、NodeState、run identity、waveform、IR、real root 或设备参数。

```powershell
$executionRoot = Join-Path $env:TEMP 'acoustic-ladder-dev0503-executions'
$syntheticRoot = Join-Path $env:TEMP 'acoustic-ladder-dev0503-synthetic'
acoustic-ladder synthetic-protocol-execution-init @bundle --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example --development-execution-root $executionRoot --synthetic-root $syntheticRoot --execution-id stage1-synthetic --scenario tests/fixtures/audio/conditioned_virtual_duplex_development.yaml --ess-artifact-root $essRoot
acoustic-ladder synthetic-protocol-execution-status @bundle --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example --development-execution-root $executionRoot --synthetic-root $syntheticRoot --execution-id stage1-synthetic --scenario tests/fixtures/audio/conditioned_virtual_duplex_development.yaml --ess-artifact-root $essRoot
# execute-next/pause/resume/retry/recover-current/abort also require the complete token printed by status.
acoustic-ladder synthetic-protocol-execution-validate @bundle --plan-spec tests/fixtures/protocol/stage1_protocol_plan.development.yaml --development-plan-root $planRoot --plan-id stage1-example --development-execution-root $executionRoot --synthetic-root $syntheticRoot --execution-id stage1-synthetic --scenario tests/fixtures/audio/conditioned_virtual_duplex_development.yaml --ess-artifact-root $essRoot
```

如果 capture 已完整发布而 success event 尚未发布，或最后 success event 已发布而 completion 尚未发布，status 返回 `recovery_required`，只有显式 `recover-current` 才会在完整重验后采用已有产物。mutation 错误中的 capture/event/completion publication 字段由异常返回时的只读持久化重放决定：publisher 完整发布后再抛错会报告 true，部分、语义验证失败或无法探测的发布保守报告 false，旧内存布尔值不能覆盖该结果。lock close/unlink 失败也返回同一领域错误契约并重新探测持久化事实；unlink 失败会保留 stale lock，status/validator 不自动清理，后续 mutation 被拒绝。探测不会修复或删除字节。CLI `PASS` 只表示 development synthetic 操作/完整性验证通过；所有 hardware、playback、recording、formal execution、measurement 与 experimental-result 状态保持 false。Stage 2 条件仍只是 proxy states，Stage 3 不计算 interaction residual，Stage 4 不执行分类。详见 `docs/architecture/protocol-synthetic-execution.md`。

## DEV-06.01 离线 measurement matrix

`analysis-matrix-compute` 消费四个已完成、完整重放验证的 Stage 1–4 synthetic execution；它不执行 protocol，也不接受 row、label、baseline、feature、fold、waveform 或任意输出路径。完整 development fixture 恰好产生 344 行（152/32/32/128），一行对应一个 synthetic run。每行只使用同 stage/session/reassembly 的全 BLK repeats；全 BLK 行自身使用 leave-one-repeat-out。固定 16 列来自 versioned feature schema，split 逐 stage 生成 leave-one-session-out 与 leave-one-reassembly-out。

结果位于 analysis synthetic root 的 `analyses/analysis_<id>/` exact 15-file create-only envelope；`analysis-matrix-validate` 重验四个 execution、重做 processing/QC、基线、feature、split 和 deterministic NPZ，并逐字节比较且不写回。CLI 的四组 `--protocol`、`--plan-spec`、plan/execution/synthetic/ESS roots、execution/plan IDs 必须按 stage 各提供四次；`--analysis-root` 是专用 synthetic analysis storage root，其下自动派生 `analyses/`。

DEV-06.01R 将 `analysis_evidence_time` 固定为四个 verified execution completion 中最新的 UTC instant，basis 为 `latest_verified_execution_completion_utc`。它是可重放的来源证据时间，不是 wall-clock publication timestamp、可信时间戳或外部 witness；compute 接口不接受 `now`。1.1 receipt 单向绑定 metadata 和 record 的 SHA256，二者不再反向保存 receipt SHA。validator 只从 verified sources、analysis spec 和 analysis ID 重建 expected bytes，不信任已发布 metadata/record/receipt 提供 expected 时间、路径或状态。旧 1.0 envelope 必须重新生成，不能原地迁移；SHA256 仍不是数字签名。

这里的 feature extraction 仅是 development fixture 的确定性软件产物：没有模型拟合、预测、分类、interaction analysis、normalization fitting、阈值或真实 QC PASS/FAIL，也没有硬件枚举/I/O、播放、录音、校准或实验结论。详见 `docs/architecture/synthetic-measurement-matrix.md`。

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
