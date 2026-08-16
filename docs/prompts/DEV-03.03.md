# DEV-03.03 项目实施提示词——离线 ESS 激励契约、确定性生成与审计闭环加固

你现在位于 Acoustic Ladder 的实际代码仓库中。

本步骤序列号：

`DEV-03.03`

本步骤名称：

`离线 ESS 激励契约、确定性生成与审计闭环加固`

只执行本步骤。完成后停止，不得自行进入 DEV-03.04、DEV-04 或任何真实音频实验。

---

# 1. 本步目标

本步骤需要完成两项工作：

1. 在不连接、不枚举、不调用任何实验硬件的条件下，建立严格、可复现、可审计的离线指数正弦扫频 ESS 生成能力。
2. 补齐 DEV-03.02 中 `audio-context-validate` 的语义验证闭环，使其不仅验证 sidecar，还能识别“文件自身 sidecar 正确，但文件与 inventory/context/hardware 不匹配”的情况。

本步骤必须实现：

- 严格的 ESS 参数契约；
- 确定性的离线 ESS 数学生成；
- 规范的单通道 float32 WAV；
- channel-first 内存数组；
- canonical JSON 元数据；
- SHA256 sidecar；
- create-only、受限路径、成组发布；
- 离线生成 CLI；
- 离线验证 CLI；
- 完整数值、存储、安全和篡改测试；
- DEV-03.02 审计链语义一致性加固；
- 提示词、实施日志和完成报告；
- 只有全部验收成功后才提交并推送 GitHub。

本步骤不实施：

- 音频播放；
- 音频录音；
- 全双工流；
- 真实设备枚举；
- 设备索引、Host API 或通道绑定；
- 声学校准；
- 绝对 SPL；
- 麦克风校准文件读取或应用；
- ESS 反卷积；
- 脉冲响应；
- 复传递函数；
- QC 处理链；
- 真实实验协议执行；
- 正式实验参数锁定。

---

# 2. 已冻结的研究与硬件条件

以下条件不得改变。

## 2.1 研究边界

正式实验仍是：

`1 个扬声器输出 + 1 个麦克风输入`

即：

`1 + 1`

底层数据结构可以继续支持：

`outputs[n_output_channels, n_samples]`

`inputs[n_input_channels, n_samples]`

但阶段 1–4 的正式协议仍固定为 1+1。

边界条件保持：

- TX 近端：扬声器；
- RX 近端：麦克风；
- TX 远端：闭合；
- RX 远端：闭合；
- 未使用节点：BLK；
- 不得把 BLK 解释为开放；
- 不得改变为麦克风阵列或多扬声器正式协议。

## 2.2 模型状态

当前项目：

`Acoustic Ladder V1.3 校准后圆形主管版本`

当前物理状态：

`physical_print_status = actual_printed`

当前校准状态：

`calibration_status = applied`

但在最终打印包差异检查和几何锁定前，仍必须保持：

`model_status = provisional`

不得标记：

- `geometry_locked`
- `experiment_ready`
- `release`
- `formal_ready`

## 2.3 当前音频硬件事实

操作者已经确认：

- MOONDROP CHU II / 水月雨竹 2 未连接；
- Dayton Audio iMM-6C 未连接；
- 实验装置未连接；
- 当前 DEV-03.01 inventory 是无实验硬件的开发主机基线；
- inventory 中所有现有端点均不是实验设备候选；
- 当前不选择设备索引；
- 当前不选择 Host API；
- 当前不选择输入或输出通道；
- 当前不进行真实音频预检；
- 当前不应用麦克风校准文件；
- 当前不进行绝对 SPL 校准；
- 当前不进行电气回环。

必须继续保持：

`hardware_ready = false`

`full_duplex_verified = false`

`shared_clock_verified = false`

`channel_mapping_verified = false`

`calibration_file_verified = false`

`absolute_spl_calibrated = false`

设备绑定仍为：

`deferred_until_hardware_connection`

## 2.4 当前正式音频配置

当前已确认但仍属临时配置的参数：

- 采样率：48 kHz；
- ESS 起始频率：300 Hz；
- ESS 结束频率：10 kHz；
- 主要分析范围：500 Hz–8 kHz。

以下正式参数仍未知，必须保持 `null`：

- 正式 ESS 时长；
- 正式前置静音；
- 正式后置静音；
- 正式淡入时间；
- 正式淡出时间；
- 正式数字峰值；
- 正式输出增益；
- 正式输入增益。

不得根据测试夹具、经验或通用建议填写这些正式字段。

特别注意：

- 数字波形峰值使用 dBFS 表达；
- `output_gain_db` 和 `input_gain_db` 是未来硬件/接口相关参数；
- 数字波形峰值不得与硬件输出增益混为同一字段；
- 任意 dBFS 数值都不能被描述成对耳机或人耳“安全”；
- 本步骤生成的开发波形不得播放。

---

# 3. Git 基线和开始门禁

首先读取仓库，不要立即修改文件。

必须确认：

- 仓库根目录正确；
- 当前分支为 `main`；
- 工作区干净；
- 没有未提交文件；
- 没有未跟踪的用户文件需要处理；
- remote 名称为 `origin`；
- remote URL 为：

`https://github.com/haocheng26710/fingers.git`

