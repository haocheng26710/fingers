# DEV-04.01R 实施报告：处理产物规范性、防篡改绑定与独立 Oracle 闭环

## 结论与范围

- 软件实现与提交前验收：`PASS`；Git 提交和推送在本报告冻结时尚未执行，最终结果以 Git 历史与最终回复为准。
- 基线：`main`；本地 HEAD、`origin/main`、GitHub `main` 均为 `078c7257a588f3621d388ea81dd6e6a7f4c4265e`；remote 为 `https://github.com/haocheng26710/fingers.git`；开始时工作区干净。
- 原 DEV-04.01：`61 passed`；DEV-04.01R 新增：`30 passed`；完整套件：`460 passed`，原有 430 项无减少。
- 范围严格限于 synthetic offline ESS processing 的规范字节、事件审计绑定和公共数学流水线 oracle。没有进入 DEV-04.02，没有连接、枚举、选择、绑定、播放、录制或打开任何真实音频设备/流，没有读取或应用校准。

## 提示词、日志和历史保护

附件以原始 CRLF 字节归档为 `docs/prompts/DEV-04.01R.md` 并标记 binary。源与归档均为 17311 bytes、401 个 CRLF、无结尾换行，SHA256 均为 `fba5d19ee17e46715c8f51e8f466b1d96dac2d6e8b03d180368b310a1dc0f07a`。

`docs/IMPLEMENTATION_LOG.md` 追加前为 86232 bytes，SHA256 `558f2ad796c1603e9e7b2510508c090531dc5476b0445f9e7c34406012240afa`。验收时重新提取前 86232 bytes，SHA256 完全一致。`docs/prompts/DEV-04.01.md`、`docs/reports/DEV-04.01.md`、配置、fixtures、reference 与 V1.3 源包相对基线均无 diff。

## TDD RED 证据

生产修正前新增真实临时文件系统攻击：arrays sidecar 额外换行、receipt sidecar 尾随空格、LF→CRLF、完成标记内容替换、processing record aware datetime 规范篡改、processing event 删除、record hash/receipt hash/event timestamp 篡改、同 identity 重复事件。

首次攻击组实际为 `10 failed, 1 passed, 33 deselected`。唯一 pass 不是基线安全行为，而是测试最初把 `+00:00` 字符串直接写入 strict model，Pydantic 规范重序列化会使用另一时间表示，现有 canonicality 检查先拒绝。攻击构造改为先经 `ProcessingRecord.model_validate_json()` 再 canonical 序列化后，测试得到预期 `DID NOT RAISE` RED，证明 validator 使用 record 自身时间构造 expected record 的自我验证缺陷。

规范字节与事件最小修正后，原始攻击组为 `11 passed, 33 deselected in 3.99s`。随后扩展重复记录、错误文件名、非 ASCII、缺失/目录 sidecar、目录完成标记、event identity/extra/canonical/filename sequence、append failure 和双 processing 区分，最终 DEV-04.01R 30 项全部通过。所有拒绝测试保存攻击后的文件树字节并验证 validator 没有写回、修复或删除。

## 规范字节修正

`_verify_sidecar` 计算目标真实 SHA256 后，把 sidecar 的原始 bytes 与 `_sidecar(digest, filename)` 逐字节比较；不再使用 `.split()`、`.strip()` 或文本空白归一化。额外空格/空行、CRLF、重复记录、错误文件名、非 ASCII、缺失和目录替代均拒绝。

processing 目录仍严格只有原七文件。`PROCESSING_COMPLETE` 必须是普通可读文件且 bytes 精确等于 `b"complete\n"`。validator 保持只读。

## ProcessingRecord 独立审计绑定

新增 strict、`extra="forbid"` 的 `ProcessingCreatedEvent`。七文件 processing 目录完成 create-only 发布后，publisher 通过既有根约束接口：

```text
append_event(DataOrigin.SYNTHETIC, session_id, "processing_created", payload)
```

追加 canonical session event。payload 绑定 `schema_version`、`processing_id`、`source_run_id`、`created_at`、实际 canonical `processing_record.json` bytes 的 SHA256 和 processing receipt SHA256。通用 store API、安全事件名、保留字段和 synthetic/real 根边界均未修改。

事件追加失败包装为 `EssProcessingPersistenceError(..., published=true)`；已经发布的 immutable processing 不删除，调用不声称整体成功。回归测试注入 append failure，确认七文件目录保留、事件不存在、异常明确为 `published=true`。

validator 在 session 的其他合法事件和其他 processing 事件之间寻找唯一匹配 identity，验证 canonical JSON、文件名和 JSON sequence、event/session/origin、strict payload、record/receipt hashes 与时间。expected record 时间来自独立事件，不来自被验证 record 自身。缺失、重复、非规范、字段或 identity 篡改均拒绝；两个合法 processing event 可分别验证。无事件的旧 DEV-04.01 临时 processing 不走 legacy bypass，必须重新生成。

