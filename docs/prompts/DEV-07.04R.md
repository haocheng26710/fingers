# DEV-07.04R：修复历史音频 API 门禁并完成模拟链路冻结

你现在负责 Acoustic Ladder V1.3 项目的 `DEV-07.04R`。

DEV-07.04 的定向测试、3条件/6次 fake sweep、恢复测试和静态检查均已通过，但完整测试套件因两个历史 DEV-03 AST 门禁失败而停止。

本步骤只修复该门禁契约与 DEV-07.01 受控真实 backend 之间的冲突，然后完成 DEV-07.04 冻结验收。

不得增加新功能，不得连接真实硬件。

## 一、当前基线

仓库：

- Remote：`https://github.com/haocheng26710/fingers.git`
- Branch：`main`
- 当前 HEAD：`6dc77e7bbd346f381aaee9b7881b5e9e7015518f`

当前状态是有意保留的未提交 DEV-07.04 工作区，不能要求工作区干净，也不能丢弃这些改动。

开始前：

1. 阅读：
   - `AGENTS.md`
   - `docs/reports/DEV-07.04.md`
   - `docs/prompts/DEV-07.04.md`
   - `docs/IMPLEMENTATION_LOG.md`
   - DEV-03.01 关于禁止音频流的历史提示词
   - DEV-07.01 capture backend、授权测试和报告
2. 验证：
   - 当前分支为 `main`
   - local HEAD、`origin/main`、GitHub `main` 均为上述基线
   - 当前没有 DEV-07.04 提交
   - 当前工作区中的修改与 `docs/reports/DEV-07.04.md` 记录的文件一致
3. 预期保留的 DEV-07.04 修改范围为：
   - `.gitattributes`
   - `README.md`
   - `docs/prompts/DEV-07.04.md`
   - `docs/reports/DEV-07.04.md`
   - `docs/IMPLEMENTATION_LOG.md`
   - `src/acoustic_ladder/ui/controller.py`
   - `src/acoustic_ladder/ui/simulated_workflow.py`
   - `src/acoustic_ladder/ui/tk_app.py`
   - `tests/dev07/test_simulated_measurement_workflow.py`
   - `tests/dev07/test_simulated_workflow_controller.py`
   - `tests/dev07/test_simulated_workflow_failures.py`
   - `tests/dev07/test_simulated_workflow_recovery.py`
   - `tests/dev07/test_simulated_workflow_ui.py`
4. 如果存在上述范围之外且无法解释的修改：
   - 停止
   - 不删除、不提交、不推送
   - 报告文件路径
5. 禁止：
   - `git reset --hard`
   - `git checkout --`
   - 丢弃当前 DEV-07.04 改动
   - amend
   - rebase
   - force push
6. 将本提示词以 UTF-8 无 BOM 原样保存为：
   - `docs/prompts/DEV-07.04R.md`
7. 向 `docs/IMPLEMENTATION_LOG.md` 末尾追加：
   - `[DEV-07.04R][STARTED]`
   - 当前 HEAD
   - 两个失败测试
   - 本步骤只调整历史门禁契约
8. 实施日志只能追加，不能改写历史。

## 二、已确认的失败

完整套件结果：

- `985 passed`
- `2 failed`
- 总计987项
- 耗时3104.17秒
- 未提交、未推送

失败测试：

1. `tests/dev03/test_context_encoding.py::test_production_audio_code_calls_no_forbidden_api_after_context_change`
2. `tests/dev03/test_preflight_persistence_cli.py::test_production_audio_code_calls_no_forbidden_api`

已确认的调用位置：

- `src/acoustic_ladder/audio/pilot_capture_backends.py`
  - `module.Stream(...)`
  - `finished.wait(...)`

`pilot_capture_backends.py` 由 DEV-07.01 引入，DEV-07.04 没有修改该文件。

## 三、根因

两个 DEV-03 测试建立时，项目只允许设备枚举和格式查询，禁止任何真实 Stream。因此测试对整个 `src/acoustic_ladder/audio/*.py` 做 AST 扫描，只要调用属性名出现在以下集合中就失败：

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

DEV-07.01 后，项目有意增加：

- 受完整授权门保护的 `SoundDeviceFullDuplexBackend`
- 授权通过后唯一的 `module.Stream(...)`
- 用于等待 callback 完成的 `threading.Event` 对象 `finished.wait(...)`

旧测试只识别属性名称，不识别：

- 调用对象
- 所在文件
- 所在类和方法
- 授权门
- `threading.Event.wait` 与 sounddevice `wait` 的区别

因此旧门禁已经与当前架构不一致。

## 四、修复原则

必须修复测试契约，不得通过隐藏或改名生产调用来骗过 AST 扫描。

禁止以下做法：

- 将 `module.Stream(...)` 改成 `getattr(module, "Stream")(...)`
- 将 `finished.wait(...)` 包装或改名，只为避开字符串匹配
- 删除真实 backend
- 删除授权门
- 使用 `noqa`
- 使用 `type: ignore`
- 使用 `skip` 或 `xfail`
- 缩小 pytest 测试发现范围
- 直接删除两个历史测试
- 将整个 `pilot_capture_backends.py` 排除在所有检查之外
- 放宽为“audio目录可任意调用Stream”

