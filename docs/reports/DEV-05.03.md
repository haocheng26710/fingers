# DEV-05.03 实施报告

## 结果与范围

DEV-05.03 在 `2d901b22618d4ecfd338fa2fd4c7731f1fa112e8` 基线上实现阶段 1–4 development synthetic execution。实现只消费 replay-validated compiled plan，创建 synthetic session/reassembly/run 与独立 create-only execution ledger；未创建 real session/run，未枚举、连接、播放、录音或校准真实音频设备，未进入 DEV-06.01。

该能力不是正式 protocol execution。所有 manifest/record/event/completion/status/capture receipt 均保留 `data_origin=synthetic`、`run_mode=development`、operator confirmation pending，以及 hardware/playback/recording/measurement/formal/experimental false，并使用 `SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT`。

## 公共接口与派生

公共模块提供：

- `derive_synthetic_protocol_work_orders`
- `initialize_synthetic_protocol_execution`
- `read_synthetic_protocol_execution_status`
- `execute_next_synthetic_protocol_work_order`
- `apply_synthetic_protocol_execution_control`
- `recover_current_synthetic_protocol_work_order`
- `validate_synthetic_protocol_execution`

工作项严格遍历 compiled plan 的 `session → reassembly → condition block → measurement`，绑定 plan/receipt/schedule hashes、stage、所有 ordinal、condition role/identity、完整 NodeState map/digest、selected nodes/modules 和 operator requirements。调用者不能提交这些计划事实，也不能提交 origin、session/run path、run identity、waveform、IR、设备或实验判决。

确定性身份为 `sx_<execution>_s<session>`、`sx_<execution>_s<session>_r<reassembly>` 和 `sx_<execution>_w<global-ordinal>`；run ID 与 capture ID 相同。ID 不依赖路径、PID、线程、UUID、用户、机器、临时时间或目录枚举。

## Plan-bound synthetic capture

通用 capture 层复用已验证离线 ESS、SyntheticConfig、synthetic generator、causal conditioned FIR、`VirtualCaptureEngine` 和 `ImmutableSessionStore`。完整 plan NodeState 进入 generator；manifest-derived IR 驱动 block-wise virtual duplex。receipt/run record 绑定 execution、plan/work-order、condition/NodeState、session/reassembly/ordinal、bundle/manifest/protocol/synthetic config、scenario、ESS、IR、WAV、trace 与 artifact hashes。validator 重新生成 IR、虚拟 capture、float32 WAV、receipt 和 run record并逐字节比较。

Stage 1 historical conditioned capture 未改写；Stage 2–4 未伪造 Stage 1 condition-plan。Stage 2 状态仍明确为 proxy；Stage 3 未计算 interaction residual；Stage 4 未执行分类。

## Ledger、状态和恢复

独立 root 为 `executions/execution_<safe-id>/`。base envelope 是 canonical manifest/record pairs、sidecars、initialized marker 和 `events/`；事件是连续 create-only JSON/sidecar pairs，绑定 previous body hash、before/after state/cursor、plan/current work order，成功事件另绑定 session/reassembly/run/capture receipt/run record/ordered artifacts。complete 才发布 completion pair 与 fixed marker，绑定 counts、final head、ordered run/event aggregates。没有 mutable current snapshot。

状态覆盖 active/paused/failed/recovery_required/aborted/complete。每个 mutation 在 exclusive lock 内先重验 plan/base/full event chain/referenced runs，再比较 execution/event head/work-order/cursor/recovery run 的完整 token。真实双线程 init、execute 和 recovery 测试均最多一个成功；loser 不创建第二 run/event，也不前进下一项。

capture root 与 ledger root 不能跨目录原子提交，因此：完整 capture 无 success event 会只读识别为 capture recovery；最后 success event 无 completion 会识别为 completion recovery。两者都只允许显式、完整验证后的 recovery。错误独立报告 `capture_published`、`ledger_event_published`、`completion_published`。partial、foreign、missing 或 tampered capture 均 fail closed，不修复、不覆盖。

## TDD 与测试证据

首个公开 init/read 测试真实 RED 为 `ModuleNotFoundError: acoustic_ladder.protocol.synthetic_execution`，最小 slice 后 `1 passed in 1.12s`。execute-next slice 先因入口缺失 RED，补 session/run/capture/event 后 `1 passed in 2.01s`。后续逐步增加状态、恢复、并发、篡改、CLI 与 Schema。

最终快速文件：`38 passed in 43.46s`。独立双根完整执行首次为 `1 passed in 912.55s`；最终代码纳入全部 DEV-05 后为 `196 passed in 2052.28s`。每个根实际完成 Stage 1/2/3/4 的 152/32/32/128 项，共344；双根总计688个成功 synthetic runs，核心 execution/session/capture trees 与 ordered aggregate 逐字节一致，real roots不存在。DEV-05.02 完整双根 rehearsal 慢测保留并通过。

