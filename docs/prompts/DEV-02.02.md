# DEV-02.02：不可变事件存储的根目录约束修正

你现在负责修正 Acoustic Ladder 项目 DEV-02.01 中已确认的存储边界缺陷。

本步骤仅修复事件写入的路径约束及直接相关测试，不进入 DEV-03.01，不实现任何真实音频功能。

## 1. 基线

仓库：

https://github.com/haocheng26710/fingers.git

分支：

main

本步骤必须基于提交：

d767c31be682197a6cd09811dc0d6570577950e1

开始前必须确认：

- 当前分支为 main；
- 本地 HEAD、origin/main 和上述提交一致；
- 工作区干净；
- 远程地址正确；
- 没有需要优先遵守但尚未读取的项目级指令文件。

如果基线不一致，立即停止，不得修改或推送。

## 2. 已确认缺陷

DEV-02.01 的 `ImmutableSessionStore.append_event()` 接受调用者直接提供的任意 `session: Path`。

已通过独立反例确认：

- 为 store 配置互不重叠的 synthetic/real 根目录；
- 将两个根目录之外的路径传给 `append_event()`；
- 当前实现会在该外部路径创建：
  `events/000001_boundary_probe.json`；
- 调用成功且文件真实存在。

这违反 DEV-02.01 的以下要求：

- 所有写入必须限制在指定数据根目录内；
- synthetic 与 real 必须强隔离；
- 路径逃逸必须拒绝；
- 事件文件必须不可覆盖；
- 持久化接口不得信任调用者提供的任意本机路径。

该问题必须通过 API 约束修复，不能只在 CLI 层规避，也不能只增加文档警告。

## 3. 修正要求

### 3.1 重构事件写入入口

公开事件写入接口不得再接受任意 session 文件系统路径。

推荐形式：

- 接收 `DataOrigin`；
- 接收 `session_id`；
- 通过 `ImmutableSessionStore.session_path()` 从已注入的 DataRoots 推导 session；
- 验证 session 位于对应 synthetic/real 根目录内；
- 验证 session 已完成；
- 验证 `session_record.json` 中的 session_id 和 data_origin 与调用参数一致；
- 然后才能写入 `events/`。

可以使用等价设计，但必须从结构上保证调用者无法选择两个已配置数据根之外的写入位置。

不要以字符串前缀比较代替解析后的路径包含关系。

### 3.2 事件名称安全

事件名称将进入文件名，因此必须：

- 非空；
- 不能为 `.` 或 `..`；
- 只允许稳定、安全的 ASCII 标识字符，例如字母、数字、连字符和下划线；
- 拒绝 `/`、`\`、冒号、绝对路径、盘符、父级遍历和其他路径分隔形式；
- 不允许事件 payload 覆盖系统生成的 `event` 字段。

如果准备加入 `sequence`、`session_id` 等系统字段，也必须防止 payload 覆盖这些保留字段。

### 3.3 事件不可变性

继续保持：

- 连续编号事件文件；
- create-only；
- 已存在文件不得替换；
- 使用同文件系统临时文件及原子发布；
- 竞争或编号冲突不得覆盖旧事件；
- 任何拒绝操作不得在目标根之外留下目录或文件。

更新 `create_run()`，使其只能通过新的受约束事件接口记录 `run_created`。

### 3.4 路径约束复核

同时复核本次涉及的事件路径构造，确保：

- synthetic 事件只能进入 synthetic 根；
- real 事件只能进入 real 根；
- session_id 仍通过安全标识校验；
- 缺少 `SESSION_COMPLETE` 的 session 不能追加正式事件；
- session record 身份不一致时拒绝；
- 不接受调用者提供的任意绝对 session 路径。

不要借本步骤重写整个存储系统。

## 4. 必须新增的回归测试

至少增加以下测试：

1. 向 synthetic/real 根之外追加事件时抛出 `StorageError`；
2. 上述失败后，外部目标目录和事件文件均不存在；
3. synthetic 事件只出现在 synthetic session；
4. real 事件只出现在 real session；
5. 缺少完成标记的 session 被拒绝；
6. session record 的 data_origin 不一致时被拒绝；
7. session record 的 session_id 不一致时被拒绝；
8. `../escape`、`a/b`、`a\b`、空字符串、`.`、`..` 等事件名称被拒绝；
9. payload 试图覆盖 `event` 等保留字段时被拒绝；
10. 合法事件仍按连续编号创建；
11. 已有事件内容保持字节不变；
12. synthetic session/run CLI 的完整流程仍然通过；
13. `create_run()` 仍能正确生成受约束的 `run_created` 事件；
14. 原有 109 项测试全部继续通过。

测试必须验证真实文件系统结果，不能只断言辅助函数返回值。

不得添加 skip、xfail、noqa 或 type ignore 来绕过问题。

## 5. 不得修改的历史产物

以下内容必须保持字节不变：

- DEV-01.01 要求保护的十个文件；
- `docs/prompts/DEV-01.01.md`
- `docs/reports/DEV-01.01.md`
- `docs/prompts/DEV-02.01.md`
- `docs/reports/DEV-02.01.md`
- `docs/IMPLEMENTATION_LOG.md` 中已有的 DEV-01.01、DEV-02.01 内容。

其中：

- ZIP SHA256 必须仍为  
  `1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest SHA256 必须仍为  
  `bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`

