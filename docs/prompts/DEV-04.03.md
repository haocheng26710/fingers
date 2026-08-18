# DEV-04.03：离线重复测量集合与 provisional repeatability 证据

你现在负责在 Acoustic Ladder 仓库中实际实施 `DEV-04.03`。

这是代码实施任务，不是方案讨论。必须严格遵循本文的范围、日志、验证和 Git 规则。只有全部实现与门禁通过后才能提交和推送；发生失败、权限问题、远端变化、中断或未解决疑点时，必须保留真实记录并停止，不得推送。

---

## 一、任务目标

在现有 DEV-04.02 基础上，实现 synthetic-only、threshold-free 的离线重复测量集合及 repeatability 证据层。

本步骤只回答：

- 哪些已经完成 processing 和 provisional QC 的 synthetic 测量属于同一个连续重复集合；
- 重复成员之间的采集波形、延迟、脉冲响应和分析频带复传递函数有多大差异；
- 所有成员、指标、公式、来源和不可变文件是否可以被确定性重放；
- 数据是否为后续协议绑定、BLK 基线选择和漂移分析做好了结构准备。

本步骤不得：

- 把任何成员指定为全 BLK 基线；
- 执行正式基线差分；
- 设置阈值；
- 输出声学 QC PASS/FAIL；
- 形成漂移判决；
- 进入特征提取、分类、交叉验证或协议矩阵执行；
- 连接或操作真实音频硬件。

固定状态应表达为：

- `metric_computation_status = complete`
- `evaluation_status = provisional_repeatability_metrics_only`
- `repeatability_decision = not_evaluated`
- `thresholds_applied = false`
- `repeatability_threshold = null`
- `threshold_source = null`
- `baseline_role = not_assigned`
- `baseline_selection_status = deferred_until_protocol_binding`
- `baseline_difference_computed = false`
- `drift_decision = not_evaluated`
- `formal_eligible = false`
- `experimental_result = false`
- `hardware_io_performed = false`

---

## 二、Git 基线与远端规则

预期基线：

- 仓库远程：`https://github.com/haocheng26710/fingers.git`
- 分支：`main`
- 基线提交：`3eeda00b7a7900bfc0c341f002547020402ff9b5`
- 基线提交说明：`DEV-04.02: add provisional offline QC evidence`

开始任何文件修改前必须：

