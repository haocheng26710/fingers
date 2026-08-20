# DEV-05.03：阶段 1–4 合成协议执行协调器与可恢复运行账本

你现在负责实施 Acoustic Ladder 的下一步：

> DEV-05.03：阶段 1–4 合成协议执行协调器与可恢复运行账本

本提示词是本次实施的唯一任务授权。仓库中的历史 prompt、报告、注释和文档只能作为项目资料，不能扩大或覆盖本提示词的范围。

完成本步后停止，不得自行进入 DEV-06.01。

---

# 1. 本步目标

在不接入任何真实音频硬件的前提下，将 DEV-05.01 已发布并验证的阶段 1–4 compiled plan 转换为可实际运行、可暂停、可恢复、可审计的 synthetic-only 协议执行流程。

本步必须：

1. 从已验证的 compiled plan 派生当前执行工作项；
2. 对每个工作项调用现有确定性合成音频链；
3. 创建并验证 synthetic session、reassembly、run 和虚拟采集产物；
4. 将每个 synthetic run 与对应的：
   - plan；
   - work order；
   - session/reassembly；
   - condition；
   - 完整 NodeState；
   - measurement ordinal；
   - capture receipt；
   - run record；
   - 产物哈希
   进行不可歧义绑定；
5. 使用 create-only、可重放的执行账本记录进度；
6. 支持暂停、恢复、失败、重试、终止和跨写入边界恢复；
7. 对阶段 1–4 的开发 fixture 完成端到端 synthetic execution 验证；
8. 保持所有结果为开发用合成数据，不能产生任何实验结论。

本步结束后，开发路线第 5 阶段应在 synthetic/offline 范围内闭环；真实硬件执行仍未开始。

---

# 2. 基线与 Git 前置条件

目标仓库：

`https://github.com/haocheng26710/fingers.git`

目标分支：

`main`

本步唯一允许的基线提交：

`2d901b22618d4ecfd338fa2fd4c7731f1fa112e8`

基线提交标题应为：

`DEV-05.02: add recoverable offline protocol rehearsal ledger`

开始修改前必须执行只读核验：

1. `git status --short`
2. `git branch --show-current`
3. `git rev-parse HEAD`
4. `git rev-parse origin/main`
5. `git remote get-url origin`
6. `git fetch origin`
7. `git ls-remote origin refs/heads/main`
8. 检查是否存在 merge、rebase、cherry-pick、revert 等未完成操作。

必须满足：

- 当前分支为 `main`；
- local HEAD、`origin/main`、GitHub main 均为上述基线；
- remote URL 完全正确；
- 工作区干净；
- 没有未完成的 Git 操作。

如任一条件不满足：

- 停止实施；
- 不修改项目文件；
- 不提交；
- 不推送；
- 如实报告实际状态。

禁止通过 merge、rebase、reset、checkout 覆盖、force push 或修改历史来“修复”基线。

---

# 3. 提示词归档与实施日志

## 3.1 提示词归档

在开始源码实现前，将本提示词完整归档为：

`docs/prompts/DEV-05.03.md`

要求：

- 尽可能保存本提示词的原始字节；
- 如果客户端提供本提示词 attachment，优先读取 attachment 原始字节，不要从渲染后的聊天界面重构；
- 不得删节、总结、改写或重新排版；
- 记录实际字节数、换行形式和 SHA256；
- 不得预填或猜测最终哈希。

## 3.2 日志保护

现有日志：

`docs/IMPLEMENTATION_LOG.md`

开始前必须记录：

- 文件当前字节数；
- 完整文件 SHA256；
- 将该完整文件视为本步冻结前缀。

本步只允许在文件末尾追加，不得修改、格式化、移动、删除或重写既有内容。

完成后必须重新验证：

- 原冻结长度以内的所有字节逐字节不变；
- 冻结前缀 SHA256 不变；
- 所有 DEV-05.03 内容只出现在原文件末尾之后。

## 3.3 日志序列

保持现有日志的统一形式，以以下序列号逐项追加真实记录：

