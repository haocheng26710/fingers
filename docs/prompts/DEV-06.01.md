# DEV-06.01：计划绑定的离线分析数据集与防泄漏测量矩阵

你现在负责在 Acoustic Ladder 仓库中实施 DEV-06.01。

本步骤必须采用严格 TDD、不可变持久化、完整来源重放和失败关闭原则。完成后立即停止，不得自行进入 DEV-06.02、分类模型、真实硬件接入或正式实验。

---

## 一、目标

将 DEV-05.03R2 已完成并验证的 Stage 1–4 development synthetic execution，转换为统一、可审计、可重放的离线分析数据集和测量矩阵，为后续阶段效应分析、交互分析及解码模型提供可信输入。

本步骤必须：

1. 消费已经完成并验证的 synthetic execution。
2. 从 compiled plan、execution ledger 和 plan-bound capture receipt 自动派生每个测量行的身份与标签。
3. 复用既有 ESS processing、复传递函数、IR 和 provisional QC 数学内核。
4. 建立严格的同组全 BLK 基线。
5. 保存完整频域、时域、基线差分数组和可解释标量特征。
6. 建立禁止数据泄漏的 session/reassembly 分组切分契约。
7. 发布 exact-file、create-only、可逐字节重放验证的分析 envelope。
8. 保持所有结果为 synthetic、development-only、provisional、not-evaluated。
9. 不访问任何真实音频硬件。
10. 不训练模型、不计算分类准确率、不应用正式阈值。

---

## 二、仓库与基线

仓库：

`https://github.com/haocheng26710/fingers.git`

分支：

`main`

本步骤预期起始提交：

`e8edafac3e78f1ddff76818d2c0a3e1031f79a40`

提交标题应为 DEV-05.03R2 对应提交。

开始任何写操作前必须：