必须确认本地 HEAD、`origin/main` 和 GitHub 远端 `main` 均为：

`1ca161c1da4fa02054c023a86941a72adb517e9c`

建议执行并记录实际结果：

- `git status --short --branch`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `git remote -v`
- `git ls-remote origin refs/heads/main`
- 项目级 `AGENTS.md`、`CLAUDE.md`、`CONTEXT.md` 或其他指令文件扫描

如果发生以下任一情况，立即停止：

- HEAD 不一致；
- 远端已经前进；
- 工作区不干净；
- 存在无法安全保留的用户修改；
- remote URL 不一致；
- 发现新的项目指令与本提示词冲突。

停止时：

- 不得 reset；
- 不得 checkout 覆盖文件；
- 不得 clean；
- 不得删除用户文件；
- 不得提交；
- 不得推送；
- 必须报告实际阻塞信息。

禁止：

- `git reset --hard`
- `git clean`
- 强制 checkout
- force push
- rebase 已发布的 `main`
- 修改历史提交
- amend DEV-03.02

---

# 4. 开始时建立并更新审计记录

在开始实际实现时，先完成以下动作。

## 4.1 保存本提示词

将本提示词按收到的原始内容保存为：

`docs/prompts/DEV-03.03.md`

要求：

- UTF-8；
- LF 换行；
- 不得总结；
- 不得删节；
- 不得改写；
- 不得把代码块之外的聊天内容编造进提示词；
- 如果运行环境提供了原始提示词附件，应直接复制并比较源文件与目标文件 SHA256；
- 如果没有原始附件，则保存实际收到的完整提示词文本，并在日志中如实说明保存方式；
- 将该文件视为本步骤的审计输入。

## 4.2 实施日志

读取并保留：

`docs/IMPLEMENTATION_LOG.md`

必须保证当前文件的全部既有字节保持为新文件的完整前缀。

只允许在末尾追加：

`## DEV-03.03`

该条目固定采用与 DEV-03.01、DEV-03.02 相同的“序列号 + 字段内容”形式。

开始时先记录：

- 序列号；
- 名称；
- 状态 `IN_PROGRESS`；
- 开始时间和时区；
- 基线提交；
- 远端基线；
- 本步骤范围；
- 已确认没有连接实验硬件；
- 预期禁止范围。

执行过程中持续追加或更新本步骤的新条目，但不得修改任何既有步骤。

结束时将本步骤状态更新为真实状态：

- `PASSED`
- `FAILED`
- `BLOCKED`
- `INTERRUPTED`

日志必须记录：

- 实际创建和修改的文件；
- 每条重要命令；
- 实际参数；
- 实际生成的哈希；
- 测试数量和结果；
- 初次失败；
- 错误原因；
- 实际修正；
- 未执行项目及原因；
- 已知限制；
- Git 提交和推送门禁状态。

不得预先写“测试通过”“推送成功”或不存在的错误。

日志详细程度必须足以让另一名操作者借助其他 AI 尽可能复刻相同实现和验证过程。

---

# 5. 受保护输入和已知哈希

重新计算并核对下列文件，不得只照抄本提示词。

## 5.1 模型包

文件：

`reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip`

预期 SHA256：

`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`

## 5.2 provisional manifest

文件：

`config/devices/device_manifest.provisional.json`

预期 SHA256：

`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

## 5.3 DEV-03.01 inventory

文件：

`reference/audio/inventory/DEV-03.01_audio_inventory.json`

预期 SHA256：

`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

## 5.4 DEV-03.02 capture context

文件：

`reference/audio/inventory/DEV-03.02_inventory_capture_context.json`

预期 SHA256：

`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`

## 5.5 DEV-03.02 summary

文件：

`reference/audio/inventory/DEV-03.02_audio_inventory_summary.md`

预期 SHA256：

`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`

## 5.6 DEV-03.02 contextual preflight

文件：

`reference/audio/inventory/DEV-03.02_contextual_preflight_report.json`

预期 SHA256：

`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`

## 5.7 provisional hardware setup

文件：

`reference/audio/hardware_setup.provisional.json`

预期 SHA256：