- `DEV-05.03-00`：任务授权、Git 基线和冻结前缀
- `DEV-05.03-01`：现有架构、公共接口和数据边界审查
- `DEV-05.03-02`：首个公共行为 RED 与最小 vertical slice
- `DEV-05.03-03`：严格模型、工作项身份和执行状态机
- `DEV-05.03-04`：合成 session/reassembly/run 派生与绑定
- `DEV-05.03-05`：计划绑定的确定性合成采集
- `DEV-05.03-06`：create-only 执行账本与只读重放
- `DEV-05.03-07`：跨账本/采集边界恢复与 exactly-once 语义
- `DEV-05.03-08`：并发、故障注入和篡改测试
- `DEV-05.03-09`：CLI、Schema、架构文档和运行说明
- `DEV-05.03-10`：四阶段端到端执行与确定性证据
- `DEV-05.03-11`：完整回归、静态门禁和保护哈希
- `DEV-05.03-12`：完成报告、最终审计和提交前状态

每条日志必须完全贴合实际执行，至少记录：

- 本项输入和目标；
- 实际读取、创建或修改的文件；
- 实际运行的命令；
- 实际观察到的 RED、错误或限制；
- 实际采取的修复；
- 测试名称和真实结果；
- 关键路径、数据身份和哈希；
- 未执行的操作；
- 当前是否满足进入下一序列的条件。

不得：

- 事后编造 RED；
- 把预期结果写成实际结果；
- 预写最终测试数量、最终 SHA、提交或推送结果；
- 隐瞒失败、重试、环境限制或被中断的命令；
- 在日志中声称接触了实际硬件。

日志详细程度应足以让另一名人员借助其他 AI，尽可能复刻相同实现和验收过程。

---

# 4. 已冻结的研究与安全边界

以下条件不可改变：

- 项目仍为 Acoustic Ladder V1.3 校准后圆形主管版本；
- device manifest 仍是 `provisional`；
- 尚未 geometry-locked；
- 尚未 experiment-ready；
- 正式实验仍固定为 1 个输出和 1 个输入；
- 当前没有接入实际扬声器、麦克风、声卡或声学装置；
- 不知道最终 Host API、输入索引、输出索引和通道映射；
- 不进行真实设备枚举；
- 不连接设备；
- 不播放；
- 不录音；
- 不打开 Stream；
- 不执行麦克风校准文件验证；
- 不执行共享时钟、延迟或全双工硬件验证；
- 不执行绝对 SPL 校准；
- 不执行电气回环；
- 不创建 real session 或 real run。

本步只允许：

- `data_origin=synthetic`
- `run_mode=development`
- 确定性离线 ESS
- 确定性虚拟双工调度
- 根据 manifest 和 plan NodeState 生成的开发用合成 IR
- synthetic session/reassembly/run
- development-only 执行账本

所有新持久化模型、receipt、event、completion 和返回状态必须保持或等价表达：

- `development_synthetic_run=true`
- `data_origin=synthetic`
- `physical_operator_confirmation_performed=false`
- `operator_confirmation_status=pending`
- `formal_protocol_execution_performed=false`
- `measurement_performed=false`
- `hardware_io_performed=false`
- `playback_performed=false`
- `recording_performed=false`
- `hardware_ready=false`
- `full_duplex_verified=false`
- `shared_clock_verified=false`
- `channel_mapping_verified=false`
- `calibration_file_verified=false`
- `calibration_applied=false`
- `absolute_spl_calibrated=false`
- `formal_eligible=false`
- `experimental_result=false`

允许增加明确字段：

`synthetic_capture_performed=true`

但它只能表示开发用合成采集，不能被解释为物理测量或正式协议执行。

必须使用明确 safety marker，例如：

`SYNTHETIC_PROTOCOL_EXECUTION_NOT_AN_EXPERIMENTAL_RESULT`

不得将 DEV-05.02 的 rehearsal completion 解释为：

- 真实物理安装确认；
- 协议执行授权；
- 硬件准备完成；
- 正式实验许可。

DEV-05.02 rehearsal 可作为独立审计资料存在，但本步不得依靠它把任何安全状态改为 true。

---

# 5. 必须读取的项目资料

实施前完整检查与本步有关的现有文件，至少包括：

