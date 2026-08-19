# DEV-04.04：Synthetic 协议条件绑定与全 BLK 基线差分证据

你现在负责在 Acoustic Ladder 仓库中实施 DEV-04.04。

本步骤必须采用严格的 TDD 红—绿—重构流程，通过公共接口验证行为。完成本步骤后停止，不得自行进入特征提取、分类、正式协议执行、真实硬件接入或后续阶段。

---

## 一、基线与远端

仓库：

`https://github.com/haocheng26710/fingers.git`

分支：

`main`

预期基线提交：

`b30e70d5709673bb1e8a7d5d9284c20359db261c`

预期提交标题：

`DEV-04.03R: close repeatability state and threshold gates`

开始修改前必须：

1. 定位仓库根目录。
2. 阅读全部项目级指令文件；如不存在，如实记录。
3. 确认工作区干净。
4. 确认当前分支为 `main`。
5. 确认 remote URL 正确。
6. 正常执行 `git fetch origin main`。
7. 分别核对：
   - local `HEAD`
   - `origin/main`
   - GitHub `refs/heads/main`
8. 三者必须全部为上述基线提交。

如果基线不同、存在未提交修改或远端已前进：

- 立即停止；
- 不修改文件；
- 不 reset、rebase、merge 或覆盖用户内容；
- 不提交、不推送；
- 如实报告差异。

基线预期门禁：

- 完整测试：`601 passed`
- Ruff format：123 files
- strict mypy：77 source files
- generated Schema：22
- Schema 总数：23
- `git diff --check`：PASS

实际基线结果必须重新运行并记录，不能直接照抄。

---

## 二、本步目标

在现有 synthetic capture → ESS processing → provisional QC → repeatability 链上，新增一个严格受控的开发阶段能力：

1. 使用经过验证的 Stage 1 development condition plan，将 synthetic capture 确定性绑定到协议条件。
2. 支持至少：
   - 全节点 `BLK` 条件；
   - 一个单桥候选条件，例如 `N1 + B40`，其他节点全部 `BLK`。
3. condition plan 必须从现有 manifest 和 Stage 1 协议草案解析、验证并生成完整节点状态，不接受调用者提交任意节点状态字典。
4. 生成 condition-aware、synthetic-only 的确定性虚拟采集证据。
5. 使 condition-aware capture 能继续通过现有 processing、QC 和 repeatability 证据链。
6. 从两个已验证的 condition-aware repeatability set 中：
   - 自动识别全 `BLK` 基线；
   - 自动识别单桥候选；
   - 计算原始、未平滑的基线差分；
   - 生成不可变、可重放、可审计的 provisional baseline-difference evidence。
7. 保留完整复传递函数、幅值、相位、展相位、脉冲响应、有效频点掩码和来源哈希。
8. 不产生任何阈值判决、PASS/FAIL、漂移结论或真实实验结论。

本步骤的软件 `PASS` 只表示实现、发布和验证成功，不表示单桥效应显著、结构可分、声学有效或实验通过。

---

## 三、严格禁止范围

本步骤禁止：

- 枚举、选择或绑定真实音频设备；
- 调用 production `sounddevice`、PortAudio、WASAPI、ASIO 或其他真实音频 API；
- 播放、录音或打开任何真实 Stream；
- 使用 iMM-6C、竹 2、校准文件、SPL 校准器或电气回环；
- 创建或写入 real data root；
- 修改现有正式 Stage 1–4 协议草案为 `execution_ready=true`；
- 声称执行了正式实验协议；
- 允许调用者提交任意 waveform、IR、复频谱、NPZ、预计算指标或输出目录；
- 根据结果选择“效果最好”的基线；
- 将非全 `BLK` 条件标为基线；
- 填写 `baseline_selection_rule`；
- 填写任何：
  - `qc_threshold`
  - `effect_threshold`
  - `drift_threshold`
  - `classification_pass_threshold`
- 产生 QC、effect、repeatability 或 drift PASS/FAIL；
- 实现特征提取、分类器、交叉验证、混淆矩阵或阶段 1–4 正式协议引擎；
- 修改现有 repeatability 数学；
- 修改现有 ESS、processing 或 QC 数学；
- 将 synthetic 非零差分描述成真实装置可检测性；
- 修改历史 prompt、report 或实施日志旧内容；
- force push；
- 自动进入 DEV-05 或其他后续阶段。

---

## 四、Prompt 归档与实施日志

### 4.1 Prompt 归档

在修改生产代码前，将本次完整提示词归档为：

`docs/prompts/DEV-04.04.md`

优先从当前任务暴露的 pasted-text/attachment 原始文件逐字节复制，不得人工重输后声称 byte-identical。

记录：

- 原始附件路径或来源方式；
- 字节数；
- CRLF 数；
- lone LF 数；
- 是否有末尾换行；
- SHA256；
- 归档文件 SHA256；
- 两者是否逐字节相同。

如任务环境没有提供可访问的原始 prompt 文件：

- 不得伪造 byte-identical 结论；
- 在日志中明确记录；
- 停止修改并向用户请求原始提示词文件。

如需保护换行，更新 `.gitattributes`，沿用已有 prompt binary 归档形式。

### 4.2 实施日志

只能向以下文件末尾追加：

`docs/IMPLEMENTATION_LOG.md`

