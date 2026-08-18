# DEV-04.01：离线 ESS 反卷积、延迟估计与 IR/复传递函数内核

你现在负责实施 Acoustic Ladder 的：

`DEV-04.01`

本步骤必须以测试驱动方式完成。若环境提供 TDD skill，先完整读取并遵守；否则手工执行 RED → GREEN → REFACTOR，并记录真实过程。

完成本步骤后停止，不得自行进入 DEV-04.02、真实硬件接入、正式 QC、基线差分、特征提取或分类阶段。

---

# 1. 本步目标

在完全不连接、不枚举、不播放、不录音、不打开音频 Stream 的条件下，为已经通过验证的 DEV-03.04R synthetic virtual capture 建立可审计的离线信号处理链：

```text
已验证 synthetic capture
→ 来源和完整性复核
→ ESS 逆滤波
→ 完整线性反卷积
→ 波形独立延迟估计
→ 原始与对齐脉冲响应
→ 原始与对齐复传递函数
→ 幅值、相位、展相位
→ 500–8000 Hz 工作频带标记
→ 确定性持久化
→ 只读语义重算验证
```

本步骤必须证明软件能够从波形中恢复 DEV-03.04R nominal fixture 的：

- 输入相对输出延迟：`37 samples`；
- 主脉冲相对增益：约 `0.5`。

这两个值只能作为测试 oracle，不能作为处理算法的输入、默认值、场景提示或隐藏捷径。

本步骤输出仍然必须标记为：

```text
data_origin = synthetic
run_mode = development
formal_eligible = false
experimental_result = false
hardware_ready = false
```

不得把 synthetic 处理结果解释为真实声学有效性、实际装置传递函数、听力安全结论或论文实验结论。

---

# 2. Git 基线与停止条件

开始前必须核对：

```text
Repository: https://github.com/haocheng26710/fingers.git
Branch: main
Expected baseline:
42af61b89b1c8101004446e55fce9e2762da3b6c
```

必须实际执行并记录：

```text
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git remote -v
git log -1 --oneline
git ls-remote origin refs/heads/main
```

只有以下条件全部成立才能开始：

- 当前分支为 `main`；
- 本地 HEAD 为预期基线；
- `origin/main` 为预期基线；
- GitHub `refs/heads/main` 为预期基线；
- remote URL 正确；
- 工作区干净；
- 没有未提交或未跟踪的用户文件；
- 没有需要遵守但尚未读取的 `AGENTS.md`、`CLAUDE.md` 或等价项目指令。

如任一条件不成立：

- 立即停止；
- 不修改文件；
- 不 merge；
- 不 rebase；
- 不 reset；
- 不清理用户文件；
- 不 force push；
- 报告实际状态并说明未推送。

---

# 3. 提示词归档与实施日志

## 3.1 提示词归档

在生产代码实施前创建：

`docs/prompts/DEV-04.01.md`

要求：

- 保存本提示词完整内容；
- 若环境提供原始附件或 pasted-text 文件，必须按原始字节直接复制；
- 若只有聊天文本，则保存完整 Markdown，使用 UTF-8 和 LF，并明确记录“没有独立附件字节源”；
- 不得声称不存在的源文件或伪造“逐字节一致”；
- 计算并记录实际字节数及 SHA256；
- 在 `.gitattributes` 中保护该 prompt，避免 Git 自动改变换行；
- 不得修改任何旧 prompt。

## 3.2 实施日志

现有日志：

`docs/IMPLEMENTATION_LOG.md`

必须保持 append-only。

开始实施前，先在末尾新增：

```text
DEV-04.01：离线 ESS 反卷积、延迟估计与 IR/复传递函数内核
```

初始状态写为：

```text
IN_PROGRESS
```

之后每完成一个真实动作或确认一个结果，就同步更新同一 DEV-04.01 区块。至少记录：

- 序列号；
- 开始和结束时间；
- Git 基线；
- prompt 路径、字节数和 SHA256；
- 实际读取的文件；
- 采用的数学定义；
- RED 测试及真实失败；
- 每次修正；
- 实际执行命令；
- 实际测试数量和结果；
- 新生成 artifact 的真实哈希；
- 保护哈希；
- 静态检查结果；
- 未执行项及原因；
- 偏差和已知限制；
- Git 提交与推送门禁。

不得：

- 改写旧日志；
- 提前填写尚未发生的测试结果；
- 编造命令、时间、哈希或失败；
- 在提交前伪造最终 commit SHA；
- 把计划写成已完成事实。

---

# 4. 已冻结事实

## 4.1 模型与几何

当前模型为：

```text
Acoustic Ladder V1.3 校准后圆形主管版本
```

模型已实际打印并通过校准件确定以下值：

```text
MODULE_DRY_SEAL_DIAMETRAL_INTERFERENCE = 0.00 mm
JOINT_DRY_SEAL_DIAMETRAL_INTERFERENCE = -0.14 mm
END_DRY_SEAL_DIAMETRAL_INTERFERENCE = -0.08 mm
FDM_ACOUSTIC_HOLE_COMPENSATION = +0.15 mm
SUPPORT_GUIDE_CLEARANCE_PER_SIDE = 0.20 mm
正式楔块 = M
```