`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

本步骤不得修改：

- V1.3 ZIP；
- provisional manifest 及 sidecar；
- calibration record；
- DEV-03.01 inventory 及 sidecar；
- DEV-03.01 preflight；
- provisional hardware setup；
- DEV-03.02 capture context 及 sidecar；
- DEV-03.02 summary 及 sidecar；
- DEV-03.02 contextual preflight 及 sidecar；
- 既有提示词；
- 既有实施日志内容。

如果实际哈希不一致，停止，不得继续，不得推送。

---

# 6. 输入文件

实现前至少阅读：

- `pyproject.toml`
- `uv.lock`
- `README.md`
- `.gitignore`
- `.gitattributes`
- `config/audio/default_1x1_ess.yaml`
- `config/analysis/default.yaml`
- `src/acoustic_ladder/config/models.py`
- `src/acoustic_ladder/config/schema.py`
- `src/acoustic_ladder/config/loader.py` 或实际配置加载模块
- `src/acoustic_ladder/audio/models.py`
- `src/acoustic_ladder/audio/persistence.py`
- `src/acoustic_ladder/audio/preflight.py`
- `src/acoustic_ladder/audio/summary.py`
- `src/acoustic_ladder/audio/backend.py`
- `src/acoustic_ladder/cli.py`
- `src/acoustic_ladder/storage/io.py`
- `src/acoustic_ladder/domain/paths.py`
- `tests/dev03/`
- `docs/architecture/audio-inventory.md`
- `docs/architecture/configuration.md`
- `data/README.md`
- `docs/reports/DEV-03.02.md`
- `docs/IMPLEMENTATION_LOG.md`

复用已有：

- strict Pydantic 模型；
- canonical JSON；
- 安全相对路径；
- create-only 写入；
- SHA256 sidecar；
- Schema 导出与一致性检查；
- 可注入测试结构；
- CLI 约定；
- synthetic/real 强隔离原则。

不得另建一套相互冲突的存储和配置框架。

---

# 7. 预期创建或修改的文件

根据实际架构决定最终文件名，但建议包括：

## 7.1 代码

- `src/acoustic_ladder/audio/ess.py`
- `src/acoustic_ladder/audio/excitation_models.py`
- `src/acoustic_ladder/audio/excitation_persistence.py`
- `src/acoustic_ladder/audio/persistence.py`
- `src/acoustic_ladder/audio/models.py`
- `src/acoustic_ladder/config/models.py`
- `src/acoustic_ladder/config/schema.py`
- `src/acoustic_ladder/cli.py`

文件可合理合并，但职责必须清晰。

## 7.2 配置与测试夹具

更新：

`config/audio/default_1x1_ess.yaml`

只增加必要的 nullable ESS 字段，不得填写未知正式值。

可新增仅用于测试的开发配置，例如：

`tests/fixtures/audio/ess_offline_development.yaml`

该夹具必须明确：

- `run_mode = development`
- `config_status = draft`
- `hardware_ready = false`
- `formal_eligible = false`
- `playback_authorized = false`
- `experimental_result = false`
- 仅用于数学、存储和 CLI 测试。

建议测试夹具参数：

- sample rate：48000 Hz；
- start：300 Hz；
- end：10000 Hz；
- sweep duration：0.25 s；
- pre-silence：0.01 s；
- post-silence：0.01 s；
- fade-in：0.005 s；
- fade-out：0.005 s；
- digital peak：-20 dBFS。

这些值只能作为 DEV-03.03 数学测试夹具，不得复制到正式配置的未知字段，不得描述为实验推荐值或听力安全值。

## 7.3 Schema

建议新增：

- `schemas/ess_signal_spec.schema.json`
- `schemas/ess_artifact_metadata.schema.json`

如果正好新增两个生成 Schema，Schema 总数应从 13 增加到 15。

如果实际设计导致数量不同，必须在报告中解释原因；不得手工修改生成 Schema 掩盖模型漂移。

## 7.4 测试

建议新增：

`tests/dev03/test_ess_offline.py`

可按职责拆分，但 DEV-03.03 新增测试总数不得少于 30 项。

## 7.5 文档

- `docs/prompts/DEV-03.03.md`
- `docs/reports/DEV-03.03.md`
- `docs/architecture/ess-excitation.md`
- 更新 `README.md`
- 更新 `docs/architecture/configuration.md`
- 必要时更新 `docs/architecture/audio-inventory.md`
- 向 `docs/IMPLEMENTATION_LOG.md` 末尾追加 DEV-03.03

## 7.6 依赖

优先复用标准库和 NumPy。

如果为可靠写入和读取 IEEE float WAV 需要使用 `soundfile` 或等价库：

- 必须在 `pyproject.toml` 中添加受约束依赖；
- 必须更新 `uv.lock`；
- 必须记录实际版本；
- 必须验证 Windows 环境可安装；
- 不得静默回退为不同 WAV 格式；
- 不得引入播放功能；
- 不得使用库的设备或流 API。

不得为了写一个 WAV 引入完整音频工作站或大型无关框架。

---

# 8. ESS 配置契约

## 8.1 正式 AudioConfig 扩展

为 `AudioConfig` 增加或等价表达：

- `ess_fade_in_s: float | null`
- `ess_fade_out_s: float | null`
- `ess_digital_peak_dbfs: float | null`

约束：

- fade 不得为负；
- digital peak 不得大于 0 dBFS；
- 正式配置允许这些值为 `null`；
- `hardware_ready=true` 时仍必须满足既有完整性条件；
- 本步骤不得将 `hardware_ready` 改成 true。

更新：

`config/audio/default_1x1_ess.yaml`

其中必须保持：

- `ess_duration_s: null`
- `pre_silence_s: null`
- `post_silence_s: null`
- `ess_fade_in_s: null`
- `ess_fade_out_s: null`
- `ess_digital_peak_dbfs: null`
- `output_gain_db: null`
- `input_gain_db: null`
- 设备、Host API、通道索引全部为 null；
- `hardware_ready: false`。

## 8.2 EssSignalSpec

新增严格、禁止未知字段的 `EssSignalSpec` 或等价模型，至少包含：

- schema version；
- algorithm ID；
- algorithm version；
- sample rate；
- start frequency；
- end frequency；
- sweep duration；
- pre-silence duration；
- post-silence duration；
- fade-in duration；
- fade-out duration；
- digital peak dBFS；
- output channel count；
- output dtype；
- usage scope；
- playback authorization；
- formal eligibility；
- experimental-result 标记。

本步骤允许的持久化开发规格必须满足：

- `usage_scope = development_fixture`
- `playback_authorized = false`
- `formal_eligible = false`
- `experimental_result = false`
- `output_channel_count = 1`
- `output_dtype = float32`

不要把生成的激励本身标记为真实实验数据。

建议使用：

`artifact_origin = software_generated`

`artifact_role = development_test_excitation`

不要错误地声称它是一次 acoustic measurement。

## 8.3 参数校验

至少拒绝：

- sample rate ≤ 0；
- start frequency ≤ 0；
- end frequency ≤ start frequency；
- end frequency ≥ Nyquist；
- sweep duration ≤ 0；
- 任一 silence < 0；
- 任一 fade < 0；
- fade-in + fade-out 超过 sweep duration；
- 非零 fade 只对应 0 或 1 个样本；
- digital peak > 0 dBFS；
- output channel count 不是 1；
- dtype 不是 float32；
- playback authorization 为 true；
- formal eligibility 为 true；
- NaN；
- Infinity；
- 未知字段；
- 字符串代替严格数值；
- 不完整的正式 `AudioConfig` 被当作完整生成规格。

从 `AudioConfig` 提取 ESS 规格时，如果必要字段为 null，必须明确列出缺失字段并拒绝生成，不得填默认值。

---

# 9. ESS 数学定义

使用确定性的指数正弦扫频。

令：

- `f0 = start_frequency_hz`
- `f1 = end_frequency_hz`
- `r = f1 / f0`
- `fs = sample_rate_hz`
- `N = sweep_sample_count`
- `T = N / fs`

相位定义：

`phi(t) = 2*pi*f0*T/ln(r) * (exp(t*ln(r)/T) - 1)`

扫频：

`x(t) = sin(phi(t))`

离散时间：

`t[n] = n / fs`

其中：

`n = 0, 1, ..., N-1`

必须在文档中说明：

- 理论瞬时频率在 `t=0` 为 `f0`；
- 理论瞬时频率在边界 `t=T` 为 `f1`；
- 最后一个实际离散样本位于 `T - 1/fs`；
- 因此不得错误断言最后一个采样点的瞬时频率精确等于 `f1`。

## 9.1 样本数转换

秒到样本数必须使用一种明确、跨运行稳定的规则。

建议对非负值使用：

`floor(seconds * sample_rate + 0.5)`

即 round-half-up。

必须记录：

- 请求秒数；
- 派生样本数；
- 实际秒数 `samples / sample_rate`；
- 请求值与实际值的差。

不得依赖未记录的隐式取整。

## 9.2 淡入淡出

使用明确记录的确定性窗函数，例如半余弦窗。

要求：

- fade-in 起点严格为 0；
- fade-out 终点严格为 0；
- 不得作用于前后静音区；
- 前后静音必须保持精确零；
- fade 样本数必须记录；
- fade 公式和端点约定必须记录；
- fade 为 0 时不得出现除零；
- 非零 fade 必须至少包含 2 个样本。

## 9.3 数字幅度

目标线性峰值：

`target_peak = 10 ** (digital_peak_dbfs / 20)`

在施加淡入淡出后，对 sweep 有效区进行确定性归一化，使 float32 输出峰值在规定容差内等于目标峰值。

必须记录：

- 归一化前峰值；
- 归一化因子；
- 目标峰值；
- float32 实际峰值；
- RMS；
- crest factor；
- 均值/DC；
- 最小值；
- 最大值；
- finite 检查。

不得通过 DC 去除或其他未声明处理改变波形。

不得将测试夹具的 -20 dBFS 描述为实际耳机安全级别。

## 9.4 输出数组

纯生成 API 必须返回 channel-first：

`shape = [1, total_sample_count]`

要求：

- dtype 为 NumPy `float32`；
- C-contiguous 或明确记录实际内存约定；
- 所有值 finite；
- 前置静音精确为零；
- 后置静音精确为零；
- 不削波；
- 不包含随机噪声；
- 相同规格必须得到逐样本完全相同的 float32 数组。

---

# 10. WAV 和元数据产物

## 10.1 WAV

输出单通道 WAV，要求：

- mono；
- sample rate 来自规格；
- IEEE float32 WAV，或经过充分理由说明且能无损恢复 float32 样本的等价格式；
- 不得静默量化为 int16；
- 不得自动归一化；
- 不得添加随机或当前时间元数据；
- 写入后必须重新读取；
- 重新读取的 float32 数组必须与生成数组逐样本相等；
- WAV 文件必须有 SHA256 sidecar。

内存 API 继续使用 `[channel, sample]`。

WAV 文件可以使用常规 mono 帧布局，但读取层必须恢复为 `[1, n_samples]`。

## 10.2 EssArtifactMetadata

新增 strict 元数据模型，至少包含：

- schema version；
- artifact ID；
- artifact origin；
- artifact role；
- algorithm ID；
- algorithm version；
- source audio config 的仓库相对路径；
- source audio config 原文件 SHA256；
- source audio config normalized SHA256；
- 完整的解析后 ESS 规格；
- sample rate；
- channel count；
- dtype；
- sweep/pre/post/fade 样本数；
- total sample count；
- 请求和实际时长；
- shape；
- target peak dBFS；
- target linear peak；
- actual peak；
- RMS；
- crest factor；
- DC/mean；
- min/max；
- raw float32 sample-byte SHA256；
- WAV SHA256；
- writer 名称和版本；
- `playback_authorized = false`；
- `formal_eligible = false`；
- `experimental_result = false`；
- `hardware_ready = false`；
- 安全标记。

安全标记固定为：

`OFFLINE_GENERATION_ONLY_NOT_AUTHORIZED_FOR_PLAYBACK`

元数据不得包含：

- 用户名；
- 主机名；
- 本机绝对路径；
- 临时目录绝对路径；
- 随机 UUID；
- 当前时间；
- 设备索引；
- Host API；
- 未确认通道；
- 伪造的硬件增益；
- 伪造的校准状态。

为保持产物确定性，本步骤的离线 excitation metadata 不应写入生成时间。实际未来 measurement 的时间戳由 run/session 记录负责。

## 10.3 canonical JSON 和 sidecar

元数据必须：

- canonical JSON；
- UTF-8；
- 稳定键排序；
- LF；
- 禁止 NaN/Infinity；
- 有 SHA256 sidecar；
- 可由 strict 模型重新解析；
- 相同输入产生相同字节。

sidecar 文件名和格式必须稳定、可验证。

---

# 11. create-only 与成组发布

不得直接把多个产物逐个写入最终目录后再祈望全部成功。

实现安全的开发产物目录发布，例如：

`<development-root>/<artifact-id>/`

其中至少包含：

- `excitation.wav`
- `excitation.wav.sha256`
- `excitation.metadata.json`
- `excitation.metadata.sha256`

要求：

1. `artifact-id` 必须通过安全标识符校验；
2. 最终路径必须限制在调用者明确提供的 development root 内；
3. 禁止绝对持久化引用；
4. 禁止 `..`；
5. 禁止路径穿越；
6. 最终 artifact directory 必须 create-only；
7. 如果目录已存在，必须失败且不覆盖；
8. 先在同一父文件系统的临时目录中生成全部文件；
9. 生成后先完成内部验证；
10. 再以 create-only 方式发布完整目录；
11. 失败时只能清理本次创建的临时文件；
12. 不得删除已有最终目录；
13. 不得写入 real 数据根；
14. 不得把测试产物提交进 Git。

如果 Windows 上无法提供严格的多文件原子提交，应：

- 尽可能采用同父目录 staging + 不覆盖 rename；
- 明确记录平台语义；
- 在发布前检查目标不存在；
- 在发布后立即完整验证；
- 不得声称超出实际保证范围的“绝对原子性”。

---

# 12. CLI

新增名称清晰的离线命令，例如：

- `acoustic-ladder ess-generate-offline`
- `acoustic-ladder ess-validate-offline`

## 12.1 ess-generate-offline

至少接受：

- `--project-root`
- `--audio-config`
- `--development-root`
- `--artifact-id`

行为：

1. 安全加载配置；
2. 记录原文件和 normalized config hash；
3. 只提取 ESS 相关字段；
4. 缺失字段时明确失败；
5. 拒绝当前不完整的正式配置；
6. 接受显式的 development 测试配置；
7. 生成波形；
8. 写入 staging；
9. 重新读取并验证；
10. create-only 发布；
11. 输出 artifact 相对信息和哈希；
12. 输出安全标记。

必须输出：

`OFFLINE_GENERATION_ONLY_NOT_AUTHORIZED_FOR_PLAYBACK`

不得：

- 调用 `_audio_backend()`；
- 实例化 `SoundDeviceInventoryBackend`；
- import 实际 `sounddevice` 模块；
- query devices；
- check settings；
- 播放；
- 录音；
- 打开 stream；
- wait 音频流；
- 绑定设备。

## 12.2 ess-validate-offline

至少接受：

- `--project-root`
- `--audio-config`
- `--artifact-root`

必须执行：

- 安全加载规格和配置；
- 验证所有 sidecar；
- 验证元数据模型；
- 验证 WAV 基本格式；
- 读取 WAV 为 `[1, n] float32`；
- 验证 shape；
- 验证样本数；
- 验证静音区；
- 验证 finite；
- 验证峰值和指标；
- 验证 raw float32 sample-byte SHA256；
- 从已验证配置重新生成预期波形；
- 使用 `np.array_equal` 或同等级逐样本严格比较；
- 重新计算元数据中所有派生指标；
- 验证 metadata 中 config hash；
- 验证 WAV hash；
- 即使攻击者重新计算了某个被修改文件的 sidecar，也必须通过跨文件和重新生成检查识别语义不一致。

该命令必须只读，不得重写、修复或覆盖产物。

---

# 13. DEV-03.02 审计闭环加固

现有 `audio-context-validate` 不能只停留在“文件和它自己的 sidecar 一致”。

必须增强该命令。

## 13.1 输入

在现有参数基础上增加必要参数，例如：

- `--hardware-setup`
- `--hardware-setup-reference`

继续使用：

- inventory；
- inventory sidecar；
- context；
- context sidecar；
- summary；
- summary sidecar；
- contextual preflight；
- contextual preflight sidecar。

## 13.2 必须验证的语义关系

1. inventory sidecar 正确；
2. context sidecar 正确；
3. summary sidecar 正确；
4. contextual preflight sidecar 正确；
5. hardware setup 能通过 strict 模型解析；
6. hardware setup 实际 SHA256 等于 contextual preflight 中记录的 SHA256；
7. 所有持久化引用均为仓库相对路径；
8. context 引用的 inventory 路径和 SHA256正确；
9. contextual preflight 引用的 inventory 路径和 SHA256正确；
10. contextual preflight 引用的 context 路径和 SHA256正确；
11. contextual preflight 引用的 hardware setup 路径和 SHA256正确；
12. 使用已验证 inventory/context 重新生成 summary；
13. 重新生成的 summary 字节必须与当前 summary 完全一致；
14. 使用已加载 contextual preflight 的 `generated_at` 作为固定时间，重新构造预期 contextual preflight；
15. 重新构造的模型内容必须与已提交 contextual preflight 完全一致；
16. candidate 列表保持为空；
17. binding/confirmation 保持 deferred；
18. 所有 readiness/calibration 字段保持 false。

必须新增篡改测试：

- 用另一个内容正确且 sidecar 也重新计算的 summary 替换原 summary，验证必须失败；
- 修改 summary 设备名并重新计算 sidecar，验证必须失败；
- 修改 hardware setup 内容，验证必须失败；
- 修改 contextual preflight 的 hardware hash 并重新计算其 sidecar，验证必须失败；
- 修改任一引用路径并重新计算 sidecar，验证必须失败；
- 调换 context 和 inventory 组合，验证必须失败；
- 原始已提交文件必须继续通过。

该加固命令仍不得：

- 重新枚举硬件；
- 调用 sounddevice；
- 修改 DEV-03.02 产物；
- 自动修复文件。

更新 README 中相应验证命令。

---

# 14. 测试要求

DEV-03.03 至少新增 30 项有效测试。

不得使用以下方式掩盖问题：

- skip；
- xfail；
- noqa；
- type ignore；
- 放宽 strict mypy；
- 删除既有测试；
- 修改断言使错误行为通过；
- 使用过宽误差容限；
- mock 掉被测试的核心数学逻辑。

## 14.1 配置测试

至少覆盖：

1. 当前正式配置未知字段继续为 null；
2. 当前正式配置不能生成 ESS；
3. 错误信息列出缺失字段；
4. development fixture 能生成严格规格；
5. 起始频率非正被拒绝；
6. 结束频率不大于起始频率被拒绝；
7. Nyquist 冲突被拒绝；
8. 非正 sweep duration 被拒绝；
9. 负 silence 被拒绝；
10. 负 fade 被拒绝；
11. fade 总长越界被拒绝；
12. 不足两个样本的非零 fade 被拒绝；
13. 大于 0 dBFS 被拒绝；
14. NaN/Infinity 被拒绝；
15. 未知字段被拒绝；
16. 字符串数值不被隐式接受；
17. playback authorization=true 被拒绝；
18. formal eligibility=true 被拒绝。

## 14.2 ESS 数学测试

至少覆盖：

1. 相同规格逐样本确定性；
2. 输出 dtype 为 float32；
3. 输出 shape 为 `[1, n]`；
4. total sample count 正确；
5. round-half-up 规则正确；
6. pre-silence 精确为零；
7. post-silence 精确为零；
8. fade-in 首样本为零；
9. fade-out 末样本为零；
10. 所有值 finite；
11. 不削波；
12. 实际峰值符合目标；
13. 理论相位公式正确；
14. 理论瞬时频率从 f0 单调增加到边界 f1；
15. 不把最后离散样本误判为精确 f1；
16. 没有随机噪声；
17. 元数据指标与数组重算一致；
18. raw sample-byte SHA256 稳定。

数学测试应包含至少一个独立计算的参考向量或等价的独立公式校验，不能只调用同一个生产函数比较自身。

## 14.3 WAV 与存储测试

至少覆盖：

1. WAV mono；
2. WAV sample rate 正确；
3. WAV float32；
4. WAV roundtrip 逐样本一致；
5. WAV sidecar 正确；
6. metadata sidecar 正确；
7. metadata canonical；
8. 相同输入产物字节确定；
9. 已存在 artifact ID 不得覆盖；
10. 路径穿越被拒绝；
11. 不安全 artifact ID 被拒绝；
12. 部分生成失败不发布最终目录；
13. sidecar 篡改被拒绝；
14. WAV 篡改被拒绝；
15. metadata 篡改被拒绝；
16. WAV 和 metadata 调换组合被拒绝；
17. 即使重新计算被修改文件的 sidecar，跨文件验证仍失败；
18. 元数据不含绝对路径、用户名或主机名。

## 14.4 CLI 安全测试

至少覆盖：

1. 生成 CLI 不调用生产 audio backend；
2. 验证 CLI 不调用生产 audio backend；
3. 运行时 monkeypatch `_audio_backend` 为立即失败，ESS 命令仍应成功；
4. 不导入或调用 sounddevice；
5. 不存在 play/rec/playrec/stream API；
6. 不发生真实设备枚举；
7. 不写 real 数据根；
8. 输出安全标记；
9. 对不完整正式配置明确失败；
10. development fixture 的临时目录工作流成功。

## 14.5 DEV-03.02 审计加固测试

覆盖第 13 节的所有正确和篡改情形。

## 14.6 回归测试

必须保持当前全部 192 项测试继续通过。

如果新增不少于 30 项测试，则完整测试数量应至少为：

`222 passed`

实际数量必须以 pytest 输出为准，并记录在报告中。

分别运行并记录：

- 原 43 项；
- 原 DEV-02.01 66 项；
- 原 DEV-02.02 23 项；
- 原 DEV-03.01 36 项；
- 原 DEV-03.02 24 项；
- DEV-03.03 新增测试；
- 完整测试。

---

# 15. 静态和禁止调用检查

必须运行：

- Ruff format check；
- Ruff lint；
- strict mypy；
- Schema consistency；
- `git diff --check`；
- skip/xfail/noqa/type-ignore 扫描；
- U+FFFD 扫描；
- 绝对路径和身份信息扫描；
- 禁止音频 API AST 扫描；
- 受保护文件 diff；
- 实施日志前缀检查。

禁止 API 至少包括：

- `play`
- `rec`
- `playrec`
- `wait`，当其用于音频流时
- `Stream`
- `RawStream`
- `InputStream`
- `OutputStream`
- `RawInputStream`
- `RawOutputStream`
- 任何等价的 sounddevice 播放或录音入口

允许读取和写入 WAV 文件，但不得打开音频设备。

不得因为 `soundfile` 名称中包含 sound 而误报；检查应针对实际设备/流调用。

---

# 16. 演示要求

使用系统临时目录或测试临时目录运行一次 development fixture 的完整离线工作流：

1. 加载 development 配置；
2. 生成 ESS；
3. 发布 artifact directory；
4. 运行离线验证；
5. 记录 artifact ID；
6. 记录 WAV SHA256；
7. 记录 metadata SHA256；
8. 记录 raw float32 sample-byte SHA256；
9. 记录样本数、shape、dtype 和实际时长；
10. 确认没有音频设备调用。

演示完成后：

- 不得将临时 WAV 提交到 Git；
- 不得删除用户已有目录；
- 只清理本次明确创建的临时目录；
- 如不能安全清理，保留并报告精确位置；
- 报告和日志中不得写入包含用户名的本机绝对路径，可使用 `<TEMP>/...` 的脱敏表示；
- 哈希、artifact ID 和参数必须保留。

另外运行一次当前正式配置的负向演示：

`config/audio/default_1x1_ess.yaml`

它必须因正式 ESS 时长、静音、fade 和 digital peak 仍为 null 而拒绝生成，并清楚列出缺失字段。

这属于预期 PASS，不得偷偷填入默认值使其生成。

---

# 17. 文档要求

## 17.1 架构文档

创建：

`docs/architecture/ess-excitation.md`

至少说明：

- ESS 公式；
- 瞬时频率；
- 离散采样边界；
- 秒到样本取整规则；
- fade 规则；
- peak dBFS 与硬件 gain 的区别；
- channel-first 内存布局；
- WAV 布局；
- 元数据；
- create-only artifact bundle；
- 验证流程；
- 为什么本步骤不授权播放；
- 为什么 development fixture 不是正式实验参数；
- 为什么本步骤不进行反卷积。

## 17.2 README

更新 README，说明项目当前完成到 DEV-03.03，但仍然：

- 没有连接实验硬件；
- 没有设备绑定；
- 没有播放；
- 没有录音；
- 没有流；
- 没有校准；
- 没有反卷积；
- 没有真实实验结果；
- 没有 geometry lock；
- 没有 experiment-ready。

提供：

- 离线 ESS development 演示命令；
- 离线验证命令；
- 当前正式配置拒绝生成的说明；
- 更新后的 `audio-context-validate` 命令。

不得给出任何会播放 WAV 的命令。

## 17.3 完成报告

创建：

`docs/reports/DEV-03.03.md`

必须包含：

- Outcome；
- 基线提交；
- 实际实现；
- ESS 数学契约；
- 配置未知量保持情况；
- development fixture 的明确边界；
- 生成产物和实际哈希；
- 审计闭环修正；
- 测试分组和实际数量；
- 静态检查；
- 初次失败和修正；
- 受保护哈希；
- 未执行事项；
- 已知限制；
- Git 提交前的真实状态。

报告冻结时不能编造尚未产生的最终提交 SHA。

可以说明最终提交和远端验证将在报告冻结后的 Git 门禁执行，实际结果以 Git 历史和最终回复为准。

---

# 18. 验收标准

只有同时满足以下条件，DEV-03.03 才能判定为 PASS：

1. 基线提交正确；
2. 工作区起始干净；
3. 受保护哈希全部正确；
4. 本提示词已归档；
5. 实施日志只追加；
6. 正式未知参数仍为 null；
7. development fixture 明确非正式、非实验结果；
8. ESS 公式正确；
9. channel-first `[1, n]`；
10. dtype 为 float32；
11. 样本数转换明确且正确；
12. silence 精确为零；
13. fade 边界正确；
14. 峰值正确；
15. 所有值 finite；
16. 相同输入逐样本确定；
17. WAV 可逐样本无损恢复；
18. metadata canonical 且可验证；
19. create-only 目录发布正确；
20. 路径穿越被拒绝；
21. 不覆盖已有 artifact；
22. 离线 validator 能重新生成并严格比较；
23. `audio-context-validate` 能识别有效 sidecar 下的语义错配；
24. DEV-03.02 原产物字节不变；
25. 没有真实硬件枚举；
26. 没有播放；
27. 没有录音；
28. 没有 Stream；
29. 没有设备绑定；
30. 所有 readiness/calibration 状态仍为 false；
31. 原 192 项测试全部通过；
32. DEV-03.03 新增不少于 30 项有效测试；
33. Ruff format 通过；
34. Ruff lint 通过；
35. strict mypy 通过；
36. Schema consistency 通过；
37. `git diff --check` 通过；
38. 没有 skip/xfail/noqa/type-ignore；
39. 工作区最终只包含本步骤预期修改；
40. 完成报告和日志与实际执行完全一致。

任一条件失败：

- 状态不得写成 PASSED；
- 不得提交成功标记；
- 不得推送；
- 必须报告失败证据。

---

# 19. 建议运行命令

根据实际 CLI 名称调整，但必须在报告中记录真实命令。

环境：

`uv --cache-dir .uv-cache sync --all-groups --frozen`

测试：

`uv --cache-dir .uv-cache run pytest -q tests/unit tests/integration`

`uv --cache-dir .uv-cache run pytest -q tests/dev02/test_config.py tests/dev02/test_domain_schema_cli.py tests/dev02/test_storage.py tests/dev02/test_synthetic.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev02/test_event_boundaries.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev03/test_inventory.py tests/dev03/test_preflight_persistence_cli.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev03/test_context_encoding.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev03/test_ess_offline.py`

`uv --cache-dir .uv-cache run pytest -q`

静态检查：

`uv --cache-dir .uv-cache run ruff format --check .`

`uv --cache-dir .uv-cache run ruff check .`

`uv --cache-dir .uv-cache run mypy`

`uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check`

`git diff --check`

开发夹具演示应使用系统临时 development root，不得写 real 数据根。

更新后的上下文验证命令必须读取：

- inventory；
- inventory sidecar；
- context；
- context sidecar；
- summary；
- summary sidecar；
- contextual preflight；
- contextual preflight sidecar；
- hardware setup；
- hardware setup reference。

---

# 20. Git 提交与推送门禁

只有在以下条件全部满足后才允许提交：

- 所有验收检查通过；
- 日志状态已真实更新为 PASSED；
- 报告已完成；
- 没有临时 WAV 或测试输出进入 Git；
- 没有本机绝对路径或身份信息；
- 受保护文件无变化；
- `git diff --check` 通过；
- 完整测试通过；
- 静态检查通过；
- 当前远端 `main` 仍为基线提交：

`1ca161c1da4fa02054c023a86941a72adb517e9c`

提交主题：

`DEV-03.03: add deterministic offline ESS generation`

提交前列出 staged 文件，确认没有：

- 临时文件；
- `.uv-cache`；
- `.venv`；
- 测试输出；
- 实际 WAV 演示产物；
- 用户数据；
- 本机路径；
- 密钥；
- token；
- 设备友好名之外的个人信息。

提交后：

1. 确认工作区干净；
2. 确认提交内容正确；
3. 再次运行必要的最终门禁；
4. 推送：

`git push origin main`

5. 使用远端引用确认 GitHub `main` 与本地 HEAD 完全一致；
6. 禁止 force push；
7. 禁止创建未经要求的额外分支；
8. 禁止自动创建 release 或 tag。

如果发生以下任一情况，不得推送：

- 测试失败；
- 静态检查失败；
- Schema 漂移；
- 受保护哈希变化；
- 远端在执行过程中前进；
- 工作区不干净；
- 无法确认提交范围；
- 依赖安装失败；
- 网络或认证失败；
- 任务被中断；
- 实现只完成一部分；
- 日志和实际不一致。

如果 push 失败：

- 不得 force push；
- 不得伪造成功；
- 保留本地提交；
- 报告实际错误；
- 最终状态不得声称远端已更新。

---

# 21. 最终回复格式

最终回复必须简洁但包含真实证据：

- `PASS — DEV-03.03 完成` 或真实失败状态；
- 提交 SHA；
- 本地 HEAD；
- `origin/main`；
- GitHub `main`；
- 工作区是否干净；
- 原测试数量；
- 新增测试数量；
- 完整测试数量；
- Ruff、mypy、Schema 状态；
- development fixture 的 WAV、metadata、raw sample hashes；
- 正式配置是否仍因 null 字段拒绝生成；
- `audio-context-validate` 篡改测试状态；
- ZIP、manifest、inventory、context、summary、contextual preflight 哈希；
- 是否发生设备枚举；
- 是否发生播放；
- 是否发生录音；
- 是否打开音频流；
- `hardware_ready`；
- 主要交付文件；
- 已知限制。

不得把 development fixture 描述成：

- 正式激励；
- 实验测量；
- 听力安全信号；
- 结构有效性证据；
- 校准结果。

不得宣布进入 DEV-03.04。

完成本步后停止，不要自行进入下一步。