当前0.3.0提供十进制/有理数精确接口，见[EXACT-TIME](EXACT-TIME.md)。下文的`time_window`与CSV仍是Double接口，不能用它们恢复源TAL全部精度；旧`event_window`现在采用精确源事件选择。

# 从事件时间到可分析的样本窗口

`time_window` / `window` 回答“原始文件中，时间处于这个区间的样本有哪些”。
它不生成新的EDF文件，不涉及医学判断，也不会替使用者补齐缺失数据。

## 一个可运行的完整流程

```sh
moon run examples/time_window --target js
moon run examples/time_window --target wasm-gc
```

示例用MoonBit创建两个不同采样率的合成通道，记录起点为0.25和2.25秒、
每条记录长1秒，第二条记录带有2.5秒的事件。查询事件前2秒到后0.5秒：

- 查询区间 `[0.5, 3.0)`，快通道得到6个样本，慢通道得到3个。
- `[1.25, 2.25)` 是真实记录间断，不生成样本或补零。
- 第一条结果仍是原始记录0的样本1，时间0.5秒；不会重新从零编号或计时。
- 输出CSV按快通道、慢通道分组，保留每个通道自己的采样时间。

库调用的主要部分是：

```moonbit
let start = event.onset - 2.0
let end = event.onset + 0.5
let window = recording.time_window(0, start, end, max_samples=65536)
let text = recording.window_csv([0, 1], start, end, physical=false)
```

调用方应处理 `EdfError`。完整错误处理和构造过程见 `examples/time_window/main.mbt`。
对已有文件，构建release后使用：

```sh
node tools/edf.mjs window INPUT.edf examples/window.json
node tools/edf.mjs window-csv INPUT.edf examples/window-csv.json > window.csv
```

重定向是shell操作；若命令失败，shell可能已经创建空的CSV文件，应检查退出码。
窗口本身在数量超限时没有部分输出。

## 精确的时间与缺失语义

时间遵循[EDF+规范](https://www.edfplus.info/specs/edfplus.html)的记录起点和记录内等间隔采样；
plus文件使用timekeeping TAL，普通文件使用记录序号乘记录时长。

| 情况 | 结果 |
|---|---|
| 时间等于start | 包含 |
| 时间等于end | 不包含；便于相邻窗口无重复拼接 |
| start等于end | 无样本、无间断；仍检查通道与限额参数 |
| 查询完全在一个已知记录间断内 | 无样本；gaps给出查询与间断的交集 |
| 查询落在两个普通采样点之间 | 可以无样本，但不推断为记录间断 |
| 查询在文件之前或之后 | 不外推样本，不制造头尾间断 |
| 零时长事件记录 | 每个样本是一个时间点，同刻的不同记录都保留 |
| 微小时间回退 | 按文件原顺序输出，不重新排序；遵循既有100ns记录检查容差 |

`TimedSample.time` 使用与 `sample_time` 完全相同的Double表达式。
查询不对端点套用100ns容差，也不把端点四舍五入到采样点。
十进制不能总被Double精确表示；需要精确接续原样本时，使用原样本时间作为边界。
`gaps` 只描述已知记录覆盖之间的间隔；零时长记录不占据正时长区间，
其点样本可能恰好位于间断的左端点。

## 值、索引与资源限制

`SignalWindow` 含原始通道索引、标签、物理单位、请求起止、样本和已知间断。
每个 `TimedSample` 含原始记录号、记录内样本号、秒数、整数数字值和校准后的物理值。
索引均从0开始；通道标签不是唯一键。负增益按原始校准解释。

- `max_samples` 默认65536，允许1到1000000。超限抛 `Limit`，不截断。
- 多通道CSV共享一个限额，先检查全部选择的数量，再读取值和生成CSV。
- 重复通道、空CSV通道列表、注释通道、非有限或反向区间抛 `Invalid`。
- 负的查询起点允许，用于事件前窗口；不会把负起点强制改成0。
- CSV `physical=false` 直接输出数字值，单位写 `digital`；不执行物理校准。
- JSON窗口同时返回数字和物理值，所以校准溢出会报错，不产生无效数值。
- 查询使用逐记录的二分边界定位，复杂度约为记录数乘每记录样本数的对数，加返回样本数；
  不为窄窗口展开整个通道。但文件解析仍是整文件，数量上限不是内存承诺。

## 验证边界

`tools/test-time-window.py` 从官方字段布局独立构造EDF/BDF字节，并通过全量枚举
判断样本归属；不调用本库写出器，也不复用二分查找算法。
小样例覆盖连续、间断、不同采样率、零时长、负增益和端点相邻浮点数，
另有超过默认限额的65537样本输入。真实CLI检查包含失败时stdout为空。
MoonBit测试在JS和Wasm-GC上检查公开接口，包括直接传入NaN与无穷值。
pyedflib不支持的间断格式未声称通过其读取验证。
