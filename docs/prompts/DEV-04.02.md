# DEV-04.02：离线处理质量证据与 provisional QC 状态框架

你负责实现 Acoustic Ladder 的下一步：

`DEV-04.02`

目标是在已经通过验证的 synthetic capture 与 DEV-04.01R2 processing 产物上，计算、保存和重放验证确定性的离线质量证据。

本步骤只建立质量指标和审计框架。由于正式实验设备尚未连接、真实数据尚不存在、`analysis.decision_gates.qc_threshold` 仍为 `null`，不得制定正式阈值，不得产生正式 QC PASS/FAIL，也不得进入 baseline 差分、特征提取、分类或 DEV-04.03。

## 一、Git 基线

开始前必须只读核验：

- 仓库：`https://github.com/haocheng26710/fingers.git`
- 分支：`main`
- 预期基线提交：
  `cb2798f8b2d1544271b45c41741b3c6ee6cab6a7`
- 提交主题：
  `DEV-04.01R2: fix processing identity and version provenance`
- 本地 `HEAD`、`origin/main`、GitHub `refs/heads/main` 必须一致
- 工作区必须干净

若基线不一致、远端已前进或存在无法归属的修改，立即停止，不修改、不提交、不推送，并如实报告。

## 二、基线验收数据

当前基线：

- DEV-04.01：`61 passed`
- DEV-04.01R：`30 passed`
- DEV-04.01R2：`13 passed`
- DEV-04 合计：`104 passed`
- 完整套件：`473 passed`
- Ruff、strict mypy、18 个生成 Schema、`git diff --check` 均通过

当前 processing 版本：

- receipt schema version：`1.1.0`
- processing algorithm version：`1.1.0`

受保护 processing hashes：

- arrays：`e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89`
- arrays sidecar：`f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902`
- receipt：`25616c6e2d42413243eb8e14cd099d01e69e736c29ffcce5cdd413e97841ad5f`
- receipt sidecar：`38ef680d07fbc88ca7f2d59bba10866439fe2db80b95b34bcea7eec202830e63`
- metadata：`daa1c08780c9381604f08be14a268bcb7a539844622096de588c5c020c2a04cb`

上述 processing hashes 必须保持不变。

## 三、V1.3 与历史保护哈希

必须保持：

- ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`
- ESS WAV：`608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- ESS metadata：`e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- ESS raw float32：`eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

## 四、日志与提示词归档

### DEV-04.02-00：初始化

在修改生产代码前：

1. 阅读全部适用的仓库指令、配置、存储架构、capture、processing、CLI、测试、历史提示词和报告。
2. 如环境提供 TDD skill，先完整读取并按 RED→GREEN→REFACTOR 执行。
3. 将本提示词正文原样归档为：
   `docs/prompts/DEV-04.02.md`
4. 按仓库惯例在 `.gitattributes` 中将提示词归档标记为 binary。
5. 记录提示词实际字节数、换行形式和 SHA256，不得编造源格式。
6. 测量 `docs/IMPLEMENTATION_LOG.md` 的初始字节数和 SHA256。
7. 在日志末尾追加：
   `## DEV-04.02：离线处理质量证据与 provisional QC 状态框架`
8. 初始状态写为 `IN_PROGRESS`，记录真实开始时间、Git 基线、问题范围、计划和禁止范围。
9. 每完成一个序列步骤，就追加真实命令、输出、失败、修正、测试计数、哈希和清理结果。
10. 日志原有内容必须保持完整字节前缀，只能追加。
11. 不得修改任何历史 prompt 或 report。

## 五、核心状态语义

### DEV-04.02-01：只保存指标，不作正式判决

本步骤必须严格区分：

- 软件计算是否成功；
- 质量证据是否完整；
- 是否应用了正式 QC 阈值；
- 是否形成正式实验判决。

固定状态：

- `metric_computation_status = "complete"`
- `evaluation_status = "provisional_metrics_only"`
- `qc_decision = "not_evaluated"`
- `thresholds_applied = false`
- `qc_threshold = null`
- `threshold_source = null`
- `formal_eligible = false`
- `experimental_result = false`
- `hardware_io_performed = false`
- `hardware_ready = false`

不得使用以下说法描述 QC 产物：

