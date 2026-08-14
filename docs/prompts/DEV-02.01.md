# Acoustic Ladder 实施提示词 — DEV-02.01

## 0. 执行身份

你当前位于 Acoustic Ladder 的实际代码仓库中。

本序列编号：

`DEV-02.01`

本序列名称：

`工程骨架、配置契约、不可变存储与合成数据`

本步骤必须在已经通过验收的 `DEV-01.01` 基础上实施。

基线提交应为：

`06d77b39acc9f609617a4e216647dc3f6c590a1d`

目标远端：

`https://github.com/haocheng26710/fingers.git`

目标分支：

`main`

本步骤完成后停止，不得自行进入 `DEV-03.01`。

---

# 1. 执行前检查

先执行只读检查：

- 当前仓库根目录；
- 当前分支；
- 本地 HEAD；
- `origin/main`；
- 远端 URL；
- 工作区状态；
- 最近提交；
- 是否存在用户未提交修改；
- 是否存在新的项目级指令文件。

必须确认：

- 当前位于正确仓库；
- 当前分支为 `main`；
- 本地 HEAD 与 `origin/main` 一致；
- 基线包含已通过的 `DEV-01.01`；
- 工作区干净；
- 远端为指定仓库。

如果发现不一致、无关修改、冲突历史或远端异常，立即停止，不修改、不提交、不推送。

通过预检后，首批写入动作必须包括：

1. 将本提示词原文保存到 `docs/prompts/DEV-02.01.md`；
2. 在 `docs/IMPLEMENTATION_LOG.md` 末尾新增 `DEV-02.01`；
3. 将新条目状态标为 `IN_PROGRESS`；
4. 不得修改已经完成的 `DEV-01.01` 日志、提示词或完成报告。

---

# 2. 本步目标

本步骤建立后续音频、实验协议和分析功能共同依赖的稳定基础：

1. 建立领域数据模型；
2. 建立分层配置系统；
3. 建立设备、音频、实验协议和分析配置契约；
4. 建立配置加载、严格校验、规范化和内容哈希；
5. 建立 session、reassembly、run 和 artifact 数据模型；
6. 建立不可覆盖、可追踪、原子写入的数据存储；
7. 建立 synthetic 与 real 的强制隔离；
8. 实现简单、透明、可重复的合成数据生成器；
9. 生成阶段 1–4 的草案配置，但不实现正式协议引擎；
10. 提供 CLI、Schema、测试和文档；
11. 保持 V1.3 provisional manifest 和 ZIP 原样不变；
12. 全部验收通过后提交并推送。

---

# 3. 本步禁止解决的问题

本步骤不实现：

- 真实声卡枚举；
- 真实音频播放或录音；
- PortAudio、sounddevice 或声卡驱动；
- ESS 正式激励；
- 音频延迟校准；
- 反卷积；
- 脉冲响应恢复；
- 复传递函数；
- 正式 QC 信号算法；
- 阶段 1–4 测量矩阵生成；
- 正式随机化协议执行；
- 分类器、回归器或交叉验证；
- 操作界面；
- 数据库服务；
- GitHub Actions；
- CAD 重建；
- 几何锁定；
- `experiment-ready`；
- `device_manifest.lock.json`；
- 阶段 5 以后功能。

可以为后续步骤定义接口和数据契约，但不得提前实现其业务逻辑。

---

# 4. 必须保持不变的 DEV-01.01 产物

以下文件必须保持字节不变：

- `reference/model_packages/Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip`
- `config/devices/device_manifest.provisional.json`
- `config/devices/device_manifest.provisional.sha256`
- `schemas/device_manifest.schema.json`
- `reference/model_reviews/V1_3_package_audit.json`
- `reference/model_reviews/V1_3_package_review.md`
- `reference/calibration/V1_3_user_calibration_record.json`
- `reference/calibration/V1_3_user_calibration_record.md`
- `docs/prompts/DEV-01.01.md`
- `docs/reports/DEV-01.01.md`

其中：

- ZIP SHA256 必须仍为  
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest SHA256 必须仍为  
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

`docs/IMPLEMENTATION_LOG.md` 只能追加 `DEV-02.01`，不得改写 `DEV-01.01`。

如果确实发现 DEV-01.01 阻断性缺陷，停止本步骤并报告，不得顺手重写已经验收的事实文件。

---

# 5. 已冻结的研究边界

必须继续保持：