1. 定位真实仓库根。
2. 检查项目级 `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`.agents/**`、`.codex/**` 等指令文件。
3. 检查当前分支、工作区、HEAD 和 remote。
4. 普通执行 `git fetch origin main`。
5. 分别读取：
   - local HEAD；
   - `origin/main`；
   - GitHub `refs/heads/main`。
6. 要求三者全部等于上述提交。
7. 要求工作区干净。
8. 要求 remote URL 精确指向上述仓库。

若远程发生变化、工作区不干净、基线不一致或存在未知指令冲突：

- 立即停止；
- 不修改文件；
- 不提交；
- 不推送；
- 如实报告差异。

禁止使用：

- `git reset --hard`
- `git clean`
- `git checkout -- <path>`
- `git restore` 覆盖未知用户改动
- `git rebase`
- `git commit --amend`
- force push
- 改写历史

---

## 三、当前已知事实

必须保留以下事实，不得重新解释：

- 模型版本：Acoustic Ladder V1.3 校准后圆形主管版本。
- 模型已经实际打印。
- 当前设备、耳机、麦克风和实验装置均未连接。
- `hardware_ready=false`。
- device binding 仍为 deferred。
- 不得执行新的设备枚举、Host API 探测、通道选择、播放、录音、Stream、校准、SPL 或电气回环。
- 当前 execution 全部为：
  - `data_origin=synthetic`
  - `run_mode=development`
  - 非正式实验
  - 非正式协议执行
  - 非实验结果
- Stage 2 仍是 proxy-state experiment。
- Stage 3 尚未形成正式交互结论。
- Stage 4 尚未执行分类。
- 当前 AnalysisConfig 中的正式 features、normalization、cross-validation strategy、random seed 和 decision thresholds 仍未确定。
- synthetic fixture 的参数不是正式实验参数或听力安全建议。

当前基线据报告为：

- 完整测试：`882 passed`
- Ruff format：168 files
- strict mypy：66 source files
- generated Schema：40
- Schema 文件总数：41

这些数字必须重新运行后才能写入新报告，不能直接复制为本次结果。

---

## 四、受保护来源与历史证据

不得修改模型包、校准记录、provisional manifest、硬件上下文或历史 golden 的语义。

至少复核并保护：

- V1.3 ZIP SHA256  
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`

- provisional manifest SHA256  
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

- inventory SHA256  
  `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

- capture context SHA256  
  `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`

- summary SHA256  
  `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`

- contextual preflight SHA256  
  `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`

- hardware setup SHA256  
  `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

- ESS WAV SHA256  
  `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`

- ESS metadata SHA256  
  `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`

- ESS raw float32 SHA256  
  `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

必须运行现有 locked/golden selectors，保护：

- ESS；
- processing；
- provisional QC；
- repeatability；
- DEV-04.04 baseline difference；
- protocol planning；
- rehearsal；
- synthetic execution；
- recovery、concurrency、tamper 和 lock cleanup。

新 DEV-06.01 产物应产生新哈希。不得预先编造这些新哈希。

---

## 五、提示词归档与实施日志

### 5.1 提示词归档

在实现源码前创建：

`docs/prompts/DEV-06.01.md`

要求：

1. 从当前任务原始文本或原始 attachment 复制。
2. 优先使用原始字节，不得从渲染后的网页文本手工重构。
3. 保留原始换行、Unicode 和编码。
4. 计算原始来源与目标文件的：
   - byte count；
   - SHA256；
   - `SequenceEqual`。
5. 将提示词归档加入项目既有 binary 属性规则。
6. 不得格式化、自动换行或修改归档提示词。

若无法获得原始提示词字节：

- 停止实施；
- 不用近似文本代替；
- 不提交；
- 不推送；
- 报告阻断原因。

### 5.2 日志冻结

在第一次追加日志前，记录：

- `docs/IMPLEMENTATION_LOG.md` 当前 byte count；
- 当前 SHA256。

该现有内容成为冻结前缀。后续验证必须证明：

- 原前缀逐字节不变；
- 只能在文件末尾追加；
- 不得改写、删除或重新格式化历史条目。

### 5.3 日志格式

每完成一个序列步骤，立即追加真实记录，使用统一格式：

`### DEV-06.01-XX — 标题`

每条至少包含：

- 实际状态；
- 实际时间；
- 实际读取的输入；
- 实际执行的命令类别；
- RED 失败表现；
- GREEN 结果；
- 修改的文件；
- 实际测试结果；
- 实际哈希；
- 临时目录及清理结果；
- 已知限制；
- 未执行内容。

禁止：

- 预写尚未运行的测试结果；
- 预写 commit SHA；
- 预写 push 成功；
- 编造命令、文件、时间、测试或哈希；
- 把计划写成已经完成的事实。

---

## 六、固定实施序列

必须使用以下序列号：

- `DEV-06.01-00`：仓库、远程、工作区与项目指令检查
- `DEV-06.01-01`：提示词归档与日志冻结
- `DEV-06.01-02`：分析来源与配置契约 TDD
- `DEV-06.01-03`：plan-bound processing/QC 适配层 TDD
- `DEV-06.01-04`：同组全 BLK 基线与纯数学特征内核 TDD
- `DEV-06.01-05`：344 行测量矩阵与标签派生 TDD
- `DEV-06.01-06`：防泄漏分组切分 TDD
- `DEV-06.01-07`：不可变发布、只读验证与并发边界 TDD
- `DEV-06.01-08`：CLI、Schema、架构文档与用户说明
- `DEV-06.01-09`：双根、篡改、保护哈希和完整门禁
- `DEV-06.01-10`：实施报告、最终日志、提交与条件式推送

不得合并序列号，也不得将一个序列号伪造为多个已完成步骤。

---

## 七、总体架构约束

优先新增独立分析命名空间，例如：

`src/acoustic_ladder/analysis/`

建议职责分离：

- `source_validation.py`：完整 execution、plan 和 capture 来源验证
- `processing_adapter.py`：复用既有 ESS processing/QC 内核
- `measurement_matrix.py`：行派生、基线和矩阵组装
- `feature_models.py`：严格 feature/row/split/receipt 模型
- `feature_kernel.py`：纯确定性数值内核
- `split_planning.py`：session/reassembly 分组切分
- `persistence.py`：不可变发布和只读验证

名称可以根据现有仓库风格调整，但不得：

- 将所有逻辑堆入 CLI；
- 复制一份 ESS 或反卷积算法；
- 在多个模块散布 plan-bound capture 类型分支；
- 修改历史 golden 来迁就新实现；
- 将标签、节点或状态写死在分析源码中。

应优先建立一个经过完整重放后才能创建的内部 typed capability，例如：

`ValidatedSyntheticAnalysisSources`

它应只在当前进程内有效，不能由调用者通过 JSON 或 CLI 自行构造。

---

## 八、分析来源契约

DEV-06.01 只能消费：

1. replay-validated compiled plan；
2. 完整且状态为 complete 的 synthetic execution；
3. 已验证 execution manifest、record、events 和 completion；
4. execution 引用的全部 plan-bound synthetic captures；
5. 已验证 ESS artifact；
6. 已验证 bundle、manifest、protocol、audio、synthetic 和原始 analysis config；
7. 新增的 development-only analysis matrix spec。

发布前必须证明：

- execution 状态为 `complete`；
- 无 `recovery_required`；
- 无 unresolved failed/paused/aborted 状态；
- completion 与全部成功事件一致；
- work-order 数与 plan 完全一致；
- 每个 success event 对应且只对应一个完整 run；
- 每个 capture/run 均与 plan work order 逐字段一致；
- 不存在 missing、extra、duplicate 或 foreign run；
- 不存在残留 transition lock；
- 不存在 staging 或 partial publication；
- 所有来源均为 synthetic/development；
- real root 不存在；
- 没有硬件 I/O 证据。

若存在 DEV-05.03R2 所定义的 stale mutation lock：

- analysis compute 必须拒绝；
- analysis validate 不得清理它；
- 不得自动接管；
- 不得 force unlink；
- 不得通过修改权限绕过；
- 必须保留给人工审计。

---

## 九、公共接口边界

公共 compute/publish 接口可接受：

- project root；
- synthetic root；
- analysis root；
- execution ID；
- analysis ID；
- compiled plan/spec 引用；
- scenario 引用；
- ESS artifact root；
- development analysis spec 引用；
-已加载且验证的 bundle；
- 注入式 aware clock。

不得接受：

- 行数据；
- condition labels；
- NodeState；
- selected nodes；
- stage；
- session/reassembly ordinal；
- measurement order；
- run ID 列表；
- waveform；
- IR；
- transfer function；
- feature vector；
- baseline 数组；
- baseline condition ID；
- fold assignments；
- train/test row IDs；
- truth labels；
-分类结果；
- threshold；
- decision；
- real root；
- device、Host API、channel、gain 或 SPL。

所有这些内容必须从经过验证的 plan、execution 和 capture receipt 自动派生。

为上述禁止字段增加公共签名和 CLI 负例测试，防止未来接口偷偷扩大 authority。

---

## 十、development analysis spec

不得直接把当前 `config/analysis/default.yaml` 中的未知正式选择改成确定值。

应新增独立、明确标记为 development-only 的 analysis matrix spec。它必须：

- 引用现有 analysis config；
- 绑定原始与 normalized SHA256；
- 明确 `data_origin=synthetic`；
- 明确 `run_mode=development`；
- 明确不是正式分析配置；
- 保持 smoothing disabled；
- 不包含任何 decision threshold；
- 不包含 model；
- 不包含 classification pass threshold；
- 不包含随机样本切分；
- 不包含正式实验参数建议。

至少允许配置：

- analysis band；
- feature IDs；
- baseline reference policy；
- split strategies；
- scalar dtype；
- matrix schema version。

本步骤固定支持：

- `leave_one_session_out`
- `leave_one_reassembly_out`

本步骤不支持：

- leave-one-day-out，因为没有可信 day identity；
- random split；
- stratified random split；
- k-fold over individual measurements；
- 数据驱动的 feature selection；
- PCA；
- supervised normalization；
- hyperparameter search。

若 day 不可用，应写：

- `day_group = null`
- `day_group_status = trusted_day_identity_unavailable`

不得从不可信时间戳推断 day。

---

## 十一、plan-bound processing 与 QC 适配

当前 legacy processing/QC 主要服务既有 virtual/conditioned capture。DEV-06.01 必须新增集中式 plan-bound adapter，不得在整个仓库散布类型判断。

要求：

1. 完整验证 execution 后，按 compiled plan 的 global planned ordinal 读取 run。
2. 验证 plan-bound capture receipt 与 run record。
3. 读取已验证的 output reference 和 simulated input WAV。
4. 复用既有 ESS processing 纯数学内核。
5. 复用既有 provisional QC 纯数学内核。
6. 不修改：
   - ESS 数学；
   - FFT 约定；
   - 延迟定义；
   - IR 定义；
   - transfer function 定义；
   - analysis-band mask 规则；
   - legacy receipt；
   - legacy golden。
7. 所有计算使用明确 dtype，核心累计计算优先使用 float64。
8. 禁止静默 smoothing。
9. 禁止覆盖原始 capture。
10. 禁止把 provisional QC 解释为正式 PASS/FAIL。

对于每一行，至少保留：

- source execution ID；
- work-order ID；
- run/capture ID；
- capture receipt SHA256；
- run record SHA256；
- source artifact aggregate SHA256；
- sample rate；
- FFT 长度；
- frequency axis hash；
- analysis-band mask hash；
- processing algorithm/schema version；
- QC algorithm/schema version；
- processing latency；
- correlation；
- provisional QC metrics；
- `qc_decision=not_evaluated`；
- `thresholds_applied=false`。

任何一行处理失败时：

- 整个 analysis publication 失败；
- 不发布部分矩阵；
- 不静默排除该行；
- 不把失败行写成零向量；
- 不用 NaN 掩盖失败；
- 不产生完成标记。

---

## 十二、测量矩阵行契约

完整 development fixture 必须得到恰好：

| Stage | 行数 |
|---|---:|
| Stage 1 | 152 |
| Stage 2 | 32 |
| Stage 3 | 32 |
| Stage 4 | 128 |
| 合计 | 344 |

每个 successful synthetic run 对应且只对应一行。

行顺序必须严格使用 compiled plan 的 global planned ordinal，不得依赖：

- 文件系统枚举顺序；
- 字典插入顺序；
-线程完成顺序；
-路径排序偶然性；
- UUID；
- PID；
-当前时间。

每个 row ID 必须确定性派生，并绑定 source execution、work order 和 global ordinal。

每行至少包含：

- row ID；
- global/stage/session/reassembly/condition/measurement ordinal；
- stage；
- condition ID；
- condition role；
-完整 NodeState map；
- NodeState digest；
- selected node IDs；
- selected module/state IDs；
- loading direction；
- repeat kind；
- session ID；
- reassembly ID；
- source run/capture ID；
-全部来源哈希；
- baseline group ID；
- split group IDs；
- Stage 2 proxy 标记；
- synthetic/development 状态；
- formal/experimental/hardware false 状态。

标签必须从 plan 派生：

- Stage 1：完整节点状态、唯一活动节点和桥状态；
- Stage 2：proxy state 及可选连续标签；不存在时保持 null；
- Stage 3：从两个选中节点的完整状态派生二元状态向量；
- Stage 4：按 plan/manifest 提供的 selected-node 顺序派生四节点状态向量。

禁止在源码中写死：

- N1、N3、N4、N6；
- B28、B32、B40；
- `00`、`11`、`0000` 等字符串作为唯一真值来源；
- 当前节点数量；
- 当前 module 推荐列表。

显示标签可以来自 protocol，但数值状态必须从经过验证的完整 NodeState 派生并互相校验。

---

## 十三、同组全 BLK 基线

基线组必须由以下复合身份定义：

- stage；
- planned session；
- planned reassembly。

每个复合组必须从完整 NodeState 中自动识别唯一全 BLK condition。

不得：

- 依赖 condition ID 字符串；
- 依赖 CLI 参数名；
- 跨 stage 使用基线；
- 跨 session 使用基线；
- 跨 reassembly 使用基线；
- 使用 candidate 数据估计 baseline；
- 使用全局平均基线；
- 使用测试折之外的 reassembly 基线。

每个 candidate row：

- 与同 stage/session/reassembly 的全部合法全 BLK repeats 的确定性算术均值比较。

每个 baseline row：

- 使用 leave-one-repeat-out baseline reference；
- 不能让该行自身参与自己的 reference；
- 若无法形成合法 leave-one-out reference，应失败关闭，不得产生全零伪特征。

完整 fixture 应满足每组具备足够的 baseline repeats。必须使用测试验证实际数量，不得假设。

基线计算必须分别保留：

- raw transfer mean；
- aligned transfer mean；
- raw IR mean；
- aligned IR mean；
- analysis-band valid mask；
- denominator-valid mask；
- reference member row IDs；
- reference aggregate SHA256。

数值稳定 floor 只能用于避免除零，必须由 baseline 数值、dtype epsilon 和维度确定性派生。它不是 effect threshold 或实验判定阈值。

---

## 十四、数组与特征

必须保存完整数组，不能只保存标量特征。

至少保存：

- frequency axis；
- analysis-band mask；
- raw complex transfer；
- aligned complex transfer；
- raw magnitude；
- aligned magnitude；
- raw wrapped phase；
- aligned wrapped phase；
- raw unwrapped phase；
- aligned unwrapped phase；
- raw IR；
- aligned IR；
- baseline raw/aligned complex transfer；
- baseline raw/aligned IR；
- additive complex difference；
-稳定 ratio；
- magnitude difference dB；
- wrapped/unwrapped phase difference；
- raw/aligned IR difference；
- denominator-valid mask；
- feature matrix。

建议使用确定性 NPZ；必须延续项目已有 deterministic NPZ 规则。

无效 frequency bins：

- 数组值使用确定性零值；
- 另存显式 mask；
- 不保存 NaN 或 Infinity；
- 标量无法计算时使用严格的 null + reason 模型；
- synthetic development fixture 中若必填特征为 null，publication 应拒绝。

development feature spec 至少包含以下可解释特征：

1. raw complex additive symmetric relative L2
2. aligned complex additive symmetric relative L2
3. raw magnitude difference RMS dB
4. aligned magnitude difference RMS dB
5. raw magnitude difference maximum absolute dB
6. aligned magnitude difference maximum absolute dB
7. raw phase difference RMS rad
8. aligned phase difference RMS rad
9. raw phase difference maximum absolute rad
10. aligned phase difference maximum absolute rad
11. raw IR difference symmetric NRMSE
12. aligned IR difference symmetric NRMSE
13. raw IR difference absolute peak
14. aligned IR difference absolute peak
15. raw IR difference peak index
16. aligned IR difference peak index

要求：

- feature 列顺序来自 versioned feature schema；
-不依赖 Python set/dict 偶然顺序；
- feature matrix 使用 finite float64；
- 每列记录名称、单位、定义、来源数组、版本；
- 标签、row ordinal、session/reassembly ID 不能混入 feature matrix；
- QC 指标保存在 row metadata，不自动作为分类特征；
- 不执行 PCA；
- 不执行自动特征选择；
- 不执行 normalization fitting；
- 不训练模型。

DEV-06.01 的 `feature_extraction_performed=true` 只表示上述确定性开发特征已经生成，不表示特征有效、物理可分或适合正式模型。

---

## 十五、防泄漏切分契约

切分必须逐 stage 建立。

### 15.1 Leave-one-session-out

每一折：

- 一个完整 session 作为 test；
- 其他 session 作为 train；
- 同一 session 的所有 reassembly、condition 和 repeat 必须处于同一侧。

### 15.2 Leave-one-reassembly-out

group identity 必须是：

`(stage, session_id, reassembly_id)`

每一折：

- 一个完整复合 reassembly group 作为 test；
- 其余 group 作为 train；
- 同一 reassembly 的所有 condition 和连续 repeats 必须处于同一侧。

### 15.3 强制不变量

必须验证：

- train/test row ID 交集为空；
- train/test group ID 交集为空；
- 每行在每个适用 strategy 中恰好进入一次 test；
- 不丢行；
- 不重复行；
- 不跨 stage 混淆标签空间；
- fold 顺序确定；
- row 输入顺序反转不改变规范化结果；
- 不使用 random seed；
- 不按单次 measurement 随机拆分；
- 不使用标签进行 fold 优化；
- baseline reference 仅使用该行自身 group 内的 BLK，不从其他 fold 学习参数。

本步骤只生成 split plan，不进行 fit、predict 或 score。

---

## 十六、不可变分析 envelope

分析产物不得写入已完成 execution envelope 内部，以免破坏 DEV-05 的 exact-file 验证。

建议独立位置：

`<synthetic-root>/analyses/analysis_<analysis-id>/`

最终 envelope 固定为以下 exact 15 项：

1. `analysis_source_binding.json`
2. `analysis_source_binding.sha256`
3. `measurement_row_index.json`
4. `measurement_row_index.sha256`
5. `feature_schema.json`
6. `feature_schema.sha256`
7. `split_plan.json`
8. `split_plan.sha256`
9. `measurement_matrix.npz`
10. `measurement_matrix.npz.sha256`
11. `analysis_receipt.json`
12. `analysis_receipt.sha256`
13. `analysis_metadata.json`
14. `analysis_record.json`
15. `ANALYSIS_COMPLETE`

如仓库现有命名规范要求小幅调整，可以调整名称，但必须：

- 在实施前通过测试固定；
- 在报告中列出；
- 保持 exact-file envelope；
- 不允许发布后追加文件。

发布必须采用：

- safe identifier；
-目标父目录验证；
-同一文件系统 staging；
- create-only lock；
- no-replace rename；
- completion marker 最后发布；
-失败时不覆盖旧产物；
-不将临时文件提交到仓库。

不得修改已完成 execution ledger 或向其追加“分析完成”事件。分析 receipt 通过哈希引用 execution completion 和 ordered source aggregate。

---

## 十七、receipt 状态

analysis receipt、record 和 metadata 必须从同一个 strict typed state builder 派生，至少包含：

- `data_origin = synthetic`
- `run_mode = development`
- `analysis_status = provisional_measurement_matrix_only`
- `source_execution_complete = true`
- `source_execution_validated = true`
- `measurement_row_count = 344`
- Stage 1–4 row counts
- `rows_excluded = 0`
- `silent_exclusion_performed = false`
- `feature_extraction_performed = true`
- `split_plan_generated = true`
- `model_fit_performed = false`
- `prediction_performed = false`
- `classification_performed = false`
- `interaction_analysis_performed = false`
- `thresholds_applied = false`
- `qc_decision = not_evaluated`
- `analysis_decision = not_evaluated`
- `formal_eligible = false`
- `experimental_result = false`
- `hardware_enumeration_performed = false`
- `hardware_io_performed = false`
- `playback_performed = false`
- `recording_performed = false`
- `stream_opened = false`
- `calibration_performed = false`
- `absolute_spl_verified = false`
- `day_group_status = trusted_day_identity_unavailable`
- `safety_marker = SYNTHETIC_MEASUREMENT_MATRIX_NOT_AN_EXPERIMENTAL_RESULT`

任何 receipt 缺字段、extra 字段、错误 Literal、错误 schema/algorithm version、null/false 被篡改或 canonical bytes 不一致，都必须拒绝。

CLI 的状态必须从已发布或已验证 receipt 读取，不能从调用路径或内存布尔值自行推断。

---

## 十八、发布、恢复与并发

本步骤不需要实现复杂自动恢复状态机，但必须覆盖：

- 两个并发 publisher 最多一个成功；
- loser 不覆盖 winner；
- 已存在完成产物时再次 compute 拒绝；
- partial target 拒绝；
- stale analysis lock 拒绝；
- staging 不被当成完成产物；
- completion marker 缺失时 validate 拒绝；
- marker 存在但文件不完整时拒绝；
- cleanup 失败不得泄漏裸 `OSError`、`PermissionError` 或 `FileExistsError`；
- cleanup 失败不得谎报 publication 成功；
- lock unlink 失败应保留实际 lock 供审计；
-只读 validator 不得清理 lock、staging 或 partial 文件；
-不提供 force cleanup 或 stale-lock takeover。

主体异常与 cleanup 异常同时发生时：

- 原始主体异常必须保留；
- cleanup 事实必须可见；
- `KeyboardInterrupt`、`SystemExit` 等 `BaseException` 不得被吞掉；
-不得用旧内存状态覆盖持久化探测结果。

优先复用 DEV-05.03R2 已验证的错误归一化思想，但不要与 execution mutation lock 共享同一物理 lock 或错误地修改其状态。

---

## 十九、只读验证

提供公共 read-only validator，例如：

- `validate_synthetic_measurement_matrix(...)`

它必须：

1. 不创建目录。
2. 不创建 lock。
3. 不写 staging。
4. 不修复 sidecar。
5. 不重命名文件。
6. 不更新 metadata。
7. 不清理 stale lock。
8. 重新读取并验证全部 source。
9. 重新验证完整 execution。
10. 重新派生全部344行。
11. 重新运行 processing/QC 和 feature kernel。
12. 重新生成 baseline references。
13. 重新生成 split plan。
14. 重新生成 deterministic NPZ 和 canonical JSON。
15. 逐字节比较全部 payload。
16. 验证 exact-file envelope。
17. 验证 completion marker。
18. 返回 receipt 中的状态和实际哈希。

验证前后应记录分析 root 的 tree hash，证明 validator 无写回。

---

## 二十、CLI

建议新增：

- `analysis-matrix-compute`
- `analysis-matrix-validate`

命名可依据现有 CLI 风格微调。

CLI 至少接受：

-既有 bundle 参数；
- synthetic root；
- analysis root；
- execution ID；
- analysis ID；
- compiled plan；
- plan spec；
- scenario；
- ESS artifact root；
- development analysis spec。

CLI 不得接受第九节列出的派生数据。

成功输出至少包含：

- analysis path；
- analysis ID；
- source execution ID；
- source execution completion SHA256；
- row count；
- Stage 1–4 row counts；
- feature count；
- split strategy；
- fold counts；
- source-binding SHA256；
- row-index SHA256；
- feature-schema SHA256；
- split-plan SHA256；
- matrix NPZ SHA256；
- receipt SHA256；
- rows excluded；
- thresholds applied；
- model/classification status；
- hardware I/O status；
- formal eligibility；
- experimental-result status；
- safety marker。

`PASS` 只表示软件 compute/validate 和完整性重放成功，不能输出“实验通过”或“声学有效”。

---

## 二十一、Schema

至少新增并导出严格 Schema：

- development analysis matrix spec；
- analysis source binding；
- measurement row；
- feature column schema；
- split fold/plan；
- analysis receipt。

要求：

- Pydantic strict；
- `extra="forbid"`；
-禁止 NaN/Infinity；
-使用 Literal 固定安全状态；
- canonical JSON；
- schema/algorithm version 显式；
- committed Schema 与运行时 export 一致。

只能机械更新受新增 Schema 数量影响的历史数量断言。不得修改历史 Schema 语义来让测试通过。

---

## 二十二、TDD 要求

必须遵循真实 RED → GREEN → REFACTOR。

### 22.1 首批公共 RED

至少先建立：

1. analysis spec 加载测试；
2. incomplete execution 被拒绝；
3. completed execution 派生行测试；
4.全 BLK 同组 baseline 测试；
5. feature kernel hard-coded oracle；
6. session/reassembly split 零重叠测试；
7. publisher/validator 公共入口不存在或行为缺失的 RED。

RED 必须因目标能力缺失而失败，不能通过故意破坏 unrelated fixture 制造。

### 22.2 数学 oracle

测试内硬编码小型复数 transfer 和 IR，不调用被测函数生成 expected。

人工核对至少包括：

- baseline 算术均值；
- baseline row leave-one-out；
- additive difference；
- stable ratio；
- magnitude dB difference；
- wrapped phase difference；
-连续 valid segment unwrap；
- complex symmetric relative L2；
- IR symmetric NRMSE；
- difference peak/index；
- feature 列顺序；
- invalid denominator mask。

### 22.3 行和标签

覆盖：

-恰好344行；
- Stage counts 为152/32/32/128；
- global ordinal 完整连续；
-无重复 row ID；
-输入枚举反转后结果相同；
- Stage 2 proxy 标记；
- Stage 3 状态向量由 NodeState 派生；
- Stage 4 selected-node 顺序来自 plan；
-标签伪造被拒绝；
-硬编码当前节点列表的测试反例。

### 22.4 分组切分

覆盖：

- leave-one-session-out；
- leave-one-reassembly-out；
- train/test row 零交集；
- train/test group 零交集；
-所有连续 repeats 同侧；
-所有同一 reassembly condition 同侧；
-每行恰好一次作为 test；
-随机拆分入口不存在；
- random seed 不参与本步骤；
-day 不可信时不生成 leave-one-day-out。

### 22.5 持久化与攻击

覆盖：

-双 publisher；
-已存在目标；
- partial target；
- extra/missing file；
- sidecar mismatch；
-非 canonical JSON；
-非 deterministic/篡改 NPZ；
- receipt 篡改；
- row label 篡改；
- feature schema 篡改；
- fold 篡改；
- completion marker 篡改；
- source execution completion 篡改；
- plan/spec/config/source run 篡改；
-混合两个 execution；
-混合 session/reassembly；
-跨 stage baseline；
- foreign run；
- real origin；
- stale execution lock；
- stale analysis lock；
- path traversal；
-symlink/reparse point；
-本机绝对路径泄漏；
- validator 前后 tree hash 相同。

### 22.6 禁止测试抑制

新增和修改的测试中禁止：

- skip；
- xfail；
- pytest warning suppression；
- `# noqa`；
- `# type: ignore`；
-放宽 mypy；
-删除失败测试；
-仅修改 golden 使失败消失。

---

## 二十三、性能与重复验证

完整 Stage 1–4 synthetic execution 已较慢。

要求：

1. 不为每一行重复执行完整 execution validation。
2. 每个公共 compute/validate 调用最多建立一次完整 validated-source capability。
3. capability 建立后，每行仍必须验证其与 capability 中的 work order/capture 对应。
4. 不得将 capability 持久化为可伪造的“已验证”JSON。
5. 不得使用进程间全局缓存跳过验证。
6. 不得牺牲只读 validator 的完整重放。
7. 单元测试使用最小 fixture。
8. 完整344行验收应尽量接入现有 Stage 1–4 双根完成测试，复用其已创建 execution roots，不额外生成第三套完整 execution。
9. 不得使用 skip 或环境变量默认跳过完整验收。

报告中必须分别记录：

-纯数学测试时间；
-目标模块测试时间；
-现有快速回归时间；
-完整344行分析时间；
-完整 suite 时间。

---

## 二十四、双根确定性验收

使用两个预先确认不存在、位于安全 workspace 临时范围内的独立根。

相同输入、相同 aware clock 和相同 analysis ID 下：

1. 分别生成完整 analysis envelope。
2. 每根都必须有344行。
3. 两根 canonical JSON、deterministic NPZ、receipt 和 marker 必须逐字节一致。
4. 每项 payload SHA256 相同。
5. ordered aggregate SHA256 相同。
6. 交换输入枚举顺序后 normalized 输出仍一致。
7. 临时绝对根路径不得进入 payload。
8. 完成验证后解析精确路径。
9. 确认路径位于预期 workspace 临时父目录内。
10. 精确清理两个根并确认不存在。

禁止删除 workspace 根、仓库根、用户目录或通过未验证变量递归删除。

---

## 二十五、文档

至少更新：

- `README.md`
- `data/README.md`
- `docs/architecture/storage-layout.md`
-现有 protocol synthetic execution 文档中的下游关系
-新增分析矩阵架构文档
- `docs/IMPLEMENTATION_LOG.md`
- `docs/reports/DEV-06.01.md`
- `docs/prompts/DEV-06.01.md`

文档必须明确：

- DEV-06.01 消费已完成 execution，不执行 protocol；
-一行对应一个 synthetic run；
-完整 fixture 为344行；
-基线只来自同 stage/session/reassembly 的全 BLK；
- baseline row 使用 leave-one-repeat-out；
-无静默丢行；
-切分按 session/reassembly；
- feature extraction 已执行但仅为 development fixture；
-没有模型、预测、分类或阈值；
-没有真实 QC PASS/FAIL；
-没有物理显著性、可分性或实验结论；
-没有真实音频硬件操作；
- DEV-06.02 未实施。

不得把 synthetic 特征差异描述成实际打印结构有效性的证据。

---

## 二十六、验收门禁

最终至少执行：

1. DEV-06.01 新增测试。
2. plan-bound processing/QC 适配测试。
3. feature oracle 测试。
4. matrix/split 测试。
5. publication/validator 测试。
6. recovery/concurrency/tamper/cleanup 定向测试。
7. DEV-05.03R/R2 全部回归。
8. DEV-05 全部测试。
9. DEV-04 全部测试。
10.配置、manifest 和 Schema 测试。
11.全部 locked/golden selectors。
12.完整 pytest suite。
13. Ruff format check。
14. Ruff lint。
15. strict mypy。
16. generated Schema consistency。
17. `git diff --check`。
18. prompt archive byte/hash 验证。
19. implementation log 冻结前缀验证。
20.秘密、本机路径、U+FFFD、临时文件、真实音频 API 扫描。
21. changed/new tests 的 skip/xfail/noqa/type-ignore 扫描。
22.工作区状态检查。

Windows 下必须使用短、明确且位于 workspace 内的 pytest basetemp，避免历史路径长度问题。失败命令不能算作通过；修复后必须原样重跑相应门禁。

若任一门禁失败：

-最终状态为 FAIL；
-不得提交“通过”报告；
-不得推送；
-保留可审计的实际失败记录；
-停止并向用户报告。

---

## 二十七、报告

创建：

`docs/reports/DEV-06.01.md`

必须记录实际：

-目标和范围；
-起始 commit；
-读取的指令文件；
-提示词 byte count/SHA256；
-日志冻结前缀 byte count/SHA256；
-新增公共 API；
-新增 Schema；
- exact envelope；
-实际 feature schema；
-实际 row counts；
-实际 fold counts；
-基线组数量和成员数量；
-双根哈希；
-保护哈希；
-测试命令和结果；
-静态门禁结果；
-失败与修复过程；
-临时目录和清理；
-修改文件；
-已知限制；
-未实现内容；
-硬件操作均未发生；
- DEV-06.02 未实施。

报告不得预写最终 commit SHA。commit 和 push 结果在最终回复中报告。

---

## 二十八、最终差异审计

提交前必须检查：

- `git status --short`
- `git diff --stat`
- `git diff --check`
-完整 diff
-新增文件列表
-删除文件列表
-历史 protected 文件差异
- prompt 与 log 前缀
-所有临时根均已清理
-没有 WAV、NPZ、测试根、cache、lock、staging 或真实数据误提交
-没有用户目录、桌面路径或个人身份信息进入仓库
-没有修改模型 ZIP、manifest 或校准事实
-没有真实音频 API 调用
-没有分类、模型、阈值或实验结论

只允许与 DEV-06.01 直接相关的更改。

---

## 二十九、提交和推送规则

只有在以下条件全部满足后才允许提交和推送：

-所有功能完成；
-所有验收门禁通过；
-完整 suite 通过；
-报告和日志已经落盘；
-工作区差异仅包含预期文件；
-远程 `main` 仍等于起始基线；
-没有未知用户修改；
-没有真实硬件操作；
-没有未清理临时产物。

提交标题：

`DEV-06.01: add plan-bound synthetic measurement matrices`

要求：

1. 普通 commit。
2. 不 amend。
3. 不 rebase。
4. 不 force push。
5. 推送到：
   - remote：`https://github.com/haocheng26710/fingers.git`
   - branch：`main`
6. 普通 `git push origin main`。
7. 推送后再次 fetch。
8. 验证：
   - local HEAD；
   - `origin/main`；
   - GitHub remote main；
   三者完全一致。
9. 验证工作区干净。

如果推送前远程已变化：

-不 rebase；
-不 merge；
-不 force；
-不推送；
-报告阻断。

如果 push 发生网络中断或结果不确定：

-只读查询远程；
-若远程已存在最终 commit，则按实际成功报告；
-若远程不存在或状态无法证明，不得盲目重复 push；
-不得声称成功；
-停止并报告。

---

## 三十、最终回复格式

成功时以以下内容开头：

`PASS — DEV-06.01 完成`

随后报告：

- commit SHA；
- parent SHA；
- branch/remote；
-普通非 force push 结果；
-local/origin/GitHub 一致性；
-工作区状态；
-完整测试结果；
- DEV-06.01 新增测试结果；
- Stage 1–4 行数；
- feature count；
- fold counts；
-双根确定性结果；
-新分析产物 SHA256；
- prompt SHA256；
- implementation log 冻结前缀结果；
-保护哈希结果；
-主要修改文件；
-已知限制；
-明确说明未访问真实音频硬件；
-明确说明未训练模型、未分类、未应用阈值；
-明确说明 DEV-06.02 未实施。

失败或中断时以以下内容开头：

`FAIL — DEV-06.01 未完成或未推送`

并如实报告：

-失败序列号；
-最后成功步骤；
-失败命令；
-错误信息；
-已产生的文件；
-是否有本地 commit；
-明确说明未推送；
-下一步需要的人工决定。

完成 DEV-06.01 后立即停止，不得自行进入 DEV-06.02、DEV-06.03、真实硬件接入、分类模型、正式阈值或实验执行。