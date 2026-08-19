# DEV-04.04 实施报告：Synthetic 协议条件绑定与全 BLK 基线差分证据

## 结论

软件实现与本地验收 PASS。基线为 `b30e70d5709673bb1e8a7d5d9284c20359db261c`；最终提交和推送在本报告首次落盘时尚未执行，实际结果由后续 Git 审计和最终回复给出。

提交前普通 sandbox 的最终 `git fetch`/`ls-remote` 因无法连接 GitHub 失败，未据此声称远端一致；按权限流程重新执行获准的 `git fetch origin main` 后成功，确认 `HEAD == origin/main == b30e70d...`、remote URL 正确，再进入提交。最终 commit/push SHA 不能自引用写入其自身内容，以最终 Git 审计和最终回复为准。

本步骤只实现 development-only、synthetic-only 的 Stage 1 condition binding 和 provisional baseline-difference continuous metrics。没有枚举、播放、录音或打开音频 Stream；没有执行正式 protocol；没有 QC/effect/repeatability/drift/classification PASS/FAIL，也没有硬件、校准、SPL 或实验结论。

## 实现

- 新增 strict development condition plan loader。它把唯一 all-BLK reference 和单节点 bridge candidate 解析为覆盖 V1.3 manifest 全部节点的 `NodeState` map，并绑定 plan、Stage 1 protocol 与 manifest hashes。未知节点/模块、错误 Stage/boundary、重复/缺失 baseline、错误角色、extra、threshold/array authority 和路径逃逸均拒绝。
- 新增 `deterministic_conditioned_virtual_duplex` synthetic backend。响应由既有 synthetic generator 根据 manifest 几何、module 参数和完整 node-state map 派生；继续使用块调度器、同一 raw-run envelope 和 create-only store。receipt/run record 绑定 condition provenance、派生 delay/weight、IR hash、ESS 和全部 false hardware flags。
- processing 和 QC 数学、receipt 版本与 legacy bytes 不变；公共 API 根据场景类型重放 legacy 或 condition-aware capture。repeatability 数学仍为 algorithm `1.1.0`，condition-aware receipt 单独版本化为 `1.2.0` 并绑定 plan/protocol/condition/state provenance；source repeatability 仍是 no-baseline/no-threshold/no-drift-decision。
- 新增纯 float64 baseline-difference kernel：raw/aligned transfer 算术均值、complex additive difference、稳定 ratio、magnitude dB difference、wrapped phase、按连续 valid segment 独立 unwrap，以及 raw/aligned IR mean/difference。invalid ratio/phase 输出为零并保存 bool mask；零对称分母返回 null 和固定 reason，不产生 NaN/Inf。
- 新增窄 publisher/validator。它只接受 store、bundle、condition-aware scenario、condition plan、ESS root、session/comparison ID、两个 repeat-set/member identities 和 publisher clock。baseline/candidate role、condition、reassembly、states、waveform/IR/NPZ、metrics、threshold/decision、real root 和输出路径均不可注入。角色从两个已完整验证的 repeatability receipt 自动派生。
- comparison 使用 `processed/baseline_differences/comparison_<id>/` exact 11-file envelope、同文件系统 staging、独占 create-only lock、原子 rename、失败清理、唯一 canonical `baseline_difference_created` event 和只读 deterministic replay。event append 失败保留 envelope 并报告 `published=true`。
- 新增 condition-aware capture 和 baseline-difference CLI；旧无 condition 参数命令保持原行为。新增 5 个 generated Schema，registry 为 27 generated、目录总数 28（含手工 manifest Schema）。

## TDD 与回归

按公共行为逐片 RED→GREEN。实际 RED 包括：缺少 condition-plan/capture/kernel/persistence 模块；重复 selected node/state 未拒绝；condition-aware processing/repeatability 被 legacy scenario validator 拒绝；condition-aware replay 未检查 source protocol 当前字节；旧 Schema 数量断言仍为 22/23。每个 RED 均以最小相邻实现转绿后再进入下一切片。

独立数学 oracle 硬编码 complex difference、ratio、magnitude/phase、零 baseline bin、phase valid-gap 和 IR expected，没有调用生产 expected 生成逻辑。新增测试最终为 58 项；基线 601 项全部保留，完整 suite 为 659 项，无 skip/xfail/noqa/type-ignore。

最终分层结果：

- 新增 DEV-04.04 最终复跑：`58 passed in 81.62s`
- DEV-04.03R repeatability：`48 passed in 46.99s`
- DEV-04.02 QC：`80 passed in 19.87s`
- DEV-04.01R2 processing：`104 passed in 18.32s`
- DEV-04 全组：`290 passed in 160.54s`
- 完整 pytest 最终复跑：`659 passed in 181.36s`
- Ruff format：`88 files already formatted`
- Ruff lint：PASS
- strict mypy：`Success: no issues found in 57 source files`
- Schema：`PASS exported 27 schemas`、`PASS schema consistency`、28 total
- `git diff --check`：PASS
- suppression、新增 U+FFFD、secret/本机身份/绝对路径、新真实音频 API、tracked media/cache/staging/lock/temp 扫描：PASS

