# DEV-06.02：Stage 1–4 离线研究分析最小闭环

## 目标

基于 DEV-06.01R 已验证的 measurement matrix，完成论文研究主线所需的最小离线分析：

- Stage 1：单节点/桥状态差异；
- Stage 2：proxy 状态趋势或组间描述；
- Stage 3：双节点交互残差；
- Stage 4：四节点状态基线分类。

本步骤只处理 synthetic development 数据，不产生真实声学结论。

## 基线

- 仓库：`https://github.com/haocheng26710/fingers.git`
- 分支：`main`
- 预期 HEAD：`3065887952676e3545633c177651f86713f5b50b`
- 开始前确认 local HEAD、`origin/main` 与上述提交一致，且工作区干净。
- 不一致时停止，不 reset、不覆盖、不推送。

## 精简规则

- 不运行完整测试套件。
- 不重新生成完整 Stage 1–4 execution。
- 不重新计算无关历史哈希。
- 不建立新的攻击矩阵、签名、外部 witness、迁移框架或复杂发布系统。
- 只增加完成研究分析所必需的模块、命令、测试和产物。
- 已通过的检查在相关代码未变化时不重复执行。
- 不访问或操作真实音频硬件。

## DEV-06.02-01：提示词归档与日志

将本提示词原文保存为：

`docs/prompts/DEV-06.02.md`

在 `docs/IMPLEMENTATION_LOG.md` 末尾追加 `DEV-06.02`，只记录实际执行内容：

- 基线；
- 修改文件；
- 分析定义；
- 运行命令和真实结果；
- 遇到的问题及处理；
- 提交和推送状态。

不得改写旧日志，不得编造结果，不重复粘贴历史哈希。

## DEV-06.02-02：最小分析入口

在现有 `acoustic_ladder.analysis` 命名空间中实现一个公开研究分析入口，并增加一个 CLI 命令。命令应：

1. 读取 DEV-06.01 measurement matrix、row index、feature schema 和 split plan；
2. 检查行数、特征列、标签和 fold 引用相互一致；
3. 不修改 DEV-06.01 的 15 文件 envelope；
4. 将结果写入用户指定的新输出目录；
5. 输出目录已存在时拒绝覆盖；
6. 不重新运行 ESS processing 或重新生成 1.13 GB matrix。

如执行时已有完整 344 行 matrix，则直接复用。若不存在，不得仅为本步骤重新生成；使用小型测试 fixture 完成实现，并把完整 344 行运行推迟到 Stage 6 最终验收。

## DEV-06.02-03：Stage 1 分析

从 row metadata 派生 Stage 1 分组，不在源码中写死节点名称。

对每个“活动节点 × 桥状态 × feature”输出：

- 样本数；
- feature 均值；
- 标准差；
- 相对同 session/reassembly BLK baseline 的平均差值。

只做描述性分析，不计算或宣称正式显著性，不设置 pass/fail 阈值。

## DEV-06.02-04：Stage 2 分析

Stage 2 必须继续标记为 proxy。

- 如果 row metadata 中存在由协议来源提供的有限数值连续标签：
  - 对每个 feature 计算普通最小二乘斜率和 `R²`；
  - 记录使用的标签字段和样本数。
- 如果不存在可信连续标签：
  - 只输出各 proxy 状态的样本数、均值和标准差；
  - trend 状态写为 `not_computed_missing_continuous_label`；
  - 不从 condition 名称猜测数值。

## DEV-06.02-05：Stage 3 交互分析

对每个双节点组合和 feature 计算：

`interaction_residual = observed_pair_delta - delta_node_a - delta_node_b`

其中所有 delta 均相对对应的 BLK baseline。

输出：

- 节点对；
- 两个单节点 delta；
- 双节点 observed delta；
- additive expected delta；
- interaction residual；
- 样本数。

只作为 synthetic development 交互量，不进行正式显著性判定。

## DEV-06.02-06：Stage 4 基线分类

分类目标必须由 Stage 4 row 中按 plan/manifest 顺序排列的四节点状态向量派生。不得使用 row ID、session ID、reassembly ID、measurement order 或其他来源字段作为特征。

使用单一模型：

