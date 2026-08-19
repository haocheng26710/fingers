# DEV-05.01 实施报告：阶段 1–4 协议矩阵编译器与确定性随机化

## 结论

DEV-05.01 的软件实现与本地验收通过。基线及唯一父提交为 `2affc46a5f902adcc5b946cc800542c937d25d6e`（`DEV-04.04: record delivery audit`）。本报告落盘时尚未创建最终提交或执行推送；按提示词要求，最终 commit SHA 与推送后 local/origin/GitHub 审计只在最终回复中报告，推送后不会再修改 tracked 文件。

本步骤仅实现 development-only 协议计划编译、确定性调度、不可变发布和只读验证。没有执行协议、创建 synthetic/real session、run 或 event，没有访问、枚举、连接、播放、录音或校准真实音频设备，也没有增加阈值、判决、分类器或实验结论。

## 实现结果

- 新增 strict `DevelopmentProtocolPlanSpec`，绑定当前 V1.3 bundle、manifest、manifest sidecar、四个正式 protocol 及 development spec 的 raw/normalized provenance。调用者不能注入条件、NodeState、measurement order、正式 counts、真实根、设备、阈值或判决。
- 编译器从当前 manifest、state definitions、protocol 和 development spec 派生完整 NodeState 矩阵。当前 fixture 的 Stage 1–4 condition count 分别为 `19 / 4 / 4 / 16`；production compiler 未硬编码 N1–N6、Stage 4 推荐节点、Stage 2/3 fixture 选择或 bridge module 常量。
- 层级固定为 session → reassembly → condition block → repeat，repeat 在 block 内相邻。当前 development fixture 的 planned measurement count 分别为 `152 / 32 / 32 / 128`。
- 随机化算法为 `sha256_ranked_condition_blocks`、版本 `1.0.0`。相同输入与 seed 跨根逐字节一致；不同 seed 只改变 condition-block order；关闭随机化保持 canonical order；seed 缺失、多余或非安全 ASCII 均拒绝。
- 每个条件保存完整 node-state map、active count、condition identity、来源绑定和 protocol 的 operator confirmation requirements。全部 compiled/receipt/record 模型会自校验节点集合、active count、ordinal、multiset、repeat 相邻性、总量和哈希。
- 新增 `DevelopmentProtocolPlanStore`。每个 plan 只允许位于注入的 development root 下，并以同文件系统 staging、独占 create-only lock、原子 rename 发布 exact 7-file envelope：plan/sidecar、receipt/sidecar、metadata、record、completion marker。重复、并发、unsafe ID、路径逃逸、source drift、byte/semantic tamper、missing/extra file 均只读拒绝且不覆盖旧 bytes。
- 新增 `protocol-plan-compile` 与 `protocol-plan-validate`。CLI 只接受 bundle、plan spec、development root 与 plan ID，输出由已发布/验证 receipt 派生，并明确 `execution_ready=false`、`hardware_ready=false`、`experimental_result=false`。
- 新增四个 generated Schema，registry 现为 31 个 generated Schema，目录共 32 个 Schema（另含手工 device manifest Schema）。同步更新 README、configuration、storage layout，并新增 protocol planning 架构文档。

## TDD 与真实失败

按公共行为 tracer bullet 执行 RED→GREEN。实际 RED 包括：协议包不存在；Stage 2–4 compiler 未实现；compiled model 缺 schedule 字段；compile 未重读已变更 protocol；persistence、CLI、Schema registry 不存在；validator 未拒绝当前 manifest tamper；15 passed/7 failed 暴露底层 `StorageError`；非 ASCII seed 未在 source load 前拒绝；伪造的 loaded spec model 未被重新解析；condition 未携带 operator confirmation requirements。各项均以相邻最小实现修正并新增回归测试，无 skip/xfail/noqa/type-ignore。

过程中的非门禁成功也如实保留：第一次 DEV-04.04 复跑使用过长的 `.t501final404b` basetemp，Windows 在深层 QC staging 临时文件处报 `FileNotFoundError`，结果 `1 failed, 35 passed`；改用短根 `.t4` 后同一完整 DEV-04.04 组 `58 passed`。一次误用不存在的 `check-schemas` 子命令返回 CLI usage error，随后使用项目真实命令 `export-schemas --output-dir schemas --check` 得到 consistency PASS。一次探索性 `mypy src tests --strict` 命中 99 个历史 test-only 类型问题，不作为门禁；提示要求的正确 `mypy src --strict` 最终通过。

## 验收结果

- DEV-05.01：`76 passed in 9.81s`
- 阶段配置与 manifest：`44 passed in 0.57s`
- DEV-04.04：`58 passed in 80.13s`
- DEV-04 全组：`290 passed in 167.67s`
- locked/golden selectors：`4 passed in 0.61s`
- 完整 suite：`735 passed in 189.36s`；原 659 项全部保留，新增 DEV-05 回归 76 项
- Ruff format：`147 files already formatted`
- Ruff lint：`All checks passed!`
- strict mypy：`Success: no issues found in 61 source files`
- Schema：`PASS exported 31 schemas`，`PASS schema consistency`
- `git diff --check`：PASS