不得修改、排序、格式化或重写任何历史内容。

使用一致序号：

- `DEV-04.04-00`：基线、远端、工作区和指令文件
- `DEV-04.04-01`：prompt 归档与范围冻结
- `DEV-04.04-02`：condition plan TDD
- `DEV-04.04-03`：condition-aware virtual capture TDD
- `DEV-04.04-04`：baseline-difference 数学内核 TDD
- `DEV-04.04-05`：不可变发布与只读验证 TDD
- `DEV-04.04-06`：CLI、Schema 和文档
- `DEV-04.04-07`：双根、攻击和保护哈希
- `DEV-04.04-08`：最终门禁与待提交状态

日志必须详细到另一位人员使用其他 AI 可以尽可能复刻同样结果，包括：

- 时间；
- 工作目录；
- 输入文件及哈希；
- 实际命令；
- 真实 RED 输出；
- 对应最小 GREEN 修改；
- 测试数量与结果；
- 失败、误操作及修复；
- 数据结构和公式决定；
- 临时目录；
- 清理前后的绝对路径确认；
- 生成产物及 SHA256；
- 已知限制；
- 未执行内容。

不能预填尚未发生的 PASS、测试数量、哈希、提交或推送结果。

---

## 五、TDD 强制流程

如环境提供 TDD skill，先完整读取它及其直接引用的测试、mocking、deep-module、interface-design 和 refactoring 指南。

采用纵向 tracer-bullet 流程：

1. 一个公共行为测试；
2. 运行并保存真实 RED；
3. 仅实现使该测试转绿的最小代码；
4. 运行并保存 GREEN；
5. 再开始下一个行为；
6. 所有行为转绿后才能重构；
7. 每次重构后重新测试。

禁止：

- 一次写完全部测试再一次写完全部实现；
- 只测私有函数；
- mock 自己的生产模块；
- 通过测试代码复制生产算法生成 expected；
- 为了转绿而放宽模型、删除断言或隐藏异常；
- 使用 `skip`、`skipif`、`xfail`、`noqa` 或 `type: ignore` 回避问题。

允许 mock 的边界仅限：

- 时间提供器；
- 明确的故障注入；
- 必要的系统边界。

主要验收测试必须经过真实文件系统和公共 API。

---

## 六、保护内容与哈希

### 6.1 核心保护哈希

必须直接重新计算：

- V1.3 ZIP  
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest  
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- audio inventory  
  `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context  
  `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- inventory summary  
  `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight  
  `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup  
  `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

### 6.2 ESS 保护哈希

- WAV  
  `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- metadata  
  `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- raw float32  
  `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

### 6.3 DEV-04.01R2 processing 保护哈希

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

### 6.4 DEV-04.02 QC 保护哈希

- metrics  
  `627ad7791b284b038e32beadb30a9603242d3b68f8fd0a466e2a9b7d606e4c0f`
- metrics sidecar  
  `8702aa02ee3337f9bdd9b192c8b8a78657bd9c93674f7c623db5a9e17a43047b`
- receipt  
  `8a72666b84179d708128e9b06eff66cb94d9819ec00d708e268a926f26b6754d`
- receipt sidecar  
  `f07e31fdb3c9a903b32e06048599d70c9f135d9265c2512b5c27e3a48d09b9f8`
- metadata  
  `7c11de246773d89d481a4f575b3a9efdfccae4102fdae4b30c366a9076b961d2`

### 6.5 DEV-04.03R repeatability 保护哈希

- metrics  
  `730872025244fb847b6ed9937865017b9563cb030865fb8bac193ea0cd2928b3`
- metrics sidecar  
  `2581bdb2b036e87035e5f0da5e45c93d173b4e75d84eb71b4279b6a76853a6c8`
- receipt  
  `916b67b54bc1f4ec59176ce57a6160d6de0c7a8c68c902a4597283d5f5a27f60`
- receipt sidecar  
  `99dda95fa7705b43bab13328b4491166b8aebe426433f421c02aee07a0444a98`
- metadata  
  `474e96ddf753bc07ac7189ed380173c6ecbd7af5a69a42600b7e1fc095aa3d6d`

任何现有保护哈希改变时：

- 立即停止；
- 不接受新的旧功能 golden；
- 不提交、不推送；
- 报告发生变化的文件、前后哈希和最小原因。

新 DEV-04.04 产物预计产生新哈希；不得预先编造。必须通过两个独立根逐字节一致后，才可将实际值固化为新回归 golden。

---

## 七、Condition plan 契约

新增一个独立于正式 `ProtocolConfig` 执行状态的 strict development condition plan。

建议文件：

`tests/fixtures/protocol/stage1_single_bridge_conditions.development.yaml`

建议模型与加载器：

- `DevelopmentConditionPlan`
- `DevelopmentConditionDefinition`
- `ResolvedConditionBinding`
- `LoadedDevelopmentConditionPlan`
- `load_development_condition_plan(...)`

可根据现有架构调整文件名，但公共语义必须保持。

### 7.1 Condition plan 必填边界

必须包含或通过加载器派生并绑定：