但当前状态仍为：

```text
provisional
geometry_locked = false
experiment_ready = false
```

不得在本步骤创建 lock manifest 或改变这些状态。

## 4.2 音频硬件

已知计划硬件：

```text
输出/扬声器：MOONDROP CHU II（水月雨竹 2）
输入/麦克风：Dayton Audio iMM-6C
麦克风接口：USB-C
功率放大器：无
麦克风校准文件：有，但尚未提供或验证
94 dB / 1 kHz 声学校准器：无
电气回环：不能进行
```

当前事实：

- iMM-6C 未连接；
- CHU II 未连接；
- 实验装置未连接；
- Host API 未确认；
- 输入设备索引未知；
- 输出设备索引未知；
- 通道号未知；
- shared clock 未验证；
- full duplex 未验证；
- calibration file 未验证；
- absolute SPL 未校准。

因此必须保持：

```text
hardware_ready = false
full_duplex_verified = false
shared_clock_verified = false
channel_mapping_verified = false
calibration_file_verified = false
calibration_applied = false
absolute_spl_calibrated = false
```

## 4.3 DEV-03.04R 已验证基线

DEV-03.04R 已完成虚拟采集来源和封装闭环。必须复用其公共接口，不得绕过。

稳定事实：

```text
Scenario raw:
74eefa7181d739272726fd59472ae0cd766ec7a8a9391b9a566f0031d6a81ab2

Scenario normalized:
cd5b82148d5fb88ea1fd86737510504030bca219ebe61de018b0f0b00bf90dbe

Output raw float32:
51531aedf7b6d253085315bf2ffd1efc7c760de363bc68565756ed5b2c2b3621

Input raw float32:
284c6bd0d320dfd0d1a97015d80e0bcc6aff3b49d9a2befbe68e55b5ef550b81

Output WAV:
1aea497f8868d1f2e187b2ed1f80efd7b05e4c0a6084f1901dcc425180bdb508

Input WAV:
51d68378a916f82e9080cba276c8c5dfb386ffd19f4fb3c0b3dd9e9d594222b1

Capture receipt:
343afe1bfdfb6df83cafb30096f3d2777c3d3273cdf8ddfdc389d91a84e1f448

Capture sample count: 13024
Block count: 51
Last block frame count: 224
```

`virtual_duplex_scheduler_exercised=true` 仍不等于 `full_duplex_verified=true`。

---

# 5. 开始前必须读取的文件

至少完整读取：

```text
pyproject.toml
uv.lock
.gitignore
.gitattributes
README.md
data/README.md
docs/IMPLEMENTATION_LOG.md

config/analysis/default.yaml
config/protocols/stage4_four_node_states.yaml
tests/fixtures/audio/ess_offline_development.yaml
tests/fixtures/audio/virtual_duplex_development.yaml

src/acoustic_ladder/audio/ess.py
src/acoustic_ladder/audio/excitation_models.py
src/acoustic_ladder/audio/excitation_persistence.py
src/acoustic_ladder/audio/virtual_capture.py
src/acoustic_ladder/audio/virtual_capture_models.py
src/acoustic_ladder/audio/virtual_capture_persistence.py
src/acoustic_ladder/config/bundle.py
src/acoustic_ladder/config/models.py
src/acoustic_ladder/config/schema.py
src/acoustic_ladder/domain/models.py
src/acoustic_ladder/storage/io.py
src/acoustic_ladder/storage/store.py
src/acoustic_ladder/synthetic/generator.py
src/acoustic_ladder/cli.py

tests/dev03/test_ess_offline.py
tests/dev03/test_virtual_capture.py

docs/architecture/ess-excitation.md
docs/architecture/virtual-capture.md
docs/architecture/storage-layout.md
docs/reports/DEV-03.03R.md
docs/reports/DEV-03.04.md
docs/reports/DEV-03.04R.md
```

读取后先说明：

- 哪些现有接口可以直接复用；
- 哪些接口需要最小扩展；
- 如何避免复制 deterministic NPZ、canonical JSON、sidecar 和路径约束代码；
- 如何保证 processing validator 不信任调用者提供的“已处理结果”。

不得从 ZIP 中导入或执行 Python，不得重建 CAD。

---

# 6. 范围与禁止范围

## 6.1 本步骤允许

- 纯离线 NumPy 数学；
- 处理经过验证的 synthetic virtual capture；
- ESS 逆滤波；
- 线性反卷积；
- 波形延迟估计；
- 原始和对齐 IR；
- 原始和对齐复传递函数；
- 幅值、相位和展相位；
- 分析频带 mask；
- 严格数据模型；
- deterministic NPZ；
- canonical JSON；
- SHA256 sidecar；
- synthetic `processed/` create-only 持久化；
- 只读语义重算 validator；
- synthetic-only CLI；
- 单元、集成、错误输入和确定性测试；
- 文档、日志和报告。

## 6.2 本步骤禁止

