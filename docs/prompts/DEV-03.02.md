# DEV-03.02：音频清单编码与无实验硬件基线上下文修正

你现在负责实施 Acoustic Ladder 的 DEV-03.02。

本步骤用于修正 DEV-03.01 的设备名称编码记录错误，并补充一项后来由用户明确确认的重要事实：

DEV-03.01 实际枚举时，iMM-6C、竹 2 和实验装置均未连接电脑。

本步骤只修正审计语义、报告生成和控制台编码，不进行新的硬件枚举，不播放、不录音、不打开音频流。

完成后停止，不得自行进入 DEV-03.03。

# 1. Git 基线

仓库：

https://github.com/haocheng26710/fingers.git

分支：

main

必须基于提交：

6332adc85be898f7c8d57e17b5d41fcce52587a1

开始前必须确认：

- 当前分支为 main；
- 本地 HEAD、origin/main、远程 main 与上述提交一致；
- 工作区干净；
- origin 地址正确；
- 没有未读取的项目级指令文件。

如基线不一致，立即停止，不得修改或推送。

# 2. 已确认问题一：报告设备名称编码错误

DEV-03.01 的权威 inventory：

`reference/audio/inventory/DEV-03.01_audio_inventory.json`

SHA256：

`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

该 JSON 中保存了正确的 UTF-8 中文设备名称，例如：

- `Microsoft 声音映射器 - Input`
- `阵列麦克风 (AMD Audio Device)`
- `耳机 (Senary Audio)`
- `扬声器 (Senary Audio)`
- `麦克风 (Senary Audio capture)`

但是：

- `audio-list` 经当前终端输出后显示为 `����` 等乱码；
- `docs/reports/DEV-03.01.md` 手工复制了这些乱码；
- DEV-03.01 报告和实施日志误称这些 replacement characters 是 sounddevice 的原始返回结果。

经独立复核，inventory JSON 已证明 sounddevice 规范化结果中保存的是正确中文。

因此必须更正为：

- inventory JSON 是本次设备名称的权威记录；
- 名称损坏发生在 inventory 构建之后的控制台输出、解码或报告转录路径；
- 当前证据不足以把错误精确归因到某一个终端、代码页或工具层；
- 不得继续声称 sounddevice 原始返回了 replacement characters；
- 不得猜测未被 inventory 保存的设备名称。

# 3. 已确认问题二：枚举时实验硬件未连接

用户在 DEV-03.01 完成后明确确认：

- iMM-6C 当时没有连接电脑；
- 竹 2 当时没有连接；
- 实验装置当时没有接入；
- 用户计划在大体程序完成后再接入实际设备并开展实验。

因此 DEV-03.01 inventory 必须解释为：

`development_host_baseline_without_experimental_hardware`

它只能表示开发电脑在未连接实验硬件时的音频端点基线。

必须明确：

- 当前所有设备索引均不得绑定为 iMM-6C；
- `Senary Audio` 不得推断为 iMM-6C；
- AMD、蓝牙及其他端点不得作为实验输入或输出；
- 当前不存在应由用户确认的实验设备索引；
- 当前不需要选择 Host API；
- 当前不需要选择输入或输出通道；
- device binding 应为 deferred，而不是硬件识别失败；
- `hardware_ready=false`；
- `full_duplex_verified=false`；
- `shared_clock_verified=false`；
- `channel_mapping_verified=false`；
- `calibration_file_verified=false`；
- `absolute_spl_calibrated=false`。

无实验硬件连接是预期状态，不是枚举失败。

# 4. 历史数据保护

以下 DEV-03.01 实际采集产物必须保持字节不变：

- `reference/audio/inventory/DEV-03.01_audio_inventory.json`
- `reference/audio/inventory/DEV-03.01_audio_inventory.sha256`
- `reference/audio/inventory/DEV-03.01_preflight_report.json`
- `reference/audio/hardware_setup.provisional.json`
- `docs/prompts/DEV-03.01.md`

其中 inventory SHA256 必须仍为：

`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

不要重写或“清洗”原 inventory。

Git 历史已经保留 DEV-03.01 原始报告，因此允许在本修正步骤更新：