- `README.md`
- `pyproject.toml`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/architecture/configuration.md`
- `docs/architecture/storage-layout.md`
- `docs/architecture/protocol-planning.md`
- `docs/architecture/protocol-rehearsal.md`
- `docs/architecture/virtual-capture.md`
- `docs/reports/DEV-05.01.md`
- `docs/reports/DEV-05.02.md`
- `docs/prompts/DEV-05.01.md`
- `docs/prompts/DEV-05.02.md`
- `src/acoustic_ladder/protocol/planning.py`
- `src/acoustic_ladder/protocol/planning_models.py`
- `src/acoustic_ladder/protocol/planning_persistence.py`
- `src/acoustic_ladder/protocol/rehearsal.py`
- `src/acoustic_ladder/protocol/rehearsal_models.py`
- `src/acoustic_ladder/audio/virtual_capture.py`
- `src/acoustic_ladder/audio/virtual_capture_models.py`
- `src/acoustic_ladder/audio/virtual_capture_backend.py`
- `src/acoustic_ladder/audio/virtual_capture_persistence.py`
- `src/acoustic_ladder/audio/conditioned_virtual_capture.py`
- `src/acoustic_ladder/audio/conditioned_virtual_capture_models.py`
- `src/acoustic_ladder/audio/excitation_persistence.py`
- `src/acoustic_ladder/synthetic/generator.py`
- `src/acoustic_ladder/storage/store.py`
- `src/acoustic_ladder/storage/io.py`
- `src/acoustic_ladder/domain/models.py`
- `src/acoustic_ladder/cli.py`
- `src/acoustic_ladder/config/schema.py`
- `tests/dev03/`
- `tests/dev04/`
- `tests/dev05/`
- `tests/fixtures/protocol/`
- `tests/fixtures/audio/`

先确认现有公共接口和持久化边界，再决定最小相邻实现。不得复制历史模块形成第二套不兼容的数据系统。

---

# 6. 开发 fixture 的事实边界

当前 DEV-05.01 development fixtures 的派生结果为：

| Stage | condition count | planned work orders |
|---|---:|---:|
| 1 | 19 | 152 |
| 2 | 4 | 32 |
| 3 | 4 | 32 |
| 4 | 16 | 128 |

这些数量必须从当前已验证 compiled plan 派生，不能在生产源码中写死。

当前 development fixture 中的：

- sessions；
- reassemblies；
- continuous repeats；
- randomization seed；
- Stage 2 proxy states

都只是软件验证数据，不是正式实验参数或建议。

阶段语义必须保持：

- Stage 1：全 BLK 基线与单桥位置/孔径条件；
- Stage 2：BLK/B28/B32/B40 仅作为代理离散状态，不能描述为真实连续形变；
- Stage 3：四个二元组合条件，只执行合成采集，不计算交互残差；
- Stage 4：16 个组合条件，只执行合成采集，不执行分类或多标签恢复。

不得修改正式 Stage 1–4 protocol draft 中尚未确认的参数，不得将其改为 `execution_ready=true`。

---

# 7. 推荐模块与公共接口

优先在现有 `acoustic_ladder.protocol` 深模块中扩展，不要把协议执行逻辑堆入 CLI。

预计可以创建或调整：

- `src/acoustic_ladder/protocol/synthetic_execution_models.py`
- `src/acoustic_ladder/protocol/synthetic_execution.py`
- `src/acoustic_ladder/protocol/synthetic_execution_persistence.py`
- 必要时增加一个窄的 plan-bound synthetic capture 模块
- `src/acoustic_ladder/protocol/__init__.py`
- `src/acoustic_ladder/cli.py`
- `src/acoustic_ladder/config/schema.py`
- 对应 Schema
- `tests/dev05/test_synthetic_protocol_execution.py`
- `tests/dev05/test_synthetic_protocol_execution_full.py`

可以根据现有架构调整文件拆分，但必须保持深模块、窄入口和依赖方向清晰。

建议提供等价于以下能力的公共接口：

- `initialize_synthetic_protocol_execution(...)`
- `read_synthetic_protocol_execution_status(...)`
- `execute_next_synthetic_protocol_work_order(...)`
- `apply_synthetic_protocol_execution_control(...)`
- `recover_current_synthetic_protocol_work_order(...)`
- `validate_synthetic_protocol_execution(...)`

接口命名可以按项目现有风格调整。

公共入口不得允许调用者注入：

- NodeState；
- condition ID；
- condition role；
- session/reassembly ordinal；
- measurement ordinal；
- synthetic 或 real origin；
- real root；
- session/run 路径；
- run record；
- receipt 字段；
- artifact 哈希；
- waveform；
- IR；
- gain；
- latency；
-设备名称；
- Host API；
- 输入输出索引；
- 通道映射；
- 硬件准备状态；
- 实验判决。

上述内容必须从：

- replay-validated compiled plan；
- verified V1.3 bundle；
- 已验证 ESS artifact；
- 已验证 synthetic scenario；
- 已验证 synthetic config；
- 执行 ID 和当前游标

派生。

调用者最多可以提供：

- execution ID；
-安全 actor ID；
-完整 concurrency token；
-允许的控制动作；
-加载后且可重新验证来源的 plan/spec/scenario；
-对应 development roots；
-测试可注入的 aware clock。

---

# 8. 工作项、身份和确定性命名

必须从 compiled plan 的：

`session → reassembly → condition block → measurement`

顺序派生执行工作项。

每个工作项至少绑定：

- execution ID；
- plan ID；
- compiled plan SHA256；
- protocol plan receipt SHA256；
- schedule SHA256；
- experiment stage；
- global planned ordinal；
- session index；
- reassembly index；
- condition block order；
- continuous repeat index；
- condition ID；
- condition role；
- condition NodeState SHA256；
- 完整 NodeState map；
- selected nodes/modules；
- operator confirmation requirements；
- plan-derived work-order SHA256。

必须使用确定性 ID 规则生成：

- synthetic session ID；
- reassembly ID；
- run ID；
- capture ID。

ID 必须由 execution ID 和 plan 坐标派生，不能依赖：

- 当前路径；
- PID；
-线程 ID；
-随机 UUID；
-本地用户名；
-机器名；
-临时时间；
-目录枚举顺序。

同一输入、同一 execution ID、同一固定 aware clock 在两个独立根中必须生成逐字节一致的规范化核心产物。

---

# 9. 合成采集执行要求

每个工作项必须使用完整 plan-derived NodeState 生成合成响应。

优先复用：

- 已有离线 ESS artifact；
- `VirtualCaptureEngine`；
- 确定性 block-wise virtual duplex；
- 已有 synthetic generator；
- 已有 conditioned FIR 思路；
- `ImmutableSessionStore`；
- 已有 create-only run publication 和验证能力。

如现有 Stage 1 conditioned capture 接口不能支持 Stage 2–4：

- 提取或增加通用的 plan-bound synthetic capture 能力；
- 不得通过伪造 Stage 1 condition-plan 文件来执行 Stage 2–4；
- 不得让调用者直接提交任意 NodeState；
- 不得破坏或改变已有 Stage 1 conditioned capture 的历史行为和哈希。

每个成功 synthetic run 必须：

- 是 mono `1×1`；
- `data_origin=synthetic`；
- `run_mode=development`；
- 保存原始 output WAV；
- 保存原始 synthetic input WAV；
- 保存原始 float32 身份或等价强校验；
- 保存 capture receipt；
- 保存完整 run record；
- 保存 NodeState 和 condition identity；
- 保存 plan/work-order binding；
- 保存 ESS、scenario、bundle、manifest、protocol、synthetic config 来源哈希；
- 使用 create-only 发布；
- 通过现有和新增 validator；
- 不覆盖已有 run；
- 不写入 real root；
- 不生成实验结论。

不得把 synthetic capture 的成功写成：

- protocol execution performed；
- measurement performed；
- hardware I/O；
- playback；
- recording；
- hardware-ready；
- full-duplex verified；
- formal eligible；
- experimental result。

---

# 10. 执行状态机

实现严格状态机，至少覆盖：

- `active`
- `paused`
- `failed`
- `recovery_required`
- `aborted`
- `complete`

正常执行路径：

`active/current work order → execute-next → synthetic capture validated → success event → cursor +1`

只有经过完整验证的 synthetic capture 才允许推进游标。

控制动作至少包括：

- `pause`
- `resume`
- `retry`
- `abort`

约束：

- paused 状态不能执行下一个工作项；
- failed 状态必须 retry 后才能再次执行同一工作项；
- abort 和 complete 为终态；
- 终态拒绝后续动作且不能写入新事件；
- retry 必须保持同一 work-order identity；
- success 只能推进一个工作项；
- 调用者不能直接提交“成功”事件；
- 调用者不能跳过工作项；
- 调用者不能指定下一 ordinal；
- 不允许从事件文件名或目录顺序推测计划事实。

如果验证当前 plan、source、ledger 或 capture 时发现篡改：

- fail closed；
- 不生成失败事件；
- 不推进游标；
- 不修复；
- 不覆盖；
- 保持读取前后的文件树字节不变。

---

# 11. Create-only 执行账本

执行账本必须位于独立 development root，例如：

`executions/execution_<safe-id>/`

不得与以下根混用：

- plan root；
- rehearsal root；
- synthetic session root；
- real session root。

建议 envelope 至少包含：

- execution manifest JSON 和 sidecar；
- execution record JSON 和 sidecar；
-固定 initialized marker；
- `events/`；
-完成后才出现的 completion JSON、sidecar 和固定 complete marker。

所有 JSON 必须：

- strict model；
- `extra=forbid`；
- `strict=true`；
- `allow_inf_nan=false`；
- canonical JSON；
- SHA256 sidecar；
- create-only；
- 可语义重放。

事件必须：

- 从 1 连续编号；
- 绑定上一 event body SHA256；
- 绑定 execution、plan 和当前 work order；
- 绑定 before/after state 和 cursor；
- 成功时绑定 synthetic session/reassembly/run/capture receipt；
- 记录实际事件类型；
- 使用 aware datetime；
- 保持全部硬件和实验资格字段为 false。

completion 必须绑定：

- execution ID；
- plan/receipt/schedule hashes；
- expected work-order count；
- completed work-order count；
- final event sequence；
- final event SHA256；
- ordered successful-run aggregate；
- ordered event aggregate；
-所有安全 false 状态。

不得创建可被覆盖的 `current.json` 或其他 mutable snapshot 作为事实来源。当前状态必须从 base envelope 和事件重放派生。

允许缓存只读派生结果，但缓存不能成为权威事实，也不得改变验证结果。

---

# 12. 跨执行账本与 synthetic run 的恢复

必须明确处理 synthetic run root 与 execution ledger 不可能跨目录原子提交的问题。

使用确定性 run ID 和验证后采用策略，至少支持以下情况：

1. capture 尚未发布：
   - 正常执行并发布；
2. capture 已完整发布，但成功 event 尚未发布：
   - 只读 status 必须识别为 `recovery_required` 或等价明确状态；
   - 不能静默推进；
   - 显式 recovery 操作重新验证完整 run；
   - 验证通过后发布唯一 success event；
3. capture 仅部分发布：
   - 必须由现有 store 或新边界拒绝；
   - 不得将其视为成功；
4. capture 已存在但身份、plan、condition、NodeState、ordinal 或哈希不匹配：
   - fail closed；
   - 不覆盖；
   - 不采用；
5. success event 已存在：
   - 重复请求不得创建第二个 run 或第二个 success event；
6. ledger success event 存在但引用的 capture 缺失或被篡改：
   - status/validate 必须只读拒绝；
7. 最后一个 success event 已发布但 completion 发布失败：
   - 错误必须如实说明已有发布；
   - 不得回滚已发布 success event；
   - 后续只能通过显式、受验证的 completion recovery 完成；
   - 不得静默 repair。

错误类型应明确区分，例如：

- `capture_published`
- `ledger_event_published`
- `completion_published`

不得只用含糊的单个布尔值掩盖跨根发布状态。

只读入口不得：

- 创建目录；
- 创建 lock；
-删除 staging；
-采用 orphan；
-补写 event；
-补写 completion；
-更新时间；
-执行 synthetic capture。

---

# 13. 并发和 exactly-once 语义

使用完整 concurrency token，至少绑定：

- execution ID；
-当前 event sequence；
-当前 head event SHA256；
-当前 work-order SHA256；
-当前 cursor；
-如存在 recovery target，则绑定确定性 run identity。

transition/execute/recover 必须在独占锁内：

1. 重新验证当前 compiled plan；
2. 重新验证 execution base envelope；
3. 重放完整事件链；
4. 重新验证已引用 synthetic runs；
5. 再比较 token；
6. 最后才允许发布。

必须有真实并发测试证明：

- 两个线程使用同一 token 并发执行同一工作项时，最多只有一个成功；
- 不能创建两个 run；
- 不能创建重复 event sequence；
- loser 必须是 stale/unpublished；
- loser 不能错误地执行下一工作项；
- 并发初始化最多一个成功；
- 并发 recovery 最多一个采用 orphan run。

不得用仅在测试中生效的全局布尔值模拟并发正确性。

---

# 14. CLI

增加窄 CLI，名称可按现有风格调整，至少提供：

- synthetic protocol execution init
- status
- execute-next
- pause
- resume
- retry
- recover-current
- abort
- validate

CLI 必须：

- 显式要求 development execution root；
- 显式要求 synthetic session root；
- 使用已验证 plan/spec/scenario/ESS；
- 一次最多执行一个工作项；
- 输出 execution state、cursor、work-order identity 和安全标志；
- 对 partial publication 如实输出；
- 不提供默认的“执行全部阶段”生产命令；
- 不提供 real root 参数；
- 不提供设备索引、Host API、通道或增益参数；
- 不导入或调用生产 `sounddevice` backend。

以下参数或等价能力必须被 CLI 明确拒绝：

- `--real-root`
- `--device`
- `--input-device`
- `--output-device`
- `--host-api`
- `--input-channel`
- `--output-channel`
- `--play`
- `--record`
- `--stream`
- `--calibration`
- `--spl`
- `--loopback`
-调用者提供的 condition/NodeState/session ordinal/run identity/hash/waveform。

CLI 中的 `PASS` 只能表示：

- development synthetic execution 操作完成；
-或只读完整性验证通过。

不能表示真实协议、真实测量或声学实验通过。

---

# 15. Schema 和模型要求

为所有新增持久化模型导出 Schema。

至少覆盖等价于：

- synthetic execution manifest；
- execution record；
- execution event；
- execution completion；
-必要的 plan-bound synthetic capture receipt。

所有模型必须：

- strict；
-拒绝未知字段；
-拒绝 bool 伪装 int；
-拒绝 NaN/Inf；
-验证安全常量；
-验证 SHA256 格式；
-验证模型内部数量、状态、cursor 和身份关系；
-验证 deterministic ID 与 plan 坐标一致；
-验证 full NodeState map；
-验证 ordered aggregate；
-验证所有 formal/hardware/experimental 状态不能为 true。

如果新增 Schema 导致历史“Schema 数量”断言变化，可以只对机械数量断言进行最小更新并记录原因；不得修改历史 golden、降低历史断言或删除历史 Schema。

---

# 16. 测试要求

使用公共行为的 RED→GREEN→refactor 过程。

每个真实 RED、修复和验证结果必须同步追加到实施日志。不得先写完整实现后编造 RED 过程。

## 16.1 工作项与身份

测试必须证明：

- 工作项完全来自 replay-validated compiled plan；
- Stage 1–4 数量从 fixture 真实派生为 152/32/32/128；
-顺序、session/reassembly boundary 和 continuous-repeat adjacency 与 compiled plan 一致；
- NodeState、condition identity 和 ordinal 不能由调用者替换；
- deterministic IDs 在两个根中一致；
- unsafe execution ID 被拒绝且不创建 root。

## 16.2 代表性阶段行为

至少覆盖：

- Stage 1 全 BLK baseline；
- Stage 1 一个桥条件；
- Stage 2 全部四个 proxy states；
- Stage 3 的 00、10、01、11；
- Stage 4 全 BLK 与多个组合条件；
- Stage 4 全部 16 种 condition identity 的派生检查。

不得把 proxy state 描述为真实连续状态。

## 16.3 状态机

测试：

- init；
- execute-next；
- pause/resume；
-失败/retry；
- abort；
- complete；
-终态拒绝；
- stale token；
- foreign token；
- caller 试图跳 ordinal；
- caller 试图复用旧 work-order；
-非法控制动作前后树字节不变。

## 16.4 合成产物

测试每个成功工作项：

- 仅产生 synthetic session/run；
-完整绑定 plan/work-order/condition/NodeState；
- output/input 形状为 mono 1×N；
- dtype 为 float32；
- WAV、receipt、run record 和 sidecar 均可验证；
- `data_origin=synthetic`；
-所有硬件、正式资格和实验结果状态为 false；
-不存在 real root；
-不存在真实设备 API 调用。

## 16.5 故障恢复

故障注入至少覆盖：

- session 初始化前失败；
- synthetic capture 执行前失败；
- capture staging 失败；
- capture 已发布、ledger event 发布前失败；
- event body/sidecar 中途失败；
- success event 已发布、completion 发布失败；
-显式 recovery；
-重复 recovery；
- recovery 时 capture 被篡改；
- recovery 时 plan 已变化；
- owner staging/lock 精确清理；
-不删除非本任务文件。

必须验证错误中的 publication 状态真实。

## 16.6 并发

真实线程并发测试：

- concurrent init；
- concurrent execute-next；
- concurrent recovery；
-最多一个成功；
-无重复 run；
-无重复 event；
-无跨工作项推进。

## 16.7 篡改和只读性

分别攻击：

- 当前 bundle/manifest；
- protocol source；
- plan spec；
- compiled plan；
- plan receipt；
- execution manifest/record；
- event body/sidecar；
- event missing/extra/reorder；
- run record；
- capture receipt；
- WAV；
- completion；
- marker；
- symlink/junction/reparse point；
- non-file entry；
-绝对路径与目录穿越。

拒绝前后必须证明只读树字节不变。恢复原始字节后应再次验证通过。

## 16.8 硬件隔离

加入 canary，确保所有新增测试和公共 synthetic execution 路径：

- 不枚举设备；
-不调用生产 sounddevice backend；
-不播放；
-不录音；
-不打开 Stream；
-不执行校准、SPL 或 loopback；
-不创建 real root。

扫描新增生产模块，禁止直接 import `sounddevice` 或真实音频 API。

## 16.9 四阶段完整执行

增加独立的最终慢速验收测试：

- 两个预先不存在的独立根；
-相同 V1.3 bundle；
-相同四阶段 development fixtures；
-相同 execution ID；
-相同 scenario/ESS；
-固定 aware clock；
-完整执行 Stage 1–4；
-分别完成 152/32/32/128 个工作项；
-所有 run 和账本均通过只读验证；
-两个根的规范化核心产物和 ordered aggregates 逐字节一致；
-没有 real root、真实设备或实验判决。

测试过程中不得把运行产物加入 Git。

DEV-05.02 已存在的完整双根 rehearsal 慢速测试必须保留并继续通过。不得使用 skip、xfail、marker 排除或减少测试数量来缩短最终门禁。

开发过程中可以分层运行快速测试，但最终提交前必须运行完整 suite。

---

# 17. 已有保护对象

以下历史对象不得改变：

- V1.3 ZIP：
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- audio inventory：
  `8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- capture context：
  `10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- inventory summary：
  `84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：
  `e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：
  `013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`

ESS golden：

- WAV：
  `608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- metadata：
  `e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- raw float32：
  `eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

