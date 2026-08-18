# DEV-04.01 实施报告：离线 ESS 反卷积、延迟估计与 IR/复传递函数内核

## 结论与范围

- 软件实现和提交前验收：`PASS`。
- 基线：分支 `main`，本地 `HEAD`、`origin/main` 和 GitHub `main` 均为 `42af61b89b1c8101004446e55fce9e2762da3b6c`；remote 为 `https://github.com/haocheng26710/fingers.git`；起始工作区干净。
- 原有测试：`369`；DEV-04.01 新增回归：`61`；最终完整套件：`430 passed in 18.58s`。
- 范围仅含已验证 synthetic virtual capture 的离线 ESS 处理、不可变发布、只读语义重放验证、Schema 和 CLI。
- 没有连接、枚举、绑定、播放、录制、开流或验证任何真实音频硬件；没有读取或应用麦克风校准，没有形成 SPL、正式 QC、真实延迟/时钟或声学结论。

报告冻结时 Git 提交和推送尚未发生；提交不能在自身内容中记录最终 SHA。只有报告/日志冻结后的远端基线复核和最终门禁继续通过，才会提交并正常推送；实际提交 SHA 和三方一致性由 Git 历史与最终回复报告。

## 提示词与基线审计

附件按原始 CRLF 字节复制为 `docs/prompts/DEV-04.01.md` 并通过 `.gitattributes` 标记 binary。源与归档均为 39335 bytes、1569 个 CRLF、SHA256 `d4df6b074477e9ef0c1799343a5e77be7373e977656e37d7676c4230061d6f79`。

实现前确认仓库根、分支、remote、clean status、local/origin/GitHub 三方提交和项目指令文件扫描。未发现 `AGENTS.md`、`CLAUDE.md`、`CONTEXT.md` 或 ADR 指令。完整读取提示词、TDD skill 及其 tests/mocking/deep-modules/interface-design/refactoring 参考、列明的配置/存储/ESS/virtual-capture/CLI/Schema 源码、DEV-03 测试、架构和三个前序报告。

实施日志原始 75313-byte 前缀 SHA256 为 `9f4bad2c6ec7b9a7f806fbe6200e1b83965792501409f3f37081c4618b01e1f2`；完成时重新计算仍一致。

## API 与信任边界

新增纯数学 `process_ess_waveforms`，其输入仅为 output/input 波形以及从已验证 metadata/config 提供的采样率、sweep/pre-silence 计数、扫频边界、分析带和 smoothing 状态。API 不含 scenario、expected latency/gain、declared latency/gain、设备或持久化参数。

新增 `publish_ess_processing` 与 `validate_ess_processing`。publisher 参数严格为 store、LoadedBundle、LoadedVirtualCaptureScenario、ESS root、session/source-run/processing IDs 和 outer record clock；validator 除 clock 外相同。两者首先调用现有 `validate_virtual_capture`，重建 source session/run/bundle/scenario/ESS/WAV/receipt/run envelope 信任链。调用者不能提供 waveform、任意 processed 路径、real root、预计算 inverse/IR/transfer/hash/receipt、设备、Host API、通道、校准或 expected/declared latency/gain。

处理路径只能由 store 从 synthetic root 推导为：

```text
session_<session_id>/processed/run_<source_run_id>/processing_<processing_id>/
```

processing ID 使用稳定 ASCII 标识约束。store 先验证 synthetic source run，再在同一 session filesystem 中使用 staging、协作 create-only lock 和最终 rename。已有目标、并发竞争和 staging 故障不会覆盖已发布字节；测试验证两并发调用恰有一次成功，故障后无 target/staging/lock 残留。

提交前按提示词逐字段复核时发现初版 receipt 漏记 source output/input WAV/raw hashes、candidate lag range/相关绝对值、deconvolution FFT length 和完整 hardware/calibration false flags，且 latency/IR 字段名未完全采用提示词列出的规范名。新增第 61 个审计回归后补齐这些 strict 字段并重新导出 Schema；最终 receipt 同时记录 `matched_correlation_signed/absolute`、`candidate_lag_min/max=0/544`、`estimated_latency_seconds`、deconvolution FFT 32768，以及所有 source hashes 和 false flags。该修正只增加审计闭环，没有从 capture receipt 读取 latency/gain truth。

## 数学契约

共享 pre-silence 在处理前移除，active sweep 与时序均从已验证 ESS metadata 得到。内部数组为 finite C-contiguous float64。逆滤波器为：

```text
q0[n] = s[N-1-n] * exp(-ln(f_end/f_start) * n/N)
```