`docs/reports/DEV-03.01.md`

但只能修正已确认的名称、错误归因和“硬件未连接”上下文，不得重写其他真实测试结果。

`docs/IMPLEMENTATION_LOG.md` 中既有 DEV-03.01 条目不得修改。必须通过末尾追加 DEV-03.02 更正条目来纠正旧说法。

# 5. 新增枚举上下文记录

建立严格类型模型，例如：

`AudioInventoryCaptureContext`

至少包括：

- schema_version
- context_id
- inventory_reference
- inventory_sha256
- context_recorded_at
- context_source
- experimental_input_hardware_connected
- experimental_output_hardware_connected
- experimental_fixture_connected
- inventory_role
- candidate_binding_status
- existing_endpoint_interpretation
- hardware_ready
- full_duplex_verified
- shared_clock_verified
- channel_mapping_verified
- calibration_file_verified
- absolute_spl_calibrated
- notes

当前必须记录：

- `experimental_input_hardware_connected = false`
- `experimental_output_hardware_connected = false`
- `experimental_fixture_connected = false`
- `inventory_role = development_host_baseline_without_experimental_hardware`
- `candidate_binding_status = deferred_until_hardware_connection`
- `existing_endpoint_interpretation = not_experimental_hardware`
- `hardware_ready = false`
- 其余 readiness/calibration 字段全部为 false
- context_source 明确为用户在 DEV-03.01 后提供的操作者事实更正

建议创建：

- `reference/audio/inventory/DEV-03.02_inventory_capture_context.json`
- `reference/audio/inventory/DEV-03.02_inventory_capture_context.sha256`

必须使用 canonical JSON、create-only 写入和 SHA256 sidecar。

不得在其中存储用户名、主机名、本机绝对路径或无关个人信息。

# 6. 修正 preflight 语义

扩展相关模型或增加上下文解释层，使 preflight 能区分：

- `candidate_found`
- `no_candidate_found`
- `not_applicable_hardware_disconnected`

当 capture context 表明实验硬件未连接时：

- 不执行设备名称候选匹配；
- input candidate 列表必须为空；
- output candidate 列表必须为空；
- 不得把所有输出端点列为实验候选；
- input/output candidate status 均为：
  `not_applicable_hardware_disconnected`
- operator confirmation status 为：
  `deferred_until_hardware_connection`
- device binding status 为：
  `deferred_until_hardware_connection`
- blocker 应说明需要未来连接实验硬件并重新枚举；
- 不得把“未找到 iMM-6C”描述为当前故障。

不要修改原 DEV-03.01 preflight 文件。

创建新的解释结果，例如：

`reference/audio/inventory/DEV-03.02_contextual_preflight_report.json`

该文件必须引用：

- 原 inventory 路径和 SHA256；
- DEV-03.02 capture context 路径和 SHA256；
- provisional hardware setup 路径和 SHA256。

# 7. 设备名称的权威来源与报告生成

新增确定性 Markdown 渲染功能。

输入必须是：

- 已验证 sidecar 的 inventory JSON；
- 可选的 capture context。

输出必须直接从解析后的模型生成，不能复制终端文字。

建议新增 CLI：

`acoustic-ladder audio-inventory-summary`

至少接受：

- `--inventory`
- `--inventory-sidecar`
- `--context`
- `--context-sidecar`
- `--output`

生成：

`reference/audio/inventory/DEV-03.02_audio_inventory_summary.md`

要求：

- UTF-8；
- LF 换行；
- 包含 inventory 路径和 SHA256；
- 包含 capture context；
- 明确说明实验硬件未连接；
- 每个设备名称来自 inventory 模型；
- 不含 U+FFFD replacement character；
- Markdown 表格中的竖线、换行和反斜杠必须安全转义；
- 不得通过 shell 输出重新解析名称；
- 不得手工维护设备表。

为生成的 summary 创建 SHA256 sidecar。

# 8. 修正 audio-list 控制台输出

当前环境中，直接输出中文名称可能在终端或工具层被错误解码。

必须提供稳定、无歧义的控制台模式。

推荐：

