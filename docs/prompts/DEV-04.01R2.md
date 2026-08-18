# DEV-04.01R2：Processing 复合身份与算法版本溯源闭环

你负责对 Acoustic Ladder 的 DEV-04.01R 做第二次、范围严格受控的修正。本步骤只解决已经独立复现的 processing event 身份作用域错误，以及 transfer estimator 变更后的版本与 receipt 溯源缺口。

必须使用测试驱动方式推进：先复现 RED，再做最小修正，最后运行完整回归。不得进入 DEV-04.02。

## 一、已确认的问题

### 1. Processing event 身份作用域错误

Processing 实际存储路径为：

`processed/run_<source_run_id>/processing_<processing_id>/`

因此 `processing_id` 只在所属 source run 内唯一，不是 session 全局唯一。

当前 `_validated_processing_event()` 只按：

`event.processing_id == processing_id`

筛选事件。

当同一 session 中两个不同 source run 合法复用相同 `processing_id` 时，两个 processing 都能成功发布，但两个 validator 都会因为找到两个事件而失败。

已独立复现：

- source run：`capture-1`，processing ID：`processing-1`
- source run：`capture-2`，processing ID：`processing-1`
- 两个 publish 均成功
- 验证 `capture-1`：`expected exactly one matching processing_created event`
- 验证 `capture-2`：`expected exactly one matching processing_created event`

现有测试 `test_two_processing_events_are_distinguished_by_identity` 只覆盖了同一 source run 下两个不同 processing ID，未覆盖该合法复用情况。

### 2. Processing 算法语义变化但版本未变化

DEV-04.01R 已经得到用户确认，将 transfer estimator 从旧定义：

`rfft(ir_raw)`

修正为复频谱比：

`rfft(input_after_pre) / rfft(output_after_pre)`

aligned transfer 使用零填充前移后的 input 与相同 output reference 做复频谱比。

该数学变化有合理依据，并成功关闭 identity oracle；本步骤不得撤销它。

但是当前：

- `EssProcessingReceipt.algorithm_version` 仍限定为 `1.0.0`
- `_receipt()` 仍写入 `algorithm_version="1.0.0"`
- receipt 中没有明确记录新的 transfer estimator、aligned 定义和近零参考频点策略

这会导致同一个算法版本号对应 DEV-04.01 和 DEV-04.01R 两套不同输出，不利于复现、解释和交叉验证。

## 二、Git 基线

开始前必须只读核验：

- 仓库：`https://github.com/haocheng26710/fingers.git`
- 分支：`main`
- 预期基线：`a52aac34d003f00f3f7583d68927dced8d83a0e8`
- 提交主题：`DEV-04.01R: close processing envelope validation`
- 本地 `HEAD`、`origin/main`、GitHub `refs/heads/main` 必须完全一致
- 工作区必须干净

若基线不一致、远端已前进或工作区存在无法归属的修改，立即停止，不修改、不提交、不推送，并如实报告。

## 三、现有验收基准

DEV-04.01R 当前已知结果：

- 原 DEV-04.01：`61 passed`
- DEV-04.01R 新增：`30 passed`
- DEV-04 合计：`91 passed`
- 完整套件：`460 passed`
- Ruff、strict mypy、18 个生成 Schema、`git diff --check` 均通过
- nominal fixture：
  - latency：`37 samples`
  - IR peak index：`37`
  - IR peak value：约 `0.4999999999999999`

当前已授权的 transfer 修正后 deterministic hashes：

- arrays：`e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89`
- arrays sidecar：`f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902`
- receipt：`6f67bacb552cd5544ae1d6f38a0926c4af80e4616998cbf3216e18d1697d5446`
- receipt sidecar：`45506eec1c9df45ea1061c8df359e89d3a8d2402f94a7ec5154b6dabb9bb25a8`
- metadata：`d10c01d1688070b991518f0db02e17ec0833431943d70578e5f53107a83508af`

本步骤中：

- arrays 与 arrays sidecar 必须保持上述值不变
- receipt、receipt sidecar、metadata 因版本和溯源字段更新，应产生新的确定性哈希
- 新 receipt 系列哈希必须通过双根重放得到，不得预先编造或直接沿用旧值

## 四、保护哈希

以下内容必须保持不变：

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

## 五、日志与提示词归档

### DEV-04.01R2-00：初始化

在修改生产代码前：

1. 阅读全部适用的仓库指令、DEV-04.01/DEV-04.01R 提示词、报告、日志、架构、模型、持久化实现及测试。
2. 如环境提供 TDD skill，先完整读取并按其 RED→GREEN→REFACTOR 流程执行。
3. 将本提示词正文原样归档为：
   `docs/prompts/DEV-04.01R2.md`
