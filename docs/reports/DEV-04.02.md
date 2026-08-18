# DEV-04.02 实施报告：离线处理质量证据与 provisional QC 状态框架

## 结论

软件实现与提交前门禁通过。DEV-04.02 新增 synthetic-only、threshold-free 的 provisional QC 指标、不可变七文件发布、只读重放验证、严格事件绑定、两个生成 Schema 和 `qc-compute` / `qc-validate` CLI。未调用 production `audio-list` / `audio-inventory`，未枚举、连接、选择、绑定、播放、录音或打开真实 Stream，未使用校准，未进入 DEV-04.03。

基线为 `main` 的 `cb2798f8b2d1544271b45c41741b3c6ee6cab6a7`；开始时本地 HEAD、`origin/main`、GitHub `refs/heads/main` 一致，远程为 `https://github.com/haocheng26710/fingers.git`，工作区干净且无项目级额外 agent 指令。提示词以原始 24466 bytes 归档，SHA256 为 `2da0eb11322f409b54ddcd38ff244ccb74277a257fc94c1e5e47045aec97bba6`。

## 实现

- `provisional_qc.py` 提供无文件系统副作用的纯 float64 内核。它验证 mono `[1,N]`、非空、实数 dtype、有限性和 timing，计算 output/input peak、full/active/pre RMS、`abs(sample) >= 1.0` clipping、带固定 null 状态的 input pre-silence SNR proxy、processing latency/correlation、IR 主次峰比、reference off-peak residual，以及 analysis-band 谱除法/transfer finite coverage。它不接受 scenario、expected truth 或 threshold。
- `provisional_qc_models.py` 提供 strict、`extra=forbid`、`allow_inf_nan=false` 的 `ProvisionalQcMetrics`、`ProvisionalQcReceipt`、`QcRecord`、`QcCreatedEvent`、`PublishedProvisionalQc` 及嵌套 waveform 模型。所有 optional metric/status、count/fraction、correlation 和安全状态有交叉验证。QC metrics/receipt/algorithm/record/event 版本均为 `1.0.0`。
- Receipt 绑定 session/source-run/processing/QC 复合身份、capture/processing/arrays/config/manifest/AnalysisConfig/metrics hashes、processing schema/algorithm version、固定公式 ID、create-only/immutable，以及全部 hardware/shared-clock/channel/calibration/electrical-loopback/formal/experimental false flags。状态固定为 `complete` / `provisional_metrics_only` / `not_evaluated`，threshold 为空且从未应用。
- `provisional_qc_persistence.py` 的 publisher 首先调用 `validate_ess_processing()`，再读取已验证 capture WAV 和 canonical processing NPZ；公开参数没有 waveform、array、precomputed metrics、arbitrary WAV/NPZ、real root、truth、threshold、decision 或 device。AnalysisConfig `qc_threshold` 非 null 会被拒绝。
- `ImmutableSessionStore.create_synthetic_qc()` 仅从 injected synthetic root 和四个身份推导 `qc/run_<source_run_id>/processing_<processing_id>/qc_<qc_id>/`，要求 source run/processing 完成，并用同文件系统 staging、create-only lock 和 rename 发布 exact seven-file envelope。没有 generic real-root QC writer。
- 七文件为 metrics/receipt 及严格 sidecar、固定 metadata、outer record 和 exact `QC_COMPLETE == b"complete\n"`。发布后 `qc_created` 绑定 `(source_run_id, processing_id, qc_id)`、record/metrics/receipt hashes 与时间；event 失败保留目录并报告 `published=true`。Validator 重验 processing、重算 metrics、重建所有期望 bytes，并只读校验 exact set、canonical JSON、sidecars、record、completion 和恰好一条 composite event。
- Schema registry 从 18 增至 20 个生成文件；仓库另有一个 manual device-manifest Schema，因此 `schemas/*.schema.json` 共 21 个。CLI 成功输出 path/hashes、SNR/IR/coverage、provisional/not-evaluated/threshold false、formal/experimental false 和 safety marker。

## TDD 与测试

按公共接口纵向 RED→GREEN：

1. 纯内核首个 RED 为 `ModuleNotFoundError: acoustic_ladder.audio.provisional_qc`；最小实现后 14 项 GREEN，随后扩展到 20 项。
2. persistence 首个 RED 为 `ModuleNotFoundError: acoustic_ladder.audio.provisional_qc_persistence`；最小七文件纵切后 7 项 GREEN，最终两个 DEV-04.02 文件共 80 项通过。
3. 旧 DEV-04 两文件为 `104 passed in 22.73s`；新增测试为 `80 passed in 24.60s`。
4. 首次完整门禁在新增 Schema 后暴露旧断言仍硬编码 18：`1 failed, 552 passed in 58.90s`。仅把受影响断言更新为 20 后，完整结果为 `553 passed in 60.40s`；原 473 项无减少，新增回归 80 项。

新增覆盖独立 peak/RMS/SNR/IR/reference/spectral oracle、切片和 clip 边界、所有 null reason、错误 shape/dtype/NaN/Inf/空 band、API authority；严格模型；七文件/sidecar/canonical/create-only/concurrency/staging cleanup；metrics/receipt/metadata/record/timestamp/completion/extra/event attacks；event missing/duplicate/identity/sequence/extra/noncanonical；source processing missing/tamper；两种 composite identity 复用；read-only tree invariance；real root absence；完整 CLI；20 generated / 21 total Schema；processing protected hashes。

## 双根重放与攻击

预先确认 `.dev0402ess`、`.dev0402a`、`.dev0402b` 不存在。两个独立 synthetic roots 均真实完成：ESS generate/validate → session create/validate → virtual capture publish/validate → processing publish/validate → QC publish/validate，固定身份为 `source_ess/dev0402/assembly001/capture001/processing001/qc001/order0`。