1. 查找并完整读取仓库适用的 `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`.agents`、`.codex` 或同类项目指令。
2. 确认当前目录确实是目标 Git 仓库。
3. 确认当前分支为 `main`。
4. 确认工作区干净，包括未跟踪文件。
5. 确认本地 `HEAD` 与 `origin/main` 均为上述基线。
6. 只读查询 GitHub `refs/heads/main`，确认仍为上述基线。
7. 确认 remote URL 正确。

如任一条件不满足：

- 不修改项目文件；
- 不自动 merge、rebase、reset、stash 或覆盖用户更改；
- 不提交；
- 不推送；
- 报告实际状态并停止。

禁止 force push、reset hard、clean 或其他破坏性 Git 操作。

---

## 三、提示词归档与实施日志

### DEV-04.03-00：初始化记录

在写业务代码前完成以下工作。

#### 1. 提示词归档

将本次收到的完整提示词归档为：

`docs/prompts/DEV-04.03.md`

要求：

- 尽可能保存收到的原始文本；
- 使用明确、可复核的编码；
- 记录文件字节数、换行形式、是否有末尾换行及 SHA256；
- 如果执行环境提供原始附件，必须逐字节复制并验证 SHA256；
- 如果只能访问可见消息文本，则保存为 UTF-8，并明确记录“未获得独立原始附件，不能声称与附件逐字节一致”；
- 不得编造 byte-exact 结论；
- 在 `.gitattributes` 中延续已有 prompt 归档策略；
- 不得修改历史 prompt 文件。

#### 2. 实施日志

继续使用：

`docs/IMPLEMENTATION_LOG.md`

这是 append-only 日志。开始前必须记录：

- 原文件字节数；
- 原完整前缀 SHA256；
- 当前时间和时区；
- Git 基线；
- remote；
- 工作区状态；
- 项目指令扫描结果；
- prompt 归档信息；
- 当前任务范围和禁止范围；
- 状态 `IN_PROGRESS`。

后续每完成一个编号步骤，都必须追加对应记录。不得重写、删除、美化或修正既有历史内容；如先前记录有误，只能在后面追加更正。

日志必须足够详细，使另一个人使用其他 AI 能尽可能复刻本次实施，包括：

- 实际读取的关键文件；
- 实际采用的模型、字段和公式；
- 每次 RED 的失败原因；
- 每次 GREEN 的真实结果；
- 实际命令；
- 测试数量和耗时；
- 中间失败及修正；
- deterministic hashes；
- 临时目录；
- 清理前后的验证；
- 未执行内容；
- 已知限制；
- Git 门禁结果。

不得记录尚未发生的结果，不得提前写 `PASSED`，不得编造最终提交 SHA 或远端推送结果。

---

## 四、现有基线必须保持

DEV-04.02 基线应至少满足：

- 完整测试：`553 passed`
- 生成 Schema：20 个
- strict mypy：72 个 source files
- processing receipt/algorithm：`1.1.0`
- provisional QC metrics/receipt/algorithm：`1.0.0`

DEV-04.02 固定身份 QC 哈希：

- `qc_metrics.json`  
  `627ad7791b284b038e32beadb30a9603242d3b68f8fd0a466e2a9b7d606e4c0f`
- `qc_metrics.sha256`  
  `8702aa02ee3337f9bdd9b192c8b8a78657bd9c93674f7c623db5a9e17a43047b`
- `qc_receipt.json`  
  `8a72666b84179d708128e9b06eff66cb94d9819ec00d708e268a926f26b6754d`
- `qc_receipt.sha256`  
  `f07e31fdb3c9a903b32e06048599d70c9f135d9265c2512b5c27e3a48d09b9f8`
- `qc_metadata.json`  
  `7c11de246773d89d481a4f575b3a9efdfccae4102fdae4b30c366a9076b961d2`

DEV-04.01R2 processing 保护哈希：

- arrays  
  `e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89`
- arrays sidecar  
  `f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902`
- receipt  
  `25616c6e2d42413243eb8e14cd099d01e69e736c29ffcce5cdd413e97841ad5f`
- receipt sidecar  
  `38ef680d07fbc88ca7f2d59bba10866439fe2db80b95b34bcea7eec202830e63`
- metadata  
  `daa1c08780c9381604f08be14a268bcb7a539844622096de588c5c020c2a04cb`

其他保护哈希：

- V1.3 ZIP  
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest  
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory  
  `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context  
  `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- inventory summary  
  `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight  
  `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup  
  `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`
- ESS WAV  
  `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- ESS metadata  
  `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- ESS raw float32  
  `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

这些值必须通过实际复算或真实回归验证，不得直接把本文中的字符串抄入报告后声称已验证。

---

## 五、TDD 要求

使用严格的 RED → GREEN → REFACTOR 方法。

如果执行环境提供 TDD skill，必须先完整读取并遵循；如果不可用，也必须执行同样的测试优先流程。

每个纵向切片都必须：

1. 先编写通过公共接口失败的测试；
2. 真实运行并记录 RED；
3. 实现满足契约的最小代码；
4. 真实运行并记录 GREEN；
5. 再进行不改变行为的整理；
6. 运行相关回归；
7. 将事实追加到实施日志。

不得：

- 先写完整实现再补测试；
- 使用 skip、xfail、noqa 或类型抑制掩盖失败；
- 删除或放宽已有测试；
- 只测试私有函数；
- 把 production 结果硬编码为测试期望；
- 把 synthetic fixture 的零差异当成算法正确性的唯一证据。

---

## 六、重复集合的权威边界

### DEV-04.03-01：成员身份与集合规则

定义严格的重复成员身份，至少包含：

- `source_run_id`
- `processing_id`
- `qc_id`

publisher 可接受成员身份列表，但不得接受：

- waveform；
- arbitrary WAV/NPZ 路径；
- processing arrays；
- precomputed metrics；
- caller-supplied measurement order；
- caller-supplied reassembly ID；
- condition label；
- BLK/baseline 标志；
- expected latency/gain；
- expected truth；
- threshold；
- decision；
- real root；
- device、Host API、channel 或 calibration 参数。

所有成员事实必须从已经保存的 synthetic run、processing 和 QC 中派生。

每个成员必须依次通过现有公共验证器：

1. virtual capture replay validation；
2. ESS processing replay validation；
3. provisional QC replay validation。