该机制只提供项目内部完整性与审计绑定。它没有数字签名、外部只读见证日志或可信时间戳，不能抵御恶意参与者协调改写 processing 与 event 的所有绑定字节；不得称为密码学不可篡改或密码学真实性。

## 独立数学 Oracle 与授权修正

三个测试均通过 public `process_ess_waveforms()`，没有 expected/truth 参数。

1. Identity：`captured == reference`。首次 RED 中 lag、raw IR peak 和 correlation 正确，但 production transfer 的 500–8000 Hz magnitude 为 `1.7960754654588951..1.9967704334738352`，phase absolute max 为 `0.45225886895605577 rad`，明显不满足 unity/zero-phase。
2. Multi-tap：测试用独立 `np.convolve` 构造 `h[7]=+0.25`、`h[23]=-0.10`。首次实际 lag/peak/sign 正确，taps 为 `0.24850389176540777`、`-0.096277175897485412`，ratio `-0.38742723590169298`。偏差来自有限长度 ESS inverse reference 峰前/峰后旁瓣交叉贡献。最终 expected 在测试内用显式 inverse 公式和独立时域 `np.convolve` 计算，production taps 与独立 expected 的 absolute tolerance 为 `1e-10`；该容差是 float64 development 数值回归，不是声学 QC 阈值。
3. Polarity：`captured == -reference`，lag 0、signed correlation -1、absolute correlation 1、raw IR peak -1，极性未被绝对值吞掉。

根因是旧 transfer 对从 reference peak 开始截断的 `ir_raw` 直接 FFT，保留有限 inverse 的 reference 旁瓣频响。只读最小化证明同 FFT 长度的 input/reference deconvolution 比可把 identity magnitude max error 降为 `1.1102230246251565e-16`、phase absolute max 降为 `7.6547552663460845e-17`。

这一修正必然改变 transfer/magnitude/phase arrays 和 deterministic hashes，实施按提示词停止。用户随后明确回复“确认”，授权最小数学修正和新 golden。最终 raw transfer 使用 input-after-pre/output-after-pre 的复频谱比；aligned transfer 使用零填充前移后的 input 与同一 reference 比。只在 reference spectrum 大于 `max(abs(reference_spectrum)) * float64_eps * reference_sample_count` 的 bins 做除法。ESS inverse、完整 deconvolution、latency、raw/aligned IR、21 数组名称/shape 和七文件集合均未改变。修正后三个 oracle 为 `3 passed`。

## 双根重放、哈希与攻击复验

两个预先不存在的隔离临时根分别执行：ESS generate/validate → synthetic session create/validate → virtual capture publish/validate → processing publish/validate。固定身份为 `source_ess/dev0401/assembly001/capture001/processing001/order0`，真实结果：

```text
estimated latency = 37 samples
raw IR peak index = 37
raw IR peak value = 0.4999999999999999
```

两根五类 payload 逐字节一致。经用户授权后的 DEV-04.01R golden：

- arrays：`e15435561f404813a46b9558197b76e5ed6e1746fed394225fd1758a3dc4fa89`
- arrays sidecar：`f9867a44d0573cd60ce2a42c7a8f279210e1a6c1cf18bcf6c87f5d0d958ba902`
- receipt：`6f67bacb552cd5544ae1d6f38a0926c4af80e4616998cbf3216e18d1697d5446`
- receipt sidecar：`45506eec1c9df45ea1061c8df359e89d3a8d2402f94a7ec5154b6dabb9bb25a8`
- metadata：`d10c01d1688070b991518f0db02e17ec0833431943d70578e5f53107a83508af`

每根均有唯一 record/receipt hash-bound event，real root 未创建。对第一根现场执行 arrays sidecar、receipt sidecar、completion、record created_at 和 event record hash 篡改，全部拒绝；每次 validator 前后被测文件 SHA256 分别相同：

- arrays sidecar attack：`9369c3ee5e16c343230cb6a6944cab2a7fab9e40bd5a174ea2a49398dbf42144`
- receipt sidecar attack：`09c351e1e2e9ec14ecf4e8d0c8b8e2ac29e9f2f87965b5805037a6ace62fd562`
- completion attack：`92e78d0b032962f47792a9fa95fd981ef63e1e3ef074d536d6304c75eddbe29f`
- record time attack：`ba759f5326a8e3303f064ecf9668c9992631be92d1156d7566e0487262a42ea7`
- event record-hash attack：`d21004853de0cb563d8de2ade2369f30fafdaa3fbd6bc399666829604fae0308`

脚本只删除自己创建的两个根及其共同临时父目录，最终三者均不存在。没有发布到项目数据根，也不存在本步骤留下的“已发布但缺少 event”的 synthetic processing。

