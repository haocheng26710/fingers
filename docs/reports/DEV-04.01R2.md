# DEV-04.01R2 实施报告：Processing 复合身份与算法版本溯源闭环

## 结论

DEV-04.01R2 的软件实施与提交前门禁通过。`processing_created` 现在以 session 内 `(source_run_id, processing_id)` 作为唯一复合身份；processing receipt schema 和 processing algorithm 版本均升为 `1.1.0`，并用 strict `Literal` 锁定五个 transfer estimator 溯源事实。已通过的 transfer 数学、21 个数组和七文件 processing envelope 未改。本报告冻结时尚未提交或推送，不编造未来提交 SHA。

## 基线与初始化

- 分支：`main`。
- 本地 HEAD、`origin/main`、GitHub `refs/heads/main`：`a52aac34d003f00f3f7583d68927dced8d83a0e8`。
- remote：`https://github.com/haocheng26710/fingers.git`。
- 开始时工作区干净，未发现 `AGENTS.md`/`CLAUDE.md`/`CODEX.md` 等未读项目指令。
- 附件原文 19124 bytes、465 个 CRLF、无结尾换行，SHA256 `37441fe98a60c654ad2047399526536393566746722291f54c8ba760247453ca`；`docs/prompts/DEV-04.01R2.md` 与附件逐字节相等，并已标记 binary。
- implementation log 追加前长度 97450 bytes，SHA256 `112d192dfa8697f2c77e6f6ab0c84d97c520e566f64cad4d9f2b4f3612f3e163`；收尾复核仍保持此完整字节前缀。
- 零改动基线：DEV-04 `91 passed in 24.69s`，完整 suite `460 passed in 44.30s`。

## 复合身份 RED→GREEN

真实反例在同一 synthetic session 中发布 `capture-1/order0` 和 `capture-2/order1`，然后为两者都发布 `processing-1`。两个 processing 目录、两个 event 以及各自的 record/receipt/time 绑定均真实存在，但修正前两次 validator 都报：

```text
capture-1: expected exactly one matching processing_created event; published=true
capture-2: expected exactly one matching processing_created event; published=true
```

根因是 `_validated_processing_event()` 枚举当前 session event 后只用 `event.processing_id == processing_id` 收集候选。修正后候选条件为 `event.source_run_id == source_run_id and event.processing_id == processing_id`。因此 processing ID 的实际作用域是特定 source run，session 内唯一键为 `(source_run_id, processing_id)`；同 source/different processing 和 different source/same processing 均合法，重复同一复合身份仍拒绝。最小修正后身份回归为 `3 passed, 58 deselected`。

## Receipt 版本与 transfer 溯源

- `EssProcessingReceipt.schema_version = "1.1.0"`。
- `EssProcessingReceipt.algorithm_version = "1.1.0"`。
- `transfer_estimator_id = "complex_spectral_ratio"`。
- `transfer_raw_definition = "rfft(input_after_pre)/rfft(output_after_pre)"`。
- `transfer_aligned_definition = "rfft(zero_fill_advance(input_after_pre,estimated_latency_samples))/rfft(output_after_pre)"`。
- `spectral_division_threshold_formula = "max_abs_reference_spectrum*float64_epsilon*reference_sample_count"`。
- `spectral_division_below_threshold_policy = "zero_where_reference_at_or_below_threshold"`。

五个字段均为必填 fixed literal，模型继续 `extra="forbid"`。回归覆盖缺字段、extra、每个错误 literal、旧 schema/algorithm `1.0.0`、receipt 篡改后重算 sidecar，并验证拒绝路径无写回。`ProcessingCreatedEvent` 和 `ProcessingRecord` schema 仍为 `1.0.0`。ESS excitation generator 的 algorithm `1.0.0`、`EssSignalSpec` 与 ESS golden 未变，因为本次变更只描述 processing receipt 中已存在的 transfer 实现，没有改动 excitation 算法。

`schemas/ess_processing_receipt.schema.json` 由活动 Pydantic model 重新导出。注册生成 Schema 仍为 18 个，`schemas/` 包含另一个历史手工 device schema，合计 19 文件。

## 数学、确定性与双根重放

`src/acoustic_ladder/audio/ess_processing.py` 相对基线无 diff。DEV-04.01R 的 identity、multi-tap FIR、polarity 独立 oracle 包含在原 30 项回归中并全部通过。名义输出仍为 latency `37`、IR peak index `37`、IR peak value `0.4999999999999999`。

两个事先不存在的短隔离根 `.r2a`/`.r2b` 分别完整执行 ESS generate/validate → session `dev0401r2`/assembly `assembly001` create/validate → `capture001/order0` 与 `capture002/order1` publish/validate → 两个 `processing001` publish/validate → session validate。两个 source run 均发布到各自子目录，对应 payload 在两根逐字节一致，real root 未创建。

`capture001` 固定 R2 身份的 golden：

- arrays：`e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89`（不变）。
- arrays sidecar：`f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902`（不变）。
- receipt：`25616c6e2d42413243eb8e14cd099d01e69e736c29ffcce5cdd413e97841ad5f`。
- receipt sidecar：`38ef680d07fbc88ca7f2d59bba10866439fe2db80b95b34bcea7eec202830e63`。
- metadata：`daa1c08780c9381604f08be14a268bcb7a539844622096de588c5c020c2a04cb`。

`capture002` 因 source identity/capture receipt 不同而有自身稳定 receipt 系列：receipt `312078601249463f96e0494ffb7c490f695399f2f388e4f5d9bef9c9453e8eb8`，sidecar `9725edba7aaba1a0113f8647e41114821fab5eaec035f0ea52d6041be2439db8`，metadata `e223ad71220df9d5e6bfe2c5099c54e155f9d38e8a5ce35c788cc5bf4165af09`；同样在两根逐字节相等。

