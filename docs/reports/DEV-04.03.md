# DEV-04.03 实施报告：离线重复测量集合与 provisional repeatability 证据

## 结论

软件实现与提交前门禁通过。DEV-04.03 新增 synthetic-only continuous repeat set、纯 float64/complex128 pair 数学、严格 provenance receipt、不可变七文件发布、只读重放验证、复合身份事件、两个模型生成 Schema，以及 `repeatability-compute` / `repeatability-validate` CLI。没有调用 production `audio-list` / `audio-inventory`，没有枚举、连接、选择、播放、录音或打开 Stream，没有读取或应用校准，没有进入 DEV-04.04。

当前结果固定为 `provisional_repeatability_metrics_only` / `not_evaluated` / no baseline / no threshold。CLI 的 `PASS` 只表示软件命令与完整性验证成功，不表示声学 repeatability、QC、drift 或实验 PASS。

## 实现

- 成员公开输入仅为 `(source_run_id, processing_id, qc_id)`。每个成员依次通过 virtual capture、ESS processing 和 provisional QC 的现有只读 replay validator；captured WAV、processing NPZ、receipt 与 hash 全部从 synthetic session 派生。
- 集合要求至少两个不同 source run，同一 session/reassembly/ESS/bundle/device/AudioConfig/AnalysisConfig/scenario/processing/QC version、相同 timing/FFT/IR dimensions 和逐元素相同 analysis-band mask。`measurement_order` 从 capture receipt 派生，规范化后必须唯一且连续。调用者顺序不影响 deterministic payload。
- 纯内核产生全部 `n*(n-1)/2` 唯一无序 pair：captured-input/IR normalized correlation、signed/absolute latency delta、IR symmetric NRMSE、in-band complex-transfer symmetric relative L2、float64 tiny-floor magnitude RMSE dB，以及 joint-nonzero phase RMS。零分母和零 phase-valid bins 使用 null + 固定 reason，不添加 epsilon。
- strict Pydantic 模型禁止 extra/coercion/NaN/Inf/unsafe ID，绑定 pair identity/order、count/fraction/null status、完整 pair 集与重算 aggregate。Receipt 绑定每个成员的 capture/processing/arrays/QC hashes、公共 config/scenario/ESS provenance、mask digest、固定算法/公式 ID，以及全部 hardware/calibration/formal/experimental false 状态。
- 存储路径由验证后的 reassembly 派生为 `qc/repeat_sets/reassembly_<reassembly_id>/repeat_set_<repeat_set_id>/`。同文件系统 staging、cooperative create-only lock 和 rename 产生 exact seven-file envelope。`repeatability_created` 用 `(reassembly_id, repeat_set_id)` 匹配并绑定 record/metrics/receipt/member-list hashes；event 失败保留目录并报告 `published=true`。
- Validator 重验全部成员、重算 pair/aggregate、重建 deterministic payload，严格检查 file set、canonical JSON、sidecar、completion、record 与唯一事件；不写回、不修复。
- Schema registry 由 20 增至 22 个 model-generated Schema；加历史手工 device-manifest Schema 后目录总数 23。

## TDD 与回归

按 TDD 技能实施。真实中间失败包括：首个测试因模块不存在 RED；aggregate 篡改和 phase fraction 篡改最初未被模型拒绝；不同但等有效-bin 数的 mask 最初未被纯内核拒绝；三成员独立 Oracle 首次把对称分母算错，production 的 `sqrt(2/5)` 正确，测试期望由 `sqrt(2/2.5)` 修正；首次静态门禁发现格式、一个 Literal 推断、CLI 局部变量复用和 strict-mypy 测试辅助类型问题，随后仅做对应修正。

运行环境方面，直接系统 `python -m pytest` 因项目未安装而 collection 失败；无显式 cache-dir 的 `uv run` 遇到 Windows uv cache os error 183；之后统一使用锁定 `.venv`。分组门禁首次误用不存在的 `tests/dev01`，未计 PASS；从历史记录确认 DEV-01 的真实路径为 `tests/unit tests/integration` 后得到 43 passed。

新增两个测试文件共 23 项，覆盖非零独立 Oracle、三成员/polarity/scaling/single-bin phase、null/status/fraction/aggregate/mask、来源规范化、七文件、create-only、unsafe ID、read-only replay、CLI/authority、双根三成员、全 envelope/event 攻击、tree-hash 无写回、并发、event failure 和两种复合身份复用。最终：

