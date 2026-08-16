# DEV-03.03R 修正提示词——ESS 配置溯源与数值边界闭环

你现在位于 Acoustic Ladder 实际代码仓库中。

本步骤序列号：

`DEV-03.03R`

本步骤名称：

`ESS 配置溯源与数值边界闭环修正`

这是 DEV-03.03 的有限修正步骤。只修正已经独立复现的三个问题，不得扩展到 DEV-03.04、真实采集、反卷积或其他后续功能。

完成本步骤后停止。

---

# 1. 修正目标

独立审查已经确认 DEV-03.03 的主流程、262 项测试、WAV 哈希、元数据哈希和安全边界基本正确，但发现以下问题。

## 1.1 配置溯源缺口

当前底层公开函数：

- `publish_offline_ess_artifact`
- `validate_offline_ess_artifact`

同时接受：

- `LoadedConfig`
- 调用者独立传入的 `EssSignalSpec`

函数只检查 metadata 中的 spec 是否等于调用者提供的 spec，没有证明该 spec 实际由 `LoadedConfig.model` 派生。

已复现：

- 已加载配置中的 `ess_digital_peak_dbfs = -20.0`
- 调用者另行构造 `ess_digital_peak_dbfs = -18.0` 的 spec
- 发布成功
- 验证成功
- metadata 继续记录原始 -20 dBFS 配置的 SHA256
- metadata spec 和实际波形却是 -18 dBFS

复现结果：

`MISMATCH_ACCEPTED ... metadata=-18.0 config=-20.0`

这会产生“配置哈希正确，但实际 ESS 参数与配置不同”的错误审计链。

## 1.2 零样本 sweep 规格被模型接受

当前 `EssSignalSpec` 只要求：

`sweep_duration_s > 0`

但非常小的正数经过：

`floor(seconds * sample_rate + 0.5)`

可能得到：

`sweep_sample_count = 0`

已复现：

`TINY_SPEC_ACCEPTED 0`

不合法规格应在 strict 模型阶段被拒绝，而不是留到生成阶段产生其他异常。

## 1.3 极低 dBFS 导致未受控除零

当前模型只规定：

`digital_peak_dbfs <= 0`

极端低值可能在转换或 float32 量化后成为零幅值，随后在计算：

`crest_factor = actual_peak / rms`

时触发：

`ZeroDivisionError`

已复现：

`digital_peak_dbfs = -10000.0`

结果：

`ZeroDivisionError: float division by zero`

这应当在规格验证阶段拒绝，并在生成阶段保留防御性检查，不能暴露原始除零异常。

---

# 2. 冻结条件

以下内容不得改变。

## 2.1 研究边界

正式实验仍为：

`1 个扬声器输出 + 1 个麦克风输入`

即：

`1 + 1`

边界保持：

- TX 近端：扬声器；
- RX 近端：麦克风；
- TX 远端：闭合；
- RX 远端：闭合；
- 未使用节点：BLK；
- 不增加正式通道；
- 不改变阶段 1–4 的实验定义。

## 2.2 模型与硬件状态

继续保持：

- `model_status = provisional`
- `physical_print_status = actual_printed`
- `calibration_status = applied`
- `hardware_ready = false`
- `full_duplex_verified = false`
- `shared_clock_verified = false`
- `channel_mapping_verified = false`
- `calibration_file_verified = false`
- `absolute_spl_calibrated = false`

当前仍未连接：

- MOONDROP CHU II；
- Dayton Audio iMM-6C；
- 实验装置。

不得：

- 枚举真实硬件；
- 绑定设备；
- 选择 Host API；
- 选择输入/输出通道；
- 播放；
- 录音；
- 打开音频流；
- 读取或应用麦克风校准文件；
- 进行绝对 SPL 校准。

## 2.3 正式 ESS 配置

`config/audio/default_1x1_ess.yaml` 中以下字段必须继续为 `null`：

- `ess_duration_s`
- `pre_silence_s`
- `post_silence_s`
- `ess_fade_in_s`
- `ess_fade_out_s`
- `ess_digital_peak_dbfs`
- `output_gain_db`
- `input_gain_db`

不得填写正式值。

DEV-03.03 development fixture 的参数仍然只是软件测试输入，不是正式参数或听力安全建议。

---

# 3. Git 基线门禁

开始前必须确认：

- 分支为 `main`；
- 工作区干净；
- remote 为 `origin`；
- remote URL 为：

