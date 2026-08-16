# DEV-03.04R 项目实施提示词——虚拟采集来源与封装语义闭环修正

你现在位于 Acoustic Ladder 的实际代码仓库中。

本步骤序列号：

`DEV-03.04R`

本步骤名称：

`虚拟采集来源与封装语义闭环修正`

这是 DEV-03.04 的有限修正步骤。

只修正已经独立复现的来源闭环、封装元数据、run record、manifest sidecar 和复刻日志问题。

不得扩展到：

- 新的采集功能；
- 真实音频后端；
- DEV-03.05；
- DEV-04；
- 反卷积；
- DSP；
- 实验协议执行；
- 任何真实硬件操作。

---

# 1. 修正目标

DEV-03.04 的核心实现已经通过：

- 逐 block 虚拟调度；
- 状态机；
- synthetic-only publication；
- output/input WAV 语义重放；
- 故障路径；
- 341 项测试；
- Ruff、mypy、17 个 Schema；
- 七个保护哈希；
- 三个 ESS golden hash；
- 无真实音频 I/O。

本步骤不得推翻或重写该实现。

本步骤只关闭以下四类问题：

1. `LoadedVirtualCaptureScenario` 的原始文件、模型和 normalized bytes 可以互相不一致；
2. `synthetic_metadata.json` 被篡改后 capture validator 仍接受；
3. `run_record.json` 的 BLK 状态和 measurement order 被篡改后仍接受；
4. stored provisional manifest sidecar 被篡改后仍接受；
5. DEV-03.04 演示 receipt 缺少完整身份和命令记录，无法仅凭日志复刻。

完成后必须证明：

```text
scenario source bytes
  -> safe parse
  -> strict model
  -> canonical normalized bytes
  -> recorded raw/normalized hashes
```

形成唯一闭环。

同时必须证明：

```text
capture receipt
synthetic_metadata.json
run_record.json
stored manifest sidecar
```

不存在互相矛盾但 validator 仍返回 PASS 的情况。

---

# 2. 硬件和研究边界

当前仍然没有连接：

- MOONDROP CHU II / 水月雨竹 2；
- Dayton Audio iMM-6C；
- Acoustic Ladder 实验装置。

必须继续保持：

```text
hardware_ready = false
full_duplex_verified = false
shared_clock_verified = false
channel_mapping_verified = false
calibration_file_verified = false
calibration_applied = false
absolute_spl_calibrated = false
electrical_loopback_available = false
device_binding = deferred_until_hardware_connection
```

本步骤严禁：

- 运行生产 `audio-list`；
- 运行生产 `audio-inventory`；
- 枚举或绑定设备；
- 查询 Host API；
- 选择通道；
- 调用任何 `sounddevice` 播放、录音或 Stream API；
- 播放 ESS；
- 录音；
- 读取麦克风校准文件；
- 测量 SPL；
- 测量真实延迟或时钟；
- 反卷积；
- 声学分析；
- 修改 CAD；
- 修改模型校准值。

继续保持：

```text
physical_print_status = actual_printed
calibration_status = applied
model_status = provisional
```

其中模型打印校准的 `calibration_status=applied` 不得与音频校准状态混淆。

---

# 3. Git 基线门禁

首先只读检查，不要立即修改。

必须确认：

- 仓库根目录正确；
- 当前分支为 `main`；
- 工作区干净；
- 无未跟踪用户文件；
- remote 为 `origin`；
- remote URL 为：

`https://github.com/haocheng26710/fingers.git`

本地 HEAD、`origin/main` 和 GitHub `main` 必须全部为：

`4efbba7bcb7b56baece117b3cacd7092b1bba706`

至少执行并记录：

```text
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git remote -v
git ls-remote origin refs/heads/main
git log -1 --format=fuller
```

扫描：

- `AGENTS.md`
- `CLAUDE.md`
- `CONTEXT.md`
- `docs/adr/`
- 其他项目指令

如果基线、远端、工作区或指令不符合，立即停止：

- 不 reset；
- 不 clean；
- 不 rebase；
- 不覆盖用户文件；
- 不提交；
- 不推送。

始终禁止：

```text
git reset --hard
git clean
force push
修改历史提交
amend DEV-03.04
rebase 已发布的 main
```

---

# 4. 归档提示词与日志

## 4.1 保存提示词