- 生产设备枚举；
- 运行 `audio-list` 或 `audio-inventory`；
- 选择设备、Host API 或通道；
- `sounddevice.play`；
- `sounddevice.rec`；
- `sounddevice.Stream`；
- 任何实际音频流；
- 播放或录音；
- 麦克风校准文件读取或应用；
- SPL 校准；
- 把 dBFS 解释为 dB SPL；
- 电气回环；
- 真实延迟或 shared-clock 测量；
- 修改正式 AudioConfig 中的未知值；
- 填写正式 QC、effect、drift 或 classification 阈值；
- 平滑；
- 基线差分；
- 特征提取；
- 分类；
- 协议矩阵生成或执行；
- Stage 1–4 正式实验；
- 修改 CAD、ZIP、manifest 几何或校准值；
- geometry lock；
- experiment-ready；
- DEV-03.05、DEV-04.02 或后续功能。

不得提交 WAV、NPY、NPZ、缓存、临时数据根、staging 或 lock 文件。

---

# 7. 输入信任边界

## 7.1 持久化入口不得接受任意数组作为事实

生产级 processing publisher 必须从以下身份输入重新定位并验证来源：

- `ImmutableSessionStore`；
- `LoadedBundle`；
- `LoadedVirtualCaptureScenario`；
- ESS artifact root；
- synthetic session ID；
- source run ID；
- processing ID；
- injected time provider。

publisher 必须在任何处理、staging 或写入发生前调用现有 DEV-03.04R 语义 validator。

不得让生产持久化入口直接接受：

- 任意 output WAV；
- 任意 input WAV；
- 任意 NumPy 数组；
- 预先计算的延迟；
- 预先计算的增益；
- 预先计算的 IR；
- 预先计算的传递函数；
- 调用者提供的哈希；
- 调用者提供的 processing receipt；
- 任意 real root；
- 设备或通道参数。

纯数学函数可以接受数组以支持单元测试，但不得把这些数组自动视为可发布事实。

## 7.2 处理前必须重新验证

至少验证：

- synthetic session 完整；
- source run 完整；
- capture exact file set；
- capture receipt；
- capture sidecars；
- synthetic metadata；
- run envelope；
- stored manifest 和 sidecar；
- config bundle；
- ESS artifact；
- scenario 当前来源；
- output/input WAV 的 canonical bytes；
- output/input 波形与 capture semantic replay 一致。

如果来源在加载后被修改、删除、移动或重新哈希，必须拒绝。

拒绝时：

- publication 前失败必须标记 `published=false`；
- 已存在 processed artifact 的只读验证失败必须标记 `published=true`；
- validator 不得修复、覆盖或删除篡改文件。

---

# 8. 数学契约

所有公式、索引方向、归一化和时间原点必须写入架构文档、模型字段和测试。

内部计算使用：

```text
float64
```

原始 float32 WAV 不得被覆盖。

## 8.1 ESS 有效段

从已验证的 ESS metadata 读取：

- sample rate；
- sweep sample count；
- pre-silence sample count；
- post-silence sample count；
- start frequency；
- end frequency；
- actual rounded duration。

不得重新猜测时间或使用未经验证的 YAML 数值。

必须验证 output reference：

- pre-silence 为精确零；
- active sweep 与已验证 ESS artifact 一致；
- sweep 后的声明区域和 capture tail 符合既有 capture contract；
- output 和 input sample rate 相同；
- output 和 input shape 符合当前 1+1 capture；
- 所有样本有限；
- output sweep 能量非零。

分析时从 output 和 input 同一 pre-silence 边界开始，删除共同的已知 pre-silence，但不得改变原始文件。

## 8.2 逆滤波器

令实际 active sweep 为：

```text
s[n], n = 0 ... N-1
```

令：

```text
R = ln(f_end / f_start)
```

主算法固定标识建议为：

```text
normalized_time_reversed_exponential_compensation
algorithm_version = 1.0.0
```

未归一化逆滤波器定义为：

```text
q0[n] = s[N-1-n] * exp(-R*n/N)
```

必须使用实际 `N` 和实际已持久化 sweep 样本。

不得：

- 根据目标延迟修改 inverse；
- 使用 scenario 的 gain；
- 使用 circular convolution；
- 静默截断卷积；
- 使用未记录的 window；
- 使用未记录的 smoothing。

## 8.3 完整线性卷积

实现确定性的 FFT linear convolution：

```text
linear_length = len(a) + len(b) - 1
fft_length = smallest power of two >= linear_length
```

计算后必须裁剪回精确 `linear_length`。

不得返回 circular convolution 的尾部回绕。

可以在生产代码使用 FFT；测试中必须用小规模独立直接时域卷积作为 oracle，不能用生产函数验证自身。

## 8.4 逆滤波器归一化

使用处理后的 output reference 与 `q0` 做完整线性卷积，得到 reference deconvolution。

找到唯一的最大绝对峰：

```text
reference_peak_index
```

如果出现非有限值、零峰或无法唯一决定的并列峰，必须拒绝。

用该峰对 inverse 进行归一化，使重新计算的 reference peak 为 `+1`。必须保存：