还必须保持：

- DEV-04 processing/QC/repeatability/baseline-difference golden；
- DEV-05.01 四阶段 plan golden；
- DEV-05.02 四阶段 rehearsal golden；
- DEV-05.02 prompt archive；
-已有事件、receipt 和 Schema 语义。

如果新增实现导致任何历史 golden 不一致：

- 将其视为回归；
-查找真实原因；
-不得更新 golden 来掩盖差异；
-不得降低测试强度。

---

# 18. 静态质量和完整门禁

提交前至少执行并记录：

1. DEV-05.03 新增快速测试；
2. DEV-05 全部测试；
3. DEV-04.04；
4. DEV-04 全部测试；
5. config/manifest 测试；
6. locked/golden selectors；
7.完整 `pytest`；
8. Ruff format check；
9. Ruff lint；
10. strict mypy；
11. Schema export/check；
12. `git diff --check`；
13. suppression 扫描：
    - skip
    - xfail
    - noqa
    - type ignore
    -测试选择性规避
14. U+FFFD 扫描；
15. secret/credential 扫描；
16.本地绝对路径扫描；
17. production `sounddevice`/真实音频 API 扫描；
18.新增/修改文件审计；
19. tracked 临时产物扫描；
20.保护哈希复算；
21. prompt archive SHA256；
22. implementation log 冻结前缀逐字节验证；
23.工作区状态检查。