## 测试、静态检查与扫描

- 开始基线：DEV-04 `61 passed in 7.75s`；完整 `430 passed in 21.75s`。首次无 `--cache-dir` 的 `uv run` 因默认缓存初始化 os error 183，未进入 pytest；随后统一使用仓库 `.uv-cache`。
- 原 DEV-04.01：`61 passed, 30 deselected in 7.72s`。
- DEV-04.01R：`30 passed, 61 deselected in 10.06s`。
- DEV-04 合计：`91 passed in 17.35s`。
- 完整 suite：`460 passed in 30.33s`。
- Ruff format：`102 files already formatted`。
- Ruff lint：`All checks passed!`。
- strict mypy：`Success: no issues found in 67 source files`。
- Schema：18 个注册生成 Schema consistency `PASS`；目录另含历史手工 `device_manifest.schema.json`，合计 19 个文件，本步骤没有 Schema 变化。
- `git diff --check`：PASS。
- suppression、U+FFFD、本机绝对路径/用户身份、新真实音频 API/`sounddevice`/Stream/play/rec 扫描：0 matches。
- tracked WAV/FLAC/NPY/NPZ：0；tracked cache/staging/lock：排除合法依赖锁 `uv.lock` 后 0。

实际主要命令包括：Git status/branch/HEAD/origin/remote/root、`git ls-remote origin refs/heads/main`、项目指令扫描；提示词/TDD skill/源码/测试/架构读取；prompt/log bytes/CRLF/SHA；多轮目标 pytest；`uv --cache-dir .uv-cache run pytest tests/dev04 ...`；完整 pytest；Ruff format/check；strict mypy；Schema check；`git diff --check`；上述安全扫描、保护 hash/diff/log-prefix；两个独立 Python API 烟雾脚本完成双根重放、攻击和 ESS protected hash 重建。所有命令及中间失败在 implementation log 中保留。

## 保护哈希

- ZIP：`1bf3cc17a46cac8552b8eb80d543cec5880afef7f8c716fd8f029636899d688b`
- provisional manifest：`bd69f27305681e6552e61d402571300c2eea340a6d7878dc2b93531c8b6608b0`
- inventory：`8a68d714a86fa8228e17b7f751da8060c558f79f881fb55994e5130caf199de2`
- context：`10472424e35958bc6cef156fe8b48c9b927f13b041414b2125b53dbec7d5e67c`
- summary：`84879af2f2229bbbd4511b0f6985db6adedc6b9e2764262721bebec71756a159`
- contextual preflight：`e47678644a36ddc7d4e8d1fad06ba0cb0ec3a02a179de2816d2d8ba767e35e15`
- hardware setup：`013fd2b10df23569a8998dad1c36fa5793146df29fdb4fa19210d26bbe3c0ac1`
- ESS WAV：`608311700bb64350c9eecc428fb78e1e82d30edea404dbb9d6d3a79b38c422e0`
- ESS metadata：`e581731a06f0951594f73f5d62c7b1d8291027cb64973723a045f92e05d1c25a`
- ESS raw float32：`eabd87614dd0d204ee948b13561298c879539af82258809f1d35dc5ed8ac70ca`

ESS protected-hash artifact 在隔离临时根重新生成/验证后精确清理，root 不存在。

## 文件与已知限制

主要修改：`ess_processing.py`、`ess_processing_models.py`、`ess_processing_persistence.py`、两个 DEV-04 测试文件、ESS processing/storage 架构、README、`.gitattributes`、prompt archive、本报告和 append-only implementation log。`store.py`、receipt Schema、21 数组集合、七文件 processing envelope 和历史 DEV-04.01 prompt/report 未修改。

已知限制：mono 1x1 development、整数样本延迟、无 harmonic separation/smoothing/校准/SPL/正式 QC；reference 近零频点按明确 float64 threshold 输出零。event 绑定没有数字签名、外部见证或可信时间源。create-only 文件系统边界仍是协作式本地完整性机制。

未执行：production `audio-list`/`audio-inventory`、真实设备枚举/连接/选择/绑定、Host API/通道、stream/play/record、校准读取/应用、SPL/电气回环/真实 latency/shared clock、正式 QC/基线差分/特征/分类/协议矩阵、CAD/geometry lock、DEV-03.05、DEV-04.02。均为明确禁止范围，不是遗漏的软件验收。

## Git

报告冻结时尚未提交或推送，不能在提交内容中自引用最终 SHA。仅在报告/日志落盘后的最终测试、静态、哈希、diff、远端基线和工作区内容门禁继续通过后，才提交 `DEV-04.01R: close processing envelope validation` 并正常推送 `origin/main`；禁止 force push。实际结果由 Git 历史和最终回复给出。