- schema version；
- condition plan ID；
- `usage_scope = development_fixture`；
- Stage 1 源协议仓库相对路径；
- 源协议 raw SHA256；
- 源协议 normalized SHA256；
- device manifest SHA256；
- `experiment_stage = 1`；
- `protocol_execution_authorized = false`；
- `hardware_io_authorized = false`；
- `formal_eligible = false`；
- `experimental_result = false`；
- 条件定义集合。

至少定义：

1. 全 `BLK`：
   - condition role：`all_blk_reference`
   - selected node：null
   - selected module：null
2. 单桥候选：
   - condition role：`single_bridge_candidate`
   - 例如 selected node：`N1`
   - selected module：`B40`

不得永久硬编码 N1 或 B40 到生产算法；它们只是 fixture 数据。生产逻辑必须从 condition plan、protocol 和 manifest 读取。

### 7.2 解析要求

加载器必须：

1. 逐字节读取 condition plan。
2. 保存原始字节、规范化字节、仓库相对路径和两个 SHA256。
3. 验证源协议确实是当前 bundle 中已验证的 Stage 1 协议。
4. 验证源协议：
   - `experiment_stage = 1`
   - `execution_ready = false`
   - `run_mode = formal`
   - `max_active_bridges = 1`
   - TX near speaker
   - RX near microphone
   - TX/RX far 均 closed
   - unselected nodes 为 BLK
5. 验证节点来自 manifest。
6. 验证模块来自 manifest 和协议 allowed modules/state definitions。
7. 将每个条件解析为完整节点状态表。
8. 全 `BLK` 条件必须所有 manifest 节点均为 BLK。
9. 单桥条件必须恰好一个节点非 BLK，其他节点全部 BLK。
10. 必须恰好一个 `all_blk_reference` 条件。
11. condition ID、节点和状态不得重复。
12. 未知/extra 字段、路径逃逸、非有限数值和隐式类型转换必须拒绝。
13. plan 不得包含 threshold、decision、waveform、IR、频谱或任意输出路径。

Condition plan 表示开发夹具条件绑定，不表示正式协议已执行。

---

## 八、Condition-aware synthetic capture

实现最小、向后兼容的 condition-aware virtual capture 路径。

允许采用：

- 版本化扩展现有 virtual-capture 模型；
- 或增加窄的新公共 API。

必须满足以下结果，不强制内部类名。

### 8.1 向后兼容

现有未带 condition plan 的：

- virtual capture；
- processing；
- QC；
- repeatability；
- CLI；
- Schema；
- golden hashes

必须保持字节级兼容。

不得给旧 receipt 自动增加 null 字段。

如需要新版本模型，应使用明确的版本化模型或严格 union/discriminator，不得让旧模型宽松接受任意新字段。

### 8.2 新 condition-aware 场景

新增一个共享的 condition-aware development scenario fixture，例如：

`tests/fixtures/audio/conditioned_virtual_duplex_development.yaml`

它必须：

- condition-neutral；
- 不在场景文件中硬编码 N1/B40；
- 使用 development-only backend；
- 禁止真实硬件；
- 不允许任意 waveform、IR 或传递函数；
- 由 condition plan 的 condition ID 决定节点状态；
- 由 manifest 和 synthetic config 决定透明的合成响应；
- 保留 block-wise、跨 block 状态；
- 使用线性、非循环卷积；
- tail 长度必须覆盖由 manifest 派生的最大 IR 延迟；
- 输出、输入保持 channel-first 1×1；
- 只生成 float32 WAV；
- 所有内部处理必须 finite。

建议复用并深化现有 synthetic generator：

- 抽取“由 manifest + SyntheticConfig + 完整 NodeState 构造 IR”的纯函数；
- 现有 `generate_synthetic_arrays()` 调用同一函数；
- condition-aware virtual backend 也调用同一函数；
- 重构前后现有 synthetic generator 输出字节和测试必须不变。

为避免将随机漂移解释为候选效应，新增专用 development synthetic fixture，建议：

`tests/fixtures/synthetic/stage1_conditioned_development.yaml`

其中：

- noise = 0；
- session drift = 0；
- reassembly drift = 0；
- 仍明确标记 synthetic/development；
- 其他传播公式来自现有透明模型；
- 这些值只是确定性软件夹具，不是实验参数建议。

### 8.3 Condition-aware receipt

新 capture receipt 必须额外绑定：

- condition plan ID；
- condition plan reference；
- condition plan raw/normalized SHA256；
- source protocol reference/raw/normalized SHA256；
- condition ID；
- condition role；
- 完整 resolved node states；
- resolved node-state canonical SHA256；
- condition binding performed = true；
- protocol condition binding performed = true；
- protocol execution performed = false；
- synthetic response formula ID/version；
- synthetic IR raw SHA256；
- manifest-derived node delays；
- manifest/module-derived node weights；
- scenario provenance；
- bundle、ESS 和全部现有 provenance；
- 全部真实硬件/calibration/formal/experimental flags 为 false。

写入 `MeasurementRunRecord.node_states` 的内容必须与 receipt 的 resolved node states 完全一致。

调用者只能提供已加载 condition plan 和 condition ID，不得提交 NodeState 映射、权重、延迟、IR 或数组。

---

## 九、Condition-aware processing、QC 与 repeatability

condition-aware capture 必须能继续使用处理链。

要求：

