# DEV-05.02 实施报告：离线协议工作单状态机与可恢复排练账本

## 结论与边界

DEV-05.02 已实现 development-only、offline protocol rehearsal ledger：从当前 replay-validated DEV-05.01 compiled plan 派生工作单，以 create-only hash-chain event 重放状态，并支持只读恢复、乐观并发、pause/resume、failure/retry、abort 和 full completion。本步骤没有枚举、连接、播放、录音或校准真实音频设备，没有创建 real/synthetic measurement session 或 capture run，没有执行 processing/QC/repeatability/baseline analysis，没有阈值、decision 或 classification，也没有实施 DEV-05.03。

基线为 `f6ecdc15517b2e1c970788f4637662ebfcddf1ad`（父提交 `2affc46a5f902adcc5b946cc800542c937d25d6e`，标题 `DEV-05.01: add deterministic protocol plan compiler`）。开始前 local HEAD、`origin/main` 与 GitHub main 一致，分支 `main`、remote URL 正确、工作区干净且无进行中的 Git operation。

## 公共接口与状态机

新增 `DevelopmentProtocolRehearsalStore` 及四个窄入口：

- `initialize_protocol_rehearsal(...)`
- `read_protocol_rehearsal_status(...)`
- `apply_protocol_rehearsal_transition(...)`
- `validate_protocol_rehearsal(...)`

每次 init/read/transition/validate 都先调用 DEV-05.01 public validator 重读并验证 manifest、bundle、protocol、spec 与 exact seven-file plan envelope。工作单只按 compiled plan 的 `session → reassembly → condition block → measurement` 顺序派生，包含完整 condition/NodeState/operator requirement 和 plan/receipt identities；caller 不能注入 ordinal、condition、state、session/reassembly/repeat、路径、设备、波形或结果。work-order SHA256 来自 canonical core，不含路径、时间、进程/线程或随机值。

正常路径是 `present-requirements → claim → mark-rehearsed`，只有最后一步推进游标。pause 只允许 awaiting/presented，resume 恢复原 phase；claimed work 可 mark-failed，retry 保持同一工作单并要求重新展示；abort 与 complete 为终态。严格 command 只携带 action、safe actor、expected sequence/head/current-work-order、适用的 safe reason 与受限 detail。完整 concurrency token 另绑定 rehearsal ID。

所有持久化和返回状态明确保存 `development_rehearsal=true`、`operator_confirmation_status=pending`，且 physical confirmation、protocol execution、measurement、hardware I/O、hardware ready、formal eligibility 与 experimental result 全部 false。`requirements_presented_for_rehearsal=true` 只表示软件已展示要求，不表示物理安装已确认。

## 持久化、并发与恢复

独立 root 使用 `rehearsals/rehearsal_<safe-id>/`，与 plan、real、synthetic session store 分离。base envelope 是 manifest/record canonical JSON 与 sidecar、固定 `REHEARSAL_INITIALIZED == b"initialized\n"`、`events/`。初始化使用 same-filesystem staging、exclusive create-only lock 和 no-replace rename；事件 pair 为 `event_<eight-digit-sequence>.json/.sha256`，从 1 连续编号、canonical、create-only，并链接上一 event body SHA256。没有可覆盖的 current-state 文件。

transition lock 内重新验证 plan、base 和完整 chain，再比较 rehearsal/sequence/head/work-order token。真实并发测试证明只有一个请求发布下一事件，另一请求 stale/unpublished；不会让 loser 作用下一工作单。pre-publication fault 清除自身 staging/lock 且不留 half event；event 已发布后的 outer failure 返回 `published=true` 并保留可恢复 event。

最后一个 work order rehearsed 后才发布 completion JSON/sidecar 与固定 `PROTOCOL_REHEARSAL_COMPLETE == b"complete\n"`；completion 绑定 expected/rehearsed count、final sequence/head、ordered event aggregate 及 plan/receipt/schedule hashes。status/validate 只读验证 exact file/type set、fixed marker、canonical strict model/sidecar、当前 plan binding、sequence/hash chain、state/cursor/work-order replay 和 completion；不建 lock、不 repair 或写回。

攻击覆盖当前 sources 与 plan 七文件，base/event/completion body/sidecar/marker，semantic identity/state/phase/cursor/work-order/NodeState/safety，event missing/extra/reorder/tail，non-file，unsafe ID/path，symlink/junction/reparse point，duplicate/concurrent init/transition，stale/foreign token，以及 init/event/post-publication fault。原 bytes 恢复后再次只读验证通过，拒绝操作前后树 bytes 不变。

