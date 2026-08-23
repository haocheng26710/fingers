# DEV-07.04 实施报告：UI 与完整模拟测量链路集成

## 结论

**FAIL**。DEV-07.04 新增定向测试、直接相关 DEV-07 回归、静态检查和 3 条件/6 次 fake sweep 演练均通过；唯一一次完整测试套件得到 `985 passed, 2 failed in 3104.17s (0:51:44)`。依据完整套件失败门禁，本步骤没有提交或推送，并停止等待后续专门修复步骤。

## 基线与范围

- 仓库/分支：`https://github.com/haocheng26710/fingers.git` / `main`。
- 基线提交：`6dc77e7bbd346f381aaee9b7881b5e9e7015518f`。
- 开始时 local HEAD、`origin/main` 与 GitHub `main` 一致，工作区干净；完整套件前再次 fetch，remote 仍保持该基线。
- 未发现需要优先遵守的项目级 agent 指令文件。
- 本提示词按原始字节归档为 `docs/prompts/DEV-07.04.md`，16,488 bytes，SHA256 `05615FF4A489A406C2D5180D4CD714AD3A3F17B50775BBB61DE1145752AABAEF`。

## 集成架构

新增 `acoustic_ladder.ui.simulated_workflow.SimulatedMeasurementRunner` 作为一个窄应用服务。Tk factory 默认只构造该 runner；controller 仍负责用户确认、条件/重复顺序、暂停/取消、失败停留、重试身份和原子 session state，runner 顺序复用现有 ESS、DEV-07.01 `FakeFullDuplexBackend`、DEV-07.03 pilot bundle processing/calibration 以及仓库持久化工具。UI 不包含 real backend 选择或设备入口。

单次 repeat 的实际顺序为：

1. 从当前 demo condition、repeat 和新 run ID 构造确定性 48 kHz mono capture request；
2. 使用既有 ESS fixture/生成器及 `FakeFullDuplexBackend` 发布 create-only 四文件 capture bundle；
3. 重读 run/QC，并由既有 pilot bundle processing 入口验证 completed 状态、WAV SHA256、48 kHz、mono、样本形状和有限性；
4. 拒绝 underrun、overrun、clipping 或不完整 capture；
5. 验证并加载固定 `CMM29939.txt`；
6. 复用 ESS processing 生成 IR、未校准复数 transfer/幅值/原始相位；
7. 应用 DEV-07.03 log-frequency iMM-6C 幅值校准，验证 500–8,000 Hz mask 全部有效且相位逐元素不变；
8. 在 session 内以同父目录 staging、create-only 原子发布七文件 processing envelope 和 receipt；
9. 比较 capture bundle 处理前后字节；所有步骤成功后 controller 才记录 successful run 并推进 repeat。

UI 增加 Capture、Bundle、ESS、iMM-6C、校准频段、结构检查和结果目录状态，保留单后台 worker + queue/`after()` 主线程更新边界，并提供“重试当前重复”。界面持续声明 fake-only、不会播放或录音、结构检查不构成正式声学 PASS/FAIL。

## 3 条件 / 6 次 fake sweep 演练

通过 controller 等价用户确认状态执行全部 3 个 demo conditions，每条件自动执行 2 次 repeat。结果：

- 6/6 successful runs，6 个 run ID 唯一；顺序固定为 condition 1–3、各 repeat 1–2；
- 六个四文件 capture bundle和六个七文件 processing envelope均逐一完整重放验证；
- 六个 receipt 均绑定各自 run ID，校准 SHA256 均为 `421070ec6d41c1b92cb69f0f5e4e290f9644847d92d52590994a80ea9e17a11e`；
- 恢复后状态为 `all_complete`，成功 run 列表一致，未新增或重复 capture；
- 所有演练数据只写入任务临时目录下的 `development/demo/`，验收后精确清理；未写入正式数据 root。

## 失败、重试与恢复

定向 fault 测试覆盖首次/第二次 capture 失败、cancel、clipping、underrun、overrun、processing 失败、校准哈希失败和 persistence collision。失败 repeat 不计完成、不推进下一 repeat/condition，UI 显示具体失败和“需要重试”；重新采集使用 `attempt_002` 新 run ID 和新 create-only 目录，旧 bundle 字节保持不变。

恢复会严格重放成功 bundle、processing envelope、receipt、run ID 与路径绑定；缺失 receipt 的成功声明被拒绝且 state bytes 不被改写。若 state 已记录某位置开始尝试但没有成功证据，恢复为当前 repeat 的待重试状态，下一次使用递增的新身份；已经成功的 repeat 不重复执行。