`https://github.com/haocheng26710/fingers.git`

本地 HEAD、`origin/main` 和 GitHub `main` 必须全部为：

`7a5859a84a606f535e2c91f4a16d7a69acb332be`

建议实际运行并记录：

- `git status --short --branch`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `git remote -v`
- `git ls-remote origin refs/heads/main`
- 项目级 `AGENTS.md`、`CLAUDE.md`、`CONTEXT.md` 扫描

如果基线不一致、远端已经前进或工作区不干净：

- 立即停止；
- 不得 reset；
- 不得 clean；
- 不得覆盖用户文件；
- 不得提交；
- 不得推送。

禁止：

- `git reset --hard`
- `git clean`
- force push
- amend DEV-03.03
- rebase 已发布的 `main`
- 删除或改写历史提交

---

# 4. 提示词与日志

## 4.1 保存本提示词

将本提示词保存为：

`docs/prompts/DEV-03.03R.md`

要求：

- 保存实际收到的完整提示词；
- 不得总结或删节；
- 如有原始附件，优先直接复制并比较 SHA256；
- 如附件换行与显示格式冲突，保留原始审计字节并如实记录；
- 在 `.gitattributes` 中按既有提示词归档方式防止 Git 自动改写；
- 不得修改任何旧提示词。

## 4.2 实施日志

只允许在：

`docs/IMPLEMENTATION_LOG.md`

末尾追加：

`## DEV-03.03R`

不得修改 DEV-01、DEV-02、DEV-03.01、DEV-03.02 或 DEV-03.03 的既有日志字节。

新条目使用相同格式，至少记录：

- 序列号；
- 名称；
- 状态；
- 开始时间及时区；
- 基线提交；
- 三个复现问题；
- 实际修正；
- 实际修改文件；
- 测试数量；
- 初次失败及修正；
- 实际命令；
- 保护哈希；
- 未执行项目；
- Git 门禁结果；
- 已知限制。

开始时状态为：

`IN_PROGRESS`

只有全部验收通过后才能改为：

`PASSED`

失败或中断必须使用真实状态，且不得推送。

---

# 5. 受保护文件和哈希

重新计算并核对，不得只复制本提示词中的值。

## 5.1 V1.3 ZIP

文件：

`reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip`

SHA256：

`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`

## 5.2 provisional manifest

文件：

`config/devices/device_manifest.provisional.json`

SHA256：

`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

## 5.3 inventory

文件：

`reference/audio/inventory/DEV-03.01_audio_inventory.json`

SHA256：

`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

## 5.4 capture context

文件：

`reference/audio/inventory/DEV-03.02_inventory_capture_context.json`

SHA256：

`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`

## 5.5 summary

文件：

`reference/audio/inventory/DEV-03.02_audio_inventory_summary.md`

SHA256：

`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`

## 5.6 contextual preflight

文件：

`reference/audio/inventory/DEV-03.02_contextual_preflight_report.json`

SHA256：

`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`

## 5.7 hardware setup

文件：

`reference/audio/hardware_setup.provisional.json`

SHA256：

`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

不得修改：

- 上述所有文件及 sidecar；
- DEV-03.03 development fixture 的已确认有效参数，除非测试明确需要临时副本；
- 既有 DEV-03.03 报告；
- 既有 DEV-03.03 提示词；
- 既有实施日志内容；
- 已提交 Schema 数量；
- 既有演示哈希。

DEV-03.03 有效演示哈希必须继续保持：

- WAV：`608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- Metadata：`e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- Raw float32：`eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

如果有效 development fixture 的三个哈希发生变化，默认判定为失败；只有发现并证明原 DEV-03.03 数学或序列化本身错误时才能提出变更，不得静默更新预期值。

---

# 6. 修正一：配置必须成为 ESS 规格的唯一权威来源

涉及：

- `src/acoustic_ladder/audio/excitation_persistence.py`
- `src/acoustic_ladder/audio/ess.py`
- `src/acoustic_ladder/cli.py`
- 相关测试

## 6.1 推荐设计

公开的持久化 API 不应允许调用者独立决定一份与配置脱钩的 spec。

优先将公开接口调整为：

`publish_offline_ess_artifact(development_root, artifact_id, loaded)`

`validate_offline_ess_artifact(artifact_root, loaded)`

两个函数内部必须：