- 归一化前峰值；
- 归一化因子；
- 归一化后峰值；
- reference peak index；
- inverse 长度；
- convolution FFT length。

不得通过 nominal `0.5` gain 进行归一化。

## 8.5 波形独立延迟估计

延迟必须由实际波形估计。

使用 active sweep `s` 在 input 的可完整容纳区间进行归一化 matched correlation：

```text
candidate lag = 0 ... len(input_after_pre) - N
```

每个候选 lag 使用完整 N 个 sweep 样本。

相关系数：

```text
corr[k] =
dot(s, input[k:k+N])
/
(norm(s) * norm(input[k:k+N]))
```

要求：

- 分母有限且非零；
- 使用 `abs(corr)` 选择峰，以允许未来极性反转；
- 保存带符号峰值；
- 不允许只比较部分 sweep；
- 不允许使用只有少量重叠样本的虚假高相关；
- 若最大绝对值并列而无法唯一决定，必须拒绝；
- lag 约定必须明确：正值表示 input 落后 output。

输出至少包含：

```text
estimated_latency_samples
estimated_latency_seconds
matched_correlation_signed
matched_correlation_absolute
candidate_lag_min
candidate_lag_max
```

不得从 scenario、receipt 或测试期望值读取延迟。

## 8.6 反卷积与 IR

使用已归一化 inverse 分别计算：

```text
reference_deconvolution
input_deconvolution
```

以 `reference_peak_index` 作为零时刻。

必须保存完整未裁剪的：

- reference deconvolution；
- input deconvolution；
- 相对 sample/time axis。

定义 causal raw IR：

```text
ir_raw = input_deconvolution[reference_peak_index:]
```

这一步只建立相对于 reference peak 的因果时间原点。完整负时间及前峰信息仍必须存在于完整 deconvolution arrays 中，不能无声丢弃。

找到 raw IR 的主峰并保存：

```text
ir_dominant_peak_index
ir_dominant_peak_value
```

nominal fixture 中：

```text
ir_dominant_peak_index = 37
ir_dominant_peak_value ≈ 0.5
```

延迟对齐必须使用 zero-fill shift：

```text
ir_aligned[0 : len(ir_raw)-lag] = ir_raw[lag:]
ir_aligned[len(ir_raw)-lag :] = 0
```

不得使用：

- `np.roll`；
- circular shift；
- 将尾部绕回开头；
- 覆盖 `ir_raw`。

必须同时保存 `ir_raw` 和 `ir_aligned`。

## 8.7 复传递函数

从完整 causal IR 计算：

```text
transfer_raw = rfft(ir_raw, n_fft)
transfer_aligned = rfft(ir_aligned, n_fft)
```

其中：

```text
n_fft = smallest power of two >= len(ir_raw)
```

必须保存原始复数信息，不能只保存 dB：

- real；
- imaginary；
- magnitude linear；
- magnitude dB；
- phase radians；
- unwrapped phase radians；
- frequency Hz。

NPZ 中不得使用 object dtype 或 pickle。复数可以保存为独立 real/imag float64 arrays。

dB 转换必须有明确有限值策略。建议：

```text
db_floor_linear = np.finfo(np.float64).tiny
20 * log10(max(magnitude, db_floor_linear))
```

如果采用该策略，必须在 receipt 和文档中记录。不得把这个数值描述为物理噪声阈值或 QC 阈值。

## 8.8 工作频带

工作频带必须来自当前已加载的：

`config/analysis/default.yaml`

预期为：

```text
500–8000 Hz
```

必须生成并保存：

```text
analysis_band_mask
```

要求：

- lower 和 upper 均来自 AnalysisConfig；
- lower < upper；
- upper 小于 Nyquist；
- 当前 smoothing 必须为 disabled；
- 本步骤不执行 smoothing；
- 不修改 `baseline_selection_rule`、`features`、`normalization`、`cross_validation_strategy` 或 decision gate null 值。

不得把 500–8000 Hz 再写成算法内部无来源常量。

---

# 9. 数组 shape、dtype 与命名

当前公开持久化路径只允许已验证的 1+1 synthetic capture。

建议至少保存以下 arrays：

```text
inverse_filter
reference_deconvolution
input_deconvolution
deconvolution_relative_samples
deconvolution_relative_seconds
ir_raw
ir_aligned
frequency_hz
transfer_raw_real
transfer_raw_imag
transfer_aligned_real
transfer_aligned_imag
magnitude_raw_linear
magnitude_raw_db
phase_raw_rad
phase_raw_unwrapped_rad
magnitude_aligned_linear
magnitude_aligned_db
phase_aligned_rad
phase_aligned_unwrapped_rad
analysis_band_mask
```

要求：

- 波形、IR、传递函数和频谱值使用 float64；
- relative sample axis 使用明确的整数 dtype；
- band mask 使用 bool；
- IR 与 transfer 保持 channel-first；
- 当前 1+1 建议为：

```text
ir: [1, 1, n_ir]
transfer: [1, 1, n_frequency]
```