- 正式模式为 1 个输出 + 1 个输入；
- TX 近端为扬声器；
- RX 近端为麦克风；
- TX 远端闭合；
- RX 远端闭合；
- 未使用节点必须安装 BLK；
- BLK 表示封堵，不是开放端；
- 阶段 1–4 正式数据不得混入诊断参考通道；
- synthetic 和 real 必须明确区分；
- synthetic 不能作为真实结构有效性的证据；
- 当前模型状态仍为 provisional；
- 当前几何已经实际打印且校准已应用；
- 当前仍不是 geometry-locked；
- 当前仍不是 experiment-ready。

所有常规参数必须由配置文件提供，不能散落在业务源码中。

---

# 6. 推荐项目结构

在尊重现有项目结构的前提下，建议新增：

- `src/acoustic_ladder/config/`
  - 配置模型；
  - YAML 安全加载；
  - 配置 bundle；
  - Schema 导出；
  - 配置校验 CLI。
- `src/acoustic_ladder/domain/`
  - session；
  - reassembly；
  - run；
  - node state；
  - artifact；
  - config snapshot；
  - data origin。
- `src/acoustic_ladder/storage/`
  - 规范化 JSON；
  - 内容哈希；
  - 原子写入；
  - 不可变 session/run 存储；
  - 相对路径安全检查。
- `src/acoustic_ladder/synthetic/`
  - 合成配置；
  - 透明合成模型；
  - 数组生成；
  - 合成 session 创建；
  - CLI。
- `config/audio/`
- `config/protocols/`
- `config/analysis/`
- `config/synthetic/`
- `schemas/`
- `docs/architecture/`
- `data/README.md`
- 新增单元和集成测试。

可以根据现有代码风格调整模块文件名，但职责必须清晰，不能把所有实现堆入单一文件。

---

# 7. 配置系统要求

## 7.1 技术要求

使用严格的类型模型，推荐 Pydantic v2。

YAML 加载必须：

- 使用安全加载；
- 禁止执行自定义 YAML tag；
- 拒绝重复键；
- 拒绝未知字段；
- 对错误给出清晰字段路径；
- 不静默转换明显不合理的值。

更新 `pyproject.toml` 和 `uv.lock`，锁定新增依赖。

建议新增：

- Pydantic；
- NumPy；
- 安全 YAML 解析依赖。

不要引入数据库、Web 框架、机器学习框架或音频驱动依赖。

## 7.2 四层配置

必须明确区分：

1. `device_manifest`
2. `audio_config`
3. `protocol_config`
4. `analysis_config`

另外允许独立的：

5. `synthetic_config`

配置 bundle 必须保存：

- schema version；
- 原始文件相对路径；
- 原始文件 SHA256；
- 规范化内容 SHA256；
- 加载时间只进入运行记录，不进入内容哈希；
- 对应 device manifest SHA256；
- 验证状态。

配置内容哈希必须基于规范化、稳定排序的 JSON，而不是 YAML 空格和注释。

---

# 8. AudioConfig 契约

创建草案配置，例如：

`config/audio/default_1x1_ess.yaml`

至少包含：

- schema version；
- config ID；
- config status；
- run mode；
- audio backend；
- output device；
- input device；
- output channel列表；
- input channel列表；
- 通道角色；
- 采样率；
- ESS 起始频率；
- ESS 终止频率；
- ESS 时长；
- 前静音；
- 后静音；
- 输出增益；
- 输入增益；
- hardware ready；
- notes。

当前可确认：

- 采样率：48000 Hz；
- ESS 起始频率：300 Hz；
- ESS 终止频率：10000 Hz；
- formal 输出通道数：1；
- formal 输入通道数：1；
- 输出角色：TX speaker；
- 输入角色：RX microphone。

当前不能确认：

- 音频 backend；
- 实际设备 ID；
- 实际设备名称；
- 设备通道号；
- ESS 时长；
- 前后静音；
- 输入增益；
- 输出增益。

这些字段必须为 `null`，并使：

`hardware_ready = false`

配置本身可以作为 draft 通过结构校验，但不得被判定为可执行真实采集。

底层模型必须能够表达 N 输出 + M 输入；正式模式校验器必须要求恰好 1+1。正式配置中出现额外通道必须失败。

需要验证：

- 频率大于 0；
- 起始频率小于终止频率；
- 终止频率低于 Nyquist；
- 通道角色不重复；
- formal 模式严格 1+1；
- 未确认硬件字段不能被默认值伪造。

---

# 9. ProtocolConfig 契约

本步骤只定义、加载和校验草案，不生成正式测量矩阵。

