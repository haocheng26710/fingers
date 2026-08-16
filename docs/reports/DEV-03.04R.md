# DEV-03.04R 实施报告：虚拟采集来源与封装语义闭环修正

## 结论与边界

- 状态：`PASSED`（报告冻结时 Git 尚未提交或推送，最终提交 SHA 不能在提交自身中自引用）。
- 基线：本地 `HEAD`、`origin/main` 和 GitHub `main` 均为 `4efbba7bcb7b56baece117b3cacd7092b1bba706`；分支 `main`，remote `https://github.com/haocheng26710/fingers.git`，开始时工作区干净。
- 范围：只关闭 DEV-03.04 的虚拟场景来源和持久化封装审计缺口；没有进入 DEV-03.05/DEV-04，没有枚举、连接、绑定、播放、录音或验证真实音频硬件。
- 提示词归档：附件与 `docs/prompts/DEV-03.04R.md` 均为 25539 bytes、1136 个 CRLF，SHA256 `5a2d84b62cb5812292e2d1c80d16c1dec3fa6dcaee19a1c578dc6b4c1bc507d9`。

## 基线反例与根因

修改前使用互相隔离的系统临时根和公开 API 实际得到：

```text
FORGED_PUBLISH_AND_VALIDATE_ACCEPTED linear_gain=0.25 raw=74eefa7181d739272726fd59472ae0cd766ec7a8a9391b9a566f0031d6a81ab2 normalized=394fa3955c8eb587d1eb065ecaae2f5993f1eb005591cf7f4c36811925536ed4 run=run_forged-scenario
TAMPERED_ENVELOPE_ACCEPTED
TAMPERED_RUN_ACCEPTED measurement_order=999 module_id=NOT_BLK
TAMPERED_MANIFEST_SIDECAR_ACCEPTED
```

四个临时根在复现前均不存在，复现后只清理各自解析确认过的精确根并确认 `exists=False`。根因分别是：

1. `_validate_loaded_scenario()` 只核对对象内部 bytes/model/hash 的自洽性，没有重读来源文件，调用者可构造另一组同样自洽的模型与 normalized bytes。
2. validator 完全没有重建或比较 `synthetic_metadata.json`。
3. validator 只比较 run record 的少数字段；它信任 run 的 `measurement_order`、节点状态内容、软件版本、notes 和时间等旁路事实。
4. stored bundle 检查比较 manifest bytes 和配置快照，但漏掉同目录 manifest sidecar。

## 修正后的契约

`LoadedVirtualCaptureScenario` 现在保留解析后的 `source_path` 和 `project_root`。publisher 与 validator 均在持久化边界通过安全 YAML loader 重读同一个 project 内来源，然后要求当前 raw bytes/hash、strict parsed model、canonical normalized bytes/hash、relative source reference 与传入对象逐项一致。伪造、修改、删除、移动或移出 project root 都会拒绝；publisher 在执行或 staging 前报告 `published=false`，validator 只读报告 `published=true`。

`synthetic_metadata.json` 由一个规范构造函数生成，固定且仅允许 `capture_receipt_sha256`、`data_origin=synthetic`、`hardware_io_performed=false` 和固定 safety marker。validator 比较完整 canonical bytes，因此缺字段、多字段、语义变化和非 canonical 序列化均拒绝。

`VirtualCaptureReceipt` 新增 strict `measurement_order >= 0`，publisher 使用同一输入构造 receipt 和 run record；validator 从 receipt 取得预期顺序，不从可能被篡改的 run record 反推。随后重建完整 `MeasurementRunRecord`：身份、protocol、measurement order、synthetic/development/non-formal 语义、每个节点的精确 BLK 状态、config hashes、ArtifactRefs、backend、软件版本、complete/null failure/marker/fixed notes，以及三个相同 aware timestamp 的外层创建时间契约必须完全一致。