- frequency 和 mask 为 `[n_frequency]`；
- 所有数值数组必须 C-contiguous；
- 除 mask 外的数值数组必须 finite；
- 禁止 object arrays；
- 禁止 pickle；
- 元数据必须明确记录每个 array 的 shape 和 dtype。

如采用不同但等价的数组名称或维度，必须先说明理由，并保持所有接口、Schema、测试和文档一致。

---

# 10. 数据模型

建议新增：

```text
src/acoustic_ladder/audio/ess_processing_models.py
```

至少定义严格模型：

```text
EssProcessingReceipt
ProcessingArrayDescriptor
PublishedEssProcessing
```

可根据架构增加必要的内部 dataclass，但不得创建重复事实源。

模型必须：

- `extra="forbid"`；
- strict validation；
- 禁止 NaN/Infinity；
- SHA256 使用 64 位小写十六进制约束；
- ID 使用安全标识符约束；
- 路径必须为 project/session relative；
- 明确 algorithm ID/version；
- 明确 source capture identity；
- 明确 processing identity；
- 明确 synthetic/development 状态；
- 明确无硬件 I/O；
- 明确非正式、非实验结果。

`EssProcessingReceipt` 至少包含：

- schema version；
- processing ID；
- source session ID；
- source run ID；
- source capture receipt SHA256；
- source output WAV SHA256；
- source input WAV SHA256；
- source output/input raw SHA256；
- source ESS metadata/WAV/raw SHA256；
- bundle content SHA256；
- device manifest SHA256；
- config snapshot hashes；
- scenario raw/normalized SHA256；
- analysis config reference/hash；
- algorithm ID/version；
- inverse formula ID；
- sample rate；
- sweep timing；
- FFT/linear convolution长度；
- reference peak；
- inverse normalization；
- matched-correlation latency；
- IR dominant peak；
- IR/transfer shapes；
- analysis band；
- smoothing disabled；
- dB floor策略；
- deterministic NPZ SHA256；
- 每个 array 的名称、shape、dtype、byte count 或 hash；
- create-only/immutable；
- synthetic/development flags；
- 所有 hardware/calibration/formal/experimental flags；
- safety marker。

建议 safety marker：

```text
SYNTHETIC_OFFLINE_ESS_PROCESSING_NOT_AN_EXPERIMENTAL_RESULT
```

生成对应 Schema，例如：

`schemas/ess_processing_receipt.schema.json`

Schema 必须由模型导出，不得手写漂移版本。

当前生成型 Schema 数为 17；若只增加一个新生成型 Schema，完成后应为 18。目录还存在手工 `device_manifest.schema.json`，不得把目录总文件数与生成型数量混淆。

---

# 11. 纯数学模块

建议新增：

```text
src/acoustic_ladder/audio/ess_processing.py
```

至少提供：

- 输入数组与 timing 校验；
- inverse filter 构造；
- FFT linear convolution；
- matched-correlation latency estimation；
- deconvolution；
- raw/aligned IR；
- transfer arrays；
- band mask；
- deterministic result object。

纯数学模块：

- 不得导入 sounddevice；
- 不得访问文件系统；
- 不得访问 scenario；
- 不得接收 expected latency/gain；
- 不得读环境变量；
- 不得生成时间、UUID 或随机数；
- 相同输入必须逐字节产生相同数组。

---

# 12. Deterministic NPZ

现有项目已经有固定 ZIP metadata、排序 array name 的 deterministic NPZ 实现。

必须：

- 优先把既有实现安全提取为可复用公共 utility；
- 不复制两套稍有不同的 NPZ writer；
- 保持 DEV-02 synthetic NPZ 原哈希不变；
- array 名按稳定顺序写入；
- ZIP timestamp 固定；
- 禁止 pickle；
- 解码 validator 必须检查 array 名、shape、dtype、finite 和 metadata 一致性。

既有 synthetic 示例保护哈希：

```text
908a2c01ca652390cd7ddcf055c608b3339dedfbcbcc1724dc4e06010bef333a
```

如果当前测试夹具能复现该示例，必须加入回归；如其完整身份参数不足以从仓库独立复现，不得编造复现结果，只需证明相关既有测试和 golden 未变化。

---

# 13. 持久化契约

建议新增：

```text
src/acoustic_ladder/audio/ess_processing_persistence.py
```

processed artifact 必须写入 synthetic session 的：

```text
processed/
```

建议路径：

```text
session_<session_id>/
  processed/
    run_<source_run_id>/
      processing_<processing_id>/
```

必须验证每个 path component。

不得：

- 写入 raw run；
- 修改 `run_record.json`；
- 修改 capture receipt；
- 写入 real root；
- 覆盖已有 processing；
- 通过绝对路径或 `..` 逃逸。

建议 exact file set：

```text
processing_arrays.npz
processing_arrays.npz.sha256
processing_receipt.json
processing_receipt.sha256
processing_metadata.json
processing_record.json
PROCESSING_COMPLETE
```

要求：

