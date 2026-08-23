# DEV-07.04：UI 与完整模拟测量链路集成

你现在负责 Acoustic Ladder V1.3 项目的 `DEV-07.04`。

本步骤是进入真实硬件操作前的软件冻结点。

唯一目标是把以下现有组件连接成一条可见、可恢复的完整模拟测量链路：

- DEV-07.02 Tkinter 实验向导
- DEV-07.01 fake full-duplex capture
- 现有 ESS 生成与处理
- DEV-07.03 iMM-6C 幅值校准
- 现有 create-only 持久化和处理凭证

本步骤仍然不连接、枚举或操作真实音频硬件。

## 一、执行基线

仓库：

- Remote：`https://github.com/haocheng26710/fingers.git`
- Branch：`main`
- 预期父提交：`6dc77e7bbd346f381aaee9b7881b5e9e7015518f`

开始前：

1. 阅读：
   - `AGENTS.md`
   - README
   - `docs/IMPLEMENTATION_LOG.md`
   - `docs/reports/DEV-07.01.md`
   - `docs/reports/DEV-07.02.md`
   - `docs/reports/DEV-07.02R.md`
   - `docs/reports/DEV-07.03.md`
   - DEV-07.01 capture core
   - DEV-07.02 UI/controller
   - DEV-07.03 microphone calibration 和 pilot bundle adapter
2. 检查：
   - 当前分支为 `main`
   - 工作区干净
   - local HEAD、`origin/main`、GitHub `main` 一致
   - 当前提交等于预期父提交
3. 如果基线不一致、工作区不干净或无法验证：
   - 立即停止
   - 不修改、不提交、不推送
   - 报告实际状态
4. 不覆盖、回滚、删除或格式化无关文件。
5. 将本提示词以 UTF-8 无 BOM 原样保存为：
   - `docs/prompts/DEV-07.04.md`
6. 修改前向 `docs/IMPLEMENTATION_LOG.md` 末尾追加：
   - `[DEV-07.04][STARTED]`
   - 父提交
   - 本步骤集成范围
   - 明确声明只使用 fake backend，尚未访问真实音频硬件
7. 实施日志只能追加，不得修改已有历史。

## 二、前序临时文件检查

先检查以下文件是否存在以及是否被 Git 跟踪：

- `.dev0703-start.patch`
- `.dev0703-attributes.patch`
- `.dev0702r-log.patch`
- 根目录其他 `.dev*.patch`
- `__pycache__`
- `.pytest_cache`
- demo WAV、JSON、session state
- 前序任务产生的临时目录

处理规则：

1. 如果这些 `.dev*.patch` 不存在于 HEAD，只记录它们是执行期间临时文件，不做额外清理提交。
2. 如果它们被当前 HEAD 跟踪，并且确认只是任务辅助补丁：
   - 在本次新提交中删除；
   - 如确有需要，只加入精确 ignore 规则；
   - 不得使用过宽的 `*.patch` 忽略规则。
3. 如果存在无法确认归属的文件：
   - 停止；
   - 不删除；
   - 不提交、不推送；
   - 报告路径和原因。
4. 不重新审计整个仓库。

## 三、角色边界

### `[用户操作]`

在本步骤的 UI 模拟演练中，用户只负责：

- 查看当前 Stage、条件和 N1–N6 装配要求
- 勾选装配确认
- 确认耳机未佩戴
- 确认装置位置
- 点击开始当前条件
- 必要时重试、暂停或紧急停止

### `[程序执行]`

程序负责：

- 生成确定性 ESS 输出参考
- 调用 fake backend
- 保存四文件 capture bundle
- 验证 bundle
- 执行现有 ESS 处理
- 应用 `CMM29939.txt` 幅值校准
- 生成处理凭证
- 判断结构流程是否完整
- 保存进度
- 两次重复均成功后进入下一条件

本步骤不得把任何程序模拟行为描述为真实实验操作。

## 四、集成原则

先检查现有组件接口，再进行最小连接。

必须复用：

- 现有正式计划和 demo plan
- DEV-07.02 controller 和 session state
- DEV-07.01 capture request、fake backend、取消机制和四文件 bundle
- 现有 ESS 生成
- 现有 ESS processing
- DEV-07.03 bundle adapter 和 microphone calibration
- 现有 create-only / atomic publish
- 现有 processing receipt

不得：

