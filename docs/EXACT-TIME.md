# 0.4.0 统一时间轴

`create`、`decode`、`Annotation`、`Recording.starts`、`sample_time`、`gaps`、`flat_runs`、`time_window`、`event_window`、`window_csv`、`crop` 和 `crop_time_window` 共用精确十进制/有理数时钟。旧 `_exact` 名称只保留为同一实现的别名。

严格模式比较完整十进制值；容差模式显式配置十进制秒数。查询边界可用 `1/3`，样本时间返回约分分子/分母，CSV 不经过浮点转换。Double 输入仅是便利接口，不能恢复调用方已经舍弃的小数位；推荐直接传字符串。

读写多个注释通道时遵循 [EDF+ §2.2.4](https://www.edfplus.info/specs/edfplus.html)：仅第一注释通道负责 timekeeping。CRUD 保持事件通道身份；写出按实际 UTF-8 字节自动扩容。日期跨越 2084 时使用完整 Startdate 年与字面 `yy`。

时间窗写回以精确样本选择结果求公共记录长度，保留相位和采样率。EDF 的定长记录和有限小数 TAL 约束不可通过扩大小数精度消除；若某组不同采样率的选中样本没有共同起点，或所需记录时长/起点不可写为标准字段，API 报出具体原因。无需 EDF 容器的任意窗可直接导出精确 CSV。

本轮证据见 `../evidence/deep-20261020/`。完整标准验收终点是结构、数值字段、TAL、连续性、多注释与写后样本/时间身份均满足相应标准；仅通过 EDFlib 或若干样例不构成外部认证。
