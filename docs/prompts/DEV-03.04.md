# DEV-03.04 项目实施提示词——采集执行内核、虚拟全双工后端与原始采集契约

你现在位于 Acoustic Ladder 的实际代码仓库中。

本步骤序列号：

`DEV-03.04`

本步骤名称：

`采集执行内核、虚拟全双工后端与原始采集契约`

只执行本步骤。完成后停止，不得自行进入真实硬件接入、反卷积、声学分析、DEV-03.05、DEV-04 或正式实验。

---

# 1. 本步目标

在完全不连接、不枚举、不调用真实音频硬件的条件下，建立未来真实采集所需的软件执行内核。

必须完成：

1. 严格的采集状态机；
2. 硬件无关的采集后端接口；
3. 唯一可执行的确定性虚拟全双工后端；
4. 分块输出/输入和样本计数契约；
5. 确定性整数样本延迟和固定增益仿真；
6. short-read、dropout、clipping、backend error、abort 等故障路径；
7. synthetic-only、create-only 的原始采集 bundle；
8. 配置、manifest、protocol、ESS 和场景来源的完整哈希链；
9. 虚拟采集执行与验证 CLI；
10. 完整的状态、数值、存储、篡改、CLI 和失败清理测试；
11. README、架构文档、完成报告和实施日志；
12. 只有全部验收通过后才提交并推送 GitHub。

本步骤的产物只能证明：

- 虚拟采集执行流程可以运行；
- 软件状态机和分块契约可用；
- synthetic 原始数据可以确定性生成、保存和验证；
- 失败路径能被识别和审计。

本步骤不能证明：

- 真实全双工可用；
- 真实设备共享时钟；
- 真实输入/输出通道正确；
- 真实设备延迟；
- 实际声压安全；
- 麦克风校准有效；
- 实际装置声学性能；
- 实验已经准备完成。

---

# 2. 不可突破的硬件边界

当前实际情况：

- MOONDROP CHU II / 水月雨竹 2 未连接；
- Dayton Audio iMM-6C 未连接；
- Acoustic Ladder 实验装置未连接；
- 操作者暂不希望接入实际设备；
- 当前 DEV-03.01 inventory 只是未连接实验硬件时的开发主机基线；
- inventory 内所有现有设备索引都不是实验设备绑定依据；
- 用户报告未来输入和输出属于同一个音频接口，但尚未通过实际连接验证；
- iMM-6C 麦克风校准文件存在，但尚未提供和验证；
- 没有 94 dB/1 kHz 声学校准器；
- 不能进行输出到输入的电气回环；
- 不使用功率放大器。

必须继续保持：

```text
hardware_ready = false
full_duplex_verified = false
shared_clock_verified = false
channel_mapping_verified = false
calibration_file_verified = false
calibration_applied = false
absolute_spl_calibrated = false
electrical_loopback_available = false
device_binding = deferred_until_hardware_connection
```

其中 `calibration_applied=false` 指音频/麦克风声学校准状态，不得与 V1.3 打印配合校准的 `calibration_status=applied` 混淆。

本步骤严禁：

- 运行生产 `audio-list`；
- 运行生产 `audio-inventory`；
- 查询、枚举或绑定新的真实设备；
- 调用 `sounddevice.query_devices()`；
- 调用 `sounddevice.query_hostapis()`；
- 调用输入/输出格式检查；
- 创建 `InputStream`、`OutputStream` 或 `Stream`；
- 使用 `play()`、`rec()`、`playrec()`；
- 播放任何 ESS；
- 录制任何声音；
- 打开任何 OS 音频资源；
- 读取或应用 iMM-6C 校准文件；
- 做 SPL、回环、真实延迟或时钟测量。

新代码不得直接导入 `sounddevice`。

现有只读 inventory 模块中的延迟导入不需要删除，但 DEV-03.04 的任何运行路径都不得触发它。

---

# 3. 冻结的研究和模型状态

项目：

`Acoustic Ladder V1.3 校准后圆形主管版本`

保持：

```text
physical_print_status = actual_printed
calibration_status = applied
release_role = calibrated_printed_candidate
model_status = provisional
```

不得设置：

```text
geometry_locked
experiment_ready
formal_ready
release
```

正式实验拓扑仍为：

```text
1 个扬声器输出 + 1 个麦克风输入
```

内存数组继续使用 channel-first：

```text
outputs[n_output_channels, n_samples]
inputs[n_input_channels, n_samples]
```

本阶段具体固定为：

```text
outputs.shape = [1, n_samples]
inputs.shape = [1, n_samples]
dtype = float32
```

正式 AudioConfig 中以下未知值必须继续保持 `null`：

- 正式 ESS duration；
- 正式 pre-silence；
- 正式 post-silence；
- 正式 fade-in；
- 正式 fade-out；
- 正式 digital peak；
- output gain；
- input gain；
- 设备索引；
- Host API；
- 通道映射。

不得把 development fixture 参数复制到正式配置。

---

# 4. Git 开始门禁

首先只读检查仓库，不要立即修改文件。

必须确认：

- 仓库根目录正确；
- 当前分支为 `main`；
- 工作区干净；
- 没有未跟踪的用户文件；
- remote 名称为 `origin`；
- remote URL 为：