- 两根 latency/IR 为 `37 / 37 / 0.4999999999999999`（PowerShell JSON 显示为 `0.5`）；input pre-silence SNR proxy 为 null，状态 `zero_pre_silence_rms`。
- 最终五个 deterministic payload 在两根逐字节相同：
  - `qc_metrics.json` `627ad7791b284b038e32beadb30a9603242d3b68f8fd0a466e2a9b7d606e4c0f`
  - `qc_metrics.sha256` `8702aa02ee3337f9bdd9b192c8b8a78657bd9c93674f7c623db5a9e17a43047b`
  - `qc_receipt.json` `8a72666b84179d708128e9b06eff66cb94d9819ec00d708e268a926f26b6754d`
  - `qc_receipt.sha256` `f07e31fdb3c9a903b32e06048599d70c9f135d9265c2512b5c27e3a48d09b9f8`
  - `qc_metadata.json` `7c11de246773d89d481a4f575b3a9efdfccae4102fdae4b30c366a9076b961d2`
- Receipt false flags补齐后按要求重新执行了完整双根链；此前 receipt/sidecar/metadata 的中间哈希不作为最终值。
- 对 root A 的 metrics、metrics sidecar、completion、record、event 分别篡改；五次 `qc-validate` 均 exit 1，validator 前后 session-tree aggregate SHA256 分别完全一致。恢复原始测试 bytes 后 validation 再次 PASS。
- 两个 synthetic CLI real placeholder roots 始终不存在。三个短临时根都在 resolved parent 等于 workspace 后精确递归清理，最终均 absent。

## 静态、Schema、保护与扫描

- Ruff format：`112 files already formatted`；Ruff lint：PASS。
- strict mypy：先对新增/直接修改的 5 源文件通过；完整配置最终 `Success: no issues found in 72 source files`（既有 67 + 新增 5 source/test files）。
- Schema：`PASS exported 20 schemas`，随后 consistency PASS；`git diff --check` PASS。
- suppression 扫描：skip/xfail/noqa/type-ignore 0；secret 0；新增本机身份/绝对路径 0；新增真实 audio API 0；tracked WAV/FLAC/NPY/NPZ/cache/staging/lock/DEV-04.02 temp 0。
- 全仓 U+FFFD 扫描命中 1 个既有且受保护的 `docs/prompts/DEV-03.02.md` 历史原文；本次新增 diff 命中 0，未修改该文件。
- 配置、reference、fixtures、`ess_processing.py`、processing models/persistence 和全部历史 prompt/report diff 为 0。实施日志追加前 106035-byte prefix SHA256 仍为 `8638d5a9709e7f6df9e5ace751608c49f29a225531562f6e2e65122fbe895e48`。
- ZIP/manifest/inventory/context/summary/contextual-preflight/hardware hashes 依次保持：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b` / `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0` / `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2` / `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c` / `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159` / `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15` / `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`。
- `smoke` ESS WAV/metadata/raw hashes 保持 `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0` / `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a` / `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`。生成/验证通过后，metadata 哈希路径先后被误写为两个不存在文件名；两次命令均未计为 PASS，列出实际四文件后以 `excitation.metadata.json` 正确复算，随后安全清理 smoke root。
- 固定 `dev0401r2` processing 五个 hashes 由回归测试保持：arrays `e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89`、sidecar `f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902`、receipt `25616c6e2d42413243eb8e14cd099d01e69e736c29ffcce5cdd413e97841ad5f`、sidecar `38ef680d07fbc88ca7f2d59bba10866439fe2db80b95b34bcea7eec202830e63`、metadata `daa1c08780c9381604f08be14a268bcb7a539844622096de588c5c020c2a04cb`。

## 文件与命令

新增：DEV-04.02 prompt/report、provisional QC architecture、两个 Schema、三个 QC 源模块、两个测试文件。修改：`.gitattributes`、README、data README、configuration/storage architecture、CLI、Schema registry、store、一个旧 Schema-count 测试和 append-only implementation log。未修改 processing 数学、processing models/persistence、配置、fixtures、reference 或历史产物。

实际命令类别：Git branch/status/HEAD/origin/remote/root/指令扫描及 `git ls-remote`；prompt/TDD/历史/源/测试/架构分段读取；byte-exact prompt copy/hash/log-prefix；多轮 RED/GREEN pytest；旧 DEV-04、新 DEV-04.02 与完整 pytest；Schema export/check；Ruff format/check/lint；partial 与完整 strict mypy；diff check；双根全 CLI 链、byte/hash compare、五类攻击/tree hash、恢复验证与安全 cleanup；ESS smoke；保护 diff/hash；suppression/U+FFFD/identity/secret/audio API/tracked transient 扫描。

## 限制与 Git 状态

仍只支持 synthetic mono 1×1 development fixture、整数 latency、无 smoothing/harmonic separation/calibration/SPL/shared-clock/electrical-loopback/formal threshold/baseline/drift/classification。QC 指标不是正式质量判决。Event 无签名、外部 witness 或可信 timestamp，协同篡改全部相互绑定文件不在声明范围。

本报告首次落盘时尚未提交或推送，不能预写最终 SHA 或虚构远端结果。只有报告/日志加入后的最终回归、远端基线复核和内容审查仍通过，才会提交 `DEV-04.02: add provisional offline QC evidence` 并正常推送 `main`；最终 SHA、三向一致性和工作区状态在最终回复报告。

报告与日志落盘后的最终复跑结果：完整 suite `553 passed in 60.01s`；Ruff format `113 files already formatted`；Ruff lint、72-file strict mypy、20 generated Schema consistency 与 `git diff --check` 全部 PASS。