将实际收到的完整提示词保存为：

`docs/prompts/DEV-03.04R.md`

要求：

- 不总结；
- 不删节；
- 不改写；
- 有原始附件时直接复制；
- 比较源文件与归档文件 SHA256；
- 如实记录编码、换行和保存方法；
- 如需保留 CRLF 审计字节，在 `.gitattributes` 中标记 binary。

## 4.2 实施日志

读取：

`docs/IMPLEMENTATION_LOG.md`

既有文件全部字节必须继续作为新文件的完整前缀。

不得修改 DEV-03.04 条目。

只允许在末尾新增：

`## DEV-03.04R`

开始时记录：

- 序列号；
- 名称；
- `IN_PROGRESS`；
- 开始时间和时区；
- 基线提交；
- 远端基线；
- 本步骤有限范围；
- 四组已知反例；
- 硬件禁止范围。

执行中持续记录：

- 实际复现输出；
- TDD red run；
- 根因；
- 实际代码修正；
- 文件；
- 命令；
- 测试数量；
- 哈希；
- 演示标识；
- 失败及修正；
- 未执行内容；
- Git 门禁。

结束状态只能是实际状态：

```text
PASSED
FAILED
BLOCKED
INTERRUPTED
```

不得预填通过、提交 SHA 或推送结果。

---

# 5. 开始前复现四个缺陷

必须在未修改生产代码的基线提交上，在系统临时目录中重新复现。

不得直接把以下字符串写进日志假装运行；必须记录真实输出。

## 5.1 场景原始字节与模型错配

构造一个 `LoadedVirtualCaptureScenario`：

- `original_bytes` 仍来自正式 development scenario，其中 `linear_gain=0.5`；
- `original_sha256` 仍为该原始文件哈希；
- `model.linear_gain` 改为 `0.25`；
- normalized bytes/hash 根据 0.25 模型重新生成。

在基线实现中调用：

- `publish_virtual_capture`
- `validate_virtual_capture`

预期复现基线缺陷：

```text
FORGED_PUBLISH_AND_VALIDATE_ACCEPTED
linear_gain=0.25
raw hash 对应原始 0.5 文件
normalized hash 对应 0.25 模型
```

必须确认该反例没有接触真实硬件。

## 5.2 `synthetic_metadata.json` 篡改

先生成一个正常虚拟 capture，再将：

`synthetic_metadata.json`

改成 canonical JSON，但内容包含例如：

```json
{
  "capture_receipt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "data_origin": "real",
  "hardware_io_performed": true,
  "safety_marker": "FALSE_CLAIM"
}
```

在基线实现中重新运行 capture validator。

预期复现：

`TAMPERED_ENVELOPE_ACCEPTED`

## 5.3 `run_record.json` 篡改

生成正常 capture 后，保持 node ID 集合不变，但将至少一个节点改为：

```text
module_id = NOT_BLK
state_id = tampered
discrete_label = NOT_BLK
```

并将：

`measurement_order = 999`

重新写成 canonical JSON，然后运行 capture validator。

预期复现：

`TAMPERED_RUN_ACCEPTED`

## 5.4 manifest sidecar 篡改

修改 synthetic session 内：

`manifest/device_manifest.provisional.sha256`

使其内容与实际 manifest 不一致，再运行 capture validator。

预期复现：

`TAMPERED_MANIFEST_SIDECAR_ACCEPTED`

所有反例必须使用自己创建的精确临时根。

完成复现后仅清理这些临时根。

不得修改仓库内正式数据。

---

# 6. 受保护哈希

重新计算以下文件，不得照抄。

## 6.1 七个保护输入

```text
reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip
1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b

config/devices/device_manifest.provisional.json
bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0

reference/audio/inventory/DEV-03.01_audio_inventory.json
8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2

reference/audio/inventory/DEV-03.02_inventory_capture_context.json
10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c

reference/audio/inventory/DEV-03.02_audio_inventory_summary.md
84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159

reference/audio/inventory/DEV-03.02_contextual_preflight_report.json
e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15

reference/audio/hardware_setup.provisional.json
013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1
```

## 6.2 ESS golden

```text
WAV:
608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0

Metadata:
e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a

Raw float32:
eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca
```

## 6.3 DEV-03.04 场景和音频结果

正常 scenario 必须继续保持：