## TDD 过程

实施使用公共行为 vertical tracer bullets。实际 RED 包括模块/入口不存在；strict nested NodeState 构造失败；每个新 action unsupported；非法 transition 的 `published` 边界错误；CLI subcommand 与 Schema registry 不存在；以及 Windows junction 在 validator 中被接受。每个 RED 以相邻最小实现转为 GREEN 后才继续。Stage 2 full completion 是相邻能力扩展且首次通过，未伪造 RED。真实 `os.symlink` 因 Windows privilege 失败后改用 `cmd.exe /c mklink /J` 得到有效 junction attack RED，再以 lstat reparse check 修复。无 skip、xfail、noqa 或 type-ignore。

## 四阶段双根与 deterministic golden

两个独立根以相同 rehearsal ID、plan、fixed aware clock、actor 经 public init/transition/validate 完整排练。Stage 1–4 分别得到 152/32/32/128 work orders 与正常 456/96/96/384 events；顺序、continuous-repeat adjacency、session/reassembly boundaries 和 condition multiset 来自 compiled plan。共 2,064 个双根事件，未出现 session/run/audio/NPZ/processing/QC/analysis 产物。首次真实双根运行 `1 passed in 923.48s`，两根 deterministic artifacts 逐字节一致后才固化以下 SHA256（`aggregate-hash` 是 completion 中 ordered aggregate ASCII bytes 的 SHA256）：

| Stage | manifest | manifest sidecar | record | record sidecar | first event | last event | completion | completion sidecar | aggregate-hash |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `4696f9e06cb525712f1e5dc38353ee40ba6f082524686e2e2304425c3f138df3` | `3bacfe25ead10c0f5e98acef0d93f6cad1190b2af75b06b707920509f7ddf1f7` | `2553fcaa84926ed2e393cd43ea149925f8aec1d26677cf36088e1c5baaa874bc` | `73249c8b23e0794e46a7eb2b35cf7cfb76029b2640cd170f5ede83704ead3029` | `7db73ca8747177aaf2da2afe6321c66b53f604d7fe19c5e76d5d7287ebcdc481` | `5bf18e699c1ce9a779e80c33deea5d1f4ac183952a5505fbc4734cf605b084b4` | `9742273e5457d2dc22f7501e6e3e133614fa2bc2f342ffbe7479443078e4c87b` | `476e6f68dd4c7399c4fd11b4529727ba21e4c3f92700265593ba6752a28e29de` | `16bf1b39e3d21f99dee7c652c44bd20785a866db376f28dea0b51a960c3c5801` |
| 2 | `abcdb020002285bbaede39439c943901fb7f86d86b92576262093e0ddf0ded67` | `447211eb74ae13c8a04894c58ea119088cb374ffff3e5a26dbde534d1cab48f7` | `5e40e10dc1a20e8a96d76947e843d1079da54e852ccb8a01a086c7e0332ce5a0` | `4ea236e10647f310e8ff1264607d56369bad9f66ff762b7f7dfc9ad3863c6229` | `7d76618fd43c1a5dac45e408d6bec1b640f2f1dd2cdaccdd0aaca46db2c51e52` | `6a5171f58ae3f3a614d23c9495215b146959ced329057d12c0a16476b8ca0656` | `46d830a40b575a8449d64ad7548de59c0046e27a3bb9ac2a78d3d2764333c50e` | `0ef5e823bbac515743d016759297ef25b36c8fc4f417374384f6454fb2547c43` | `26e9cb7a5f6211b51af747f40eabb7604ab3416b7623960653566c6e2444f88b` |
| 3 | `2c6aef8c6100b6bd6a550fab6c2c821b949bf568fee1cf76d811588ab7282c0f` | `45b0b92cee2c99a01577c046471b15266fb45e6d79e4e198f3a9bc67854fe3c1` | `5812b70bd0323d864a4c6209a6a0078d4e4f4c1bb1ee1dc556e07e5a7dcae6ab` | `ca785eb91a8865a4bcd576c28f89eb724431f10d97944a417a0cc947140a5e23` | `a45805a40c9357a30a7bd429f95201bd2bbcea247360132ef1544c968116734e` | `0f0a868c1c68421d030c9626d5820f7f6ad14ceb6e43ed05597efe8f5de3637e` | `9a6f40bd8dc45cf62a76cf55b302cffdd2296d03f7e9e714c8032670ed57793a` | `60daf31ff3b1d5067712e5176261944782b9baa4f6f5803a16a14150ebd6478a` | `1cb87cf29e4ac26e1fae6c5f207b20d25859b4d04fcaeecf42336382c2819d87` |
| 4 | `dbbe77a9704fb9e8c01d175767fc6e937db825738b6d3757989830d0e9efaac8` | `18180cd6b3cd01213ddb46690431b7848b86906c03d12b87150b87c9a091c5f5` | `7f32dd91159cf94bfbbd85b2a1f8a0794a3fc7a0a265d52d438244547ba6d94f` | `c6be323d5b050571b4ca02035e30ad0b9ac584be91ae97eef63db57341dba936` | `36543abcb9a7384704a36d10fc1303e6b13ba3bc8ee2da508f4b470394c8a14f` | `df2bc575813f3a451b827bed9dafee2c275a6d2fb56301649b0cb66e1c1e09c1` | `c59b29e90513ee61f9b1b35cbfc88a57c8fbcff22b2dad90c821a567dc1f252a` | `bc50e7301f6f2f2d11275411e77c32b2ce27c0ebe762d39dc3860a741cb16be1` | `b90600ee964168dc452da8dbd99f5c7f0173e62f91bbca912e5ad5cfbe06d5c1` |