`https://github.com/haocheng26710/fingers.git`

本地 HEAD、`origin/main` 和 GitHub `main` 必须全部为：

`fcaf4f7bbac2778c21888d8e8bc4676b2350e926`

至少执行并记录真实结果：

```text
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git remote -v
git ls-remote origin refs/heads/main
git log -1 --format=fuller
```

扫描项目级：

- `AGENTS.md`
- `CLAUDE.md`
- `CONTEXT.md`
- `docs/adr/`
- 其他实际存在的项目指令

如果出现以下任一情况，立即停止：

- HEAD 不匹配；
- 本地与远端不一致；
- GitHub `main` 已前进；
- 工作区不干净；
- 存在无法安全保留的用户修改；
- remote URL 不一致；
- 新项目指令与本提示词冲突。

停止时：

- 不得 reset；
- 不得 clean；
- 不得覆盖用户文件；
- 不得提交；
- 不得推送；
- 报告真实阻塞原因。

始终禁止：

```text
git reset --hard
git clean
force push
rebase 已发布 main
修改历史提交
amend DEV-03.03R
```

---

# 5. 提示词归档与实施日志

## 5.1 保存本提示词

开始实现时，先将实际收到的本提示词完整保存为：

`docs/prompts/DEV-03.04.md`

要求：

- 不得总结；
- 不得删节；
- 不得改写；
- 不得加入代码块之外不存在的聊天内容；
- 如果运行环境提供原始提示词附件，优先直接复制原始附件；
- 复制后计算源文件和归档文件 SHA256；
- 如果没有原始附件，如实记录采用的保存方式；
- 保持真实换行和编码，不得伪造“逐字节复制”。

如果原始提示词包含 CRLF 且需要保留审计字节，可在 `.gitattributes` 中将：

`docs/prompts/DEV-03.04.md`

标为 binary；必须记录原因。

## 5.2 实施日志

读取：

`docs/IMPLEMENTATION_LOG.md`

必须保证原文件的全部既有字节仍是新文件的完整前缀。

只允许在末尾新增：

`## DEV-03.04`

开始时先写入：

- 序列号；
- 名称；
- 状态 `IN_PROGRESS`；
- 开始时间和时区；
- 基线提交；
- 远端基线；
- 本步骤目标；
- 当前硬件未连接事实；
- 禁止范围；
- 预期文件和测试范围。

执行过程中持续更新本步骤条目。

结束时状态必须是实际状态之一：

```text
PASSED
FAILED
BLOCKED
INTERRUPTED
```

日志必须如实记录：

- 实际读取的输入；
- 实际创建和修改的文件；
- 每条重要命令；
- TDD 首次失败；
- 错误信息；
- 根因；
- 实际修正；
- 模型和 API 决定；
- 场景参数；
- 样本数和 block 数；
- 实际生成的 SHA256；
- 每组测试的收集数量和结果；
- 静态检查结果；
- Schema 数量；
- 临时目录创建和清理；
- 未执行项目及原因；
- 已知限制；
- Git 提交与推送门禁状态。

不得预先填写：

- 测试通过；
- 哈希值；
- commit SHA；
- 推送成功；
- 不存在的失败；
- 未实际运行的命令。

日志详细程度必须让另一名操作者借助其他 AI，尽可能复刻相同实现、测试和验收结果。

---

# 6. 受保护输入

必须重新计算，不得照抄以下 SHA256。

## 6.1 V1.3 模型包

文件：

`reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip`

预期：

`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`

## 6.2 provisional manifest

文件：

`config/devices/device_manifest.provisional.json`

预期：

`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

## 6.3 DEV-03.01 inventory

文件：

`reference/audio/inventory/DEV-03.01_audio_inventory.json`

预期：

`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

## 6.4 DEV-03.02 capture context

文件：

`reference/audio/inventory/DEV-03.02_inventory_capture_context.json`

预期：

`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`

## 6.5 DEV-03.02 summary

文件：

`reference/audio/inventory/DEV-03.02_audio_inventory_summary.md`

预期：

`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`

## 6.6 DEV-03.02 contextual preflight

文件：

`reference/audio/inventory/DEV-03.02_contextual_preflight_report.json`

预期：

`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`

## 6.7 provisional hardware setup

文件：

`reference/audio/hardware_setup.provisional.json`

预期：

`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

如果任一哈希不匹配，停止，不得实现、提交或推送。

本步骤不得修改：

- 上述七个保护文件及其 sidecar；
- V1.3 校准记录；
- 正式 device manifest；
- DEV-03.01/03.02 既有文件；
- 正式 `config/audio/default_1x1_ess.yaml` 的未知字段；
- DEV-03.03 和 DEV-03.03R 的 prompt、report；
- 既有实施日志内容；
- 既有 ESS development fixture 参数；
- 既有 ESS golden 结果。

必须保护 DEV-03.03 的三个 golden SHA256：

```text
WAV:
608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0

Metadata:
e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a