- staging 必须位于同一 synthetic session/filesystem；
- 所有 payload 完成并验证后才 rename；
- create-only；
- 已存在目标必须拒绝；
- 失败时清理精确 staging；
- 不删除既有完成结果；
- 若 rename 后外层事件或记录追加失败，必须报告 `published=true`，不得假装未发布；
- Windows 不得用会覆盖目标的 rename；
- 并发同 ID 最多一个成功；
- 不声称绝对多文件事务或抵御恶意 TOCTOU actor。

`processing_metadata.json` 必须为 canonical fixed envelope，至少包括：

```text
processing_receipt_sha256
data_origin = synthetic
hardware_io_performed = false
safety_marker
```

validator 必须精确比较 canonical bytes，拒绝：

- 缺字段；
- 多字段；
- 改值；
- 非 canonical 序列化；
- `data_origin=real`；
- `hardware_io_performed=true`；
- 假 safety marker。

---

# 14. 只读 processing validator

必须提供只读 validator。

validator 不得只验证 sidecar；必须：

1. 重新验证 source capture；
2. 重新读取 exact output/input WAV；
3. 重新读取 ESS metadata 和 excitation；
4. 重新执行整个处理算法；
5. 重建所有 arrays；
6. 重建 deterministic NPZ；
7. 重建 receipt；
8. 核对 exact file set；
9. 核对所有 sidecars；
10. 核对 canonical JSON；
11. 核对 processing metadata；
12. 核对 processing record；
13. 核对 source/bundle/config/scenario hash chain；
14. 精确比较重算结果和已保存结果。

validator 必须只读。篡改测试要确认验证失败前后的目标文件字节完全一致。

不得接受“攻击者同时修改 payload 和 sidecar”作为有效处理结果。

---

# 15. CLI

扩展现有 CLI，建议命令：

```text
process-simulated-capture
validate-simulated-processing
```

`process-simulated-capture` 至少要求：

- project root；
- manifest 和 sidecar；
- audio/protocol/analysis/synthetic 配置；
- synthetic root；
- session ID；
- source run ID；
- processing ID；
- scenario；
- ESS artifact root。

不得提供：

- `--real-root`；
- `--expected-latency`；
- `--linear-gain`；
- `--ir`；
- `--transfer-function`；
- 设备索引；
- Host API；
- 通道；
- playback/record/stream 参数。

命令成功输出必须明确包含：

```text
SYNTHETIC_ONLY
OFFLINE_PROCESSING_ONLY
NO_HARDWARE_AUDIO_IO_PERFORMED
NOT_AN_EXPERIMENTAL_RESULT
```

并报告实际：

- processing ID；
- source run ID；
- estimated latency；
- matched correlation；
- IR dominant peak；
- NPZ SHA256；
- receipt SHA256；
- sample rate；
- FFT length；
- frequency-bin count。

正式或 real 输入在本步骤必须被拒绝。

---

# 16. 预期文件

可以根据现有架构微调，但预计包括：

```text
src/acoustic_ladder/audio/ess_processing.py
src/acoustic_ladder/audio/ess_processing_models.py
src/acoustic_ladder/audio/ess_processing_persistence.py
tests/dev04/__init__.py
tests/dev04/test_ess_processing.py
schemas/ess_processing_receipt.schema.json
docs/architecture/ess-processing.md
docs/prompts/DEV-04.01.md
docs/reports/DEV-04.01.md
```

并可能最小修改：

```text
.gitattributes
README.md
data/README.md
docs/IMPLEMENTATION_LOG.md
src/acoustic_ladder/cli.py
src/acoustic_ladder/config/schema.py
src/acoustic_ladder/storage/store.py
src/acoustic_ladder/synthetic/generator.py
相关既有测试
```

不得借机大规模重构无关模块。

---

# 17. TDD 与测试要求

先写失败测试，确认 RED 原因正确，再实现。

不得：

- 先写完整实现后补测试；
- 删除旧测试；
- 降低旧断言；
- 使用 skip/xfail；
- 使用 `noqa` 或 `type: ignore` 隐藏问题；
- 只验证“没有抛异常”；
- 用生产函数生成自身 expected result。

建议新增不少于 45 个有意义测试，但验收以覆盖契约和攻击面为准，不得通过无意义参数化凑数量。

## 17.1 数学单元测试

至少包括：

1. FFT linear convolution 与独立小数组 `np.convolve` oracle 一致；
2. 无 circular wrap；
3. identity system：
   - lag 0；
   - dominant gain 1；
4. nominal gain+delay：
   - lag 37；
   - dominant gain 0.5；
5. 多抽头 FIR：
   - 已知 tap 位置；
   - 已知 tap 符号；
   - 已知 dominant delay；
6. 极性反转；
7. zero input 拒绝；
8. zero output energy 拒绝；
9. NaN 拒绝；
10. Infinity 拒绝；
11. 空数组拒绝；
12. shape mismatch 拒绝；
13. sample-rate mismatch 拒绝；
14. capture 不足以容纳完整 sweep 时拒绝；
15. 分析上限超过 Nyquist 时拒绝；
16. 非唯一 correlation peak 时拒绝；
17. 非唯一 reference deconvolution peak 时拒绝；
18. zero-fill alignment 不回绕；
19. raw IR 不被 alignment 修改；
20. transfer real/imag 可重建 complex；
21. magnitude 与 complex 绝对值一致；
22. phase 与 complex angle 一致；
23. unwrapped phase 连续规则正确；
24. frequency vector 正确；
25. band mask 来自 AnalysisConfig；
26. smoothing enabled 时明确拒绝或按本步骤契约拒绝；
27. 所有输出 shape/dtype/finite 正确；
28. 相同输入 arrays 逐字节一致。