生产实现若没有发现新的真实安全缺陷，应保持不变。

## 五、快速反馈循环

先只运行两个失败 selector，确认 RED：

`tests/dev03/test_context_encoding.py::test_production_audio_code_calls_no_forbidden_api_after_context_change`

`tests/dev03/test_preflight_persistence_cli.py::test_production_audio_code_calls_no_forbidden_api`

预期修复前：

- 2 failed
- 原因仍为 `Stream` 和 `wait`

只运行这两个 selector，不运行完整套件。

记录实际失败结果。

## 六、更新后的音频 API 门禁

将两个重复历史门禁更新为符合当前架构的精确规则。

允许采用一个小型共享测试辅助函数，避免两个测试以后再次产生不同规则；如果现有测试架构不适合，共享函数不是强制要求。

### 6.1 全局继续禁止

以下调用在所有生产音频代码中继续禁止：

- `play`
- `rec`
- `playrec`
- `RawStream`
- `InputStream`
- `OutputStream`
- `RawInputStream`
- `RawOutputStream`

除下面唯一授权点外，其他 `Stream` 调用也继续禁止。

不得因为 DEV-07.01 存在真实 backend，就放开 sounddevice 快捷播放或其他 Stream 类型。

### 6.2 唯一允许的 Stream

只允许以下调用：

- 文件：`pilot_capture_backends.py`
- 类：`SoundDeviceFullDuplexBackend`
- 方法：`capture`
- 接收对象：`module`
- 属性：`Stream`

即唯一允许：

`module.Stream(...)`

必须验证：

- 只存在一个允许的 `module.Stream` 调用点
- 其他文件、类、方法或接收对象上的 `Stream` 调用仍然失败
- `RawStream`、`InputStream`、`OutputStream` 等仍然全部禁止

不要仅按文件名排除整个文件。

### 6.3 唯一允许的 wait

只允许以下调用：

- 文件：`pilot_capture_backends.py`
- 类：`SoundDeviceFullDuplexBackend`
- 方法：`capture`
- 接收对象：`finished`
- 属性：`wait`

即唯一允许：

`finished.wait(...)`

该调用是 `threading.Event.wait`，不是 sounddevice快捷播放等待。

其他可疑的 `wait` 调用不得因本次修复自动获得授权。

### 6.4 门禁输出

AST门禁失败时应报告具体调用位置，至少包含：

- 文件
- 调用属性
- 行号

避免以后只得到集合不相交失败而无法快速定位。

## 七、保持运行时安全门

修改AST测试后，必须继续验证以下运行时安全条件：

1. `playback_authorized=false` 时：
   - 拒绝capture
   - module loader调用次数为0
   - Stream构造次数为0
2. 设备绑定变化时：
   - 在module load之前拒绝
3. formal模式时：
   - 在module load之前拒绝
4. 采样率、mono通道或配置来源不符合要求时：
   - 在module load之前拒绝
5. 测试使用注入的fake sounddevice module：
   - 不枚举真实设备
   - 不导入或调用真实sounddevice
6. fake backend：
   - 永远不导入sounddevice
7. UI默认：
   - 仍只构造fake backend
   - 不提供切换real backend的入口

不得删除或弱化现有 DEV-07.01 安全回归。

## 八、回归测试

修复门禁后，按以下顺序测试。

### 8.1 门禁selector

首先重跑两个历史失败selector。

预期：

- 2 passed

### 8.2 门禁自身回归

增加最小回归，证明新门禁：

- 接受唯一的 `module.Stream`
- 接受唯一的 `finished.wait`
- 拒绝其他文件中的 `Stream`
- 拒绝其他接收对象上的 `Stream`
- 拒绝 `play`
- 拒绝 `rec`
- 拒绝 `playrec`
- 拒绝 `InputStream` 或其他Stream类型
- 拒绝额外的可疑 `wait`
- 报告文件和行号

可以使用小型内存AST fixture，不得创建复杂测试框架。

### 8.3 直接相关测试

只运行：

- 两个历史门禁测试文件中相关测试
- DEV-07.01 pilot capture授权测试
- DEV-07.04 的直接相关测试
- `tests/dev07` 定向集合

不要在这一阶段运行完整套件。

### 8.4 静态检查

只运行：

- Ruff format：本步骤受影响Python文件
- Ruff lint：本步骤受影响Python文件
- strict mypy：若共享辅助模块位于类型检查范围
- `git diff --check`
- suppression扫描

不得新增：

- `skip`
- `xfail`
- `noqa`
- `type: ignore`
- 测试过滤绕过

## 九、DEV-07.04功能复核

不要重新执行所有人工开发过程。

使用现有自动化定向测试确认：

- 3个demo条件
- 每条件2次fake sweep
- 6个唯一run
- 6个capture bundle
- 6个processing envelope
- iMM-6C校准SHA256正确
- 500–8,000 Hz校准有效
- 相位不变
- session恢复为`all_complete`
- 已成功repeat不重复执行
- 失败repeat可重试
- 不显示正式声学PASS/FAIL
- 不写入正式数据root