1. 确认 `loaded.kind == "audio"`；
2. 确认 `loaded.model` 是 `AudioConfig`；
3. 调用唯一的 `spec_from_audio_config(loaded.model)`；
4. 使用内部派生的 spec 生成或验证；
5. 不接受调用者覆盖 spec；
6. metadata 中的 spec 必须来自该内部派生结果；
7. metadata 中的原配置与 normalized 配置哈希必须来自同一个 `LoadedConfig`。

如果为了内部 staging 验证需要传递 spec：

- 只能放在私有函数中；
- 私有函数名应以 `_` 开头；
- 对外公开入口必须重新从配置派生；
- 不得让 CLI 或未来采集引擎绕过配置一致性检查。

允许的备选方案：

- 暂时保留显式 spec 参数；
- 但必须在创建目录、写入文件或读取 artifact 前，重新从 `LoadedConfig` 派生 expected spec；
- 使用严格模型相等性比较；
- 不一致立即抛出明确的 `EssArtifactError`；
- 后续所有行为只能使用派生的 expected spec，不能继续信任调用者参数。

优先采用移除公开 spec 参数的设计，以从接口层消除双重事实来源。

## 6.2 CLI

更新：

- `ess-generate-offline`
- `ess-validate-offline`

CLI 只加载配置并调用公开 API。

不得：

- 在 CLI 中派生一份 spec，再允许底层接受任意另一份 spec；
- 增加 `--peak`、`--duration` 等绕过配置的参数；
- 添加环境变量覆盖；
- 添加默认值；
- 修改正式配置的 null 字段。

## 6.3 配置一致性验证

验证流程必须证明：

`metadata.spec == spec_from_audio_config(loaded.model)`

并证明：

- WAV 是从该 spec 重新生成；
- raw hash 属于该 WAV；
- metadata config hash 属于同一个 loaded config；
- 不能通过同时提交“原配置哈希 + 另一份合法 spec”绕过。

不一致错误必须明确包含类似含义：

`ESS specification does not match the loaded audio configuration`

不得只返回模糊的 sidecar 错误。

## 6.4 写入前失败

任何配置/spec 不一致必须发生在：

- 创建 development root 前；
- 创建 staging 目录前；
- 创建 lock 前；
- 写入 WAV 前；
- 写入 metadata 前。

失败后不得留下：

- development root；
- artifact directory；
- staging；
- lock；
- sidecar；
- 部分文件。

---

# 7. 修正二：sweep 派生样本数边界

涉及：

`src/acoustic_ladder/audio/excitation_models.py`

在 `EssSignalSpec` strict 模型验证阶段计算：

`sweep_count = floor(sweep_duration_s * sample_rate_hz + 0.5)`

必须要求：

`sweep_count >= 2`

理由：

- 0 个样本无法形成 sweep；
- 1 个样本只有 `t=0`，正弦值为零；
- 无法形成非零峰值；
- 无法表达从起始频率向结束频率变化的离散信号；
- 不应留给生成阶段产生 Pydantic timing 错误或零峰值错误。

错误信息必须明确，例如：

`sweep duration must produce at least two samples`

必须测试：

- 取整为 0 的正时长被拒绝；
- 取整为 1 的正时长被拒绝；
- 刚好取整为 2 的时长可以通过规格验证；
- 原 12000 样本 development fixture 不变；
- Schema consistency 继续通过。

不要人为规定正式 sweep 时长的最小秒数；约束应基于采样率和派生样本数。

---

# 8. 修正三：dBFS 和零能量防御

涉及：

- `src/acoustic_ladder/audio/excitation_models.py`
- `src/acoustic_ladder/audio/ess.py`

## 8.1 规格阶段

对：

`target_peak = 10 ** (digital_peak_dbfs / 20)`

执行明确验证。

必须要求：

- target peak 为 finite；
- target peak > 0；
- 转换为 NumPy float32 后仍严格大于 0；
- 不允许 underflow 成零；
- 不允许无法由 float32 ESS 表示的目标幅度。

不得随意选择一个未经解释的固定最低 dBFS。

应根据 float32 可表示性判断，例如使用实际 float32 转换或明确的 `np.nextafter`/`np.finfo` 边界。

错误信息应说明：

`digital peak is not representable as a positive float32 amplitude`

生成的 JSON Schema 可能无法完整表达这一跨字段/浮点表示约束，因此必须：

- 保留 Pydantic model validator；
- 在架构文档中说明；
- 通过运行时测试证明；
- 不得手工伪造 Schema 条件。

## 8.2 生成阶段防御