4. 按既有仓库规则在 `.gitattributes` 中将提示词归档标记为 binary；不得改变其他历史规则。
5. 记录提示词实际字节数、换行形式和 SHA256，不得虚构来源格式。
6. 测量 `docs/IMPLEMENTATION_LOG.md` 的初始字节数和 SHA256。
7. 在日志末尾追加：
   `## DEV-04.01R2：Processing 复合身份与算法版本溯源闭环`
8. 首次状态写为 `IN_PROGRESS`，记录真实开始时间、基线、工作区状态、问题、计划和禁止范围。
9. 后续每完成一个序列步骤就追加真实命令、输出、失败、修正、测试计数、哈希及清理结果。
10. 日志原有字节必须保持完整前缀，只能追加。
11. 不得修改既有 DEV-04.01R 提示词和报告。

## 六、复合身份 TDD

### DEV-04.01R2-01：建立真实 RED

先增加一个真实文件系统回归：

1. 在同一个 synthetic session 中发布：
   - `capture-1`
   - `capture-2`
2. 使用不同合法 measurement order。
3. 分别对两个 source run 发布：
   - `processing_id="processing-1"`
4. 确认两个 processing 路径不同且均成功发布。
5. 分别调用 `validate_ess_processing()`。
6. 在未修复代码上证明两个验证均因错误的 session-global `processing_id` 匹配而失败。
7. 记录真实 RED 输出。
8. 所有数据使用预先不存在的隔离临时根。
9. 测试结束后精确清理，仅删除本测试创建的根。
10. 不得使用 mock 绕过真实 publish/validate 流程。

同时保留现有：

- 同一 source run 下不同 processing ID 的测试
- 同一复合身份重复 event 必须拒绝的测试
- event identity 篡改测试

### DEV-04.01R2-02：最小身份修正

修正 `_validated_processing_event()`：

- 唯一匹配身份至少必须是：
  `(source_run_id, processing_id)`
- session 由当前受根约束的 session events 目录确定，同时仍必须验证 event 内的 `session_id`
- event 的 `data_origin`、event name、sequence、canonical bytes、record hash、receipt hash和时间绑定继续严格验证
- 同一 session 中其他 source run 使用相同 processing ID 必须被允许
- 同一复合身份出现零个或多个 event 必须拒绝
- 不得把 processing ID 改成 session 全局唯一
- 不得改变 processing 存储路径结构
- 不得修改通用 `append_event()` API，除非测试证明不可避免；若无需修改 `store.py`，保持不变

让真实复合身份 RED 转为 GREEN。

至少增加以下回归：

1. 两个 source run 复用同一个 processing ID，二者均可验证。
2. 两个 source run 的 event 分别绑定各自 record。
3. 同一复合身份重复 event 仍拒绝。
4. 另一个 source run 的合法同名 processing event 不得造成误拒绝。
5. 篡改 source run identity 后拒绝且 validator 无写回。
6. 既有同一 source run、不同 processing ID 测试继续通过。

## 七、算法和 Schema 版本闭环

### DEV-04.01R2-03：Processing algorithm version

只升级 offline ESS processing 的算法版本：

- 新 processing algorithm version：`1.1.0`

必须修改：

- `EssProcessingReceipt.algorithm_version`
- `_receipt()` 中写入的 processing algorithm version
- 对应测试和生成 Schema

不得修改：

- ESS excitation generator 的 `algorithm_version="1.0.0"`
- `EssSignalSpec`
- ESS WAV/metadata/raw golden
- `ProcessingCreatedEvent.schema_version`
- `ProcessingRecord.schema_version`
- 任何不属于 processing receipt 的版本

增加回归，证明：

- 新 processing receipt 明确为 `algorithm_version="1.1.0"`
- 旧 `algorithm_version="1.0.0"` 不能伪装为当前算法产物
- validator 从当前配置和代码重建的 receipt 与存储值一致
- 仅篡改版本并重算 sidecar 仍被 replay validator 拒绝

### DEV-04.01R2-04：Receipt 的 transfer estimator 溯源字段

为 `EssProcessingReceipt` 增加严格、必填、可复现的 transfer estimator 字段。优先采用以下字段和固定值；若现有命名规范要求调整，必须在报告中列出一一对应关系，不能降低信息量：

- `transfer_estimator_id`
  - `complex_spectral_ratio`
- `transfer_raw_definition`
  - `rfft(input_after_pre)/rfft(output_after_pre)`
- `transfer_aligned_definition`
  - `rfft(zero_fill_advance(input_after_pre,estimated_latency_samples))/rfft(output_after_pre)`
- `spectral_division_threshold_formula`
  - `max_abs_reference_spectrum*float64_epsilon*reference_sample_count`
- `spectral_division_below_threshold_policy`
  - `zero_where_reference_at_or_below_threshold`