如现有 QC validator 已传递执行前两项，可复用，但重复集合仍必须获得并验证成员所需的 capture receipt、processing receipt、QC receipt和数组来源，不得信任调用者提供的副本。

连续重复集合必须满足：

- 至少两个不同 `source_run_id`；
- 所有成员属于同一 `session_id`；
- 所有成员属于同一 `reassembly_id`，该值从 capture provenance 派生；
- 所有成员使用同一 ESS 来源和哈希；
- 同一 bundle content hash；
- 同一 device manifest hash；
- 同一 AudioConfig、AnalysisConfig及其 normalized hash；
- 同一 virtual scenario 原始与规范化哈希；
- 同一 processing schema/algorithm version；
- 同一 QC schema/algorithm version；
- 同一 sample rate、sweep timing、FFT dimensions和 analysis-band mask；
- 每个 source run 在集合中只能出现一次；
- 成员三元身份不得重复；
- `measurement_order` 必须来自 capture receipt；
- 排序必须由 `measurement_order` 派生，不能使用调用者列表顺序；
- measurement order 不得重复；
- 本步骤的“连续重复”要求排序后的 measurement order 连续无缺口。

调用者以不同顺序传入同一组成员时，规范化后的 deterministic payload 必须相同。

任何成员缺失、未完成、被篡改、版本不匹配、来源不一致或顺序无效时，必须在 repeatability 目录写入前拒绝。

不得把同一 source run 的不同 processing/QC 版本当作两个独立测量成员。

---

## 七、纯函数 repeatability 数学内核

### DEV-04.03-02：指标公式

建立没有文件系统副作用的纯函数内核。内部统一使用 float64/complex128，明确检查：

- shape；
- dtype；
- 非空；
- C-contiguous 规范化；
- NaN/Inf；
- 分母为零；
- analysis band 非空；
- 每个成员的数组尺寸一致；
- 相关系数范围；
- 所有 count/fraction 的一致性。

对每个成员按 measurement order 排序。对于 `n` 个成员，生成所有唯一无序成员对 `i < j`，pair 数必须为：

`n * (n - 1) / 2`

每条 pair record 必须包含两个成员的三元身份及 measurement order。

### 1. 捕获输入重复扫频相关性

从经过验证的 captured-input WAV 派生：

`x_i = captured_input_i[0, pre_silence_sample_count:]`

要求所有 `x_i` 长度一致。

使用 normalized dot correlation：

`corr_x(i,j) = dot(x_i,x_j) / (norm2(x_i) * norm2(x_j))`

要求：

- 结果限制在 `[-1, 1]`；
- 只允许极小浮点舍入后进行有依据的边界夹紧；
- 如任一范数为零，值为 `null`，并使用固定 reason enum；
- 不得添加 epsilon 伪造结果。

### 2. 延迟差异

从 replay-validated processing receipt 派生：

- signed delta：`latency_j - latency_i`
- absolute delta：`abs(latency_j - latency_i)`

同时记录：

- member latency min；
- member latency max；
- latency span；
- pairwise maximum absolute delta。

不得重新把 synthetic scenario 的 expected latency 当作测量输入。

### 3. 对齐后 IR 重复性

使用：

`r_i = ir_aligned_i[0,0,:]`

要求长度一致且有限。

IR correlation：

`corr_ir(i,j) = dot(r_i,r_j) / (norm2(r_i) * norm2(r_j))`

IR symmetric normalized RMSE：

`nrmse_ir(i,j) = norm2(r_i-r_j) / sqrt((norm2(r_i)^2 + norm2(r_j)^2)/2)`

如分母为零：

- 值必须为 `null`；
- 使用明确 reason enum；
- 不得产生 NaN、Inf 或 epsilon 替代值。

### 4. 分析频带复传递函数差异

由 processing arrays 重建：

`H_i[k] = transfer_aligned_real_i[0,0,k] + 1j * transfer_aligned_imag_i[0,0,k]`

只在经过验证且所有成员一致的 `analysis_band_mask` 内计算。

复传递函数 symmetric relative L2：

`relative_l2_H(i,j) = norm2(H_i-H_j) / sqrt((norm2(H_i)^2 + norm2(H_j)^2)/2)`

分母为零时使用 null + reason，不得添加 epsilon。

### 5. 幅度差异

固定 float64 floor：

