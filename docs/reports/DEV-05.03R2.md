# DEV-05.03R2 实施报告

## 结果与范围

DEV-05.03R2 在唯一基线 `56c1cbbbd8d8dab8dfd7d82b62cd9890f2978815` 上闭合 durable publication evidence 被旧内存状态覆盖，以及 initialize/control/recovery/execute-next mutation lock 清理异常泄漏两个缺陷。公共函数签名、Pydantic 模型、Schema、plan/condition/NodeState/work-order identity 和成功路径确定性均未改变。

本步没有枚举、连接、选择、播放、录音或校准真实音频设备，没有打开 Stream，没有执行 SPL、shared-clock 或 loopback，也没有实施 DEV-06.01。

## 独立缺陷复现与真实 RED

第一项 RED 通过公共 execute-next 完整发布 capture，使第一次 semantic replay 成功；随后 event publisher 抛 `OSError`，错误处理中的第二次 capture replay 注入 `PermissionError`。基线错误消息正确写出 `publication state not proven for: capture, ledger event`，但外层因旧内存 `capture_published=True` 再次包装，最终字段仍为 true。命令真实得到 `1 failed in 1.46s`。

第二项 RED 通过公共 pause 完整发布 control event 后，仅对该 execution 的 transition lock 注入 `Path.unlink()` `PermissionError`。基线从 `finally` 裸泄漏该异常，无法返回 publication 字段；命令真实得到 `1 failed in 1.07s`。两个 RED 均在修改生产代码前建立。

另一个反例在 capture 已有 `RUN_COMPLETE` 和 receipt 文件后使 receipt 变为非规范 JSON。即使路径存在，semantic replay 失败仍得到 false/false/false；连续 status 均拒绝且文件树不写回，证明“存在”不等于已验证 publication。

## 根因与最终 evidence 机制

旧 execute-next 用“三个公开 bool 是否任一为 true”推断内部错误是否已经 normalized。持久化探测恰好得到全 false 时，该判断无法区分“已探测且未获证明”与“尚未探测”，于是旧内存 true 覆盖了权威结果。

修复增加私有 `_NormalizedPublicationError`，从结构上标记已经完成持久化探测的错误。capture、event、completion 仍分别使用完整 semantic capture/run replay、完整 ledger replay及目标 verified-head 比较、完整 status/ledger/run/completion replay。探测的 PermissionError、OSError、缺失、部分、非规范或语义失败保守映射为 false；公开字段保持 bool，原始普通异常作为 cause 保留。

## 统一 mutation lock 生命周期

initialize、control、recovery 和 execute-next 共享 lock cleanup 机制。descriptor close 与 lock unlink 被视为两个独立、可能失败的 I/O 操作，并始终逐项尝试。清理成功不改变 mutation 主体的异常；清理失败不会覆盖已发生的 publication，而是结合主体错误、cleanup 错误、实际 lock retained 状态和重新执行的只读 evidence probe 形成 `SyntheticProtocolExecutionError`。

unlink 失败时不强制删除、修改权限或自动接管，实际 lock 文件保留；status/validator 不清理它，后续 mutation 在 acquire 边界以 `already in progress` 拒绝。close-after-real-close 故障而 unlink 成功时，领域错误仍返回，但 lock 实际不存在。initialize cleanup 失败逐字节验证 base envelope，并保持 capture/event/completion 为 false。

## Publication 与 cleanup 矩阵

| 场景 | capture | event | completion | lock |
|---|---:|---:|---:|---|
| initialize 成功，unlink 失败 | false | false | false | retained |
| control event 成功，unlink 失败 | false | true | false | retained |
| 非最终 execute-next 成功，unlink 失败 | true | true | false | retained |
| capture recovery 成功，unlink 失败 | true | true | false | retained |
| completion recovery 成功，unlink 失败 | true | true | true | retained |
| control event 成功，close 故障后 unlink 成功 | false | true | false | absent |
| control 主体发布前失败且 unlink 失败 | false | false | false | retained |
| event publish-then-raise 且 unlink 失败 | false | true | false | retained |
| completion publish-then-raise 且 unlink 失败 | true | true | true | retained |

主体与 cleanup 同时失败时，消息同时包含两者；`__cause__` 稳定保留原 mutation/publication 失败，cleanup 类型和消息保留在结构化领域消息中。只有 cleanup 失败时，cause 为首个原 cleanup 异常。`KeyboardInterrupt` 不转换为领域错误；正常 close/unlink 仍被尝试且成功时 lock 不残留。