Raw float32:
eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca
```

现有完整测试基线为：

`277 passed`

现有生成 Schema 数量为：

`15`

---

# 7. 实现前必须阅读

至少阅读：

- `pyproject.toml`
- `uv.lock`
- `.gitignore`
- `.gitattributes`
- `README.md`
- `data/README.md`
- `config/audio/default_1x1_ess.yaml`
- `tests/fixtures/audio/ess_offline_development.yaml`
- `config/protocols/stage4_four_node_states.yaml`
- `config/analysis/default.yaml`
- `config/synthetic/default.yaml`
- `src/acoustic_ladder/config/bundle.py`
- `src/acoustic_ladder/config/models.py`
- `src/acoustic_ladder/domain/models.py`
- `src/acoustic_ladder/domain/paths.py`
- `src/acoustic_ladder/storage/io.py`
- `src/acoustic_ladder/storage/store.py`
- `src/acoustic_ladder/audio/ess.py`
- `src/acoustic_ladder/audio/excitation_models.py`
- `src/acoustic_ladder/audio/excitation_persistence.py`
- `src/acoustic_ladder/audio/backend.py`
- `src/acoustic_ladder/cli.py`
- `tests/dev02/`
- `tests/dev03/`
- `docs/architecture/ess-excitation.md`
- `docs/architecture/audio-inventory.md`
- `docs/reports/DEV-03.03.md`
- `docs/reports/DEV-03.03R.md`
- `docs/IMPLEMENTATION_LOG.md`

必须复用：

- strict Pydantic；
- canonical JSON；
- safe relative path；
- `LoadedBundle`；
- `ConfigSnapshot`；
- `DataOrigin`；
- `ImmutableSessionStore`；
- synthetic/real 根隔离；
- `ArtifactRef`；
- create-only staging；
- SHA256 sidecar；
- 现有 IEEE float32 WAV 编码/解码；
- ESS 的单一配置事实源；
- Schema 导出/检查；
- 现有 CLI 风格。

不得另建互相冲突的数据根、配置加载器或 WAV 格式。

如需把 WAV 读写函数移动到更通用模块，可以重构，但必须证明：

- 既有 ESS WAV 字节完全不变；
- 三个 ESS golden hash 不变；
- 全部旧测试继续通过；
- 没有引入播放或录音能力。

不得增加新的第三方依赖，除非标准库、NumPy 和现有依赖确实无法完成；如确需新增，必须先说明必要性并完整更新锁文件。

---

# 8. 核心权威边界

持久化虚拟采集不得接受调用者分别提供的：

- 任意 ESS spec；
- 任意 audio config hash；
- 任意 manifest hash；
- 任意 protocol hash；
- 任意预计算 waveform；
- 任意预计算 receipt 字段；
- 任意声称已完成的状态轨迹。

公共持久化入口必须从以下受验证对象派生事实：

1. `LoadedBundle`
2. 由其中 audio config 验证的离线 ESS artifact
3. 经过严格加载的虚拟采集场景
4. 已验证的 synthetic session/reassembly
5. 执行内核真实产生的结果

建议设计：

```text
LoadedVirtualCaptureScenario
VirtualCaptureScenario
VirtualCaptureEngine
VirtualDuplexBackend
CaptureStateMachine
VirtualCaptureResult
VirtualCaptureReceipt
VirtualCaptureError
```

公共 publish/validate API 可以根据实际架构命名，但必须满足：

- publish 接受 `LoadedBundle`，而不是独立哈希；
- 内部从 `LoadedBundle.configs["audio"]` 获取唯一 audio config；
- 内部调用现有离线 ESS validator；
- 场景从单一严格场景文件加载；
- receipt 字段由实际执行结果派生；
- validate 必须重新计算语义结果，不能只验证 sidecar。

纯数学或纯内存 engine 可以接受严格模型和数组，以便测试；但只要 metadata 声称来源于配置、ESS 或 bundle，持久化边界就必须从受验证对象派生。

---

# 9. 虚拟采集场景

新增 development-only 场景文件，建议：

`tests/fixtures/audio/virtual_duplex_development.yaml`

建议正常场景参数：

```yaml
schema_version: "1.0.0"
scenario_id: "virtual_duplex_nominal_v1"
usage_scope: "development_fixture"
backend_id: "deterministic_virtual_duplex"
backend_version: "1.0.0"
block_size_frames: 256
integer_latency_samples: 37
capture_tail_samples: 64
linear_gain: 0.5
fault_mode: "none"
fault_block_index: null
hardware_io_authorized: false
formal_eligible: false
experimental_result: false
```

这些值只是软件测试夹具，不是：

- 真实装置延迟；
- 真实声学增益；
- 正式实验参数；
- 设备安全参数；
- 未来硬件推荐值。

严格约束至少包括：

- `block_size_frames > 0`
- `integer_latency_samples >= 0`
- `capture_tail_samples >= integer_latency_samples`
- `linear_gain` finite 且大于 0
- 禁止 NaN/Infinity
- 禁止未知字段
- 禁止字符串到数值的隐式转换
- `hardware_io_authorized=false`
- `formal_eligible=false`
- `experimental_result=false`
- `usage_scope=development_fixture`
- `backend_id=deterministic_virtual_duplex`

`sample_rate`、ESS 长度和数字峰值不得在场景文件中再次定义，必须来自经过验证的 ESS/audio config。

场景加载必须记录：

- 仓库相对路径；
- 原文件 SHA256；
- canonical normalized SHA256。

建议新增相应生成 Schema。

---

# 10. 采集状态机

必须实现显式状态机，不能只用若干布尔值模拟。

正常路径固定为：

```text
created
  -> prepared
  -> armed
  -> running
  -> completed