```text
raw:
74eefa7181d739272726fd59472ae0cd766ec7a8a9391b9a566f0031d6a81ab2

normalized:
cd5b82148d5fb88ea1fd86737510504030bca219ebe61de018b0f0b00bf90dbe
```

正常虚拟采集必须继续保持：

```text
output raw float32:
51531aedf7b6d253085315bf2ffd1efc7c760de363bc68565756ed5b2c2b3621

input raw float32:
284c6bd0d320dfd0d1a97015d80e0bcc6aff3b49d9a2befbe68e55b5ef550b81

output WAV:
1aea497f8868d1f2e187b2ed1f80efd7b05e4c0a6084f1901dcc425180bdb508

simulated input WAV:
51d68378a916f82e9080cba276c8c5dfb386ffd19f4fb3c0b3dd9e9d594222b1
```

旧 receipt hash：

`a58351bc1efc50cb40263f78949f923d5358c90f701e1b63f4b33281cba80480`

不作为本步骤必须保持的 golden，因为：

- 旧日志没有完整记录生成它的 identity 输入；
- 本步骤需要把 `measurement_order` 纳入 receipt；
- receipt Schema 和字节预计会合法变化。

必须在报告中明确说明旧 receipt hash 被替换的原因，不得描述成 WAV 或算法漂移。

---

# 7. 场景来源闭环修正

当前 `_validate_loaded_scenario()` 只分别验证：

- original bytes hash；
- model 的 canonical normalized bytes；
- normalized hash。

它没有证明 model 是由 original bytes 解析得到。

必须修正为完整链：

```text
source file current bytes
  == loaded.original_bytes

SHA256(source bytes)
  == loaded.original_sha256

safe parse(source bytes)
  -> strict VirtualCaptureScenario

parsed model
  == loaded.model

canonical_json(parsed model)
  == loaded.normalized_bytes

SHA256(canonical normalized bytes)
  == loaded.normalized_sha256

source path relative to project root
  == loaded.original_relative_path
```

## 7.1 推荐实现

可以选择以下方式之一：

### 方式 A

让 `LoadedVirtualCaptureScenario` 在内存中同时保存：

- resolved source path；
- resolved project root；
- relative reference；
- original bytes；
- parsed model；
- normalized bytes；
- hashes。

在 publish/validate 边界重新读取 source path，并调用相同安全 loader 重建整个对象后逐字段比较。

### 方式 B

让公共 publish/validate API 接受 scenario path 和 project root，并在 API 内部调用唯一 loader，不再信任调用者构造的 `LoadedVirtualCaptureScenario`。

无论选择哪种方式，都必须保证：

- public persistence 边界无法接受 raw/model/normalized 互相不一致的组合；
- source 文件在 load 后发生修改时拒绝；
- source 文件被删除、移动或逃逸 project root 时拒绝；
- YAML duplicate key/custom tag 等安全规则保持不变；
- 拒绝发生在 run 或 staging 创建之前；
- engine 的纯内存 strict model API可以保留。

不得通过“约定调用者不要直接构造 dataclass”解决。

必须由代码强制。

---

# 8. `synthetic_metadata.json` 闭环

建立单一函数生成期望字节，例如：

```text
expected_synthetic_metadata_bytes(receipt_sha256)
```

期望内容必须精确为：

```json
{
  "capture_receipt_sha256": "<actual receipt sha256>",
  "data_origin": "synthetic",
  "hardware_io_performed": false,
  "safety_marker": "SYNTHETIC_VIRTUAL_CAPTURE_NOT_AN_EXPERIMENTAL_RESULT"
}
```

要求：

- canonical JSON；
- UTF-8；
- LF 结尾；
- 不允许额外字段；
- 不允许缺失字段；
- 不允许其他 origin；
- hardware flag 只能为 false；
- receipt hash 必须与实际 receipt bytes 一致；
- safety marker 必须精确一致。

capture validator 必须读取并 byte-exact 比较。

不得只检查它是合法 JSON。

必须拒绝：

- `data_origin=real`；
- `hardware_io_performed=true`；
- 错误 receipt hash；
- 错误 marker；
- 添加额外字段；
- 非 canonical bytes；
- 内容篡改后重新保存为 canonical JSON。

不强制新增第三个 Schema；如果采用内部 exact canonical contract，生成 Schema 总数应继续为 17。