- `audio-list` 默认将设备名称输出为 ASCII-only JSON string；
- 使用 `json.dumps(name, ensure_ascii=True)` 或等价可逆方式；
- 明确输出标记：
  `DEVICE_NAME_ENCODING=JSON_ASCII_ESCAPED`
- JSON 转义必须可通过标准 JSON 解码恢复为 inventory 中的原名称；
- 不得使用 `errors="replace"`；
- 不得把不可编码字符替换成 `?` 或 U+FFFD。

可以另提供显式 UTF-8 或机器 JSON 模式，但默认模式必须在未知 Windows 控制台编码下保持字节安全。

所有模式仍必须输出：

`NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED`

本步骤不得重新运行真实硬件 inventory，也不得打开音频流。

# 9. 修正 DEV-03.01 报告

更新：

`docs/reports/DEV-03.01.md`

只修正以下内容：

1. 将乱码设备表替换为从原 inventory 生成的正确名称；
2. 删除“sounddevice 返回 replacement characters”的错误说法；
3. 明确名称损坏发生于后续控制台/转录路径，精确层级未证明；
4. 添加显著更正说明：
   - 用户后来确认枚举时实验硬件完全未连接；
   - 原 inventory 是无实验硬件开发主机基线；
   - 所有原索引均不得用于 iMM-6C 绑定；
   - 原测试、哈希和只读枚举事实保持有效；
5. 引用 DEV-03.02 context 和 summary。

不得改变 DEV-03.01 的真实测试数量、依赖版本、PortAudio 版本、inventory 哈希或禁止范围事实。

如果表格由命令生成，应将生成结果嵌入或链接到 summary，避免未来再次手工复制。

# 10. 实施日志

原样保存本提示词：

`docs/prompts/DEV-03.02.md`

创建：

`docs/reports/DEV-03.02.md`

向 `docs/IMPLEMENTATION_LOG.md` 末尾追加 DEV-03.02。

不得修改既有 DEV-03.01 日志。

DEV-03.02 日志必须明确写出：

- 旧日志中“sounddevice 返回 replacement characters”的说法不准确；
- 权威 inventory 保存的是正确中文；
- 乱码在后续控制台/转录路径出现；
- 精确编码故障层级没有被证明；
- 用户后来确认采集时实验硬件完全未连接；
- DEV-03.01 inventory 被重新分类为无实验硬件基线；
- 当前所有索引不得绑定为实验设备；
- 原 inventory 和 sidecar 未修改；
- 实际新增/修改文件；
- 实际运行命令；
- 初次失败及修正；
- 测试数量；
- 未执行检查及原因；
- Git 结果；
- 已知限制。

日志只能记录真实发生的内容。

# 11. 测试

至少新增以下测试：

1. DEV-03.01 inventory 中不存在 U+FFFD；
2. inventory 中已知中文名称按 UTF-8 正确保留；
3. summary 由 inventory 模型生成；
4. summary 不包含 U+FFFD；
5. summary 中每个设备索引和名称与 inventory 一致；
6. Markdown 特殊字符和设备名换行被安全处理；
7. ASCII 控制台模式只输出 ASCII；
8. ASCII 名称可通过 JSON 解码恢复为原名称；
9. 不使用 `errors="replace"`；
10. 无实验硬件 context 的三个 connected 字段均为 false；
11. context 下不执行 candidate name matching；
12. contextual preflight 的输入/输出候选均为空；
13. candidate status 为 `not_applicable_hardware_disconnected`；
14. binding/confirmation 状态为 deferred；
15. 任一 readiness 字段不能变为 true；
16. context、summary sidecar 验证；
17. 原 inventory 和 sidecar 字节保持不变；
18. DEV-03.01 报告不含 U+FFFD；
19. DEV-03.01 报告不再声称 sounddevice 原始返回 replacement characters；
20. 生产代码仍没有播放、录音或 Stream API；
21. 原有 168 项测试全部继续通过。

不得添加 skip、xfail、noqa 或 type ignore。

# 12. 禁止范围

本步骤禁止：

