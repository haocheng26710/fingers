# DEV-06.01R：分析 Envelope 时间来源与 Metadata/Record 防篡改闭环

你现在负责在 Acoustic Ladder 仓库中实施 DEV-06.01R。

本步骤是对 DEV-06.01 独立验收发现的不可变证据缺口进行定向修复。只允许修复分析 envelope 的时间来源、metadata/record 哈希绑定和只读重放验证，不得进入 DEV-06.02，不得修改测量矩阵数学、特征、分组切分、真实硬件或分类能力。

完成本步后立即停止。

---

## 一、独立验收发现的缺陷

DEV-06.01 当前实现存在以下阻断问题：

1. `analysis_receipt.json` 没有绑定：
   - `analysis_metadata.json` SHA256；
   - `analysis_record.json` SHA256。
2. metadata 和 record 的 `created_at` 来自运行时 `now()`。
3. validator 先读取已发布的 `analysis_metadata.json`。
4. validator 再把该 metadata 中的 `created_at` 作为 `_payloads(...)` 的预期输入。
5. 因此，如果攻击者同时把 metadata 和 record 的 `created_at` 改成另一个相同、合法、canonical 的 aware datetime：
   - 核心五项 payload 不变；
   - receipt 不变；
   - receipt sidecar 不变；
   - validator 可能重新生成相同的已篡改 metadata/record 并接受。

这违反 DEV-06.01 的明确要求：

- metadata/record 篡改必须拒绝；
- validator 必须完全从验证过的来源重建预期值；
- 被验证文件不能成为自身预期值的 authority。

这不是“哈希不是数字签名”或“没有可信时间戳”的一般限制，而是内部 full replay 的自引用缺陷。

---

## 二、目标

本步骤必须：

1. 用真实公共验证路径复现上述缺陷。
2. 将分析证据时间改为从已验证 source execution completion 确定性派生。
3. 消除 receipt、metadata、record 之间的哈希循环。
4. 使 receipt 单向绑定 metadata 和 record。
5. 使 validator 不再从待验证 metadata/record 读取任何 expected 输入。
6. 保持 exact 15-file envelope。
7. 保持344行、16项特征和24个 grouped folds 的数学结果不变。
8. 保持核心频域、IR、feature matrix 和 split plan 不变。
9. 更新版本、Schema、报告和防篡改测试。
10. 只有全部门禁通过后才允许普通 push。

---

## 三、仓库和基线

仓库：

`https://github.com/haocheng26710/fingers.git`

分支：

`main`

预期起始提交：

`7ec44c2b0904d26627f7c15b0ad021881bda71bc`

预期父提交：

`e8edafac3e78f1ddff76818d2c0a3e1031f79a40`

预期提交标题：

`DEV-06.01: add plan-bound synthetic measurement matrices`

开始任何写操作前必须：