- QC PASS
- QC FAIL
- experiment ready
- hardware verified
- calibration verified
- acoustic validity established
- sufficient SNR
- acceptable drift
- formal measurement quality

软件测试通过只能描述为“QC 指标软件实现通过”，不能描述为“实验质量通过”。

如果当前 `AnalysisConfig.decision_gates.qc_threshold` 不为 `null`，DEV-04.02 publisher 必须拒绝执行，并明确说明本版本不支持应用正式阈值；不得静默忽略或擅自解释该值。

## 六、确定性 QC 指标内核

### DEV-04.02-02：纯指标计算

实现一个无文件系统副作用的 float64 指标内核。它可以接受已经解码并经过调用边界验证的数据，但 QC publisher 不得接受外部预计算指标。

所有数组必须：

- mono `1 × N`
- 非空
- float64 计算
- 不含 NaN/Inf
- C contiguous 输出或规范标量
- 不读取 scenario truth
- 不接受 expected latency、expected gain 或正式阈值

至少计算以下指标。

### A. 波形完整性与幅度指标

分别对 output reference 与 captured input 保存：

- `full_sample_count`
- `peak_abs`
- `rms`
- `active_sweep_rms`
- `pre_silence_rms`
- `clipped_sample_count`
- `clipped_sample_fraction`

固定定义：

- `peak_abs = max(abs(x))`
- `rms = sqrt(mean(x²))`
- active sweep 区间：
  `[pre_silence_sample_count : pre_silence_sample_count + sweep_sample_count]`
- pre-silence 区间：
  `[0 : pre_silence_sample_count]`
- clipping representational boundary：
  `abs(sample) >= 1.0`
- `clipped_sample_fraction = clipped_sample_count / full_sample_count`

`1.0` 是归一化 float WAV 的数字表示边界，不是扬声器安全阈值、SPL 阈值或实验 QC 阈值。

若 `pre_silence_sample_count == 0`，pre-silence RMS 必须为 `null`，并记录明确 reason；不得对空数组求均值。

### B. Pre-silence SNR proxy

保存：

- `input_pre_silence_snr_proxy_db`
- `input_pre_silence_snr_proxy_status`

定义：

`20 * log10(input_active_sweep_rms / input_pre_silence_rms)`

只在两个 RMS 均严格大于零时计算。

状态必须是固定枚举之一：

- `computed`
- `pre_silence_absent`
- `zero_pre_silence_rms`
- `zero_active_sweep_rms`

无法计算时数值必须为 `null`。不得使用 epsilon 伪造有限 SNR，不得把该 proxy 称为正式声学 SNR。

### C. 延迟与相关证据

保存来自已验证 processing receipt 的：

- `estimated_latency_samples`
- `estimated_latency_seconds`
- `matched_correlation_signed`
- `matched_correlation_absolute`

QC publisher 必须将这些值与 processing replay 结果交叉核对，不得从 scenario 的 declared delay/gain 获取。

### D. IR 主峰集中度

从 `ir_raw[0,0,:]` 计算：

- `ir_dominant_peak_index`
- `ir_dominant_peak_value`
- `ir_dominant_peak_abs`
- `ir_second_largest_abs`
- `ir_peak_to_second_peak_ratio`

定义：

1. dominant index/value 必须与 processing receipt 一致。
2. second largest 是排除 dominant index 后的最大绝对值。
3. 若不存在第二个样本或 second largest 为零，ratio 为 `null`，并记录固定 reason。
4. 否则：
   `dominant_peak_abs / second_largest_abs`

该比值只是 development concentration metric，不是正式 peak-quality 阈值。

### E. Reference deconvolution off-peak residual

从 `reference_deconvolution` 及 `reference_peak_index` 计算：

- `reference_deconvolution_peak_abs`
- `reference_deconvolution_off_peak_rms`
- `reference_peak_to_off_peak_rms_ratio`
- 对应 ratio status

定义：

1. 复制 reference deconvolution。
2. 排除唯一 reference peak 样本。
3. 对剩余样本计算 float64 RMS。
4. off-peak RMS 为零或没有剩余样本时，ratio 为 `null` 并记录原因。
5. 不得把它称为真实装置的模型残差或正式反卷积 QC。