`floor = numpy.finfo(float64).tiny`

`M_i_db[k] = 20 * log10(max(abs(H_i[k]), floor))`

幅度差异 RMS：

`magnitude_rmse_db(i,j) = sqrt(mean((M_i_db-M_j_db)^2))`

必须记录所用 floor 策略的 formula ID。该值只是数值表示差异，不是 SPL、听力安全指标或正式 QC。

### 6. 相位差异

只在同时满足以下条件的 analysis-band bins 上计算：

- `abs(H_i[k]) > 0`
- `abs(H_j[k]) > 0`

相位差定义为：

`phase_delta[k] = angle(H_i[k] * conjugate(H_j[k]))`

相位 RMS：

`phase_rms_rad(i,j) = sqrt(mean(phase_delta[k]^2))`

必须记录：

- joint phase-valid bin count；
- joint phase-valid fraction；
- 无有效 bin 时返回 `null` + 固定 reason；
- 不得把零幅值 bin 的 `angle(0)` 当成有效相位；
- 不得执行 smoothing；
- 不得执行新的 phase unwrap 作为隐式预处理。

### 7. 聚合指标

至少记录：

- member count；
- pair count；
- measurement order min/max；
- latency min/max/span；
- captured-input correlation 的 defined count、min、mean；
- IR correlation 的 defined count、min、mean；
- IR normalized RMSE 的 defined count、mean、max；
- complex-transfer relative L2 的 defined count、mean、max；
- magnitude RMSE dB 的 defined count、mean、max；
- phase RMS rad 的 defined count、mean、max；
- phase-valid fraction 的 min/mean；
- 所有必填数值有限性标志。

聚合只能从逐 pair 数据重算，不得单独接受调用者提供的 aggregate。

所有 nullability、reason enum、count、fraction、mean/min/max 必须由严格模型交叉验证。

---

## 八、严格数据模型

### DEV-04.03-03：模型与版本

建议建立以下严格模型，名称可根据现有代码风格做最小调整，但语义不得弱化：

- `RepeatabilityMemberIdentity`
- `RepeatabilityMemberEvidence`
- `RepeatabilityPairMetrics`
- `ProvisionalRepeatabilityMetrics`
- `ProvisionalRepeatabilityReceipt`
- `RepeatabilityRecord`
- `RepeatabilityCreatedEvent`
- `PublishedProvisionalRepeatability`

统一要求：

- Pydantic strict mode；
- `extra="forbid"`；
- `allow_inf_nan=false`；
- 安全 identifier；
- SHA256 使用严格小写 64 hex；
- 相对路径必须通过现有 path validator；
- aware datetime；
- 不允许 `"."`、`"..“` 或路径逃逸；
- 所有固定状态使用 Literal；
- schema/algorithm 初始版本均为 `1.0.0`；
- 所有公式具有固定 formula ID；
- 所有 optional value 必须与 reason/status 一致；
- 所有 fraction 必须与 count/denominator 完全一致；
- pair 身份顺序必须与 measurement order 一致；
- member count、pair count和实际数组长度一致；
- aggregate 必须能由 pair records 验证；
- `all_required_numeric_values_finite` 只能为 true，且必须由实现实际检查得出。

Receipt 必须绑定：

- session；
- 派生出的 reassembly；
- repeat set ID；
- 规范化成员顺序；
- 每个成员的 source run、processing、QC 身份；
- capture receipt SHA256；
- processing receipt SHA256；
- processing arrays SHA256；
- QC metrics SHA256；
- QC receipt SHA256；
- bundle hash；
- device manifest hash；
- AudioConfig/AnalysisConfig引用和哈希；
- virtual scenario引用、原始哈希与规范化哈希；
- ESS metadata/raw/WAV相关来源哈希；
- processing 和 QC schema/algorithm versions；
- repeatability metrics SHA256；
- repeatability algorithm ID/version；
- 全部公式 ID；
- create-only/immutable；
- 固定 provisional/not-evaluated状态；
- 全部 hardware/calibration/formal/experimental false 标志；
- 明确 safety marker，例如：

`SYNTHETIC_PROVISIONAL_REPEATABILITY_METRICS_NOT_AN_EXPERIMENTAL_RESULT`

不得复用一个含义不准确的旧 safety marker。

---

## 九、不可变发布与存储

### DEV-04.03-04：发布路径和 exact envelope