---

# 9. `run_record.json` 闭环

将 `measurement_order` 加入：

`VirtualCaptureReceipt`

要求：

```text
measurement_order >= 0
```

publish 时 receipt 和 run record 必须从同一个已验证输入派生。

capture validator 必须验证 run record 至少以下全部字段：

- `run_id`；
- `session_id`；
- `reassembly_id`；
- `protocol_id`；
- `measurement_order` 等于 receipt；
- `data_origin=synthetic`；
- `run_mode=development`；
- `formal_eligible=false`；
- node states 精确等于 `_blocked_states(bundle)` 的派生结果；
- config hashes 精确等于 loaded bundle；
- artifacts 精确等于重建的 ArtifactRef；
- backend 精确为 `deterministic_virtual_duplex`；
- software version 符合当前创建契约；
- status 为 `complete`；
- failure reason 为 `null`；
- result marker 为 `NOT_EXPERIMENTAL_RESULT`；
- notes 符合固定 synthetic capture 契约；
- created/started/completed time 均为 aware datetime；
- 三个 run 时间满足当前创建契约；
- identity 与实际 session/run 路径一致。

必须拒绝：

- 任一节点不是派生的 BLK；
- state ID、module ID、label 或 provenance 篡改；
- measurement order 篡改；
- backend 篡改；
- config hash 篡改；
- formal flag 篡改；
- result marker 篡改；
- failure/status 矛盾；
- notes 被替换；
- ArtifactRef 被替换。

validator 不得从已经被篡改的 run record 中读取 measurement order，再用它生成“期望 receipt”而形成自证循环。

期望值必须优先来自：

- receipt；
- loaded bundle；
-固定 capture 契约；
- 实际路径；
-确定性重放结果。

其中 node states 必须完全从 manifest/bundle 派生。

---

# 10. stored manifest sidecar 闭环

在 `_validate_stored_bundle()` 或等价位置增加：

1. stored manifest bytes 必须等于 `bundle.manifest_bytes`；
2. stored manifest sidecar bytes 必须等于 `bundle.manifest_sidecar_bytes`；
3. sidecar 必须实际解析为：
   - 正确的 manifest SHA256；
   - 正确的文件名；
4. manifest SHA256 必须等于 bundle receipt 中的 manifest SHA256。

必须拒绝：

- sidecar 全零；
- sidecar 文件名错误；
- sidecar digest 错误；
- sidecar 多余字段；
- sidecar 与 loaded bundle 不一致。

不得通过重写 sidecar 自动修复。

validator 必须保持只读。

---

# 11. 回归测试

先增加失败测试，再修改生产代码。

必须保留真实 red run。

DEV-03.04 当前测试基线：

```text
64 passed
```

完整基线：

```text
341 passed
```

建议至少新增 12 项真实回归测试。

## 11.1 场景闭环

至少测试：

1. original 0.5 / model 0.25 / normalized 0.25 被 publish 拒绝；
2. 同一 forged object 被 validate 拒绝；
3. source file 在 load 后修改被拒绝；
4. source file在 load 后删除被拒绝；
5. relative path/source path 不一致被拒绝；
6. 全部拒绝发生在 run/staging 创建前。

## 11.2 synthetic metadata

至少测试：

- origin 改为 real；
- hardware flag 改为 true；
- receipt hash 改为零；
- marker 改写；
- canonical 篡改；
- 非 canonical bytes；
- validator 不重写文件。

## 11.3 run record

至少测试：

- BLK 改成 NOT_BLK；
- measurement order 改写；
- backend 改写；
- formal flag 改为 true；
- marker 改写；
- config hash 改写；
- status/failure reason 矛盾；
- ArtifactRef 改写。

## 11.4 manifest sidecar

至少测试：

- digest 改为零；
- filename 改写；
- sidecar 内容改变但 manifest bytes 不变；
- validator 只读拒绝。

## 11.5 正常路径

必须证明：

- output/input raw hash 不变；
- output/input WAV hash不变；
- scenario raw/normalized hash不变；
- 13024 samples；
- 51 blocks；
- last block 224；
-状态机不变；
- synthetic/hardware flags不变；
-新的 receipt 可重复生成相同字节。

不得使用：

- skip；
- xfail；
- noqa；
- type ignore；
- 宽泛异常吞噬

掩盖失败。

---

