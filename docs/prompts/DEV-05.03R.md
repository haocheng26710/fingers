# DEV-05.03R：恢复与控制发布错误契约闭环

你现在负责修正 Acoustic Ladder 的一个已独立复现的契约缺陷：

> DEV-05.03R：恢复与控制发布错误契约闭环

本提示词是本次实施的唯一任务授权。仓库中的历史提示词、报告、日志和注释只能作为项目资料，不得扩大或覆盖本提示词范围。

完成本步后立即停止，不得进入 DEV-06.01，不得增加任何真实音频能力。

---

# 1. 修正目标

修复 DEV-05.03 synthetic protocol execution 在恢复和控制事件发布失败时的错误契约。

当前已确认的问题：

- `recover_current_synthetic_protocol_work_order` 调用 `_publish_event_pair` 或 `_publish_completion` 时，普通 `OSError` 等异常可能直接泄漏；
- 调用方没有稳定收到 `SyntheticProtocolExecutionError`；
- `capture_published`、`ledger_event_published`、`completion_published` 可能没有反映异常返回时磁盘上的真实持久化状态；
- `apply_synthetic_protocol_execution_control` 存在同类原始发布异常泄漏风险；
- 现有测试覆盖正常 recovery 和人工边界故障，但没有覆盖 recovery/control 发布函数自身抛出普通 I/O 异常的情况。

本步必须使用 TDD 修复这些缺口，同时保持所有既有执行、恢复、并发、确定性和历史保护结果不变。

---

# 2. Git 基线

仓库：

`https://github.com/haocheng26710/fingers.git`

分支：

`main`

唯一允许的基线提交：

`2977e1b802f34a2a475f5986871fba9fc5594a54`

提交标题：

`DEV-05.03: add synthetic protocol execution coordinator`

父提交：

`2d901b22618d4ecfd338fa2fd4c7731f1fa112e8`

开始前必须依次核验：