提示词列出的 R1 receipt/sidecar/metadata `6f67bacb...` / `45506eec...` / `d10c01d...` 在新 R2 固定重放中分别变为 `25616c6e...` / `38ef680d...` / `daa1c087...`；变化源于必填 receipt schema/algorithm/五个溯源字段，且 R2 重放按要求使用新 session identity `dev0401r2`。为单独观察旧 session identity `dev0401` 下的当前契约，另一次隔离重放得到 receipt/sidecar/metadata `1599ae7861b14b9d3788d07d6d3f4461feef3d0f06b013cb44a4b51bd05f5ad5` / `bd6f40eb962e0ca5f856fc4fb9cfca20eb2d9eadaffdc2875e6a6592fb215f2d` / `68d3bff7e7ad10a4561eae5fe8d3ad1b7380bd7e2757b3ccd66cd8f99c66581f`。

双根 event 分别精确绑定各自 canonical record SHA256、新 receipt SHA256 和 record created time。在 `.r2a` 追加第二个合法编码的 `(capture001, processing001)` event 后，validator exit 1 并报 expected exactly one matching event；processing 树聚合 SHA256 `a503fceca9491241a79dbcd0059dc2c46cb22008552a40dfd309f605663baf49` 前后不变，攻击 event SHA256 `abd222a5e20e3a9d5668988eb77ffa99948f2e2bd83176a433ddd57d949666fc` 前后不变。`.r2a`、`.r2b`、`.r2legacy`、`.r2smoke` 均在解析绝对目标并确认位于工作区后精确删除，最终全部 absent。

## 测试与静态门禁

- DEV-04.01 原始：`61 passed, 43 deselected in 9.72s`。
- DEV-04.01R 原始：`30 passed, 74 deselected in 13.60s`。
- DEV-04.01R2 新增：`13 passed, 91 deselected in 5.42s`。
- 旧 DEV-04 合集：`91 passed, 13 deselected in 22.32s`。
- DEV-04 全部：`104 passed in 28.93s`。
- 完整 suite：`473 passed in 45.86s`，原 460 项无减少。
- Ruff format check：`104 files already formatted`。
- Ruff lint：`All checks passed!`。
- strict mypy：`Success: no issues found in 67 source files`。
- Schema：`PASS schema consistency`；18 generated / 19 total schema files。
- `git diff --check`：PASS。
- suppression、U+FFFD、新本机绝对路径/用户身份/秘密、新真实音频 API/`sounddevice`/Stream/play/rec 扫描均为 0。
- tracked WAV/FLAC/NPY/NPZ 和 cache/staging/lock/测试临时目录扫描为 0。
- 首次将多项扫描合并的 PowerShell 命令因 secret regex 引号解析产生 `ParserError`，未进入扫描；拆分并简化引用后全部真实重跑通过，未将失败命令计为 PASS。

## 保护回归

- ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`。
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`。
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`。
- context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`。
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`。
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`。
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`。
- ESS `smoke` WAV/metadata/raw float32：`608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0` / `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a` / `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`。
- DEV-04.01R prompt/report、历史 prompts/reports、config、fixtures 和 `reference/` 相对基线均无 diff。

## 实际命令概要

实际执行了 Git root/branch/status/HEAD/origin/remote/log/指令文件检查、`git ls-remote`、附件分段读取与 byte-exact `Copy-Item`、提示词/日志长度与 SHA256 检查；历史 prompt/report/log/架构/数学/模型/持久化/测试完整读取；基线、RED、目标 GREEN、原 61、R1 30、R2 13、DEV-04 104 和完整 pytest；Schema export/check、Ruff format/check/lint、strict mypy、`git diff --check`；保护 hash/diff/log-prefix、suppression/encoding/identity/secret/audio/media/transient 扫描；两根完整 CLI 重放、event 绑定检查、重复复合身份攻击、validator 前后 hash 比较、ESS `smoke` 重生成/验证与解析目标后精确 cleanup。

## 交付文件、未执行项与限制

新增 `docs/prompts/DEV-04.01R2.md`、`docs/reports/DEV-04.01R2.md`。修改 `.gitattributes`、README、`docs/architecture/ess-processing.md`、`docs/architecture/storage-layout.md`、`schemas/ess_processing_receipt.schema.json`、processing models/persistence、DEV-04 persistence tests 和 append-only implementation log。未修改 processing 数学模块、store、ESS excitation、event/record schema、七文件 envelope 或历史 DEV-04.01R prompt/report。

未运行 production `audio-list`/`audio-inventory`，未枚举、连接、选择、绑定、播放、录音或打开任何真实 Stream；未读取/应用 iMM-6C 校准，未做 SPL、电气回环、真实 latency/shared clock、正式 QC、DEV-04.02 或后续阶段。所有运行都是 synthetic 离线软件流程。

已知限制保持：mono 1x1、整数 sample latency、无 harmonic separation/smoothing/校准/正式 QC；event 是项目内部完整性关联，没有数字签名、外部只读 witness 或可信 timestamp，不声称抵御协同恶意改写。

报告与日志落盘后的最终复跑更新为：完整 suite `473 passed in 37.21s`；Ruff format `105 files already formatted`；lint、67 source files strict mypy、18 Schema consistency 与 `git diff --check` 均再次 PASS。上文 `45.86s`/104 files 是报告创建前同样通过的真实运行，最终值以本段为准。