即使 strict spec 已验证，`generate_ess` 仍必须防御：

- target peak 非 finite；
- target peak ≤ 0；
- normalization factor 非 finite；
- float32 转换后实际 peak ≤ 0；
- RMS ≤ 0；
- RMS 非 finite；
- crest factor 非 finite；
- 波形全零。

发生这些情况时必须抛出项目级明确异常：

`EssError`

不得暴露：

- `ZeroDivisionError`
- `OverflowError`
- NumPy runtime warning 后继续生成
- 含 NaN/Infinity 的 metadata

错误必须发生在 artifact 写入前。

## 8.3 有效边界

至少测试：

- `-10000 dBFS` 被规格模型拒绝；
- 一个转换为 0 float32 的有限 dBFS 被拒绝；
- 一个非常低但仍能转换成正 float32 的值按实际设计决定是否允许；
- 如果允许，生成结果 peak 和 RMS 必须大于 0；
- `0 dBFS` 在纯数学开发规格中仍可由模型表达，但不得被解释为播放安全；
- 原 development fixture `-20 dBFS` 的数组和三个哈希完全不变。

---

# 9. 独立数学参考测试

DEV-03.03 的现有测试验证了数学性质，但没有固定的独立参考向量或等价 golden reference。

本修正必须补充至少一种独立参考。

推荐同时增加：

## 9.1 固定 fixture golden hashes

对现有 `smoke` artifact ID 和 development fixture，直接断言：

- WAV SHA256：

`608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`

- Metadata SHA256：

`e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`

- Raw float32 SHA256：

`eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

## 9.2 固定数值参考

选取一个规模很小但至少包含多个有效 sweep 样本的规格。

使用独立公式计算并硬编码：

- 若干指定采样时刻的理论 phase；
- 对应理论瞬时频率；
- 淡入淡出前的指定 sweep 样本；
- 归一化后的指定 float32 样本；
- 或完整小型 raw float32 reference hash。

参考值的生成方法必须记录在 DEV-03.03R 日志或报告中。

不得在测试运行时调用同一个生产函数生成 expected，再与自身比较。

可以使用：

- 独立公式脚本；
- 高精度计算；
- 单独手算/外部计算得到的固定常量；
- 已经人工复核的 hard-coded reference。

测试误差容限必须基于数值精度说明，不能过宽。

---

# 10. 必须新增的回归测试

新增或扩展：

`tests/dev03/test_ess_offline.py`

建议至少新增 10 个测试用例，使完整测试数不少于：

`272 passed`

实际数量以 pytest collection 为准。

至少包括：

1. 原配置 -20 dBFS 与显式 -18 dBFS spec 不一致时，公开发布 API 拒绝；
2. 上述拒绝发生在 development root 创建前；
3. metadata 使用原配置哈希但包含另一 spec，即使 sidecar 全部重算，验证仍拒绝；
4. validator 重新从 loaded config 派生 spec；
5. 取整为 0 sweep 样本的正时长被模型拒绝；
6. 取整为 1 sweep 样本的正时长被模型拒绝；
7. 取整为 2 sweep 样本的边界规格通过模型验证；
8. `-10000 dBFS` 在模型阶段被拒绝；
9. generator 的零 RMS/零 peak 防御返回 `EssError`，不是 `ZeroDivisionError`；
10. development fixture 的三个 golden hash 保持不变；
11. 至少一个独立固定 phase/sample/reference-vector 测试；
12. CLI 的 generate/validate 工作流仍成功；
13. 当前正式配置仍列出六个缺失 ESS 字段并拒绝生成；
14. 正式配置拒绝时不创建 development root；
15. 不调用 `_audio_backend()`；
16. 不枚举、播放、录音或打开 Stream。

如果使用 monkeypatch 模拟生成阶段内部异常：

- 只允许用于验证防御性错误路径；
- 不得 mock 掉正常数学生成主路径；
- 正常数学路径仍必须通过真实计算测试。

不得添加：

- skip；
- xfail；
- noqa；
- type ignore；
- 宽松 mypy；
- 静默 fallback。

---

# 11. 预期文件范围

建议只修改或新增：

- `src/acoustic_ladder/audio/excitation_models.py`
- `src/acoustic_ladder/audio/ess.py`
- `src/acoustic_ladder/audio/excitation_persistence.py`
- `src/acoustic_ladder/cli.py`
- `tests/dev03/test_ess_offline.py`
- 必要的生成 Schema
- `docs/architecture/ess-excitation.md`
- `README.md`
- `.gitattributes`
- `docs/prompts/DEV-03.03R.md`
- `docs/reports/DEV-03.03R.md`
- `docs/IMPLEMENTATION_LOG.md`

除非 strict 模型导出的 Schema 字节确实变化，否则不得无意义重写全部 Schema。

不得修改：

- `docs/reports/DEV-03.03.md`
- `docs/prompts/DEV-03.03.md`
- `tests/fixtures/audio/ess_offline_development.yaml` 的有效测试参数
- 正式 audio config 的 null 参数
- DEV-03.02 产物
- inventory/hardware/manifest/ZIP
- CAD 文件
- 实际数据目录

不要创建或提交 WAV、NPY、NPZ 或临时 artifact。

---

# 12. 回归验证

必须保持原 262 项全部通过：

- DEV-01：43
- DEV-02.01：66
- DEV-02.02：23
- DEV-03.01：36
- DEV-03.02：24
- DEV-03.03：70

然后运行 DEV-03.03R 新增测试和完整套件。

建议运行：

`uv --cache-dir .uv-cache sync --all-groups --frozen`

`uv --cache-dir .uv-cache run pytest -q tests/unit tests/integration`

`uv --cache-dir .uv-cache run pytest -q tests/dev02/test_config.py tests/dev02/test_domain_schema_cli.py tests/dev02/test_storage.py tests/dev02/test_synthetic.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev02/test_event_boundaries.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev03/test_inventory.py tests/dev03/test_preflight_persistence_cli.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev03/test_context_encoding.py`

`uv --cache-dir .uv-cache run pytest -q tests/dev03/test_ess_offline.py`

`uv --cache-dir .uv-cache run pytest -q`

静态检查：

`uv --cache-dir .uv-cache run ruff format --check .`

`uv --cache-dir .uv-cache run ruff check .`

`uv --cache-dir .uv-cache run mypy`

`uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check`

`git diff --check`

还必须运行：

- skip/xfail/noqa/type-ignore 扫描；
- 禁止音频 API AST 扫描；
- direct sounddevice import 扫描；
- U+FFFD 扫描；
- 本机绝对路径和身份信息扫描；
- 日志旧前缀验证；
- 保护文件 diff；
- 保护 SHA256 复核；
- 临时 WAV 未进入 Git 的检查。

---

# 13. 复现与修正证明

完成报告必须先证明原问题能够在基线提交复现，或引用本提示词给出的独立复现事实，然后证明修正后行为。

至少记录以下前后对照：

## 13.1 配置/spec 不一致

修正前：

`MISMATCH_ACCEPTED`

修正后必须为明确拒绝，例如：

`MISMATCH_REJECTED_BEFORE_WRITE`

同时证明：

- development root 不存在；
- staging 不存在；
- lock 不存在；
- artifact 不存在。

## 13.2 零样本 sweep

修正前：

`TINY_SPEC_ACCEPTED 0`

修正后：

`ZERO_SAMPLE_SPEC_REJECTED`

## 13.3 极低 dBFS

修正前：

`ZeroDivisionError`

修正后：

`UNREPRESENTABLE_FLOAT32_PEAK_REJECTED`

错误类型必须属于项目定义的 strict validation 或 `EssError`，不得再出现原始除零。

## 13.4 正常 fixture

必须继续得到：

- shape：`[1, 12960]`
- dtype：`float32`
- WAV：`608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- Metadata：`e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- Raw float32：`eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

使用 artifact ID：

`smoke`

临时演示完成后只清理本次明确创建的临时目录，不得扩大删除范围。

---

# 14. 文档

## 14.1 架构文档

更新：

`docs/architecture/ess-excitation.md`

补充：

- `LoadedConfig` 是持久化 ESS 的唯一配置事实来源；
- 公开发布/验证 API 不接受脱离配置的第二事实源；
- 纯数学 `generate_ess(spec)` 仍可接受显式 strict spec，因为它不自行声明配置哈希；
- 一旦 metadata 声明 source config hash，spec 必须由该配置派生；
- sweep 至少需要两个派生样本；
- dBFS 目标必须能表示为正 float32；
- generator 仍保留零峰值/RMS 防御；
- 正常 fixture 的字节保持不变。

区分：

- 纯数学 API；
- 带配置溯源的持久化 API。

## 14.2 README

只做必要更新：