要求：

1. 字段使用 `Literal` 或等价严格约束。
2. 禁止任意自由文本代替固定契约。
3. receipt 必须足以区分旧 `rfft(ir_raw)` 与当前复频谱比定义。
4. 字段值必须与当前 `_spectral_ratio()` 实现逐项一致。
5. 不修改已经通过 oracle 的 `_spectral_ratio()` 数学代码，除非新测试证明真实缺陷。
6. 不改变 21 个数组的名称、dtype、shape 或顺序。
7. 不改变 processing 七文件集合。
8. 更新 `ess_processing_receipt.schema.json`。
9. 生成 Schema 总数保持 18；历史手工 Schema 不计入生成数量。
10. 增加缺字段、额外字段、错误 literal、错误版本和 receipt 篡改拒绝测试。

由于 receipt 新增必填字段，processing receipt 的 `schema_version` 也必须反映新契约。若仓库没有另行定义 Schema 版本策略，使用：

- processing receipt `schema_version="1.1.0"`

仅更新 `EssProcessingReceipt` 的 Schema 版本；event、record 和其他历史 Schema 版本保持原值。

如果仓库已经存在明确且冲突的版本策略，停止实施并向用户说明，不得自行猜测。

## 八、确定性要求

### DEV-04.01R2-05：固定与更新边界

本次不得修改 transfer 数学，因此以下两个哈希必须保持：

- arrays：`e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89`
- arrays sidecar：`f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902`

以下旧值应因 receipt schema、algorithm version 和新增字段而变化：

- old receipt：`6f67bacb552cd5544ae1d6f38a0926c4af80e4616998cbf3216e18d1697d5446`
- old receipt sidecar：`45506eec1c9df45ea1061c8df359e89d3a8d2402f94a7ec5154b6dabb9bb25a8`
- old metadata：`d10c01d1688070b991518f0db02e17ec0833431943d70578e5f53107a83508af`

要求：

1. 先完成语义测试，再生成新 golden。
2. 使用两个独立临时根重放。
3. 两根 receipt、sidecar、metadata 必须逐字节一致。
4. 记录旧值→新值的映射和变化原因。
5. 不得把一次运行结果直接当成数学正确性证明；正确性仍由 identity、multi-tap、polarity oracle 和字段语义测试提供。
6. 新 golden 稳定后增加明确回归，防止无说明漂移。
7. processing record hash和 event bytes 可因 receipt hash变化而变化；必须重新验证绑定。
8. 若 arrays 或 arrays sidecar 变化，立即停止，不提交、不推送，并调查是否意外修改了数学实现。

## 九、双根重放

### DEV-04.01R2-06：完整重放

使用两个预先确认不存在的短路径隔离临时根，执行：

ESS generate/validate → synthetic session create/validate → 两个 virtual capture publish/validate → processing publish/validate

至少覆盖：

- session：`dev0401r2`
- assembly：`assembly001`
- source runs：
  - `capture001`
  - `capture002`
- 两个 source run 均使用：
  - `processing_id="processing001"`
- measurement order：
  - `0`
  - `1`

验证：

1. 两个同名 processing 均发布到各自 source run 子目录。
2. 两个 event 均能按复合身份正确区分。
3. 两个 processing 均能独立 validate。
4. 同一复合身份重复 event 仍拒绝。
5. nominal 数学结果继续为：
   - latency `37`
   - IR peak index `37`
   - IR peak value约 `0.5`
6. arrays/arrays sidecar 保持指定哈希。
7. 新 receipt/sidecar/metadata 在两个根逐字节一致。
8. event 正确绑定各自 record hash、新 receipt hash和 created time。
9. validator 在成功和拒绝路径均不写回。
10. real root 不得创建。
11. 所有临时根最终精确清理并确认不存在。

Windows 下必须使用足够短的隔离临时路径，避免传统路径长度导致与代码无关的测试失败。若首次测试因临时目录权限或路径长度失败，必须记录为环境失败并用新的短隔离根重跑，不得计作项目测试失败或通过。

## 十、完整门禁

### DEV-04.01R2-07：测试与静态检查

至少执行并记录：

1. 修复前复合身份真实 RED。
2. DEV-04.01 原 61 项全部通过。
3. DEV-04.01R 原 30 项全部通过。
4. DEV-04.01R2 新增测试全部通过。
5. DEV-04 合计测试通过。
6. 完整套件通过，原 460 项不得减少。
7. Ruff format check。
8. Ruff lint。
9. strict mypy，覆盖与既有验收相同的 67 source files。
10. 18 个生成 Schema 一致性检查。
11. `git diff --check`。
12. `skip`、`xfail`、`noqa`、`type: ignore` 等 suppression 扫描。
13. U+FFFD、本机绝对路径、用户名、身份和秘密扫描。
14. 新真实音频 API、`sounddevice`、Stream、play、record 扫描。
15. tracked WAV、FLAC、NPY、NPZ、cache、staging、lock 和测试临时目录扫描。
16. 历史 prompt、report、配置、fixture 和保护文件 diff/hash 检查。
17. implementation log 初始字节前缀检查。
18. Git 工作区和未跟踪文件检查。