# 12. Schema

更新：

`VirtualCaptureReceipt`

增加：

`measurement_order`

重新由模型导出：

`schemas/virtual_capture_receipt.schema.json`

不得手工修改生成 Schema。

预期 Schema 总数继续为：

`17`

如果数量变化，必须解释具体模型原因。

`virtual_capture_scenario.schema.json` 不应因本次来源验证修正发生无理由漂移。

执行 Schema consistency 检查。

---

# 13. 可复刻演示

重新运行正常软件演示。

本次必须固定并记录以下 identity：

```text
ESS artifact ID: source_ess
session ID: dev0304r
reassembly ID: assembly001
run ID: capture001
measurement order: 0
```

使用：

- development ESS audio config；
- stage4 protocol snapshot；
- default analysis config；
- default synthetic config；
-正式 nominal virtual capture scenario。

必须记录完整、可直接复制的实际命令，不得只写“运行了演示”。

至少记录：

- project root 参数；
- manifest/sidecar；
- audio config；
- protocol；
- analysis；
- synthetic config；
- scenario；
- ESS root；
- synthetic root；
-全部 identity；
- measurement order。

在两个分别预先确认不存在的临时根中重复运行相同演示。

两次必须证明 capture payload 中以下文件逐字节一致：

```text
excitation.metadata.json
excitation.metadata.sha256
output_reference.wav
output_reference.wav.sha256
simulated_input.wav
simulated_input.wav.sha256
capture_receipt.json
capture_receipt.sha256
```

外层 run record 包含运行时间，可以不要求两次逐字节相同；但必须说明这一边界。

两次 receipt SHA256 必须一致。

重新记录新的 receipt SHA256。

必须保留：

```text
output raw:
51531aedf7b6d253085315bf2ffd1efc7c760de363bc68565756ed5b2c2b3621

input raw:
284c6bd0d320dfd0d1a97015d80e0bcc6aff3b49d9a2befbe68e55b5ef550b81

output WAV:
1aea497f8868d1f2e187b2ed1f80efd7b05e4c0a6084f1901dcc425180bdb508

input WAV:
51d68378a916f82e9080cba276c8c5dfb386ffd19f4fb3c0b3dd9e9d594222b1
```

如果这些 WAV/raw hash 变化，停止并调查，不得接受。

演示结束后：

- 仅清理自己创建的精确临时根；
- 验证 resolved parent；
- 不使用宽泛 glob；
- 确认根不存在；
- 不删除仓库或用户数据。

---

# 14. 预期文件范围

建议新增：

```text
docs/prompts/DEV-03.04R.md
docs/reports/DEV-03.04R.md
```

建议修改：

```text
src/acoustic_ladder/audio/virtual_capture_models.py
src/acoustic_ladder/audio/virtual_capture_persistence.py
tests/dev03/test_virtual_capture.py
schemas/virtual_capture_receipt.schema.json
docs/architecture/virtual-capture.md
README.md
docs/IMPLEMENTATION_LOG.md
.gitattributes
```

如果需要从字节安全重解析 YAML，可以有限修改：

```text
src/acoustic_ladder/config/yaml_loader.py
```

但必须保证所有原配置加载测试继续通过。

除非测试证明必要，不得修改：

```text
src/acoustic_ladder/audio/virtual_capture.py
src/acoustic_ladder/audio/virtual_capture_backend.py
src/acoustic_ladder/audio/ess.py
src/acoustic_ladder/audio/excitation_persistence.py
src/acoustic_ladder/storage/store.py
src/acoustic_ladder/domain/models.py
```

不得修改：

- DEV-03.04 prompt；
- DEV-03.04 report；
- DEV-03.04 原日志条目；
- 七个保护输入；
-正式 AudioConfig；
- ESS development fixture；
- nominal virtual scenario 参数；
-模型包和校准文件。

---

# 15. 文档和报告

新增：

`docs/reports/DEV-03.04R.md`

必须包括：

- baseline；
- 四个基线反例真实输出；
- 每个根因；
- 修正方式；
- raw/model/normalized 闭环；
- synthetic metadata contract；
- run record contract；
- manifest sidecar contract；
-新增 receipt 字段；
- TDD red/green；
-测试数量；
- Schema 数量；
-两次固定 identity 演示命令；
-新 receipt hash；
- output/input hash不变证明；
-保护哈希；
-未执行硬件范围；
-已知限制；
- Git 尚未提交时不能自引用最终 SHA。

