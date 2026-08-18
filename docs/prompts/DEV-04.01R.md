# DEV-04.01R：处理产物规范性、防篡改绑定与独立 Oracle 闭环

你现在负责对 Acoustic Ladder 的 DEV-04.01 做一次范围严格受控的修正。必须先审计现状、用测试复现缺陷，再修复；不得借机进入下一开发阶段。

## 一、任务目标

修复 DEV-04.01 中已经独立复现的四个验收绕过，并补齐原 DEV-04.01 提示词要求但尚未落实的完整数学流水线独立 oracle：

1. 非规范 `processing_arrays.npz.sha256` 会被接受。
2. 非规范 `processing_receipt.sha256` 会被接受。
3. 内容被篡改的 `PROCESSING_COMPLETE` 会被接受。
4. `processing_record.json` 的 `created_at` 可被规范化篡改并通过验证。
5. 缺少 identity、multi-tap FIR 和极性反转的完整公共处理流水线 oracle。

本步骤仅修正 synthetic offline ESS processing 的完整性、审计绑定和回归覆盖，不修改 ESS 核心算法，不进入 DEV-04.02。

## 二、已知基线

开始时必须只读核验：

- 仓库：`https://github.com/haocheng26710/fingers.git`
- 分支：`main`
- 预期基线提交：`078c7257a588f3621d388ea81dd6e6a7f4c4265e`
- 本地 `HEAD`、`origin/main`、GitHub `refs/heads/main` 必须完全一致。
- 工作区必须干净。
- 若基线不一致、远端已前进或存在无法归属的修改：立即停止，不修改、不提交、不推送，并如实报告。

当前 DEV-04.01 已知正常结果：

- 全量测试：`430 passed`
- DEV-04.01：`61 passed`
- arrays SHA256：`4c6b9b740112fd2afc34b35ff939de6f0632abb638080c4be9e0dc67af07a560`
- arrays sidecar SHA256：`b55e75ad2ae170cba054e557e61084dff4e48efbaf96e700b667ca7704660dc9`
- receipt SHA256：`183387988658058a3cb1cf4b056e59326bb609d4fd414898edea99fed8e98727`
- receipt sidecar SHA256：`b0a6275e2f2adac141a70fe896cd4fedc22fd852406ef0172fbaca4d2331c9b9`
- metadata SHA256：`af00d2cfd737739797defa39da5596e5a88a98e5d2d54dc78dfcacc3aa26e745`
- nominal development fixture：延迟 `37 samples`，IR 主峰索引 `37`，峰值约 `0.5`

受保护哈希：

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

## 三、日志和提示词归档

### DEV-04.01R-00：初始化

在修改生产代码前：

1. 阅读仓库内全部适用的项目指令、`pyproject.toml`、相关架构文档、DEV-04.01 提示词、报告、测试与实现。
2. 将本提示词正文原样保存为：
   `docs/prompts/DEV-04.01R.md`
3. 不得修改既有 `docs/prompts/DEV-04.01.md` 或 `docs/reports/DEV-04.01.md`。
4. 记录本提示词归档文件的字节数和 SHA256。
5. 测量 `docs/IMPLEMENTATION_LOG.md` 的初始字节数和 SHA256。
6. 在日志末尾创建：
   `## DEV-04.01R：处理产物规范性、防篡改绑定与独立 Oracle 闭环`
7. 首次状态写为 `IN_PROGRESS`，记录实际开始时间、Git 基线、工作区状态、提示词哈希、计划和明确禁止范围。
8. 此后每完成一个序列步骤就追加真实记录。必须记录实际命令、真实输出、失败原因、修正、测试计数、哈希和清理结果；未知内容留空或标记未知，严禁编造。
9. 保证日志原有内容保持逐字节前缀不变，只能追加。

## 四、TDD 缺陷复现

### DEV-04.01R-01：先建立 RED 证据

必须先在 `tests/dev04/` 中增加回归测试，并在未修复的基线上分别证明以下攻击被错误接受：

1. 在 `processing_arrays.npz.sha256` 后增加额外换行或空白。
2. 在 `processing_receipt.sha256` 后增加额外换行或空白。
3. 把合法 LF sidecar 改成 CRLF。
4. 将 `PROCESSING_COMPLETE` 改为其他非空内容。
5. 将 `processing_record.json` 的 `created_at` 改为另一个合法 aware datetime，重新规范化 JSON，但不修改对应审计锚点。
6. 删除 processing audit event。
7. 篡改 audit event 中的 record hash、receipt hash或时间戳。
8. 为同一个 processing identity 制造重复 audit event。

