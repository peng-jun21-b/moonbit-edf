# 来源、验证工具与样例

本库自身许可证是根目录 MIT LICENSE。按公开格式独立编写 MoonBit 核心，
不是 pyedflib/EDFlib 的源码翻译或绑定；它们仅由独立验证脚本调用。

| 外部来源 | 角色 | 许可证或使用边界 |
|---|---|---|
| [EDF/EDF+ 官方规范](https://www.edfplus.info/specs/edfplus.html) | 头布局、TAL与时间语义 | 仅链接规范，不收录规范全文 |
| [BioSemi BDF 说明](https://www.biosemi.com/faq/file_format.htm) | 24位交换格式 | 仅参考格式，不模拟硬件专有状态 |
| [pyedflib](https://github.com/holgern/pyedflib/) | 0.1.42 Python/C独立读写对照 | 上游声明 BSD-3-Clause；底层使用EDFlib |
| [NumPy](https://github.com/numpy/numpy/blob/main/LICENSE.txt) | 2.5.3 数值与数组参考 | BSD-3-Clause；仅开发验证 |

版本锁定见 tools/requirements.txt。2026-09-22核对上游许可证声明及本机pyedflib发行包许可证；
本表不替代依赖发行包自带的完整许可清单。交付源码不含这些依赖的源码或二进制。
若将来把Python/C运行环境一起分发，应另行保留其完整许可和版权文件。

examples/create.json及测试中的信号、患者占位值、日期和事件均为合成fixture；
tools/differential.py自行生成参考文件，不分发临床数据或上游测试数据集。
时间窗口专项 `tools/test-time-window.py` 使用Python标准库从字段布局生成合成字节，
并独立逐样本枚举；不复制上游测试文件、不调用本库写出器。
evidence仅记录检查结果、环境与源码散列。AI辅助开发保留真实提交作者。

0.3.0再次核对EDF+§2.2.2任意精度小数。新增exact-time输入、定宽构造和Fraction核验为原创MIT；不复制EDFlib时间实现，也不以其100ns结果认证更细小数。标准只引用，不分发原文。
