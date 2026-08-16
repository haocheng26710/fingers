# DEV-03.01：音频设备枚举、硬件档案与只读预检

你现在负责实施 Acoustic Ladder 的 DEV-03.01。

本步骤目标是建立音频硬件领域模型、PortAudio/sounddevice 只读枚举后端、实际设备清单和非侵入式能力预检。

本步骤绝对禁止播放、录音、打开音频流或生成正式 ESS。

完成后停止，不得自行进入 DEV-03.02。

# 1. Git 基线

仓库：

https://github.com/haocheng26710/fingers.git

分支：

main

必须基于提交：

3e075956727fcbfe2c0b57588cbef6ee34440136

开始前确认：

- 当前分支为 main；
- 本地 HEAD、origin/main、远程 main 与上述提交一致；
- 工作区干净；
- origin 地址正确；
- 没有未读取的 AGENTS.md、CLAUDE.md、CONTEXT.md、ADR 或其他项目级指令。

如基线不一致，立即停止，不得修改或推送。

# 2. 已确认硬件事实

以下是用户提供并确认的事实：

- 输出换能器：
  - 品牌：MOONDROP 水月雨
  - 型号：CHU II / 竹 2
  - 类型：10 mm 动圈入耳式耳机
  - 标准线材插头：3.5 mm 立体声单端
  - 不使用独立功率放大器
- 输入换能器：
  - 品牌：Dayton Audio
  - 型号：iMM-6C
  - 接口：USB-C
  - 内置 ADC/DAC：CM6542
  - 自带耳机/线路输出
  - 麦克风校准文件：用户确认存在，但当前尚未提供文件及路径
- 用户确认输入和输出属于同一个音频接口。
- 没有 94 dB/1 kHz 声学校准器。
- 不能进行输出到输入的电气回环。
- 当前尚未确认：
  - Windows 实际枚举设备名称；
  - PortAudio 设备索引；
  - host API；
  - WASAPI/ASIO 选择；
  - 输入通道号；
  - 输出通道号；
  - 是否能以 48 kHz 同步全双工打开；
  - 设备延迟；
  - Windows 独占/共享模式；
  - iMM-6C 校准文件的路径、格式、内容和 SHA256。

参考资料：

- https://www.daytonaudio.com/product/1974/imm-6c-idevice-usb-c-calibrated-microphone
- https://www.daytonaudio.com/images/resources/390-813--dayton-audio-imm-6c-quick-reference-guide.pdf
- https://moondroplab.com/cn/products/chu-ii
- https://python-sounddevice.readthedocs.io/
- https://pypi.org/project/sounddevice/

只可将这些资料作为硬件说明来源，不得把厂商标称性能当作本实验的实测结果。

# 3. 冻结判断

必须保持：

- 正式实验仍为 1 输出 + 1 输入；
- TX 为竹 2；
- RX 为 iMM-6C；
- 两个远端闭合；
- 未使用节点安装 BLK；
- 当前 manifest 仍为 provisional；
- 当前不是 geometry-locked；
- 当前不是 experiment-ready；
- `hardware_ready` 必须继续为 false；
- 本步骤不能证明同步全双工可用；
- 本步骤不能证明输入输出共用同一硬件时钟；
- 本步骤不能证明延迟稳定；
- 本步骤不能证明绝对 SPL；
- 麦克风校准文件尚未导入，因此 `calibration_applied = false`；
- 无声学校准器，因此 `absolute_spl_calibrated = false`；
- 无电气回环，因此 `electrical_loopback_available = false`。

即使设备枚举成功，也不得把 `hardware_ready` 改为 true。

# 4. 依赖与后端

使用 Python sounddevice 作为 PortAudio 枚举适配器。

依赖要求：

- 增加 `sounddevice>=0.5.5,<0.6`；
- 更新并锁定 uv.lock；
- 不引入 GUI、Web 框架、数据库或其他音频处理框架；
- 不引入播放/录音业务逻辑。

实现应分离：

1. 与硬件无关的领域模型和服务；
2. 可注入的 inventory backend 协议；
3. 生产用 SoundDeviceInventoryBackend；
4. 测试用确定性 FakeInventoryBackend。

禁止在模块 import 时自动查询硬件。

sounddevice 必须延迟初始化，并将 PortAudio 错误转换为项目自己的明确异常。

# 5. 只允许使用的 sounddevice 能力

本步骤只允许调用相当于以下只读或非流式能力：

- `query_hostapis()`
- `query_devices()`
- 查询 sounddevice/PortAudio 版本
- `check_input_settings()`
- `check_output_settings()`