### F. 分析频带与谱除法覆盖

使用已验证 output reference、processing receipt 的 `transfer_fft_length` 和现有 processing `analysis_band_mask`，重新计算：

- `analysis_band_bin_count`
- `spectral_division_valid_bin_count_in_band`
- `spectral_division_zeroed_bin_count_in_band`
- `spectral_division_valid_fraction_in_band`
- `transfer_raw_finite_bin_count_in_band`
- `transfer_aligned_finite_bin_count_in_band`
- 对应 finite fractions

必须使用与 processing receipt 固定字段一致的定义：

- reference spectrum：
  `rfft(output_after_pre, n=transfer_fft_length)`
- threshold：
  `max(abs(reference_spectrum)) * float64_epsilon * reference_sample_count`
- valid：
  `abs(reference_spectrum) > threshold`
- 其余 bin 为 zeroed

必须验证：

`valid_count + zeroed_count == analysis_band_bin_count`

若 analysis band 没有任何 bin，拒绝计算，不得产生除零值。

### G. 数据有限性证据

保存：

- QC metrics 中所有必填数值均为有限值
- optional 数值只能因明确 status/reason 为 `null`
- raw/aligned transfer 在分析频带内的 finite count
- metrics 不得包含 NaN、Inf 或字符串形式的 `"NaN"`、`"Infinity"`

## 七、严格数据模型

### DEV-04.02-03：模型与 Schema

至少建立：

- `ProvisionalQcMetrics`
- `ProvisionalQcReceipt`
- `QcRecord`
- `QcCreatedEvent`
- `PublishedProvisionalQc`

建议版本：

- metrics schema：`1.0.0`
- receipt schema：`1.0.0`
- QC algorithm version：`1.0.0`
- record/event schema：`1.0.0`

所有模型必须：

- strict
- `extra="forbid"`
- `allow_inf_nan=false`
- identity 使用安全 ASCII 标识符
- SHA256 使用严格小写 64 位十六进制
- datetime 必须带时区
- count 非负
- fraction 限制在 `[0,1]`
- RMS、peak、ratio 等非负
- nullable metric 与 status/reason 必须通过 model validator 保持一致

Receipt 至少绑定：

- `session_id`
- `source_run_id`
- `processing_id`
- `qc_id`
- `data_origin="synthetic"`
- `run_mode="development"`
- source capture receipt SHA256
- source processing receipt SHA256
- source processing arrays SHA256
- source processing schema/algorithm version
- config bundle content SHA256
- device manifest SHA256
- AnalysisConfig reference/raw/normalized SHA256
- QC metrics SHA256
- QC algorithm/version及上述 metric formula identifiers
- threshold和判决状态
- 全部 hardware/calibration/formal/experimental false flags
- create-only/immutable 标志
- safety marker：
  `SYNTHETIC_PROVISIONAL_QC_METRICS_NOT_AN_EXPERIMENTAL_RESULT`

生成并注册：

- `provisional_qc_metrics.schema.json`
- `provisional_qc_receipt.schema.json`

生成 Schema 数量应从 18 增至 20。不得手写与活动模型不一致的 Schema。

## 八、存储结构与不可变发布

### DEV-04.02-04：QC 七文件 envelope

QC 路径固定为：

`qc/run_<source_run_id>/processing_<processing_id>/qc_<qc_id>/`

路径必须由 store 根据：

- synthetic root
- session ID
- source run ID
- processing ID
- QC ID

推导。公共 API 不得接受任意目标目录、real root 或调用者拼接的发布路径。

QC 目录必须严格包含七个文件：

1. `qc_metrics.json`
2. `qc_metrics.sha256`
3. `qc_receipt.json`
4. `qc_receipt.sha256`
5. `qc_metadata.json`
6. `qc_record.json`
7. `QC_COMPLETE`

要求：

- JSON 使用项目 canonical JSON bytes
- sidecar 必须逐字节等于：
  `<sha256>  <filename>\n`
- 完成标记必须逐字节等于：
  `b"complete\n"`
- create-only
- same-filesystem staging
- 协作式 create-only lock
- 不覆盖既有 QC
- 并发发布最多一个成功
- 失败只清理调用者自己的 staging/lock
- 不删除已经发布的不可变目录
- QC 目录 exact file set，额外文件必须被 validator 拒绝