```

终止状态：

```text
failed
aborted
completed
```

建议允许：

```text
prepared -> failed
prepared -> aborted
armed -> failed
armed -> aborted
running -> failed
running -> aborted
```

要求：

- 非法跳转必须抛出专用异常；
- 不能跳过 `prepared` 或 `armed`；
- 不能从终止状态继续执行；
- 不能重复 complete；
- 不能在样本不足时 complete；
- 不能在存在未处理状态 flag 时 complete；
- 每次转换必须产生真实的 transition record；
- transition sequence 从 1 开始连续递增；
- transition 记录使用虚拟 sample cursor 或派生秒数；
- 不得使用随机 UUID；
- 不得把墙钟时间伪装为音频时钟；
- receipt 中不得记录非确定性当前时间。

状态轨迹至少记录：

- sequence；
- from state；
- to state；
- reason；
- sample cursor；
- completed block count。

正常 completed receipt 的状态顺序必须完全等于：

```text
created
prepared
armed
running
completed
```

失败和中止必须保留实际到达的状态轨迹，但不得伪造 completed。

---

# 11. 硬件无关后端与虚拟后端

定义窄接口，例如：

```text
prepare(...)
arm(...)
exchange_block(output_block, frame_count)
close(...)
abort(...)
```

具体签名由实际架构决定，但必须：

- 使用 channel-first float32；
- 明确 frame count；
- 返回 input block 和状态信息；
- 能注入测试后端；
- 不含设备索引；
- 不含 Host API；
- 不含 `sounddevice` 类型；
- 不打开真实流。

唯一生产可执行实现：

`VirtualDuplexBackend`

不得在本步骤实现真实 PortAudio/sounddevice backend。

## 11.1 正常确定性关系

令输出参考为 `x`，虚拟输入为 `y`：

```text
y[k] = linear_gain * x[k - integer_latency_samples]
```

当索引越界时：

```text
y[k] = 0
```

总采集样本数：

```text
capture_sample_count =
    ess_total_sample_count + capture_tail_samples