1. processing 验证完整 capture receipt、condition plan、run record 和所有哈希。
2. QC 验证 condition-aware processing 来源。
3. repeatability 验证所有成员：
   - 属于同一 session；
   - 属于同一 reassembly；
   - condition ID 相同；
   - condition role 相同；
   - resolved node states 相同；
   - condition plan provenance 相同；
   - scenario、bundle、ESS、processing、QC 兼容；
   - measurement order 连续；
   - source run 不重复。
4. condition-aware repeatability receipt 必须绑定 condition provenance。
5. 现有 repeatability 数学和 `ProvisionalRepeatabilityMetrics` 不得改变。
6. 旧 DEV-04.03R receipt、algorithm、hash 和验证行为不得改变。
7. 新 condition-aware receipt 如需新 schema version，必须明确版本化；repeatability 数学 algorithm version 不得因只增加 provenance 而伪装成数学改变。
8. source repeatability receipt 在自身层级仍保持：
   - no baseline；
   - no threshold；
   - no drift decision。
9. baseline assignment 只能发生在新的 baseline-difference 层。

---

## 十、Baseline-difference 公共接口

提供窄公共接口，建议：

- `compute_provisional_baseline_difference(...)`
- `publish_provisional_baseline_difference(...)`
- `validate_provisional_baseline_difference(...)`

具体名称可按现有风格调整。

公共 publisher/validator 允许接受：

- `ImmutableSessionStore`
- `LoadedBundle`
- 已加载的 condition-aware scenario
- 已加载的 development condition plan
- ESS artifact root
- session ID
- comparison ID
- 两个 repeatability source identity
- 每个 source 的 repeat-set ID 和成员 identity
- publisher 的可注入 aware clock

不得接受：

- baseline role；
- condition ID；
- reassembly ID；
- node-state map；
- waveform；
- IR；
- complex spectrum；
- NPZ；
- precomputed metrics；
- threshold；
- decision；
- truth label；
- real root；
- 任意输出路径；
- device/channel/Host API/calibration 参数。

baseline/candidate 角色必须从两个已验证 repeatability receipt 的 condition binding 自动派生。即使 CLI 参数名称区分 baseline/candidate，也必须重新验证实际角色，不能相信参数名称。

### 10.1 Source 约束

两个 source 必须：

- 位于同一个 synthetic session；
- 使用同一 V1.3 manifest；
- 使用同一 Stage 1 protocol；
- 使用同一 condition plan；
- 使用同一 bundle、audio、analysis、synthetic config 和 ESS；
- 使用相同 sample rate、FFT 长度、frequency axis 和 analysis mask；
- 使用相同 processing/QC 数学版本；
- 分别为两个不同 reassembly；
- 不共享任何 source run；
- 每组至少两个成员；
- 各自已有完整、可验证的 condition-aware repeatability evidence；
- 一个且仅一个是 `all_blk_reference`；
- 另一个且仅一个是 `single_bridge_candidate`。

必须拒绝：

- 两个 baseline；
- 两个 candidate；
- baseline 非全 BLK；
- candidate 不止一个非 BLK；
- candidate 实际也是全 BLK；
- 同一个 repeat set；
- 同一个 reassembly；
- 成员交叉；
- condition plan/manifest/protocol/scenario/config 不一致；
- source artifact 缺失、篡改或版本不兼容。

所有拒绝必须发生在创建 comparison parent、lock 或 staging 前。

---

## 十一、基线差分数学

新增纯、确定性 float64 数学内核。不得读写文件，不得读取全局配置，不得调用硬件 API。

### 11.1 输入来源

只能使用已经通过完整验证的 source processing arrays。

每个 condition 内：

- 按规范 measurement order 排序；
- 每个成员等权；
- 分别计算 baseline 和 candidate 的算术均值；
- 不做平滑；
- 不做归一化学习；
- 不丢弃成员；
- 不执行异常值剔除。

同时处理：

- raw complex transfer；
- aligned complex transfer；
- raw IR；
- aligned IR。

复传递函数由已保存的 real/imag 数组重建，不得从 dB/phase 反推。

### 11.2 必须保存的数组

建议生成 deterministic channel-first NPZ，至少包含：

- `frequency_hz`
- `analysis_band_mask`

对 `raw` 和 `aligned` 两种 representation 分别保存：

- baseline mean transfer real
- baseline mean transfer imag
- candidate mean transfer real
- candidate mean transfer imag
- complex additive difference real
- complex additive difference imag
- complex ratio real
- complex ratio imag
- ratio valid mask
- baseline magnitude dB
- candidate magnitude dB
- magnitude difference dB
- wrapped phase difference rad
- unwrapped phase difference rad
- phase valid mask

对 IR 分别保存：

- baseline mean raw IR
- candidate mean raw IR
- raw IR difference
- baseline mean aligned IR
- candidate mean aligned IR
- aligned IR difference

所有浮点数组必须是 canonical float64；mask 必须是 bool。禁止 complex dtype 直接写入持久化 NPZ。

### 11.3 明确公式

对每种 transfer representation：

- `B(f)`：baseline 成员复传递函数算术均值
- `C(f)`：candidate 成员复传递函数算术均值
- additive difference：  
  `D(f) = C(f) - B(f)`
- ratio：  
  `Q(f) = C(f) / B(f)`，仅在 baseline denominator 有效处计算
- magnitude difference：  
  `20 log10(max(|C|, tiny)) - 20 log10(max(|B|, tiny))`