创建：

- `config/protocols/stage1_single_bridge.yaml`
- `config/protocols/stage2_single_node_proxy_states.yaml`
- `config/protocols/stage3_two_node_interaction.yaml`
- `config/protocols/stage4_four_node_states.yaml`

共同字段至少包括：

- schema version；
- protocol ID；
- protocol version；
- experiment stage；
- draft/execution-ready 状态；
- device manifest 引用和哈希；
- formal/diagnostic 模式；
- 边界条件；
- 允许模块；
- 未选择节点状态；
- selected nodes；
- state definitions；
- continuous labels；
- loading direction；
- repeats；
- reassemblies；
- sessions；
- randomization enabled；
- random seed；
- operator confirmation requirements；
- proxy experiment 标记；
- notes。

当前所有协议都必须：

- formal 模式；
- TX 近端扬声器；
- RX 近端麦克风；
- 双远端闭合；
- 未使用节点为 BLK；
- `execution_ready = false`。

尚未确认的重复次数、session 数和重装次数必须为 `null`。

阶段要求：

### Stage 1 草案

- 允许 BLK、B40、B32、B28；
- 一次一个桥；
- 其他节点 BLK；
- selected node 在模板中可为 `null`；
- 不生成 19 状态测量矩阵。

### Stage 2 草案

- 通用 NodeState；
- 代理状态为 BLK、B28、B32、B40；
- `proxy_experiment = true`；
- selected node 为 `null`；
- 支持可选连续值及单位；
- 支持 loading/unloading 方向字段；
- 不把固定桥孔描述为真实连续形变。

### Stage 3 草案

- 两个二元节点；
- selected node pair 当前为 `null`；
- 允许表达 00、10、01、11；
- 其他节点 BLK；
- 不计算交互残差；
- 不生成组合计划。

### Stage 4 草案

- selected nodes 从 device manifest 的推荐节点读取；
- 预期为 N1、N3、N4、N6；
- 不能在 Python 代码中硬编码该列表；
- 配置中必须记录选择来源为 manifest recommendation；
- 其他节点 BLK；
- 不生成 16 个组合；
- 不执行分类。

协议校验必须确认所有节点均存在于当前 manifest，拒绝未知、重复或非法节点。

---

# 10. AnalysisConfig 契约

创建：

`config/analysis/default.yaml`

至少包含：

- schema version；
- config ID；
- config status；
- 分析频带；
- 平滑开关；
- 平滑参数；
- 基线选择规则；
- 特征列表；
- 归一化方式；
- 分组字段；
- 交叉验证策略；
- 模型顺序；
- 随机种子；
- decision gate 阈值；
- notes。

当前可确认：

- 分析频带：500–8000 Hz；
- 平滑默认关闭；
- 模型顺序：
  1. template/correlation
  2. ridge
  3. logistic regression
  4. LDA
  5. random forest
- 分组候选：
  - session
  - reassembly
  - day

当前不能确认：

- QC 阈值；
- 效应/漂移门限；
- 分类通过门限；
- 具体特征集合；
- 具体归一化方式；
- 最终交叉验证方法。

未知项必须为 `null` 或明确 draft，不得伪造。

本步骤只校验配置，不实现特征、模型或交叉验证。

---

# 11. 领域数据模型

至少建立以下稳定概念。

## 11.1 DataOrigin

只允许：

- `synthetic`
- `real`

诊断或正式属性必须使用独立字段，不能用 `data_origin` 混淆。

## 11.2 RunMode

至少允许：

- `formal`
- `diagnostic`
- `development`

synthetic run 应同时具有：

- `data_origin = synthetic`
- `run_mode = development`
- `formal_eligible = false`

## 11.3 NodeState

至少包括：

- node ID；
- state ID；
- module ID；
- state type；
- discrete label；
- optional continuous value；
- optional unit；
- loading direction；
- proxy state；
- provenance/notes。

NodeState 不能绑定某一种未来状态模块。

## 11.4 SessionRecord

至少包括：

- session ID；
- session schema version；
- created time；
- data origin；
- run mode；
- operator；
- device manifest reference；
- config bundle reference；
- reassembly IDs；
- run IDs；
- immutable status；
- notes。

## 11.5 ReassemblyRecord

至少包括：

- reassembly ID；
- session ID；
- sequence index；
- created time；
- assembly description；
- operator confirmation；
- related runs。

## 11.6 MeasurementRunRecord

至少包括：