- scikit-learn 多项逻辑回归；
- `solver="lbfgs"`；
- `C=1.0`；
- `max_iter=1000`；
- 固定 random seed；
- 不搜索超参数；
- 不使用 PCA、自动特征选择、神经网络或模型集成。

若项目尚未声明 scikit-learn，可增加一个受约束的直接依赖并更新 lockfile；不要自行实现新的优化器。

每个 fold 必须：

1. 只用训练集拟合 feature 均值和标准差；
2. 零方差列使用安全处理，不产生 NaN/Inf；
3. 只用训练集拟合模型；
4. 在测试集生成预测；
5. 禁止任何跨 fold 预处理泄漏。

直接使用 DEV-06.01 已有的 session 和 reassembly 分组 folds，分别汇总：

- accuracy；
- balanced accuracy；
- macro-F1；
- confusion matrix；
- 每行真实类别与预测类别。

不设置分类通过阈值，不根据 synthetic 分数选择模型。

若某 fold 的训练集缺失必需类别，必须明确失败，不得改成随机切分。

## DEV-06.02-07：最小产物

输出目录只需包含：

1. `research_summary.json`

   - 输入 analysis ID/hash；
   - feature schema/version；
   - 数据状态；
   - Stage 1–4 汇总；
   - 模型名称、参数、random seed；
   - Python、NumPy、scikit-learn 版本；
   - `synthetic=true`；
   - `development=true`；
   - `provisional=true`；
   - `experimental_result=false`。

2. `stage1_effects.csv`

3. `stage2_proxy_analysis.csv`

4. `stage3_interactions.csv`

5. `stage4_predictions.csv`

6. `research_receipt.json`

   - 输入文件哈希；
   - 输出文件哈希；
   - 行数、特征数、fold 数；
   - 是否完成各 Stage；
   - 未执行真实硬件和正式实验的状态。

CSV 行顺序必须确定，数值必须有限。不要保存 pickle/joblib 模型；当前只需保存模型参数和结果。

除非仓库现有公共持久化约定强制要求，否则不要为每个文件增加 sidecar 或新 Schema。

## DEV-06.02-08：定向测试

只新增少量核心测试：

1. Stage 1 baseline delta 的手算 fixture；
2. Stage 2 有连续标签与无连续标签两种行为；
3. Stage 3 interaction residual 手算 fixture；
4. Stage 4 训练折标准化、防泄漏和预测覆盖；
5. 相同输入与 seed 产生相同结构化结果；
6. CLI 小型 smoke test。

使用小型内存或临时 fixture，不生成第二套完整 344 行矩阵。

如已有完整 matrix 可直接访问，再运行一次 344 行分析 smoke；没有则跳过该人工验收并在报告中说明“推迟到 Stage 6”，不要把自动测试标记为 skip。

## DEV-06.02-09：验收

只运行：

- DEV-06.02 新增测试；
- 被修改分析模块的直接相关测试；
- 修改文件的 Ruff format check；
- 修改文件的 Ruff lint；
- 受影响模块的 mypy；
- 若实际修改 Schema，再运行 Schema consistency；
- `git diff --check`。

不要运行整个 `tests/`。不要使用 skip、xfail、noqa、降低类型严格度或放宽断言来获得 PASS。

创建简短报告：

`docs/reports/DEV-06.02.md`

报告说明实际分析、测试结果、是否运行完整 344 行 smoke、已知限制以及 synthetic/provisional 边界。

## DEV-06.02-10：提交与推送

只有所有定向验收通过后才可以：

1. 提交代码、测试、依赖/lockfile、提示词、日志和报告；

2. 提交标题：

   `DEV-06.02: add minimal offline research analysis`

3. 普通非 force push 到 `origin/main`；

4. 确认 local HEAD 与 `origin/main` 一致。

失败、中断或远程冲突时不推送，不 force push，不 amend/rebase 已发布历史。

## 最终回复

只报告：

- PASS 或 FAIL；
- commit SHA 和推送状态；
- 修改文件；
- 新增测试及结果；
- 实际运行的定向检查；
- Stage 1–4 是否完成；
- Stage 2 是否存在可信连续标签；
- Stage 4 模型、fold 和指标；
- 是否运行完整 344 行 smoke；
- 完整测试套件未运行；
- 工作区状态；
- 已知限制；
- 未访问真实音频硬件，未产生正式实验结论。

完成后停止，不进入下一步骤。
