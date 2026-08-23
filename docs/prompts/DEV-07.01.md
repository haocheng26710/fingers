# DEV-07.01：受控的真实全双工采集核心（精简版）

你现在负责 Acoustic Ladder V1.3 项目的 `DEV-07.01`。

本步骤只实现“真实音频采集所需的最小核心和安全边界”，不制作 UI、不连接设备、不播放声音、不录音，也不进入正式实验。

## 一、执行基线

仓库：

- Remote：`https://github.com/haocheng26710/fingers.git`
- Branch：`main`
- 预期父提交：`0597953517638db0cff5f208542a41fa817746d3`

开始前必须：

1. 阅读仓库中的 `AGENTS.md`、README、现有架构文档、`docs/IMPLEMENTATION_LOG.md` 和最近的 DEV-06 报告。
2. 检查：
   - 当前分支为 `main`；
   - 工作区干净；
   - local HEAD、`origin/main`、GitHub `main` 一致；
   - 当前提交等于预期父提交。
3. 如果工作区不干净、分支或提交不一致、存在未解决冲突或远程发生意外变化：
   - 立即停止；
   - 不修改、不提交、不推送；
   - 报告实际状态和阻塞原因。
4. 不得覆盖、删除、回滚或格式化与本步骤无关的用户文件。
5. 将本提示词按 UTF-8 无 BOM 原样保存为：
   - `docs/prompts/DEV-07.01.md`
6. 在真正修改程序前，向 `docs/IMPLEMENTATION_LOG.md` 末尾追加一条真实的 `[DEV-07.01][STARTED]` 记录，至少包含：
   - 父提交；
   - 本步骤范围；
   - 明确声明尚未访问任何真实音频硬件。
7. `IMPLEMENTATION_LOG.md` 只能追加，不得改写已有历史内容。

## 二、研究背景与当前边界

当前项目已经具备：

- 确定性 ESS 生成；
- synthetic/virtual capture；
- ESS 处理；
- provisional QC；
- Stage 1–4 离线研究分析；
- 数据持久化和 create-only 保护机制。

当前尚不具备：

- 真实音频播放；
- 真实麦克风录音；
- 真实全双工 Stream；
- 已确认的设备索引、Host API 和通道；
- 已冻结的播放电平、ESS 时长和正式 QC 阈值；
- 已授权的正式实验。

已知硬件但本步骤不得访问：

- 输出：MOONDROP CHU II；
- 输入：Dayton Audio iMM-6C USB-C；
- 麦克风校准文件存在，但本步骤不解析、不应用；
- 没有 94 dB/1 kHz 声学校准器；
- 不能进行电气回环；
- 当前真实设备和实验装置尚未连接。

不得编造任何设备索引、Host API、通道号、播放电平、校准结果或实验结论。

## 三、本步骤唯一目标

实现一个小型、可测试、默认关闭的全双工采集核心，为后续 GUI 和真实设备试运行提供底层接口。

核心必须满足：

- 默认不能访问真实硬件；
- 真实播放和录音必须经过显式安全门；
- 开发和测试仅使用 fake backend；
- 输出参考波形与实际送入 backend 的样本逐样本一致；
- 输入采集结果使用统一的 channel-first `float32` 内存格式；
- 出错、取消或中断时不发布不完整的正式采集包；
- 不增加与研究主线无关的复杂基础设施。

## 四、实现范围

### 4.1 先适配现有架构

先检查现有音频、ESS、持久化、配置和模型代码，再决定具体文件位置和命名。

优先复用现有：

- ESS 波形生成与验证；
- WAV 写入工具；
- create-only / staging / atomic publish 机制；
- 哈希工具；
- QC 基础计算；
- 类型和异常体系。

不得复制已有算法形成第二套实现。

不得为本步骤重构整个音频、持久化或配置架构。

### 4.2 最小 backend 抽象

实现最小的全双工 backend 协议或抽象类，至少能够表达：

- 输入和输出设备绑定；
- 采样率；
- 输入和输出通道；
- block size；
- 输出样本；
- 输入采集缓冲区；
- 开始；
- 正常完成；
- 取消/紧急停止；
- backend 状态标记；
- underrun、overrun 或 PortAudio callback 状态。

至少实现两个 backend：

1. `FakeFullDuplexBackend`
   - 供测试使用；
   - 完全确定性；
   - 可配置固定延迟、固定增益和小型确定性噪声；
   - 可模拟取消、输入不足、underrun、overrun 和 backend 异常；
   - 不得调用 `sounddevice`。

