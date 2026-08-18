# DEV-04.03R：Repeatability 状态语义与无阈值边界闭环

你现在负责在 Acoustic Ladder 仓库中实际实施 `DEV-04.03R`。

这是针对 DEV-04.03 独立验收发现问题的限定修正任务。不得扩大到新功能、基线分析、正式漂移分析或后续阶段。

只有全部修正、回归、确定性验证和 Git 门禁通过后才能提交及推送。任何失败、中断、远端变化或未解决问题都必须如实记录并停止，不得推送。

---

## 一、修正目标

DEV-04.03 的数学内核、成员 provenance、不可变发布和确定性重放基本正确，但存在两个必须修复的契约问题。

### 问题一：状态只出现在 CLI 文案中，没有完整进入不可变 receipt

已确认方案要求：

- `repeatability_decision = not_evaluated`
- `baseline_role = not_assigned`
- `baseline_selection_status = deferred_until_protocol_binding`
- `drift_decision = not_evaluated`

当前实现却是：

- `decision_status = not_evaluated`
- `baseline_role = null`
- 没有 `baseline_selection_status`
- 没有 `drift_decision`
- 只有 `protocol_condition_binding_performed=false`
- 只有 `drift_evaluated=false`

CLI 会硬编码打印：

- `BASELINE_NOT_ASSIGNED`
- `BASELINE_SELECTION_DEFERRED_UNTIL_PROTOCOL_BINDING`
- `REPEATABILITY_NOT_EVALUATED`

但这些结论并未完整存在于不可变 receipt 中，无法由另一个验证器仅根据产物重建。

### 问题二：无阈值边界未被强制

独立反例已经证明：

- 将活动 AnalysisConfig 的 `drift_threshold` 设置为 `0.5`
- repeatability publisher仍然成功发布
- receipt仍声称：
  - `thresholds_applied=false`
  - `threshold_source=null`

这不等于“阈值被应用”，但违反了 DEV-04.03 已确认的严格边界：本阶段应拒绝任何非空 baseline selection rule和 decision threshold，不能在存在阈值配置时发布“threshold-free”产物。

本步骤必须修复这两个问题，同时保持 repeatability 数学结果不变。

---

## 二、Git 基线

预期状态：

- remote：`https://github.com/haocheng26710/fingers.git`
- branch：`main`
- baseline commit：`074abae69216672aa7a8410640c5ba79118c6f44`
- baseline message：`DEV-04.03: add provisional repeatability evidence`

开始修改前必须：

1. 完整读取适用的仓库级 agent 指令。
2. 确认当前仓库、分支和remote。
3. 确认工作区干净，包括未跟踪文件。
4. 确认 local HEAD、`origin/main` 和 GitHub `refs/heads/main` 均为上述基线。
5. 记录基线测试和保护哈希。

如任一项不满足：

- 不修改；
- 不 reset、merge、rebase、stash或覆盖用户内容；
- 不提交；
- 不推送；
- 报告实际状态并停止。

---

## 三、提示词与实施日志

### DEV-04.03R-00：初始化

归档本次完整提示词为：

`docs/prompts/DEV-04.03R.md`

要求继续遵循既有 prompt 归档规则：

- 有原始附件时逐字节复制并验证；
- 无原始附件时保存 UTF-8可见文本，并如实说明不能声称附件 byte-exact；
- 记录 bytes、换行、末尾换行和 SHA256；
- 不修改历史 prompt；
- 更新 `.gitattributes`。

继续追加：

`docs/IMPLEMENTATION_LOG.md`

开始前记录：

- 旧日志字节数和完整前缀 SHA256；
- 时间和时区；
- Git基线；
- remote；
- 工作区；
- prompt归档；
- 两个独立验收缺陷；
- 允许修改范围；
- 预期会改变和必须保持不变的哈希；
- 状态 `IN_PROGRESS`。

每完成一个编号步骤都必须追加真实记录。旧内容不可重写；错误只能以后续更正形式追加。