- 连接、断开或要求操作者连接实际硬件；
- 重新采集真实 inventory；
- 自动识别 Senary Audio；
- 选择设备索引；
- 选择 Host API；
- 选择通道；
- 播放；
- 录音；
- 打开任何音频流；
- ESS 生成；
- 测试音或噪声生成；
- 延迟或时钟测量；
- 麦克风校准文件读取或应用；
- SPL 校准；
- synthetic 数据写入 real 根；
- geometry lock；
- experiment-ready；
- DEV-03.03 及之后功能。

# 13. 历史产物保护

除本提示词明确允许修正的 `docs/reports/DEV-03.01.md` 外，必须保护：

- V1.3 ZIP；
- provisional manifest 和 sidecar；
- device manifest Schema；
- calibration record；
- model audit/review；
- DEV-01.01、DEV-02.01、DEV-02.02 的 prompts/reports；
- DEV-03.01 prompt；
- DEV-03.01 inventory、sidecar、preflight 和 hardware setup；
- implementation log 的所有既有内容。

ZIP SHA256 必须仍为：

`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`

manifest SHA256 必须仍为：

`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

inventory SHA256 必须仍为：

`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`

# 14. 验收

至少实际运行：

- DEV-01 原测试；
- DEV-02.01 原测试；
- DEV-02.02 回归；
- DEV-03.01 原测试；
- DEV-03.02 新测试；
- 完整 pytest；
- Ruff format check；
- Ruff lint；
- strict mypy；
- 全部 Schema 一致性检查；
- `git diff --check`；
- skip/xfail/noqa/type-ignore 扫描；
- 禁止音频调用 AST 扫描；
- U+FFFD 扫描；
- 旧错误说法扫描；
- inventory/context/summary sidecar 校验；
- 历史保护文件 diff；
- ZIP、manifest、inventory SHA256；
- ASCII audio-list 的可逆性测试；
- 最终工作区检查。

不得在验收期间调用生产 sounddevice 后端进行新枚举。

应使用已有 DEV-03.01 inventory 和 FakeInventoryBackend。

# 15. PASS 条件

只有同时满足以下条件才可标记 PASS：

- 原 inventory 字节和哈希不变；
- DEV-03.01 报告设备名称已修正；
- 报告不再包含 U+FFFD；
- 日志通过新条目明确纠正旧说法；
- 无实验硬件上下文已持久化并有 sidecar；
- contextual preflight 不列出实验候选；
- 控制台设备名称采用可逆 ASCII 表达；
- 所有测试和静态检查通过；
- 未发生音频枚举、播放、录音或流打开；
- 所有 readiness 状态仍为 false；
- 工作区只包含本步骤预期改动。

# 16. Git 推送门禁

只有全部验收 PASS 后才允许提交并推送。

建议提交信息：

DEV-03.02: correct audio inventory context and encoding

推送到：

- remote：`https://github.com/haocheng26710/fingers.git`
- branch：`main`

禁止 force push。

推送后确认：

- 本地 HEAD、origin/main、GitHub main 完全一致；
- 工作区干净；
- 提交只包含 DEV-03.02；
- 没有缓存、虚拟环境、临时文件或秘密。

如果测试失败、历史 inventory 被修改、出现新硬件枚举、结果不完整、中途停止或推送失败：

- 不得推送；
- 不得声称 PASSED；
- 如实记录阻塞点；
- 停止等待用户处理。

# 17. 最终回复

最终回复必须报告：

- DEV-03.02 PASS/FAIL；
- 提交 SHA；
- 本地、origin/main、GitHub main 是否一致；
- 工作区是否干净；
- 原有测试数、新增测试数和完整测试数；
- 原 inventory SHA256；
- inventory 是否保持字节不变；
- context SHA256；
- summary SHA256；
- DEV-03.01 报告是否已移除 U+FFFD；
- ASCII 控制台名称是否可逆；
- inventory 当前角色；
- experimental hardware connected 状态；
- device binding 状态；
- hardware_ready；
- 是否发生任何新枚举、播放、录音或流打开；
- ZIP/manifest SHA256；
- 仍然保留的限制。

完成后停止，不得进入 DEV-03.03。