- 在 UI 中重新实现 ESS
- 在 UI 中重新实现校准
- 增加第二套 fake capture
- 复制 Stage 1–4 条件定义
- 建立新的数据库或事件总线
- 重构整个项目
- 增加不必要的 Schema 或 sidecar

可以增加一个小型应用服务或 runner，将 controller 与现有 capture/processing API 连接，但不要创建多层抽象框架。

## 五、单次 repeat 的完整流程

每个 repeat 必须按以下顺序执行：

1. 从当前 demo 条件构造确定性 capture request。
2. 使用现有 ESS 生成器生成输出参考。
3. 调用 DEV-07.01 `FakeFullDuplexBackend`。
4. 成功采集后创建四文件 bundle：
   - `captured_input.wav`
   - `output_reference.wav`
   - `run.json`
   - `qc.json`
5. 重新读取并验证 bundle：
   - 状态为 completed
   - SHA256 一致
   - 48 kHz
   - mono
   - 样本数量有效
   - 数值有限
6. 使用现有 ESS 处理生成：
   - IR
   - 未校准复数传递函数
   - 未校准幅值
   - 原始相位
7. 加载仓库中的：
   - `calibration/microphones/dayton_imm6c/CMM29939.txt`
8. 验证校准文件 SHA256：
   - `421070EC6D41C1B92CB69F0F5E4E290F9644847D92D52590994A80EA9E17A11E`
9. 应用 DEV-07.03 校准：
   - 在对数频率轴线性插值
   - 幅值加校准 dB
   - 复数传递函数乘以 `10 ** (correction_db / 20)`
   - 相位保持不变
   - 500–8,000 Hz 全部在有效校准范围内
10. 使用现有 processing persistence 保存处理数组和凭证。
11. 全部保存成功后，才将该 repeat 标记为成功。
12. 更新 `session_state.json`。
13. 如果是第一个 repeat，自动开始第二个 repeat。
14. 如果两个 repeat 都成功，进入下一条件并重新等待用户装配确认。

不得在 capture 完成但 processing 失败时把 repeat 标记为成功。

## 六、结构性完成判定

本阶段没有正式声学阈值，不得显示正式实验 `PASS/FAIL`。

UI 只允许显示：

- `结构检查通过`
- `需要重试`
- `已取消`
- `处理失败`

一个 repeat 只有同时满足以下条件，才可显示“结构检查通过”：

- capture 状态为 completed
- 输入输出文件完整
- WAV 哈希一致
- 输入输出样本数量有效
- 所有必要数据为有限数
- 无 backend underrun
- 无 backend overrun
- 无 clipping sample
- ESS processing 成功
- 分析频段存在有效频点
- 500–8,000 Hz 校准掩码全部有效
- 校准 SHA256 正确
- processing receipt 成功发布
- 原始数据未被覆盖

该判定只是软件结构完整性，不是声学质量或实验结论。

UI 中必须显示：

`当前结果仅为模拟链路结构检查，不代表正式声学 PASS/FAIL。`

## 七、失败和重试

### 7.1 Capture失败

如果 capture：

- cancelled
- failed
- 样本不足
- 哈希不符
- underrun
- overrun
- clipping

则：

- 不执行或不完成后续正式 processing；
- repeat 不计为成功；
- UI 显示具体原因；
- 不自动进入下一 repeat 或下一条件；
- 用户可点击“重试当前重复”。

### 7.2 Processing或校准失败

如果：

- ESS处理失败
- 校准文件哈希错误
- 校准文件解析失败
- 分析频段不完整
- processing persistence失败

则：

- capture bundle 保持不变；
- repeat 不计为完成；
- 不覆盖已有文件；
- UI 显示“处理失败”及简短原因；
- 用户可以重试处理或重新执行当前 repeat；
- 不自动跳过。

不要增加复杂自动重试策略。

### 7.3 重试身份

每次重新采集必须使用新的 run ID。

不得覆盖先前失败或取消的 bundle。

session state 应明确记录：

- 当前条件
- 当前 repeat
- 已成功 run ID
- 最近失败 run ID（如有）
- processing receipt 路径
- 是否需要重试

## 八、UI显示要求

保留 DEV-07.02 的精简布局，只增加必要状态。

每个 repeat 至少显示：