不得预先规定新增测试最终数量。报告必须写实际收集和通过数量。

如完整门禁未全部通过：

- 不提交；
-不推送；
-保留真实诊断；
-停止并报告。

---

# 19. 文档与报告

创建：

`docs/reports/DEV-05.03.md`

更新必要的：

- `README.md`
- `docs/architecture/protocol-synthetic-execution.md`
- `docs/architecture/storage-layout.md`
- `docs/architecture/protocol-planning.md`
- `docs/IMPLEMENTATION_LOG.md`

报告至少说明：

-实现范围；
-公共接口；
-工作项派生；
-确定性 ID；
-状态机；
-create-only ledger；
-跨 capture/ledger 恢复；
-concurrency；
-四阶段实际工作项数量；
-代表性和完整测试；
-真实 RED/GREEN 过程；
-静态门禁；
-保护哈希；
-已知限制；
-未访问硬件的证据；
-未实施 DEV-06.01；
-提交前 Git 状态。

报告不得：

-把 synthetic execution 称为正式 protocol execution；
-把 synthetic WAV 称为麦克风录音；
-把虚拟 full duplex 称为真实 full-duplex verified；
-声称验证了真实声学可分性；
-声称获得实验结果；
-预写最终 commit SHA 或 push 成功。

最终 commit SHA 和远程验证只在推送后的最终回复中报告，不能为了写入 SHA 再创建第二个提交。