- 说明 DEV-03.03R 修复配置/spec 审计一致性；
- 不新增后续功能；
- 不改变正式参数；
- 不给出播放命令；
- 不声称 experiment-ready。

## 14.3 修正报告

创建：

`docs/reports/DEV-03.03R.md`

至少包含：

- Outcome；
- 基线；
- 三个独立复现问题；
- 根因；
- API 修正；
- 数值边界修正；
- golden reference；
- 正常 fixture 哈希；
- 测试数量；
- 静态检查；
- 保护哈希；
- 未执行范围；
- Git 报告冻结状态；
- 已知限制。

不得修改旧 DEV-03.03 报告来隐藏原缺口。

---

# 15. 验收条件

只有同时满足以下条件才能判定 PASS：

1. 基线为 `7a5859a84a606f535e2c91f4a16d7a69acb332be`；
2. 起始工作区干净；
3. 本提示词已归档；
4. 实施日志只追加；
5. 持久化 API 的 spec 只能来自 loaded config；
6. -20 配置与 -18 spec 的复现被拒绝；
7. 不一致在任何目录或文件创建前失败；
8. metadata 不能组合原配置哈希和另一 spec；
9. 0 样本 sweep 被模型拒绝；
10. 1 样本 sweep 被模型拒绝；
11. 2 样本边界行为有测试；
12. 不可表示的 float32 peak 被模型拒绝；
13. 零 RMS/peak 不再触发 `ZeroDivisionError`；
14. 正常 fixture 波形不变；
15. 三个正常 fixture 哈希不变；
16. 独立 golden reference 测试通过；
17. 正式六个未知字段仍为 null；
18. 正式配置仍拒绝生成；
19. 没有真实硬件枚举；
20. 没有播放；
21. 没有录音；
22. 没有 Stream；
23. 没有设备绑定；
24. readiness/calibration 全部保持 false；
25. 原 262 项测试全部通过；
26. DEV-03.03R 新增测试全部通过；
27. 完整测试不少于 272 项，除非实际参数化计数不同且报告说明；
28. Ruff format 通过；
29. Ruff lint 通过；
30. strict mypy 通过；
31. 15 个 Schema 一致；
32. `git diff --check` 通过；
33. 没有 suppression；
34. 保护文件哈希不变；
35. 没有 WAV 或临时 artifact 提交；
36. 日志和报告完全符合实际。

任一条件失败：

- 不得写 PASSED；
- 不得提交成功状态；
- 不得推送；
- 必须报告真实失败证据。

---

# 16. Git 提交与推送

只有全部验收通过后才能提交。

提交前：

- 列出 staged 文件；
- 确认没有 WAV；
- 确认没有临时目录；
- 确认没有 `.venv` 或 `.uv-cache`；
- 确认没有本机绝对路径；
- 确认保护文件无变化；
- 再次确认远端 `main` 仍为：

`7a5859a84a606f535e2c91f4a16d7a69acb332be`

提交主题：

`DEV-03.03R: close ESS provenance and numeric boundaries`

提交后：

1. 确认工作区干净；
2. 确认提交内容仅属于 DEV-03.03R；
3. 运行最终必要门禁；
4. 推送：

`git push origin main`

5. 核对本地 HEAD、`origin/main`、GitHub `main` 完全一致。

禁止：

- force push；
- amend DEV-03.03；
- 创建无关分支；
- 创建 tag/release；
- 修改历史提交。

如果远端前进、认证失败、网络中断、测试失败或任务未完整完成：

- 不得 force push；
- 不得声称成功；
- 保留真实状态；
- 报告错误。

---

# 17. 最终回复

最终回复必须包含：

- `PASS — DEV-03.03R 完成` 或真实失败状态；
- 提交 SHA；
- 分支；
- 本地 HEAD；
- `origin/main`；
- GitHub `main`；
- 工作区状态；
- 原 262 项测试结果；
- 新增测试数量；
- 完整测试数量；
- Ruff、mypy、Schema 状态；
- mismatch 是否在写入前拒绝；
- 0/1 样本 sweep 是否拒绝；
- 极低 dBFS 是否拒绝；
- 是否仍存在 `ZeroDivisionError`；
- 三个 golden hash；
- 保护哈希；
- 是否枚举硬件；
- 是否播放；
- 是否录音；
- 是否打开 Stream；
- `hardware_ready`；
- 主要修改文件；
- 已知限制。

不得宣布进入 DEV-03.04。

完成本步后停止，不要自行进入下一步。