# DEV-06.03：结果导出与 Stage 6 最终验收

## 目标

为 DEV-06.02 的 Stage 1–4 分析结果增加最小论文图表和摘要导出能力，并完成 Stage 6 唯一一次集中验收。

完成后，软件开发主线暂停，等待真实硬件接入。

## 基线

- 仓库：`https://github.com/haocheng26710/fingers.git`
- 分支：`main`
- 预期 HEAD：`db7d1ca26e5a23349447c052dbd0cd046b037931`
- 开始前确认 local HEAD、`origin/main` 和上述提交一致，工作区干净。
- 不一致时停止，不 reset、不覆盖、不推送。

## 精简规则

- 只实现结果导出，不增加新的分析算法或模型。
- 不增加网页、GUI、数据库、交互式仪表盘或自动论文写作。
- 不重新计算无关历史哈希。
- 定向检查通过后，阶段末只运行一次完整测试。
- 不访问或操作任何真实音频硬件。

## DEV-06.03-01：归档与日志

将本提示词原文保存为：

`docs/prompts/DEV-06.03.md`

在 `docs/IMPLEMENTATION_LOG.md` 末尾追加 `DEV-06.03`。只记录实际命令、修改、结果、错误、提交和推送状态，不改写旧内容，不编造结果。

## DEV-06.03-02：结果导出入口

在现有 analysis 命名空间增加一个公开导出函数和一个 CLI 命令。

输入为 DEV-06.02 输出目录，至少读取：

- `research_summary.json`
- `stage1_effects.csv`
- `stage2_proxy_analysis.csv`
- `stage3_interactions.csv`
- `stage4_predictions.csv`
- `research_receipt.json`

要求：

1. 检查必需文件存在；
2. 检查 CSV 列、有限数值和 summary/receipt 的基本一致性；
3. 不重新训练模型；
4. 不重新生成 measurement matrix；
5. 输出目录已存在时拒绝覆盖；
6. 使用 Matplotlib 非交互后端；
7. 如项目没有 Matplotlib，增加受约束的直接依赖并更新 lockfile；
8. 不增加 pandas、seaborn 或其他非必要绘图库。

## DEV-06.03-03：最小图表

输出以下图表，每张同时生成 300 DPI PNG 和 SVG：

1. `stage1_effects`

   - 展示节点/桥状态相对 BLK 的 feature 平均差值；
   - 使用热图或清晰的分组图；
   - 不显示显著性星号。

2. `stage2_proxy`

   - 无连续标签时绘制 proxy 状态的描述性均值；
   - 标题明确包含 `Proxy / no continuous label`；
   - 只有结果中确实存在连续趋势时才绘制拟合趋势。

3. `stage3_interactions`

   - 展示节点对 × feature 的 interaction residual；
   - 使用以零为中心的发散色标。

4. `stage4_confusion_matrix`

   - 使用 out-of-fold 真实标签和预测标签；
   - 类别顺序确定；
   - 图中说明数据为 synthetic development fixture。

图表要求：

- 轴名称、feature 名称和单位来自输入结果，不手工改写研究含义；
- 布局可读，标签不能明显截断；
- 默认使用英文图中文字，避免依赖特定中文字体；
- 每张图带有 `SYNTHETIC / PROVISIONAL` 标识；
- 不把 fixture 的 1.0 accuracy 描述成实际装置性能。

## DEV-06.03-04：摘要与清单

输出：

- `analysis_summary.md`
- `report_manifest.json`

`analysis_summary.md` 包含：

- 数据来源状态；
- Stage 1–4 简要结果；
- Stage 2 是否缺少连续标签；
- Stage 4 模型、fold、accuracy、balanced accuracy、macro-F1；
- 图表相对路径；
- synthetic/development/provisional 限制；
- 不构成正式实验结论的声明。

`report_manifest.json` 只需记录：

- 输入 research receipt/hash；
- 生成文件列表；
- Matplotlib/Python 版本；
- `synthetic=true`；
- `provisional=true`；
- `experimental_result=false`。

不需要为每张图片增加 sidecar，不需要新建复杂 Schema。

## DEV-06.03-05：定向测试

只增加以下核心测试：

1. 小型 DEV-06.02 fixture 能完成导出；
2. 四类图表的 PNG、SVG 和 Markdown 均生成；
3. 缺少输入文件或必需列时明确失败；
4. Stage 2 无连续标签时不会伪造趋势；
5. 输出目录已存在时拒绝覆盖；
6. CLI smoke test。

测试只检查文件存在、非空、SVG/PNG 基本格式和摘要字段，不做像素级 golden test。

## DEV-06.03-06：定向验收

先运行：

- DEV-06.03 新增测试；
- DEV-06.02 与导出接口直接相关的测试；
- 修改文件的 Ruff format check；
- 修改文件的 Ruff lint；
- 受影响模块的 mypy；
- 若修改 Schema，再运行 Schema consistency；
- `git diff --check`。

不得通过 skip、xfail、noqa、放宽类型或删除断言获得 PASS。

## DEV-06.03-07：Stage 6 集中验收

定向验收通过后，运行一次完整测试套件。

要求：

1. 使用仓库标准命令；
2. 使用较短的临时目录，避免 Windows 路径长度导致伪失败；
3. 不并行重复运行完整套件；
4. 如果完整套件已覆盖完整 344 行 measurement matrix，则不得再单独运行 344 行 smoke；
5. 如果没有覆盖，才补运行一次 344 行端到端 smoke；
6. 不额外生成第二套完整 1.13 GB matrix；
7. 测试临时产物完成后按现有测试机制清理。

若完整测试失败：

- 先定位失败原因，不立即重复整套测试；
- 只运行失败测试及直接相关回归完成修复；
- 代码发生修复后，最多再运行一次完整套件确认；
- 无法通过则报告 FAIL，不推送。

## DEV-06.03-08：文档

创建：

`docs/reports/DEV-06.03.md`

简要记录：

- 导出功能；
- 实际生成的图表；
- 定向测试结果；
- 完整测试结果与耗时；
- 是否覆盖完整 344 行；
- 是否发生重跑及原因；
- 当前软件就绪状态；
- 已知限制；
- 未访问真实硬件。

同步更新 README，将状态写为：

`Stage 6 software workflow complete; awaiting real hardware connection and authorization.`

不得写成实验完成或模型已证明有效。

## DEV-06.03-09：提交与推送

仅当定向检查和最终集中验收全部通过时：

1. 提交代码、测试、依赖/lockfile、提示词、日志、报告和 README；

2. 提交标题：

   `DEV-06.03: add analysis report export and close stage 6`

3. 普通非 force push 到 `origin/main`；

4. 确认 local HEAD 与 `origin/main` 一致；

5. 确认工作区干净。

失败、中断或远程冲突时不推送，不 force push，不 amend/rebase 已发布历史。

## 最终回复

只报告：

- PASS 或 FAIL；
- commit SHA 与推送状态；
- 新增图表和摘要；
- 定向测试结果；
- 完整测试数量、结果和耗时；
- 是否覆盖完整 344 行；
- 是否重复运行完整套件及原因；
- Ruff、mypy、Schema、`git diff --check` 结果；
- 工作区状态；
- Stage 6 是否完成；
- 已知限制；
- 未访问真实硬件，未产生正式实验结论。

完成后停止，不进入真实硬件接入。等待用户明确确认设备和装置已经连接。