## 定向验证

- DEV-07.04 新增测试：`18 passed in 5.49s`。
- 合并 DEV-07.01/02/03 直接相关路径：`.venv\\Scripts\\python.exe -m pytest tests/dev07 -q --basetemp .d704direct -p no:cacheprovider`，`78 passed in 10.80s`。
- Ruff format check（8 个 affected Python files）：`8 files already formatted`。
- Ruff lint（同 8 文件）：`All checks passed!`。
- strict mypy：`.venv\\Scripts\\mypy.exe --strict src/acoustic_ladder/ui`，`Success: no issues found in 7 source files`。
- `git diff --check`：通过；仅出现 Git 对工作树 CRLF 将规范化为 LF 的信息性 warning，无 whitespace error。
- 新增/修改 Python 文件 suppression 扫描：`NO_SUPPRESSIONS_FOUND`；未增加 skip、xfail、noqa 或 type ignore。
- 未修改 Schema，因此未运行 Schema consistency。
- 校准文件 SHA256 实测：`421070EC6D41C1B92CB69F0F5E4E290F9644847D92D52590994A80EA9E17A11E`。

TDD 过程中真实出现并修正的 RED 包括缺少完整 runner、controller 未接入 processing、缺少 retry/recovery 状态、默认 UI 仍使用 capture-only runner、缺少 UI 状态字段，以及 interrupted attempt 未标记重试。一个早期 focused pytest 使用系统默认 temp root 时遇到 Windows `PermissionError`；之后统一使用工作区短 basetemp。环境原生 patch helper 持续返回 `helper_unknown_error`，因此改用可审计的 Git patch输入；期间数个手工 patch 计数/插入位置错误均在语法检查或 focused test 前后被发现并纠正，没有计为通过。

## 唯一一次完整测试套件

命令：

```powershell
.venv\Scripts\python.exe -m pytest --basetemp=.d704all -q -p no:cacheprovider
```

结果：`2 failed, 985 passed in 3104.17s (0:51:44)`。没有并行运行，也没有第二次完整套件。

失败测试：

1. `tests/dev03/test_context_encoding.py::test_production_audio_code_calls_no_forbidden_api_after_context_change`
2. `tests/dev03/test_preflight_persistence_cli.py::test_production_audio_code_calls_no_forbidden_api`

首个根因：这两个历史 DEV-03 测试对整个 `src/acoustic_ladder/audio/*.py` 做 AST 扫描，并要求任何调用属性都不得命名为 `Stream` 或 `wait`。现有、未由 DEV-07.04 修改的 `src/acoustic_ladder/audio/pilot_capture_backends.py` 在第 210 行包含 DEV-07.01 的完整运行时授权门之后的 `module.Stream(...)`，第 222 行包含完成事件 `finished.wait(...)`；因此两个断言的 `called.isdisjoint(forbidden)` 为 false。DEV-07.04 diff 不包含该文件。按本步骤门禁，没有修改历史测试或 DEV-07.01 backend，也没有运行失败 selector或重跑完整套件。

完整套件 basetemp `.d704all` 已验证为 workspace 内精确目录并删除，删除后不存在。

## 修改文件

- `.gitattributes`
- `README.md`
- `docs/prompts/DEV-07.04.md`
- `docs/reports/DEV-07.04.md`
- `docs/IMPLEMENTATION_LOG.md`（仅追加）
- `src/acoustic_ladder/ui/controller.py`
- `src/acoustic_ladder/ui/simulated_workflow.py`
- `src/acoustic_ladder/ui/tk_app.py`
- `tests/dev07/test_simulated_measurement_workflow.py`
- `tests/dev07/test_simulated_workflow_controller.py`
- `tests/dev07/test_simulated_workflow_failures.py`
- `tests/dev07/test_simulated_workflow_recovery.py`
- `tests/dev07/test_simulated_workflow_ui.py`

## 当前状态与限制

- Git commit：未创建。
- push：未执行。
- 工作区保留上述未提交 DEV-07.04 改动和本失败报告，供后续专门修复步骤处理。
- 完整套件失败，因此 DEV-07.04 不能声明 PASS，不能进入真实硬件接入或 UI-01.01。
- 仍只有幅值校准；没有相位校准、94 dB 绝对 SPL、正式 QC 阈值或正式实验授权。
- 全程未枚举或连接真实设备，未打开真实 Stream，未播放，未录音，未产生正式实验结论。
