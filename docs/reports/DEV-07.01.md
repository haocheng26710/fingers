# DEV-07.01 实施报告：受控的真实全双工采集核心

## 结果与范围

- 基线：`main` 的 `0597953517638db0cff5f208542a41fa817746d3`；开始时 local HEAD、`origin/main`、GitHub main 一致且工作区干净。
- 实现了默认关闭的 mono 48 kHz pilot 全双工核心、线程安全取消、确定性 fake backend、延迟加载且可注入的 sounddevice adapter，以及四文件 create-only 原子发布。
- 最小包仅包含 `captured_input.wav`、`output_reference.wav`、`run.json`、`qc.json`。失败、取消、输入不足或 staging 写入失败均不发布最终目录。
- `qc.json` 只记录结构指标，固定为 `pilot_structural_metrics_only`、`not_evaluated`、`thresholds_applied=false`。
- 未新增或修改 Schema、CLI、GUI、分析算法、模型或正式实验编排。

## 安全门

真实 adapter 在加载 sounddevice 和构造 `Stream` 前验证 hardware/operator/playback 三项授权、pilot 模式、正式模式关闭、pilot 配置来源、完整设备/Host API/通道绑定、48 kHz、mono、播放电平冻结及当前绑定与授权绑定完全一致。任一条件不满足即拒绝；不自动枚举、切换设备、提高音量或重试。

本步骤没有枚举、访问或连接真实音频设备，没有打开真实 Stream，没有播放、录音或校准。sounddevice adapter 测试仅使用进程内注入的 fake module；其 `query_devices` 若被调用会立即使测试失败。

## 测试先行与实际命令

- 首个 RED：`.\.venv\Scripts\python.exe -m pytest tests/dev07/test_pilot_capture.py -q`，按预期因 `acoustic_ladder.audio.pilot_capture` 尚不存在而 collection error。首次 GREEN 尝试遇到系统 pytest temp 权限错误；改用工作区短 `--basetemp` 后得到 `1 passed in 0.22s`。
- 扩展 RED：新增安全门和故障测试后因 `DeviceBinding` 尚不存在而 collection error；实现后 `14 passed in 0.38s`。
- fake 输入不足单测：`1 passed in 0.23s`。
- 最终定向 pytest：DEV-07.01 全部 15 个新增回归，加 8 个直接相关 ESS/virtual 测试选择器（含参数化展开），结果 `31 passed in 3.02s`。
- 最终 changed-file Ruff format check：`5 files already formatted`。
- 最终 changed-file Ruff lint：`All checks passed!`。
- strict mypy：`Success: no issues found in 2 source files`。
- 最终 `git diff --check` 与禁止抑制扫描记录在完成日志中。

开发过程中 Windows 沙箱补丁 helper 间歇性初始化失败；没有通过脚本重写文件，改用 Git patch stdin 应用同一最小补丁，并用哈希确认提示词原始字节及历史日志前缀未变化。

## 未执行检查

- 按提示词明确要求，没有运行完整 pytest suite、344 行 smoke、1.13 GB NPZ 生成、Stage 1–4 分析、历史 golden 全量检查或 Schema consistency。
- 原因：本步骤只允许新增测试和少量直接相关音频/ESS/持久化回归，且未修改 Schema。

## 已知限制与下一步

本步骤不冻结 ESS/静音/fade 时长、播放 dBFS 或正式 QC 阈值；不提供真实设备发现、UI、校准、SPL、正式 session/run 编排或实验结论。真实 adapter 只是受控底层接口，必须等待设备连接和未来显式授权后才可使用。

下一步：`DEV-07.02 — 最小 Tkinter 实验向导 UI`。

## Final pre-commit consolidation

The staged allowlist review found that the first RED/GREEN fake implementation remained beside the completed backend module. Before commit it was removed so there is exactly one `FakeFullDuplexBackend`. Because production code changed, the same directed set was run one permitted additional time: `31 passed in 4.44s`. Focused Ruff format, Ruff lint, and strict mypy were then rerun and again passed (`5 files already formatted`; `All checks passed!`; `Success: no issues found in 2 source files`).