参考反卷积的绝对峰必须 finite、非零且唯一；使用峰的符号归一化，使归一化后同位置为正一。所有卷积为 power-of-two FFT 的完整线性卷积，并裁剪到精确 full length。零能量、非 finite、峰 tie、非法频率/shape/timing/分析带和启用 smoothing 均拒绝。

延迟使用 active sweep 在 input-after-pre 中所有完整重叠窗口的归一化 matched correlation；不使用部分重叠。绝对最大值必须唯一，保留相关系数符号。名义 capture 由波形恢复：

```text
estimated_latency_samples = 37
latency_correlation_coefficient = 0.9999999999999922
ir_raw_dominant_peak_index = 37
ir_raw_dominant_peak_value = 0.4999999999999999
```

raw IR 从 reference peak 起保留；aligned IR 用测得延迟做 zero-fill advance，不用 `np.roll`，不回卷，raw 不变。raw/aligned transfer 使用共同 power-of-two `rfft` 长度 16384，得到 8193 bins；保存 real/imag、linear/dB magnitude、wrapped/unwrapped phase。dB floor 固定为 `np.finfo(np.float64).tiny`。当前 AnalysisConfig 的 500–8000 Hz 只形成 inclusive bool mask，未执行 smoothing。

## 确定性数组与持久化

旧 synthetic generator 内的 NPZ writer 抽取为共享 `storage.npz`，没有复制第二套 writer。编码按名称排序，固定 ZIP timestamp/mode，stored compression，`np.save(..., allow_pickle=false)`；拒绝 object、不安全名字、非 C-contiguous 和非 finite 数组。旧示例 `synthetic_arrays.npz` 重新生成 SHA256 仍为 `908a2c01ca652390cd7ddcf055c608b3339dedfbcbcc1724dc4e06010bef333a`。

处理 NPZ 精确包含 21 个数组：inverse/reference/input deconvolution、relative sample/time axes、raw/aligned IR、frequency、raw/aligned transfer real/imag、linear/dB magnitude、wrapped/unwrapped phase 和 analysis mask。IR/transfer 为 `[1,1,n]`，frequency/mask 为 `[n]`；relative samples 为 int64，mask 为 bool，其余为 float64。receipt 对每个数组记录 name/dtype/shape/raw SHA256。

每个 processing 目录精确包含：

```text
processing_arrays.npz
processing_arrays.npz.sha256
processing_receipt.json
processing_receipt.sha256
processing_metadata.json
processing_record.json
PROCESSING_COMPLETE
```

validator 首先重验 source capture，然后核对 exact set、sidecar、canonical JSON、fixed metadata、outer record 和 completion marker；它重读 WAV/ESS/config，重做全部数学、21 个数组、NPZ、descriptors 与 receipt，并逐字节比较。篡改 arrays/receipt/metadata/record 或添加 extra file 均被拒绝，validator 不修复文件。

## TDD 记录

1. 首个纯数学 RED 在收集阶段为 `ModuleNotFoundError: acoustic_ladder.audio.ess_processing`；实现后 `10 passed`。
2. NPZ/model RED 为 `ModuleNotFoundError: acoustic_ladder.audio.ess_processing_models`。抽取 writer 后新测试通过，但并跑旧 DEV-02 时因过度删除 `io` import 得到 `2 failed, 14 passed`；恢复读取器仍需的 import 后 `16 passed`，NPZ 字节不变。
3. persistence RED 为 `ModuleNotFoundError: acoustic_ladder.audio.ess_processing_persistence`。初版后 `2 failed, 15 passed`，发现 strict receipt 的 string origin 被传给以 enum identity 选择 root 的 store；固定使用不可由调用者控制的 `DataOrigin.SYNTHETIC` 后 `17 passed`。
4. CLI RED 唯一失败为 `process-simulated-capture` 非法子命令；新增两个命令后 DEV-04 为 `57 passed`，扩展并发/staging/source-complete 后为 `60 passed`；receipt 逐字段审计回归后最终为 `61 passed`。
5. 静态检查真实发现 7 个需 format 文件、Ruff import/line/error-class 问题和 33 个 strict mypy 问题；均以格式化、精确类型和精确异常修正，无 suppression。后续又发现一次 import-order 和两次测试注入点/空行问题，均修正后重跑全部静态门禁。

没有添加 skip、xfail、noqa 或 type-ignore。

## 测试、静态检查与扫描

