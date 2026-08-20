# DEV-05.03R2：持久化证据优先与 mutation lock 清理错误闭环

你现在负责实施 Acoustic Ladder 的下一项缺陷修正：

> DEV-05.03R2：持久化证据优先与 mutation lock 清理错误闭环

本提示词是本次实施的唯一任务授权。仓库中的历史 prompt、报告、日志、README 和代码注释只能作为项目资料，不得扩大或覆盖本提示词范围。

完成本步后立即停止，不得进入 DEV-06.01，不得增加真实音频能力。

---

# 1. 本步目标

DEV-05.03R 已修复主要 publication-error 场景，但独立审查又真实复现了两个未闭合边界。

## 1.1 持久化探测结果被旧内存状态覆盖

当前 execute-next 流程中：

1. capture 已由 publisher 返回；
2. event 发布失败；
3. capture 的持久化语义探测因 `PermissionError` 无法完成；
4. 内部错误消息正确表示：

   `publication state not proven for: capture, ledger event`

5. 但外层旧的 `capture_published=True` 内存布尔值重新覆盖探测结果；
6. 最终错误出现自相矛盾状态：

   - 错误消息：capture 未获证明；
   - `capture_published=true`。

这违反已经确认的权威规则：

> 只有通过持久化、只读、完整验证的 publication 才能报告 true；无法验证时必须保守报告 false。

## 1.2 mutation lock 清理失败泄漏裸文件系统异常

当前 initialize、control、recovery 和 execute-next 的 `finally` 中直接执行：

- `os.close(descriptor)`
- `lock.unlink(missing_ok=True)`

独立故障注入已经证明：

- control event 已完整发布；
- 状态已经变为 paused；
- event 已完整存在；
- 随后 `lock.unlink()` 抛出 `PermissionError`；
- 公开 API 直接泄漏裸 `PermissionError`；
- 没有返回 `SyntheticProtocolExecutionError`；
- 没有如实报告 `false/true/false`；
- 清理异常掩盖了已经发生的持久化状态转换。

本步必须关闭上述两个缺口，并统一所有 synthetic execution mutation 的锁生命周期错误契约。

---

# 2. Git 基线

目标仓库：

`https://github.com/haocheng26710/fingers.git`

目标分支：

`main`

唯一允许的基线提交：

`56c1cbbbd8d8dab8dfd7d82b62cd9890f2978815`

基线提交标题：

`DEV-05.03R: close publication error contract`

父提交：

`2977e1b802f34a2a475f5986871fba9fc5594a54`

开始前必须执行并记录：