重复集合是 session-level QC 派生产物，建议路径：

`qc/repeat_sets/reassembly_<reassembly_id>/repeat_set_<repeat_set_id>/`

其中 `reassembly_id` 必须从验证后的成员派生，不能由调用者决定。

如现有存储风格要求略微调整路径，可以进行最小一致性调整，但必须：

- 仍位于 injected synthetic session root；
- 不接受 real root；
- 路径完全由已验证身份派生；
- 在架构文档中明确；
- 有路径逃逸和 unsafe ID 回归测试。

exact envelope 固定为七个文件：

1. `repeatability_metrics.json`
2. `repeatability_metrics.sha256`
3. `repeatability_receipt.json`
4. `repeatability_receipt.sha256`
5. `repeatability_metadata.json`
6. `repeatability_record.json`
7. `REPEATABILITY_COMPLETE`

要求：

- JSON 使用现有 canonical JSON writer；
- sidecar 必须是严格规范字节；
- completion 必须是固定精确字节，例如 `b"complete\n"`；
- 同文件系统 staging；
- create-only cooperative lock；
- final rename；
- 不覆盖已有集合；
- staging 失败只清理本次 staging/lock；
- 不删除或修复已有产物；
- 并发发布最多一个成功；
- exact file set，额外文件也必须导致验证失败。

成功发布目录后追加 session event：

`repeatability_created`

事件复合身份至少为：

`(reassembly_id, repeat_set_id)`

事件必须绑定：

- session；
- reassembly；
- repeat set ID；
- created_at；
- record SHA256；
- metrics SHA256；
- receipt SHA256；
- 规范化 member list digest或等价绑定。

同一 session 中：

- 不同 reassembly 可复用 repeat set ID；
- 同一 `(reassembly_id, repeat_set_id)` 不得重复；
- 不得只按 repeat set ID 匹配事件。

事件追加失败时：

- 已发布目录不得删除；
- 异常必须准确报告 `published=true`；
- 不得把事件失败误报为“未产生任何文件”。

---

## 十、只读重放验证

### DEV-04.03-05：validator

实现只读 validator，必须：

1. 重新验证全部成员的 capture、processing 和 QC。
2. 重新派生 reassembly 和 measurement order。
3. 重新规范化成员顺序。
4. 重新读取 capture WAV 和 processing arrays。
5. 重新计算全部 pair 和 aggregate metrics。
6. 重建 metrics、receipt、metadata及其预期字节。
7. 严格验证 exact seven-file envelope。
8. 严格验证 canonical JSON。
9. 严格验证两个 SHA256 sidecar。
10. 严格验证 completion bytes。
11. 使用唯一匹配 event 的时间重建 record，不允许 record 自证时间。
12. 验证 event filename sequence、JSON sequence、session、origin、复合身份、hash和时间。
13. 要求恰好一个匹配事件。
14. 对验证前后的完整目标树保持逐字节不变。

validator 不得：

- 写回；
- 修复；
- 重命名；
- 删除；
-补 sidecar；
-补 completion；
-重新发布；
- 接受调用者提供的 metrics或可信 hash。

---

## 十一、CLI

### DEV-04.03-06：synthetic-only CLI

新增清晰的 CLI，例如：

- `repeatability-compute`
- `repeatability-validate`

成员参数可以采用可重复的：

`--member SOURCE_RUN_ID:PROCESSING_ID:QC_ID`

要求：

- identifier 不允许冒号，因此可无歧义解析；
- 至少两个 `--member`；
- 调用者顺序不影响最终成员顺序；
- 不提供 measurement order；
- 不提供 reassembly；
- 不提供 condition/BLK/baseline；
- 不提供 threshold/decision；
- 不提供 arbitrary WAV/NPZ；
- 不提供 real root；
- 不提供硬件或校准参数。

成功输出至少包括：

- repeat set ID；
- 派生 reassembly ID；
- normalized member count；
- pair count；
- measurement order范围；
- latency span；
- IR correlation min/mean；
- complex transfer difference mean/max；
- magnitude RMSE mean/max；
- phase RMS defined count/mean/max；
- metrics hash；
- receipt hash；
- fixed provisional states；
- safety marker。

必须明确输出：

