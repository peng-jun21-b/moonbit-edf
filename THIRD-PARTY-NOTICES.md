# 来源与许可证

0.8.0新增对chgttyyr/MoonSpectrum@0.2.2的运行时依赖（作者chgttyyr，2026，Apache-2.0，https://github.com/chgttyyr/MoonSpectrum）。Welch、FFT、窗及periodogram直接调用该发布包，不将其重新声明为MoonEDF原创。固定提交d4ca4a2cb138897476a048b271dde0bbb2a302b4，发布包SHA256为024ebf8c9dfec27a237706e31508df244c668e247ac4ea0bdae9dad8cd01f971；详细来源身份见SPECTRUM-DEPENDENCY.json。上游自己的许可证随依赖提供，源码ZIP不捆绑依赖实现。新PSD开发参考固定SciPy1.16.2、NumPy2.3.4（均BSD-3-Clause），不影响下述历史验证环境，也不是产品运行时依赖。

本项目代码MIT。EDF/EDF+格式是既有工作，参见 https://www.edfplus.info/specs/edfplus.html 。独立验证依赖PyEDFlib0.1.42/EDFlib，其许可证由各上游包提供；本项目不将其作为运行时依赖或把它们的实现重新声明为原创。

公开样本来自PhysioNet EEG Motor Movement/Imagery Dataset1.0.0（Gerwin Schalk及同事），DOI10.13026/C28G6P，ODC-By1.0。原文件未随代码分发；tools/fetch-public-eeg.py按固定校验值获取，派生输出manifest保留来源与署名。完整引用与使用边界见docs/PUBLIC-EEG.md和数据集页面。源码MIT不覆盖第三方数据的权利或许可。

本地另核对EEGMAT Subject00_1.edf（PhysioNet eegmat1.0.0，ODC-By1.0）；未随包分发，不把原始采集工作或数据描述列为本项目成果。

0.4.1 记录大小核验的定宽构造器及合成样本为原创，适用本项目 MIT；不使用患者数据。61,440 字节依据 EDF+ §2.1.2 和 https://www.edfplus.info/specs/guidelines.html 第4项，仅引用规范，不将规范网页重新声明为 MIT。该 EDF+ 强制值没有被推断为 BioSemi BDF+ 的限制。

BDF+ 扩展约定来源：https://www.teuniz.net/edfbrowser/bdfplus%20format%20description.html （作者说明其非BioSemi）。其中独立的15 Megabyte单记录边界尚未在本库认证，不能将免用EDF+的61,440字节值解释成免除全部BDF+限制。该网页只作格式参考，不随源码重新许可。

Python Fraction是标准库的精确算术参考，不是TAL格式认证器；PyEDFlib的固定开发参考版本为0.1.42（BSD-3-Clause），NumPy为2.5.3（BSD-3-Clause），均非运行时依赖。既有公开EEG数据遵循各数据集ODC-By1.0及署名要求，不能因本项目MIT而重标为MIT；本期没有引入新的睡眠或患者数据。
