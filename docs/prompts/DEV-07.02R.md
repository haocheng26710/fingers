# DEV-07.02R：DEV-07.02 提交范围审计与临时产物清理

你现在负责 Acoustic Ladder V1.3 项目的 `DEV-07.02R`。

本步骤不是新增功能，也不是重写 UI。唯一目标是审计 DEV-07.02 修改的71个文件，清理误提交的临时产物和无关变化，使仓库恢复到与“最小 Tkinter UI”相符的精简状态。

## 一、执行基线

仓库：

- Remote：`https://github.com/haocheng26710/fingers.git`
- Branch：`main`
- 待审计提交：`144cea841b63d598817e901ae6c98ed2172028c9`
- 其预期父提交：`5c5ad0253f9dc02109b2982d1ddfa01789dcf052`

开始前：

1. 阅读：
   - `AGENTS.md`
   - `docs/reports/DEV-07.02.md`
   - `docs/IMPLEMENTATION_LOG.md`
   - `docs/prompts/DEV-07.02.md`
2. 检查：
   - 当前分支是 `main`
   - 工作区干净
   - local HEAD、`origin/main`、GitHub `main` 一致
   - 当前 HEAD 等于待审计提交
3. 如果基线不一致、工作区不干净或无法验证 Git 状态：
   - 立即停止
   - 不修改、不提交、不推送
   - 报告实际状态
4. 将本提示词以 UTF-8 无 BOM 原样保存为：
   - `docs/prompts/DEV-07.02R.md`
5. 修改前向 `docs/IMPLEMENTATION_LOG.md` 末尾追加：
   - `[DEV-07.02R][STARTED]`
   - 待审计提交 SHA
   - 明确说明本步骤只做范围审计和清理
6. 实施日志只能追加，不得修改已有历史。

## 二、先进行只读审计

在修改任何文件前，检查 DEV-07.02 相对父提交的全部变化。

至少检查：

- 文件总数
- 每个文件的状态：新增、修改、删除、重命名
- 每个文件的行数变化
- 是否存在整文件换行符转换
- 是否存在编码变化
- 是否存在文件权限变化
- 是否存在临时文件、补丁、缓存、运行数据或自动生成产物
- 是否修改了与 UI 无关的历史代码、测试、Schema、golden 或受保护文件

重点检查：

- `.dev0702-start.patch`
- 其他 `*.patch`
- `__pycache__`
- `.pytest_cache`
- 临时日志
- demo WAV
- demo JSON
- `session_state.json`
- 开发运行目录
- IDE 文件
- 自动备份文件
- 无意产生的二进制文件
- 无关 `.gitattributes` 或 `.gitignore` 扩张
- 仅由 CRLF/LF 转换导致的修改

必须生成一个分类表，至少分为：

1. UI 正式实现
2. UI 定向测试
3. 必要启动入口或项目配置
4. 必要文档、提示词和追加日志
5. 必要 `.gitignore` / `.gitattributes`
6. 临时或误提交文件
7. 无关修改
8. 尚不能判断的修改

不得仅凭文件名判断。必须检查实际 diff。

## 三、允许保留的范围

通常允许保留：

- `src/acoustic_ladder/ui/**`
- DEV-07.02 直接相关的 UI/controller 测试
- 必要的 Python 模块入口
- 必要的 Windows 启动脚本
- 为 UI 入口所需的最小项目配置修改
- README 中的简短启动说明
- `docs/prompts/DEV-07.02.md`
- `docs/reports/DEV-07.02.md`
- `docs/IMPLEMENTATION_LOG.md` 的追加内容
- 防止 demo 运行数据入库所需的最小 `.gitignore`
- 有明确依据的 `.gitattributes` 修改

即使位于这些目录，也必须确认内容确实与 DEV-07.02 有关。

## 四、应清理的内容

以下内容原则上不得保留在当前仓库版本中：

- `.dev0702-start.patch`
- 执行过程中用于恢复或比较的临时补丁
- cache
- demo capture 运行产物
- WAV、临时 JSON、临时 session state
- 自动生成但不属于正式源码的文件
- 无关格式化
- 无关换行符变化
- 无关测试改动
- 为一次性调试添加的代码
- 与 DEV-07.02 无关的 Schema、golden、分析结果或历史文档变化

`.dev0702-start.patch` 必须先检查内容和来源：

- 如果只是本次执行的临时起始补丁或恢复文件，应从当前版本中删除。
- 如有继续生成同类文件的可能，应在不扩大范围的情况下加入精确的 ignore 规则。
- 不要使用过宽的规则忽略所有有意义的 patch 文件。
- 如果它确有正式用途，必须在报告中给出明确证据；不能因为已经提交就默认保留。

## 五、修复原则