stored bundle 现在要求 `device_manifest.provisional.sha256` 存在，逐字节等于加载 bundle 的 sidecar，严格等于当前 manifest digest 与固定 filename 的 canonical sidecar，且 digest 等于 bundle receipt。validator 不修复或重写任何被篡改文件。

## TDD 记录

- 首个来源 RED：单测预期 forged scenario 被拒绝，实际 `Failed: DID NOT RAISE VirtualCapturePersistenceError`；实现来源重载闭环后 `1 passed`。
- metadata RED：semantic/extra/noncanonical 三例均 `DID NOT RAISE`；加入 canonical envelope 比较后 `3 passed`，最终再加入 missing-field 覆盖。
- run record RED：measurement order、NOT_BLK、software version、notes、created_at、started_at 六例均 `DID NOT RAISE`；receipt 顺序字段和完整 expected run 重建后 `7 passed`（含正常 receipt 字段断言），最终扩展 completed_at、backend、formal、marker、config hash、status/failure 和 ArtifactRef。
- manifest sidecar RED：零 digest 与删除两例均 `DID NOT RAISE`；加入 stored-sidecar 闭环后 `2 passed`，最终扩展 filename 与非 canonical bytes。
- receipt RED：正常发布对象没有 `measurement_order`；添加字段后转绿。负 measurement order 初次泄漏为 Pydantic `ValidationError`，前置持久化边界拒绝后 `1 passed` 且无 run/staging 残留。
- 原 DEV-03.04：`64 passed, 28 deselected`；新增 DEV-03.04R：`28 passed, 64 deselected`；合并文件 `92 passed`。

## 确定性双根演示

实际在以下两个预先确认不存在的根执行相同流程，结束后均确认不存在：

```text
$env:TEMP\acoustic-ladder-dev0304r-a-05f60f511ef140eea3d9e791d541ac08
$env:TEMP\acoustic-ladder-dev0304r-b-e9acb5e45599421f9bef432ef197e211
```

实际命令的可复刻形式如下；对两个 `$demoRoot` 各执行一次：

```powershell
$repoRoot = (Resolve-Path '.').Path
$demoRoot = Join-Path $env:TEMP 'acoustic-ladder-dev0304r-a-05f60f511ef140eea3d9e791d541ac08'
$essRoot = Join-Path $demoRoot 'ess'
$syntheticRoot = Join-Path $demoRoot 'synthetic'
$bundle = @('--project-root', $repoRoot, '--manifest', 'config/devices/device_manifest.provisional.json', '--manifest-sidecar', 'config/devices/device_manifest.provisional.sha256', '--audio', 'tests/fixtures/audio/ess_offline_development.yaml', '--protocol', 'config/protocols/stage4_four_node_states.yaml', '--analysis', 'config/analysis/default.yaml', '--synthetic', 'config/synthetic/default.yaml')
.venv\Scripts\acoustic-ladder.exe ess-generate-offline --project-root $repoRoot --audio-config tests/fixtures/audio/ess_offline_development.yaml --development-root $essRoot --artifact-id source_ess
.venv\Scripts\acoustic-ladder.exe ess-validate-offline --project-root $repoRoot --audio-config tests/fixtures/audio/ess_offline_development.yaml --artifact-root (Join-Path $essRoot 'source_ess')
.venv\Scripts\acoustic-ladder.exe create-synthetic-session @bundle --synthetic-root $syntheticRoot --session-id dev0304r --reassembly-id assembly001
.venv\Scripts\acoustic-ladder.exe simulate-duplex-capture @bundle --synthetic-root $syntheticRoot --session-id dev0304r --reassembly-id assembly001 --run-id capture001 --measurement-order 0 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
.venv\Scripts\acoustic-ladder.exe validate-simulated-capture @bundle --synthetic-root $syntheticRoot --session-id dev0304r --run-id capture001 --scenario tests/fixtures/audio/virtual_duplex_development.yaml --ess-artifact-root (Join-Path $essRoot 'source_ess')
.venv\Scripts\acoustic-ladder.exe validate-session --synthetic-root $syntheticRoot --session-id dev0304r
.venv\Scripts\acoustic-ladder.exe validate-run --synthetic-root $syntheticRoot --session-id dev0304r --run-id capture001
```