2. `SoundDeviceFullDuplexBackend`
   - 使用现有 `sounddevice` 依赖；
   - 采用延迟导入或依赖注入，导入模块时不得枚举或打开设备；
   - 只提供后续真实采集需要的 adapter；
   - 本步骤不得通过 CLI、测试或自动流程实际调用真实设备；
   - 单元测试只能注入 fake sounddevice module；
   - callback 中只执行必要的缓冲区复制和状态记录，不执行文件写入、日志格式化或信号分析。

不要引入新的大型依赖。

### 4.3 最小采集状态

使用简单、明确的状态，至少区分：

- `DISARMED`
- `ARMED`
- `RUNNING`
- `COMPLETED`
- `CANCELLED`
- `FAILED`

禁止将：

- `CANCELLED`
- `FAILED`
- 部分采集
- 样本数量错误

标记成成功采集。

不要实现复杂工作流引擎、事件总线或数据库。

### 4.4 数据格式

采集核心内部统一使用：

- `float32`
- channel-first
- mono 输入和 mono 输出
- 48 kHz

输出参考必须是实际提交给 backend 的完整样本序列，包括调用方提供的前静音、ESS、后静音和 fade 结果。

写入 WAV 时可转换成标准的 sample-first 文件布局，但读取后必须能够逐样本恢复。

禁止在本步骤中自行冻结或猜测：

- ESS 时长；
- 前后静音时长；
- fade 时长；
- 播放 dBFS；
- 正式实验阈值。

这些值只能由以后经过确认的 pilot 配置提供。

### 4.5 真实硬件安全门

真实 backend 必须默认拒绝执行。

进入真实 backend 前，至少验证：

- `hardware_ready == true`
- `operator_confirmed == true`
- `playback_authorized == true`
- 运行模式明确为 `pilot`
- 正式实验模式未启用
- 输入设备 ID 已提供
- 输出设备 ID 已提供
- Host API 已提供
- 输入和输出通道已提供
- 采样率明确为 48000 Hz
- 输出为 mono
- 输入为 mono
- 播放电平已经由未来步骤显式冻结
- 当前设备绑定与授权时的设备绑定完全一致

任意一项缺失或不一致都必须在 Stream 打开前拒绝。

授权对象应是简单、运行时使用的数据对象，不要实现账号、密码、数字签名、网络授权或密钥系统。

开发/synthetic 配置不得用于真实 backend。

正式实验模式在本步骤必须继续拒绝。

不得自动提高音量、自动重试播放或自动切换设备。

### 4.6 取消与紧急停止

采集核心必须提供线程安全的取消/停止入口。

收到取消后：

- 尽快向输出写入零值；
- 停止 Stream；
- 标记为 `CANCELLED`；
- 不把部分采集发布为成功 run；
- 不自动重试。

backend 异常必须转换成项目领域内的明确错误，不得把底层异常静默吞掉。

### 4.7 最小采集包

只实现一个调用方指定目录下的最小 create-only 采集包：

- `captured_input.wav`
- `output_reference.wav`
- `run.json`
- `qc.json`

要求：

- 先写入同一父目录下的 staging 目录；
- 四个文件全部成功后再原子发布最终目录；
- 已存在的最终目录不得覆盖；
- 失败或取消时不得留下看似完成的最终目录；
- 可安全清理本步骤创建的 staging 目录；
- 不得清理无法确认归属的目录。

`run.json` 只保存必要信息：

- run ID；
- `pilot` 模式；
- 采样率；
- 通道数；
- 样本数；
- backend 类型；
- 设备绑定；
- 最终状态；
- backend 状态标记；
- 两个 WAV 的 SHA256；
- 授权检查结果的布尔摘要；
- 必要的 UTC 时间。

不得保存虚假的硬件信息。

`qc.json` 只保存无需正式阈值即可计算的结构性信息，例如：

- 输入/输出是否为有限数；
- 输入/输出样本数；
- peak；
- RMS；
- clipping sample count；
- underrun/overrun 状态；
- 是否完整采集。

由于正式阈值尚未冻结：

- `evaluation_status` 必须明确为 `pilot_structural_metrics_only`；
- `qc_decision` 必须为 `not_evaluated`；
- `thresholds_applied` 必须为 `false`。

不得输出正式 PASS/FAIL 声学结论。

不要为这四个文件分别增加 sidecar，也不要新增 JSON Schema。若现有架构强制要求新增 Schema，先停止并报告，不得自行扩大范围。

## 五、测试要求（精简版）

只运行本步骤新增测试和直接相关的少量测试，不运行完整测试套件。

新增测试至少覆盖：

