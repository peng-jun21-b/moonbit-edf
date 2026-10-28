# 编码前范围和查重

日期 2026-09-21。Mooncakes 的 edf 命中 NLSE 掺铒光纤模型，不是 European Data Format；biosignal 命中 BioSeqs 的 bamsignals_demo，未发现 EDF API，该模块没有可核验的 GitHub 来源。GitHub `edf language:MoonBit` 零结果，biosignal 的 camera-autolabeler 是相机手势标注，不是 EDF/BDF 交换库。GitLink 公共索引组合搜索未发现同类。完整检索记录位于本批总目录 research/，不宣称全球绝无前人实现。

范围：EDF、EDF+C/D、BDF、BDF+C/D 的头和记录读写；16/24位样本、物理换算、多采样率；TAL UTF-8 注释和时间线；通道选择、整记录裁剪及正确的起始日期/时间；数字/物理 CSV、统计、饱和/平坦段/断点检查；真实文件 CLI、pyedflib 独立双向对照、坏输入及边界、可运行例子、文档/CI/提交。

不做 EEG/ECG 诊断，不扩展为通用信号处理平台。整文件上限 256 MiB，最多 4096 通道、1,000,000 记录，单记录 8 MiB。原始 TAL 字节在无变换交换中保持；新建及修改时间采用 100 ns 精度，无法精确重写的超精度时间明确拒绝。日期工作流覆盖 1985–2084；不猜测无效日期。

规范：
- https://www.edfplus.info/specs/edf.html
- https://www.edfplus.info/specs/edfplus.html
- https://www.biosemi.com/faq/file_format.htm （直接打开失败，后续官方站点搜索成功读取格式说明，与 pyedflib 输出交叉核验）
- https://pyedflib.readthedocs.io/en/latest/

按公开规范独立实现，不复制 pyedflib/edflib 源码。Python/C 库仅开发验证依赖。原始 EDF+ 支持负增益（physical_max 可小于 physical_min）、duration=0 的特殊记录、注释通道内按字节排列的 UTF-8，不能用常见的简化假设替代这些规则。
