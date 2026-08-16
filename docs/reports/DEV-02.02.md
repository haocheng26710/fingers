# DEV-02.02 完成报告

## 结果

DEV-02.02 已在基线 `d767c31be682197a6cd09811dc0d6570577950e1` 上完成本地修复和验收，状态 `PASSED`。修复范围仅限不可变事件写入边界、直接调用方、回归测试和受影响文档；没有进入 DEV-03.01，也没有访问音频设备或实现音频、DSP、协议矩阵及几何锁定功能。

Git 目标为 `https://github.com/haocheng26710/fingers.git` 的 `main`，计划提交主题为 `DEV-02.02: confine immutable event writes`。本文档冻结时尚未创建提交，因此不编造提交 SHA；实际提交和远端一致性由 Git 历史及最终回复报告。

## 缺陷复现与根因

在未修改基线上，以临时目录分别配置 synthetic/real 根，然后调用旧接口 `store.append_event(outside, "boundary_probe", ...)`。调用成功，并在两个根之外真实创建 `outside/events/000001_boundary_probe.json`：

- `outside_event_exists=True`
- `outside_roots=True`

复现目录随后由临时目录清理。根因是公开 API 直接信任调用者提供的 `session: Path`，并基于该路径创建 `events/`；它没有从 DataRoots 推导 session，没有验证完成标记和 SessionRecord 身份，也没有验证事件名或保护系统字段。

新增回归文件先在旧实现上运行，结果为 `22 failed in 1.95s`：21 项因受约束 API 尚不存在而失败，`create_run` 用例则证明旧事件没有系统 `sequence`。这建立了确定、快速且直接覆盖真实文件系统的红灯反馈环。

## API 修正

公开入口现为：

```python
append_event(origin: DataOrigin, session_id: str, event: str, payload: dict[str, object])
```

调用者不再能传入 session 文件系统路径。实现会：

1. 使用 `session_path(origin, session_id)` 从已注入的根推导并解析 session；
2. 用 `Path.is_relative_to()` 验证解析后路径位于选定根内，不使用字符串前缀；
3. 验证 session 目录和 `SESSION_COMPLETE`；
4. 严格解析 `session_record.json`，验证 session_id 和 data_origin；
5. 解析并验证 `events/` 同时位于 session 和选定根内；
6. 只接受 `[A-Za-z0-9_-]+` 事件名；
7. 拒绝 payload 中的 `event`、`sequence`、`session_id`、`data_origin`；
8. 生成这些系统字段后，通过原有同目录临时文件、fsync 和 create-only hard-link 原子发布事件。

`create_run()` 现在只能以 run 的 DataOrigin/session_id 调用该受约束入口。扫描和编号仍连续；若扫描后发生竞争，create-only 发布会拒绝冲突，绝不会替换竞争者事件。

## 测试与真实文件系统结果

新增 `tests/dev02/test_event_boundaries.py`，最终包含 23 个 pytest item，覆盖：

- synthetic/real 外部绝对 session 标识拒绝且无目录、events 或事件残留；
- synthetic 与 real 同 ID session 的事件不串根；
- 缺少完成标记拒绝；
- SessionRecord origin/session_id 不一致拒绝；
- 空、`.`、`..`、遍历、正反斜杠、冒号、绝对/盘符和非 ASCII 事件名拒绝；
- 四个保留字段覆盖拒绝；
- 合法事件连续编号，旧事件字节不变；
- 注入编号竞争时旧/竞争事件不被覆盖且无临时文件残留；
- `create_run()` 生成受约束的 `000003_run_created.json`。

第一轮完整验收（新增 Unicode 用例前）真实结果：

- DEV-01 原测试：`43 passed in 0.47s`
- DEV-02.01 原测试：`66 passed in 1.39s`
- DEV-02.02 回归：`22 passed in 1.69s`
- 全量：`131 passed in 3.34s`
- format：`51 files already formatted`
- Ruff：`All checks passed!`
- strict mypy：`Success: no issues found in 37 source files`
- Schema 一致性：PASS
- `git diff --check`：PASS
- skip/xfail/noqa/type-ignore 扫描：无匹配