- wrapped phase difference：  
  `angle(C * conjugate(B))`
- unwrapped phase difference：
  - 仅对连续有效频段分别 unwrap；
  - 不得跨无效 gap unwrap；
  - 无效位置持久化为 0；
  - 必须同时保存 validity mask。

division floor 必须是数值稳定性规则，例如从 baseline 频谱、float64 epsilon 和样本/频点数量确定性派生。它不是实验 decision threshold。

必须在 receipt 中保存：

- denominator floor 公式 ID；
- 实际 floor；
- valid/invalid bin 数；
- invalid-bin 输出为零的策略；
- phase contiguous-segment unwrap 规则。

禁止 NaN、Inf 或使用任意固定经验阈值。

### 11.4 Continuous metrics

分别对 raw/aligned representation 计算并保存：

- analysis-band valid bin count/fraction；
- complex additive difference symmetric relative L2；
- magnitude difference RMS dB；
- magnitude difference maximum absolute dB；
- phase difference RMS rad；
- phase difference maximum absolute rad；
- phase defined count/fraction。

对 raw/aligned IR 计算：

- symmetric NRMSE；
- difference L2；
- difference absolute peak；
- difference peak index。

所有零分母必须返回：

- value = null；
- 对应明确 status/reason。

不得抛出原始 `ZeroDivisionError`。

这些只是连续描述指标，不是 effect size 的正式判决，不得输出 significant/not significant。

---

## 十二、独立数学 Oracle

必须增加不调用生产 expected 生成逻辑的手算测试。

至少包含：

1. 一个简单复数例：
   - baseline 与 candidate 数组由测试硬编码；
   - 人工给出 complex difference；
   - 人工给出 ratio；
   - 人工给出 magnitude dB difference；
   - 人工给出 phase difference。
2. 一个 baseline 零频点例：
   - 证明该频点 mask=false；
   - ratio/phase 输出为 0；
   - 其他有效频点仍正常计算；
   - 无 NaN/Inf。
3. 一个存在 valid-gap 的 phase 例：
   - 证明 unwrap 不跨无效 gap。
4. 一个 IR 例：
   - 手工核对 mean、difference、peak index 和 symmetric NRMSE。
5. 成员输入逆序后输出逐字节或逐元素一致。
6. 非有限输入、shape/dtype/frequency/mask 不匹配被拒绝。

expected 必须硬编码或通过独立简单算术推导，不能调用生产函数生成。

---

## 十三、新状态契约

新的 baseline-difference receipt、record 和 metadata 必须共享一个 strict、typed 状态构造来源，至少包含：

- `evaluation_status = provisional_baseline_difference_metrics_only`
- `decision_status = not_evaluated`
- `baseline_comparison_decision = not_evaluated`
- `protocol_condition_binding_performed = true`
- `protocol_execution_performed = false`
- `baseline_assigned = true`
- `baseline_role = all_blk_reference`
- `baseline_selection_status = selected_from_verified_all_blk_condition`
- `baseline_difference_computed = true`
- `thresholds_applied = false`
- `qc_threshold = null`
- `effect_threshold = null`
- `drift_threshold = null`
- `classification_pass_threshold = null`
- `drift_evaluated = false`
- `drift_decision = not_evaluated`
- `smoothing_applied = false`
- `feature_extraction_performed = false`
- `classification_performed = false`
- `cross_validation_performed = false`
- `hardware_io_performed = false`
- `playback_performed = false`
- `recording_performed = false`
- `hardware_ready = false`
- `calibration_applied = false`
- `absolute_spl_calibrated = false`
- `formal_eligible = false`
- `experimental_result = false`

receipt、record、metadata 中对应字段不得分歧。

不要修改 DEV-04.03R `RepeatabilityStateFields` 的 no-baseline 状态；source repeatability 和新的 baseline-difference 是两个不同语义层。

---

## 十四、AnalysisConfig 门禁

baseline-difference publisher 和 validator 都必须在任何写盘前验证当前 AnalysisConfig：

- active model 与加载时 normalized bytes/hash 完全一致；
- smoothing disabled；
- `baseline_selection_rule is None`；
- features is null；
- normalization is null；
- cross-validation strategy is null；
- 所有 decision gates 均为 null。

本步骤的全 BLK 基线由经过验证的 Stage 1 condition plan 唯一派生，不是来自 `AnalysisConfig.baseline_selection_rule`。

任一字段不满足时：

- `published=false`；
- comparison target 不存在；
- event 不增加；
- session tree hash 不变；
- real root 不存在。

必须为每个 decision gate、baseline rule、smoothing、features、normalization 和 cross-validation 增加公共接口负例。

---

## 十五、不可变存储

建议路径：

`session_<id>/processed/baseline_differences/comparison_<comparison_id>/`

最终路径必须从 synthetic session root 和 safe comparison ID 推导，不能由调用者传入。

建议 exact envelope：

1. `condition_binding.json`
2. `condition_binding.sha256`
3. `baseline_difference_arrays.npz`
4. `baseline_difference_arrays.npz.sha256`
5. `baseline_difference_metrics.json`
6. `baseline_difference_metrics.sha256`
7. `baseline_difference_receipt.json`
8. `baseline_difference_receipt.sha256`
9. `baseline_difference_metadata.json`
10. `baseline_difference_record.json`
11. `BASELINE_DIFFERENCE_COMPLETE`