- DEV-01：43 passed。
- DEV-02：89 passed。
- DEV-03：237 passed。
- DEV-04：报告前一轮 205 passed；加入最后两个复合身份回归后由完整套件覆盖。
- DEV-04.03 专项：23 tests collected；最后一次 persistence 文件 18 passed，pure 文件 5 passed。
- 完整 suite：576 passed in 92.05s；基线 553 全部保留，新增 23。
- Ruff format：120 files already formatted；lint PASS。
- strict mypy：77 source files PASS。
- 22 generated Schema consistency PASS；`git diff --check` PASS。

未添加 skip、skipif、xfail、noqa 或 type-ignore。

## 双根、攻击与确定性

两个预先不存在的短测试根各建立一个 synthetic session/reassembly、三个 capture（order 0/1/2）、各自 processing/QC，以及一个三成员 repeat set；publish 后立即 validate。输入成员在第二根逆序，规范化顺序仍为 0/1/2，pair count 为 3，real 目录计数为 0。五个跨根 exact-byte payload SHA256：

- `repeatability_metrics.json`: `730872025244fb847b6ed9937865017b9563cb030865fb8bac193ea0cd2928b3`
- `repeatability_metrics.sha256`: `2581bdb2b036e87035e5f0da5e45c93d173b4e75d84eb71b4279b6a76853a6c8`
- `repeatability_receipt.json`: `bb4253cbb3a92c5dd3c9d92563e4abf5dd93fbdb2918496fcb2b14ef98e5073f`
- `repeatability_receipt.sha256`: `d5f3adf4ca72ce7af21be5fde27d1dd29af9bf187934650045964de85c13fd4c`
- `repeatability_metadata.json`: `bb6fea1c5da81f10a6c39c9ae597ec1acca955a605758634d05a7bdbc361bc16`

在一个真实 published session 上依次攻击 metrics、两个 sidecar、receipt、metadata、record、record time、completion、extra file 和 event。每次失败验证前后完整 session-tree SHA256 相同；恢复原字节后再次 validation PASS。双根临时父目录经 resolved parent/leaf 核对后精确删除，最终不存在。

## 保护与扫描

Prompt 原附件和归档均为 33919 bytes，SHA256 `364b032787a146fdf1deeb8867615f1dc48d87b5a84e7862215187c239807a49`。Implementation log 追加前 114003-byte 前缀 SHA256 仍为 `252a41db18fd0740b3afc40603152bebfba55989412db51bf0ab83faa2e68417`。历史 prompts/reports、config、fixtures、reference、ESS/processing/QC 数学与 models/persistence 相对基线无 diff。

实际复算 ZIP/manifest/inventory/context/summary/contextual-preflight/hardware hashes 分别保持：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b` / `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0` / `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2` / `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c` / `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159` / `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15` / `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`。

DEV-03 回归实际验证 ESS WAV/metadata/raw golden；DEV-04 回归实际验证 R2 processing 与 DEV-04.02 QC 五个 locked hashes。新增 suppression、U+FFFD、secret、绝对本机路径/身份、真实音频 API 扫描均为 0；AST 为 `AUDIO_API_CALLS=[]`。Tracked transient 扫描只匹配合法依赖文件 `uv.lock`，排除后为 0。

## 文件、命令与限制

主要新增：三个 repeatability 源模块、两个测试文件、两个 Schema、repeatability architecture、prompt 和本报告。主要修改：store、CLI、Schema registry、README/data README、configuration/storage architecture、两个既有 Schema-count 断言、`.gitattributes` 和 append-only log。未修改受保护 processing/QC 实现、config、fixture、reference 或历史产物。

实际命令类别：Git branch/status/HEAD/origin/remote/remote-main 与指令扫描；prompt/TDD/历史/源码/测试/文档分段读取；prompt/log byte/hash 检查；多轮 RED/GREEN pytest；DEV-01/02/03/04/专项/完整 pytest；Schema export/check；Ruff format/check/lint；strict mypy；diff check；双根测试、hash compare、攻击/tree hash、restore/cleanup；保护 diff/hash；suppression/U+FFFD/identity/secret/audio API/tracked transient 扫描。上述系统 Python、uv cache 和错误 `tests/dev01` 命令均未冒充 PASS。

已知限制：仍只支持 synthetic mono 1×1 development fixture、整数 latency 和同一 reassembly 的连续 order；没有 protocol condition binding、BLK/baseline、baseline difference、threshold/pass-fail、drift、smoothing、harmonic separation、校准/SPL/shared clock/electrical loopback、feature/classifier 或真实实验。Event 无数字签名、外部 witness 或可信 timestamp，不声称抵御协调改写全部相互绑定文件或所有 TOCTOU actor。

本报告冻结时尚未提交或推送，不能自引用最终提交 SHA 或虚构远端结果。只有最终复跑、远端基线和内容检查继续通过后，才提交 `DEV-04.03: add provisional repeatability evidence` 并正常推送 `main`；最终 Git 事实在最终回复报告。
