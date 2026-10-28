# 外部 BDF 交换验证与 0.2.1 修复

固定来源为 [MNE-Python](https://github.com/mne-tools/mne-python/tree/47d5be239f12eb310e7799b5119baf24bed89d05/mne/io/edf/tests/data) 的两个未修改上游测试文件。数据不随源码分发；它们的生理采集来源未在本任务中确认，不能当作临床数据、采用方或诊断验证。

```sh
python tools/fetch-external-bdf.py work/external-bdf
moon build --target js --release --deny-warn
python tools/verify-external-bdf.py work/external-bdf --output work/external-bdf-result.json
```

开发依赖见tools/requirements.txt。成功样本test_bdf_stim_channel.bdf共61,280字节、4通道、10秒、每秒500样本；SHA256在 [reference.json](../evidence/external-bdf-20260927/reference.json)。对照PyEDFlib0.1.42：全部20,000数字样本、3普通通道15,000物理值和12个半开窗口；Status作为原始数值保留，不解释触发位。四种MoonBit写出再由参考库读取：copy、select[3,0]、crop[2,5)整秒、plain转BDF+，56,000数字样本一致。copy还与原文件字节一致。

原实现把普通格式空白patient字段直接复制进BDF+，参考库因此拒绝转出的文件。依据 [EDF+ 2.1.3患者子字段规则](https://www.edfplus.info/specs/edfplus.html)，0.2.1把转换后的未知身份置为X X X X；原非空患者及记录标识保存在+0注释，记录字段写标准Startdate。既有plus保持原文。此转换不是匿名化，原身份文本仍可从注释取回。

2026-09-28在本机隔离 Python 3.12 环境按上述固定哈希重新运行独立参考检查，25 项核对通过；完整结果及失败边界见 [本轮回执](../evidence/acceptance-20260928/EXTERNAL-BDF-RECHECK.json)。

第二个test.bdf共467,456字节、73通道；MoonEDF可以读取，PyEDFlib报Number of Datarecords并拒绝，原字段是带前置空格的`  1     `。保留原始字节与错误；没有修改输入使参考库通过，也没有把148k样本计入独立对照。

这里没有外部负值或间断BDF的证明；负极值/负增益由此前 2026-09-27 的合成矩阵覆盖，本轮未重跑该矩阵；间断语义仍是既有独立字节布局验证。文件限额、身份字段语义和整文件内存边界沿用README。