不得提前填写：

- 最终测试数；
- 新 deterministic receipt hashes；
- 最终提交 SHA；
- 推送成功；
- `PASSED`。

---

## 四、基线保护

开始时应有：

- 完整测试：`576 passed`
- generated Schema：22
- total Schema：23
- strict mypy：77 source files

DEV-04.03 当前 deterministic hashes：

### 必须保持不变

Repeatability数学内容不应改变，因此以下两个哈希必须保持：

- `repeatability_metrics.json`  
  `730872025244fb847b6ed9937865017b9563cb030865fb8bac193ea0cd2928b3`
- `repeatability_metrics.sha256`  
  `2581bdb2b036e87035e5f0da5e45c93d173b4e75d84eb71b4279b6a76853a6c8`

### 预计必须改变

因为 receipt 状态契约和版本将被修正，以下 DEV-04.03值只能作为旧版 `1.0.0` 参考，不得继续作为新最终值：

- old receipt  
  `bb4253cbb3a92c5dd3c9d92563e4abf5dd93fbdb2918496fcb2b14ef98e5073f`
- old receipt sidecar  
  `d5f3adf4ca72ce7af21be5fde27d1dd29af9bf187934650045964de85c13fd4c`
- old metadata  
  `bb6fea1c5da81f10a6c39c9ae597ec1acca955a605758634d05a7bdbc361bc16`

必须通过真实双根重放生成新的：

- receipt hash；
- receipt-sidecar hash；
- metadata hash。

如果 metrics或metrics-sidecar哈希发生变化：

1. 停止；
2. 查明数学或成员序列为何变化；
3. 不接受新 golden；
4. 不提交；
5. 不推送；
6. 报告用户。

历史保护项必须继续保持：

- V1.3 ZIP；
- manifest；
- inventory/context/summary/preflight/hardware；
- ESS WAV/metadata/raw；
- DEV-04.01R2 processing五个 golden；
- DEV-04.02 QC五个 golden；
- 历史 prompts/reports；
- config、fixtures和reference文件。

---

## 五、TDD要求

使用严格 RED → GREEN → REFACTOR。

如果环境提供 TDD skill，必须完整读取并遵循。

必须先建立能够重现以下问题的公共接口测试：

1. receipt接受 `baseline_role=null`。
2. receipt缺少 `baseline_selection_status`。
3. receipt缺少 `drift_decision`。
4. repeatability publisher接受非空 `drift_threshold`。
5. CLI输出了receipt中不存在的状态。

先运行并记录真实 RED，然后才允许修改 production代码。

不得：

- 先改代码再补测试；
- 删除或放宽旧测试；
- 使用skip、xfail、noqa或type-ignore；
- 只测试私有helper；
- 仅断言CLI硬编码字符串而不检查receipt；
- 用更新golden掩盖状态契约错误。

---

## 六、状态模型修正

### DEV-04.03R-01：Receipt 1.1.0

保持：

- `ProvisionalRepeatabilityMetrics.schema_version = 1.0.0`
- 纯数学公式不变
- pair和aggregate结构不变

升级：

- `ProvisionalRepeatabilityReceipt.schema_version = 1.1.0`
- `repeatability_algorithm_version = 1.1.0`

新增或修正为严格Literal：

- `decision_status: Literal["not_evaluated"]`
- `repeatability_decision: Literal["not_evaluated"]`
- `baseline_assigned: Literal[False]`
- `baseline_role: Literal["not_assigned"]`
- `baseline_selection_status: Literal["deferred_until_protocol_binding"]`
- `baseline_difference_computed: Literal[False]`
- `protocol_condition_binding_performed: Literal[False]`
- `drift_evaluated: Literal[False]`
- `drift_decision: Literal["not_evaluated"]`
- `thresholds_applied: Literal[False]`
- `repeatability_threshold: None`
- `threshold_source: None`

保留全部：