- run ID；
- session ID；
- reassembly ID；
- protocol ID；
- measurement order；
- data origin；
- run mode；
- formal eligible；
- complete node-state map；
- timestamps；
- config hashes；
- artifact references；
- generation/acquisition backend；
- software version；
- status；
- failure reason；
- notes。

## 11.7 ArtifactRef

至少包括：

- artifact type；
- repository/session 相对路径；
- SHA256；
- byte size；
- MIME 或数据格式；
- shape；
- dtype；
- created by；
- immutable flag。

不得在持久记录中保存本机绝对路径。

---

# 12. 不可变数据存储

实现 session/run 文件存储，不实现数据库。

每个 session 至少形成：

`session_<id>/`

其下包括：

- `manifest/`
- `protocol/`
- `raw/`
- `processed/`
- `qc/`
- `features/`
- `models/`
- `reports/`
- `events/`
- `session_record.json`

要求：

- synthetic 位于独立的 synthetic 根目录；
- real 位于独立的 real 根目录；
- synthetic 写入器不得写入 real；
- 目标 session 或 run 已存在时必须失败；
- 默认禁止覆盖；
- 不能用静默删除后重建；
- 所有文件写入使用临时文件和同文件系统原子替换；
- 完成标记只能在必需文件全部成功后写入；
- 失败时不能留下看似完成的 run；
- 所有路径必须限制在指定数据根目录内；
- 拒绝 `..`、绝对路径和路径逃逸；
- 配置快照必须复制到 session；
- 同时保存原始配置和规范化 JSON；
- 保存原始 SHA256 和规范化内容 SHA256；
- device manifest sidecar 必须验证；
- artifact 必须计算 SHA256；
- 不同配置不得覆盖已有数据。

允许通过依赖注入提供时间和 ID 生成器，以便测试确定性；不得为了测试在生产逻辑中写死时间或 ID。

事件记录建议使用不可变的连续编号文件，例如：

- `events/000001_session_created.json`
- `events/000002_run_created.json`

已存在的事件文件不得修改。

---

# 13. 合成数据生成器

## 13.1 用途边界

合成数据只用于：

- 测试配置；
- 测试目录和文件写入；
- 测试运行记录；
- 测试数组接口；
- 测试后续处理模块的输入契约。

不得用于：

- 证明真实结构有效；
- 生成实验结论；
- 报告分类准确率；
- 调整出人为夸大的类间差异；
- 与 real 数据混放。

## 13.2 配置

创建：

`config/synthetic/default.yaml`

至少包含：

- schema version；
- generator version；
- random seed；
- sample rate；
- duration；
- speed of sound；
- baseline coupling；
- propagation loss；
- module effect scale；
- noise level；
- session drift；
- reassembly drift；
- output/input channel counts；
- output dtype；
- notes；
- physical limitations。

343 m/s 可以作为合成模型假设，但必须记录来源和假设属性，不能伪装成实际环境测量值。

## 13.3 生成逻辑

实现简单、透明、文档化的模型：

- 从 device manifest 读取节点位置；
- 根据 `2*x/c` 形成节点近似往返延迟；
- 根据模块孔径形成相对耦合权重；
- 支持 BLK 基线；
- 支持简单传播损耗；
- 支持可控噪声；
- 支持 session 漂移；
- 支持 reassembly 漂移；
- 所有随机行为由显式 seed 控制。

模型可以生成简单的合成激励、合成脉冲响应和输入响应，但不得称为正式 ESS、正式反卷积或真实声学仿真。

必须记录模型局限：

- 不包含完整波导模态；
- 不包含真实端部反射；
- 不包含打印粗糙度；
- 不包含泄漏；
- 不包含扬声器和麦克风响应；
- 不包含真实非线性；
- 不能验证真实可分性。

## 13.4 数组接口

规范化数组形状：

- `outputs[n_output_channels, n_samples]`
- `inputs[n_input_channels, n_samples]`
- 可选 `synthetic_ir[n_input_channels, n_output_channels, n_ir_samples]`

要求：

- dtype 明确；
- 数值有限；
- shape 与元数据一致；
- synthetic 默认仍采用 1+1；
- 文件中保存 seed、生成器版本和模型参数；
- 建议使用 NPZ 保存数组；
- JSON 保存元数据；
- 数组文件必须有 ArtifactRef 和 SHA256。

所有合成 run 必须：

- `data_origin = synthetic`
- `formal_eligible = false`
- 带有明显的 `NOT_EXPERIMENTAL_RESULT` 标记。