所有攻击测试必须：

- 只使用隔离临时目录。
- 先确认目标临时目录不存在。
- 不调用真实音频 API。
- 验证 validator 在失败时不写回、不修复、不删除被篡改文件。
- 记录修复前真实 RED 输出。
- 不使用 `skip`、`xfail`、测试抑制或弱化断言制造通过。

若其中某个反例在当前基线上已经被拒绝，记录真实结果并检查复现方法，不得伪造 RED。

## 五、规范字节验证

### DEV-04.01R-02：关闭 sidecar 与完成标记绕过

修改 `ess_processing_persistence.py` 中相关验证逻辑：

1. `_verify_sidecar` 必须计算目标文件真实 SHA256，并将 sidecar 原始 bytes 与 `_sidecar(digest, filename)` 的结果逐字节比较。
2. 不得继续使用 `.split()`、`.strip()` 或其他会接受非规范空白的解析方式。
3. 必须拒绝：
   - 额外空格；
   - 额外空行；
   - CRLF；
   - 重复记录；
   - 错误文件名；
   - 非 ASCII 内容；
   - 缺失或目录替代。
4. `PROCESSING_COMPLETE` 必须是普通文件，且原始内容严格等于 `b"complete\n"`。
5. validator 必须保持只读。
6. processing 目录的既有七文件 exact-set 契约保持不变，不为 record 新增目录内 sidecar。

完成后让对应 RED 测试转为 GREEN，并同步日志。

## 六、ProcessingRecord 独立审计绑定

### DEV-04.01R-03：消除时间戳自我验证

当前 validator 使用被验证记录自身的 `created_at` 构造期望记录，这是无效的自我比较。必须建立独立审计锚点。

优先复用现有：

`ImmutableSessionStore.append_event(DataOrigin.SYNTHETIC, session_id, event, payload)`

实现一个严格的 `processing_created` session event。事件至少必须绑定：

- `schema_version`
- `processing_id`
- `source_run_id`
- `created_at`
- `processing_record_sha256`
- `processing_receipt_sha256`

要求：

1. `processing_record_sha256` 必须来自实际 canonical `processing_record.json` bytes。
2. publisher 在 processing 目录成功 create-only 发布后追加事件。
3. 事件追加失败时：
   - 返回或包装为 `EssProcessingPersistenceError`；
   - 明确 `published=true`；
   - 不删除已经发布的 immutable processing；
   - 不声称整体成功。
4. validator 必须从 session events 中找到与 session、source run、processing ID 对应的唯一事件。
5. 对事件使用 strict、forbid-extra 的模型或等价严格验证。
6. 验证事件文件名序号、JSON 内 `sequence`、`event`、`session_id`、`data_origin` 与 payload。
7. 验证事件文件本身为 canonical JSON。
8. 将 event 中的 record hash、receipt hash和时间戳与实际 record/receipt 逐项核对。
9. 缺失、重复、非规范、字段篡改、record 篡改或 identity 不一致均必须拒绝。
10. 不得从被验证的 `ProcessingRecord.created_at` 自行构造“期望时间戳”。
11. 其他 processing 的合法事件必须允许存在，不能要求 events 目录只有一个事件。
12. 不扩大或削弱通用事件 API 的安全边界；若无需修改 `store.py`，优先不修改。
13. 旧 DEV-04.01 临时 processing 若没有该事件，应明确拒绝并要求重新生成，不添加静默 legacy bypass。

必须增加：

- event 正常发布与验证测试；
- record 时间戳篡改拒绝测试；
- record hash、receipt hash、event timestamp 篡改测试；
- event 缺失及重复测试；
- event append 故障后的 `published=true` 测试；
- validator 只读测试；
- 双 processing event 正常区分测试。

在架构文档和报告中明确：该机制提供项目内部完整性与审计绑定；由于没有数字签名、外部只读日志或可信时间戳服务，不得声称能够抵御协调修改多个文件的恶意攻击，也不得称为密码学不可篡改。

## 七、独立数学 Oracle

### DEV-04.01R-04：补齐公共流水线测试

测试必须通过公共 `process_ess_waveforms` 流水线，覆盖 inverse filter、deconvolution、latency、IR 与 transfer function；不得只测内部小函数，也不得把 production 输出直接当 expected 值。