## 验收、归档与保护

- DEV-05.02 快速组：`80 passed in 64.21s`
- 全部 DEV-05：`157 passed in 961.24s`（原 76 + 新 81）
- 阶段配置/manifest：第一次并行进程静默且被明确中断；随后独立短根重跑 `44 passed in 0.73s`
- DEV-04.04：`58 passed in 84.50s`
- 全部 DEV-04：`290 passed in 191.51s`
- locked/golden selectors：`4 passed in 0.86s`
- 完整 suite：`816 passed in 1236.23s`；原 735 项全部保留，新增 81
- Ruff format：`163 files already formatted`；lint：`All checks passed!`；strict mypy：`63 source files` PASS；Schema：`PASS exported 35 schemas`、`PASS schema consistency`；`git diff --check` PASS；production forbidden API/current node-state constant/absolute path、suppression、U+FFFD、secret 与 tracked task transient 扫描均为 0 hits（唯一 tracked `uv.lock` 是历史依赖锁文件，不是任务 transient）

四个 persisted models 均 strict (`extra=forbid`, `strict=true`, `allow_inf_nan=false`)；35 generated Schemas 与手工 manifest 共 36。Prompt 从 attachment byte-exact 归档，36300 bytes、1351 CRLF、SHA256 `065c55f41c271f3470cd38abc95ac60009d41370237b46cd58a5867987ffd9dc`、`SequenceEqual=True`。Implementation log 原 151768-byte prefix 的 SHA256 为 `819358be9c36a48f348fe644b6c83bcd193e52aaa00227ef305dd5cfa311e14d`，仅在末尾追加。

直接复算 V1.3 ZIP、manifest、inventory、capture context、summary、contextual preflight、hardware setup 七项 SHA256 与提示词完全一致。Locked tests 保持 ESS WAV/metadata/raw `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0` / `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a` / `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`，并覆盖 processing/QC/repeatability/DEV-04.04 golden；全部 DEV-05 同时保持 DEV-05.01 四阶段 plan golden。

实际命令范围包括基线 Git/fetch/ls-remote/指令扫描、prompt/log byte/hash、逐片 RED/GREEN pytest、全部 DEV-05、配置/manifest、DEV-04.04、全部 DEV-04、locked/golden、完整 pytest、Ruff format/lint、strict mypy source gate、Schema export/check、`git diff --check`、direct SHA256、changed/new 与 transient scans、双根/攻击/并发/fault tests，以及临时根 resolved containment 后 exact cleanup。探索性 `rg`、`Get-Content`、`git diff/status` 仅用于定位和审阅。

## 已知限制与待交付状态

本地 hash chain 不是数字签名、external witness、non-repudiation 或 trusted timestamp。它能检测被后续 event/completion 引用的修改、删除、插入和重排；活动 ledger 未被后续记录引用的最后尾部删除没有外部可证明性。Full event 发布后 completion 外层发布若失败，会如实返回 `published=true` 并保留 event；该损坏/不完整终态只读拒绝，本步骤不提供 repair/migration 接口。合作式 lock 不能约束绕过 API 的恶意本机写入者。

本报告落盘时 commit 尚未创建、push 尚未执行；不预写最终 SHA。提交前 remote 复核、唯一 commit、普通非-force push 与推送后 local/origin/GitHub 一致性只在完成后最终回复报告。