禁止调用或构造：

- `play`
- `rec`
- `playrec`
- `wait`
- `Stream`
- `RawStream`
- `InputStream`
- `OutputStream`
- `RawInputStream`
- `RawOutputStream`

不得用静音流、零数组流或“只打开不播放”的方式绕过该限制。

`check_input_settings()` 和 `check_output_settings()` 只能证明单方向格式被 PortAudio 接受，不能被描述为全双工验证。

# 6. 新增模块

建议建立：

`src/acoustic_ladder/audio/`

至少包括：

- `models.py`
- `backend.py`
- `inventory.py`
- `preflight.py`
- `errors.py`
- `__init__.py`

可以调整文件划分，但职责必须清晰。

# 7. 音频设备领域模型

至少建立严格类型模型：

## 7.1 HostApiRecord

字段至少包括：

- host_api_index
- name
- default_input_device_index
- default_output_device_index
- device_count

## 7.2 AudioDeviceRecord

字段至少包括：

- snapshot_device_index
- name
- host_api_index
- host_api_name
- max_input_channels
- max_output_channels
- default_sample_rate_hz
- default_low_input_latency_s
- default_low_output_latency_s
- default_high_input_latency_s
- default_high_output_latency_s
- is_default_input
- is_default_output
- supports_input
- supports_output

设备索引必须明确标注为单次枚举快照索引，不得称为跨重启稳定 ID。

## 7.3 FormatCapabilityResult

至少表达：

- device index
- direction
- sample rate
- channel count
- dtype
- supported
- error type
- error message
- check method

本步骤只检查：

- 48000 Hz
- float32
- 1 个输入通道
- 1 个输出通道

输入、输出必须分别检查和分别记录。

## 7.4 AudioInventorySnapshot

至少记录：

- schema version
- captured_at，必须带时区
- operating system 名称、版本和架构
- Python 版本
- sounddevice 版本
- PortAudio 版本
- host APIs
- devices
- default input/output
- 48 kHz 单方向能力结果
- warnings
- provenance
- snapshot SHA256 或可验证 sidecar

禁止记录：

- 用户名；
- 主机名；
- 本机绝对路径；
-环境变量；
- 序列号之外的个人信息；
- 无关硬件信息。

## 7.5 HardwareSetupRecord

记录用户已确认的硬件事实：

- output_transducer
- input_transducer
- interface_model
- operator_reported_shared_interface
- amplifier_used
- microphone_connection
- microphone_calibration_file_available
- microphone_calibration_reference
- microphone_calibration_sha256
- microphone_calibration_applied
- acoustic_calibrator_available
- absolute_spl_calibrated
- electrical_loopback_available
- exact_physical_connection_pending_confirmation
- notes

当前必须满足：

- `interface_model = Dayton Audio iMM-6C`
- `operator_reported_shared_interface = true`
- `amplifier_used = false`
- `microphone_calibration_file_available = true`
- 校准文件 reference 和 SHA256 为 null
- `microphone_calibration_applied = false`
- `acoustic_calibrator_available = false`
- `absolute_spl_calibrated = false`
- `electrical_loopback_available = false`
- `exact_physical_connection_pending_confirmation = true`

不能自行填写校准文件内容或序列号。

## 7.6 AudioPreflightReport

至少区分：

- software_inventory_status
- input_candidate_status
- output_candidate_status
- operator_confirmation_status
- separate_input_format_check
- separate_output_format_check
- full_duplex_verified
- shared_clock_verified
- channel_mapping_verified
- calibration_file_verified
- absolute_spl_calibrated
- hardware_ready
- blockers
- warnings

必须固定：

- `full_duplex_verified = false`
- `shared_clock_verified = false`
- `channel_mapping_verified = false`
- `calibration_file_verified = false`
- `absolute_spl_calibrated = false`
- `hardware_ready = false`

# 8. 配置处理

更新或扩展现有音频配置契约，使其能引用：

- hardware setup record；
- inventory snapshot；
- input candidate；
- output candidate；
- host API candidate；
- operator confirmation状态。

但当前正式 audio config 中：

- audio_backend 仍不得假定为 WASAPI 或 ASIO；
- input/output device ID 不得仅凭名称自动锁定；
- channel_index 必须保持 null；
- hardware_ready 必须保持 false；
- config_status 保持 draft。

如果自动发现名称类似 `iMM-6C`、`USB Audio Device` 或 `CM6542` 的设备，只能列为 candidate，不能自动确认为正式设备。