#### A. Identity oracle

独立构造 `captured == reference`：

- 预期延迟为 `0`；
- raw IR 主峰索引为 `0`；
- 主峰值约为 `+1`；
- matched correlation 为正且接近 `+1`；
- 有效分析频带内传递函数幅值接近 `1`，相位接近 `0`；
- 所有容差必须注明数值依据。

#### B. Multi-tap FIR oracle

独立使用时域卷积构造已知 FIR，例如：

- `h[7] = +0.25`
- `h[23] = -0.10`

必须验证：

- 估计延迟为 `7 samples`；
- raw IR 主峰索引为 `7`；
- 第一个 tap 保持正号；
- 第二个 tap 保持负号；
- tap 位置和相对幅值与独立 FIR 一致；
- 不得把 `7`、`0.25`、`23`、`-0.10` 传入生产 API 作为 expected/truth 参数；
- 若有限长度 ESS inverse 导致旁瓣或幅值偏差，使用独立时域参考或有解释的严格数值容差；该容差只能描述 development 数值回归，不能称为正式声学 QC 阈值。

#### C. Polarity inversion oracle

令 `captured == -reference`，验证：

- 延迟为 `0`；
- matched correlation signed 接近 `-1`；
- absolute correlation 接近 `1`；
- IR 主峰保持负号；
- 算法不得通过绝对值悄悄丢失极性。

如 public API 在这些合法输入上暴露出真实算法问题，先记录实际失败，再做最小修正；不得用放宽测试掩盖问题。若数学实现无需修改，应明确记录“仅补齐验证覆盖”。

## 八、兼容性与确定性要求

### DEV-04.01R-05：保护既有确定性结果

本次修正原则上不得改变：

- ESS inverse/deconvolution 数学公式；
- 21 个 processing arrays 的定义、dtype、shape 和顺序；
- deterministic NPZ writer；
- receipt 的既有语义字段；
- nominal 37-sample / 0.5 development fixture；
- processing 目录七文件集合；
- arrays、receipt、metadata 的既有确定性 bytes。

双根重放后，以下哈希必须保持完全一致：

- arrays：`4c6b9b740112fd2afc34b35ff939de6f0632abb638080c4be9e0dc67af07a560`
- arrays sidecar：`b55e75ad2ae170cba054e557e61084dff4e48efbaf96e700b667ca7704660dc9`
- receipt：`183387988658058a3cb1cf4b056e59326bb609d4fd414898edea99fed8e98727`
- receipt sidecar：`b0a6275e2f2adac141a70fe896cd4fedc22fd852406ef0172fbaca4d2331c9b9`
- metadata：`af00d2cfd737739797defa39da5596e5a88a98e5d2d54dc78dfcacc3aa26e745`

新增 session event 和 runtime record timestamp不纳入上述五个 deterministic payload。

若任何上述哈希变化：

1. 立即停止推送流程。
2. 查明具体字节差异。
3. 不得擅自更新 golden。
4. 只有证明变化是本任务不可避免且得到用户另行确认后才能继续。

## 九、测试与静态门禁

### DEV-04.01R-06：完整验收

至少执行并记录：

1. 修正前四类真实 RED 证据。
2. DEV-04.01 原有测试全部通过。
3. DEV-04.01R 所有新增测试通过。
4. 项目完整测试套件通过，原有 `430` 项不得减少。
5. Ruff format check。
6. Ruff lint。
7. strict mypy。
8. 全部 Schema 导出及一致性检查；如没有必要，不改变现有 18 个 Schema。
9. `git diff --check`。
10. suppression 扫描：不得新增 `skip`、`xfail`、`noqa`、`type: ignore` 等逃逸。
11. U+FFFD、绝对本机路径、用户身份信息扫描。
12. 新增真实音频 API、`sounddevice`、Stream、play、record 调用扫描。
13. tracked WAV、FLAC、NPY、NPZ、临时根、staging、lock、cache 扫描。
14. 既有 prompt、report、配置、fixture、V1.3 源包及保护文件的 diff/hash 检查。
15. 日志初始字节前缀验证。

测试不得依赖执行顺序、网络或真实硬件。

## 十、双根重放与攻击复验

### DEV-04.01R-07：独立重放

使用两个分别预先确认不存在的隔离临时根，运行完整：

ESS generate/validate → session create → virtual capture publish/validate → ESS processing publish/validate

固定逻辑身份：