日志只能在文件末尾追加 DEV-02.02。

## 6. 文档与可复刻日志

原样保存本提示词为：

`docs/prompts/DEV-02.02.md`

创建：

`docs/reports/DEV-02.02.md`

如事件 API 或存储契约发生变化，应同步更新：

- `docs/architecture/storage-layout.md`
- README 中受影响的调用示例

向 `docs/IMPLEMENTATION_LOG.md` 末尾追加 `DEV-02.02`，至少真实记录：

- 序列号和步骤名称；
- 基线提交；
- 缺陷的实际复现方式和复现结果；
- 根因；
- API 修改；
- 新增和修改文件；
- 实际运行的全部命令；
- 修正前失败测试和修正后结果；
- 原有测试与新增测试数量；
- 静态检查结果；
- 受保护文件回归结果；
- 未执行检查及原因；
- Git 提交和推送结果。

只能记录实际发生的内容，不能补写、猜测或美化未执行过程。

## 7. 验收命令

至少实际运行：

- 原有 DEV-01 测试；
- 原有 DEV-02 测试；
- 新增 DEV-02.02 回归测试；
- 完整 pytest；
- Ruff format check；
- Ruff lint；
- strict mypy；
- Schema 一致性检查；
- `git diff --check`；
- skip/xfail/noqa/type-ignore 扫描；
- 受保护文件 diff 与 SHA256 检查；
- synthetic session → run → validate-session → validate-run 的真实临时目录烟雾测试；
- 修正后的外部根目录写入反例，确认现在被拒绝且没有残留文件。

所有测试必须真实通过。

## 8. Git 门禁

只有全部验收通过后才允许提交并推送。

建议提交信息：

DEV-02.02: confine immutable event writes

推送到：

- remote：`https://github.com/haocheng26710/fingers.git`
- branch：`main`

推送后必须确认：

- 本地 HEAD、origin/main 和远程 main 完全一致；
- 工作区干净；
- 提交确实包含 DEV-02.02；
- 没有临时数据、测试输出、缓存、虚拟环境或秘密被提交。

禁止 force push。

如果中途失败、中断、测试不完整、远程发生冲突或无法验证推送结果：

- 不得推送；
- 不得声称 PASSED；
- 日志如实标记失败或中断；
- 报告具体阻塞点。

## 9. 完成边界

完成 DEV-02.02 后立即停止。

不得自行进入 DEV-03.01，不得枚举或访问真实音频设备，不得实现 ESS、采集、校准、DSP、协议矩阵或几何锁定。

最终回复必须报告：

- PASS/FAIL；
- 提交 SHA；
- 本地与远程一致性；
- 完整测试数量；
- 新增回归测试数量；
- 外部根目录写入反例是否已被拒绝；
- ZIP/manifest 哈希；
- 工作区是否干净；
- 主要修改文件；
- 已知限制。