1. 定位真实仓库根。
2. 读取项目中的 `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`.agents/**`、`.codex/**` 等指令文件。
3. 检查工作区必须干净。
4. 检查当前分支为 `main`。
5. 检查 remote URL。
6. 普通执行 `git fetch origin main`。
7. 分别读取：
   - local HEAD；
   - `origin/main`；
   - GitHub remote main。
8. 要求三者均等于 `7ec44c2b0904d26627f7c15b0ad021881bda71bc`。

如有任何不一致：

- 立即停止；
- 不修改文件；
- 不提交；
- 不推送；
- 如实报告。

禁止 reset、clean、rebase、amend、force push 或改写历史。

---

## 四、当前必须保护的 DEV-06.01 结果

当前报告中的以下结构应继续成立：

- Stage 1：152行；
- Stage 2：32行；
- Stage 3：32行；
- Stage 4：128行；
- 总计：344行；
- features：16；
- leave-one-session-out：8 folds；
- leave-one-reassembly-out：16 folds；
- 合计：24 folds；
- exact envelope：15 files；
- rows excluded：0；
- synthetic/development-only；
- model、prediction、classification、threshold 均未执行。

当前稳定核心哈希：

- ordered source aggregate  
  `39640ff09910541ba09f56e08a388ce161602d6dbc867a7eecb850745db96893`

- row index  
  `229c3f96d7976c9a95adbe7847a4f0d88e947f722d5cd63b3fd31f3b548c5d78`

- feature schema  
  `3d7858e931dd8938b9ebc269d0f84a5f3fae1a685cd150e66f083dfd76bd27c1`

- split plan  
  `02e606080c599d6ea3ae5563a6a9a80f6603af87f862e46b6dd50eccb799df1b`

- matrix NPZ  
  `9529e178c2a719ad473137681fc209ef3597f1a538c682dd0e4f5d40d9387a93`

如果本次只修改时间和 envelope 绑定，则以上五项原则上应保持不变。

以下哈希预计会因版本或新增时间来源字段而改变，不得强制保持旧值：

- source binding；
- metadata；
- record；
- receipt；
- receipt sidecar。

任何新哈希必须由实际双根运行生成，不得预先编造。

---

## 五、提示词归档与日志

### 5.1 提示词归档

在源码修改前创建：

`docs/prompts/DEV-06.01R.md`

要求：

- 从当前任务原始 attachment 或原始任务文本逐字节复制；
- 不从渲染后的 Markdown 手工重构；
- 保留编码、Unicode 和换行；
-记录源和目标 byte count；
-记录源和目标 SHA256；
-验证 `SequenceEqual=True`；
-加入现有 binary `.gitattributes` 规则。

若无法取得原始字节，停止且不推送。

### 5.2 日志冻结

在第一次追加前计算：

- `docs/IMPLEMENTATION_LOG.md` 当前 byte count；
-当前完整 SHA256。

同时继续验证历史冻结前缀：

- 202,796-byte 前缀 SHA256  
  `af4412e920ab2204b4e136f828976d47b328e0b18408751aaa625a47bdd54f57`

只能在日志末尾追加，不能修改任何历史字节。

### 5.3 日志格式

使用以下序列：

- `DEV-06.01R-00`：仓库、远程、工作区和指令检查
- `DEV-06.01R-01`：提示词归档与日志冻结
- `DEV-06.01R-02`：metadata/record 双文件篡改 RED
- `DEV-06.01R-03`：确定性 source-completion 时间派生
- `DEV-06.01R-04`：无循环 receipt→metadata/record 哈希绑定
- `DEV-06.01R-05`：只读 validator authority 修复
- `DEV-06.01R-06`：篡改矩阵、双根和版本迁移测试
- `DEV-06.01R-07`：Schema、CLI、文档和完整门禁
- `DEV-06.01R-08`：报告、最终日志、提交和条件式推送

每个步骤完成后立即追加真实记录，不得预写测试、哈希、commit 或 push 结果。

---

## 六、真实 RED 要求

在修改生产代码前，必须建立一个通过公共 API 复现缺陷的测试。

测试必须：

1. 使用真实 `compute_synthetic_measurement_matrix(...)` 发布一个完整 envelope。
2. 保存原始 metadata 和 record bytes。
3. 解析两者。
4. 将二者的 `created_at` 同时改成另一个合法、timezone-aware、canonical 的时间。
5. 不修改：
   -核心五项 payload；
   - receipt；
   - receipt sidecar；
   - completion marker。
6. 写回 canonical metadata 和 record。
7. 调用真实 `validate_synthetic_measurement_matrix(...)`。
8. 在当前 DEV-06.01 基线上证明 validator 错误接受该 envelope。

RED 必须因 validator 接受一致双篡改而失败，不能用 mock validator、直接调用私有比较函数或人工抛异常代替。

为了避免额外生成第三套约1.13 GB矩阵，应优先把该攻击加入现有 Stage 1–4 双根集成测试，在已经生成的分析根上执行。

RED 结果必须写入实施日志。

---

## 七、确定性证据时间

### 7.1 时间来源

分析不可变证据时间必须只从已验证的四个 source execution completion 派生。

建议规则：

`analysis_evidence_time = max(all verified execution completed_at instants)`

规范化要求：

1. 每个 source completion 必须已经通过完整 execution replay。
2. 读取其 typed `completed_at`。
3. 验证 timezone-aware。
4. 转换为 UTC。
5. 使用 UTC instant 比较。
6. 将最大值规范化为 UTC canonical representation。
7. 不保留来源文件中等价但不同的 timezone offset 表示。
8. 派生规则必须有固定 Literal：

`latest_verified_execution_completion_utc`

### 7.2 来源能力

在 `ValidatedAnalysisExecution` 中增加实际验证得到的：

- execution completed time；
- canonical UTC completed time；
- completion SHA256。

不得让调用者提交这些字段。

`ValidatedSyntheticAnalysisSources` 应提供：

-四个规范化 completion times；
-派生后的 analysis evidence time；
- time derivation algorithm/version。

### 7.3 禁止自引用

validator 不得从以下文件读取 expected 时间：

- `analysis_metadata.json`
- `analysis_record.json`
- `analysis_receipt.json`

这些文件中的时间只能被拿来与 source-derived expected 值比较，不能反过来驱动 expected payload。

### 7.4 `now()` authority

持久化内容不得再受 `now()` 控制。

优先选择：

- 从 `compute_synthetic_measurement_matrix` 公共接口移除 `now`；
-更新 CLI 和测试；
-所有 persisted bytes 只依赖 validated sources、analysis spec 和 analysis ID。

如果为了临时兼容保留 `now`：

-它不得进入任何 persisted payload；
-不得进入 receipt、metadata、record 或 sidecar；
-两次传入不同 `now()` 必须得到逐字节一致产物；
-文档必须说明它没有证据 authority。

不要保存无法验证的“实际发布时间”。没有可信时间戳时，应明确保存可重放的 source-derived evidence time，而不是伪装成可信 wall-clock publication time。

---

## 八、无循环哈希绑定

必须消除当前循环：

- metadata/record 保存 receipt SHA；
- receipt 若再保存 metadata/record SHA 会形成循环。

采用单向无循环构造：

1. 验证全部 source。
2. 派生 source completion times。
3. 派生 `analysis_evidence_time`。
4. 生成核心五项 payload：
   - source binding；
   - row index；
   - feature schema；
   - split plan；
   - matrix NPZ。
5. 生成 metadata。
6. 生成 record。
7. 计算 metadata SHA256。
8. 计算 record SHA256。
9. 最后生成 receipt，使其绑定：
   -核心五项哈希；
   - metadata SHA256；
   - record SHA256；
   - ordered source aggregate；
   - source-derived evidence time；
   - time derivation algorithm/version。
10. 生成 receipt sidecar。
11. 最后发布 completion marker。

metadata 和 record 不再保存 `receipt_sha256`。

单向关系必须为：

`validated sources → deterministic time/core/metadata/record → receipt → receipt sidecar`

不得出现：

- metadata 依赖 receipt，同时 receipt 又依赖 metadata；
- record 依赖 receipt，同时 receipt 又依赖 record；
- validator 从 metadata 读取 expected time；
- validator从 record 读取 expected path/status；
- validator从 receipt读取本应由 source决定的状态。

---

## 九、模型和版本

建议版本升级：

- `AnalysisSourceBinding.schema_version = 1.1.0`，如果增加 execution completed time；
- `AnalysisReceipt.schema_version = 1.1.0`；
- `AnalysisReceipt.algorithm_version = 1.1.0`；
- `AnalysisMetadata.schema_version = 1.1.0`；
- `AnalysisRecord.schema_version = 1.1.0`。

metadata 至少包含：

- analysis ID；
- source-derived evidence time；
- time basis；
- ordered source aggregate SHA256；
-全部既有安全状态。

record 至少包含：

- analysis ID；
- analysis relative path；
- source-derived evidence time；
- time basis；
- immutable status；
- ordered source aggregate SHA256；
-全部既有安全状态。

receipt 新增：

- `analysis_metadata_sha256`
- `analysis_record_sha256`
- `analysis_evidence_time`
- `analysis_evidence_time_basis`
-如有需要，time derivation version。

如果 source binding 增加时间，应为每个 execution 保存：

- `execution_completed_at_utc`
- completion SHA256 已存在则继续保留。

旧 `1.0.0` DEV-06.01 envelope 必须：

-明确拒绝；
-要求重新生成；
-不能原地迁移；
-不能修改旧 envelope；
-不能自动补字段。

没有必要改变：

- MeasurementRow schema；
- FeatureColumn schema；
- SplitPlan schema；
- feature algorithm；
- baseline math；
- matrix NPZ 格式。

---

## 十、exact 15-file envelope

必须保持以下15项，不增加第16或17项：

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

metadata 和 record 不单独增加 sidecar；由 receipt 中的新哈希绑定。

继续保持：

- same-filesystem staging；
- create-only lock；
- no-replace rename；
- completion marker 最后发布；
- exact-file validation；
- reparse/symlink rejection；
- cleanup 异常领域化；
- validator 只读。

---

## 十一、validator 修复

`validate_synthetic_measurement_matrix(...)` 必须：

1. 先检查 exact 15-file envelope。
2. 不读取 metadata 中的时间作为 `_payloads` 输入。
3. 不读取 record 中的时间或路径作为 expected 输入。
4. 完整重放四个 source executions。
5. 从 source completions 派生 expected evidence time。
6. 重算全部344行。
7. 重算16项特征。
8. 重算24个 folds。
9. 重算 metadata。
10. 重算 record。
11. 重算 receipt。
12. 重算 receipt sidecar。
13. 与15个实际文件逐字节比较。
14. metadata/record 任一字节变化必须拒绝。
15. 即使二者被一致修改，也必须拒绝。
16. 不写回、不修复、不删除、不清理。

validator 前后必须比较：

-文件名集合；
-每个文件 SHA256；
-tree hash；
- lock/staging 状态。

证明完全无写回。

---

## 十二、强制攻击回归

至少覆盖：

### 12.1 时间篡改

1. 只修改 metadata evidence time。
2. 只修改 record evidence time。
3. 同时将二者改成同一时间。
4. 改成同一瞬间但不同 timezone offset。
5. 改为 naïve datetime。
6. 改为非法时间字符串。
7. 修改 time-basis Literal。
8. metadata 和 record 时间互相不一致。

全部必须拒绝。

### 12.2 状态篡改

分别或同时篡改：

- `formal_eligible`
- `experimental_result`
- `hardware_io_performed`
- `thresholds_applied`
- `classification_performed`
- `analysis_status`
- `immutable_status`
- `analysis_relative_path`
- ordered source aggregate。

全部必须拒绝。

### 12.3 哈希攻击

覆盖：

1. 修改 metadata 但不修改 receipt。
2. 修改 record 但不修改 receipt。
3. 同时修改 metadata/record。
4. 同时修改 metadata/record，并更新 receipt 中的两个哈希。
5. 同时更新 receipt sidecar。
6. 使用旧1.0.0 receipt。
7. 删除新增字段。
8. 添加 extra 字段。
9. 将 metadata hash 与 record hash 交换。

即使攻击者重新计算内部 SHA256，full replay 仍必须因 source-derived expected 不一致而拒绝。

### 12.4 只读性

每个攻击测试必须验证：

- validator 前后 tree hash 相同；
-没有 lock；
-没有 staging；
-没有自动恢复；
-没有文件时间或内容写回。

---

## 十三、保持不变的数学与协议行为

本步骤禁止修改：

- Stage 1–4 work-order 数；
-344行矩阵；
-16项特征；
- baseline group identity；
- baseline leave-one-out；
- ESS processing；
- QC math；
- complex transfer；
- magnitude/phase；
- IR；
- denominator floor；
- feature column order；
- split strategy；
-24 folds；
- train/test group membership；
- row labels；
- NodeState；
- synthetic generator；
- protocol planning/rehearsal/execution；
-真实硬件状态。

对下列文件的修改必须具有直接理由，否则禁止：

- `feature_kernel.py`
- `measurement_identity.py`
- `split_plan.py`
- `measurement_matrix.py`
- `processing_adapter.py`

优先只修改：

- source validation；
- persisted models；
- persistence；
-相关 Schema；
-测试；
-文档；
- CLI 中受 `now` 或版本影响的机械部分。

---

## 十四、TDD 和测试组织

必须执行真实 RED → GREEN → REFACTOR。

建议将快速测试与完整矩阵攻击分离：

### 快速测试

覆盖：

- source completion time 规范化；
-四个时间取最大值；
-不同时区表示转 UTC；
-无 aware datetime 拒绝；
- metadata/record 不含 receipt SHA；
- receipt 含 metadata/record SHA；
-构造顺序无循环；
-旧 Schema 拒绝；
-不同 `now()` 不影响 payload。

### 完整双根测试

复用现有 Stage 1–4 双根测试已经生成的两个完整 envelope：

1. 先验证两个正常 root。
2. 记录正常哈希。
3. 在测试控制的一个 root 上进行攻击。
4. 每次攻击前保存原始 bytes。
5. 每个攻击均通过公共 validator 验证拒绝。
6. 测试可恢复自身 fixture 以继续下一个攻击，但 validator 自身绝不能修复。
7. 不生成第三套完整 execution/matrix。
8. 最后确认另一个未攻击 root 始终不变。

禁止 skip、xfail、noqa、type-ignore 或缩小原完整门禁。

---

## 十五、双根确定性

相同 source executions 和 analysis ID 下：

-不同调用时间不得改变 persisted bytes；
-不同 source 输入顺序不得改变 persisted bytes；
-两个独立根逐字节一致；
- canonical UTC time 一致；
- exact 15 names 一致；
- core NPZ 哈希保持；
- metadata/record/receipt 新哈希在两根一致；
- validator 重放成功；
- tree hash 不变。

必须实际报告：

- evidence time；
-四个 source completion times；
- time basis；
- source binding SHA256；
- metadata SHA256；
- record SHA256；
- receipt SHA256；
- receipt sidecar SHA256；
- unchanged core hashes。

---

## 十六、Schema 与文档

更新：

-相关 analysis Schema；
- Schema registry；
- `README.md`
- `data/README.md`
- `docs/architecture/synthetic-measurement-matrix.md`
- `docs/architecture/storage-layout.md`
- `docs/reports/DEV-06.01R.md`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/prompts/DEV-06.01R.md`

文档必须明确：

- `analysis_evidence_time` 是最新 verified source execution completion time；
-它不是可信 wall-clock publication timestamp；
- receipt 单向绑定 metadata 和 record；
- metadata/record 不再反向绑定 receipt；
- validator 不相信任何已发布 payload 提供的 expected time；
-旧1.0.0 envelope 必须重新生成；
-哈希仍不是数字签名、外部 witness 或可信时间戳；
-但内部 full replay 能拒绝 metadata/record 一致篡改；
-数学、行、特征和 splits 未改变；
-没有模型、分类、阈值或真实硬件；
- DEV-06.02 未实施。

---

## 十七、保护哈希

继续复核：

- V1.3 ZIP  
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`

- provisional manifest  
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

- inventory  
  `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

- capture context  
  `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`

- summary  
  `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`

- contextual preflight  
  `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`

- hardware setup  
  `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

- ESS WAV/metadata/raw  
  `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`  
  `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`  
  `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

- DEV-06.01 prompt  
  `731683abb9c3fb983c39c462f420d06c9e76d3666e85e9681008de0fb561ef54`

运行全部既有 locked/golden tests，不得更新历史 golden 来掩盖回归。

---

## 十八、验收门禁

最终至少运行：

1. DEV-06.01R 快速回归。
2. DEV-06.01 原10项测试。
3. metadata/record 时间攻击测试。
4.状态字段攻击测试。
5. receipt/hash 重计算攻击测试。
6.完整 Stage 1–4 双根测试。
7. DEV-05.03R/R2 回归。
8. DEV-05 全部测试。
9. DEV-04 全部测试。
10.全部 locked/golden selectors。
11.完整 pytest suite。
12. Ruff format check。
13. Ruff lint。
14. strict mypy。
15. generated Schema consistency。
16. `git diff --check`。
17. prompt byte/hash 验证。
18. implementation log 冻结前缀验证。
19. U+FFFD、秘密、本机路径、真实音频 API、临时产物扫描。
20. changed/new tests 的 skip/xfail/noqa/type-ignore 扫描。
21.工作区清洁检查。

Windows pytest 必须使用预先确认不存在的短 basetemp。路径长度失败不能算作项目失败或通过；必须使用短路径原样重跑。

若任何门禁失败：

-状态为 FAIL；
-不提交成功结论；
-不推送；
-记录真实失败；
-停止并报告。

---

## 十九、报告

创建：

`docs/reports/DEV-06.01R.md`

必须记录实际：

-缺陷复现；
- RED 命令和表现；
-修复设计；
-时间派生规则；
-四个 source completion times；
- analysis evidence time；
-版本变化；
-模型字段变化；
-无循环构造顺序；
- metadata/record/receipt 实际 SHA256；
- core hashes 是否保持；
-攻击测试结果；
- validator 前后 tree hash；
-双根结果；
-完整测试结果；
-静态门禁；
-修改文件；
-临时目录和清理；
-保护哈希；
-已知限制；
-无真实硬件操作；
-无模型、分类或阈值；
- DEV-06.02 未实施。

报告不得预写最终 commit SHA。

---

## 二十、提交和推送

只有所有门禁全部通过后才能提交。

提交标题：

`DEV-06.01R: bind analysis audit metadata to verified sources`

要求：

-普通 commit；
-不 amend；
-不 rebase；
-不 force；
-提交前重新 fetch；
-要求远程 main 仍为起始提交；
-普通 `git push origin main`；
-推送后验证 local HEAD、origin/main、GitHub main 完全一致；
-验证工作区干净。

如果远程变化、测试失败、网络状态不确定或发生中断：

-不 force；
-不改写历史；
-不盲目重复 push；
-只读核对远程；
-无法证明成功则报告未推送。

---

## 二十一、最终回复

成功时以：

`PASS — DEV-06.01R 完成`

开头，并报告：

- commit 和 parent；
-普通 push；
-三向 SHA 一致性；
-工作区状态；
- RED 复现；
-修复后的攻击矩阵；
- evidence time 和 time basis；
- metadata/record/receipt SHA256；
-保持不变的 core hashes；
- DEV-06.01R 测试数；
-完整测试数；
- Ruff/mypy/Schema/diff；
- prompt 和 log prefix；
-保护哈希；
-无硬件操作；
-无模型、分类、阈值；
- DEV-06.02 未实施。

失败时以：

`FAIL — DEV-06.01R 未完成或未推送`

开头，如实说明失败序列号、错误、已生成内容、本地提交状态和未推送状态。

完成 DEV-06.01R 后立即停止，不得自行进入 DEV-06.02。