## 17.2 防止 truth leakage

必须有测试证明：

- 纯数学入口没有 scenario 参数；
- 没有 expected latency 参数；
- 没有 expected gain 参数；
- 生产代码不读取 `integer_latency_samples` 作为估计结果；
- 生产代码不读取 `linear_gain` 作为恢复结果；
- 改变测试 oracle 而不改变波形不会改变算法输出；
- nominal `37/0.5` 只出现在 fixture、测试断言或报告，不作为算法常量。

可使用 signature/AST 检查，但不能只依赖字符串搜索。

## 17.3 持久化与来源测试

至少包括：

- 未验证 capture 不能处理；
- capture source 修改后拒绝；
- scenario source 修改后拒绝；
- ESS source 修改后拒绝；
- output WAV 修改并重算 sidecar仍拒绝；
- input WAV 修改并重算 sidecar仍拒绝；
- capture receipt 修改并重建外层引用仍拒绝；
- analysis config 修改后拒绝旧 processing；
- processing ID 路径逃逸拒绝；
- create-only；
- 同 ID 二次写入拒绝；
- 并发同 ID 最多一个成功；
- staging 失败无残留；
- NPZ 篡改拒绝；
- NPZ 篡改并重算 sidecar仍拒绝；
- receipt 篡改并重算 sidecar仍拒绝；
- metadata `real/true/fake marker` 篡改拒绝；
- processing record 篡改拒绝；
- extra file 拒绝；
- missing file 拒绝；
- validator 完全只读；
- synthetic 不能写入 real root；
- formal/experimental/hardware flags 永远 false。

## 17.4 集成测试

用 DEV-03.04R nominal capture 完成：

```text
ESS generate/validate
→ synthetic session
→ virtual capture
→ capture validate
→ processing publish
→ processing validate
→ session/run validate
```

必须确认：

```text
estimated_latency_samples = 37
ir_dominant_peak_index = 37
abs(ir_dominant_peak_value - 0.5) <= 1e-6
```

`1e-6` 是 development 数值回归容差，不是物理、QC 或实验阈值。若实现无法满足，不得静默放宽；应停下、分析归一化或索引定义。

## 17.5 双根确定性

在两个分别确认不存在的临时目录中，以完全相同身份运行完整 CLI 流程。

固定建议身份：

```text
ESS artifact ID: source_ess
session ID: dev0401
reassembly ID: assembly001
capture run ID: capture001
processing ID: processing001
measurement order: 0
```

必须确认 deterministic processing payload 逐字节一致，至少包括：

- processing arrays NPZ；
- NPZ sidecar；
- processing receipt；
- receipt sidecar；
- canonical processing metadata。

如果 outer processing record 包含真实运行时间，应明确将其排除在跨运行字节确定性声明之外；不得谎称时间戳文件确定。

记录所有实际新哈希，结束后精确清理两个临时根并确认不存在。

---

# 18. 回归和保护哈希

必须复算并保持：

```text
V1.3 ZIP:
1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b

Provisional manifest:
bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0

DEV-03.01 inventory:
8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2

DEV-03.02 context:
10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c

DEV-03.02 summary:
84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159

Contextual preflight:
e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15

Hardware setup:
013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1
```

ESS smoke golden：

```text
WAV:
608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0

Metadata:
e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a

Raw float32:
eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca
```

还必须保护：

- nominal scenario 文件字节；
- DEV-03.04R output/input golden；
- capture receipt golden；
- 正式 AudioConfig；
- development ESS fixture 参数；
- 所有旧 prompt；
- 所有旧 report；
- `docs/IMPLEMENTATION_LOG.md` 的完整旧前缀。

允许在日志末尾追加，不允许修改前缀。

---

# 19. 静态检查与全套门禁

至少执行：

```text
uv --cache-dir .uv-cache sync --all-groups --frozen
uv --cache-dir .uv-cache run pytest -q
uv --cache-dir .uv-cache run pytest tests/dev04/test_ess_processing.py -q
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
git diff --check
```

必须确认：

- 原有 `369` 项测试全部保留；
- 新增测试全部通过；
- 完整测试通过；
- 无 skip/xfail；
- Ruff format 通过；
- Ruff lint 通过；
- strict mypy 通过；
- Schema consistency 通过；
- `git diff --check` 通过；
- 没有 U+FFFD；
- 没有本机绝对路径、用户名或私人身份写入产物；
- 没有新增真实音频 API 调用；
- 没有 direct sounddevice import；
- 没有 `play/rec/Stream`；
- 没有 tracked WAV/FLAC/MP3/NPY/NPZ；
- 没有 tracked cache/staging/lock/temp；
- 工作区只包含 DEV-04.01 预期修改。