建议在 store 中增加窄接口：

`create_synthetic_qc(...)`

不得创建允许选择 real root 的通用危险入口。

## 九、来源信任链

### DEV-04.02-05：只从已验证来源计算

QC publisher 必须首先调用 DEV-04.01R2 的 public validator：

`validate_ess_processing(...)`

该 validator 已负责：

- 重验 capture
- 重验 ESS
- 重算 processing arrays
- 重建 receipt
- 验证 record/event/sidecars/completion

QC publisher 随后只能从该已验证 synthetic session/source/processing 派生所需 WAV 和 arrays。

公共 QC publisher API 不得接受：

- 任意 waveform
- 任意 processing arrays
- 任意 precomputed metrics
- arbitrary processed path
- real root
- expected latency/gain
- scenario truth latency/gain
- formal threshold
- QC decision override

若 processing、capture、ESS、config 或 event 任一验证失败，QC 目录不得创建。

## 十、QC event 审计绑定

### DEV-04.02-06：`qc_created` event

七文件 QC 目录发布后，通过既有受根约束的 session event API 追加：

`qc_created`

事件至少绑定：

- `schema_version`
- `source_run_id`
- `processing_id`
- `qc_id`
- `created_at`
- canonical `qc_record.json` SHA256
- `qc_metrics.json` SHA256
- `qc_receipt.json` SHA256

事件唯一身份必须是 session 内复合键：

`(source_run_id, processing_id, qc_id)`

必须吸取 DEV-04.01R 的教训：

- 同一个 `qc_id` 可以在不同 processing 下复用
- 同一个 processing ID 可以在不同 source run 下复用
- 不得只按 `qc_id` 或 `processing_id` 匹配
- 同一完整复合身份缺失或重复 event 必须拒绝

Event append 失败时：

- QC 七文件目录保留
- 返回 `published=true`
- 不声称整体成功
- validator 因缺少 event 拒绝该 QC
- 不删除已发布目录

报告中必须说明：event 只提供项目内部完整性和审计绑定，没有数字签名、外部只读 witness 或可信时间戳。

## 十一、只读重放 validator

### DEV-04.02-07：完整重算验证

实现 public validator，必须：

1. 重验 source processing。
2. 重新读取已验证 capture WAV 与 processing arrays。
3. 重新计算全部 QC metrics。
4. 验证 metrics canonical bytes 与 SHA sidecar。
5. 重建并验证 QC receipt。
6. 验证 metadata 完整 canonical bytes。
7. 验证 QC record canonical bytes。
8. 验证 `qc_created` 唯一复合身份及其 hashes/time。
9. 验证七文件 exact set。
10. 验证 `QC_COMPLETE == b"complete\n"`。
11. 拒绝旧版本、缺字段、extra、错误 literal、错误 null/status 组合。
12. 拒绝缺失、目录替代、额外空白、CRLF、错误 filename、重复 sidecar。
13. 成功或失败路径均不得写回、修复、删除或更新时间。
14. 返回严格 `PublishedProvisionalQc`。

## 十二、CLI

### DEV-04.02-08：Synthetic-only CLI

增加清晰的 synthetic-only 子命令，例如：

- `qc-compute`
- `qc-validate`

命名可按现有 CLI 风格调整，但报告必须说明最终名称。

CLI 必须：

- 要求明确的 session/source run/processing/QC identity
- 使用配置 bundle、scenario 和 ESS artifact reference
- 不接受 real root
- 不接受任意 WAV/NPZ
- 不接受 expected latency/gain
- 不接受 QC threshold或 decision
- 输出路径、metrics/receipt hashes、状态和 safety marker
- 明确显示：
  - `evaluation_status=provisional_metrics_only`
  - `qc_decision=not_evaluated`
  - `thresholds_applied=false`
  - `formal_eligible=false`
  - `experimental_result=false`
- 不枚举、播放、录音或打开 Stream

## 十三、TDD 测试要求

### DEV-04.02-09：纯内核测试

至少覆盖：