- hardware false；
- playback false；
- recording false；
- hardware-ready false；
- full-duplex false；
- shared-clock false；
- channel-mapping false；
- calibration false；
- SPL false；
- electrical-loopback false；
- formal false；
- experimental false；
- safety marker。

要求：

- 旧 `baseline_role=null` 必须被模型拒绝；
- 缺少任何新增状态字段必须被拒绝；
- 错误字符串必须被拒绝；
- extra字段必须被拒绝；
- 旧 receipt schema/algorithm `1.0.0` 必须被新 validator拒绝；
- 不提供兼容降级或隐式迁移；
- 旧 artifact需要重新生成。

`decision_status` 与 `repeatability_decision` 如同时保留，必须都是固定Literal，不能形成两个可分歧的自由字段。架构文档中应说明：

- `decision_status` 是通用处理流水线状态；
- `repeatability_decision` 是本层显式重复性判决状态；
- 两者当前都固定为 `not_evaluated`。

---

## 七、Record、metadata和事件绑定

### DEV-04.03R-02：状态贯穿不可变产物

`RepeatabilityRecord` 因字段契约变化，应升级：

- `schema_version = 1.1.0`

至少加入并固定：

- `repeatability_decision = not_evaluated`
- `baseline_role = not_assigned`
- `baseline_selection_status = deferred_until_protocol_binding`
- `drift_decision = not_evaluated`

同时保留：

- `baseline_assigned=false`
- `formal_eligible=false`
- `experimental_result=false`

`repeatability_metadata.json` 必须加入并固定：

- `repeatability_decision`
- `baseline_role`
- `baseline_selection_status`
- `baseline_difference_computed=false`
- `drift_decision`
- `thresholds_applied=false`
- `repeatability_threshold=null`
- `threshold_source=null`
- `protocol_condition_binding_performed=false`
- `drift_evaluated=false`

record和metadata不得自行生成另一套状态。应从已验证 receipt或统一的严格状态构造函数派生，避免三个位置将来漂移。

事件模型如果字段集合未变化，可以保留 event schema `1.0.0`；但必须继续绑定新的：

- record SHA256；
- receipt SHA256；
- metrics SHA256；
- normalized member-list SHA256；
- created_at；
- `(reassembly_id, repeat_set_id)`。

validator必须根据唯一事件时间重建新 `1.1.0` record，不允许旧record自证时间。

event失败继续：

- 保留已发布目录；
- 报告 `published=true`；
- 不删除不可变产物。

---

## 八、AnalysisConfig 无阈值门禁

### DEV-04.03R-03：发布前配置审计

在 repeatability publisher和validator的公共执行路径中增加明确的 AnalysisConfig门禁。

门禁必须在创建任何 repeatability目录、parent、staging或lock之前完成。

必须确认：

- bundle中存在活动 AnalysisConfig；
- 类型正确；
- `baseline_selection_rule is None`；
- 以下全部为 `None`：
  - `qc_threshold`
  - `effect_threshold`
  - `drift_threshold`
  - `classification_pass_threshold`

任一字段非空时：

- 抛出 `RepeatabilityPersistenceError`；
- `published=false`；
- 错误信息明确指出具体非空字段；
- 不创建repeatability target；
- 不创建repeatability event；
- 不修改已有member artifacts；
- 不创建real root。

不得只依赖 CLI 没有 threshold参数，因为阈值可以存在于 AnalysisConfig。

不得只检查 `qc_threshold`。本步骤的 repeatability产物要求所有决策阈值和baseline selection rule均未定义。

建议同时验证活动 AnalysisConfig model与其加载快照的 normalized hash一致。如果现有公共bundle验证器已经严格完成该工作，应复用并添加回归；如果没有，应在不扩大到全仓重构的前提下，对本步骤读取的活动 AnalysisConfig执行最小规范化哈希复核。

必须建立至少以下独立反例：