1. fake backend 正常完成；
2. 输出参考与送入 backend 的样本逐样本一致；
3. 固定延迟/增益恢复结果确定；
4. 内存数组为 channel-first `float32`；
5. 缺失授权时真实 backend 在打开 Stream 前被拒绝；
6. 设备绑定变化时拒绝；
7. 正式模式被拒绝；
8. 取消后状态为 `CANCELLED`，且不发布最终包；
9. backend 异常后状态为 `FAILED`，且不发布最终包；
10. underrun/overrun 被记录；
11. create-only 拒绝覆盖已有 run；
12. staging 写入失败时不会生成完整目录；
13. fake sounddevice module 可以验证 adapter 行为；
14. 测试期间没有真实设备查询、Stream 打开、播放或录音。

只执行以下验收：

- DEV-07.01 新增测试；
- 与修改代码直接相关的现有音频/ESS/持久化测试；
- Ruff format：仅检查/格式化受影响文件；
- Ruff lint：受影响文件；
- strict mypy：受影响包；
- `git diff --check`；
- 检查修改代码中没有新增 `skip`、`xfail`、`noqa`、`type: ignore` 或测试抑制。

本步骤明确禁止：

- 完整 pytest suite；
- 344 行完整 smoke；
- 重新生成 1.13 GB NPZ；
- 重跑 Stage 1–4 分析；
- 重跑全部历史 golden；
- Schema consistency（因为本步骤不得修改 Schema）；
- 为了“更完备”而增加额外重复验证。

同一项验收正常通过后不要反复重跑。只有修复了会影响该项的代码后，才允许重跑对应检查。

## 六、明确不在本步骤实施

不得实施：

- Tkinter 或其他 GUI；
- 真实设备枚举；
- 真实 Stream 打开；
- 实际播放；
- 实际录音；
- iMM-6C 校准文件解析或应用；
- 自动音量设置；
- 绝对 SPL；
- 正式 QC 阈值；
- Stage 1–4 新分析；
- 多设备或多麦克风支持；
- ASIO 专用支持；
- 云服务、账号、数据库；
- 实时频谱动画；
- 自动恢复正式实验；
- 正式实验 session/run 编排；
- 修改 V1.3 ZIP、manifest 或历史受保护哈希。

如果实现这些内容才可继续，必须停止并报告，不能自行扩大任务。

## 七、文档与日志

成功完成代码和定向验收后：

1. 新建 `docs/reports/DEV-07.01.md`，记录：
   - 实际修改内容；
   - 实际运行的命令；
   - 测试数量与结果；
   - 未运行完整套件的事实和原因；
   - 未访问真实硬件的事实；
   - 当前安全门；
   - 已知限制；
   - 下一步为 DEV-07.02 最小 Tkinter UI。
2. 向 `docs/IMPLEMENTATION_LOG.md` 末尾追加 `[DEV-07.01][COMPLETED]`：
   - 只能记录实际发生的内容；
   - 包含测试结果、文件、关键设计、安全边界和未完成事项；
   - 保留足够细节，使其他人员或 AI 能复现；
   - 不得声称真实设备、播放、录音、校准或正式实验已完成。
3. README 只增加一小段当前能力和限制，不写长篇重复说明。
4. 不得修改既有日志内容或历史报告来美化结果。

## 八、提交与推送规则

只有同时满足以下条件才允许提交和推送：

- 本步骤范围全部实现；
- 所有规定的定向测试通过；
- Ruff、mypy、`git diff --check` 通过；
- 没有测试抑制；
- 没有访问真实音频硬件；
- 没有修改受保护产物；
- 报告和日志已真实更新；
- 工作区除本步骤文件外没有意外修改；
- 推送前远程 `main` 仍以预期父提交为基线。

提交信息：

`feat: add guarded pilot full-duplex capture core`

只允许普通非 force push 到：

- Remote：`origin`
- Branch：`main`

禁止：

- force push；
- amend；
- rebase；
- 改写历史；
- 绕过检查；
- 删除他人修改。

推送后验证：

- local HEAD；
- `origin/main`；
- GitHub `main`

三者必须等于本次新提交 SHA，且工作区干净。

如果任一实现、测试、文档、Git 或推送步骤失败或中断：

- 不提交；
- 不推送；
- 不伪造 PASS；
- 保留可诊断信息；
- 报告具体失败命令、错误、当前工作区状态和下一步建议。

## 九、最终回复格式

最终只给出精简、可核查的结果：

- `PASS` 或 `FAIL`
- 提交 SHA（未提交则写 `未提交`）
- 推送状态
- 实际运行的定向测试及结果
- 主要修改文件
- 明确写出：
  - 是否枚举真实设备
  - 是否打开 Stream
  - 是否播放
  - 是否录音
- 是否运行完整测试套件（本步骤应为否）
- 当前限制
- 下一步：`DEV-07.02 — 最小 Tkinter 实验向导 UI`

不要用大量 token复述整个实现过程。