# EDF 初审补充材料 · 2026-10-20

原意见指出100ns限制排除合法EDF+时间，判断成立。0.3.0采用十进制任意精度整数与有理数样本时间，补充精确创建/查询，旧事件接口选择与crop/plus也接入完整源精度。完整兼容目标、当前矩阵和剩余限制见[EXACT-TIME](docs/EXACT-TIME.md)。旧申报书与旧证据保留，本材料尚未提交表单。

```sh
moon build --target js --release --deny-warn
python tools/generate-exact-time.py --check
node tools/run-exact-time.mjs /path/to/NEW_DIRECTORY
python tools/verify-exact-time.py /path/to/NEW_DIRECTORY --report /path/to/NEW_REPORT.json
```

6组原创独立定宽源输入包括：

| 案例 | 必须观察到的结果 |
|---|---|
| 10Hz事件`+0.100000000000000000001`，持续`0.1` | `[onset,onset+duration)`只收样本2；不能把事件四舍五入到0.1而收样本1 |
| BDF起点`+0.999999999999999999999`，裁剪第二记录 | 头推进1秒，残余起点仍为`+0.999999999999999999999`；极值24位样本和21位事件/持续时间不变 |
| EDF+D记录间断`1e-21`秒 | 完整事件窗拒绝，partial窗暴露精确gap；不能以旧容差抹掉间断 |
| 3Hz有理数采样 | 比1/3稍大的事件和精确pads只收2/3点；样本时间用分子/分母表示 |
| 181位小数事件起点 | 不受旧128字符和100ns限制；10Hz向后0.1秒窗口收样本1，不收0 |
| 多个负事件时间裁剪后变长 | 自动扩容TAL通道，保留第二个源记录样本和重定位事件；不能静默截字或错读后续记录 |

每组实际跑读入、copy、通道重排、crop与精确create，共30个原/派生文件。Python从HEADER/TAL独立读取，使用`fractions.Fraction`逐样本枚举，核对窗口、原始样本字节、日期推进、全部TAL时间和duration拼写。另跑实际CLI精确查询/创建与拒绝覆盖已有文件，旧事件接口也核对源精度归属。语法、负pads、超算术预算及共享样本限额应返回明确错误。

这不是PyEDFlib对亚100ns时间的认证；旧PyEDFlib回归仅覆盖其支持的格式/时间范围。新结果见 [精度回执](evidence/exact-time-20261020.json)，本轮完整命令见 [CHECKS](evidence/reassessment-20261020/CHECKS.json)。标准PDF/网页不随数据分发；原创合成输入/脚本采用项目MIT。远程CI、发布、报名更新和组委会复审均未执行。