两次的八个 capture payload 逐字节一致，新 receipt SHA256 均为 `343afe1bfdfb6df83cafb30096f3d2777c3d3273cdf8ddfdc389d91a84e1f448`。外层 `run_record.json` 含真实运行时间，不属于八个确定性 payload，不要求跨运行字节一致。

稳定结果：scenario raw/normalized 为 `74eefa7181d739272726fd59472ae0cd766ec7a8a9391b9a566f0031d6a81ab2` / `cd5b82148d5fb88ea1fd86737510504030bca219ebe61de018b0f0b00bf90dbe`；output/input raw 为 `51531aedf7b6d253085315bf2ffd1efc7c760de363bc68565756ed5b2c2b3621` / `284c6bd0d320dfd0d1a97015d80e0bcc6aff3b49d9a2befbe68e55b5ef550b81`；output/input WAV 为 `1aea497f8868d1f2e187b2ed1f80efd7b05e4c0a6084f1901dcc425180bdb508` / `51d68378a916f82e9080cba276c8c5dfb386ffd19f4fb3c0b3dd9e9d594222b1`。样本数 13024、block 数 51、末 block 224，状态机与 synthetic/hardware flags 不变。

## 验收结果

- `uv --cache-dir .uv-cache sync --all-groups --frozen`：`Checked 29 packages`。
- 分组：DEV-01 `43 passed`；DEV-02.01 `66 passed`；DEV-02.02 `23 passed`；DEV-03.01 `36 passed`；DEV-03.02 `24 passed`；DEV-03.03/03.03R `85 passed`；DEV-03.04 原有 `64 passed`；DEV-03.04R 新增 `28 passed`。
- 最终 `uv ... pytest tests/dev03/test_virtual_capture.py -q`：`92 passed in 8.69s`；完整 `uv ... pytest -q`：`369 passed in 12.65s`，因此原 341 项全部保留。
- 最终 Ruff format：`91 files already formatted`；Ruff lint：`All checks passed!`；strict mypy：`Success: no issues found in 60 source files`；Schema：`PASS schema consistency`，总数 17；`git diff --check` PASS。
- skip/xfail/noqa/type-ignore、U+FFFD、本机路径/身份、新增真实音频 API/direct sounddevice/Stream/play/rec、tracked WAV/FLAC/NPY/NPZ、tracked cache/staging/lock 扫描均 PASS。
- 七个保护哈希依次为 `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`、`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`、`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`、`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`、`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`、`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`、`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`。
- ESS `smoke` 重新生成/验证：WAV/metadata/raw 为 `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0` / `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a` / `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`；临时根已清理。

## 修改文件与已知限制

新增 prompt archive、本报告；修改 `.gitattributes`、README、data README、virtual-capture 架构文档、receipt schema、virtual capture models/persistence 和回归测试。没有修改 DEV-03.04 prompt/report/历史日志条目、七个保护输入、正式 AudioConfig、ESS fixture、nominal scenario 参数、存储/domain/ESS/backend/state-machine 模块、模型包或校准文件。

已知限制：来源重读闭环针对协作式本地文件边界，不声称抵御能在检查与使用之间持续竞争的恶意进程；store 仍先发布 run directory 再追加跨目录 event，事件失败会保留不可变完成 run 并报告 `published=true`。虚拟 latency/gain 不是实测量，外层运行时间不是音频时钟。`virtual_duplex_scheduler_exercised=true` 仍不等于 `full_duplex_verified=true`。

未执行：production `audio-list`/`audio-inventory`、设备枚举/选择/绑定、Host API/通道确认、stream/open/play/record、真实输入输出、校准读取/应用、SPL/loopback/共享时钟/真实延迟验证、反卷积/DSP、正式协议、DEV-03.05 或 DEV-04。