1. nominal development fixture。
2. peak/RMS 独立手算 oracle。
3. active/pre-silence切片边界。
4. clipping count/fraction：无 clipping、边界 `+1/-1`、部分 clipping。
5. pre-silence absent。
6. zero pre-silence RMS。
7. zero active RMS。
8. 有限非零 SNR proxy 的独立手算。
9. IR dominant/second peak/ratio。
10. 单样本 IR。
11. second peak为零。
12. reference off-peak RMS 独立手算。
13. reference residual为零。
14. analysis band valid/zeroed count。
15. spectral valid fraction。
16. raw/aligned transfer finite count。
17. NaN/Inf 输入拒绝。
18. 空数组、错误 shape、错误 dtype或样本区间拒绝。
19. 不读取 scenario truth。
20. 不使用正式阈值。

### DEV-04.02-10：持久化与攻击测试

至少覆盖：

1. 正常七文件 envelope。
2. create-only。
3. 并发最多一个成功。
4. staging failure cleanup。
5. event append failure `published=true`。
6. metrics/receipt/metadata/record/completion/extra 文件篡改。
7. 两个 sidecar 的所有非规范字节形式。
8. record timestamp 篡改。
9. event metrics/receipt/record hash 篡改。
10. event identity、sequence、canonical、extra 字段篡改。
11. event 缺失和同一复合身份重复。
12. 不同 source run 复用相同 processing ID 与 QC ID，分别可验证。
13. 同一 source run 下不同 processing 复用相同 QC ID，分别可验证。
14. validator 拒绝缺失或不完整 processing。
15. validator 拒绝被篡改 processing。
16. validator 前后完整文件树 bytes 不变。
17. real root 永不创建。
18. 正常 CLI 完整流程。
19. CLI formal/real/arbitrary path 负例。
20. deterministic 双根 byte equality。

不得使用 `skip`、`xfail`、无依据宽容差或 suppression 获得通过。

## 十四、双根确定性演示

### DEV-04.02-11：完整软件重放

使用两个预先确认不存在的短路径隔离临时根，分别执行：

ESS generate/validate  
→ synthetic session create/validate  
→ virtual capture publish/validate  
→ processing publish/validate  
→ provisional QC publish/validate

固定身份建议：

- ESS：`source_ess`
- session：`dev0402`
- assembly：`assembly001`
- capture：`capture001`
- processing：`processing001`
- QC：`qc001`
- measurement order：`0`

要求：

1. 两根 QC metrics、metrics sidecar、receipt、receipt sidecar、metadata 逐字节一致。
2. 记录五个新 deterministic SHA256。
3. record/event runtime timestamp不纳入跨运行 deterministic payload。
4. processing 的五个保护哈希保持不变。
5. nominal latency/IR 仍为 `37 / 37 / 0.5`。
6. QC 状态固定为 provisional/not-evaluated。
7. current synthetic pre-silence 若为零，SNR proxy 必须为 `null` 并注明 `zero_pre_silence_rms`，不得伪造无穷大。
8. 对一个根执行 metrics、sidecar、completion、record、event 篡改复验。
9. 每个攻击验证前后记录被测文件或完整树 SHA256，证明 validator 无写回。
10. 精确清理两个临时根并确认不存在。
11. real root 不得创建。

Windows 下使用足够短的临时路径，避免路径长度造成与代码无关的失败。环境失败必须如实记录并重跑，不得计作软件 PASS。

## 十五、静态与完整门禁

### DEV-04.02-12：最终验收

必须执行并记录：

1. 原完整 `473` 项测试全部保留。
2. DEV-04.02 新增测试全部通过。
3. 完整测试套件通过。
4. Ruff format check。
5. Ruff lint。
6. strict mypy，覆盖既有 67 source files及新增源码。
7. 20 个生成 Schema consistency。
8. `git diff --check`。
9. suppression 扫描：
   - skip
   - xfail
   - noqa
   - type ignore
10. U+FFFD、本机绝对路径、用户名、身份和秘密扫描。
11. 新真实音频 API、`sounddevice`、Stream、play、record 扫描。
12. tracked WAV、FLAC、NPY、NPZ、cache、staging、lock、测试临时目录扫描。
13. 历史 prompts/reports、配置、fixture、processing 数学和保护文件 diff检查。
14. implementation log 初始字节前缀检查。
15. 所有受保护 SHA256 复算。
16. Git 工作区及未跟踪文件检查。