如果输入和输出显示为两个不同 PortAudio 索引，也不能据此断定它们使用不同物理时钟；只记录事实，等待后续验证。

# 9. CLI

在现有 `acoustic-ladder` CLI 中增加稳定命令，至少支持：

1. 列出 host APIs 和设备；
2. 捕获机器可读 inventory JSON；
3. 生成 inventory SHA256 sidecar；
4. 对 48 kHz、float32、1 输入和1输出分别做非流式格式检查；
5. 根据 inventory 和 hardware setup 生成 preflight report；
6. 校验已有 inventory、sidecar 和 preflight report。

命令命名可以自行设计，但必须写入 README 并保持一致。

CLI 输出必须明确包含：

`NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED`

不得打印“全双工通过”“时钟同步”或“实验就绪”，除非后续步骤真实验证；本步骤无论如何都不能输出这些结论。

# 10. 实际硬件枚举

完成软件实现和测试后，在当前机器上实际运行一次只读枚举。

要求：

- 执行时不要播放或录音；
- 保存实际 inventory；
- 保存 sidecar；
- 生成实际 preflight report；
- 在报告中列出所有具备输入或输出能力的设备；
- 标出可能对应 iMM-6C/CM6542 的候选项；
- 记录实际 host API；
- 记录实际默认设备；
- 记录实际 48 kHz 单方向格式检查结果；
- 不自动选择通道；
- 不自动修改 `hardware_ready`。

建议保存到：

- `reference/audio/hardware_setup.provisional.json`
- `reference/audio/inventory/DEV-03.01_audio_inventory.json`
- `reference/audio/inventory/DEV-03.01_audio_inventory.sha256`
- `reference/audio/inventory/DEV-03.01_preflight_report.json`

如果实际设备名称不能明确识别 iMM-6C，仍应完整保存枚举结果并标记：

`needs_operator_confirmation`

只要枚举真实执行、结果完整且没有伪造，DEV-03.01 软件步骤可以通过；设备绑定状态仍不得通过。

如果当前环境完全无法初始化 PortAudio、无法获得任何 inventory，或命令意外打开了音频流，则本步骤 FAIL，不得推送。

# 11. Schema

为新增持久类型生成 JSON Schema，至少包括：

- audio_inventory_snapshot.schema.json
- hardware_setup_record.schema.json
- audio_preflight_report.schema.json

Schema 必须由实际类型模型导出，或由自动测试保证同步。

如修改 AudioConfig，也必须重新生成并验证现有 audio_config Schema。

# 12. 测试

必须使用 FakeInventoryBackend 完成确定性测试。

至少覆盖：

- backend 不在 import 时查询硬件；
- host API 正确规范化；
- input-only、output-only、duplex-capable 设备正确表达；
- 空设备列表；
- 非 ASCII 设备名称；
- 缺失或异常 latency；
- 无效负通道数拒绝；
- 无效采样率拒绝；
- 默认设备引用不存在时拒绝或生成明确错误；
- 48 kHz 输入检查与输出检查分离；
- 单方向检查通过不能令 full_duplex_verified 变为 true；
- 名称匹配不能自动令 operator confirmation 通过；
- PortAudio index 不被标记为稳定 ID；
- hardware setup 中未知字段保持 null；
- 无校准器时 absolute_spl_calibrated 不能为 true；
- 校准文件未提供时 calibration_applied 不能为 true；
- 不可电气回环的事实被保留；
- 正式模式仍严格 1+1；
- channel index 未确认时 hardware_ready 不能为 true；
- inventory 不包含用户名、主机名或绝对路径；
- canonical JSON 与 sidecar 验证；
- Schema 与模型一致；
- CLI 输出含 `NO_AUDIO_PLAYBACK_OR_RECORDING_PERFORMED`；
- 测试确认生产代码没有调用被禁止的播放、录音或 Stream API；
- 原有 132 项测试全部继续通过。

不得使用 skip、xfail、noqa 或 type ignore 掩盖问题。

真实硬件枚举不应写成依赖特定设备名称的 pytest；它应作为单独的、实际执行并记录结果的验收命令。

# 13. 不得实施

本步骤禁止：