## Exactly-once、只读与 stale lock

每个成功 control/execute/recovery 只发布一个目标 event/run/completion。stale lock 下重复或 stale-token mutation 在取得锁前拒绝，sequence、cursor、event/run/completion 数量及文件树不变。status 和 validator 可重放已完成的 durable 状态，但不删除 lock、不创建 staging、不修复 partial/tampered 文件。没有新增自动 stale-lock takeover。

## 测试与门禁

- DEV-05.03R 原错误契约 15 项 + R2 新增 12 项：`27 passed in 98.50s`；
- 原快速测试：`38 passed in 30.11s`；
- recovery/concurrency/tamper 六个既有选择器：`6 passed in 22.56s`；
- DEV-05：`223 passed in 1979.48s (0:32:59)`，原 211 项全部保留；
- 完整 suite：`882 passed in 2245.92s (0:37:25)`，原 870 项全部保留；
- Stage 1 审计烟雾：`1 passed in 1.33s`；
- 最终临时根清理后 Ruff format：`168 files already formatted`；
- Ruff lint：PASS；
- strict mypy：`66 source files` PASS；
- generated Schema consistency：PASS，registry 仍 40 个模型，Schema 目录 41 个文件；
- `git diff --check`：PASS。

没有增加 skip、xfail、noqa 或 type-ignore。changed/new code 与测试未引入 U+FFFD、秘密、本机身份、绝对路径或真实音频 API。tracked transient 扫描只命中历史合法 `uv.lock`；本步 pytest/audit 临时根经 workspace 直属路径校验后精确清理并确认不存在。

一次 cleanup 矩阵首跑因测试 execution ID 超过既有 32 字符限制，在目标 mutation 前得到领域拒绝（`1 failed, 7 passed in 6.41s`）；仅缩短测试 ID 后同组通过。首次 Ruff 检查真实报告三个文件需格式化和一个 import-order I001；机械格式化/排序后重跑通过。这些失败未计为 PASS。

## Prompt、日志与保护证据

DEV-05.03R2 prompt 来自实际 attachment，22639 bytes、719 CRLF、无末尾换行，SHA256 `f74c5c9ed600bddef5cde1f187164360690ab98d63021d2e864e25ce1437b9d2`，归档与来源逐字节相同。Implementation log 的 191352-byte 冻结前缀保持 SHA256 `ab6f85b5b95bffc5f12f7b4678a39992ea2e976fc2f01ebb5352888ffb0fb9aa`。

直接复算并保持：

- ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`
- DEV-05.03 prompt（34647 bytes）：`ea9a9a44065254bcf8669ccf12f4ebbe1d97aac7fb60966c2e6c4ee9f1a4ea29`
- DEV-05.03R prompt（19199 bytes）：`48e9af1e92268778112565aead578bec76b87b861c61bf372344ca6b5fd3d0f9`
- Stage 1 manifest/event/capture receipt/run record：`9c311a5ffeb739f7d15cf5cc936637de83273406ac4538fdb2984367bace6331` / `9a271886ccb9d6892c3f93b03d9fb1bc10e4dc2db946c5d9422f25e9d5f9eddc` / `e7a3574d2476e29984733455ffae53f0d5e70601b503d4449a373cdff0513ef4` / `47881cf1a563355a952793499ce6639e09d9702e4e39d831466af1f372bbff17`

## 修改文件与已知限制

修改 `.gitattributes`、README、`synthetic_execution.py`、既有 publication-error 测试、execution architecture 和 implementation log；新增 DEV-05.03R2 prompt、报告和独立 lock-cleanup 回归测试。没有修改模型、CLI、Schema、计划、配置、fixture、reference、ESS、processing、QC、repeatability 或 DSP。

stale lock 需要人工审计和显式受控处置，本步没有自动清理 API。无法读取的 durable artifact 只能保守报告 false，不能证明其一定不存在。错误路径上的完整 semantic replay 有意增加 I/O 与计算成本。hash chain 只是内部完整性证据，不是数字签名、外部 witness 或可信时间戳。DEV-06.01 未实施。

本报告落盘时尚未创建提交或推送；只有文档后轻量门禁、远端基线和 staged audit 继续通过才允许唯一普通提交。