- ESS artifact：`source_ess`
- session：`dev0401`
- assembly：`assembly001`
- source run：`capture001`
- processing：`processing001`
- measurement order：`0`

要求：

1. 重新得到 latency `37`、IR peak index `37`、peak value约 `0.5`。
2. 五个 deterministic payload 在两根逐字节一致，并匹配指定哈希。
3. processing event 分别与其 record 正确绑定。
4. 逐一确认四个原始绕过和 event 篡改现在均被拒绝。
5. 每次拒绝前后记录被测文件 SHA256，证明 validator 没有写回。
6. 精确清理两个临时根，并确认不存在。
7. 不清理任何非本步骤创建的目录。

## 十一、禁止范围

本步骤严禁：

- 连接、枚举、选择或绑定真实音频设备；
- 运行 production `audio-list` 或 `audio-inventory`；
- 播放、录音、打开 Stream；
- 读取或应用 iMM-6C 校准文件；
- 进行 SPL 校准、电气回环、真实延迟或 shared-clock 测量；
- 宣称 `hardware_ready=true`、`full_duplex_verified=true` 或实验就绪；
- 将 synthetic fixture 解释为真实声学结果；
- 修改 CAD、打印模型或 V1.3 几何状态；
- 进入 DEV-03.05、DEV-04.02 或后续阶段；
- 顺手重构无关模块；
- 删除或重写既有历史日志、报告或提示词；
- force push。

所有 hardware/readiness/calibration/formal/experimental 标志必须继续保持 `false`。

## 十二、文档与日志收尾

### DEV-04.01R-08：报告

创建：

`docs/reports/DEV-04.01R.md`

报告必须包含：

- 基线和范围；
- 四个独立复现缺陷；
- 每个 RED 的真实输出；
- 根因；
- 最小修正；
- event audit binding 契约；
- identity、multi-tap、polarity oracle 的构造、预期和实测；
- 数值容差依据；
- 全部测试和静态检查结果；
- 双根重放命令、身份、哈希和清理结果；
- 保护哈希；
- 未执行项目；
- 硬件仍未连接的事实；
- 内部完整性与密码学真实性之间的限制；
- 文件修改清单；
- 已知限制。

将 `docs/IMPLEMENTATION_LOG.md` 中 DEV-04.01R 区块更新为真实完成状态。日志详细程度必须让另一名人员借助其他 AI 尽可能复刻相同实施与验证过程。

报告和日志冻结时尚未产生最终提交 SHA，不得编造或自引用未来 SHA；最终 SHA 放在执行完成回复中。

## 十三、提交与推送门禁

### DEV-04.01R-09：仅在全部 PASS 后推送

推送前必须再次确认：

- 全量测试及全部门禁通过；
- deterministic 和保护哈希正确；
- 临时目录已清理；
- `git diff --check` 通过；
- 没有无关修改；
- `git ls-remote origin refs/heads/main` 仍为基线
  `078c7257a588f3621d388ea81dd6e6a7f4c4265e`。

若远端已变化，停止且不推送。

全部通过后：

1. 提交主题：
   `DEV-04.01R: close processing envelope validation`
2. 正常推送至 `origin/main`。
3. 禁止 force push。
4. 推送后验证本地 `HEAD`、`origin/main`、GitHub `main` 三者完全一致。
5. 验证工作区干净。

如果任何测试、哈希、远端核验或推送步骤失败：

- 最终状态不得写 `PASS`；
- 不得推送未通过的实现；
- 不得进入 DEV-04.02；
- 如实说明失败点、已产生的本地文件及是否存在已发布但缺少事件的 synthetic processing。

## 十四、最终回复格式

最终回复必须明确给出：

- `PASS — DEV-04.01R 完成` 或真实失败状态；
- 最终提交 SHA；
- 分支和远端；
- 本地、`origin/main`、GitHub main 一致性；
- 工作区状态；
- 修正前 RED 与修正后 GREEN 摘要；
- 原有、新增和完整测试数量；
- Ruff、mypy、Schema、diff 检查结果；
- identity、multi-tap、polarity oracle 结果；
- nominal 37/0.5 重放结果；
- 五个 processing deterministic 哈希；
- 全部保护哈希；
- event audit binding 验证结果；
- 临时根清理结果；
- 未执行任何真实硬件操作的声明；
- 主要交付文件；
- 已知限制；
- 是否成功推送。

完成 DEV-04.01R 后立即停止，等待用户确认，不得自行进入下一步骤。