最终静态扫描覆盖新增 diff 中的 suppression、U+FFFD、secret/身份/本机路径、真实 audio API、production 节点/module 常量、real root/session/run/event 创建和 tracked transient/media/cache/staging/lock；最终结果见 implementation log。测试 expected 独立构造，没有调用 production compiler 生成 expected。

## 双根确定性与新 golden

两个预先不存在的独立短根都通过公共流程完成 bundle/spec load、Stage 1–4 compile、publish 和 read-only validate；第二根反转可交换 selected-node 输入。五个确定性核心文件逐字节一致，real root、session、run 和 event 均未创建。固定 SHA256 为：

| Stage | compiled plan | plan sidecar | receipt | receipt sidecar | metadata |
|---|---|---|---|---|---|
| 1 | `62fcb88144e84ef564053b61d4d40f30f8bd7d034953da3c2431488b8acdfce2` | `e9e0928cad4b18d4fb7bee0b6893c02c276c99149d89ecf9f24bd366422530f9` | `ed533234107927fb1c40b3860fa94e607a58cd2597deffd23b73bfa4c3f08ce9` | `6da6a79003f4b47bdd092f55d6cbb53631dfbce757f88c9fceb19e60cdd9ae4d` | `08a4d84c0348981b98be23fb9c9dfe4d03d1a82084aa6c8323e5ed156d55ca3c` |
| 2 | `fdd49fe9901f7ad7f7febb8f441a39d8e7b16bc98db0c7fc6a7b6f5e48f39fe8` | `9cc88d4c1a22a6171811ab33313465c5f006b079944662d1b3e9c1c1133b056a` | `35c97bfdb4814ad9557cb07f75d7e5dd6d1170c97e0e3d67173758c8ffcd5c65` | `890b293766b567d1113a7190921b97bda22a9f81e63585cac71612c452d58956` | `8878b6f778d4ce7788c050f305672ff215ec465d72000792109553de0ad1c559` |
| 3 | `685a6ac37018c40b80ce9cdf89fc6e338180d82581120f41173dcd64e9339ff4` | `8d08daeb184301ef2f28eb21f5dc0a8d6612bc5330deb319a5396d78047443ea` | `2fc3becd26466d281d6f5ee4073dd9df36e2960a9e196101f3cee79b1d7ec577` | `e787b8bc1f98fe3ef871c706195a6676ba7e15c7d7547d32da0c8710fa80be26` | `f4baec90065f8328bf0a91b5a5a7dea10f8ea48c631d3f7935ad752aca24cdb9` |
| 4 | `45dd7267da0c5fa30aecaf9f19a1d619622404aa3fd696a399817683aa807716` | `18065d504b352d39d27841ca5075f11102ef003cdb946b8e37eb9ade6bfcf2e6` | `c98886c429804ea9849675e510ab74ed5fac88112c5e0c0f5b9a9c9335dc9025` | `e6975efc90c7db98fca320e1eabafee3889a511fd2e17ac52205db40f46373ab` | `fdd37037644e7fa908973f3934b1171a3a3af634048ef0342e259f0b790aa266` |

## 归档、保护与限制

原始 prompt 归档为 37448 bytes，源/目标 `SequenceEqual=True`，SHA256 `ab545777ed72af68ca030f8f0f99370a6e9ef9eb237aa105c325e51d287347c4`。implementation log 追加前冻结前缀为 140074 bytes，SHA256 `49eebfb17d74b42893a6178ba97738a12845323e18128b59f5e85f6a9f33cf77`，最终复核保持不变。

直接复算 ZIP/manifest/inventory/context/summary/contextual-preflight/hardware setup 仍分别为 `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b` / `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0` / `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2` / `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c` / `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159` / `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15` / `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`。4 个 locked/golden tests 与完整 suite 同时保持 ESS、processing、QC、repeatability 和 DEV-04.04 历史保护 hashes。

已知限制均为预期边界：四个正式 protocol 仍为 draft，正式 repeats/reassemblies/sessions/seed 仍未知；Stage 2/3 operator selection 与 Stage 4 物理确认仍待完成；没有硬件发现、校准、SPL、protocol execution、交互残差、阈值、判决或分类。因此 `execution_ready=false`、`hardware_ready=false`、`experimental_result=false`，DEV-05.02 未实施。

## 实际命令范围

实际执行了基线 `git status/branch/remote/rev-parse/log/fetch/ls-remote` 与项目指令扫描；prompt/log byte/hash 检查；逐个 RED/GREEN pytest selector；DEV-05、配置/manifest、DEV-04.04、DEV-04、locked/golden 和完整 pytest；四阶段双根与 tamper/unsafe/concurrency tests；`.venv/Scripts/ruff.exe format .`、`format --check .`、`check .`、`.venv/Scripts/mypy.exe src --strict`、`.venv/Scripts/acoustic-ladder.exe export-schemas --output-dir schemas` 及 `--check`、`git diff --check`；PowerShell/Get-FileHash 与 `git diff`/`rg` 完成保护哈希和静态扫描。探索性 `rg`、`Get-Content`、`git status/diff` 用于定位和审阅。精确临时根清理、提交前远端复核、唯一提交、普通 push 及推送后审计在本报告落盘后执行，其真实结果只在最终回复中给出。