- Capture：等待 / 运行 / 完成 / 失败 / 取消
- Bundle验证：等待 / 通过 / 失败
- ESS处理：等待 / 通过 / 失败
- iMM-6C校准：等待 / 已应用 / 失败
- 校准频段：500–8,000 Hz有效或无效
- 结构检查：通过或需要重试
- 结果目录

顶部持续显示：

- `模拟演练`
- `FAKE BACKEND`
- `不会播放或录音`
- `不构成正式实验结论`

不要增加：

- 实时频谱
- 实时波形
- 复杂绘图
- 校准曲线图
- 设备下拉菜单
- 音量控制
- 正式阈值设置
- 高级设置页面

## 九、线程与界面安全

长操作不能阻塞 Tkinter 主线程。

要求：

- capture 和 processing 在单个受控后台 worker 中顺序执行；
- Tkinter 控件只由主线程更新；
- 通过现有队列或 `after()` 返回状态；
- 运行期间禁止重复开始；
- 紧急停止调用 DEV-07.01 cancellation；
- 关闭窗口时先取消 worker，再保存一致状态；
- 后台异常不得让界面永久停在“运行中”。

不要引入 asyncio、复杂线程池或任务调度框架。

## 十、会话恢复

恢复 session 时：

1. 读取 `session_state.json`。
2. 验证它与当前 demo plan 一致。
3. 对标记为成功的 repeat：
   - 验证 run bundle 仍存在；
   - 验证 processing receipt 仍存在；
   - 验证关联 run ID 一致。
4. 验证成功后不重复执行。
5. 如果状态声称成功但证据缺失：
   - 不猜测；
   - 将该 repeat 标记为需要人工确认或重试；
   - 不覆盖原状态文件；
   - 显示明确错误。
6. 如果上次在 capture 或 processing 中途退出：
   - 不将其视为成功；
   - 回到当前 repeat 的待重试状态。

状态更新继续采用临时文件加原子替换。

## 十一、Demo演练

使用 DEV-07.02 的3条件 demo plan：

- 3个条件
- 每个条件2次repeat
- 总计6次fake sweep

要求：

- 所有数据写入 development/demo root；
- 不进入正式实验数据目录；
- 每个条件都经过用户确认状态；
- 六次成功结果各自有唯一run ID；
- 六个 capture bundle均可验证；
- 六个 processing结果均应用同一校准文件；
- 条件和repeat顺序可确定性复现；
- 不把demo结果用于Stage 1–4研究结论。

自动化验收可以绕过真实鼠标点击，但必须经过 controller 中等价的用户确认状态，不能直接调用底层函数跳过流程。

## 十二、启动方式

保留现有启动方式：

`uv run --frozen python -m acoustic_ladder.ui`

启动后默认进入：

- `development_demo`
- fake backend
- 3条件demo plan

不得添加任何可以在本步骤中切换到真实 backend 的按钮、参数或隐藏入口。

如果命令缺少依赖或环境异常：

- 显示可读错误；
- 不自动安装依赖；
- 不尝试真实设备。

## 十三、定向测试

先运行定向测试，不要一开始运行完整套件。

至少覆盖：

1. 一次repeat完成capture→bundle→processing→calibration→receipt；
2. 两次repeat自动连续执行；
3. 两次都成功后进入下一条件；
4. 3条件共生成6个唯一run；
5. 六个bundle均可重新验证；
6. 六个processing receipt均绑定正确run；
7. 校准文件SHA256正确；
8. 500–8,000 Hz校准掩码全部有效；
9. 校准后相位保持不变；
10. 原始数据未覆盖；
11. 第一次capture失败时不执行第二次；
12. 第二次capture失败时不进入下一条件；
13. processing失败时repeat不完成；
14. 校准失败时repeat不完成；
15. persistence失败时repeat不完成；
16. clipping时显示需要重试；
17. underrun/overrun时显示需要重试；
18. 重试使用新run ID；
19. 已成功repeat恢复后不重复执行；
20. 证据缺失的成功状态被拒绝；
21. 取消不会标记成功；
22. 关闭时安全取消worker；
23. UI状态更新不从后台线程直接操作Tk控件；
24. demo数据不会写入正式root；
25. 没有正式声学PASS/FAIL；
26. 没有真实设备枚举；
27. 没有打开真实Stream；
28. 没有播放；
29. 没有录音。

只运行：

- DEV-07.04 新增测试；
- DEV-07.01/02/03 与本次调用路径直接相关的测试；
- Ruff format：受影响文件；
- Ruff lint：受影响文件；
- strict mypy：受影响包；
- `git diff --check`；
- 新增抑制标记扫描。