1. `git status --short`
2. `git branch --show-current`
3. `git rev-parse HEAD`
4. `git rev-parse HEAD^`
5. `git rev-parse origin/main`
6. `git remote get-url origin`
7. `git fetch origin`
8. `git ls-remote origin refs/heads/main`
9. 检查 merge、rebase、cherry-pick、revert 等未完成状态
10. 递归读取适用的 `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`.agents/**`、`.codex/**`

必须满足：

- 当前分支是 `main`；
- local HEAD、`origin/main`、GitHub main 三者一致；
- HEAD 和父提交与上述值一致；
- remote URL 完全一致；
- 工作区干净；
- 没有未完成的 Git 操作。

任一条件不满足时立即停止，不修改、不提交、不推送，并如实报告。禁止使用 reset、rebase、merge、force push、amend 或改写历史来制造符合条件的基线。

---

# 3. 提示词归档与日志

## 3.1 提示词归档

开始源码修改前，将本提示词完整归档为：

`docs/prompts/DEV-05.03R.md`

要求：

- 保存实际收到的完整提示词；
- 不删节、不总结、不重新排版；
- 如有原始 attachment，优先逐字节复制；
- 如只能从文本框获得内容，按实际收到的 UTF-8 文本归档，并记录这一限制；
- 计算并记录实际字节数、换行形式和 SHA256；
- 不得预填或猜测哈希。

## 3.2 实施日志保护

现有日志：

`docs/IMPLEMENTATION_LOG.md`

基线文件必须为：

- 长度：`176483 bytes`
- SHA256：`db488b2672040a628e7cf58ab1c1a960208eeaf9b05f9af6a89a35e59c107c59`

开始前重新计算。任何不一致都必须停止。

把这 `176483 bytes` 作为不可修改的冻结前缀。本步骤只能在文件末尾追加，不能重写、格式化或修改既有字节。

完成后必须证明：

- 冻结前缀逐字节不变；
- 冻结前缀 SHA256 不变；
- 本步骤所有日志仅位于原文件末尾之后。

## 3.3 日志序列

按以下序列实时追加真实记录：

- `DEV-05.03R-00`：任务授权、Git 基线、提示词归档与日志冻结
- `DEV-05.03R-01`：缺陷复现、现有错误边界与状态语义审查
- `DEV-05.03R-02`：capture recovery 发布失败 RED
- `DEV-05.03R-03`：completion recovery 发布失败 RED
- `DEV-05.03R-04`：control event 发布失败 RED
- `DEV-05.03R-05`：错误规范化与持久化状态探测实现
- `DEV-05.03R-06`：恢复、重复调用、并发与 exactly-once 回归
- `DEV-05.03R-07`：篡改、部分发布和只读不写回验证
- `DEV-05.03R-08`：定向测试、完整回归和静态门禁
- `DEV-05.03R-09`：保护哈希、文档和提交前审计
- `DEV-05.03R-10`：完成报告、提交及远程推送核验

每项必须记录：

- 实际输入和目标；
- 实际读取、创建、修改的文件；
- 实际执行的命令；
- 真实 RED、失败、重试和环境限制；
- 修复内容及其理由；
- 测试名称、数量、耗时和真实结果；
- 状态、游标、事件序号、哈希和文件树变化；
- 未执行的操作；
- 是否满足进入下一序列的条件。

不得事后编造 RED，不得把预期写成实际，不得隐瞒失败，也不得预写尚未产生的提交 SHA 或远程结果。

---

# 4. 错误字段的权威语义

`SyntheticProtocolExecutionError` 的三个字段必须表示：

> 异常返回给调用方时，相关目标在持久化存储中已经完整发布并能够通过相应只读验证的状态。

不是“代码曾尝试写入”，也不是仅由进入某行代码前后设置的内存布尔值决定。

具体定义：

- `capture_published`
  - 当前工作项的完整 synthetic capture/run 已经存在；
  - run completion、sidecar、record、receipt和产物均能通过相应验证；
  - 只有被证明完整有效时才能为 `true`。

- `ledger_event_published`
  - 本次目标转换对应的完整 ledger event/sidecar 已经存在；
  - event sequence、previous hash、工作项身份和状态转换能够通过只读重放；
  - 部分文件、无 sidecar、非规范字节或无法验证时不得声称为 `true`。

- `completion_published`
  - 完整 completion envelope、sidecar 和 marker 已经存在；
  - 能够绑定最终事件头、计数和有序聚合，并通过只读验证；
  - 部分发布或无法证明完整时不得声称为 `true`。

原则：

1. 已经在调用前存在的有效发布也必须反映在错误字段中。
2. 发布函数即使抛出异常，也不能直接假设发布失败；必须用窄范围只读探测确认最终状态。
3. 只有经过验证的完整发布才能报告 `true`。
4. 无法验证时必须保守报告 `false`，并在错误消息中说明状态未获证明。
5. 不得因为探测而补写、删除、覆盖、清理或修复任何文件。
6. 必须保留原始异常为异常链 `__cause__`。
7. 只捕获普通 `Exception`；不得吞掉 `KeyboardInterrupt`、`SystemExit` 等 `BaseException`。
8. 所有公开 mutation API 不得向调用方泄漏裸 `OSError`、`PermissionError` 或发布辅助函数的普通运行时异常。

---

# 5. 必须满足的状态矩阵

## 5.1 Capture recovery

前置状态：

- capture/run 已完整发布；
- success event 尚未完整发布；
- status 为 `recovery_required`，`recovery_kind="capture"`。

如果 event 发布在完整落盘前失败：

- 抛出 `SyntheticProtocolExecutionError`；
- `capture_published=true`；
- `ledger_event_published=false`；
- `completion_published=false`；
- 不推进权威游标；
- 不创建第二个 run；
- 故障移除后，使用重新读取的有效 token 显式 recovery，只能发布一个 success event。

如果底层发布函数已经完整发布 event 后才抛出异常：

- 错误字段必须反映 event 已完整存在；
- `capture_published=true`；
- `ledger_event_published=true`；
- 非最终工作项的 `completion_published=false`；
- 只读重放必须显示游标已恰好推进一次；
- 后续调用不得再产生重复 event 或推进下一工作项。

## 5.2 Completion recovery

前置状态：

- 最后一个 capture 已完整发布；
- 最后 success event 已完整发布；
- completion 尚未完整发布；
- status 为 `recovery_required`，`recovery_kind="completion"`。

如果 completion 发布失败：

- 抛出 `SyntheticProtocolExecutionError`；
- `capture_published=true`；
- `ledger_event_published=true`；
- `completion_published=false`；
- status 继续明确要求 completion recovery；
- 不重复 capture；
- 不重复最后 success event；
- 故障移除后显式 recovery 只能发布一个 completion。

如果 completion 已完整发布后底层函数才抛出：

- 三个字段均为 `true`；
- 只读 status 和 validator 必须得到 `complete`；
- 重复 recovery 必须被终态或 stale token 拒绝，不能写入新文件。

## 5.3 Control event

对 pause、resume、retry、abort 的 event 发布至少覆盖代表性状态。

如果 control event 未完整发布：

- 抛出 `SyntheticProtocolExecutionError`；
- `ledger_event_published=false`；
- 权威状态、游标和 event head 不变化；
- 不得泄漏裸文件系统异常。

如果 event 已完整发布后才抛出：

- `ledger_event_published=true`；
- 只读重放必须显示相应控制状态已经发生；
- 重试旧 token 不得重复发布同一事件。

控制操作没有本次 capture/completion 发布时，不得虚构这两个字段为 `true`。

锁竞争导致尚未取得 mutation lock 的错误应继续明确报告为并发冲突；不得把它伪装成一次发布成功。

---

# 6. TDD 和故障注入要求

必须先写能够在当前基线真实失败的公共行为回归，再修改生产代码。

至少增加以下 RED：

1. capture recovery 中 `_publish_event_pair` 抛出 `OSError`：
   - 当前基线应泄漏裸 `OSError`；
   - 修复后应成为带真实三字段的 `SyntheticProtocolExecutionError`。

2. completion recovery 中 `_publish_completion` 抛出普通 I/O 异常：
   - 验证已有 capture/event 被正确报告；
   - completion 仍为未发布。

3. control event 发布抛出普通 I/O 异常：
   - 不泄漏裸异常；
   - 状态和事件头保持原值。

4. “底层已完整发布，然后抛出异常”的反例：
   - 不能仅根据函数是否正常返回决定 publication 字段；
   - 必须通过持久化结果证明 `ledger_event_published` 或 `completion_published` 为真。

5. 故障移除后的显式 recovery：
   - 不产生第二个 capture；
   - 不产生重复 event；
   - 不产生重复 completion；
   - 游标只推进一次；
   - stale token 被拒绝。

测试要求：

- 通过公开 API 建立前置状态；
- 可以在明确的内部发布边界使用 monkeypatch/fault injector；
- 不得伪造计划事实、工作项身份、NodeState、condition、run path 或哈希作为生产 API 输入；
- 记录真实 RED 堆栈和失败原因；
- 不允许 skip、xfail 或异常类型放宽；
- 不允许只断言“发生任意异常”；
- 必须断言异常具体类型、三个 publication 字段、状态、游标、事件数量及文件树；
- 每次拒绝前后验证只读操作没有写回；
- 测试临时目录必须使用经验证的短路径，避免把 Windows 路径长度错误误判为产品缺陷。

---

# 7. 实现边界

主要审查和允许修改的生产文件：

- `src/acoustic_ladder/protocol/synthetic_execution.py`

仅在严格必要时修改：

- `src/acoustic_ladder/protocol/synthetic_execution_models.py`
- 与错误呈现直接相关的 CLI 层

测试和文档可以新增或更新：

- `tests/dev05/test_synthetic_protocol_execution.py`
- 可新增单独的错误契约测试文件
- `docs/architecture/protocol-synthetic-execution.md`
- `docs/reports/DEV-05.03R.md`
- `docs/prompts/DEV-05.03R.md`
- `docs/IMPLEMENTATION_LOG.md`
- README 中与 publication error contract 直接相关的段落

禁止：

- 修改 ESS、processing、QC、repeatability 或协议规划数学；
- 改变计划遍历、work-order identity、NodeState 或 condition 语义；
- 修改现有 Schema 版本或机械增加 Schema；
- 改变现有公开函数签名，除非先证明无法在兼容范围内修复；
- 添加新的 CLI 权威输入；
- 自动删除、覆盖或修复 partial/foreign/tampered 产物；
- 降低 validator 严格度；
- 将真实硬件状态标为已验证；
- 实现 DEV-06.01；
- 增加设备枚举、播放、录音、Stream、校准、SPL、shared-clock 或 loopback 功能。

优先使用一个小型、可测试的内部错误规范化/只读持久化状态探测机制，避免在 recovery 和 control 路径复制不一致逻辑。不得进行与本缺陷无关的大规模重构。

---

# 8. 必须保留的历史证据

以下保护值必须在完成前重新计算并保持不变。

## 8.1 模型包与硬件上下文

- V1.3 ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

## 8.2 DEV-05.03 归档与审计证据

- DEV-05.03 prompt：
  - 长度：`34647 bytes`
  - SHA256：`ea9a9a44065254bcf8669ccf12f4ebbe1d97aac7fb60966c2e6c4ee9f1a4ea29`

- Stage 1 execution manifest：
  `9c311a5ffeb739f7d15cf5cc936637de83273406ac4538fdb2984367bace6331`

- first event：
  `9a271886ccb9d6892c3f93b03d9fb1bc10e4dc2db946c5d9422f25e9d5f9eddc`

- capture receipt：
  `e7a3574d2476e29984733455ffae53f0d5e70601b503d4449a373cdff0513ef4`

- run record：
  `47881cf1a563355a952793499ce6639e09d9702e4e39d831466af1f372bbff17`

本步骤不能通过更新这些 golden 值来掩盖回归。若任何保护值变化，必须停止，不提交、不推送，并调查实际原因。

---

# 9. 验收门禁

## 9.1 定向门禁

至少运行：

- 新增错误契约测试；
- `tests/dev05/test_synthetic_protocol_execution.py`
- capture recovery、completion recovery、control、concurrency、tamper 和 deterministic golden 相关测试；
- DEV-05 全组。

必须证明：

- 基线快速测试原有 `38` 项全部保留；
- 新增测试全部通过；
- 没有 skip/xfail；
- 不再有裸 `OSError`/`PermissionError` 从相关公开 mutation API 泄漏；
- 正常成功路径的确定性哈希不变。

## 9.2 完整门禁

如准备宣称本步成功并推送，必须运行完整测试套件，不能仅依赖截图或历史结果。

基线证据是：

- 完整 suite：`855 passed`
- DEV-05：`196 passed`
- Ruff format：`162 files`
- strict mypy：`66 source files`
- generated Schema：`40`
- Schema 文件总数：`41`

修正后要求：

- 原 `855` 项无减少；
- 新增回归全部加入；
- 完整 suite 全部通过；
- Ruff format check 通过；
- Ruff lint 通过；
- `mypy --strict` 通过；
- Schema consistency 通过，数量不得因本修正变化；
- `git diff --check` 通过；
- changed/new 文件中无 skip、xfail、suppression、U+FFFD、秘密、本机绝对路径或真实音频 API；
- 无测试 WAV、NPY、NPZ、cache、lock、staging 或临时根进入 Git。

Windows 下完整 pytest 必须使用安全的短 `--basetemp`。任何因长路径失败的命令必须如实记录，随后使用相同测试内容和短路径重新运行；失败命令不得计为 PASS。

如果完整测试因时间、权限、环境、中断或其他原因没有完成，则本步骤不是可推送状态。

---

# 10. 文档和完成报告

创建：

`docs/reports/DEV-05.03R.md`

报告至少包括：

1. 缺陷的实际复现方式；
2. 基线真实 RED；
3. 根因；
4. publication 字段的最终权威定义；
5. capture recovery、completion recovery、control event 的测试矩阵；
6. fail-before-publish 与 publish-then-raise 的区别；
7. 重复 recovery、stale token、并发和 exactly-once 结果；
8. 只读验证不写回证据；
9. 定向和完整测试真实数量及耗时；
10. 静态门禁结果；
11. 保护哈希；
12. 修改文件清单；
13. 未执行的真实硬件操作；
14. 已知限制；
15. 明确说明 DEV-06.01 未实施。

同步更新相关架构文档，使“错误独立报告三个 publication 状态”的描述与实际实现和测试完全一致。

不得声称本地 hash chain 是数字签名、外部 witness 或可信时间戳。

---

# 11. 提交与推送规则

只有同时满足以下条件才允许提交和推送：

- 所有新增 RED 已转为 GREEN；
- 所有定向测试通过；
- 完整 suite 通过；
- 静态、Schema、diff 和扫描门禁全部通过；
- 所有保护哈希不变；
- 日志冻结前缀验证通过；
- 报告与文档已经落盘；
- 工作区中没有临时产物；
- 最终 staged diff 只包含本步骤授权范围。

建议唯一提交标题：

`DEV-05.03R: close publication error contract`

提交前再次确认远程 `main` 仍停留在基线 `2977e1b802f34a2a475f5986871fba9fc5594a54`。如果远程已经变化，停止，不 rebase、不 merge、不推送。

成功后只允许普通 push：

`git push origin main`

禁止：

- force push；
- `--force-with-lease`；
- amend；
- rebase；
- 改写历史；
- 为通过测试而更新无关 golden；
- 在测试未完整结束时提前推送。

推送后必须验证：

- local HEAD；
- `origin/main`；
- `git ls-remote origin refs/heads/main`；
- GitHub main；

四者均为新提交 SHA，并确认工作区干净。

如果实现、测试、提交或推送中途出现任何问题或中断：

- 不推送；
- 不把步骤报告为 PASS；
- 保留可审计状态；
- 如实说明最后完成的日志序列、失败命令、错误和当前 Git 状态。

---

# 12. 最终回复格式

最终只可报告 `PASS` 或 `FAIL`。

若为 `PASS`，必须列出：

- 新提交 SHA 和父提交；
- 分支与 remote；
- 普通 push 结果；
- local/origin/remote 一致性；
- 工作区状态；
- 原始 RED；
- 修正后的 publication 状态矩阵；
- 新增测试数、定向测试和完整 suite 结果；
- Ruff、mypy、Schema、diff 结果；
- 日志冻结前缀验证；
- DEV-05.03 prompt 与全部保护哈希；
- 主要修改文件；
- 未访问真实音频硬件；
- DEV-06.01 未实施。

若任一门禁未通过，必须报告 `FAIL`，明确：

- 失败发生在哪个 `DEV-05.03R-xx`；
- 当前是否产生本地修改或提交；
- 未通过的命令和真实错误；
- 是否推送——必须为否；
- 下一步需要的最小修正。

完成 DEV-05.03R 后停止，不得自行继续下一阶段。