完成标记固定为：

`b"complete\n"`

要求：

- create-only；
- 同文件系统 staging；
- 独占 lock；
- 原子 rename；
- 并发发布只有一个成功；
- 失败 staging 精确清理；
- 不覆盖已有 comparison；
- artifact set 必须 exact；
- sidecar 必须逐字节规范；
- JSON 必须 canonical；
- NPZ 必须 deterministic；
- 路径必须 containment-safe；
- validator 只读，绝不修复或写回。

成功发布后追加唯一 canonical 事件：

`baseline_difference_created`

事件至少绑定：

- schema version；
- sequence；
- session ID；
- comparison ID；
- baseline reassembly/repeat-set ID；
- candidate reassembly/repeat-set ID；
- condition binding hash；
- arrays hash；
- metrics hash；
- receipt hash；
- record hash；
- normalized baseline/candidate member-list hash；
- created_at。

事件仍只是项目内部完整性和审计关联，不是数字签名、外部 witness 或可信时间戳。

如 artifact 已完成但事件追加失败：

- 报错必须为 `published=true`；
- 不删除已发布目录；
- 不声称整个操作成功。

---

## 十六、Receipt 与 provenance

baseline-difference receipt 至少绑定：

- schema/algorithm ID 和 version；
- session/comparison identity；
- baseline/candidate reassembly；
- baseline/candidate repeat-set identity；
- 两组规范化成员列表及 SHA256；
- 两个 source repeatability metrics/receipt SHA256；
- 每个成员的 capture/processing/QC/repeatability provenance；
- condition plan reference/raw/normalized SHA256；
- Stage 1 protocol reference/raw/normalized SHA256；
- device manifest SHA256；
- bundle content SHA256；
- audio/analysis/synthetic config reference/raw/normalized SHA256；
- scenario reference/raw/normalized SHA256；
- ESS artifact ID/WAV/metadata/raw SHA256；
- sample rate；
- FFT/frequency/IR dimensions；
- analysis band mask SHA256；
- baseline/candidate condition ID；
- baseline/candidate condition role；
- 完整 resolved node-state maps 及 canonical SHA256；
- baseline/candidate non-BLK 节点计数；
- 公式 IDs；
- 数值 denominator floor；
- 输出 arrays、metrics SHA256；
- 全部状态和安全标志。

所有路径引用必须为安全仓库相对路径。

所有模型必须：

- strict；
- extra forbid；
- allow_inf_nan=false；
- 非法 `.`、`..` ID 拒绝；
- lowercase SHA256 pattern；
- aware datetime；
- 内部 count/shape/hash/status 自洽。

---

## 十七、CLI

新增：

- `baseline-difference-compute`
- `baseline-difference-validate`

condition-aware capture/process/QC/repeatability 可通过：

- 新的窄命令；
- 或给现有 synthetic-only 命令增加成对出现的 condition-plan 参数。

无论选择哪种方式：

- 原有无 condition 参数命令行为和输出必须保持；
- 不增加任何真实音频权限；
- downstream validator 应从 source receipt 派生 condition ID，避免调用者重复声明事实。

baseline-difference CLI 至少接受：

- 标准 bundle 参数；
- synthetic root；
- session ID；
- comparison ID；
- condition plan；
- condition-aware scenario；
- ESS artifact root；
- baseline repeat-set ID 和成员列表；
- candidate repeat-set ID 和成员列表。

CLI 不得接受：

- condition role；
- baseline role；
- condition ID；
- reassembly ID；
- node states；
- threshold；
- decision；
- waveform/IR/NPZ；
- real root；
- output path；
- hardware/device/channel/calibration 参数。

输出结构化字段必须来自已发布或已验证 receipt，包括：

- comparison path；
- arrays/metrics/receipt SHA256；
- baseline condition ID；
- candidate condition ID；
- baseline/candidate reassembly；
- member counts；
- analysis bin/valid bin 数；
- raw/aligned continuous metrics；
- baseline selection status；
- baseline difference computed；
- decision status；
- thresholds applied；
- hardware/formal/experimental flags；
- safety marker。

输出安全标记至少包括：

- `SYNTHETIC_ONLY`
- `PROVISIONAL_BASELINE_DIFFERENCE_METRICS_ONLY`
- `PROTOCOL_CONDITION_BINDING_ONLY`
- `BASELINE_SELECTED_FROM_VERIFIED_ALL_BLK_CONDITION`
- `DECISION_NOT_EVALUATED`
- `THRESHOLDS_NOT_APPLIED`
- `NO_HARDWARE_AUDIO_IO_PERFORMED`
- `NOT_AN_EXPERIMENTAL_RESULT`

CLI 的 `PASS` 只表示 compute/validate 软件操作成功。

---

## 十八、Schema

为新增 strict 公共模型导出 Schema。

至少覆盖：

- development condition plan；
- condition-aware capture receipt；
- condition-aware repeatability receipt（若新增版本）；
- baseline-difference metrics；
- baseline-difference receipt。

不要预设最终生成 Schema 数量。实际数量必须由 registry 导出结果决定。

要求：