1. `baseline_selection_rule` 非空；
2. `qc_threshold` 非空；
3. `effect_threshold` 非空；
4. `drift_threshold` 非空；
5. `classification_pass_threshold` 非空。

五个反例都必须在写盘前被拒绝，并验证目标目录不存在。

---

## 九、CLI 真实性

### DEV-04.03R-04：从receipt输出状态

CLI不得再用无来源的固定字符串代替不可变事实。

成功输出应读取并显示receipt字段，例如：

- `decision_status=<receipt value>`
- `repeatability_decision=<receipt value>`
- `baseline_assigned=<receipt value>`
- `baseline_role=<receipt value>`
- `baseline_selection_status=<receipt value>`
- `baseline_difference_computed=<receipt value>`
- `drift_evaluated=<receipt value>`
- `drift_decision=<receipt value>`
- `thresholds_applied=<receipt value>`
- `repeatability_threshold=<receipt value>`
- `threshold_source=<receipt value>`

安全标记可以继续输出，但必须与已验证receipt一致：

- `SYNTHETIC_ONLY`
- `PROVISIONAL_REPEATABILITY_METRICS_ONLY`
- `REPEATABILITY_NOT_EVALUATED`
- `THRESHOLDS_NOT_APPLIED`
- `BASELINE_NOT_ASSIGNED`
- `BASELINE_SELECTION_DEFERRED_UNTIL_PROTOCOL_BINDING`
- `NO_BASELINE_DIFFERENCE_COMPUTED`
- `DRIFT_NOT_EVALUATED`
- `NO_HARDWARE_AUDIO_IO_PERFORMED`
- `NOT_AN_EXPERIMENTAL_RESULT`

测试必须同时断言：

- receipt中的结构化字段；
- CLI字段输出；
- safety marker；
- 三者语义一致。

不要仅通过搜索固定字符串完成测试。

CLI的 `PASS` 仍只代表软件发布或验证成功，不代表repeatability、QC、drift或实验PASS。

---

## 十、Schema

### DEV-04.03R-05：Schema更新

重新从活动模型生成：

`schemas/provisional_repeatability_receipt.schema.json`

要求：

- receipt schema版本为 `1.1.0`；
- repeatability algorithm version为 `1.1.0`；
- 新状态字段全部required；
- `baseline_role` 是唯一允许值 `not_assigned`，不是null；
- `baseline_selection_status` 是唯一允许值；
- `drift_decision` 是唯一允许值；
- threshold字段只能为null/false；
- 旧 `1.0.0` payload不能通过活动模型。

Repeatability metrics Schema不得变化，除非发现独立数学缺陷；本步骤没有授权数学修改。

generated Schema数量应保持22，total应保持23。不得增加重复Schema或只修改计数断言。

执行并记录 Schema export和consistency check。

---

## 十一、回归测试

### DEV-04.03R-06：补齐缺失回归

基线576项必须全部保留。

新增测试至少覆盖：

#### 状态模型

- 正确 `1.1.0` receipt通过；
- `baseline_role=null`拒绝；
- missing `baseline_role`拒绝；
- missing `baseline_selection_status`拒绝；
- missing `drift_decision`拒绝；
- wrong `repeatability_decision`拒绝；
- wrong `baseline_selection_status`拒绝；
- `drift_evaluated=true`拒绝；
- `thresholds_applied=true`拒绝；
- non-null threshold拒绝；
- old receipt schema `1.0.0`拒绝；
- old algorithm `1.0.0`拒绝；
- extra字段拒绝。

#### 配置门禁

分别注入：

- baseline selection rule；
- QC threshold；
- effect threshold；
- drift threshold；
- classification threshold。

每次验证：

- public publisher拒绝；
- `published=false`；
- repeatability目录不存在；
- event未增加；
-成员处理/QC文件未变化；
- real root不存在。

validator也必须在活动配置违反边界时拒绝且不写回。

#### CLI