1. `git status --short`
2. `git branch --show-current`
3. `git rev-parse HEAD`
4. `git rev-parse HEAD^`
5. `git rev-parse origin/main`
6. `git remote get-url origin`
7. `git fetch origin`
8. `git ls-remote origin refs/heads/main`
9. 检查 merge、rebase、cherry-pick、revert 等未完成状态
10. 递归读取适用的 `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`.agents/**` 和 `.codex/**`

必须满足：

- 分支为 `main`；
- local HEAD、`origin/main`、GitHub main 均为上述基线；
- 父提交正确；
- remote URL 完全正确；
- 工作区干净；
- 没有未完成的 Git 操作。

任一条件不满足时：

- 立即停止；
- 不修改；
- 不提交；
- 不推送；
- 如实报告实际状态。

禁止使用 merge、rebase、reset、checkout 覆盖、amend、force push 或任何改写历史的方式制造基线一致。

---

# 3. Prompt 归档与日志保护

## 3.1 Prompt 归档

开始源码修改前，将本提示词完整归档为：

`docs/prompts/DEV-05.03R2.md`

要求：

- 尽可能保存实际收到的原始字节；
- 如存在 attachment，优先读取 attachment 原始字节；
- 如只能从文本框获取，按实际收到的 UTF-8 文本保存并记录限制；
- 不删节、不总结、不改写、不重新排版；
- 记录实际字节数、换行形式、末尾换行状态和 SHA256；
- 不得预填或猜测最终哈希。

## 3.2 Implementation log 冻结前缀

现有：

`docs/IMPLEMENTATION_LOG.md`

开始前必须重新确认：

- 当前长度：`191352 bytes`
- 当前 SHA256：`ab6f85b5b95bffc5f12f7b4678a39992ea2e976fc2f01ebb5352888ffb0fb9aa`

把这 `191352 bytes` 作为本步骤不可修改的冻结前缀。

要求：

- 只能在文件末尾追加；
- 不修改、格式化、移动、删除或重写任何既有字节；
- 完成后重新读取前 `191352 bytes`；
- 证明逐字节不变；
- 重新计算前缀 SHA256，必须仍为上述值。

任何不一致都必须停止，不提交、不推送。

## 3.3 日志序列

按以下序列实时追加真实记录：

- `DEV-05.03R2-00`：任务授权、Git 基线、prompt 归档和日志冻结
- `DEV-05.03R2-01`：两个独立审查缺陷的本地复现
- `DEV-05.03R2-02`：持久化探测失败 RED
- `DEV-05.03R2-03`：lock unlink/close 清理失败 RED
- `DEV-05.03R2-04`：权威 publication evidence 传播实现
- `DEV-05.03R2-05`：统一 mutation lock 生命周期实现
- `DEV-05.03R2-06`：组合错误、BaseException 和 stale-lock 回归
- `DEV-05.03R2-07`：重复调用、并发、exactly-once 和只读不写回
- `DEV-05.03R2-08`：定向测试、完整测试和静态门禁
- `DEV-05.03R2-09`：保护哈希、文档和提交前审计
- `DEV-05.03R2-10`：完成报告、提交、普通推送与远程核验

每项日志必须记录：

- 输入和目标；
- 实际读取、创建和修改的文件；
- 实际运行的命令；
- 真实 RED、异常栈、失败和环境限制；
- 修复及理由；
- 测试名称、数量、耗时和真实结果；
- publication 字段、状态、游标、event sequence、lock 状态和文件树；
- 未执行的操作；
- 是否满足进入下一序列的条件。

不得事后编造 RED，不得把预期结果写成实际结果，不得预写测试数量、提交 SHA 或推送结果。

---

# 4. 已冻结的研究与安全边界

以下边界不可改变：

- 项目仍是 Acoustic Ladder V1.3 校准后圆形主管版本；
- manifest 仍为 `provisional`；
- 尚未 geometry-locked；
- 尚未 experiment-ready；
- 当前没有连接任何真实扬声器、耳机、麦克风、声卡或实验装置；
- 不知道最终 Host API、输入索引、输出索引和通道映射；
- 不执行真实设备枚举；
- 不播放；
- 不录音；
- 不打开 Stream；
- 不执行校准、SPL、shared-clock 或电气 loopback；
- 不形成正式阈值、pass/fail、实验结论或听力安全建议；
- 所有数据继续为 development synthetic；
- 不实施 DEV-06.01。

---

# 5. Publication evidence 的权威传播规则

## 5.1 权威来源

三个公开字段：

- `capture_published`
- `ledger_event_published`
- `completion_published`

必须由异常返回时的持久化事实和只读验证决定。

不得以以下内容作为最终权威依据：

- publisher 曾经正常返回；
- 已执行到某行代码；
- 本地变量曾被设为 `True`；
- 内存中的预期 event/completion；
- 文件名存在但未验证；
- `RUN_COMPLETE` 或 marker 单独存在；
- 发布操作曾被调用。

只有完整、规范且通过对应语义验证时才能为 `true`。

## 5.2 无法证明时的行为

如果探测因为以下原因不能完成：

- `PermissionError`
- `OSError`
- 文件缺失；
- sidecar 缺失；
- 非规范字节；
- partial publication；
- foreign/tampered artifact；
- 语义 replay 失败；
- 状态或 event head 不一致；

则相关字段必须为 `false`。

错误消息必须说明哪些 publication 未获证明。

不得出现：

- 消息称“not proven”，字段却为 `true`；
- 内部 normalized error 全 false，外层又用旧内存布尔值覆盖；
- 通过“至少一个字段为 true”判断错误是否已经规范化。

必须使用结构上明确的机制区分：

- 已经完成持久化探测的 normalized publication error；
- 尚未完成探测的普通领域错误。

可采用但不限于：

- 私有 evidence/result 对象；
- 私有 normalized-error 标记或子类；
- 在最外层 mutation 边界统一执行一次探测；
- 明确的三态内部模型：verified true / proven false / unverified。

公开字段仍保持 bool；内部 `unverified` 最终必须保守映射为 `false`，并通过消息说明。

不得仅根据三个 bool 是否存在任意 `true` 判断是否需要重新包装。

---

# 6. Mutation lock 生命周期契约

适用范围：

1. execution store initialize；
2. control mutation；
3. recovery mutation；
4. execute-next mutation。

必须统一处理：

- lock acquisition；
- descriptor close；
- lock unlink；
- mutation 主体异常；
- publication 异常；
- cleanup 异常；
- 主体异常与 cleanup 异常同时发生。

## 6.1 获取锁

只有在取得 mutation lock 之前发生的 `FileExistsError` 才可报告为：

`already in progress`

publisher、validator 或 cleanup 中的同名异常不得误报为锁竞争。

`PermissionError`、`OSError` 等锁获取异常必须规范化为项目领域错误，不得泄漏裸异常。

## 6.2 清理锁

`os.close()` 与 `lock.unlink()` 均视为可能失败的 I/O 操作。

要求：

- 任一失败都不得泄漏裸 `OSError` 或 `PermissionError`；
- 不得让 cleanup 异常静默覆盖已经发生的 publication；
- 不得让旧的 mutation 主体异常被无记录地丢失；
- 不得谎称 lock 已删除；
- 不得使用强制删除、递归删除、权限修改或兜底覆盖；
- lock 删除失败时应保留实际 lock 文件，供人工审计；
- read-only status/validation 仍不得修复或删除 stale lock；
- 后续 mutation 应明确被现存 lock 拒绝；
- 清除故障后，只能由明确、受控且符合既有安全边界的操作处理，不得在本步骤新增自动 stale-lock takeover。

## 6.3 清理失败后的 publication 状态

如果 mutation 主体已经完整发布，随后 lock cleanup 失败，领域错误必须反映持久化事实。

代表性矩阵：

| 操作 | 已持久化事实 | capture | event | completion |
|---|---|---:|---:|---:|
| control event 成功，unlink 失败 | control event verified | false | true | false |
| capture recovery event 成功，unlink 失败 | capture + event verified | true | true | false |
| execute-next 非最终项成功，unlink 失败 | capture + event verified | true | true | false |
| completion recovery 成功，unlink 失败 | capture + event + completion verified | true | true | true |
| execute-next 最终项全部成功，unlink 失败 | capture + event + completion verified | true | true | true |
| initialize envelope 成功，unlink 失败 | base envelope verified | false | false | false |

initialize 没有对应的 capture/event/completion 字段，因此三个字段保持 false；错误消息必须明确说明：

- initialization/base envelope 已完整发布；
- mutation lock cleanup 失败；
- lock 是否仍存在。

不得为 initialize 虚构 capture/event/completion。

## 6.4 同时发生主体错误和 cleanup 错误

必须同时保留两类事实：

- mutation/publication 的原始失败；
- lock cleanup 的失败。

要求：

- 不得只剩裸 cleanup 异常；
- 不得把主体失败伪装成成功；
- 错误消息必须包含两者；
- `__cause__` 必须稳定保留一个明确的原始失败，另一个错误至少以结构化消息或异常上下文保留；
- publication 字段仍由最终持久化探测决定；
- 不能因为 cleanup 失败而跳过必要的只读 evidence 探测；
- 不能因为 evidence 探测失败而回退到内存布尔值。

---

# 7. 必须先建立的真实 RED

开始修改生产代码前，至少建立以下公共行为测试。

## 7.1 探测失败后不得被内存状态覆盖

场景：

1. initialize active execution；
2. execute-next 正常完成 capture publication；
3. 第一次 capture semantic replay 成功；
4. event publisher 抛出 `OSError`；
5. 错误处理阶段的 capture durability probe 抛出 `PermissionError`。

当前基线真实错误表现应被记录：

- 消息包含 capture 未获证明；
- 但 `capture_published` 错误地为 true。

修复后必须为：

- `capture_published=false`
- `ledger_event_published=false`
- `completion_published=false`
- 消息明确 capture/event 未获证明
- 不得泄漏裸异常。

还必须增加一个 capture 实际存在但 semantic validation 失败的反例，证明“存在”不等于“已验证发布”。

## 7.2 Control lock unlink 失败

场景：

1. pause event 完整发布；
2. 状态已经能够只读重放为 paused；
3. `lock.unlink()` 抛出 `PermissionError`。

当前基线应真实泄漏裸 `PermissionError`。

修复后要求：

- 抛出 `SyntheticProtocolExecutionError`；
- 原 cleanup 异常保留为 cause 或明确上下文；
- publication 矩阵为 `false/true/false`；
- paused event 只有一个；
- 游标不变；
- lock 文件仍存在；
- read-only status 不删除 lock；
- 后续 mutation 明确拒绝且不新增 event。

## 7.3 其他 lock cleanup 路径

至少覆盖：

- initialize unlink 失败；
- execute-next unlink 失败；
- capture recovery unlink 失败；
- completion recovery unlink 失败；
- 代表性的 `os.close()` 失败；
- mutation 主体失败后 cleanup 又失败；
- event publish-then-raise 后 cleanup 又失败；
- completion publish-then-raise 后 cleanup 又失败。

测试必须验证：

- 具体领域异常类型；
- `__cause__` 或上下文；
- publication 三字段；
- execution state；
- cursor；
- event sequence；
- run/event/completion 数量；
- lock 文件是否存在；
- 调用前后文件树；
- read-only status/validator 不写回；
- stale token 和重复调用不会创建第二份产物。

## 7.4 BaseException

保留并扩展既有 `KeyboardInterrupt` 测试：

- 不得将 `BaseException` 转换为普通领域错误；
- 仍应尝试正常资源清理；
- 如果正常清理成功，lock 不得残留；
- 不允许为了测试方便捕获全部 `BaseException`。

---

# 8. 实现范围

主要允许修改：

- `src/acoustic_ladder/protocol/synthetic_execution.py`

测试：

- 保留 `tests/dev05/test_synthetic_execution_publication_errors.py`
- 建议新增独立的 `tests/dev05/test_synthetic_execution_lock_cleanup_errors.py`
- 可对既有测试做最小直接补充

文档：

- `docs/prompts/DEV-05.03R2.md`
- `docs/reports/DEV-05.03R2.md`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/architecture/protocol-synthetic-execution.md`
- README 中与本错误契约直接相关的段落

只有严格必要时才允许修改其他文件。

禁止：

- 修改公共模型或 Schema 版本；
- 增加 Schema；
- 改变公开函数签名；
- 改变 plan、condition、NodeState 或 work-order identity；
- 修改 ESS、processing、QC、repeatability、DSP、fixture 或 reference；
- 降低 validator 严格度；
- 自动修复 partial、foreign 或 tampered 文件；
- 自动接管或强制删除 stale lock；
- 添加新 CLI 权威参数；
- 大规模重构与本缺陷无关的代码；
- 实现 DEV-06.01；
- 使用真实音频 API。

优先建立一个小型、可测试的 mutation lifecycle/evidence 机制，避免 initialize、control、recovery 和 execute-next 各自复制不同的异常处理。

---

# 9. 既有测试基线

基线提交报告并锁定：

- DEV-05.03R 新增错误契约：`15 passed`
- 新增 + 原快速测试：`53 passed`
- recovery/concurrency/tamper 定向：`20 passed`
- DEV-05：`211 passed`
- 完整 suite：`870 passed`
- Ruff format：`165 files`
- Ruff lint：PASS
- strict mypy：`66 source files`
- generated Schema：`40`
- Schema 文件总数：`41`
- `git diff --check`：PASS
- 无 skip、xfail、noqa、type-ignore

本步骤最终必须满足：

- 原 `870` 项无减少；
- 新增 R2 测试全部加入并通过；
- 不得修改历史测试来放宽断言；
- 不得使用 skip、xfail、noqa 或 type-ignore 规避问题；
- 不得只断言“发生某种异常”；
- 必须断言具体错误类型、publication 字段和持久化状态。

Windows 下所有长测试必须使用经过验证的短 `--basetemp`。路径长度导致的失败必须如实记录，并使用相同测试内容和短路径重跑，失败命令不得计为 PASS。

---

# 10. 完整验收门禁

准备宣称成功前必须运行：

1. 新增 R2 定向测试；
2. DEV-05.03R 的15项错误契约测试；
3. 原快速38项；
4. recovery/concurrency/tamper 定向组合；
5. DEV-05 全组；
6. 完整 pytest suite；
7. Ruff format check；
8. Ruff lint；
9. strict mypy；
10. Schema consistency；
11. `git diff --check`；
12. changed/new 文件扫描；
13. 临时产物扫描；
14. 所有保护哈希复算。

要求：

- 全部通过；
- 无 skip/xfail；
- 无裸 `OSError`、`PermissionError` 从相关公开 mutation API 泄漏；
- 无消息与 publication 字段自相矛盾；
- read-only API 不删除 lock、不修复文件、不创建 staging；
- 成功路径确定性哈希不变；
- Git 中没有测试 WAV、NPY、NPZ、cache、lock、staging 或临时根。

如完整套件因时间、中断、权限或环境问题未完成，则不得提交和推送。

---

# 11. 保护哈希

完成前必须重新计算并保持以下值不变。

## 11.1 模型与硬件上下文

- V1.3 ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

## 11.2 Prompt 保护

DEV-05.03 prompt：

- 长度：`34647 bytes`
- SHA256：`ea9a9a44065254bcf8669ccf12f4ebbe1d97aac7fb60966c2e6c4ee9f1a4ea29`

DEV-05.03R prompt：

- 长度：`19199 bytes`
- SHA256：`48e9af1e92268778112565aead578bec76b87b861c61bf372344ca6b5fd3d0f9`

## 11.3 Stage 1 审计证据

- execution manifest：
  `9c311a5ffeb739f7d15cf5cc936637de83273406ac4538fdb2984367bace6331`

- first event：
  `9a271886ccb9d6892c3f93b03d9fb1bc10e4dc2db946c5d9422f25e9d5f9eddc`

- capture receipt：
  `e7a3574d2476e29984733455ffae53f0d5e70601b503d4449a373cdff0513ef4`

- run record：
  `47881cf1a563355a952793499ce6639e09d9702e4e39d831466af1f372bbff17`

不得更新 golden 值来掩盖变化。任何保护哈希不一致都必须停止，不提交、不推送。

---

# 12. 报告与架构文档

创建：

`docs/reports/DEV-05.03R2.md`

报告至少包含：

1. 两个独立审查缺陷的真实复现；
2. 真实 RED 堆栈和结果；
3. 内存布尔值覆盖持久化证据的根因；
4. lock cleanup 异常泄漏的根因；
5. 最终 evidence 传播机制；
6. initialize/control/recovery/execute-next 的统一锁生命周期；
7. unlink、close、主体错误加 cleanup 错误的测试矩阵；
8. publication 字段的最终结果；
9. lock 保留、status、stale token 和 exactly-once 结果；
10. BaseException 行为；
11. read-only 不写回证据；
12. 定向与完整测试的真实数量和耗时；
13. Ruff、mypy、Schema、diff 和扫描结果；
14. prompt/log 冻结前缀和保护哈希；
15. 修改文件清单；
16. 未执行的真实硬件操作；
17. 已知限制；
18. DEV-06.01 未实施。

同步更新架构说明，明确：

- 持久化证据优先于内存布尔值；
- 无法验证映射为 false；
- cleanup error 不得掩盖 publication；
- stale lock 不会被只读 API 自动清理；
- hash chain 不是数字签名、外部 witness 或可信时间戳。

---

# 13. 提交与推送

只有全部门禁通过后才允许提交。

建议唯一提交标题：

`DEV-05.03R2: preserve durable evidence across lock cleanup`

提交前必须再次：

1. `git fetch origin`
2. 核验远程 main 仍为 `56c1cbbbd8d8dab8dfd7d82b62cd9890f2978815`
3. 检查 staged diff 仅包含授权范围
4. 复跑必要的文档后轻量门禁
5. 确认没有临时文件和测试根
6. 验证 implementation log 冻结前缀

远程基线发生变化时立即停止，不 merge、不 rebase、不提交、不推送。

仅允许普通 push：

`git push origin main`

禁止：

- force push；
- `--force-with-lease`；
- amend；
- rebase；
- merge；
- 改写历史；
- 测试未完成时提前推送。

推送后必须验证：

- local HEAD；
- `origin/main`；
- `git ls-remote origin refs/heads/main`；
- GitHub main；

四者必须完全一致，并确认工作区干净。

如果实施、测试、提交或推送中途发生任何问题或中断：

- 不推送；
- 不报告 PASS；
- 不隐瞒失败；
- 保留可审计状态；
- 报告最后完成的日志序列、失败命令、错误和当前 Git 状态。

---

# 14. 最终回复格式

最终只能报告 `PASS` 或 `FAIL`。

若为 `PASS`，必须列出：

- 新提交 SHA 和父提交；
- 分支与 remote；
- 普通 push 结果；
- local/origin/GitHub 一致性；
- 工作区与临时根状态；
- 两个原始审查 RED；
- 新增 RED/GREEN 测试；
- 最终 publication/cleanup 矩阵；
- lock 遗留与 read-only 行为；
- 定向测试、DEV-05 和完整 suite 结果；
- Ruff、mypy、Schema、diff 结果；
- implementation log 冻结前缀验证；
- DEV-05.03、DEV-05.03R、DEV-05.03R2 prompt 哈希；
- 全部保护哈希；
- 修改文件；
- 未访问真实音频硬件；
- DEV-06.01 未实施。

若任一门禁失败，必须报告 `FAIL`，并明确：

- 失败发生在哪个 `DEV-05.03R2-xx`；
- 当前是否存在本地修改或提交；
- 真实失败命令和错误；
- publication 和 lock 的实际状态；
- 是否推送——必须为否；
- 下一步最小修正。

完成 DEV-05.03R2 后停止，不得自行进入下一阶段。