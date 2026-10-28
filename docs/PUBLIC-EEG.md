# 公开事件记录到可复查样本表

本文保留0.2.0公开记录实验及其历史回执。当前0.4.1已统一精确十进制/有理时钟，当前API和预算规则见[README](../README.md)及[公共接口](../pkg.generated.mbti)；以下历史成绩不是本期重新执行。

0.2.0 使用 PhysioNet **EEG Motor Movement/Imagery 1.0.0** 的 `S001/S001R03.edf`，由 Gerwin Schalk 及同事提供。来源与用途见[数据集页](https://physionet.org/content/eegmmidb/1.0.0/)，DOI [10.13026/C28G6P](https://doi.org/10.13026/C28G6P)，数据许可 ODC-By 1.0。下载入口使用数据集页面列出的官方 `physionet-open` S3 桶。

固定文件为 2,596,896 字节，SHA-256 `3427c8d01bff1380bc9ab9f27a35ece2af5dfadf3e291bbc05eb66e4dadbfe2e`，与上游 `SHA256SUMS.txt` 一致。源码包不内嵌原始记录。示例生成的 CSV/manifest 是该数据的派生输出，应随同保留来源和署名，不能改标为项目原创数据。

## 完整复现

安装 README 指定的 MoonBit 和 Node 24 后：

```sh
moon build --target js --release
python tools/fetch-public-eeg.py work/S001R03.edf
node examples/run-public-epochs.mjs work/S001R03.edf work/eeg-epochs
```

输出目录必须不存在。下载器只取这一个文件，检查固定长度和哈希；已有文件不覆盖。例子从固定文件的30条 TAL 注释中选中8条 `T1`，每条取通道0、8、32，前后各0.25秒，并保留事件持续时间。CSV保留源注释号、记录/记录内索引、绝对和相对事件时间、数字/物理值和单位；manifest记录参数、文件哈希和完整性。事件代码的意义随run变化，此例不推断其他文件的T1含义。

独立参考只用于验证，不是运行时依赖：

```sh
python -m pip install -r tools/requirements.txt
python tools/verify-public-eeg.py work/S001R03.edf --output work/public-eeg.json
```

PyEDFlib 0.1.42核对64普通通道、125秒、30事件；逐值核对1,280,000个原始整数和60,000个物理值。30事件的三通道窗口共66,840个样本由独立读取结果和Python Decimal边界计算对照；6个超限/越界/截断失败输入应拒绝。原始记录与参考输出不是我们自己的合成数据，也不是客户采用或临床性能证据。

## 历史0.2.0核心语义（不作为当前API契约）

`Recording::event_window(annotation_index, signals, before~, after~, ...)` 是纯MoonBit公共API。按源注释索引定位，避免同名事件歧义。默认窗口为 `[onset-before, onset+duration+after)`；没有duration按零处理，`include_duration=false`只锚定onset。通道采样率各自保留，不重采样。所有通道共享样本限额，分配前检查，超限不返回半份结果。

事件边界使用已有写入器的100ns时间表示检查，先转整数tick后相加；例如 `20.8 + 4.1 + 0.25` 应得到25.15而非25.150000000000002，否则会多收右端一个采样点。拒绝超出时间范围或不能按现有100ns规则表示的精度；最后输出仍是Double秒，极长时间线受Double精度约束。原`time_window`仍采用调用者给定的Double边界，不被这个新API隐式改写。

默认拒绝越过记录头尾或已知记录间断；`allow_partial=true`才返回部分窗口，并明确 `complete=false`。已知间断仍在各通道`gaps`中，头尾缺失由requested start/end和complete表达，不造补零数据。complete仅指已记录时间覆盖，不证明采集信号健康、事件标签正确或医学有效。

命令行：`node tools/edf.mjs epoch INPUT OPTIONS.json`，选项包含 `annotation`、`signals`、`before`、`after`；可选 `include_duration`、`allow_partial` 和 `max_samples`（默认65536、最多1000000）。空窗口/空通道/重复通道拒绝。

另一个公开EEGMAT文件的头和PyEDFlib都得到182秒，尽管某些描述提到60秒；本项目不使用60秒作为真值，事件工作流采用上述自洽且官方哈希已核对的S001R03。