---

# 14. CLI 要求

保留 DEV-01.01 已有 CLI 和接口兼容性。

新增可复制命令，至少支持：

- 验证单个配置；
- 验证完整配置 bundle；
- 导出配置 JSON Schema；
- 创建 synthetic session；
- 生成一个 synthetic run；
- 校验 session/run 完整性；
- 校验 artifact SHA256；
- 显示配置规范化哈希。

可以建立统一顶层 CLI，也可以使用模块 CLI，但命名必须稳定且在 README 中明确。

不得让 synthetic CLI 接受或默认写入 real 数据目录。

---

# 15. Schema 要求

至少新增并提交：

- `audio_config.schema.json`
- `protocol_config.schema.json`
- `analysis_config.schema.json`
- `synthetic_config.schema.json`
- `session_record.schema.json`
- `reassembly_record.schema.json`
- `measurement_run_record.schema.json`
- `artifact_ref.schema.json`

Schema 应由实际类型模型导出或通过自动测试确保与模型同步，避免手工 Schema 与代码漂移。

必须拒绝：

- 未知字段；
- 缺失必需字段；
- 非法枚举；
- formal 非 1+1；
- 开放远端；
- 未使用节点不是 BLK；
- synthetic 标成 formal eligible；
- 频率超过 Nyquist；
- 重复节点；
- manifest 不存在的节点；
- 路径逃逸；
- 不一致的数组 shape/dtype 元数据。

---

# 16. 测试要求

## 16.1 回归测试

DEV-01.01 原有 43 项测试必须全部继续通过。

必须验证以下文件未改变：

- V1.3 ZIP；
- provisional manifest；
- manifest sidecar；
- device manifest Schema；
- DEV-01.01 提示词和完成报告。

## 16.2 配置测试

至少覆盖：

- 安全 YAML；
- 重复键拒绝；
- 自定义 tag 拒绝；
- 未知字段拒绝；
- audio draft 合法；
- formal 1+1 合法；
- formal 多通道拒绝；
- 频率范围检查；
- Nyquist 检查；
- hardware unknown 保持 null；
- hardware ready 不能在字段不全时为 true；
- Stage 1–4 草案加载；
- 非法节点拒绝；
- 重复节点拒绝；
- Stage 4 节点来自 manifest；
- 修改测试 manifest 推荐节点后，代码应跟随 manifest，而非继续返回 N1/N3/N4/N6；
- 双远端非闭合时拒绝；
- 未使用节点规则不是 BLK 时拒绝；
- analysis draft 未确认阈值保持 null；
- 配置规范化哈希不受 YAML 空格和键顺序影响。

## 16.3 存储测试

至少覆盖：

- 创建 synthetic session；
- 目录结构完整；
- 配置快照和哈希；
- 重复 session ID 拒绝；
- 重复 run ID 拒绝；
- 默认禁止覆盖；
- 路径穿越拒绝；
- 绝对路径拒绝；
- artifact 哈希校验；
- artifact 被篡改后校验失败；
- 写入失败时没有完成标记；
- 事件记录不可覆盖；
- session/run 记录不含本机绝对路径；
- synthetic 无法写入 real 根目录。

## 16.4 合成测试

至少覆盖：

- 同一 seed 输出字节一致；
- 不同 seed 输出不同；
- 节点延迟从 manifest 读取；
- 修改测试 manifest 节点位置后，延迟随之改变；
- 数组 shape 为 channel-first；
- dtype 正确；
- 全部数值有限；
- metadata 与数组一致；
- 1+1 默认；
- `data_origin = synthetic`；
- `formal_eligible = false`；
- 包含 `NOT_EXPERIMENTAL_RESULT`；
- session/reassembly drift 可控；
- 噪声可控；
- BLK 基线可生成；
- 未知模块拒绝；
- synthetic 文件不会出现在 real 目录；
- 不产生分类准确率或实验结论。

## 16.5 静态检查

必须运行：

- 格式检查；
- Ruff lint；
- strict mypy；
- 完整 pytest；
- Schema 生成一致性检查；
- Git diff whitespace 检查。

禁止用大范围 ignore、skip 或 xfail 隐藏问题。

---

# 17. 验收标准

## PASS

只有以下全部成立才可 PASS：