- 现有 22 个 generated Schema 在未明确版本化的情况下保持内容；
- 新 Schema 加入 registry；
- export 后 check 必须通过；
- Schema 总文件数必须等于实际 registry 输出加现有非生成文件；
- 报告准确列出新增/变化 Schema；
- 旧 Schema 若发生非必要变化，停止并调查。

---

## 十九、测试矩阵

### 19.1 Condition plan

覆盖：

- nominal all-BLK 和 N1+B40；
- 完整 node-state resolution；
- manifest/protocol 来源哈希；
- 未知节点；
- 未知模块；
- 非 Stage 1；
- 错误边界；
- 多个 baseline；
- 无 baseline；
- baseline 非全 BLK；
- candidate 零个或多个非 BLK；
- duplicated IDs；
- source path escape；
- extra 字段；
- 阈值/任意数组字段拒绝。

### 19.2 Condition-aware capture

覆盖：

- all-BLK run record 全部 BLK；
- candidate 恰好一个 B40；
- receipt 与 record 状态逐字段一致；
- baseline/candidate 响应不同；
- 差异来自 manifest/module 公式；
- 修改 manifest 节点位置会改变派生延迟，不修改代码；
- 修改 fixture condition 会改变 resolved state；
- tail 不足在发布前拒绝；
- condition plan/hash/source protocol 篡改拒绝；
- 所有硬件标志 false；
- legacy capture golden 完全不变。

### 19.3 Processing/QC/repeatability

覆盖：

- 两个 condition 分别形成完整链；
- condition 混入同一 repeatability set 被拒绝；
- source condition receipt 篡改被拒绝；
- member 逆序规范化；
- 同 condition 连续 measurement order；
- legacy processing/QC/repeatability golden 不变。

### 19.4 数学内核

覆盖第十二节所有独立 Oracle，并增加：

- raw/aligned 结果分离；
- valid counts/fractions；
- symmetric zero denominator；
- unequal member count；
- member identity 重复；
- frequency/mask 不一致；
- all numeric finite；
- phase gap segmentation；
- deterministic arrays。

### 19.5 Persistence

覆盖：

- exact 11-file envelope；
- sidecar LF/CRLF/trailing whitespace/extra newline 攻击；
- completion marker 攻击；
- missing/extra file；
- metadata/record/receipt/state/hash 攻击；
- condition binding 攻击；
- event 缺失、重复和 hash/time/identity 攻击；
- composite identity；
- duplicate create-only；
- concurrent publication；
- staging cleanup；
- append-event failure `published=true`；
- validator 失败前后 tree hash 相同；
- 恢复原始字节后验证再次 PASS。

### 19.6 Authority boundary

每个下列注入必须单独测试写盘前拒绝：

- non-null baseline selection rule；
- non-null QC threshold；
- non-null effect threshold；
- non-null drift threshold；
- non-null classification threshold；
- smoothing enabled；
- features non-null；
- normalization non-null；
- cross-validation strategy non-null；
- arbitrary waveform/IR/NPZ 参数；
- arbitrary output path；
- real root；
- baseline/candidate role伪造。

### 19.7 CLI

覆盖：

- compute；
- validate；
- 两条命令的结构化状态从 receipt 读取；
- forbidden 参数不存在；
- source 角色交换仍由 receipt 重新识别或明确拒绝；
- unsafe ID；
- missing source；
- 不连接硬件。

---

## 二十、双根确定性演示

在两个预先确认不存在的短临时根完成完整软件链。

每个根包含：

1. 同一个 synthetic session；
2. 两个不同 reassembly：
   - all-BLK
   - N1+B40
3. 每个 reassembly 三个 condition-aware captures；
4. 每个 capture：
   - processing
   - provisional QC
5. 每个 condition 一个三成员 repeatability set；
6. 一个 baseline-difference comparison；
7. publish 后立即 validate。

第二个根：

- baseline 成员输入顺序反转；
- candidate 成员输入顺序反转；
- comparison source 参数顺序如公共接口允许则交换；
- 最终规范化结果必须一致。

要求比较：

- condition binding；
- arrays；
- arrays sidecar；
- metrics；
- metrics sidecar；
- receipt；
- receipt sidecar；
- metadata。

上述 payload 必须逐字节一致并记录实际 SHA256。

还必须确认：

- baseline resolved states 全 BLK；
- candidate 恰好 N1+B40；
- baseline/candidate 分别三成员；
- baseline difference 非零只作为 synthetic fixture 行为；
- raw/aligned 数组 finite；
- real roots 均不存在；
- 无播放、录音、设备枚举或 Stream；
- 所有临时根在明确 containment 检查后精确清理；
- 清理后 `Test-Path=False`。

如果两个根不一致：

- 停止；
- 不接受不稳定 golden；
- 不提交、不推送。

---

## 二十一、文件建议

可以根据现有架构调整，但预计会涉及：

新增：

- `src/acoustic_ladder/audio/condition_plan_models.py`
- `src/acoustic_ladder/audio/condition_plan.py`
- `src/acoustic_ladder/audio/baseline_difference.py`
- `src/acoustic_ladder/audio/baseline_difference_models.py`
- `src/acoustic_ladder/audio/baseline_difference_persistence.py`
- condition-aware development fixtures
- `tests/dev04/test_condition_plan.py`
- `tests/dev04/test_baseline_difference.py`
- `tests/dev04/test_baseline_difference_persistence.py`
- 新生成 Schema
- `docs/architecture/baseline-difference.md`
- `docs/prompts/DEV-04.04.md`
- `docs/reports/DEV-04.04.md`