不得新增：

- `skip`
- `xfail`
- `noqa`
- `type: ignore`
- 其他测试绕过。

定向检查通过后冻结代码，不再增加功能。

## 十四、完整测试套件冻结门

本步骤是连接真实硬件前的软件冻结点，因此在以下全部满足后运行完整测试套件一次：

- 定向测试全部通过；
- Ruff通过；
- strict mypy通过；
- `git diff --check`通过；
- 代码和文档已完成；
- 不再计划继续修改代码。

要求：

1. 完整测试套件只运行一次。
2. 不重新生成1.13 GB大型NPZ，除非现有完整套件本身明确使用已有受保护fixture。
3. 不额外执行344次demo演练。
4. 不重复运行Stage 1–4分析。
5. 不单独重复全部历史golden。
6. 如果完整套件失败：
   - 不进行“修改后反复全量重跑”；
   - 不提交、不推送；
   - 报告失败测试、首个根因和当前状态；
   - 等待后续专门修复步骤。
7. 不得通过skip、xfail或缩小测试发现范围获得通过。

## 十五、明确不在本步骤实施

不得实施：

- 真实设备枚举
- 真实设备绑定
- Host API选择
- 打开真实Stream
- 播放
- 录音
- 真实延迟测量
- 播放电平冻结
- 94 dB校准
- 绝对SPL
- 正式QC阈值
- 正式实验授权
- Stage 3新算法
- Stage 4多标签模型
- 实时频谱或波形
- 数据库
- 网络服务
- 自动安装依赖
- 正式实验结论
- 修改V1.3 ZIP、manifest或历史受保护哈希

## 十六、报告与日志

成功完成定向测试、demo端到端验收和一次完整套件后：

1. 新建：
   - `docs/reports/DEV-07.04.md`
2. 报告必须记录：
   - 集成架构
   - 单次repeat的实际执行顺序
   - 3条件/6次fake sweep结果
   - 六个run和processing结果是否唯一
   - iMM-6C校准是否应用
   - session恢复验证
   - 失败与重试验证
   - 定向测试命令和结果
   - 完整套件命令、测试数量、耗时和结果
   - 未访问真实硬件的事实
   - 当前限制
3. 向 `docs/IMPLEMENTATION_LOG.md` 末尾追加：
   - `[DEV-07.04][COMPLETED]`
4. README只增加简短的完整demo演练说明。
5. 不得记录虚假的真实测量、真实设备或正式声学结论。

## 十七、提交与推送

只有同时满足以下条件才允许提交和推送：

- 3条件/6次fake sweep端到端演练通过；
- 定向测试通过；
- 完整测试套件一次通过；
- Ruff、mypy、`git diff --check`通过；
- 没有测试抑制；
- session恢复和重试逻辑通过；
- 校准文件SHA256保持指定值；
- 没有访问真实音频硬件；
- 没有修改受保护产物；
- 文档和追加日志完成；
- 工作区没有临时产物或意外文件；
- 远程`main`未发生意外变化。

提交信息：

`feat: integrate simulated measurement workflow`

只允许普通非force push：

- Remote：`origin`
- Branch：`main`

禁止：

- force push
- amend
- rebase
- 改写历史
- 绕过检查
- 覆盖远程变更

推送后验证：

- local HEAD
- `origin/main`
- GitHub `main`

三者等于本次提交SHA，且工作区干净。

如果实现、测试、完整套件、文档、Git或推送任一步失败：

- 不提交
- 不推送
- 不伪造PASS
- 报告具体失败命令、测试、错误和当前状态

## 十八、最终回复格式

最终回复保持精简，只报告：

- `PASS`或`FAIL`
- 提交SHA
- 推送状态
- 启动命令
- demo条件数和fake sweep数
- 定向测试数量与结果
- 完整测试套件数量、耗时与结果
- session恢复结果
- iMM-6C校准SHA256
- 是否显示正式声学PASS/FAIL：应为否
- 是否枚举真实设备：应为否
- 是否打开真实Stream：应为否
- 是否播放：应为否
- 是否录音：应为否
- 主要修改文件
- 工作区是否干净
- 已知限制
- 下一步：`UI-01.01 — 用户执行3条件模拟界面验收`

不要重复粘贴完整提示词或输出冗长验证日志。