- 播放声音；
- 录制声音；
- 打开任何输入、输出或全双工音频流；
- 生成正式 ESS；
- 生成测试音、白噪声或粉红噪声；
- 自动调节系统音量；
- 改变 Windows 默认设备；
- 启用 WASAPI 独占模式；
- 使用 ASIO；
- 执行延迟测量；
- 执行时钟漂移测量；
- 执行声压级校准；
- 读取或应用尚未提供的麦克风校准文件；
- 反卷积；
- 生成脉冲响应；
- 声学传递函数；
- 阶段 1–4 协议执行；
- 修改 CAD、ZIP 或 device manifest；
- geometry lock 或 experiment-ready；
- DEV-03.02 及之后功能。

# 14. 历史产物保护

以下内容必须保持字节不变：

- V1.3 ZIP；
- provisional device manifest 和 sidecar；
- device manifest Schema；
- DEV-01.01、DEV-02.01、DEV-02.02 的 prompt；
- DEV-01.01、DEV-02.01、DEV-02.02 的 report；
- calibration record；
- model audit/review。

关键哈希必须仍为：

ZIP：

1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b

manifest：

bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0

`docs/IMPLEMENTATION_LOG.md` 只能在末尾追加 DEV-03.01，不得改写历史条目。

# 15. 日志与文档

原样保存本提示词：

`docs/prompts/DEV-03.01.md`

创建：

`docs/reports/DEV-03.01.md`

更新相关文档：

- README
- `docs/architecture/` 下的音频设备与预检说明
- 配置说明
- Schema 说明

向 `docs/IMPLEMENTATION_LOG.md` 末尾追加 DEV-03.01。

日志必须真实记录：

- 序列号；
- 基线提交；
- 用户确认的硬件事实；
- 官方来源；
- 依赖及实际锁定版本；
- 实现结构；
- 字段决定；
- 实际硬件枚举命令；
- 枚举到的真实 host APIs 和设备；
- 单方向格式检查结果；
- 哪些候选需要用户确认；
- 真实 inventory/sidecar 哈希；
- 实际测试命令和数量；
- 初次失败及修正；
- 未执行项目及原因；
- 受保护文件回归；
- Git 结果；
- 已知限制。

不能编造设备名称、索引、通道、host API、延迟或校准结果。

# 16. 验收

至少实际运行：

- DEV-01 原测试；
- DEV-02.01 原测试；
- DEV-02.02 回归；
- DEV-03.01 新测试；
- 完整 pytest；
- Ruff format check；
- Ruff lint；
- strict mypy；
- 全部 Schema 一致性检查；
- `git diff --check`；
- skip/xfail/noqa/type-ignore 扫描；
- 禁止音频调用扫描；
- 历史保护文件 diff；
- ZIP/manifest SHA256；
- 实际只读 inventory CLI；
- inventory sidecar 校验；
- 实际 preflight CLI；
- 最终工作区检查。

必须在报告中分别说明：

- 软件步骤 PASS/FAIL；
- inventory capture PASS/FAIL；
- device binding 状态；
- hardware_ready 状态。

本步骤预期：

- 软件步骤可为 PASS；
- inventory capture 应为 PASS；
- device binding 为 `needs_operator_confirmation`；
- hardware_ready 为 false。

# 17. Git 推送门禁

只有在以下条件全部满足时才允许提交并推送：

- 软件测试全部通过；
- 实际只读 inventory 成功生成；
- inventory 和 sidecar 验证通过；
- 没有播放、录音或打开音频流；
- 没有伪造设备结果；
- 所有受保护文件保持不变；
- 日志和报告完整；
- 工作区不存在缓存、临时数据、虚拟环境或秘密。

建议提交信息：

DEV-03.01: add audio inventory and read-only preflight

推送到：

- remote：`https://github.com/haocheng26710/fingers.git`
- branch：`main`

禁止 force push。

若测试失败、枚举失败、出现意外播放/录音、结果不完整、执行中断或推送失败：

- 不得推送；
- 不得声称 PASSED；
- 如实记录状态和阻塞点；
- 保留 hardware_ready=false；
- 停止等待用户处理。

# 18. 最终回复

最终回复必须报告：

- DEV-03.01 最终状态；
- 提交 SHA；
- 本地、origin/main、远程 main 是否一致；
- 工作区是否干净；
- 总测试数及新增测试数；
- 实际 sounddevice 和 PortAudio 版本；
- 实际枚举到的 host APIs；
- iMM-6C 输入候选；
- iMM-6C 输出候选；
- 输入/输出是否显示为同一索引；
- 48 kHz 单方向检查结果；
- device binding 状态；
- hardware_ready；
- inventory SHA256；
- ZIP/manifest SHA256；
- 是否发生任何播放、录音或流打开；
- 仍需用户确认的设备索引、host API 和通道。

完成后停止，不得进入 DEV-03.02。