不要额外手动生成第二套6 sweep数据。

## 十、完整套件冻结门

只有以下全部通过后，才运行完整测试套件一次：

- 两个历史失败selector通过
- 新门禁回归通过
- DEV-07定向测试通过
- Ruff通过
- strict mypy通过
- `git diff --check`通过
- suppression扫描通过
- 代码已冻结，不再计划修改

使用仓库既有完整测试命令，并使用工作区内独立短basetemp及禁用pytest cache。

要求：

1. 本修复步骤完整套件只运行一次。
2. 不并行运行第二套完整测试。
3. 不重新生成不必要的1.13 GB NPZ。
4. 不额外重复Stage 1–4分析。
5. 如果完整套件再次失败：
   - 不继续反复全量重跑
   - 不提交、不推送
   - 报告失败测试和根因
6. 不得通过改变测试发现范围获得通过。

预期完整套件：

- 原985项继续通过
- 两个历史门禁通过
- 新增门禁回归通过
- 总套件全部通过

## 十一、临时目录与清理

所有测试临时目录必须：

- 位于确认的工作区或任务临时目录
- 使用唯一、明确的路径
- 不进入Git
- 测试完成后只清理本步骤创建的精确目录

不得：

- 对仓库根目录递归删除
- 使用不确定通配符删除
- 删除无法确认归属的文件
- 提交 `.dev*.patch`
- 提交 `__pycache__`
- 提交 `.pytest_cache`
- 提交basetemp

测试和清理后检查工作区文件清单。

## 十二、明确不在本步骤实施

不得实施：

- 新UI功能
- 新采集功能
- 真实设备枚举
- 打开真实Stream
- 播放
- 录音
- 真实硬件连接
- 播放电平冻结
- 绝对SPL
- 正式QC阈值
- Stage 3/4算法扩展
- 数据库
- 网络服务
- 重构音频架构
- 修改V1.3 ZIP、manifest或历史受保护哈希

## 十三、报告和日志

保留原失败报告：

- `docs/reports/DEV-07.04.md`

不得修改它来隐藏第一次完整套件失败。

新建：

- `docs/reports/DEV-07.04R.md`

新报告必须记录：

- 原完整套件结果：985 passed、2 failed
- 两个失败测试
- 快速selector复现结果
- 根因
- 为什么旧门禁在DEV-03时正确、在DEV-07.01后过时
- 新门禁的精确允许点
- 全局仍禁止的API
- 现有运行时授权测试结果
- DEV-07.04定向测试结果
- 修复后完整套件数量、耗时和结果
- 未访问真实硬件
- 未播放、未录音
- 已知限制

向 `docs/IMPLEMENTATION_LOG.md` 末尾追加：

- `[DEV-07.04R][COMPLETED]`

内容必须真实，不能编造测试或实验结果。

README无需增加新功能说明；仅在现有文字与实际状态冲突时做最小修正。

## 十四、提交与推送

当前 DEV-07.04 没有提交，因此修复成功后将：

- DEV-07.04完整模拟链路
- DEV-07.04R门禁修复
- 对应提示词、报告和追加日志

合并为一个原子提交。

只有同时满足以下条件才允许提交和推送：

- 两个原失败selector通过
- 新门禁回归通过
- DEV-07定向测试通过
- 完整套件通过
- Ruff、mypy、`git diff --check`通过
- 没有测试抑制
- 没有未解释文件
- 没有临时补丁或缓存
- 未访问真实音频硬件
- 校准文件SHA256保持：
  `421070EC6D41C1B92CB69F0F5E4E290F9644847D92D52590994A80EA9E17A11E`
- 文档和追加日志完成
- 远程main仍保持预期基线

提交信息：

`feat: integrate simulated measurement workflow`

提交说明中应明确：

`Align the legacy DEV-03 audio API guard with the DEV-07.01 safety-gated pilot backend.`

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
- GitHub main

三者等于新提交SHA，且工作区干净。

如果实现、测试、完整套件、文档、Git或推送任一步失败：

- 不提交
- 不推送
- 不伪造PASS
- 保留诊断证据
- 报告具体失败项和状态

## 十五、最终回复格式

最终回复保持精简，只报告：

- `PASS`或`FAIL`
- 提交SHA
- 推送状态
- 原失败selector复现结果
- 门禁修复方式
- 修复后两个selector结果
- DEV-07定向测试数量与结果
- 完整测试套件数量、耗时与结果
- 3条件/6次fake sweep结果
- Session恢复结果
- 是否显示正式声学PASS/FAIL：应为否
- 是否枚举真实设备：应为否
- 是否打开真实Stream：应为否
- 是否播放：应为否
- 是否录音：应为否
- 工作区是否干净
- 已知限制
- 下一步：`UI-01.01 — 用户执行3条件模拟界面验收`

不要重复粘贴完整提示词，不要输出冗长完整测试日志。