不能把 prompt 中作为审计文本出现的禁止词误报成生产 API；扫描必须区分 prompt、测试字符串和生产代码。

---

# 20. 文档

新增：

`docs/architecture/ess-processing.md`

至少说明：

- source-of-truth 链；
- 为什么 processing 前必须重新验证 capture；
- inverse filter 精确公式；
- sample index 和时间约定；
- FFT linear convolution；
- reference peak 归一化；
- matched-correlation 延迟估计；
- raw/aligned IR 的区别；
- zero-fill shift；
- raw/aligned complex transfer；
- frequency、magnitude、phase、unwrapped phase；
- analysis band 来源；
- deterministic NPZ；
- processed storage layout；
- create-only 和 validator；
- synthetic/real 隔离；
- 为什么 37/0.5 不是算法输入；
- 当前数值容差不是实验 QC；
- 当前结果不能证明真实声学有效性。

更新 README 和 data README，加入实际可复制的 synthetic processing 和 validation 命令，并突出：

```text
NO HARDWARE I/O
NOT AN EXPERIMENTAL RESULT
```

新增：

`docs/reports/DEV-04.01.md`

报告必须基于真实执行结果，至少包括：

- outcome；
- baseline；
- prompt archive；
- 读取文件；
- 数学定义；
- source validation；
- 模型和 Schema；
- persistence layout；
- RED/GREEN 过程；
- nominal 37/0.5 结果；
- identity 和 multi-tap oracle；
- 双根哈希；
- 测试数量；
- 静态检查；
- 保护哈希；
- 无硬件调用证据；
- 已知限制；
- 未实现内容；
- 下一步接口；
- Git 尚未提交时不能自引用最终 SHA。

---

# 21. 明确不属于本步的结论

最终文档和回复必须明确：

- recovered gain 是数字线性比值，不是 SPL；
- latency 是 synthetic waveform 的样本延迟，不是真实装置传播延迟；
- IR 是 development synthetic processing 结果；
- transfer function 不是实际 Acoustic Ladder 测量结果；
- analysis band mask 不等于正式带宽有效性证明；
- 未验证 microphone calibration；
- 未验证 transducer response；
- 未验证 leakage、roughness、reflections 或 nonlinearities；
- 未完成正式 QC；
- 未完成 baseline comparison；
- 未完成任何分类；
- 未完成真实 full duplex。

---

# 22. Git 提交与推送

只有全部门禁 PASS 才允许提交和推送。

提交前：

1. 检查完整 diff；
2. 检查无秘密；
3. 检查无大型或临时数据；
4. 检查日志真实；
5. 检查报告真实；
6. 检查所有保护哈希；
7. 检查工作区只包含 DEV-04.01；
8. 再次执行：

```text
git ls-remote origin refs/heads/main
```

此时远端 `main` 必须仍为：

```text
42af61b89b1c8101004446e55fce9e2762da3b6c
```

如果远端变化：

- 停止；
- 不提交未经重新审查的组合；
- 不 merge；
- 不 rebase；
- 不 force push；
- 报告实际远端 SHA；
- 明确说明未推送。

建议提交主题：

```text
DEV-04.01: add deterministic offline ESS processing
```

提交后：

- 确认工作区干净；
- 正常执行 `git push origin main`；
- 禁止 force push；
- 再次读取 GitHub `refs/heads/main`；
- 确认 local HEAD、origin/main、GitHub main 完全一致。

如果任一步失败或中断：

- 不得推送；
- 不得声称完成；
- 报告是否已经产生本地 commit；
- 报告远端是否改变；
- 不得自行修历史或强推。

---

# 23. 最终回复格式

成功时报告：

```text
PASS — DEV-04.01 完成
```

并列出：

- commit SHA；
- remote；
- branch；
- local/origin/GitHub 是否一致；
- 工作区是否干净；
- 原有测试数量；
- 新增测试数量；
- 完整测试数量；
- Ruff/mypy/Schema/diff 结果；
- 生成型 Schema 数量；
- estimated latency；
- matched correlation；
- IR dominant peak index/value；
- processing arrays SHA256；
- processing receipt SHA256；
- 双根是否逐字节一致；
- 七个保护哈希；
- 三个 ESS golden；
- DEV-03.04R capture golden；
- 硬件枚举：否；
- 播放：否；
- 录音：否；
- Stream：否；
- calibration：否；
- `hardware_ready=false`；
- 主要文件；
- 已知限制。

必须明确写出：

```text
本步骤只完成 synthetic 离线 ESS 处理内核。
37 samples 和 0.5 是从波形恢复的 development fixture 结果，不是算法输入。
没有连接、枚举、播放、录制或验证任何真实音频硬件。
本步骤没有产生正式实验或真实声学结论。
```

失败时使用：

```text
FAILED
BLOCKED
或
INTERRUPTED
```

并报告：

- 失败门禁；
- 实际错误；
- 已修改文件；
- 是否产生本地 commit；
- 明确说明未推送。

完成 DEV-04.01 后停止，不要自行进入下一步。