```

输出流：

```text
ESS 样本 + capture_tail_samples 个精确零
```

要求：

- tail 足以完整保留延迟后的 ESS；
- 输出和输入都为 `[1, capture_sample_count] float32`；
- C-contiguous；
- 所有值 finite；
- 输出 tail 精确为零；
- 输入延迟区精确为零；
- 正常场景不得产生隐式噪声；
- 不得自动 DC removal；
- 不得自动归一化；
- 不得使用 FFT 或反卷积；
- 不得将 gain 描述为真实声学传递函数。

相同 ESS、相同场景和相同标识必须产生逐样本和逐字节相同的 capture artifact。

## 11.2 分块执行

执行内核必须按 block 推进，不得仅生成整段数组后伪造 block trace。

要求：

- 每个 block 记录 sequence、start frame、requested frame count；
- 最后一个 block 允许短于标准 block size；
- block 区间必须连续、无重叠、无间隙；
- 输出和输入实际 frame count 必须记录；
- planned block count 使用明确的 ceiling division；
- actual block count 必须与真实执行一致；
- sample cursor 必须单调；
- completed 时 cursor 必须等于 capture sample count。

正常建议场景下应得到：

```text
ESS total samples = 12960
capture tail = 64
capture samples = 13024
block size = 256
planned blocks = 51
last block frames = 224
```

必须由程序重新计算并验证，不得只照抄。

不得使用真实 `sleep()` 模拟时间。

使用确定性虚拟时钟或 sample cursor。

---

# 12. 故障路径

至少支持以下测试故障：

```text
none
short_input_block
dropout
clipping
backend_error
abort_requested
```

需要 `fault_block_index` 的模式必须验证该索引处于真实 block 范围内。

建议结果：

- `none`：完成；
- `short_input_block`：failed；
- `dropout`：failed；
- `clipping`：failed；
- `backend_error`：failed；
- `abort_requested`：aborted。

要求：

- short-read 不得用零填充后假装成功；
- dropout/status flag 不得静默忽略；
- non-finite 数据必须失败；
- clipping 必须产生明确完整性错误；
- backend exception 必须转换为项目专用异常并保留原因；
- abort 不得标成 failed 或 completed；
- 失败和中止不得发布 `RUN_COMPLETE`；
- 失败和中止不得留下完成的 capture run；
- 自己创建的 staging 必须清理；
- 不得删除或覆盖既有 session/run；
- 不得清理任何不属于本调用的目录。

执行失败诊断可以在内存或 CLI 输出中包含：

- final state；
- fault block；
- completed blocks；
- sample cursor；
- error code；
- error message。

不得为了保存失败诊断而创建一个看似成功的实验结果。

如果发现现有存储在“目录已发布、随后事件追加失败”时存在语义歧义，必须：

- 不删除已经发布的 immutable 目录；
- 明确区分 `published=true` 和 `published=false`；
- 不得把已经成功发布的目录谎报为“完全没有输出”；
- 在报告中说明跨目录事件与 run 发布的实际原子性边界。

不得声称对所有非协作 filesystem actor 具有绝对多文件原子性。

---

# 13. 成功采集 bundle

成功的 synthetic capture run 应复用现有：

- `ImmutableSessionStore`
- `create_synthetic_run`
- synthetic session/run 结构
- `MeasurementRunRecord`
- `ArtifactRef`

不得允许公共虚拟采集入口选择 `DataOrigin.REAL`。

成功 run 必须固定：

```text
data_origin = synthetic
run_mode = development
formal_eligible = false
result_marker = NOT_EXPERIMENTAL_RESULT
status = complete
backend = deterministic_virtual_duplex
```

建议 capture payload 至少包括：

```text
excitation.metadata.json
excitation.metadata.sha256
output_reference.wav
output_reference.wav.sha256
simulated_input.wav
simulated_input.wav.sha256
capture_receipt.json
capture_receipt.sha256
```

外层现有 store 文件可以继续包括：

```text
synthetic_metadata.json
run_record.json
RUN_COMPLETE
```

## 13.1 output_reference.wav

必须表示虚拟调度器实际提供给输出端的完整 frame 序列：

```text
ESS + tail zeros
```

它不是实际播放记录。

## 13.2 simulated_input.wav

必须表示虚拟后端返回的确定性输入：

```text
delayed and scaled software array
```

它不是麦克风录音。

## 13.3 ESS metadata

复制的 ESS metadata 必须来自已经通过 `validate_offline_ess_artifact()` 的 artifact。

不得接受调用者伪造 metadata 或独立 spec。

## 13.4 CaptureReceipt

strict receipt 至少包含：

- schema version；
- capture/run/session/reassembly identity；
- `data_origin=synthetic`；
- `run_mode=development`；
- backend ID/version；
- scenario reference、raw SHA256、normalized SHA256；
- bundle content SHA256；
- device manifest SHA256；
- 全部 config snapshot 原始/normalized SHA256；
- protocol ID；
- `protocol_execution_performed=false`；
- source ESS artifact ID；
- source ESS metadata SHA256；
- source ESS WAV SHA256；
- source ESS raw float32 SHA256；
- ESS sample count；
- capture tail sample count；
- planned/actual output sample count；
- planned/actual input sample count；
- block size；
- planned/actual block count；
- last block frame count；
- integer latency samples；
- linear gain；
- output/input shape；
- output/input dtype；
- output raw float32 SHA256；
- input raw float32 SHA256；
- output WAV SHA256；
- input WAV SHA256；
- block trace；
- state transition trace；
- xrun/dropout/short-read/clipping/error 计数；
- completed/failed/aborted 状态；
- all-finite 结果；
- create-only/immutable 标记；
- `virtual_duplex_scheduler_exercised=true`；
- `hardware_io_performed=false`；
- `playback_performed=false`；
- `recording_performed=false`；
- `hardware_ready=false`；
- `full_duplex_verified=false`；
- `shared_clock_verified=false`；
- `channel_mapping_verified=false`；
- `calibration_file_verified=false`；
- `absolute_spl_calibrated=false`；
- `formal_eligible=false`；
- `experimental_result=false`；
- 安全标记：

`SYNTHETIC_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT`

不得包含：

- 本机绝对路径；
- 用户名；
- 主机名；
- 设备索引；
- Host API；
- 随机 UUID；
- 当前墙钟时间；
- 真实设备延迟声明；
- 真实采集声明；
- 听力安全声明。

receipt 不得包含自己的 SHA256，避免自引用；由 sidecar 记录 receipt 文件哈希。

所有 JSON 必须是 canonical UTF-8、稳定排序、LF 结尾并拒绝 NaN/Infinity。

---

# 14. 虚拟采集验证

新增 read-only 的 capture-specific validator。

它不能只调用现有 `validate_run()` 和检查 sidecar。

必须完成：

1. 验证 synthetic session 和 run identity；
2. 验证 `RUN_COMPLETE`；
3. 验证全部 `ArtifactRef`；
4. 验证 capture 文件集合；
5. 验证每个 sidecar；
6. 验证 canonical JSON；
7. 严格解析 receipt；
8. 验证 loaded bundle 与 session 中保存的配置快照一致；
9. 验证 manifest、protocol、audio、analysis、synthetic config 哈希；
10. 验证 scenario 原始与 normalized SHA256；
11. 验证 ESS metadata 与 loaded audio config；
12. 从 loaded audio config 重新派生 ESS spec；
13. 重新生成确定性 ESS；
14. 重建完整 output reference；
15. 按场景重新执行虚拟输入关系；
16. 比较 output/input 逐样本；
17. 比较 canonical WAV 字节；
18. 比较 raw float32 SHA256；
19. 重新计算 block trace；
20. 重新计算状态轨迹的允许性；
21. 验证全部计数、shape、dtype、flags；
22. 验证 run record 与 receipt 的 identity/config/backend/status 一致。

必须拒绝：

- 只重算 sidecar 的 receipt 篡改；
- 修改 scenario 后重算 sidecar；
- 修改 WAV 后重算 sidecar；
- receipt 与 WAV 互相一致但与 loaded config 不一致；
- ESS metadata 与 audio config 不一致；
- source ESS hash 错配；
- bundle hash 错配；
- session/run/reassembly identity 错配；
- block trace 缺失、重复、重叠或间断；
- completed 但样本不足；
- completed 但存在 fault；
- synthetic run 被标成 real；
- `formal_eligible=true`；
- `experimental_result=true`；
- 任一硬件 readiness 字段变成 true；
- 路径逃逸；
- 额外未声明文件；
- 缺少必需文件。

validator 必须为只读，不得“修复”或重写被验证目录。

---

# 15. CLI

新增两个明确带有仿真语义的命令：

```text
simulate-duplex-capture
validate-simulated-capture
```

不得使用容易被误认为实际录音的简写，例如单独的：

```text
record
capture-real
measure
run-experiment
```

## 15.1 simulate-duplex-capture

必须：

- 加载完整 `LoadedBundle`；
- 加载严格 virtual scenario；
- 验证已有 synthetic session；
- 验证 source ESS artifact；
- 使用虚拟 backend；
- 执行状态机；
- 只在成功后 create-only 发布 synthetic run；
- 不允许 real root 参数；
- 不允许通过命令行单独覆盖 latency、gain、block size 或 ESS spec；
- 不调用任何真实音频 API。

建议复用现有 bundle 参数，并增加：

```text
--synthetic-root
--session-id
--reassembly-id
--run-id
--measurement-order
--scenario
--ess-artifact-root
```

正常开发 run 使用 manifest 全节点 BLK 状态，除非现有架构要求显式节点状态。

这不是正式 protocol 执行，必须记录：

`protocol_execution_performed=false`

## 15.2 validate-simulated-capture

必须接受验证所需的：

- project/bundle 输入；
- scenario；
- synthetic root；
- session ID；
- run ID。

必须调用 capture-specific semantic validator。

## 15.3 CLI 输出

成功时必须清楚输出：

```text
PASS
SYNTHETIC_ONLY
NO_HARDWARE_AUDIO_IO_PERFORMED
NOT_AN_EXPERIMENTAL_RESULT
```

并输出：

- capture/run ID；
- sample count；
- block count；
- output WAV SHA256；
- simulated input WAV SHA256；
- receipt SHA256；
- final state。

失败时：

- 返回非零退出码；
- 不得输出 PASS；
- 输出真实错误；
- 输出是否已经发布；
- 不得输出“录音完成”“全双工验证完成”或“实验就绪”。

---

# 16. 预期文件

根据实际架构调整，但建议新增：

```text
src/acoustic_ladder/audio/virtual_capture_models.py
src/acoustic_ladder/audio/virtual_capture_backend.py
src/acoustic_ladder/audio/virtual_capture.py
src/acoustic_ladder/audio/virtual_capture_persistence.py
tests/fixtures/audio/virtual_duplex_development.yaml
tests/dev03/test_virtual_capture.py
schemas/virtual_capture_scenario.schema.json
schemas/virtual_capture_receipt.schema.json
docs/architecture/virtual-capture.md
docs/prompts/DEV-03.04.md
docs/reports/DEV-03.04.md
```

建议修改：

```text
src/acoustic_ladder/cli.py
src/acoustic_ladder/config/schema.py
README.md
docs/IMPLEMENTATION_LOG.md
.gitattributes
```

仅在确有必要时修改：

```text
src/acoustic_ladder/storage/store.py
src/acoustic_ladder/domain/models.py
src/acoustic_ladder/audio/excitation_persistence.py
```

禁止修改保护输入。

如果正好新增两个生成 Schema，最终 Schema 数量应从 15 变为 17。

如果实际模型导出数量不同：

- 必须解释原因；
- Schema 必须由模型生成；
- 不得手工改 Schema 掩盖模型漂移。

---

# 17. TDD 与测试要求

先写失败测试，再实现生产代码。

日志必须保留首次真实 red run：

- 收集测试数量；
- 失败数量；
- 关键失败原因。

不得事后伪造 red run。

DEV-03.04 新增测试建议不少于 40 项，并覆盖以下类别；不得靠无意义参数化填充数量。

## 17.1 场景模型

测试：

- 正常场景；
- unknown field；
- strict numeric；
- bool-as-int；
- block size 0/负数；
- latency 负数；
- tail 小于 latency；
- gain 0/负数；
- NaN；
- Infinity；
- fault mode；
- fault block 条件关系；
- 场景原始/normalized 哈希；
- 场景路径必须为项目相对路径。

## 17.2 状态机

测试：

- 完整正常序列；
- 每个合法 failed 路径；
- 每个合法 aborted 路径；
- 跳过 prepared；
- 跳过 armed；
- completed 后继续；
- failed 后继续；
- aborted 后继续；
- 重复 complete；
- 样本不足 complete；
- block fault 后 complete；
- transition sequence；
- sample cursor 单调性。

## 17.3 正常虚拟执行

测试：

- `[1,n] float32`；
- C-contiguous；
- ESS + tail zeros；
- 37 样本延迟；
- 0.5 gain；
- 输入延迟区为零；
- 无隐式噪声；
- 精确 13024 样本；
- 精确 51 blocks；
- 最后 block 224 frames；
- 非整除 block；
- block 区间无缝；
- 相同输入确定性；
- 不同场景产生不同内容；
- raw float32 SHA256；
- 所有值 finite；
- 正常场景无 clipping。

## 17.4 故障

测试：

- short input block；
- dropout flag；
- clipping；
- non-finite block；
- backend exception；
- abort；
- fault index 越界；
- 最终状态正确；
- 无 `RUN_COMPLETE`；
- 无完成 run 目录；
- staging 被清理；
- 既有数据不被删除；
- 错误信息保留真实 fault block。

## 17.5 存储

测试：

- synthetic-only；
- real root 保持不存在或空；
- create-only；
- 重复 run ID 拒绝；
- 路径逃逸拒绝；
- 文件集合完整；
- ArtifactRef 正确；
- sidecar 正确；
- canonical receipt；
- session/run/reassembly identity；
- config/bundle hash；
- ESS provenance；
- output/input WAV decode；
- receipt 无绝对路径和墙钟；
- 无未声明文件；
- published 状态表达准确。

## 17.6 篡改

至少测试攻击者同时修改内容并重新计算文件 sidecar：

- receipt scenario；
- receipt bundle hash；
- receipt ESS hash；
- receipt latency；
- receipt gain；
- receipt block trace；
- receipt state trace；
- output WAV；
- input WAV；
- ESS metadata；
- run identity；
- formal/hardware flags。

这些篡改必须被 semantic validator 拒绝。

## 17.7 CLI

测试：

- 正常 simulate；
- 正常 validate；
- 正式 AudioConfig 因 ESS 字段为 null 被拒绝；
- hardware flags 保持 false；
- fault CLI 非零退出；
- 不创建完成 run；
- 无真实音频调用；
- stdout 包含 synthetic marker；
- stdout 不包含真实录音/实验就绪声明；
- 不允许 CLI 数值覆盖场景；
- real root 不可选。

## 17.8 禁止调用证明

使用 AST、导入替换或等价方法验证 DEV-03.04 新代码没有：

```text
sounddevice import
query_devices
query_hostapis
check_input_settings
check_output_settings
InputStream
OutputStream
Stream
play
rec
playrec
sleep
```

测试中使用的 fake/virtual 名称不应被误判。

不得使用：

- `skip`
- `xfail`
- `noqa`
- `type: ignore`
- 宽泛异常吞噬

来掩盖问题。

---

# 18. 软件演示验收

在系统临时目录中完成一次真实的软件演示，但不得触碰音频硬件。

流程：

1. 创建精确、预先确认不存在的临时 development ESS root；
2. 使用既有 development ESS fixture 生成离线 ESS artifact；
3. 验证 ESS artifact；
4. 创建精确、预先确认不存在的 synthetic root；
5. 创建 synthetic session；
6. 执行 normal virtual duplex capture；
7. 验证 capture run；
8. 重新验证 session；
9. 输出 receipt 关键字段和真实 SHA256；
10. 仅清理本次创建的两个精确临时根；
11. 确认两个根均不存在。

演示必须确认：

```text
state = completed
data_origin = synthetic
run_mode = development
formal_eligible = false
experimental_result = false
hardware_io_performed = false
playback_performed = false
recording_performed = false
hardware_ready = false
```

必须记录实际：

- ESS sample count；
- capture sample count；
- block count；
- last block frames；
- output shape/dtype；
- input shape/dtype；
- latency；
- gain；
- output WAV SHA256；
- input WAV SHA256；
- receipt SHA256；
- cleanup 结果。

另外执行正式配置负例：

- 使用 `config/audio/default_1x1_ess.yaml`；
- 必须列出真实缺失 ESS 字段；
- 必须在创建 capture run 前拒绝；
- 不得填写默认参数；
- 不得产生完成 run。

临时清理必须：

- 只针对预先确认不存在且由本次创建的精确目录；
- 不使用宽泛 glob；
- 不删除 workspace；
- 不删除用户目录；
- 不删除既有 synthetic/real 数据。

---

# 19. 完整验证门禁

至少运行：

```text
uv --cache-dir .uv-cache sync --all-groups --frozen
```

然后分组运行并记录：

- DEV-01 原有测试；
- DEV-02.01 原有测试；
- DEV-02.02 原有测试；
- DEV-03.01 原有测试；
- DEV-03.02 原有测试；
- DEV-03.03/03.03R 原有 ESS 测试；
- DEV-03.04 新测试；
- 完整测试。

原有 `277` 项必须全部保留通过。

执行：

```text
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
git diff --check
```

strict mypy 必须通过。

不得降低 mypy、Ruff、pytest 或 Schema 检查强度。

必须扫描：

- skip/xfail；
- suppression；
- U+FFFD；
- 本机绝对路径；
- 用户身份；
- 非法真实音频调用；
- 直接 `sounddevice` import；
- 新增 WAV/FLAC/NPY/NPZ 是否误入 Git；
- staging；
- publication lock；
- 临时目录；
- 未跟踪文件。

必须重新计算：

- 七个受保护文件 SHA256；
- 三个 ESS golden SHA256；
- DEV-03.04 prompt SHA256；
- 场景 raw/normalized SHA256；
- 演示 capture hashes。

必须证明：

- `docs/IMPLEMENTATION_LOG.md` 旧内容完整保留；
- 只有 DEV-03.04 条目追加；
- 保护文件相对基线无 diff；
- 正式 AudioConfig 未被 development 参数污染；
- real root 未写入；
- 没有实际播放、录音、stream 或新 inventory。

如果任何检查失败：

- 如实记录失败；
- 可以修正并重新运行；
- 在全部通过前不得提交或推送；
- 不得删除失败历史；
- 不得把未运行写成通过。

---

# 20. 文档

新增：

`docs/architecture/virtual-capture.md`

必须说明：

- virtual full duplex 只是软件调度语义；
- 绝不等同于真实硬件 full-duplex verification；
- 状态机；
- block contract；
- sample cursor；
- 确定性延迟/增益公式；
- fault modes；
- synthetic/real 隔离；
- bundle 文件；
- receipt 权威链；
- semantic validation；
- create-only 边界；
- 失败/中止语义；
- published 状态语义；
- 不使用墙钟作为音频时钟；
- 当前限制。

更新 README，加入：

- 如何生成 development ESS；
- 如何创建 synthetic session；
- 如何运行 virtual capture；
- 如何验证 virtual capture；
- 清晰的 `NO HARDWARE I/O` 警告；
- 正式配置仍不可执行的说明。

新增：

`docs/reports/DEV-03.04.md`

报告必须基于实际执行结果，包括：

- outcome；
- baseline；
- 实际文件；
- API/模型；
- 状态机；
- scenario；
- 正常执行结果；
- 故障结果；
- artifact hashes；
- 测试数量；
- 静态检查；
- Schema 数量；
- 保护哈希；
- 未执行范围；
- 已知限制；
- Git 尚未提交时不能自引用最终 SHA。

不得写成论文结论或声学结论。

---

# 21. Git 提交和推送门禁

只有以下条件全部满足才允许提交：

- 功能完整；
- DEV-03.04 测试通过；
- 原有 277 项全部通过；
- 完整测试通过；
- Ruff format 通过；
- Ruff lint 通过；
- strict mypy 通过；
- Schema consistency 通过；
- `git diff --check` 通过；
- 七个保护哈希正确；
- 三个 ESS golden hash 不变；
- 日志真实完整；
- 报告真实完整；
- 无真实硬件调用；
- 无误入 Git 的音频或临时产物；
- 工作区只包含本步骤预期修改。

提交前再次执行：

```text
git ls-remote origin refs/heads/main
```

远端 `main` 必须仍为：

`fcaf4f7bbac2778c21888d8e8bc4676b2350e926`

若远端已变化：

- 停止；
- 不 rebase；
- 不 merge；
- 不 force push；
- 不提交未经重新审查的组合结果；
- 报告远端变化。

建议提交主题：

`DEV-03.04: add deterministic virtual duplex capture`

提交后：

1. 确认工作区干净；
2. 确认本地 commit 内容正确；
3. 正常推送：

```text
git push origin main
```

4. 不得 force push；
5. 再次读取 GitHub `main`；
6. 确认以下三者完全一致：

```text
local HEAD
origin/main
GitHub refs/heads/main
```

如果提交或推送过程中发生任何错误：

- 不得声称成功；
- 不得 force push；
- 不得隐藏错误；
- 不得继续后续阶段；
- 报告本地是否已经生成 commit；
- 报告远端是否发生变化。

---

# 22. 最终回复格式

成功时必须报告：

- `PASS — DEV-03.04 完成`
- 最终 commit SHA；
- remote URL；
- branch；
- local/origin/GitHub 是否一致；
- 工作区是否干净；
- 原有测试数量；
- 新增测试数量；
- 完整测试数量；
- Ruff/mypy/Schema/diff 结果；
- Schema 最终数量；
- scenario raw/normalized SHA256；
- output WAV SHA256；
- simulated input WAV SHA256；
- capture receipt SHA256；
- 七个保护哈希；
- 三个 ESS golden hash；
- 硬件枚举：否；
- 播放：否；
- 录音：否；
- Stream：否；
- `hardware_ready=false`；
- 主要交付文件；
- 已知限制。

必须明确写出：

```text
本步骤只完成确定性虚拟采集执行内核。
virtual_duplex_scheduler_exercised=true 不等于 full_duplex_verified=true。
没有连接、枚举、播放、录制或验证任何真实音频硬件。
```

失败或中断时必须报告：

- `FAILED`、`BLOCKED` 或 `INTERRUPTED`；
- 失败发生在哪个门禁；
- 实际错误；
- 已修改文件；
- 是否产生本地 commit；
- 明确说明未推送；
- 不得宣布进入下一阶段。

完成 DEV-03.04 后停止。

不得自行进入：

- 真实硬件连接；
- 新 inventory；
- 设备绑定；
- 真实 full-duplex stream；
- 麦克风校准；
- SPL 校准；
- 真实 ESS 播放；
- 真实录音；
- 反卷积；
- 脉冲响应；
- 传递函数；
- QC；
- DEV-03.05；
- DEV-04。