过程中的非门禁成功结果：一个 Schema pytest 命令误用了不存在的 selector，得到 `not found` 后用真实 test 名重跑为 `2 passed`；首个 U+FFFD PowerShell 扫描递归读取 `.pyc` 并命中历史受保护 DEV-03.02 的乱码引文，改为新增文本 diff 扫描后 PASS。二者未被记为验收通过。

提交前最后一次审阅补强了 event 对 baseline/candidate reassembly/repeat-set identity 的显式逐字段核对。新增攻击测试的前两次测试数据构造分别因 canonical serialization 和 strict datetime 输入失败；改为 typed event model 后目标测试 `1 passed`，随后重新执行新增组 `58 passed in 81.62s` 与完整 suite `659 passed in 181.36s`。

## 双根确定性与新 golden

两个预先不存在的独立根各完成一个 synthetic session、all-BLK/N1+B40 两个 reassembly、每组 3 次 condition-aware capture、processing、QC、3-member repeatability、comparison publish+validate。第二根反转两组成员并交换 source 参数。9 个 deterministic payload 逐字节一致；baseline 全 BLK、candidate 恰为 N1+B40、差分非零、raw/aligned arrays 全 finite、real roots absent。

- `condition_binding.json` `4dd706337e9bf68df80f4b4f315e3701bb4748d8899abab633d2d020c2937093`
- `condition_binding.sha256` `570d00e4df23860864cc081221b4dbc00c254a8125207e41db5663a833aafbaa`
- arrays `0e4be4450b31ef7f9d5c4965a5a70ec5446f30a06394ec1210af75d41185e97a`
- arrays sidecar `3f0dd00290b5ee5b9fe419d27ce2b6e35d90c01dad7f43f02b29a9f416a5f2e0`
- metrics `4fe1c19ae028bcab210b9f7b0ae32233b553b379c988f959b1fa2823169c9c57`
- metrics sidecar `cb13460f8d7c370f7a9765fbefc0f181c611cd0ffedf13b42f5ec6931db5e82a`
- receipt `c62e2e798872b0462380aa4e8f017b315c0bc131e3f3a254fcb89534539368cf`
- receipt sidecar `b72ec605c3f6f170bc0c449c3b7ae6d2953d21dfd1f0fcb5118de84b7b76a456`
- metadata `a7c5dd2db64d9741b712446c7859c287aabc0776bb0bc3e63a3d65a87e138772`

## 历史保护

直接复算 ZIP/manifest/inventory/context/summary/contextual-preflight/hardware setup 分别保持：

- `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

4 个锁定 golden 测试重新生成并验证 ESS、processing、QC、repeatability 保护值，全部 PASS。ESS WAV/metadata/raw 为 `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0` / `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a` / `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`；processing、QC、repeatability 的 15 个提示词保护 hashes 均由对应 locked tests 保持。历史 prompt/report diff 为零。implementation-log 冻结前缀 129526 bytes 的 SHA256 为 `599a43c4266a744b7b9b20d98144b05b030b188159b0e899121d84b363f94569`。DEV-04.04 prompt 42405 bytes，byte-exact SHA256 `7cf608de99a9901e269dd2e208b261ab5e96c5ba59f19522e88f5aa9294692cd`。

## 主要文件

新增 `baseline_difference.py`、`baseline_difference_models.py`、`baseline_difference_persistence.py`、`condition_plan.py`、`condition_plan_models.py`、`conditioned_virtual_capture.py`、`conditioned_virtual_capture_models.py`，三个 development fixtures、四个 DEV-04.04 测试文件和五个 Schema。修改 processing/QC/repeatability 的 condition-aware replay 分派、store、CLI、Schema registry、README 与 configuration/storage/virtual-capture/repeatability architecture 文档。

## 实际命令摘要

执行了基线 `git status/branch/remote/rev-parse/log/fetch/ls-remote`、项目指令搜索、prompt/log byte/hash 检查；TDD 中逐个运行目标 pytest selector；最终运行上述 6 组 pytest；运行 `.venv/Scripts/ruff.exe format --check src tests`、`.venv/Scripts/ruff.exe check src tests`、`.venv/Scripts/mypy.exe src --strict`、`.venv/Scripts/acoustic-ladder.exe export-schemas --output-dir schemas` 及 `--check`、`git diff --check`；PowerShell/`git diff` 执行 suppression、U+FFFD、secret/identity/path、audio API、tracked transient、历史 diff、prompt/log prefix 和 SHA256 扫描。还实际运行双根及 attack tests、4 个 locked golden tests和 exact 临时根清理检查。探索性 `rg`/`Get-Content`/`git diff/status` 只读命令用于定位代码、契约和核对结果。

## 已知限制

所有结果均为 deterministic synthetic development evidence。source repeatability 仍明确 no-baseline；baseline 只在 comparison 层由已验证 all-BLK condition 指派。division floor 是数值稳定规则而非实验阈值。continuous difference 非 effect decision、显著性、可检测性、QC、drift 或实验结果。event 只提供项目内部关联，不是签名、外部 witness 或可信时间戳。没有真实硬件、协议执行、校准或绝对 SPL 能力。