---

# 20. 禁止范围

本步禁止：

-真实设备枚举；
-设备选择或绑定；
-真实播放、录音或 Stream；
-麦克风校准文件应用；
-绝对 SPL；
-共享时钟、硬件延迟和 loopback 验证；
-real session/run；
-修改正式协议为 execution-ready；
-填写尚未知的正式 repeats/reassemblies/sessions/seed；
-将 Stage 2 proxy 描述为真实变形；
-Stage 3 interaction residual；
-Stage 4 分类或多标签模型；
-baseline 选择规则变更；
-正式 QC threshold/pass-fail；
-特征工程；
-分类器；
-交叉验证；
-UI；
-数据库；
-CAD 或 STL 修改；
-几何锁定；
-experiment-ready 状态；
-DEV-06.01 或后续功能。

---

# 21. 提交与推送规则

只有以下条件全部满足时才允许提交和推送：

- 本提示词全部授权内容完成；
-所有新增和历史测试通过；
-完整 suite 通过；
-静态门禁全部通过；
-保护哈希全部一致；
-日志冻结前缀逐字节一致；
-工作区不存在任务临时产物；
-报告和日志真实完整；
-未访问真实硬件；
-remote main 仍处于本步基线；
-没有未解决问题或中断步骤。

提交前再次执行：

