# DEV-05.01：阶段 1–4 协议矩阵编译器与确定性随机化

你现在位于 Acoustic Ladder 程序代码仓库中。本次只实施 `DEV-05.01`。完成后停止，不得自行进入 `DEV-05.02`、真实协议执行、硬件接入或分类分析。

---

# 1. 本步目标

实现一个严格、可重放、development-only 的“协议矩阵编译器”，把已经验证的：

- V1.3 provisional device manifest；
- 阶段 1–4 `ProtocolConfig`；
- development-only 计划规格；

编译为：

1. 完整的阶段条件矩阵；
2. 每个条件覆盖 manifest 全部节点的 `NodeState`；
3. session / reassembly / 连续重复层级；
4. 确定性条件块随机化顺序；
5. 操作者确认要求；
6. 不可变、可验证的计划产物。

本步只生成“计划”，不执行计划，不创建采集 run，不连接或访问真实音频设备。

成功仅表示：

`协议矩阵编译、确定性调度、持久化和只读重放的软件行为通过。`

不得解释为：

- 正式实验协议已经批准；
- 正式重复次数已经确定；
- 硬件已经就绪；
- 已完成任何真实测量；
- 已获得声学、分类、效应或可分性结论。

---

# 2. Git 基线与开始门禁

开始前执行并记录：

