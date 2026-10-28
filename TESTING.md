# 0.3.0本地整改验证 · 2026-10-20

命令、退出码和当前覆盖见 [CHECKS](evidence/reassessment-20261020/CHECKS.json)，新精度证据见 [独立Fraction回执](evidence/exact-time-20261020.json)。

```sh
python tools/generate-exact-time.py --check
node tools/run-exact-time.mjs /path/to/NEW_DIRECTORY
python tools/verify-exact-time.py /path/to/NEW_DIRECTORY --report /path/to/NEW_REPORT.json
```

新核验仅需Python标准库，6组源字节由独立定宽写入器生成。它不通过PyEDFlib的100ns内部时间来判断更细的事件；PyEDFlib只用于旧兼容范围的回归。新旧回执分别存放，下面是旧版历史。

# 工具链固定版本更新（2026-09-28）

已将 .moonbit-version 更新为 0.10.14+7d59c7ec9。使用该固定工具链执行 moon update、moon fmt --check、严格全目标检查、JS 与 Wasm-GC 测试（各16项）、release JS 构建、moon info、生成接口差异检查、9项 Node 宿主输入检查，以及 JS/Wasm-GC 时间窗口示例，全部通过。

本机原有 Python 3.14.4 安装 PyEDFlib 失败；随后改用 D 盘隔离 Python 3.12 环境，安装 PyEDFlib 0.1.42/NumPy 2.5.3，重跑外部 BDF 参考验证，25 项核对通过，见 [本轮回执](evidence/acceptance-20260928/EXTERNAL-BDF-RECHECK.json)。16 组合成差分矩阵和 PhysioNet 完整记录本轮没有重跑；下方 2026-09-27 回执仅作为先前结果。

## Prior 0.2.1 validation (2026-09-27)

该次固定工具链见.moonbit-version，收据为 [LOCAL-CHECKS](evidence/external-bdf-20260927/LOCAL-CHECKS.json)。该次全目标静态检查、JS/Wasm-GC各16项测试及JS桥接构建通过；重新运行受转换修改影响的16组PyEDFlib合成矩阵（190项对照、2项CLI），结果另存该轮目录。

新外部BDF检查不修改源文件：20,000数字值、15,000物理值、12窗口/2,012样本，复制/选通道/裁剪/转plus写出由独立库重新读取56,000数字值。原始copy逐字节一致。参考库拒绝的另一文件保留拒绝记录，不计入通过量。来源与边界见 [EXTERNAL-BDF](docs/EXTERNAL-BDF.md)。

修复前转plus保留空patient字段，PyEDFlib拒绝输出；修复后采用标准未知子字段，非空原文本作为注释保存。新增回归同时覆盖EDF/BDF、空白和自由文本身份、数字值不变及plus幂等。

0.2.0事件窗口及PhysioNet独立证据保留在 [epoch](evidence/epoch-20260927/LOCAL-CHECKS.json)：128万个数字值、6万个物理值、30事件/66,840窗口样本，以及实际8事件17,664行CSV导出。窗口代码本轮未改，未重跑该完整外部记录。旧证据不得计作本轮重新执行。

本机验证不代表远程CI、公开发布或生产采用。外部BDF测试没有负数字值/间断BDF，负极值保留合成矩阵覆盖；设备Status只原样交换，不解释其专有位。