更新架构文档，明确：

- `Loaded*` 名称本身不是信任证明；
- persistence boundary 会重新建立 source-bytes-to-model 链；
- envelope 和 run record 不能作为未验证旁路事实；
- manifest sidecar 也是 stored bundle 的审计组成部分；
- receipt 的 measurement order 与 run record 绑定；
-运行时间仍属于外层 run record，不是确定性音频时钟。

更新 README，只加入必要的 DEV-03.04R 验证说明。

---

# 16. 完整验证

至少运行：

```text
uv --cache-dir .uv-cache sync --all-groups --frozen
```

然后运行：

```text
uv --cache-dir .uv-cache run pytest tests/dev03/test_virtual_capture.py
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
git diff --check
```

分组记录：

- DEV-01；
- DEV-02.01；
- DEV-02.02；
- DEV-03.01；
- DEV-03.02；
- DEV-03.03/03.03R；
- DEV-03.04/03.04R；
-完整测试。

原 341 项必须全部继续通过。

扫描：

- skip/xfail；
- suppression；
- U+FFFD；
- 本机路径/身份；
-真实音频调用；
- direct sounddevice import；
- Stream/play/rec；
- tracked WAV/FLAC/NPY/NPZ；
- staging；
- lock；
-临时目录；
-未跟踪文件。

重新计算：

-七个保护哈希；
-三个 ESS golden；
-scenario raw/normalized；
-output/input raw；
-output/input WAV；
-新 receipt；
-prompt archive。

验证实施日志：

-基线文件完整作为前缀；
-只追加 DEV-03.04R；
-不得改写 DEV-03.04。

---

# 17. Git 提交和推送

只有以下全部通过才能提交：

-四个反例全部转为拒绝；
-正常虚拟采集仍通过；
-原 341 项全部通过；
-新增测试通过；
-完整测试通过；
-Ruff 通过；
-strict mypy 通过；
-17 个 Schema 通过；
-diff check 通过；
-保护哈希不变；
-ESS golden 不变；
-output/input raw/WAV 不变；
-两次固定 identity receipt 字节一致；
-日志和报告真实；
-无真实硬件调用；
-工作区只包含预期修改。

提交前再次执行：

```text
git ls-remote origin refs/heads/main
```

远端必须仍为：

`4efbba7bcb7b56baece117b3cacd7092b1bba706`

如果远端变化，停止，不得 rebase、merge 或 force push。

建议提交主题：

`DEV-03.04R: close virtual capture provenance and envelope validation`

提交后：

1. 确认工作区干净；
2. 正常执行：

```text
git push origin main
```

3. 不得 force push；
4. 再次读取 GitHub `main`；
5. 确认：

```text
local HEAD
origin/main
GitHub refs/heads/main
```

完全一致。

任何测试、提交或推送错误都必须如实报告。

若未全部通过：

- 不提交；
- 不推送；
- 不进入下一阶段。

---

# 18. 最终回复格式

成功时报告：

- `PASS — DEV-03.04R 完成`
- commit SHA；
- branch；
- remote；
- local/origin/GitHub 一致性；
-工作区状态；
-原测试数量；
-新增测试数量；
-完整测试数量；
-Ruff/mypy/Schema/diff；
-四个反例现在的拒绝结果；
-scenario raw/normalized；
-output/input raw；
-output/input WAV；
-新 receipt SHA256；
-两次 receipt 是否一致；
-七个保护哈希；
-三个 ESS golden；
-硬件枚举：否；
-播放：否；
-录音：否；
-Stream：否；
-`hardware_ready=false`；
-主要文件；
-已知限制。

必须明确写出：

```text
DEV-03.04R 只关闭虚拟采集来源和封装审计缺口。
没有增加真实音频能力。
virtual_duplex_scheduler_exercised=true 仍不等于 full_duplex_verified=true。
没有连接、枚举、播放、录音或验证任何真实音频硬件。
```

失败或中断时报告：

- FAILED/BLOCKED/INTERRUPTED；
-失败门禁；
-真实错误；
-已修改文件；
-是否存在本地 commit；
-明确说明未推送。

完成后停止。

不得自行进入 DEV-03.05、DEV-04 或真实硬件阶段。