- `SYNTHETIC_ONLY`
- `PROVISIONAL_REPEATABILITY_METRICS_ONLY`
- `REPEATABILITY_NOT_EVALUATED`
- `THRESHOLDS_NOT_APPLIED`
- `BASELINE_NOT_ASSIGNED`
- `BASELINE_SELECTION_DEFERRED_UNTIL_PROTOCOL_BINDING`
- `NO_BASELINE_DIFFERENCE_COMPUTED`
- `NO_HARDWARE_AUDIO_IO_PERFORMED`
- `NOT_AN_EXPERIMENTAL_RESULT`

CLI 的 `PASS` 只能表示软件命令和完整性验证通过，不能表示声学重复性或正式 QC PASS。

---

## 十二、测试要求

### DEV-04.03-07：公共接口、Oracle和攻击回归

至少覆盖以下测试。

#### 1. 纯内核独立 Oracle

不能只使用完全相同的 synthetic 波形。

构造明确、手算或由独立 NumPy公式计算的：

- 两成员非零延迟差；
- 三成员 pair count；
- captured-input correlation；
- IR correlation；
- IR symmetric NRMSE；
- complex transfer relative L2；
- magnitude RMSE dB；
- phase RMS；
- polarity变化；
- 幅值缩放；
- 单 bin相位变化；
- null denominator；
- zero phase-valid bins；
- count/fraction/aggregate。

测试期望必须由测试内独立公式产生，不能调用 production helper 计算 expected。

#### 2. 成员来源

覆盖：

- 少于两个成员；
- 重复三元身份；
- 同一 source run 的不同 processing/QC 重复计入；
- duplicate measurement order；
- measurement order gap；
- caller 输入乱序但最终 payload一致；
- mixed session；
- mixed reassembly；
- mixed scenario；
- mixed bundle；
- mixed AnalysisConfig；
- mixed ESS；
- mixed processing version；
- mixed QC version；
- missing/incomplete member；
- tampered capture；
- tampered processing；
- tampered QC；
- unsafe repeat set ID；
- unsafe member ID；
- real root 不产生。

#### 3. 模型严格性

覆盖：

- extra字段；
- 非 strict 类型；
- NaN/Inf；
- 错 formula ID；
- 错 schema/algorithm version；
- 错 fixed state；
- 不一致 count/fraction；
- 不一致 pair count；
- 不一致 aggregate；
- null/status错配；
- member order与 measurement order不符；
- baseline 被错误标记；
- threshold 非 null；
- formal/hardware/calibration/experimental flag 被改为 true。

#### 4. 持久化

覆盖：

- exact seven files；
- duplicate create-only；
- concurrent publication；
- staging failure cleanup；
- metrics tamper；
- metrics sidecar 所有非规范形式；
- receipt tamper；
- receipt sidecar 所有非规范形式；
- metadata tamper；
- record tamper；
- record time自证攻击；
- completion内容篡改；
- completion变目录；
- extra file；
- event missing；
- event duplicate；
- event hash tamper；
- event time tamper；
- event identity tamper；
- event extra field；
- event noncanonical；
- event filename/sequence mismatch；
- append event failure `published=true`；
- validator 前后树哈希不变。

#### 5. 复合身份

真实建立：

- 同 reassembly 不同 repeat set ID；
- 不同 reassembly 相同 repeat set ID；
- 同 `(reassembly_id, repeat_set_id)` duplicate；
- 两个合法事件不能让单个 validator 误判“多事件”。

#### 6. API authority

检查 publisher/validator 签名，确认不接受：

- arrays；
- waveforms；
- precomputed metrics；
- arbitrary data path；
- measurement order；
- reassembly ID；
- condition label；
- baseline role；
- truth；
- threshold；
- decision；
- real root；
- hardware/device/channel/calibration。

#### 7. CLI

覆盖：

- 完整 synthetic success；
- compute 后 validate；
- 乱序 member参数；
- 少成员；
- malformed member；
- forbidden threshold/baseline/real-root 等参数；
- 固定安全输出；
- 无 production audio API 调用。

---

## 十三、双根确定性演示

### DEV-04.03-08：完整软件重放

使用两个预先确认不存在的短临时根。

每个根建立：

- 一个 synthetic session；
- 一个 reassembly；
- 至少三个 virtual capture runs；
- measurement orders `0, 1, 2`；
- 每个 run各自完成 processing；
- 每个 processing各自完成 provisional QC；
- 一个包含三个成员的 repeatability set；
- publish 后立即 validate。