DEV-04.04 默认深 pytest 临时路径首轮因 Windows 路径长度在历史 QC staging 得到 `1 failed, 57 passed`；相同58项用短 basetemp 原样重跑为 `58 passed in 109.50s`。全部 DEV-04 首轮仅因 Schema registry机械数量35未更新为40而 `1 failed, 289 passed`；最小更新后完整重跑 `290 passed in 237.03s`。配置/manifest组 `44 passed in 0.81s`；五个 locked/golden selectors `5 passed in 19.86s`。

完整 suite 的第一轮在历史 DEV-03 Schema数量35断言失败并被明确中断；`-x` 诊断确认唯一原因后做35→40机械更新。最终正常完整命令使用短 basetemp，结果为 `855 passed in 2717.29s (0:45:17)`；原816项全部保留，新增39项，无 skip/xfail。

## CLI、Schema 与文档

CLI 提供 init/status/execute-next/pause/resume/retry/recover-current/abort/validate；一次最多一个工作项。mutation要求完整 token和安全 actor；没有 execute-all、real root、device、Host API、channel、gain、play/record/stream、condition、NodeState、ordinal、run/hash/waveform入口。CLI PASS 只表示 development synthetic 操作或只读完整性验证。

新增 manifest、record、event、completion、plan-bound capture receipt 五个 Schema。实际导出40个 generated schemas，加历史手工 schema共41；只对受影响的三个历史机械数量断言做35→40、36→41更新，未改变 golden 或 Schema语义。同步 README、storage layout、protocol planning，并新增 `protocol-synthetic-execution.md`。

## 最终验收与保护回归

最终正常完整测试为 `855 passed in 2717.29s (0:45:17)`；基线816项全部保留，DEV-05.03新增39项。DEV-05完整组为 `196 passed in 2052.28s`，DEV-04完整组为 `290 passed in 237.03s`，DEV-04.04短 basetemp 复跑为 `58 passed in 109.50s`，配置/manifest组为 `44 passed in 0.81s`，locked/golden selectors为 `5 passed in 19.86s`。无 skip/xfail。

最终静态门禁：Ruff format check为 `162 files already formatted`，Ruff lint PASS，`mypy src --strict` 对66个源文件 PASS，40个 generated Schema consistency PASS，`git diff --check` PASS。提交前轻量复跑中曾误用不存在的 `check-schemas` 子命令而得到 argparse error；该命令未计为通过，随后使用真实入口 `export-schemas --output-dir schemas --check` 重跑并得到 `PASS schema consistency`。changed/new文件的 skip/xfail/noqa/type-ignore、U+FFFD、秘密、本机绝对路径和真实音频API扫描均为0；tracked transient仅命中历史合法 `uv.lock`。

直接复算的保护 SHA256：ZIP `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`；provisional manifest `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`；inventory/context/summary/contextual-preflight/hardware依次为 `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2` / `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c` / `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159` / `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15` / `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`。提示词归档34647 bytes、SHA256 `ea9a9a44065254bcf8669ccf12f4ebbe1d97aac7fb60966c2e6c4ee9f1a4ea29`，与附件 `SequenceEqual=True`；implementation log的163927-byte冻结前缀仍为 `400f1881a24da06e021465d7f1c711d7235f912ec58849f74b80bdf76141e057`。

Stage 1首工作项审计烟雾测试真实生成并验证 execution manifest / first event / capture receipt / run record，SHA256依次为 `9c311a5ffeb739f7d15cf5cc936637de83273406ac4538fdb2984367bace6331` / `9a271886ccb9d6892c3f93b03d9fb1bc10e4dc2db946c5d9422f25e9d5f9eddc` / `e7a3574d2476e29984733455ffae53f0d5e70601b503d4449a373cdff0513ef4` / `47881cf1a563355a952793499ce6639e09d9702e4e39d831466af1f372bbff17`；测试 `1 passed in 1.47s`。所有测试临时根均按已解析的workspace直属路径清理并确认不存在；首次清理校验命令误用了不支持的 `Split-Path -LiteralPath -Parent`，虽目标已删除但校验报错，随后用正确的 `.Parent.FullName` 独立复核为 `removed=0 remaining=0`，未将失败命令记为通过。

提交与普通推送仅在本报告落盘后的最终差异、远端基线和工作区门禁仍通过时执行；本报告不预写尚未发生的提交SHA或推送结果。

## 已知限制

- 开发 fixture 的 sessions/reassemblies/repeats/seed 不是正式参数建议；正式 drafts 仍 `execution_ready=false`。
- synthetic generator/FIR/virtual duplex 不建立真实声学可分性、硬件 full duplex、shared clock、channel mapping、绝对 SPL 或校准证据。
- event hash chain 是项目内部完整性证据，不是签名、外部 witness 或可信时间戳；尚未被后续记录引用的活动尾部删除没有外部可证明性。
- 每次 mutation 对已引用 runs 做重验，完整双根门禁有意较慢。
- DEV-06.01 未实施。