- `git fetch origin`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `git ls-remote origin refs/heads/main`

如果远程已移动：

- 停止；
-不 merge；
-不 rebase；
-不 cherry-pick；
-不提交；
-不推送；
-报告远程变化。

所有门禁通过后只创建一个普通提交，建议提交信息：

`DEV-05.03: add recoverable synthetic protocol execution`

然后执行普通：

`git push origin main`

禁止：

- force push；
- `--force-with-lease`；
-amend；
-rebase；
-改写历史；
-第二个 docs-only 提交。

推送成功后验证：

- local HEAD；
- `origin/main`；
- GitHub main；
-三者 SHA 完全一致；
-工作区干净。

推送成功后不得再修改 tracked 文件。

如果 push 失败：

-不得 force；
-不得掩盖失败；
-不得把“准备推送”写成“推送成功”；
-如实报告本地提交、远程状态和错误；
-停止等待用户处理。

如果实施因任何原因未完成或中断：

-不得提交半成品；
-不得推送；
-如实报告最后完成的日志序列和阻塞点。

---

# 22. 最终回复格式

最终回复必须首先输出：

`PASS — DEV-05.03 完成`

或：

`FAIL — DEV-05.03 未完成`

若 PASS，至少报告：

- commit SHA；
- parent SHA；
- branch 和 remote；
-普通非 force push 结果；
-local/origin/GitHub main 一致性；
-工作区状态；
-新增测试数量；
-完整测试数量；
-Ruff/mypy/Schema/diff 门禁；
-Stage 1–4 实际工作项和成功 run 数；
-四阶段确定性执行结果；
-执行账本和 capture 关键哈希；
-prompt SHA256；
-implementation log 冻结前缀验证；
-全部保护哈希；
-真实硬件操作均未发生；
-已知限制；
-DEV-06.01 未实施。

若 FAIL，至少报告：

-完成到哪个日志序列；
-实际失败命令；
-错误信息；
-是否存在已发布 synthetic run、event 或 completion；
-是否创建本地提交；
-确认没有推送；
-需要的修复或用户决策。

完成 DEV-05.03 后立即停止，不得自行进入 DEV-06.01。