- compute和validate输出完整结构化状态；
- 输出值来自receipt；
- `baseline_role=not_assigned`；
- `baseline_selection_status=deferred_until_protocol_binding`；
- `drift_decision=not_evaluated`；
- threshold字段为false/null；
- 没有新的threshold/baseline/real-root命令行authority。

#### 持久化和攻击

在新 `1.1.0` 模型下重新覆盖：

- receipt状态篡改；
- metadata状态篡改；
- record状态篡改；
- receipt sidecar；
- event record/receipt hash；
- old `1.0.0` artifact；
- validator前后树hash不变；
-恢复后再次PASS。

#### 保护

明确断言：

- repeatability metrics和metrics-sidecar哈希不变；
- processing/QC历史golden不变；
-数学源文件没有意外变更。

不得用删除旧断言或减少测试数的方式通过。

---

## 十二、双根确定性复验

### DEV-04.03R-07：新版本双根

使用两个预先确认不存在的短临时根，重新完成：

ESS  
→ session/reassembly  
→ 三个capture，orders 0/1/2  
→ 每个processing  
→ 每个provisional QC  
→ repeatability publish  
→ repeatability validate

第二根使用逆序member输入，最终规范顺序仍必须为0/1/2。

要求：

- 3 members；
- 3 pairs；
- real root未创建；
- 两根五个deterministic payload逐字节相同；
- metrics和metrics-sidecar继续为：
  - `730872025244fb847b6ed9937865017b9563cb030865fb8bac193ea0cd2928b3`
  - `2581bdb2b036e87035e5f0da5e45c93d173b4e75d84eb71b4279b6a76853a6c8`
- 生成并记录新的：
  - receipt hash；
  - receipt-sidecar hash；
  - metadata hash；
- receipt schema/algorithm均为 `1.1.0`；
- record schema为 `1.1.0`；
- 所有新增状态字段存在且正确；
- 旧receipt不能通过新validator。

在其中一个根攻击：

1. `baseline_role`
2. `baseline_selection_status`
3. `drift_decision`
4. `repeatability_decision`
5. metadata对应状态
6. record对应状态
7. receipt sidecar
8. event receipt/record hash

每次攻击都必须：

- validation失败；
- 记录验证前后目标文件或完整session tree SHA256；
- 确认validator无写回；
- 恢复原字节；
- 最后再次validation PASS。

清理前必须验证每个resolved临时根位于预期测试父目录；只精确删除本步骤创建的根，清理后确认不存在。

---

## 十三、文档与日志

### DEV-04.03R-08：文档收尾

创建：

`docs/reports/DEV-04.03R.md`

最小更新：

- README；
- repeatability架构文档；
- configuration文档；
- storage layout；
- Schema说明；
- data README；
- append-only implementation log。

明确记录：

- 独立验收发现的两个问题；
- RED复现；
- 状态字段如何修正；
- 为什么receipt/algorithm升级到1.1.0；
- 为什么metrics版本和哈希保持不变；
- 哪三个deterministic hashes发生变化；
- threshold injection如何在写盘前被拒绝；
- CLI如何改为从receipt输出；
- old `1.0.0` repeatability artifact必须重新生成；
- 没有baseline、baseline difference、threshold应用、drift判决或实验结论；
- 没有真实硬件操作；
- event仍无数字签名、外部witness或可信时间戳。

报告不得把软件回归PASS写成声学repeatability或实验PASS。

---

## 十四、禁止范围

本步骤不得：

- 修改repeatability数学公式；
- 修改pair枚举；
- 修改member排序规则；
- 修改capture、ESS、processing或QC数学；
- 接受新的metrics golden；
- 实现BLK baseline；
- 实现baseline selection；
- 实现baseline difference；
-应用threshold；
-形成repeatability PASS/FAIL；
-形成drift PASS/FAIL；
-实现feature extraction；
-实现classifier；
-实现cross-validation；
-实现protocol engine；
-连接或枚举真实设备；
-播放、录音或打开Stream；
-读取或应用校准文件；
-做SPL、loopback或shared-clock验证；
-创建real root；
-修改V1.3模型包；
-修改历史prompt/report；
-进入DEV-04.04、DEV-05或后续步骤；
-force push。