- Git 基线正确；
- DEV-01.01 受保护产物未改变；
- 原 43 项测试继续通过；
- 四层配置契约完成；
- 配置未知值未被猜测；
- formal 1+1 守卫有效；
- 协议草案不执行正式测量矩阵；
- session/run/artifact 模型完成；
- 不可变存储有效；
- 路径安全和原子写入有效；
- synthetic 与 real 强隔离；
- 合成数据确定且透明；
- 合成输出明确不是实验结果；
- 所有新增 Schema 可验证；
- 所有新增测试通过；
- 无 skip/xfail；
- Ruff、格式和 mypy 通过；
- 日志、提示词和完成报告真实；
- 未实现禁止范围；
- 工作区最终只包含本序列改动；
- 推送前差异检查通过。

## FAIL

任一情况均为 FAIL：

- 修改 V1.3 ZIP 或 provisional manifest；
- 修改已完成的 DEV-01.01 记录；
- 猜测真实硬件或切片参数；
- 把 synthetic 当作 real；
- synthetic 写入 real 目录；
- synthetic 标记 formal eligible；
- 在源码中硬编码节点位置或阶段四节点；
- formal 配置接受多于 1+1；
- 接受开放远端；
- 接受未使用节点留空；
- 覆盖已有 session/run；
- 使用不安全 YAML；
- 存储本机绝对路径；
- 生成分类结论；
- 实现真实音频或后续阶段；
- 测试失败或未运行；
- 存在未解释的 skip；
- 创建 geometry lock；
- 在失败或中断时推送。

---

# 18. 文档要求

至少创建：

- `docs/architecture/configuration.md`
- `docs/architecture/domain-model.md`
- `docs/architecture/storage-layout.md`
- `docs/architecture/synthetic-data.md`

文档必须说明：

- 四层配置职责；
- 字段来源和哈希；
- formal 1+1 与底层 N+M 的关系；
- synthetic 与 real 隔离；
- session/reassembly/run 层级；
- 不可变写入规则；
- 数组 shape 和 dtype；
- 合成模型公式、参数和局限；
- 如何从干净环境复现 synthetic 示例；
- 本步骤没有证明真实声学结构有效。

更新 README，加入实际运行过的配置、存储和 synthetic 命令。

---

# 19. 日志与完成报告

在 `docs/IMPLEMENTATION_LOG.md` 追加 `DEV-02.01`，保持与 DEV-01.01 相同结构。

至少记录：

- 开始和结束时间；
- 基线提交；
- 输入 manifest 及 SHA256；
- 采用的依赖及版本；
- 实际执行动作；
- 文件变更；
- 配置字段决定；
- synthetic 模型公式和参数；
- 实际运行命令；
- 测试真实结果；
- 初次失败及修正；
- 未执行项及原因；
- 偏差；
- 已知限制；
- 下一步可用接口；
- Git 目标和提交主题。

创建：

`docs/reports/DEV-02.01.md`

完成报告至少包含：

- 本步目标和最终状态；
- 创建及修改文件；
- 配置体系摘要；
- 数据模型摘要；
- 存储不变式；
- synthetic 算法摘要；
- 实际生成示例；
- 所有运行命令；
- 原有与新增测试数；
- 静态检查结果；
- DEV-01.01 文件哈希回归结果；
- 已知限制；
- 未实现内容；
- DEV-03.01 可复用接口；
- Git 目标、分支和计划提交主题。

不得在提交文件内编造尚未产生的提交 SHA。

---

# 20. Git 提交与推送

只有全部验收 PASS 后才允许：

1. 检查 `git diff`；
2. 检查没有秘密、大型临时数据、虚拟环境或缓存；
3. 确认 synthetic 示例数据没有误提交到数据目录；
4. 确认所有改动属于 `DEV-02.01`；
5. 更新日志状态为 `PASSED`；
6. 创建提交；
7. 推送 `origin/main`；
8. 验证远端 SHA 与本地 HEAD 一致。

建议提交信息：

`DEV-02.01: add config, immutable storage, and synthetic data`

如果执行失败、中断、测试不完整或推送失败：

- 不推送；
- 不强推；
- 不删除工作；
- 本地如实记录状态；
- 返回具体问题；
- 等待 `DEV-02.02` 修正提示词。

执行完成回复必须报告：

- 最终状态；
- 实际提交 SHA；
- 远端；
- 分支；
- 本地与远端 SHA 是否一致；
- 工作区是否干净；
- 原有测试数量和新增测试数量；
- manifest 与 ZIP 是否保持原哈希；
- 配置、存储和 synthetic 的主要交付物；
- 已知限制。

完成 `DEV-02.01` 后停止，不要自行进入 `DEV-03.01`。