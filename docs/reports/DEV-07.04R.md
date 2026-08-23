# DEV-07.04R：历史音频 API 门禁修正与模拟链路冻结报告

## 结论

DEV-07.04R 验收通过。DEV-07.04 的生产实现未作修改；本修正仅把两份重复的 DEV-03 AST 门禁改为共享、上下文精确的测试门禁，并加入内存 AST 回归。DEV-07.04 与 DEV-07.04R 将作为一个原子提交交付。

## 基线与根因

- 开始时分支为 `main`，local HEAD、`origin/main`、GitHub `main` 均为 `6dc77e7bbd346f381aaee9b7881b5e9e7015518f`，远程地址正确。
- 工作区只包含上一阶段报告所列的 13 个 DEV-07.04 预期路径；没有额外用户改动。
- 两份旧测试只收集全部 `ast.Call` 的属性名，再全局禁止 `Stream` 和 `wait`。因此 DEV-07.01 已有、且未被 DEV-07.04 修改的安全门控 `module.Stream(...)` 与 `finished.wait(...)` 被误报。
- 修正前指定的两个 selector 实际得到 `2 failed in 1.83s`。

## 门禁契约

- `play`、`rec`、`playrec`、`RawStream`、`InputStream`、`OutputStream`、`RawInputStream`、`RawOutputStream` 继续全局禁止。
- `Stream` 只允许出现在 `src/acoustic_ladder/audio/pilot_capture_backends.py` 的 `SoundDeviceFullDuplexBackend.capture` 中，receiver 必须为 `module`。
- `wait` 只允许在同一文件、类和方法中以 `finished.wait(...)` 出现。
- 生产扫描要求两个允许点各恰好出现一次；违规诊断包含文件、行号、receiver 和属性名。
- 内存 AST 回归覆盖精确允许点、错误文件、错误类、错误方法、错误 receiver、全部高风险构造器、`play`/`rec`/`playrec`、额外 `wait` 和诊断位置。

## 实际验证

- 修正后两个原失败 selector：`2 passed in 1.66s`。
- 门禁自身首次回归：`14 passed in 0.03s`；诊断收紧后的门禁加两个 selector：`18 passed in 1.75s`。
- 门禁回归及两份直接相关 DEV-03 文件：`52 passed in 2.16s`。
- DEV-07.01 授权、binding、formal-mode、注入 fake module、禁止 query 和 UI 默认 fake 安全选择器：`6 passed in 0.57s`。
- DEV-07.04 五个直接测试文件：`18 passed in 5.67s`。
- 全部 `tests/dev07`：`78 passed in 9.71s`。
- 唯一一次完整 suite：`1003 passed in 2826.40s (0:47:06)`；未重复运行。
- Ruff format 最初只发现新测试两处机械折行；格式化后受影响 12 文件为 `12 files already formatted`，最终 R 门禁 4 文件为 `4 files already formatted`。
- Ruff lint：`All checks passed!`；`git diff --check` 通过；受影响文件 suppression 扫描无匹配。
- 新 helper 位于测试目录，生产源码与既有 strict mypy 范围未变化，因此按提示词未重复运行 mypy。Schema 未修改，未运行 Schema consistency。

## 文件与边界

- DEV-07.04R 新增：`tests/dev03/audio_api_guard.py`、`tests/dev03/test_audio_api_guard.py`、`docs/prompts/DEV-07.04R.md`、本报告。
- DEV-07.04R 修改：两份历史 DEV-03 门禁、`.gitattributes` 和追加式实施日志。
- `src/acoustic_ladder/audio/pilot_capture_backends.py` 无 diff；DEV-07.04 原报告未改写。
- 没有再次手工生成 3 条件 × 2 repeat 演练；既有 18 项 DEV-07.04 自动测试和全部 DEV-07 测试覆盖该链路。
- 所有 `.d704r-*` 临时目录均在仓库根内验证后删除，最终残留为 0。
- 原生 patch helper 一度报告 Windows sandbox `helper_unknown_error`；两次手写 `git apply` 因 hunk/context 被拒绝且未写入。后续使用精确计数、保留换行的受约束文本变换完成两份旧测试，最终 diff 和测试均通过。
- 未访问或枚举真实音频设备，未打开真实 Stream，未播放，未录音，未进行 94 dB、SPL、正式 QC 或正式实验，未产生正式实验结论。

报告落盘时提交、推送及推送后三端一致性尚待执行，不在此预写结果。