1. 不使用：
   - `git reset --hard`
   - force push
   - amend
   - rebase
   - 改写历史
2. 所有清理通过一个新的普通提交完成。
3. 只撤销由 DEV-07.02 提交引入的误修改。
4. 不覆盖父提交之前已有的用户内容。
5. 不修改仍然正确的 UI 功能。
6. 不借本步骤进行重构、重命名或代码美化。
7. 不新增功能。
8. 不访问真实音频硬件。
9. 不枚举设备、不打开 Stream、不播放、不录音。
10. 不修改 V1.3 ZIP、manifest、历史 golden 或受保护哈希。

对于无关但已经存在于父提交中的内容，不处理。

对于无法判断的文件：

- 不擅自删除
- 标记为待确认
- 停止提交和推送
- 在最终报告中列出路径和判断困难

## 六、精简验证规则

本步骤不得重复运行完整测试套件。

根据实际修改决定验证范围：

### 情况 A：只删除临时文件并修改文档或 ignore

只运行：

- `git diff --check`
- 临时产物扫描
- 工作区状态检查

不要重复运行31项 UI 测试、Ruff 或 mypy。

### 情况 B：修改或恢复了 Python UI/controller 代码

只运行：

- DEV-07.02 的31项定向测试一次
- 与被恢复文件直接相关的测试
- Ruff format：受影响 Python 文件
- Ruff lint：受影响 Python 文件
- strict mypy：受影响包
- `git diff --check`

### 情况 C：只修改测试代码

只运行受影响的定向测试和 `git diff --check`。

禁止运行：

- 完整 pytest suite
- 344次演练
- Stage 1–4 分析
- 1.13 GB NPZ
- 全部历史 golden
- 未修改 Schema 的 consistency
- 与本次清理无关的重复检查

同一检查通过后不得重复运行，除非之后的修改影响该检查。

不得新增：

- `skip`
- `xfail`
- `noqa`
- `type: ignore`
- 其他测试绕过

## 七、验收标准

完成后必须满足：

- 当前版本不再包含误提交的临时补丁。
- 当前版本不包含 demo WAV、运行 JSON、session state 或缓存。
- 不存在无关换行符批量变化。
- 不存在无关文件修改。
- UI 正式实现仍保留。
- demo plan 和 fake backend 流程仍保留。
- 不增加真实硬件能力。
- 当前提交相对 DEV-07.02 的改动只包含清理、必要恢复和本步骤文档。
- 工作区干净。
- 不声称运行了实际未运行的测试。

## 八、报告与日志

新建：

- `docs/reports/DEV-07.02R.md`

报告至少记录：

- DEV-07.02 原始变更文件总数
- 分类结果及每类文件数量
- `.dev0702-start.patch` 的实际性质
- 删除的文件
- 恢复的文件
- 保留的文件类型
- 是否发现换行符或编码问题
- 是否发现无关代码变化
- 实际运行的验证
- 未运行完整套件的事实
- 未访问真实硬件的事实
- 清理后的当前限制

向 `docs/IMPLEMENTATION_LOG.md` 末尾追加：

- `[DEV-07.02R][COMPLETED]`

内容必须完全贴合实际审计和清理结果，不得编造。

不要修改 DEV-07.02 原报告来隐藏问题；使用 DEV-07.02R 报告补充说明。

## 九、提交与推送

只有满足以下条件才允许提交和推送：

- 全部71个文件已经完成分类
- 临时产物已经清理
- 没有无法判断的文件
- 规定的精简验证通过
- 没有访问真实硬件
- 报告和追加日志完成
- 工作区仅包含本步骤预期改动
- 远程 `main` 未发生意外变化

提交信息：

`chore: clean DEV-07.02 repository artifacts`

只允许普通非 force push：

- Remote：`origin`
- Branch：`main`

推送后确认：

- local HEAD
- `origin/main`
- GitHub `main`

三者等于新提交 SHA，且工作区干净。

如果审计、清理、验证、Git 或推送任一步失败：

- 不提交
- 不推送
- 不伪造 PASS
- 报告具体文件、命令、错误和当前状态

## 十、最终回复格式

最终回复保持精简，只报告：

- `PASS` 或 `FAIL`
- 提交 SHA
- 推送状态
- DEV-07.02 原始变更文件数
- 分类结果摘要
- 删除的临时文件
- 恢复的无关修改
- 最终保留的核心文件范围
- 实际运行的验证及结果
- 是否运行完整测试套件：应为否
- 是否枚举真实设备：应为否
- 是否打开真实 Stream：应为否
- 是否播放：应为否
- 是否录音：应为否
- 工作区是否干净
- 下一步：`DEV-07.03 — iMM-6C 校准与真实数据处理适配`

不要重复粘贴长篇 diff 或完整提示词。