## 十六、明确禁止范围

本步骤不得：

- 修改 DEV-04.01R 的 transfer 数学；
- 修改 processing arrays、receipt或当前 golden；
- 启用 smoothing；
- 实现 harmonic separation；
- 实现 baseline 选择、全 BLK 差分或漂移判定；
- 实现特征提取、归一化、分类或交叉验证；
- 填写 `qc_threshold`、`effect_threshold`、`drift_threshold`；
- 给出正式 QC PASS/FAIL；
- 连接、枚举、选择或绑定真实音频设备；
- 运行 production `audio-list`/`audio-inventory`；
- 播放、录音或打开真实 Stream；
- 读取或应用 iMM-6C 校准文件；
- 做 SPL、电气回环、真实 latency/shared clock；
- 修改 Stage 1–4 协议执行状态；
- 修改 CAD、V1.3 模型或 geometry lock；
- 进入 DEV-04.03 或后续阶段；
- force push。

所有 hardware/readiness/calibration/formal/experimental 标志必须继续为 false。

## 十七、文档与日志收尾

### DEV-04.02-13：报告

创建：

`docs/reports/DEV-04.02.md`

新增或最小更新：

- QC 架构文档
- storage layout
- README
- Schema registry说明
- CLI使用说明
- `docs/IMPLEMENTATION_LOG.md`

报告必须包含：

- 基线和范围；
- 每个指标的精确定义；
- nullable metric 的状态语义；
- 为什么没有正式阈值和 QC 判决；
- RED→GREEN 记录；
- 数据模型、Schema及版本；
- 来源信任链；
- 七文件 envelope；
- event 复合身份；
- validator 只读性；
- CLI；
- 测试及静态门禁；
- 双根 deterministic hashes；
- processing/V1.3/硬件保护哈希；
- 临时根清理；
- 实际命令；
- 未执行项目；
- 没有真实硬件操作；
- 已知限制；
- 修改文件清单。

日志必须记录到另一名人员借助其他 AI 可以尽可能复刻本步骤的程度。未知内容不得编造。

报告与日志冻结时尚未产生最终提交 SHA，不得自引用未来 SHA。

## 十八、提交与推送

### DEV-04.02-14：仅在全部 PASS 后推送

推送前再次确认：

- 全部测试、静态检查和攻击复验通过；
- processing 及全部历史保护哈希不变；
- QC 双根 deterministic hashes 已确认；
- 临时根已清理；
- 没有无关修改和未跟踪文件；
- `git diff --check` 通过；
- GitHub `main` 仍为：
  `cb2798f8b2d1544271b45c41741b3c6ee6cab6a7`

远端若已变化，停止且不推送。

全部通过后：

1. 提交主题：
   `DEV-04.02: add provisional offline QC evidence`
2. 正常推送到 `origin/main`。
3. 禁止 force push。
4. 推送后核验本地 `HEAD`、`origin/main`、GitHub main 完全一致。
5. 核验工作区干净。

若任何测试、哈希、远端或推送步骤失败：

- 不得报告 PASS；
- 不得推送未通过实现；
- 不得进入下一阶段；
- 如实报告本地状态和失败点。

## 十九、最终回复格式

最终回复必须给出：

- `PASS — DEV-04.02 完成` 或真实失败状态
- 最终提交 SHA
- 分支和远端
- 本地、`origin/main`、GitHub main 一致性
- 工作区状态
- 原测试、新增测试和完整测试数量
- Ruff、strict mypy、Schema、diff结果
- metrics/receipt/QC algorithm 版本
- 全部指标及 nominal fixture 实测值
- SNR proxy 数值或 null reason
- `evaluation_status`
- `qc_decision`
- `thresholds_applied`
- QC 五个 deterministic hashes
- processing 五个保护哈希
- V1.3、硬件和 ESS 保护哈希
- event 复合身份和攻击复验结果
- validator 无写回结果
- 临时根清理结果
- 没有真实硬件调用的声明
- 主要交付文件
- 已知限制
- 是否成功推送

完成 DEV-04.02 后立即停止，等待用户确认，不得自行进入后续步骤。