如果metrics哈希变化或发现必须修改数学：

- 停止；
- 不提交；
- 不推送；
- 记录证据；
- 等待用户重新授权。

---

## 十五、最终门禁

### DEV-04.03R-09：完整验证

必须执行并记录：

1. 原576项测试全部保留。
2. 新增回归全部通过。
3. 完整pytest通过。
4. 无skip、skipif、xfail。
5. Ruff format check。
6. Ruff lint。
7. strict mypy。
8. 22 generated Schema consistency。
9. 23 total Schema核对。
10. `git diff --check`。
11. metrics和metrics-sidecar固定哈希。
12. 新receipt/sidecar/metadata双根哈希。
13. V1.3及全部历史保护哈希。
14. prompt归档SHA256。
15. implementation log旧前缀SHA256。
16. 历史prompt/report diff。
17. config/fixtures/reference保护。
18. suppression扫描。
19. U+FFFD扫描。
20. secret、本机路径和身份扫描。
21. 新真实音频API扫描。
22. tracked media/cache/staging/lock/temp扫描。
23. threshold injection五个反例。
24. old `1.0.0` repeatability artifact拒绝。
25.攻击后validator无写回。
26. real root未创建。
27. 所有临时根安全清理。
28. 最终工作区只包含预期文件。
29. 提交前再次运行完整测试、静态和Schema门禁。

所有中间失败必须真实保留在报告和日志中，不得只记录最终GREEN。

---

## 十六、提交与推送

### DEV-04.03R-10：条件Git操作

只有所有门禁通过，并且GitHub `main` 在提交前仍为：

`074abae69216672aa7a8410640c5ba79118c6f44`

才允许提交。

提交信息：

`DEV-04.03R: close repeatability state and threshold gates`

提交前：

- 确认diff只包含本步骤预期内容；
- 确认metrics数学源文件无非必要修改；
- 确认历史保护；
- 确认临时文件已清理。

提交后：

1. 确认工作区干净；
2. 正常push `main`；
3. 禁止force push；
4. 推送后只读验证local HEAD、`origin/main`、GitHub main三向一致；
5. 最终回复报告真实commit SHA。

如远端发生变化：

- 不push；
- 不自动merge/rebase；
- 报告远端新SHA；
- 等待用户决定。

如任何测试、权限、网络或实现步骤失败：

- `NOT PUSHED`
- 不将日志状态标记为PASSED；
- 记录最后成功检查点；
- 报告当前工作区和是否已有本地commit；
- 等待用户决定。

不要尝试在同一个提交内写入其自身最终SHA。最终SHA由Git历史和最终回复报告。

---

## 十七、最终回复

成功时至少报告：

- `PASS — DEV-04.03R 完成`
- commit SHA；
- branch/remote；
- local/origin/GitHub三向一致；
- 工作区干净；
- 原测试576、新增测试和完整测试数；
- Ruff/mypy/Schema/diff结果；
- metrics两个保护哈希保持不变；
- 新receipt/sidecar/metadata哈希；
- receipt、algorithm、record版本；
- 五类threshold/baseline配置注入均在写盘前拒绝；
- old `1.0.0` artifact拒绝；
- CLI状态来自receipt；
- 双根、攻击和清理结果；
- 所有历史保护哈希状态；
- 没有真实硬件操作；
- 仍无baseline、baseline difference、threshold应用、drift判决或实验结论；
- 主要交付文件和已知限制。

失败时至少报告：

- `NOT PUSHED`
- 当前状态；
- 真实失败原因；
- 最后成功步骤；
- 工作区状态；
- 是否产生本地commit；
- 未推送确认；
- 继续前需要的用户决定。

完成DEV-04.03R后停止，不进入下一步骤。