- frozen sync：`Checked 29 packages`。
- DEV-01：`43 passed in 0.67s`。
- DEV-02.01：`66 passed in 2.67s`。
- DEV-02.02：`23 passed in 1.99s`。
- DEV-03.01：`36 passed in 0.43s`。
- DEV-03.02：`24 passed in 0.50s`。
- DEV-03.03/03.03R：`85 passed in 1.32s`。
- DEV-03.04/03.04R：`92 passed in 8.39s`。
- DEV-04.01：最终复跑 `61 passed in 8.15s`。
- 完整 suite：`430 passed in 18.58s`；原有 369 项全部保留。
- Ruff format：`101 files already formatted`。
- Ruff lint：`All checks passed!`。
- strict mypy：`Success: no issues found in 67 source files`。
- Schema：18 个 model-generated schema，consistency PASS。
- `git diff --check`：PASS。
- skip/xfail/noqa/type-ignore、U+FFFD、新表面本机路径/身份、新真实音频 API/direct sounddevice/Stream/play/rec、tracked WAV/FLAC/NPY/NPZ、tracked cache/staging/lock 扫描：无匹配或空清单。

第一次 DEV-03.01 分组命令误写了不存在的 `tests/dev03/test_preflight.py`，pytest 报 `file or directory not found` 且 `no tests ran`；随后使用真实文件 `test_preflight_persistence_cli.py` 重跑并得到 36 passed。该失败未被计为验收通过。

## 双根 CLI 演示与稳定哈希

两个用前不存在的系统临时根分别完整执行 ESS generate/validate、synthetic session create、simulate/validate capture、process/validate processing、validate session/run。身份固定为 `source_ess/dev0401/assembly001/capture001/processing001/order0`。两根的五个 deterministic processing payload 逐字节一致：

- arrays NPZ：`4c6b9b740112fd2afc34b35ff939de6f0632abb638080c4be9e0dc67af07a560`
- arrays sidecar：`b55e75ad2ae170cba054e557e61084dff4e48efbaf96e700b667ca7704660dc9`
- receipt：`183387988658058a3cb1cf4b056e59326bb609d4fd414898edea99fed8e98727`
- receipt sidecar：`b0a6275e2f2adac141a70fe896cd4fedc22fd852406ef0172fbaca4d2331c9b9`
- metadata：`af00d2cfd737739797defa39da5596e5a88a98e5d2d54dc78dfcacc3aa26e745`

outer `processing_record.json` 含真实命令运行时间，按契约不属于跨根 deterministic payload。两个 root 在确认其解析父目录为系统 temp 后精确递归删除，最终均 `exists=False`。

ESS `smoke` 重新生成并验证：WAV `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`、metadata `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`、raw float32 `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`；临时 root 已清理。

## 保护回归

- ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

受保护 reference/config/fixture/旧 prompt/report tracked surfaces 相对基线无差异；正式 AudioConfig、ESS fixture、nominal scenario 参数和既有 capture golden 未改。提示词归档和本报告是 DEV-04.01 新文件，不属于旧历史修改。

## 修改文件与已知限制

新增 math/models/persistence 三个 ESS processing 模块、共享 deterministic NPZ 模块、DEV-04 测试目录、processing receipt schema、processing 架构文档、prompt archive 和本报告。修改 store（窄 synthetic processing publication）、synthetic generator（复用 writer）、CLI、schema registry/count assertion、README、data README、storage layout、`.gitattributes` 和 append-only implementation log。

已知限制：当前处理契约是 mono 1x1 development fixture、整数样本 matched-correlation 延迟和 full linear ESS deconvolution；没有亚样本估计、非线性 harmonic 分离、窗口/smoothing、麦克风校准、绝对 SPL、真实时钟或正式 QC。create-only lock/rename 是协作式本地 filesystem 边界，不声称抵御所有恶意非协作 TOCTOU actor。37 samples 和 0.5 只是名义 development fixture 的波形恢复 oracle，不是算法输入或实验结论。

未执行：production `audio-list`/`audio-inventory`、真实设备连接/枚举/选择/绑定、Host API/通道、stream/play/record、校准文件读取/应用、SPL/电气回环/真实 latency/shared clock、正式 QC/基线差分/特征/分类/协议矩阵、CAD/geometry lock、DEV-03.05 或 DEV-04.02。所有未执行项均为提示词禁止范围；授权的软件验收项已执行。

本步骤只完成 synthetic 离线 ESS 处理内核。

37 samples 和 0.5 是从波形恢复的 development fixture 结果，不是算法输入。

没有连接、枚举、播放、录制或验证任何真实音频硬件。

本步骤没有产生正式实验或真实声学结论。
