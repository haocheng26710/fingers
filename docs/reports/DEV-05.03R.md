# DEV-05.03R 实施报告

## 结果与范围

DEV-05.03R 在唯一基线 `2977e1b802f34a2a475f5986871fba9fc5594a54` 上闭合 synthetic protocol execution 的恢复与控制发布错误契约。改动限于一个执行协调器、一个新回归测试文件及直接相关文档；没有改变公开函数签名、模型、Schema、计划遍历、work-order/NodeState/condition、DSP 或确定性成功路径。

本步骤没有枚举、连接、选择、播放、录音或校准真实音频设备，没有打开 Stream，没有执行 SPL、shared-clock 或 loopback 验证，也没有进入 DEV-06.01。

## 缺陷复现与真实 RED

原实现只在 `_publish_event_pair` / `_publish_completion` 正常返回后设置内存布尔值。`recover_current_synthetic_protocol_work_order` 和 `apply_synthetic_protocol_execution_control` 没有覆盖 publisher 抛出的普通 I/O 异常；同时，包住整个 mutation 的 `FileExistsError` 分支会把 publisher 的同名异常误报为锁竞争。

真实 RED：

- capture recovery 的 event publisher 发布前抛 OSError：裸 OSError 泄漏，`1 failed in 1.97s`；
- completion recovery 的 publisher 发布前抛 PermissionError：增量实现最初返回 false/false/false，未报告调用前已验证的 capture/event，`1 failed in 12.79s`；
- pause control publisher 发布前抛 OSError：裸 OSError 泄漏，`1 failed in 1.20s`；
- execute-next publisher 完整发布 event 后抛 OSError：错误已规范化但 event 被误报 false，`1 failed in 1.39s`；
- control publisher 完整发布后抛 FileExistsError：被误报为“transition already in progress”，`1 failed in 1.83s`。

另有两次测试夹具错误在目标断言前失败并如实保留：completion 测试多假定了一层 `sessions/`（`1 failed in 12.41s`）；publish-then-raise 测试将字符串 origin 传给 enum API 而误选 real 根（`1 failed in 1.94s`）。两者均只修正测试路径后重跑，未计作产品 RED。

## 最终权威语义与实现

三个 publication 字段表示异常返回时持久化目标已经完整存在并通过只读验证，不表示“尝试过发布”。集中错误构造器只捕获 `Exception`，保留原异常为 `__cause__`；`KeyboardInterrupt` 等 `BaseException` 直通。

- capture：对当前或最后 work order 执行完整 semantic capture/run replay；
- ledger event：重放完整连续 ledger、sidecars、previous hash、工作项及状态转换，并要求本次目标 event 是 verified head；
- completion：运行公开 status 的完整 base/event/run/completion 验证，并逐项比较本次目标 completion。

publisher 完整发布后再抛异常会被探测为 true。缺失 sidecar、部分/非规范文件、目标不一致或探测异常均保守为 false，错误消息说明未获证明。探测不补写、删除、覆盖、清理或修复。锁获取被收窄为独立边界，只有尚未取得锁时的 FileExistsError 才表示并发冲突。

## 恢复与控制矩阵

| 场景 | capture | event | completion | 权威结果 |
|---|---:|---:|---:|---|
| capture recovery，event 发布前失败 | true | false | false | cursor/head 不变；移除故障后显式恢复恰好一个 event |
| capture recovery，event 完整发布后抛错 | true | true | false | cursor 恰好推进一次；旧 token 拒绝 |
| completion recovery，completion 发布前失败 | true | true | false | 保持 completion recovery；不重复 run/event |
| completion recovery，completion 完整发布后抛错 | true | true | true | status/validator complete；旧 token 拒绝 |
| pause/resume/retry/abort event 发布前失败 | false | false | false | 各自状态、cursor、head、tree 不变 |
| pause event 完整发布后抛错 | false | true | false | paused/sequence+1；旧 token 不重复发布 |
| execute-next event 完整发布后抛错 | true | true | false | active/cursor+1；恰好一个 run/event |

真实双线程 execute/recovery 选择器继续通过。fail-before 测试移除故障后重新读取 token 并完成显式 recovery，重复调用与 stale token 均未创建第二个 capture、event 或 completion。部分 event/completion 被保留原字节；连续 status/validator 拒绝前后文件树一致，证明只读不写回。

## 测试与门禁

- 新增错误契约：15 项；
- 新增 + 原快速 38 项：`53 passed in 85.44s`；
- recovery/concurrency/tamper 定向组合：`20 passed in 74.72s`；
- DEV-05：`211 passed in 1771.34s (0:29:31)`，基线196项全部保留；
- 完整 suite：`870 passed in 2012.64s (0:33:32)`，基线855项全部保留；
- Ruff format check（165 files）、Ruff lint、strict mypy（66 source files）、40 generated Schema consistency、41 total Schema files和 `git diff --check` 均通过。

没有增加 skip、xfail、noqa 或 type-ignore。生产、测试、报告、架构和README的扫描不包含 U+FFFD、秘密、本机绝对路径或真实音频 API；implementation log 中唯一的本机绝对路径是按审计要求记录的实际 attachment 来源。Git 中没有任务 WAV/NPY/NPZ、cache、lock、staging 或临时根。

## 保护证据

直接复算 SHA256：

- ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`
- DEV-05.03 prompt（34647 bytes）：`ea9a9a44065254bcf8669ccf12f4ebbe1d97aac7fb60966c2e6c4ee9f1a4ea29`
- Stage 1 manifest / first event / capture receipt / run record：`9c311a5ffeb739f7d15cf5cc936637de83273406ac4538fdb2984367bace6331` / `9a271886ccb9d6892c3f93b03d9fb1bc10e4dc2db946c5d9422f25e9d5f9eddc` / `e7a3574d2476e29984733455ffae53f0d5e70601b503d4449a373cdff0513ef4` / `47881cf1a563355a952793499ce6639e09d9702e4e39d831466af1f372bbff17`

DEV-05.03R prompt 为19199 bytes、541 CRLF、无末尾换行，SHA256 `48e9af1e92268778112565aead578bec76b87b861c61bf372344ca6b5fd3d0f9`，与 attachment 逐字节一致。implementation log 的176483-byte冻结前缀仍为 `db488b2672040a628e7cf58ab1c1a960208eeaf9b05f9af6a89a35e59c107c59`。

## 修改文件与限制

修改 `.gitattributes`、README、`synthetic_execution.py`、本架构文档和 implementation log；新增 DEV-05.03R prompt、报告及错误契约测试。未修改模型、CLI、Schema、计划、ESS、processing、QC、repeatability、DSP、配置、fixture 或 reference 产物。

部分/foreign/tampered 文件仍需调用方或运维人工处置；探测只会保守报告 false。错误路径的完整 semantic replay有意增加耗时。本地 hash chain 只是项目内部完整性证据，不是数字签名、外部 witness 或可信时间戳。DEV-06.01 未实施。

本报告落盘时尚未创建提交或推送；只有最终文档后门禁、远端基线与 staged audit 继续通过才允许唯一普通提交。