不得通过删除旧测试、弱化断言、提高无依据容差或增加 suppression 获得通过。

## 十一、禁止范围

本步骤严禁：

- 修改当前已经通过的 transfer 数学实现；
- 恢复旧 `rfft(ir_raw)` transfer 定义；
- 修改 ESS inverse、deconvolution、latency、IR 或 oracle 参数；
- 连接、枚举、选择或绑定真实音频设备；
- 运行 production `audio-list` 或 `audio-inventory`；
- 播放、录音或打开真实 Stream；
- 读取或应用 iMM-6C 校准文件；
- SPL 校准、电气回环、真实延迟或 shared-clock 测量；
- 将 synthetic fixture 描述为真实声学实验；
- 设置任何 hardware/readiness/calibration/formal/experimental 标志为 true；
- 修改 CAD、打印模型或 V1.3 几何状态；
- 进入 DEV-03.05、DEV-04.02 或其他后续阶段；
- 修改 DEV-04.01R 历史提示词或报告；
- force push。

## 十二、文档与日志

### DEV-04.01R2-08：收尾文档

创建：

`docs/reports/DEV-04.01R2.md`

必要时最小更新：

- `docs/architecture/ess-processing.md`
- `docs/architecture/storage-layout.md`
- README
- Schema 文档说明

报告必须包含：

- 基线；
- 独立复现的复合身份 RED；
- 根因；
- 修正前后事件匹配逻辑；
- processing ID 的实际作用域；
- algorithm version 和 receipt schema version 变更；
- 五个 transfer provenance 字段；
- 为什么 ESS excitation 版本保持不变；
- 原 460 项与新增测试结果；
- identity、multi-tap、polarity oracle 保持情况；
- 双根同名 processing 重放；
- arrays 不变证据；
- receipt 系列旧→新哈希；
- event/record/receipt 新绑定结果；
- 全部保护哈希；
- 实际命令；
- 临时根清理；
- 未执行项目；
- 没有真实硬件操作；
- 已知限制；
- 修改文件清单。

将 implementation log 的 DEV-04.01R2 区块更新为真实完成状态。详细程度必须使另一人借助其他 AI 尽可能复刻实施和验证。

报告与日志冻结时尚未产生最终提交 SHA，不得编造未来 SHA。最终 SHA 只能在执行完成回复中报告。

## 十三、提交与推送

### DEV-04.01R2-09：仅在全部 PASS 后推送

提交前再次确认：

- 全部测试和静态门禁通过；
- arrays 两个哈希保持不变；
- receipt 系列新哈希已双根确认；
- 所有保护哈希正确；
- 临时目录全部清理；
- 无无关修改和未跟踪文件；
- `git diff --check` 通过；
- GitHub `main` 仍为基线：
  `a52aac34d003f00f3f7583d68927dced8d83a0e8`

若远端已经变化，停止且不推送。

全部通过后：

1. 提交主题：
   `DEV-04.01R2: fix processing identity and version provenance`
2. 正常推送到 `origin/main`。
3. 禁止 force push。
4. 推送后核验本地 `HEAD`、`origin/main`、GitHub main 完全一致。
5. 核验工作区干净。

任何测试、哈希、远端或推送步骤失败时：

- 不得报告 `PASS`
- 不得推送未通过实现
- 不得进入 DEV-04.02
- 必须如实记录失败点和本地状态

## 十四、最终回复格式

最终回复必须给出：

- `PASS — DEV-04.01R2 完成` 或真实失败状态
- 最终提交 SHA
- 分支与远端
- 本地、`origin/main`、GitHub main 一致性
- 工作区状态
- 复合身份 RED→GREEN 结果
- 原 DEV-04.01、DEV-04.01R、DEV-04.01R2 和全量测试数量
- Ruff、strict mypy、Schema、diff 结果
- processing receipt schema version
- processing algorithm version
- transfer provenance 字段
- 两个 source run 复用同一 processing ID 的验证结果
- nominal 37/37/0.5 结果
- arrays 与 arrays sidecar 保持值
- receipt、receipt sidecar、metadata 新哈希
- event/record/receipt 绑定结果
- 全部保护哈希
- 临时根清理结果
- 没有真实硬件调用的声明
- 主要交付文件
- 已知限制
- 是否成功推送

完成 DEV-04.01R2 后立即停止，等待用户确认，不得自行进入 DEV-04.02。