可能修改：

- synthetic IR 构造模块；
- virtual capture models/engine/persistence；
- processing/QC/repeatability 的版本化来源验证；
- storage；
- CLI；
- Schema registry；
- README；
- `data/README.md`；
- configuration/storage/repeatability architecture 文档；
- `.gitattributes`；
- `docs/IMPLEMENTATION_LOG.md`。

不得为了凑文件结构创建空模块。

---

## 二十二、质量门禁

完成实现后必须依次运行：

1. 新增目标测试；
2. 原 DEV-04.03R repeatability 测试；
3. 原 DEV-04.02 QC 测试；
4. 原 DEV-04.01R2 processing 测试；
5. DEV-04 全组；
6. 完整 pytest；
7. Ruff format check；
8. Ruff lint；
9. strict mypy；
10. Schema export/check；
11. `git diff --check`；
12. suppression 扫描；
13. U+FFFD 扫描；
14. secret、本机身份和绝对路径扫描；
15. 新增真实音频 API 扫描；
16. tracked media/cache/staging/lock/temp 扫描；
17. 历史保护文件 diff；
18. 全部保护哈希复算；
19. implementation log 旧前缀校验；
20. 双根重放和攻击矩阵。

完整测试不得少于基线 601 项，不得出现 skip、xfail 或类型抑制。

运行测试产生的临时目录必须使用短、明确、预先不存在的路径。删除前必须：

- resolve 为绝对路径；
- 验证位于明确 workspace 或专用临时父目录内；
- 使用 exact literal path；
- 不得使用模糊 glob、`$HOME`、`~` 或仓库根作为递归删除目标。

---

## 二十三、文档与报告

创建：

`docs/reports/DEV-04.04.md`

报告必须包含：

- 目标和禁止范围；
- Git 基线；
- prompt 归档哈希；
- TDD tracer-bullet RED/GREEN 证据；
- condition plan 契约；
- condition-aware capture 的向后兼容策略；
- 数学公式；
- 数值 floor 与有效 mask 语义；
- 版本决定；
- exact artifact layout；
- event 绑定；
- 双根新哈希；
- 全部测试与静态结果；
- 保护哈希；
- 临时根和清理结果；
- 真实失败及修正；
- 已知限制；
- 未执行内容。

README 和架构文档必须明确：

- 正式 Stage 1 协议仍是 draft、`execution_ready=false`；
- condition plan 是 development fixture；
- baseline 由 verified all-BLK condition 唯一派生；
- source repeatability 仍是 no-baseline；
- baseline difference 只在新层计算；
- 没有 threshold/pass-fail/drift decision；
- 没有真实音频硬件操作；
- synthetic 非零差分不是实验结论；
- event 不是可信外部证明。

---

## 二十四、提交与推送

只有以下条件全部满足时才允许提交和推送：

- 全部测试通过；
- 静态门禁通过；
- Schema 一致；
- 双根 payload 逐字节一致；
- 新哈希已真实生成并锁定；
- 全部旧保护哈希不变；
- real root 未创建；
- 无真实音频 API 调用；
- prompt 已归档；
- 日志已按序追加；
- 报告已完成；
- 临时文件已清理；
- 工作区只包含本步骤预期变更；
- 提交前再次确认远端仍停留在基线提交。

提交信息固定为：

`DEV-04.04: add provisional baseline difference evidence`

然后：

1. 正常 commit；
2. 正常 push 到 `origin main`；
3. 禁止 force push；
4. 再次 fetch；
5. 核对：
   - local HEAD
   - origin/main
   - GitHub main ref
6. 三者必须完全一致；
7. 最终工作区必须干净。

如果任何测试、静态检查、哈希、确定性、远端或清理门禁失败：

- 不提交；
- 不推送；
- 不隐藏失败；
- 不自行扩大修复范围；
- 保留可审查的工作区；
- 报告准确阻断原因。

日志在提交前冻结，不要为了在日志中自引用最终 commit SHA 而追加第二个提交；最终 commit SHA 和远端一致性在终端完成报告中给出。

---

## 二十五、最终回复格式

最终只报告真实发生的结果：

- `PASS`、`FAIL` 或 `BLOCKED`
- commit SHA（仅在已成功提交时）
- push 状态
- local/origin/GitHub 一致性
- 工作区状态
- 原测试、新增测试和完整测试数量
- Ruff/mypy/Schema/diff 结果
- 新 deterministic hashes
- 全部保护哈希状态
- condition plan、baseline 和 candidate 摘要
- baseline-difference continuous metrics 摘要
- attack/validator 无写回结果
- real root 是否创建
- 是否发生硬件枚举、播放、录音或 Stream
- 主要创建/修改文件
- 报告路径
- 已知限制
- 明确声明未进入下一阶段

不得把：

- 测试 PASS；
- synthetic 非零差分；
- baseline difference；
- CLI `PASS`

描述为真实声学有效性、显著性、重复性、漂移或实验结论。

完成 DEV-04.04 后停止，不要自行进入特征提取、分类、正式协议执行、真实硬件接入、DEV-05 或其他后续步骤。