固定身份建议：

- ESS：`source_ess`
- session：`dev0403`
- reassembly：`assembly001`
- captures：`capture001`、`capture002`、`capture003`
- processing：`processing001`
- QC：`qc001`
- repeat set：`repeatset001`
- measurement order：`0`、`1`、`2`

processing/QC ID 可以在不同 source runs 下安全复用，但复合身份必须正确。

要求：

1. 两个根的 repeatability metrics、metrics sidecar、receipt、receipt sidecar、metadata逐字节相同。
2. 记录五个新 deterministic SHA256。
3. record/event timestamp不纳入跨根 deterministic payload声明。
4. 成员顺序必须为 measurement order `0,1,2`。
5. pair count 必须为3。
6. 当前相同 virtual scenario 若产生零差异，必须如实记录。
7. 零差异 golden不能替代非零纯内核 Oracle。
8. 状态必须为 provisional/not-evaluated/no-baseline。
9. real root不得创建。
10. processing、QC及所有历史保护哈希必须保持不变。
11. 对一个根执行至少：
    - metrics篡改；
    - sidecar篡改；
    - completion篡改；
    - record时间篡改；
    - event篡改。
12. 每次攻击前后计算目标文件或完整 session tree SHA256，证明 validator 无写回。
13. 攻击测试后恢复原始测试副本并再次验证 PASS。
14. 清理前先解析并确认临时根位于预期测试父目录。
15. 仅精确删除本步骤创建的临时根。
16. 清理后确认所有临时根不存在。

Windows 下使用足够短的路径，避免路径长度成为环境失败。环境失败必须记录并修正后重跑，不能计作软件 PASS。

---

## 十四、Schema与文档

### DEV-04.03-09：Schema

从活动模型生成并提交：

- provisional repeatability metrics Schema；
- provisional repeatability receipt Schema。

除非代码审计证明需要额外顶层 Schema，本步骤预计：

- generated Schema：20 → 22；
- `schemas/*.schema.json` 总数包含既有手工 device-manifest Schema，应相应为23。

不得只手写 Schema。必须由活动模型导出并执行 consistency check。

如实际架构需要不同数量：

- 必须解释原因；
- 证明没有遗漏或重复注册；
- 不得仅修改数量断言让测试通过。

### DEV-04.03-10：文档

创建：

`docs/reports/DEV-04.03.md`

新增或最小更新：

- repeatability 架构文档；
- storage layout；
- configuration说明；
- README；
- CLI说明；
- Schema registry说明；
- data README；
- append-only implementation log。

文档必须明确：

- 当前只支持 synthetic continuous repeats；
- 同一 reassembly 的连续 measurement orders；
- 没有 protocol condition binding；
- 没有 BLK baseline语义；
- 没有 baseline difference；
- 没有 threshold/pass-fail；
- 没有漂移判决；
- 没有硬件、校准或 SPL；
- event只提供项目内部完整性与审计绑定；
- 无数字签名、外部 witness或可信时间戳；
- 不声称抵御所有恶意协同文件系统篡改或 TOCTOU actor。

报告不得把 synthetic repeatability 指标写成实验结论。

---

## 十五、完整门禁

### DEV-04.03-11：最终验收

必须执行并记录：

1. 基线 553 项测试全部保留。
2. DEV-04.03 新增测试全部通过。
3. 完整测试套件通过。
4. 无 skip、xfail或测试数量减少。
5. Ruff format check。
6. Ruff lint。
7. strict mypy，覆盖既有和新增源文件。
8. 22 个 generated Schema consistency，或经审计解释的正确数量。
9. `git diff --check`。
10. prompt归档 SHA256复核。
11. implementation log旧前缀 SHA256复核。
12. suppression扫描：
    - skip
    - skipif
    - xfail
    - noqa
    - type ignore
13. U+FFFD扫描。
14. 新增本机绝对路径、用户名、身份和秘密扫描。
15. 新增真实音频 API扫描：
    - sounddevice
    - Stream
    - play
    - rec
    - audio-list
    - audio-inventory
16. tracked WAV、FLAC、NPY、NPZ、cache、staging、lock和临时目录扫描。
17. 历史 prompts/reports不得修改。
18. config、fixtures、reference和V1.3包保护检查。
19. processing数学、processing hashes、QC hashes保护检查。
20. 两根 deterministic payload逐字节比较。
21. 攻击后 validator无写回证明。
22. real root未创建。
23. 所有本步骤临时根已安全清理。
24. 最终工作区只包含预期修改。
25. 提交前完整复跑一次最终测试和静态门禁。