- 仓库根目录；
- 当前分支；
- `git status --short`；
- local `HEAD`；
- `origin/main`；
- GitHub `refs/heads/main`；
- remote URL；
- 最近提交记录；
- 项目内 `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`.agents/**`、`.codex/**` 等适用指令。

预期基线：

- remote：`https://github.com/haocheng26710/fingers.git`
- branch：`main`
- local HEAD、`origin/main`、GitHub main 应一致为：

`2affc46a5f902adcc5b946cc800542c937d25d6e`

- 提交标题：`DEV-04.04: record delivery audit`
- 工作区必须干净。

先正常执行只读 `git fetch origin main` 和远端引用核对；如果网络权限受限，应按环境权限流程申请只读网络权限后重试。

出现以下任一情况时立即停止并报告 `BLOCKED`，不得修改文件、提交或推送：

- 当前分支不是 `main`；
- remote URL 不符；
- local、origin 或 GitHub main 不一致；
- 基线不是上述提交；
- 工作区不干净；
- 存在未理解的项目级指令；
- 存在与本步骤重叠的用户未提交修改。

禁止使用：

- force push；
- `git reset --hard`；
- `git clean`；
- rebase；
- amend；
- 改写历史；
- 删除或覆盖用户文件。

---

# 3. 必须保持的研究边界

## 3.1 当前设备与几何状态

当前项目仍为：

`Acoustic Ladder V1.3 校准后圆形主管版本`

几何状态仍为：

`provisional`

不得创建或声称：

- `geometry-locked`；
- `experiment-ready`；
- `formal protocol ready`；
- `hardware-ready`；
- `experimental_result=true`。

核心受保护哈希至少包括：

- V1.3 ZIP  
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest  
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory  
  `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context  
  `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary  
  `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight  
  `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup  
  `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

必须继续通过已有 locked/golden tests，保持 ESS、processing、QC、repeatability 和 DEV-04.04 baseline-difference 的全部历史保护哈希。

DEV-04.04 的 9 个新保护哈希必须保持：

- condition binding JSON  
  `4dd706337e9bf68df80f4b4f315e3701bb4748d8899abab6333d2d020c2937093`
- condition binding sidecar  
  `570d00e4df23860864cc081221b4dbc00c254a8125207e41db5663a833aafbaa`
- arrays  
  `0e4be4450b31ef7f9d5c4965a5a70ec5446f30a06394ec1210af75d41185e97a`
- arrays sidecar  
  `3f0dd00290b5ee5b9fe419d27ce2b6e35d90c01dad7f43f02b29a9f416a5f2e0`
- metrics  
  `4fe1c19ae028bcab210b9f7b0ae32233b553b379c988f959b1fa2823169c9c57`
- metrics sidecar  
  `cb13460f8d7c370f7a9765fbefc0f181c611cd0ffedf13b42f5ec6931db5e82a`
- receipt  
  `c62e2e798872b0462380aa4e8f017b315c0bc131e3f3a254fcb89534539368cf`
- receipt sidecar  
  `b72ec605c3f6f170bc0c449c3b7ae6d2953d21dfd1f0fcb5118de84b7b76a456`
- metadata  
  `a7c5dd2db64d9741b712446c7859c287aabc0776bb0bc3e63a3d65a87e138772`

## 3.2 固定实验边界

继续保持：

- 正式架构默认 `1 输出 + 1 输入`；
- TX 近端为扬声器；
- RX 近端为麦克风；
- TX 远端闭合；
- RX 远端闭合；
- 未选节点必须为 `BLK`；
- 不恢复球体方向识别；
- 不恢复旧四管或多输入结构；
- 不添加正式参考麦克风；
- synthetic 和 real 数据严格隔离；
- 所有节点、模块和推荐节点必须从 manifest/protocol 读取；
- 不得在源码中硬编码 `N1…N6`、`B40/B32/B28` 或阶段四推荐节点。

## 3.3 真实硬件禁令

用户已明确：当前真实设备和装置均未连接，将在大体程序完成后再接入。

本步骤禁止：

- 枚举音频设备；
- 调用 production audio inventory/list；
- 连接、选择或绑定输入/输出设备；
- 推断设备索引、Host API 或通道；
- 播放声音；
- 录音；
- 打开音频 Stream；
- 读取或应用麦克风校准文件；
- SPL 校准；
- 电气回环；
- 真实延迟、共享时钟或全双工验证；
- 创建 real data root；
- 改变 `hardware_ready=false`；
- 使用 `sounddevice`、PortAudio 或其他真实音频 API 实施本步骤。

只允许处理配置、manifest、内存数据结构、development fixture 和临时目录中的计划产物。

---

# 4. 先归档提示词并初始化日志

## 4.1 提示词归档

先找到本任务实际收到的原始提示词附件或等价原始文本来源。

将原始提示词逐字节归档为：

`docs/prompts/DEV-05.01.md`

要求：

- 字节级复制；
- 不改变 CRLF/LF；
- 不添加或删除末尾换行；
- 不重新排版；
- 不进行 Unicode 规范化；
- 记录原始来源路径、字节数、换行统计和 SHA256；
- 验证源文件与归档文件逐字节一致；
- 必要时在 `.gitattributes` 中沿用既有 prompt binary 策略。

如果无法取得原始提示词字节来源，停止并报告 `BLOCKED`；不得自行从记忆重建归档内容。

## 4.2 实施日志

使用现有：

`docs/IMPLEMENTATION_LOG.md`

只允许追加，不得修改既有字节。

追加前记录：

- 文件字节数；
- 完整 SHA256；
- 将该完整内容视为冻结前缀。

本步骤日志统一使用序列：

- `DEV-05.01-00`：Git、仓库和项目指令基线；
- `DEV-05.01-01`：提示词归档及日志冻结前缀；
- `DEV-05.01-02`：现有协议/manifest/领域模型审查；
- `DEV-05.01-03`：阶段 1 条件矩阵 RED→GREEN；
- `DEV-05.01-04`：阶段 2–4 条件矩阵 RED→GREEN；
- `DEV-05.01-05`：重复层级与确定性随机化 RED→GREEN；
- `DEV-05.01-06`：不可变发布和只读验证 RED→GREEN；
- `DEV-05.01-07`：CLI、Schema 和文档；
- `DEV-05.01-08`：攻击、双根确定性与 golden；
- `DEV-05.01-09`：完整回归、静态门禁、保护哈希和清理；
- 如出现真实且必要的补充修正，继续顺序追加 `DEV-05.01-10` 等，不得覆盖旧条目。

日志必须完全贴合实际执行内容，至少记录：

- 实际命令；
- 实际 RED 失败及原因；
- 实际 GREEN 结果；
- 创建和修改的文件；
- 算法、排序和随机化规则；
- fixture 的明确数值及其 development-only 身份；
- 测试数量和耗时；
- 确定性哈希；
- 失败命令、修复方法和重跑结果；
- 临时目录的精确清理情况；
- 已知限制；
- 未执行内容；
- Git 提交/推送前的真实状态。

不得预填尚未发生的 PASS、测试数量、哈希、提交 SHA 或推送结果，不得编造操作。

日志应达到：另一位人员可依据日志和仓库，用其他 AI 尽可能复刻相同实现与验收结果。

---

# 5. 开始前必须读取的项目内容

至少完整检查：

- `README.md`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/architecture/domain-model.md`
- `docs/architecture/configuration.md`
- `docs/architecture/storage-layout.md`
- `docs/architecture/repeatability.md`
- `docs/architecture/virtual-capture.md`
- `docs/prompts/DEV-04.04.md`
- `docs/reports/DEV-04.04.md`
- `config/devices/device_manifest.provisional.json`
- `config/devices/device_manifest.provisional.sha256`
- `config/protocols/stage1_single_bridge.yaml`
- `config/protocols/stage2_single_node_proxy_states.yaml`
- `config/protocols/stage3_two_node_interaction.yaml`
- `config/protocols/stage4_four_node_states.yaml`
- `src/acoustic_ladder/config/models.py`
- `src/acoustic_ladder/config/bundle.py`
- `src/acoustic_ladder/domain/models.py`
- `src/acoustic_ladder/domain/paths.py`
- `src/acoustic_ladder/storage/io.py`
- `src/acoustic_ladder/storage/store.py`
- `src/acoustic_ladder/audio/condition_plan.py`
- `src/acoustic_ladder/audio/condition_plan_models.py`
- `src/acoustic_ladder/cli.py`
- `src/acoustic_ladder/config/schema.py`
- 现有 unit/integration/dev02/dev03/dev04 测试和相关 fixtures。

确认并记录当前协议事实：

- 阶段 1–4 都是 formal-mode draft；
- `execution_ready=false`；
- repeats/reassemblies/sessions 仍为 `null`；
- 正式随机化仍未启用且 seed 未确认；
- 阶段 2、3 的实际选择节点仍未确认；
- 阶段 4节点必须从 manifest recommendation 派生；
- 当前不存在通用阶段 1–4 测量矩阵编译器；
- 本步骤不能用测试 fixture 数值回填正式协议文件。

---

# 6. TDD 实施方法

必须遵循项目现有 TDD 方式，并完整读取当前环境提供的 `tdd` skill 及其直接引用指南。

采用纵向 tracer bullet：

`一个公共行为测试 RED → 最小实现 GREEN → 再进入下一个行为`

禁止：

- 先一次性写完全部测试；
- 先写完整实现再补测试；
- 测试私有函数；
- mock 自己的模块；
- 通过调用生产实现生成 expected；
- 只测试字段外形而不测试公共行为；
- 为未来步骤预埋未经测试的功能。

允许 mock 或注入的边界仅限：

- 固定时间；
- 文件系统故障；
- 并发冲突；
- 外部系统边界。

每个真实 RED、最小修正和 GREEN 都要同步追加实施日志。

---

# 7. 新增 development-only 计划规格

不要修改四个正式协议草案中的未知字段来制造“已确认参数”。

新增严格的 development-only 计划规格模型，例如：

`DevelopmentProtocolPlanSpec`

建议字段至少包括：

- `schema_version`
- `plan_spec_id`
- `usage_scope = development_fixture`
- `source_protocol_reference`
- `session_count`
- `reassemblies_per_session`
- `continuous_repeats_per_condition`
- `randomization_enabled`
- `random_seed`
- `selected_nodes`
- `max_planned_measurements`
- `operator_confirmation_required = true`
- `protocol_execution_authorized = false`
- `hardware_io_authorized = false`
- `formal_eligible = false`
- `experimental_result = false`

要求：

- Pydantic strict mode；
- `extra="forbid"`；
- `allow_inf_nan=false`；
- 安全 ASCII identifier；
- project-relative source reference；
- 计数必须为正整数，拒绝 bool；
- `max_planned_measurements` 必须为正并在物化前执行上限检查；
- randomization 为 true 时必须显式给出 seed；
- randomization 为 false 时 seed 必须为 null；
- 禁止条件列表、NodeState、measurement order、预计算排列或输出路径注入；
- development spec 必须绑定当前 source protocol 的原始字节、规范化字节和 SHA256；
- source protocol 被修改、移动、删除或替换后，publisher 和 validator 都必须拒绝；
- manifest/protocol/config 的来源只能由已加载 bundle 派生。

本步骤只允许 development fixture 覆盖尚未确认的运行层级参数。它不是正式实验配置，不能写回正式协议文件。

建议新增四个明确标记为 development fixture 的规格文件，分别覆盖阶段 1–4。

为了测试层级展开，可使用以下已授权的纯测试值：

- `session_count = 2`
- `reassemblies_per_session = 2`
- `continuous_repeats_per_condition = 2`
- `randomization_enabled = true`
- `random_seed = "dev0501-test-seed-v1"`

这些值只用于测试编译器，不是正式实验重复次数或随机种子。

阶段选择 fixture：

- 阶段 1：`selected_nodes = null`，必须遍历 manifest 全部节点；
- 阶段 2：可使用 `N2` 作为 development fixture 的单节点选择；
- 阶段 3：可使用 `N2`、`N5` 作为 development fixture 的双节点选择；
- 阶段 4：`selected_nodes = null`，必须从 manifest recommendation 派生。

`N2`、`N5` 只允许出现在测试 fixture 和测试 expected 中，禁止写入生产编译逻辑，也不得描述为正式实验推荐。

---

# 8. 公共编译接口

设计一个小接口、深实现的公共模块，例如：

- `load_development_protocol_plan_spec(...)`
- `compile_development_protocol_plan(...)`
- `publish_development_protocol_plan(...)`
- `validate_development_protocol_plan(...)`

公共编译或发布接口只能接收：

- 已验证的 bundle/manifest；
- 已加载且带来源证明的 development plan spec；
- 安全 plan ID；
- development-only plan store；
- publisher clock（仅发布 record 时间）。

不得接受：

- 任意 condition 列表；
- 任意 `NodeState`；
- 任意 measurement order；
- 任意 permutation；
- 任意预计算 plan；
- 任意真实 run；
- 任意 WAV/NPZ；
- 阈值、decision、features 或 classification；
- real root；
- 音频设备、Host API 或通道；
- 任意直接输出路径。

编译器必须从高优先级事实派生所有条件和节点状态。

---

# 9. 条件矩阵语义

## 9.1 通用要求

所有阶段的每个 condition 必须包含：

- 稳定、可复现的 condition ID；
- experiment stage；
- condition role/type；
- condition label；
- selected nodes；
- selected states/modules；
- manifest 全部节点的完整 `NodeState` map；
- canonical node-state SHA256；
- active/non-BLK node count；
- proxy-state 标记；
- source protocol/state-definition provenance；
- operator confirmation requirement；
- `operator_confirmation_status = pending`；
- `protocol_execution_performed = false`；
- `hardware_io_performed = false`；
- `formal_eligible = false`；
- `experimental_result = false`。

不得遗漏未选节点。未选节点必须明确为协议定义的 BLK state。

必须验证：

- manifest 节点完整；
- 未知节点和未知模块拒绝；
- state definition 必须属于 `allowed_modules`；
- BLK state 恰好存在并与边界要求一致；
- active node 数不超过 `max_active_bridges`；
- 状态标签无重复；
- 条件 ID 无重复；
- 每个 NodeState 都从协议 state definition 和 manifest 节点派生；
- 不使用源码内的几何、节点或模块常量。

条件的 canonical 初始顺序与后续随机化顺序分离保存。

## 9.2 阶段 1

从阶段 1 协议与 manifest 派生：

- 一个全 BLK baseline；
- 每个非 BLK state definition 在每个 manifest 节点上的单桥条件；
- 其他节点全部 BLK。

对于当前 V1.3 manifest 和当前阶段 1 协议，测试应得到：

`1 + 6 × 3 = 19` 个条件。

这个 `19` 只能作为当前输入的测试 oracle，生产逻辑必须由：

- manifest 节点数；
- 协议 state definitions；
- BLK/non-BLK 身份；

动态派生。

canonical 条件顺序建议为：

1. 全 BLK baseline；
2. 按协议 state definition 顺序遍历非 BLK 状态；
3. 每个状态内按 manifest 节点顺序遍历。

## 9.3 阶段 2

阶段 2 development spec 必须显式选择恰好一个 manifest 节点。

对该节点遍历阶段 2 的全部 proxy state definitions，其他节点全部 BLK。

当前 fixture 应得到 4 个条件。

必须保存：

- `proxy_experiment=true`
- `proxy_state=true`
- 实际固定模块身份；
- “固定孔径模块只是代理状态，不是真实连续变形”的状态标记。

禁止产生：

- 连续变形数值；
- 加载/卸载迟滞结论；
- 状态回归结果。

## 9.4 阶段 3

阶段 3 development spec 必须显式选择恰好两个不同 manifest 节点。

节点顺序必须按 manifest 的规范节点顺序归一，不能由调用者输入顺序改变最终字节。

根据协议 binary state definitions 和 `state_labels` 生成全部四种组合：

- `00`
- `10`
- `01`
- `11`

应验证配置标签：

- 长度等于两个节点；
- 每位仅为 `0/1`；
- 四种组合恰好一次；
- 位与规范化节点顺序稳定绑定；
- 其他节点全部 BLK。

当前 fixture 应得到 4 个条件。

本步骤只生成组合计划，不计算：

- `H11-H10-H01+H00`；
- interaction residual；
- interaction energy；
- 串扰；
- 分类或判决。

## 9.5 阶段 4

阶段 4 selected nodes 必须从已验证 manifest recommendation / 已解析 ProtocolConfig 派生，development spec 不得覆盖。

生产代码不得硬编码当前推荐节点。

必须验证：

- 恰好 4 个不同节点；
- 与 `binary_node_count=4` 一致；
- 每个节点存在于 manifest；
- 二元状态定义严格有效。

如果协议 `state_labels` 为空，编译器应以明确、版本化、确定性的二进制枚举规则生成全部：

`2^4 = 16`

种组合。

位与 recommended node 顺序必须稳定绑定。

本步骤只生成 16 状态计划，不实现整体分类或多标签恢复。

---

# 10. 层级展开与测量顺序

编译结果至少包含：

- condition matrix；
- session slots；
- reassembly slots；
- condition blocks；
- continuous repeat entries；
- global planned ordinal；
- session-local measurement order；
- reassembly-local condition block order；
- continuous repeat index；
- 完整 NodeState；
- operator confirmation pending 状态。

层级语义必须为：

`session → reassembly → condition block → continuous repeat`

连续重复必须保持在同一 condition block 内相邻，不能把同一安装状态的连续扫频拆散后随机分布。

每个 session 的每个 reassembly 必须包含完整且相同的 condition multiset。

计划总数必须严格等于：

`condition_count × session_count × reassemblies_per_session × continuous_repeats_per_condition`

对于上述 development fixture，测试 oracle 为：

- 阶段 1：`19 × 2 × 2 × 2 = 152`
- 阶段 2：`4 × 2 × 2 × 2 = 32`
- 阶段 3：`4 × 2 × 2 × 2 = 32`
- 阶段 4：`16 × 2 × 2 × 2 = 128`

这些计数只属于 development fixture。

在物化计划前计算总数并与 `max_planned_measurements` 比较。超限必须拒绝，且不得创建父目录、staging、lock 或目标。

---

# 11. 确定性随机化

不要依赖可能随 Python/NumPy 版本变化的隐式全局 PRNG 状态。

实现并版本化一个跨平台确定性 condition-block 排列规则，例如：

`sha256_ranked_condition_blocks_v1`

建议对每个 session/reassembly 的每个 condition 计算 canonical seed material：

- algorithm ID/version；
- random seed；
- protocol ID；
- plan spec ID；
- experiment stage；
- session index；
- reassembly index；
- condition ID。

对 canonical bytes 计算 SHA256，以：

`digest + condition_id`

作为稳定排序键。

要求：

- 同一输入、同一 seed、不同根目录、不同调用顺序：逐字节相同；
- caller 提供的阶段 2/3 selected node 顺序不同，经规范化后结果相同；
- source condition 输入顺序不同不会改变结果；
- 不同 seed 只能改变 condition block 顺序；
- 不同 seed 不得改变 condition multiset、NodeState、重复数或层级；
- development fixture 选取至少两个已知 seed，验证至少一个 reassembly 的条件顺序确实不同；
- randomization false 时保持 canonical 条件顺序且 seed 必须为 null；
- continuous repeats 始终在 condition block 内相邻；
- 保存 randomization algorithm ID、version 和 seed；
- 不把 development seed描述为正式随机种子。

---

# 12. 严格数据模型

至少设计以下严格模型或等价结构：

- `DevelopmentProtocolPlanSpec`
- `LoadedDevelopmentProtocolPlanSpec`
- `CompiledProtocolCondition`
- `PlannedMeasurement`
- `CompiledDevelopmentProtocolPlan`
- `ProtocolPlanReceipt`
- `ProtocolPlanRecord`
- `PublishedDevelopmentProtocolPlan`

要求：

- strict Pydantic；
- extra forbid；
- no NaN/Inf；
- identifier/path 验证；
- aware datetime 仅用于外层 record；
- canonical JSON；
- 自校验计数、顺序、哈希与状态；
- 完整 config/manifest/protocol/spec provenance；
- 编译结果不含本机绝对路径；
- 不含用户名、邮箱、秘密或随机临时目录；
- 不含真实音频设备信息；
- 不含实验结果字段的 truthy 值。

compiled plan 和 receipt 必须显式记录：

- schema version；
- compiler algorithm ID/version；
- plan ID；
- plan spec reference/raw/normalized hashes；
- protocol reference/raw/normalized hashes；
- protocol ID/version/stage；
- manifest reference/hash；
- model package hash或可追溯 bundle 字段；
- bundle content hash；
- condition count；
- planned measurement count；
- session/reassembly/repeat counts；
- randomization enabled/algorithm/seed；
- condition-matrix SHA256；
- schedule SHA256；
- all-node-state completeness；
- operator confirmation required；
- operator confirmation status pending；
- development fixture；
- protocol execution false；
- hardware I/O false；
- formal eligible false；
- experimental result false；
- 固定 safety marker。

建议 safety marker：

`DEVELOPMENT_PROTOCOL_PLAN_NOT_EXECUTED_NOT_AN_EXPERIMENTAL_RESULT`

不得出现：

- PASS/FAIL 实验判决；
- threshold；
- effect size；
- classification；
- drift decision；
- QC decision；
- calibration applied；
- hardware ready。

---

# 13. 不可变计划发布

新增一个只管理 development plan root 的窄存储接口，例如：

`DevelopmentProtocolPlanStore`

它只能接收一个 development plan root，不能选择 real root。

计划路径建议为：

`<development_plan_root>/plans/plan_<plan_id>/`

每个成功计划目录严格包含 7 个文件：

1. `compiled_protocol_plan.json`
2. `compiled_protocol_plan.sha256`
3. `protocol_plan_receipt.json`
4. `protocol_plan_receipt.sha256`
5. `protocol_plan_metadata.json`
6. `protocol_plan_record.json`
7. `PROTOCOL_PLAN_COMPLETE`

要求：

- artifact payload set 必须精确；
- canonical JSON；
- sidecar 必须为精确 ASCII canonical bytes；
- completion marker 必须为固定精确字节；
- create-only；
- 同文件系统 staging；
- 独占 lock；
- 原子 no-replace publish；
- 路径包含关系验证；
- 安全 plan ID；
- 重复发布不得覆盖；
- 并发发布只能有一个成功；
- 失败清理自己的 staging/lock；
- 不清理其他任务文件；
- 发布失败必须明确区分 `published=false/true`；
- 不创建 session、run、event、raw、processed、qc、features 或 models 目录；
- 不创建 real root。

本步骤的 plan artifact 不属于真实 session，因此不伪造 session event。这里“不创建 event”是明确设计边界，不是遗漏。

---

# 14. 只读语义重放验证

validator 必须：

1. 重新读取当前 manifest、protocol、plan spec；
2. 验证原始和规范化来源哈希；
3. 重新编译 condition matrix；
4. 重新执行层级展开和确定性随机化；
5. 重建 canonical plan、receipt、metadata 和 record expected；
6. 验证精确文件集合；
7. 验证 sidecar 和 completion marker；
8. 验证 plan/receipt/record 内部计数和哈希；
9. 逐字节比较确定性产物；
10. 除读取外不得写入任何文件。

必须覆盖攻击：

- source protocol 修改、删除、移动；
- plan spec 修改、删除、移动；
- manifest 或 sidecar 篡改；
- condition matrix 篡改；
- NodeState 缺失、增加或模块替换；
- condition ID/label/role 篡改；
- selected node 篡改；
- measurement order 篡改；
- repeat/session/reassembly 计数篡改；
- random seed/algorithm/order篡改；
- receipt/metadata/record 状态篡改；
- sidecar 非 canonical；
- completion marker 非 canonical；
- 文件缺失或 extra；
- unsafe ID 和路径逃逸；
- duplicate/concurrent publish；
- validator 失败前后树哈希不变；
- 恢复原字节后重新验证通过。

---

# 15. CLI

新增两个清晰命令，例如：

- `protocol-plan-compile`
- `protocol-plan-validate`

CLI 输入只能包含：

- 现有 bundle/config 参数；
- `--plan-spec`
- `--development-plan-root`
- `--plan-id`

不得提供：

- condition；
- node state；
- measurement order；
- permutation；
- waveform；
- metrics；
- threshold；
- decision；
- real root；
- device index；
- Host API；
- channel；
- playback/record/stream 参数。

CLI 成功输出必须从已发布或已验证 receipt 读取真实字段，至少包含：

- plan path；
- plan ID；
- experiment stage；
- condition count；
- planned measurement count；
- session/reassembly/repeat counts；
- randomization algorithm；
- plan SHA256；
- receipt SHA256；
- protocol execution false；
- hardware I/O false；
- formal eligible false；
- experimental result false；
- safety marker。

固定提示至少包括：

- `DEVELOPMENT_PLAN_ONLY`
- `PROTOCOL_NOT_EXECUTED`
- `OPERATOR_CONFIRMATION_PENDING`
- `NO_HARDWARE_AUDIO_IO_PERFORMED`
- `NOT_AN_EXPERIMENTAL_RESULT`

CLI 的 `PASS` 只表示编译/验证成功。

---

# 16. Schema 与文档

至少导出并提交以下活动模型 Schema，名称可以在保持语义清晰的前提下微调：

- `development_protocol_plan_spec.schema.json`
- `compiled_protocol_plan.schema.json`
- `protocol_plan_receipt.schema.json`
- `protocol_plan_record.schema.json`

Schema 必须由活动 Pydantic model 生成，不手工漂移。

更新：

- `README.md`
- `docs/architecture/configuration.md`
- `docs/architecture/storage-layout.md`
- 新增 `docs/architecture/protocol-planning.md`
- 必要的 data README
- `src/acoustic_ladder/config/schema.py`

文档必须明确：

- 当前正式协议仍为 draft；
- 正式 repeats/reassemblies/sessions/seed 未确认；
- development fixture 数值不是实验建议；
- 计划编译不等于协议执行；
- operator confirmation 仍 pending；
- 不访问真实硬件；
- 阶段 2 固定孔径模块只是 proxy；
- 阶段 3 未计算交互残差；
- 阶段 4 未分类；
- plan 不产生实验结论；
- DEV-05.02 尚未实施。

新增：

`docs/reports/DEV-05.01.md`

报告必须记录实际实现、TDD、命令、结果、哈希、限制和未实现内容。

---

# 17. 测试要求

至少覆盖以下公共行为。

## 17.1 条件矩阵

- 阶段 1 当前输入得到 19 条条件；
- baseline 恰好一个且全 BLK；
- 每个非 BLK 状态恰好覆盖所有 manifest 节点；
- 每个单桥条件只有一个 non-BLK；
- 阶段 2 当前 fixture 得到 4 个 proxy 条件；
- 阶段 2 只有选定节点变化；
- 阶段 3 得到 `00/10/01/11` 四组合；
- 阶段 3 位与规范节点顺序稳定绑定；
- 阶段 4 从 manifest recommendation 派生 4 节点、16 组合；
- 阶段 4生产代码不含当前推荐节点常量；
- 每个条件的 NodeState key 与 manifest 节点严格相等；
- 未选节点全部 BLK；
- 未知/重复/错误数量节点拒绝；
- 错误 state definitions、labels、boundaries、max active bridges 拒绝。

## 17.2 层级和随机化

- 四个阶段 development fixture 的总数分别为 152、32、32、128；
- session-local/global ordinal 连续；
- 每个 reassembly 包含完整 condition multiset；
- 每个 condition 连续重复恰好两次且相邻；
- 同 seed 跨根逐字节一致；
- selected node 输入逆序不改变规范结果；
- 不同 seed 只改变 block order；
- randomization false 保持 canonical order；
- seed 缺失/多余拒绝；
- 非法计数、bool 计数、总量溢出和上限超限拒绝；
- 超限在任何计划父目录创建前拒绝。

## 17.3 持久化与验证

- exact 7-file envelope；
- create-only；
- duplicate/concurrency；
- staging/lock cleanup；
- sidecar/completion canonical；
- 全部篡改只读拒绝；
- validator 不写回；
- unsafe IDs/path escape；
- source provenance 重读；
- real root 不存在；
- 不创建 session/run/event；
- 两个独立根逐字节一致。

## 17.4 历史回归

必须保留所有既有测试，不得减少、skip、xfail 或通过类型/检查抑制绕过。

至少运行：

- DEV-05.01 新增目标测试；
- 阶段配置与 manifest 相关测试；
- DEV-04.04 测试；
- DEV-04 全组；
- 完整 pytest；
- locked/golden tests；
- Ruff format check；
- Ruff lint；
- strict mypy；
- Schema export/check；
- `git diff --check`。

Windows 下使用足够短的 pytest `--basetemp`，避免把路径长度错误误报为代码失败。临时根使用前确认目标，使用后按精确 literal path 清理并验证不存在。

测试 expected 必须独立构造，不得调用生产 compiler 生成 expected。

---

# 18. 双根确定性与新 golden

在两个事先不存在的短临时根中分别执行完整公共流程：

1. 加载 V1.3 bundle；
2. 加载四个 development plan specs；
3. 编译阶段 1–4；
4. 发布；
5. 只读 validate；
6. 第二根对可交换的 selected-node 输入顺序进行反转；
7. 对确定性核心产物逐字节比较；
8. 验证 real root、session、run、event 均未创建。

至少固化以下核心产物的 SHA256：

- 每个阶段的 `compiled_protocol_plan.json`
- 每个阶段的 plan sidecar
- 每个阶段的 receipt
- 每个阶段的 receipt sidecar
- 如 metadata 设计为完全确定，也应固化 metadata

新哈希只能在真实双根运行得到后写入测试、报告和日志，不得提前编造。

如果外层 record 含创建时间：

- 测试使用同一固定 aware datetime；
- 生产计划核心 bytes 不得依赖当前时间；
- receipt 不得包含不可复现时间；
- created time 只能存在于明确的外层 record。

---

# 19. 静态与安全扫描

最终检查新增 diff 中不存在：

- `sounddevice` 或其他真实音频调用；
- playback/record/stream 实现；
- 设备枚举；
- real root；
- 硬编码 N1–N6；
- 硬编码阶段四推荐节点；
- 生产代码中的 fixture seed、N2/N5 选择；
- 正式重复次数默认值；
- threshold/decision/classifier；
- 深度学习；
- 本机绝对路径；
- 用户身份或邮箱；
- token、密码或秘密；
- U+FFFD；
- 新的 `noqa`、`type: ignore`、skip、skipif、xfail；
- tracked cache、临时根、lock、staging、WAV、NPZ 或测试产物。

不要把历史文件中已有的合法文本误判为新增问题。扫描应以本步骤新增 diff 或明确文本文件集为边界，并记录真实命令。

---

# 20. 预期文件范围

可根据现有架构小幅调整命名，但预计主要新增：

- `src/acoustic_ladder/protocol/planning.py`
- `src/acoustic_ladder/protocol/planning_models.py`
- `src/acoustic_ladder/protocol/planning_persistence.py`
- development-only stage 1–4 plan spec fixtures
- `tests/dev05/test_protocol_condition_matrix.py`
- `tests/dev05/test_protocol_schedule.py`
- `tests/dev05/test_protocol_plan_persistence.py`
- 对应 generated schemas
- `docs/architecture/protocol-planning.md`
- `docs/prompts/DEV-05.01.md`
- `docs/reports/DEV-05.01.md`

预计修改：

- `src/acoustic_ladder/cli.py`
- `src/acoustic_ladder/config/schema.py`
- `README.md`
- `docs/architecture/configuration.md`
- `docs/architecture/storage-layout.md`
- `docs/IMPLEMENTATION_LOG.md`
- `.gitattributes`

不要为迎合上述列表创建无意义薄包装；优先保持小公共接口和深实现。

禁止修改：

- V1.3 ZIP/manifest 内容；
- 历史 prompt/report；
- 已有 golden payload；
- 正式阶段 1–4 协议中的未知运行参数；
- 真实硬件档案；
- DEV-04 数学与产物格式；
- 既有 synthetic/real 数据边界。

---

# 21. 验收门禁

只有同时满足以下条件才能判定 `PASS`：

1. Git 基线正确且历史未改写；
2. 原始提示词已逐字节归档；
3. implementation log 旧内容保持完整字节前缀；
4. 阶段 1–4 条件矩阵全部通过；
5. 层级展开和确定性随机化全部通过；
6. exact create-only envelope 和只读 replay 通过；
7. 双根核心产物逐字节一致；
8. 不同 seed 只改变顺序；
9. 当前 fixture 数量 19/4/4/16 和 152/32/32/128 正确；
10. 所有 source/plan/tamper/unsafe/concurrency 反例通过；
11. 现有 659 项基线测试全部保留，完整 suite 无失败；
12. Ruff format/lint 通过；
13. strict mypy 通过；
14. Schema export/check 通过；
15. `git diff --check` 通过；
16. 全部历史 protected/golden hashes 保持；
17. 无真实音频设备访问；
18. real root、session、run、event 未创建；
19. 临时根已精确清理；
20. 报告和日志与真实执行一致；
21. 工作区仅包含本步骤预期修改；
22. 最终提交前远端仍以基线 `2affc46…` 为父提交。

任何门禁失败或存在未解决问题时：

- 状态必须为 `FAIL` 或 `BLOCKED`；
- 不得推送；
- 不得把部分成功写成完整 PASS；
- 不得进入下一步骤。

---

# 22. Git 提交与推送规则

所有实现、测试、Schema、文档、报告和日志必须先完成并通过最终门禁。

报告和日志在提交前应如实写：

- 本地软件门禁已通过；
- 最终提交和推送尚未发生；
- commit SHA 不能自引用写入自身；
- 最终 Git 结果由提交后审计和最终回复报告。

然后：

1. 最后一次检查 diff、文件范围、prompt archive 和 log 前缀；
2. 最后一次运行完整门禁；
3. `git fetch origin main`；
4. 确认 `origin/main` 仍是 `2affc46…`；
5. 创建且只创建一个提交：

`DEV-05.01: add deterministic protocol plan compiler`

6. 只执行普通：

`git push origin main`

7. 禁止 force、amend、rebase、历史改写；
8. 推送后重新 fetch，并核对：
   - local HEAD；
   - `origin/main`；
   - GitHub `refs/heads/main`；
   - 三者完全一致；
   - 工作区干净。

推送成功后不得再修改 tracked 文件，也不得为了把 push SHA 写入报告而创建第二个 docs-only 提交。最终提交 SHA 和推送审计只在最终回复中报告；下一步骤的日志基线会自然记录该远端事实。

如果：

- 执行中断；
- 最终门禁失败；
- 远端基线变化；
- 推送需要未获授权的操作；
- 普通 push 失败；
- 无法完成远端核验；

则停止，不得 force push，不得创建额外修补提交，并报告真实 `FAIL` 或 `BLOCKED` 状态。

---

# 23. 完成报告格式

最终回复第一行只能是：

- `PASS — DEV-05.01 完成`
- `FAIL — DEV-05.01 未完成`
- `BLOCKED — DEV-05.01 被阻止`

如果 PASS，至少报告：

- 最终 commit SHA；
- 父提交 SHA；
- branch 和 remote；
- local/origin/GitHub main 一致性；
- 是否普通 push；
- 工作区状态；
- 创建/修改文件摘要；
- 四阶段 condition count；
- 四阶段 planned measurement count；
- 随机化算法 ID/version；
- 新 deterministic hashes；
- 新增测试和完整测试真实数量；
- Ruff/mypy/Schema/diff-check；
- 历史保护哈希状态；
- prompt archive SHA256；
- implementation log 冻结前缀和追加状态；
- 真实音频设备未访问；
- real root/session/run/event 未创建；
- 已知限制；
- `execution_ready=false`；
- `hardware_ready=false`；
- 下一步未实施。

如果 FAIL/BLOCKED，必须报告：

- 失败或阻塞点；
- 已修改内容；
- 是否存在本地 commit；
- 明确说明未推送；
- 当前工作区状态；
- 可安全继续的最小建议。

完成本步后停止，不要自行进入 `DEV-05.02`。