最终关门结果：DEV-01 `43 passed in 0.46s`；DEV-02.01 `66 passed in 1.51s`；DEV-02.02 `23 passed in 1.78s`；完整套件 `132 passed in 3.36s`。format 为 `52 files already formatted`；Ruff、strict mypy（37 source files）、Schema、diff whitespace 和抑制扫描全部 PASS。

## CLI 烟雾与修正后反例

在系统临时目录实际执行：

1. `create-synthetic-session`
2. `generate-synthetic-run`
3. `validate-session`
4. `validate-run`

四步均 PASS。真实 `000003_run_created.json` 位于 synthetic session，包含 `event=run_created`、`sequence=3`、`session_id=smoke001`、`data_origin=synthetic` 和 `run_id=run001`。路径经过解析核对后，临时烟雾目录已删除，`Test-Path=False`。

修正后的独立临时目录反例把外部绝对路径作为 session_id 传给新 API，结果：

- `rejected=True`
- 错误为 `session_id contains unsafe characters`
- `outside_exists=False`
- `outside_event_exists=False`

## 历史产物回归

相对基线对十二个历史受保护文件执行 `git diff --exit-code`，无差异。关键 SHA256 保持：

- V1.3 ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- DEV-02.01 prompt：`e37580cef7420d9782fd40ad60623c8c0c4b4bec219c62890a6b9a351ab35b49`
- DEV-02.01 report：`64e140ec108e9c6ab343e2f0b8001f04ba64ee4cf0fad43fb3360ba2ecb3e3a8`

其余 DEV-01 文件哈希与 DEV-02.01 完成报告记录一致。`docs/IMPLEMENTATION_LOG.md` 的 diff 只有末尾新增 DEV-02.02 区块，历史 DEV-01.01/DEV-02.01 内容未变。

## 实际命令

主要实际命令如下；完整参数和首次失败已同时记录在实施日志：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git remote -v
git status --short --branch
git ls-remote --heads origin main
Get-FileHash -Algorithm SHA256 -LiteralPath <protected-files>
uv --cache-dir .uv-cache run python -c '<old external-root counterexample>'
uv --cache-dir .uv-cache run pytest tests/dev02/test_event_boundaries.py -q
uv --cache-dir .uv-cache run pytest tests/dev02/test_storage.py -q
uv --cache-dir .uv-cache run ruff format <changed-python-files>
uv --cache-dir .uv-cache run ruff check <changed-python-files>
uv --cache-dir .uv-cache run mypy <changed-python-files>
uv --cache-dir .uv-cache run pytest tests/unit tests/integration -q
uv --cache-dir .uv-cache run pytest <four-original-dev02-test-files> -q
uv --cache-dir .uv-cache run pytest tests/dev02/test_event_boundaries.py -q
uv --cache-dir .uv-cache run pytest -q
uv --cache-dir .uv-cache run ruff format --check .
uv --cache-dir .uv-cache run ruff check .
uv --cache-dir .uv-cache run mypy
uv --cache-dir .uv-cache run acoustic-ladder export-schemas --output-dir schemas --check
git diff --check
rg -n "pytest\.mark\.(skip|xfail)|@unittest\.skip|#\s*(type:\s*ignore|noqa)" src tests
uv --cache-dir .uv-cache run acoustic-ladder create-synthetic-session <smoke-args>
uv --cache-dir .uv-cache run acoustic-ladder generate-synthetic-run <smoke-args>
uv --cache-dir .uv-cache run acoustic-ladder validate-session <smoke-args>
uv --cache-dir .uv-cache run acoustic-ladder validate-run <smoke-args>
uv --cache-dir .uv-cache run python -c '<fixed external-root counterexample>'
git diff --exit-code d767c31... -- <protected-files>
```

## 修改文件与限制

修改 `.gitattributes`、README、`docs/IMPLEMENTATION_LOG.md`、`docs/architecture/storage-layout.md`、`src/acoustic_ladder/storage/store.py`、`tests/dev02/test_storage.py`；新增 prompt、本文档和 `tests/dev02/test_event_boundaries.py`。

已知限制不变：文件事件序号不是数据库事务或跨进程锁；并发者可能有一个因 create-only 冲突而失败，但旧事件不会被覆盖。不可变 session record 仍通过 append-only run/event 表达后续变化。当前 manifest 仍 provisional；本修正不证明真实声学有效性，也不新增任何音频能力。