不得把首次失败后的旧测试结果冒充最终结果。报告和日志必须同时保留真实中间失败与最终修正结果。

---

## 十六、明确禁止范围

本步骤不得：

- 修改 V1.3 模型包或 CAD；
- 修改设备校准记录；
- 修改真实打印状态；
- 修改已有 ESS 数学；
- 修改 processing transfer数学；
- 改写已有 processing/QC golden以迁就新实现；
- 启用 smoothing；
- 实现 harmonic separation；
- 选择或标记全 BLK baseline；
- 实现 baseline difference；
- 填写 `qc_threshold`、`effect_threshold`、`drift_threshold` 或 repeatability threshold；
- 输出声学 QC PASS/FAIL；
- 输出 drift PASS/FAIL；
- 实现 feature extraction；
- 实现 normalization pipeline；
- 实现 classifier；
- 实现 cross-validation；
- 实现 Stage 1–4 协议执行引擎；
- 执行真实实验；
- 枚举或连接设备；
- 选择 device index、Host API或channel；
- 播放、录音或打开 Stream；
- 读取或应用 iMM-6C 校准文件；
- 做 SPL校准；
- 做电气回环；
- 声称 shared clock/full duplex已验证；
- 创建 real root；
- 进入 DEV-04.04、DEV-05或后续步骤；
- force push。

如果实现过程中发现必须修改受保护数学、历史哈希或任务语义才能继续：

1. 停止；
2. 在日志记录证据；
3. 不提交；
4. 不推送；
5. 向用户报告最小必要变更和影响；
6. 等待用户重新确认。

---

## 十七、Git提交和推送

### DEV-04.03-12：条件提交

只有以下条件全部满足时才允许提交：

- 所有测试和静态门禁通过；
- 双根确定性通过；
- 攻击回归通过；
- 保护哈希通过；
- 日志和报告只记录真实事实；
- 临时文件已清理；
- 工作区没有非预期文件；
- GitHub `main` 在提交前仍指向基线  
  `3eeda00b7a7900bfc0c341f002547020402ff9b5`。

提交信息固定为：

`DEV-04.03: add provisional repeatability evidence`

不得在报告或日志中伪造尚未产生的最终提交 SHA。不要尝试让提交内容自引用自己的 SHA。

提交后必须：

1. 确认提交包含且只包含本步骤预期文件；
2. 确认工作区干净；
3. 再次确认 remote URL和分支；
4. 使用正常 push推送 `main`；
5. 禁止 force push；
6. 推送后只读核对：
   - local HEAD；
   - `origin/main`；
   - GitHub `refs/heads/main`；
7. 三者必须完全一致；
8. 最终回复报告真实提交 SHA、测试结果、哈希、远端一致性及已知限制。

如果远端在实施期间发生变化：

- 不 push；
- 不自动 merge/rebase；
- 报告本地已完成状态和远端新 SHA；
- 等待用户决定。

如果任何测试、权限、网络、Git或实现步骤中断：

- 不 push；
- 不把状态写成 PASSED；
- 日志记录最后成功检查点和阻塞原因；
- 最终回复明确说明未推送。

---

## 十八、最终回复格式

成功时最终回复至少报告：

- `PASS — DEV-04.03 完成`
- commit SHA；
- branch和remote；
- local/origin/GitHub三向一致性；
- 工作区状态；
- 原测试数、新增测试数、完整测试数；
- Ruff、mypy、Schema、diff结果；
- 新五个 deterministic hashes；
- member/pair数量；
- nominal repeatability结果；
- 所有保护哈希状态；
- 临时根清理状态；
- 未执行真实硬件操作；
- 当前仍无 baseline、threshold、pass/fail、drift decision或实验结论；
- 主要交付文件；
- 已知限制。

失败或中断时最终回复至少报告：

- `NOT PUSHED`
- 当前状态；
- 最后成功步骤；
- 真实失败命令和错误；
- 是否产生了本地文件或提交；
- 工作区状态；
- 未推送确认；
- 继续前需要的用户决定。

完成 DEV-04.03 后停止，不进入下一步骤。