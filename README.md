# MoonEDF 0.12.0

[项目仓库](https://github.com/peng-jun21-b/moonbit-edf) · [GitHub Actions](https://github.com/peng-jun21-b/moonbit-edf/actions/workflows/ci.yml)。模块名保留`peng-jun21/edf`，源码许可证及上游归属保持。

纯 MoonBit 的 EDF / EDF+C/D / BDF / BDF+C/D 读写、精确事件窗口及记录编辑库。Node 入口负责文件和参数 IO；容器、16/24 位样本、校准、TAL、日历、裁剪、拼接和时间运算都在 MoonBit 中实现。

0.4.0 把主工作流统一为精确时间：`decode` 默认严格校验记录连续性和重叠，`Annotation.onset/duration`、`Recording.starts` 为十进制字符串，`sample_time`、平坦段端点为约分有理数 `Time`。`gaps`、`window_csv`、事件窗口和新建文件均使用同一时钟。`_exact` 名称是同一实现的兼容别名，无需另选精确模式。

```sh
moon check --target all --deny-warn
moon test --target js --deny-warn
moon test --target wasm-gc --deny-warn
moon build --target js --release --deny-warn
node tools/edf.mjs create demo.edf examples/create.json
node tools/edf.mjs inspect demo.edf
node tools/edf.mjs window demo.edf examples/window.json
node tools/edf.mjs crop-time demo.edf cut.edf examples/crop-time.json
```

固定工具链见 `.moonbit-version`，Node 24。原始申报书和历史验收材料保留，0.4.0 的本地检查回执在 [evidence/deep-20261020](evidence/deep-20261020)。本地提交不等于远端发布或赛事录取。

## 自动验收

CI在普通Ubuntu 24.04 runner上运行原有格式、全目标check、JS/Wasm-GC测试、文件输入、精确时钟、差分/时间窗和文档示例消费者，并增加固定MoonSpectrum来源检查、独立DFT/SciPy PSD与真实公开EDF的JSON/CSV回读、旧CLI及拼接回归。公开数据仍按既有SHA获取并保留署名，不随源码分发。

工具链使用固定官方发行包和匹配core的SHA256，在隔离目录安装；不依赖本机SDK。原PyEDFlib/NumPy参考与PSD的SciPy/NumPy参考分别安装，保留各自固定版本；版本、来源和命令见[ci/README.md](ci/README.md)。每次运行的真实结果以对应提交的Actions jobs为准。

## 连续物理窗口到 Welch PSD（0.8.0）

`Recording::welch_psd`把一个普通通道的精确半开时段接到[MoonSpectrum 0.2.2](https://github.com/chgttyyr/MoonSpectrum)的既有Welch实现。复用上游FFT、窗函数和密度归一化；本项目新增的是EDF窗口/标定适配、时钟与数值检查、参数/单位溯源、可选频带积分及文件消费者。上游为Apache-2.0，来源、提交和发布包校验值见[SPECTRUM-DEPENDENCY.json](SPECTRUM-DEPENDENCY.json)。没有Python运行时依赖。

```sh
moon build --target js --release --deny-warn
node tools/edf.mjs psd INPUT.edf examples/psd.json
node examples/edf-psd.mjs INPUT.edf NEW_OUTPUT_DIRECTORY examples/psd.json
```

参数显式指定`segment_length`、整数`overlap_samples`和`window`（`rectangular`或`hann_symmetric`）。固定无去趋势、单边density、完整重叠段算术均值；`nfft`等于段长，不补零。对称Hann的分母为`N-1`，不能与周期Hann或SciPy默认参数混用。DC/Nyquist不翻倍，其余正频点翻倍；尾部不足一段的样本丢弃并计数。

仅接受完整位于采集覆盖内、严格均匀、物理值有限的单通道窗口；不同采样率分别调用。EDF+D可分析不跨gap的一段，跨gap、容差读取后仍不均匀的时钟、零记录时长、短窗和超预算均明确报错。旧时间窗/事件窗口仍保留原有partial与gap能力。PSD及物理标定为Double近似，极端归一化或谱值无法表示时返回Limit。

JSON记录源通道/标签、请求时段、实际首/末采样时刻、完整段终点、精确及近似采样率、原始标定文本、物理/PSD单位、参数、频率格和尾样本数。空单位标为unspecified。频带按bin中心`[low,high)`选取，`high=fs/2`时含Nyquist，计算`sum(density*df)`；无插值或临床频带默认值。消费者从同一输入快照输出`psd.json`与逐bin的`psd.csv`，JSON带源文件SHA256，CSV完整转义名称与单位。

完整API、预算和独立验证命令见[docs/PSD.md](docs/PSD.md)。若用`moon --target-dir`在其它磁盘构建，可向Node进程设置`MOON_EDF_BRIDGE`为该目录下`js/release/build/cmd/bridge/bridge.js`的路径；绝对路径和相对当前工作目录的路径均可，支持空格和`#`。CLI、PSD导出、`remove-window.mjs`和`run-public-epochs.mjs`使用同一选择，即使没有默认`_build`也可运行后两个文件示例。未设置时仍使用本项目`_build`；显式路径无效会报错，不静默换用其它产物。

`python tools/check-file-bridge.py --bridge PATH_TO_REAL_BRIDGE.js --public-input work/S001R03.edf --output NEW.json --work-dir NEW_CASES`可验证这条路径；公开输入须为既有SHA钉住的文件。它在无默认构建的独立目录运行真实事件删除/公开导出，以原始样本、TAL与Fraction核对产品，再对照默认构建产物字节，并检查无效路径、已有输出与公开输入校验。输入、输出和回执保留，既有数值与文件合同保持。

`python tools/check-psd-metadata.py --output NEW.json --work-dir NEW_CASES`生成可运行的16位EDF/24位BDF多通道样例，逐通道调用上述文件消费者。标准CSV读者回读含逗号/引号的标签和单位、空单位及各自`16/3`、`8`、`32/3` Hz时钟，并以独立有理数四点DFT逐bin核对两类窗；同时检查错误不创建输出、既有导出目录不被覆盖。单位按源文本保留，空单位的JSON为`unit=""`、`unit_specified=false`，显示为`(unspecified)^2/Hz`；不推断uV或自动换算单位，不重采样。验证器仅用Python标准库，运行库仍无需Python。

### 微小幅度的密度范围（0.9.0）

当物理幅度和采样率都很小时，原始FFT幅值先平方可能下溢为0，即使最终`unit²/Hz`密度可表示。0.9.0对非零峰值不超过`2^-512`的完整窗口做二进制预缩放，以内部1 Hz调用同一个上游Welch，再分离尾数/指数还原实际密度。例如8个`1e-180`恒幅样本、记录时长`1e200`，DC密度可约为`1e-160`。这是旧合同允许下溢基础上的数值可用范围提升。

普通幅度保持原路径；没有裁幅、删样本、替换FFT/Welch或新增输入限制。原始采样率、精确时间、单位、标定和CSV列保持。最终密度或频带功率不可表示时仍可下溢；极大动态跨度或接近零的谱抵消项不在全Double准确性保证内。`python tools/check-psd-scale.py --output NEW.json --work-dir NEW_CASES`以独立Decimal直接DFT核对实际JSON/CSV，保留可运行的合成EDF与输出；生成的`dc.edf`还可配合[examples/psd-small-scale.json](examples/psd-small-scale.json)调用既有消费者。

## 替换普通通道的数字样本区间（0.12.0）

`Recording::with_digital_samples(signal, first_sample, values)`与`samples-set`将调用者给出的整数写入一个普通通道已有的样本位置。`first_sample`为该通道按记录顺序展开的零基序号；连续替换`values.length()`个样本，不插入或删除。跨记录、跨采集gap时只走过实际记录样本，不创建gap内数据，不改变采样时刻或通道速率。

```sh
node tools/edf.mjs samples-set INPUT.edf NEW.edf examples/samples-set.json
moon run examples/digital_edit --target js
moon run examples/digital_edit --target wasm-gc
```

新整数须位于所选通道的`digital_min..digital_max`，与现有`create`相同；不截断、绕回、裁幅或调整标定。未选中的既有越界样本保持原值。注释通道、负/越界序号、过长区间或任何无效新值均报错，后面的值失败也不交付部分编辑。空数组在校验通道/位置后保持原字节；位置可等于该通道总样本数。零记录文件只能接受位置0的空替换。

文件参数的`signal`、`first_sample`及各个`values`必须为Int范围内的整数数值；拒绝非整数，包括会在浮点舍入后看似整数的小数。原JSON数字词法用于这项校验，不先截断或舍入；旧命令的解析策略保持。

返回Recording的`data`和新命令输出仅允许目标16/24位样本字节变化，保留其它通道、头/标定原文、TAL、gap和记录数原文；原`encode()`仍按既有合同规范化记录数。编辑后沿用原读取`time_tolerance`，严格读取策略不变。输入不改，输出须为新路径，参数/读取/替换失败不创建文件。

这是调用者指定的数字编辑，不自动发现或修复伪迹，不写物理浮点值，不进行滤波、重采样或临床解释。已有`Signal::to_digital`可由调用者显式选择做逆标定，其近似和范围策略保持。`python tools/check-digital-edit.py --help`说明独立全字节/有理时钟接收验证；自编公开包示例只证明实际接入。

## 更正既有文件的标识字段（0.11.0）

`Recording::with_identification(patient?=..., recording?=...)`和文件命令`identification-set`只替换调用者给出的原始patient / recording字段。字段遵循既有头写入策略：最多80个可打印ASCII字符，空字符串写为空格，不截断；未提供的字段保持原字节。两个参数都省略时是原字节no-op，包括未知记录数`-1`和原有空格。

```sh
node tools/edf.mjs identification-set INPUT.edf NEW.edf examples/identification-set.json
moon run examples/identification --target js
moon run examples/identification --target wasm-gc
```

原输入保持，输出路径必须不存在。返回Recording的`data`和新命令输出保留其它全部字节，包括日期/时刻、标定原文、记录数原文、TAL和16/24位样本；调用原`encode()`仍按旧合同将未知记录数写为实际值。读取时指定的`time_tolerance`沿用到编辑后解码，未放宽严格读取。字段错误或源解码错误不创建输出，两个字段一起设置时不会交付部分编辑。

EDF+/BDF+的recording字段承载起始日期，因此替换值须保留原字段前两个非空子字段的原值（通常为`Startdate`及日期或`X`）；仅更正其后会话/设备等标识，不借此改变绝对时间。无法解释这种前缀的旧字段可继续读取或更正patient；本命令不修复其recording前缀。依据见[EDF头布局](https://www.edfplus.info/specs/edf.html)及[EDF+标识约定](https://www.edfplus.info/specs/edfplus.html#additionalspecs)。

这是原始字段编辑，不解析或认证完整人口学子字段，也不承诺完整匿名化：注释、文件名和其它字段可能仍含身份信息。`python tools/check-identification.py --help`说明完整接收验证；随包独立原始输入/预期文件核对所有输出字节，并实际重新打开文件读取头与注释。自编公开包接收示例不代表第三方采用。

## 带引号的通道名称与CSV

`rename_signal`和CLI `rename`接受EDF/BDF头字段范围内的ASCII名称，包含逗号或多个双引号时，`csv`与`window-csv`会完整转义标签和单位，标准CSV读者可还原原字段。例如重命名参数`{"signal":0,"label":"A,\"B\",\"C\""}`的名称输出为`"A,""B"",""C"""`。采样时间分数、数值、CSV列及行序保持原合同。

```sh
node tools/edf.mjs rename INPUT.edf RENAMED.edf rename.json
node tools/edf.mjs annotations-window RENAMED.edf examples/annotations-window.json
node tools/edf.mjs window-csv RENAMED.edf examples/window-csv.json
node tools/edf.mjs csv RENAMED.edf examples/csv.json
```

0.7.2修复共享CSV转义只处理第一个双引号的问题；采用[RFC 4180字段引号规则](https://www.rfc-editor.org/rfc/rfc4180)将每个内部双引号翻倍。仅修正字段编码，不改变允许的头字段、分隔符、现有LF行结束或源EDF/BDF数据。

## 将自己的文件中一个事件交付为CSV

`export-epoch.mjs`接受已有注释的受支持EDF/BDF文件，从同一个只读字节快照调用现有`epoch`和`window-csv`，写出`epoch.json`与`samples.csv`。它按调用者指定的注释索引工作，不推断T1等文本的含义，也不要求公开数据SHA。

```sh
node tools/edf.mjs annotations INPUT.edf
node examples/export-epoch.mjs INPUT.edf NEW_OUTPUT_DIRECTORY examples/export-epoch.json
python tools/check-epoch-export.py --output NEW.json --work-dir NEW_CASES
```

options沿用`epoch`的`annotation`、`signals`、`before/after`、`include_duration`、`allow_partial`、共享`max_samples`及读取策略`time_tolerance`。索引属于同一未改动文件；`signals`须为互异普通通道。时间支持十进制/有理数字符串，Node 24裸JSON数字保留源词法；消费者不自行做浮点边界运算。默认包含事件原时长、拒绝缺失覆盖；显式`allow_partial=true`才保留部分窗口，JSON继续标记`complete=false`及各通道的gaps。窗口完全在gap内时CSV只有表头，不补零、不重采样。缺省事件时长与显式`"0"`保留原JSON表示。

CSV复用原`window-csv`九列及原始record/sample编号，按请求通道顺序保留各自时钟；`time_seconds`也可能为`1/3`这样的精确有理数文本，精确分子/分母列同时保留。默认`value`为物理值、单位原样保留，空单位仍为空；可用`physical=false`输出数字值并将CSV单位写为`digital`，JSON仍含原单位与两类样本值。不会自动换算单位或增加事件相对浮点时间列。

JSON附源路径/字节数/SHA、实际请求、原`EventWindow`结果和CSV SHA。原API完成全部校验后才创建输出目录；既有目录会拒绝覆盖，参数/窗口校验失败不创建输出。`MOON_EDF_BRIDGE`与其它文件消费者相同，未指定时采用默认构建。库接口、文件格式、原CSV列与固定公开T1消费者保持。

## 将固定公开EEG的T1事件导出为CSV

`examples/run-public-epochs.mjs`提供可回读的公开数据消费者：仅接受SHA钉住的[PhysioNet EEG Motor Movement/Imagery 1.0.0](https://physionet.org/content/eegmmidb/1.0.0/)中`S001R03.edf`，为其中8个T1事件导出通道0/8/32、前后各0.25秒的CSV及带来源/署名的manifest。它不将其它文件中的T1标签解释成相同任务。

```sh
python tools/fetch-public-eeg.py work/S001R03.edf
node examples/run-public-epochs.mjs work/S001R03.edf work/T1-NEW
python tools/verify-public-export.py work/S001R03.edf work/T1-NEW --output work/T1-NEW-readback.json
```

先按上方命令构建JS桥接；输出目录须为新路径。CSV保留原前11列及顺序，`time_seconds`、`event_relative_seconds`为近似数字秒，末尾追加`time_numerator`、`time_denominator`原整数字符串以保留精确采样时钟。精确事件相对时刻由采样分数减去manifest中的`annotation.onset`得到；物理值仍为Double近似。要求固定11列的读取器需接受这两列附加字段，manifest的`timeColumns`说明各列含义。

独立回读工具从原EDF定宽数字样本、TAL和Fraction时钟/标定核对8份CSV共17,664行、注释身份及产品哈希，不需要Python第三方库。原始数据采用ODC-By1.0，示例manifest保留来源/DOI/署名；数据不随源码分发。本例不做分类、滤波或临床解释。

## 拼接后按事件时间查询跨接缝注释

第21轮保持0.7.1，验证`append`→查询→文本更新→重查→epoch。两份1.5秒片段用显式offset=1.5拼接；右源的`-0.5`秒、duration=1事件变为`+1`秒，仍存于拼后record1。该记录从1.5秒开始，事件描述的时段却跨越接缝。查询按事件时间处理，存储record/signal用于身份识别。

```sh
moon run examples/appended_event --target js
moon run examples/appended_event --target wasm-gc
python tools/check-appended-event.py --output work/NEW-appended-event.json
```

查询`[1.25,1.75)`同时命中左/右记录中的重叠事件，按当前索引仅更新右事件文本为`reviewed-right`，再重查提取`[1,2)`。epoch含左末样本13、右首样本14、另一通道22，精确时刻为1、3/2、3/2秒。示例输出`matches 2 0 1`、`calibration true`、`epoch 3 13 14 22`。独立原始定宽/Fraction回读核对8个数字样本、普通通道全部头字段、`1e-324`标定原文、未选事件和两个源哈希；不重采样或改变未选通道。

[EDF+ TAL规则](https://www.edfplus.info/specs/edfplus.html)允许负onset，持续事件即使延伸到其它记录也只标注一次；本库既有查询不按存储记录的时段先过滤。[MNE.concatenate_raws](https://mne.tools/stable/generated/mne.concatenate_raws.html)将Raw视作连续对象拼接并添加边界标记；本例使用本库已有的显式文件头零点偏移和原字节重写合同，不从注释名称自动推断时钟关系。

## 物理标定后编辑事件时长并提取epoch

第20轮验证现有`map_physical`→查询→时长更新→重查→epoch组合，保持0.7.1。仅对首个普通通道请求`p'=-2p+5`并指定单位`arb`，另一通道仍为`uV`；这是调用者指定的仿射标定与单位标签，不推断通用单位换算。

```sh
moon run examples/calibrated_epoch --target js
moon run examples/calibrated_epoch --target wasm-gc
python tools/check-calibrated-epoch.py --output work/NEW-calibrated-epoch.json
```

按`[1/3,4/3)`查询原stage事件后仅将duration从0.75改为1秒，再重查索引提取`[0.5,1.5)`。双率epoch的5个数字样本为`[0,2,4]`和`[20,30]`，物理值近似为`[5,1,-3]`和`[20,30]`；时刻分别为`[2/3,1,4/3]`和`[2/3,4/3]`，不重采样。示例输出`units arb uV`、`epoch 5 0 2 4 20 30`、`physical true true`。

[EDF+附加规则5](https://www.edfplus.info/specs/edfplus.html#additionalspecs)允许负gain对应的反向物理极值，数字极值保持升序；本例physical min/max为65541/-65529，不擅自交换它们。独立原始定宽/Fraction核验确认9个数字样本与精确时刻不变，未选通道标定、注释文本/通道身份保持，仅目标标定字段/单位和请求的duration改变。物理视图按绝对`1e-8`核对，仍是Double近似。[edfio.from_digital](https://edfio.readthedocs.io/en/stable/generated/edfio.EdfSignal.html#edfio.EdfSignal.from_digital)也提供数字样本与物理范围构造；本库沿用已有标定头编辑接口，不新增组合命令。

## Unicode注释的精确文本选择

第19轮以现有接口验证同一条UTF-8消费者链，保持0.7.1。两个规范等价但码点不同的文本分别使用`é`和`e\u0301`，同时含emoji、TAB、引号/逗号与CR/LF；按查询索引更新其中一个，保留文本内的U+FEFF，再按完整原文选择删除并重新查询。`EXACT_TEXT`比较原字符串，不自动合并规范等价文本或剥除文本内U+FEFF。

```sh
moon run examples/unicode_annotations --target js
moon run examples/unicode_annotations --target wasm-gc
python tools/check-unicode-annotations.py --output work/NEW-unicode.json
```

示例输出`text true true`、`remaining 2 true`与`epoch 3 20 30 200`。独立文件核验将两个文本放在同一原始TAL内，经CLI JSON更新和文件消费者精确删除后，幸存文本、注释身份/时长、6个数字样本与采样时刻保持；从当前索引提取的多率epoch含3个样本。以上仅为本轮有限场景实证。

[EDF+ 2.2.3](https://www.edfplus.info/specs/edfplus.html)规定注释使用UTF-8，并允许TAB/LF/CR；文件头的ASCII字段限制仍适用。[MNE读取接口](https://mne.tools/stable/generated/mne.io.read_raw_edf.html)也提供默认utf8的注释编码参数，该参数本身不说明文本匹配规则。已有[Mooncakes Unicode normalization模块](https://mooncakes.io/docs/moonbit-community/unicode-normalization)可供需要规范化的上层应用研究，本库未引入该依赖或隐式匹配策略。

## 选择交错通道后重查事件索引

第18轮补充现有接口的单条消费者验证，保持0.7.1及库/CLI/API实现。导入布局为`[fast, 主注释通道, slow, 次注释通道]`；选择原普通通道2后，slow位于0，两注释通道位于1/2。事件record/onset/duration/text保留，signal表示新Recording头部的位置；按新头重新查询，再执行编辑、重查和epoch。

```sh
moon run examples/interleaved_projection --target js
moon run examples/interleaved_projection --target wasm-gc
python tools/check-interleaved-projection.py --output work/NEW-interleaved.json
```

示例中两个注释通道的事件同名，查询后只删除次通道命中项，主通道事件及其它记录事件保持；epoch从所选slow通道取到`-200000`、`0.5`秒，验证24位有符号值和采样时刻。通道选择和编辑后均以当前Recording索引为准。现有inspect/select/查询接口已完成该需求，本轮不另加按名选择或永久ID接口。

## 文件消费者的显式容差与空操作（0.7.1）

`remove-window.mjs`可将已有time_tolerance策略贯穿同一字节快照的查询、批量删除和重查；默认仍严格读取。SECONDS直接作为字符串传入MoonBit，不转Double，也不自动猜测容差。

```sh
node examples/remove-window.mjs INPUT.edf NEW.edf 0.75 1.25 drop --time-tolerance 0.000000000000000000001
node examples/remove-window.mjs INPUT.edf NEW.edf 0.75 1.25 --time-tolerance 1e-21
python tools/check-file-tolerance.py --output work/NEW-file-tolerance.json
python tools/check-file-noop.py --output work/NEW-file-noop.json
```

参数后缀为`[EXACT_TEXT] [--time-tolerance SECONDS]`。旧调用中单个字面`--time-tolerance`仍按EXACT_TEXT处理，完整的两个/三个尾参数才启用新选项。若输入在严格连续性上有偏差，输出保留原始时刻和gap，后续读取仍须提供相应策略；epoch跨缺失时段仍需显式allow_partial。容差不是时钟修正、重采样或格式认证。

0.7.1也修复文件空删除操作的字节保持：旧桥接路径无条件调用encode，把未知记录数`-1`改为实际数量，即使删除集为空。现在仍先decode校验输入和参数，空删除集直接返回原始Bytes，保留`-1`及数值拼写；截断/非法输入不会绕过校验。非空编辑继续正常重写实际记录数，通用Recording.encode的导出完成计数语义保持。

## 合法定义接续与点记录消费者

第16轮在0.7.0上补充两类可运行合同验证，库、CLI和公开API实现不变，没有新增拒绝条件或功能接口。

```sh
moon run examples/annotation_contracts --target js
moon run examples/annotation_contracts --target wasm-gc
python tools/check-annotation-contracts.py --output work/NEW-contracts.json
```

annotation-only的保护对象是每记录的合法定义，不能理解为禁止删除某个固定索引：同起点、无duration的合法第一注释通道事件仍幸存时，可以接续定义。仅有第二注释通道的同名/同起点事件则不能替代第一通道定义，缺少合法接续仍返回Invalid。示例按查询索引删除A/C后，保留B/D作为定义，重新查询获得当前索引。

BDF+D示例的零时长记录每普通通道仍有一个点样本。删除其它事件后，重查中间标记并显式allow_partial提取epoch，两个2.25秒样本和值333/-444保留，gap照常报告，complete为false；严格模式仍拒绝缺失时段。这些是既有行为的新增实证，不是格式支持范围的扩张。

## 从查询结果批量删除注释（0.7.0）

标注工具查询到多项噪声事件后，`remove_annotations(indices)`把所有索引解释为同一份未修改Recording的选择，统一校验后一次重写。输入次序无关，重复索引只删除一次；非连续选择不会因逐项删除导致索引移位。返回新的Recording，原输入保持。单项`remove_annotation`接口继续保留；任何编辑后都应重新查询索引。

```sh
moon run examples/annotation_batch --target js
moon run examples/annotation_batch --target wasm-gc
node tools/edf.mjs annotations-remove INPUT.edf NEW.edf examples/annotations-remove.json
node examples/remove-window.mjs INPUT.edf NEW.edf 0.25 2.5 drop
python tools/check-annotation-batch.py --output work/NEW-annotation-batch.json
python tools/check-annotation-contracts.py --output work/NEW-contracts.json
```

直接CLI参数为`{"indices":[0,2]}`，使用该输入的当前annotations数组索引。`remove-window.mjs`先读一次文件字节，精确查询指定时段，可用最后一个可选参数按文本挑选命中项，然后从同一字节快照批量删除并重新查询；省略文本时选择全部时段命中项。它写入新路径，不覆盖原文件，不把按文本筛选扩展成库的查询语言。

API的空数组返回原Recording，不触发plus升格或重建头，其encode视图与原Recording相同；显式encode仍按既有导出语义完成记录数。文件命令annotations-remove从0.7.1起对空数组严格返回已验证的原始字节，包括未知计数字段和普通EDF/BDF。任何负数或越界索引让整次操作返回Invalid；CLI不写部分文件。普通含采样记录可清空全部事件，mandatory timekeeping仍保留；annotation-only记录若失去其定义事件则沿用Invalid，不自动删除记录或补造事件。幸存事件的精确文本、record/signal与顺序、数字样本/采样时刻及原标定字段保持。

操作使用索引集合、线性事件筛选与一次现有记录重写，仍需完整输出内存。没有批量更新事务或跨修改的永久事件ID。[MNE.delete](https://mne.tools/stable/generated/mne.Annotations.html#mne.Annotations.delete)也接受数组索引；[edfio.drop_annotations](https://edfio.readthedocs.io/en/stable/generated/edfio.Edf.html#edfio.Edf.drop_annotations)按文本删除。本功能独立实现，将本库精确时段选择与EDF/BDF安全重写相接，不主张批量删除算法独有。

## 按当前时段查找事件（0.6.0）

回放`[20,30)`秒时，10秒开始、持续到25秒的阶段事件仍与当前时段相交。`find_annotations(start,end)`默认按持续区间检索，返回`AnnotationMatch{annotation_index,annotation}`，可把索引直接交给现有`event_window`或`update_annotation`，不必按文本猜同名事件。查询是只读的，保留原record/signal、onset/duration文本、事件顺序和当前Recording索引，不修改或截短事件。

```sh
moon run examples/annotation_query --target js
moon run examples/annotation_query --target wasm-gc
node tools/edf.mjs annotations-window INPUT.edf examples/annotations-window.json
python tools/check-annotation-query.py --output work/NEW-annotation-query.json
```

范围为半开`[start,end)`。正duration事件满足`onset < end && onset+duration > start`；缺少duration或duration为0时按点事件处理，满足`start <= onset < end`。`include_duration=false`只按起点筛选。相等边界返回空，反向边界报Invalid；`max_annotations`须为正数，超预算报Limit，不返回截断列表。API沿用String/Time/Double时间输入，支持精确`1/3`边界；CLI在Node24保留数字start/end的原词法。

查询扫描所有记录和注释通道，不按存储记录的时段预先过滤，也不因gap排除元数据；例如缺口中的阶段事件仍可被检索，但后续提取样本仍须遵守epoch的`allow_partial`规则。索引对应同一未改动Recording的annotations数组，编辑或通道选择后应重新查询。线性扫描、结果空间随匹配数增长，没有时间索引、分页或自动裁剪功能。

同类接口中，[edfio.get_annotations](https://edfio.readthedocs.io/en/stable/generated/edfio.Edf.html#edfio.Edf.get_annotations)按起点筛选并按时间排序；[MNE Annotations.crop](https://mne.tools/stable/generated/mne.Annotations.html#mne.Annotations.crop)原地限定时段。这里的贡献是MoonBit精确交集、原存储身份和现有编辑/epoch衔接；不声称事件查询算法独有。本次Mooncakes目录与关键词查询未确认可比MoonBit模块，搜索结果不构成全量不存在证明。

## 导入会话标识的裁剪（0.5.4）

`crop`和`crop_time_window`在重写plus文件的recording identification时要求至少包含`Startdate 日期 管理代码 技师代码 设备代码`五个字段；导入的空标识、缺字段或错误前缀统一返回`Invalid("cannot update malformed plus recording identification")`。普通年份的decode/inspect兼容范围保持，错误在需要改写该标识的裁剪操作返回；CLI失败不会写出部分文件。

合法未知日期`Startdate X ...`、额外尾字段和多个空格分隔均可裁剪。通常填入裁剪后的完整日期；如果补日期会超过80字节，且普通日期头可表示完整年份（1985–2084），保留未知日期`X`和全部尾字段。2084年后头部使用字面`yy`，必须写入完整日期：真正超过字段宽度仍返回checked Invalid，不截断设备或尾字段。规则依据[EDF+规范2.1.3第2、4项](https://www.edfplus.info/specs/edfplus.html)。普通EDF/BDF的自由文本标识保留原有整记录裁剪及样本级提升行为。

```sh
moon run examples/recording_identity --target js
moon run examples/recording_identity --target wasm-gc
python tools/check-recording-identity.py --output work/NEW-identity.json --reference-c
```

独立检查先构造原始定宽EDF/BDF，再运行真实CLI，并用Fraction和Gregorian日期核对数字样本、双注释通道事件及绝对采样时刻；无需下载数据。`--reference-c`可选，仅额外回读两份连续、整秒起点输出的数字样本和日期；不认证未知日期字段的跨阅读器兼容性或历史亚秒日期问题。

## 指定原生时段的统计摘要（0.10.0）

`Recording::window_statistics(signal,start,end,max_samples?)`与只读CLI `window-stats`只统计精确半开区间`[start,end)`中已有的原生样本。原`statistics`/`stats`继续统计整条通道。无需先写出一个可能无法用EDF有限小数时长/起点表达的裁剪文件，也无需接收完整样本数组后自行实现统计。

```moonbit
let summary = recording.window_statistics(
  0, "1/4", "3/4", max_samples=100000,
)
```

```sh
moon build --target js --release --deny-warn
node tools/edf.mjs window-stats INPUT.edf examples/window-stats.json
```

结果含原signal/label/unit、请求start/end、裁到请求范围的已知gaps和既有`SignalStatistics`。均值、人口方差（除以N）和RMS按实际选中样本计算，不按经过时长加权；数字范围计数仍比较原数字标定边界。物理值为Double近似，沿用既有居中/缩放两遍策略与有限/溢出检查。空单位保持空串，不推断单位、补gap或重采样。

查询允许`start==end`及文件覆盖外的范围；没有样本时数量/范围计数为0，五个可选数值字段保持None并在JSON中省略，不伪造零均值。完全在gap内的正窗口保留裁切后的gap。`gaps`只描述已知记录间断，不把头尾缺失变成新gap，也不提供临床健康或完整覆盖认证。反向边界、注释通道、非正预算、超预算与不能表示的物理值/统计量报错，CLI失败时无JSON结果。`max_samples`沿用时间窗的正数预算，默认2147483647；显式降低预算不会截断数据。

Node 24的原始JSON时间数字沿用词法保留；也可直接使用十进制/有理数字符串或公共API的Time。调用者已舍入的Double不能恢复精度。查询只建立记录区间与摘要，不为返回值建立逐样本JSON；文件读取仍是整文件，未声称常数总内存、实测加速或全Double域准确性。

公共例包仅用公开API解码预先独立构造的完整原始字节；独立接收脚本逐项消费双后端与真实文件CLI的完整结果：

```sh
moon run examples/window_statistics --target js --deny-warn > NEW_PUBLIC_JS.json
moon run examples/window_statistics --target wasm-gc --deny-warn > NEW_PUBLIC_WASM.json
python tools/check-window-statistics.py --output NEW.json --work-dir NEW_CASES --public-output NEW_PUBLIC_JS.json --public-output NEW_PUBLIC_WASM.json
```

验收保留独立构造的完整原始输入、19组合法期待与10组错误期待；原始定宽/Fraction选样与标定、100位最终平方根独立给出答案，覆盖16/24位、负gain、空单位、数字边界计数、微小/极大有限量级、原生1/3时刻、gap/empty/point记录和裸数字精度。输入与期待的版本/校验值保留，原非法BDF注释元数据另作拒绝对照。接收器保存源SHA与完整JSON产品；自编可运行接收方证明集成工作流，不表示真实第三方采用。

## 统计数值范围（0.5.3）

`statistics`/CLI stats 返回物理值的最小/最大、均值、人口方差（除以N）和RMS，并报告数字值的范围计数。0.5.3修复平方及未归一M2在中间先下溢/溢出的情况：常量`1e-200`的RMS保持`1e-200`，常量`1e200`可得到零方差与有限RMS，`±1e154`的人口方差可得到有限`1e308`；追加零值后的大幅前缀也按最终统计量判断。

```sh
moon run examples/statistics_range --target js
moon run examples/statistics_range --target wasm-gc
node tools/edf.mjs stats INPUT.edf examples/statistics-range.json
```

实现对内存数据扫描两遍，使用幅度缩放和居中后的归一方差，额外内存为常数。均值/极值/计数语义保持；空记录API仍返回None，CLI省略这些可选统计字段；全零结果为0。物理标定与统计结果仍是Double近似视图，真实不可表示的人口方差继续报Limit，例如`±1e200`的方差`1e400`。原始数字样本、精确时钟和标定头不受统计计算改变。

## 会话编辑保留原始标定（0.5.2）

样本级裁剪、注释增删改及注释通道扩容不会改变普通信号的物理标定。0.5.2让这些头重建路径逐字保留原始八字节physical min/max，避免从近似Double视图写回：例如`1e-324`不应变成`0`，`3e-324`不应变成`5e-324`。此前同一文件的样本级裁剪片段与整记录裁剪片段会因这种意外差异被append判为标定不兼容；现在可保留标定后正常拼接。

```sh
moon run examples/session_roundtrip --target js
moon run examples/session_roundtrip --target wasm-gc
node tools/edf.mjs crop-time session.edf first.edf examples/session-first.json
node tools/edf.mjs crop session.edf next.edf examples/session-tail.json
node tools/edf.mjs append first.edf next.edf joined.edf
```

CLI参数示例针对每记录1秒的两条连续记录，需按自己的文件调整。可运行MoonBit例子使用合成原始标定，展示跨闰日截取、写出、解码和拼接，输出8行原始数字样本CSV。公开Signal的物理值仍是Double近似视图；显式`map_physical`仍按Double执行所请求的仿射映射，不受“保留未修改字段”规则冻结。真实标定不一致继续拒绝拼接。

## CLI精确数字时间（0.5.1）

旧CLI的裸JSON有限小数经SDK解析后可能先变成Double，造成窗口选错边界、记录/注释丢尾数或容差被放宽。0.5.1在Node24参数IO边界保留数字原词法，再把已有时间参数交给MoonBit精确计算；字符串请求和公开库API保持。`window`、`window-exact`、`window-csv`、`crop-time`的start/end，`epoch`及别名的before/after，`create`的duration及嵌套records/events时间、`annotation-add`的onset/duration、原支持该选项命令的time_tolerance与append.offset都走该入口。采样索引、数字样本、计数和物理标定参数保留数字类型，尤其`channel.start`和`calibrate.offset`不会被当作时间。

```sh
node examples/cli-time-input.mjs NEW-cli-time-demo
```

这个可运行例子写出一个合成记录，再以裸数字窗`[0.250000000000000000001,0.750000000000000000001)`读取0.5/0.75秒的样本30/40；0.25秒的样本不应混入。创建时的嵌套事件`0.500000000000000000001`也保持原值。输出目录必须是新目录，便于检查原始JSON与EDF。

这没有扩展TAL语法：`annotation-add`的正onset仍用带`+`的字符串，负数字onset可按原契约传入；annotations-set/update的Annotation结构仍使用字符串时间。`null`可选duration继续可用。有理数查询边界如`1/3`仍用字符串。JS调用者如果已经把原值放进Number，无法恢复被舍入的尾数；`writeTransform`/`writeAppend`可接收原始JSON文本或含时间字符串的对象。直接调用底层生成的bridge仍应使用时间字符串。

## 分段记录拼接（0.5.0）

同一采集会话被分成多个文件后，`first.append(next, offset?:String)` 可把兼容的两段合成一份 EDF+/BDF+，继续使用事件窗口和CSV接口。默认根据文件头Gregorian日期/时间对齐，保留中断；明确给出offset时，它表示“第二份文件头零点相对第一份文件头零点”的有限小数秒，第二份首记录的小数起点仍保留。例如首段从0.25秒持续1秒，第二份头晚2秒且首记录也为0.25秒，结果起点为0.25/2.25秒，中间缺失`[1.25,2.25)`；不是把第二段强行贴到1.25秒。

```sh
moon run examples/append --target js
moon run examples/append --target wasm-gc
node tools/edf.mjs append first.edf next.edf joined.edf
node tools/edf.mjs append first.edf next.edf aligned.edf examples/append.json
```

默认对齐要求两份文件头属于同一采集时钟；EDF头不携带时区，库不能判定设备是否同步。偏移接受有限十进制/指数文本，不接受`1/3`这类不可终止偏移。采样时间本身仍可为有理数。

两份均须非空、格式相同、patient标识相同、记录时长数值相等；普通通道顺序、采样数、单位、标定及其他通道字段一致。标定比较原始十进制字段，不通过Double判等；普通样本字节和第一份普通信号头字段逐字保留。普通EDF/BDF自动提升为plus后，注释通道布局也须一致；注释容量可不同，随重定位后的TAL扩容。保留全部事件及其通道、record身份（第二份record加上第一份记录数），onset加精确偏移，duration文本不变。

输出保留第一份头的patient/recording及reserved附加信息；不合并第二份头的recording/reserved字段。普通格式提升时，原有自由文本身份按现有规则存为注释。连续性依据实际记录时刻选+C/+D；即便输入用Tolerance读取，拼接仍拒绝任何精确重叠或倒序。不重采样、填零、重排通道、转换16/24位或自动重切大记录。61,440字节等现有字段/记录约束继续生效，不兼容或无法容纳时明确报错，输入不变。

这延伸的是精确记录整理，不是新建分析框架。[MNE的拼接接口](https://mne.tools/stable/generated/mne.concatenate_raws.html)按连续Raw处理并标记边界；这里直接保留多率原样本及gap。Mooncakes注册表与GitHub的edf/bdf/eeg检索未发现另一份可比MoonBit生理记录拼接库，但检索覆盖有限，不据此宣称唯一或首个。

## 时间与标准

[EDF+ §2.2.2](https://www.edfplus.info/specs/edfplus.html) 的 TAL 是任意精度有限小数；库保留其值与文本，不按 100ns 量化。TAL onset 要带符号，duration 无符号；API 输入还接受指数与 `n/d` 查询边界。不可终止的采样时间例如 1/3 秒用 `Time{numerator:"1",denominator:"3"}` 表达，CSV 同时写精确分子、分母。只有显式 `Time::to_double()` 是近似视图。

0.4.4 修复该浮点视图在极大/极小值的中间缩放错误和临界舍入：先用整数商余数舍入，再按二进制指数缩放，使用最近偶数规则。有限大值不再因中间幂溢出误成 Infinity，可表示的极小值也不会提前归零；真正溢出/下溢仍遵循 binary64。精确时钟、TAL及窗口选择不经过这个近似视图。可运行 `moon run examples/time_projection --target js` 或 `--target wasm-gc` 查看两个范围边界消费者例子。

`decode(data,time_policy=Strict)` 检查精确关系；如采集设备确有误差，可显式传 `Tolerance("0.000000001")`。容差仅影响接收判定，源时间和真实微小间断仍保留。多个注释通道中，只有首个通道首 TAL 承担 timekeeping；其余 TAL 正常合并，编辑保留 record/signal 身份。

日期按 Gregorian 日历推进；EDF+ 2084 年后使用 `dd.mm.yy` 字面字段与 `Startdate dd-MMM-yyyy` 的完整年，支持到标准四位年 9999。相对 TAL 时间不受 68 年或 Double 范围限制。无 4096 字符、100 万事件等产品限额；内存操作仍受运行时地址空间及 EDF 字段真实宽度约束。

0.4.5 修复指数输入的标度溢出与无意义巨大幂分配：有效标度先用宽整数检查，超过运行时字符串可寻址范围时返回 `Limit`；合法的 `0e2147483647`、`0e-2147483648` 直接保持精确零。语法先验证，越界指数、坏指数和零分母仍返回 `Invalid`。这不是可用内存保证：可表示的非零高精度数仍需要相应内存，不设额外精度配额。

0.4.1 补齐 [EDF+ §2.1.2 / 编程指南第4项](https://www.edfplus.info/specs/guidelines.html) 的记录大小边界：EDF+C/D 的每条数据记录（包括全部普通信号和注释存储）不得超过 61,440 字节，恰好等于上限合法。读取、新建和注释扩容重写共用此检查；超限报错。这个强制上限不套用到普通 EDF 或 BDF/BDF+。这是标准记录约束，不是文件总大小或十进制精度限制。

这里的豁免仅针对这一项 61,440 字节检查：普通 EDF、BDF/BDF+ 仍受字段宽度、16/24位样本、通道、TAL、记录时序和运行时内存约束。[BDF+ 扩展说明](https://www.teuniz.net/edfbrowser/bdfplus%20format%20description.html)另列单记录 15 Megabyte 约定，当前版本尚未为该独立边界建立合规验证；不能据此声称 BDF+ 记录无限大。库没有额外的 8MiB 产品上限，且使用整文件内存处理，不提供流式读取接口。

MoonBit 解码入口是 `decode(data : Bytes, time_policy? : TimePolicy) -> Recording raise EdfError`。记录超限抛出 `Invalid("EDF+ data record exceeds 61440 bytes")`；TAL 字节解析/写出分别为 `parse_tals` / `encode_tals`，不存在 `EdfDocument::parse` 接口。可直接运行 `moon run examples/time_window --target js` 或 `--target wasm-gc` 查看保留 gap 与有理采样时间的例子。

## 编辑与重写

| API / CLI | 行为 |
|---|---|
| `create` / create | 从数字样本新建，时间默认精确；旧 Double 入参按其最短十进制值解释 |
| `find_annotations` / annotations-window | 精确检索相交事件，保留原索引与元数据；可切换为仅起点筛选 |
| `select` / select | 普通通道选择/重排，保留全部注释通道 |
| `crop` / crop | 整记录裁剪，精确平移 TAL，推进头日期时间；必要时自动提升为 plus |
| `crop_time_window` / crop-time | 按 `[start,end)` 提取样本，重新计算公共记录切分、采样数、日期和 TAL 容量 |
| `append` / append | 按文件头时钟或明确偏移拼接兼容片段，保留gap、原样本和事件 |
| `with_annotations` / annotations-set | 替换事件，保留提供的 record/signal 身份 |
| `add_annotation` / annotation-add | 添加精确 onset、可选 duration，自动选择记录或显式 record/signal |
| `update_annotation` / annotation-update | 按索引替换事件 |
| `remove_annotation` / annotation-remove | 按索引删除事件 |
| `remove_annotations` / annotations-remove | 从同一未修改Recording的索引集合批量删除，一次重写；空选集字节不变 |
| `add_annotation_signal` / annotation-signal | 新增标准注释通道 |
| `rename_signal` / rename | 修改普通通道标签 |
| `map_physical` / calibrate | 仿射映射物理标定与单位，保留数字样本字节 |
| `with_digital_samples` / samples-set | 替换单个普通通道的既有数字样本区间，保留其它原字节和所有时钟 |

`crop_time_window` 保留选中样本的原始时刻和数字值，输出 EDF+/BDF+；事件 onset 在请求区间内才保留，duration 原值保留，所有事件按头部整秒位移重定位。间断不会压平。4Hz 和 2Hz 通道的 `[0.5,1.5)` 可重切为两个 0.5 秒记录。EDF 每条记录要求各通道共用起点、固定时长与每通道固定采样数；例如同样通道的 `[0.25,0.75)` 留下不同通道起点，无法在一个普通 EDF 中无损表达，库明确报错，不能偷偷插值或移动样本。需要这类窗内全部原始时刻时，使用 `time_window`/CSV 精确表。

0.4.2 修复两条可表达裁剪路径：大记录的普通 EDF 先选样再重建 EDF+，不再因整份输入升格后的中间记录超限而误拒绝；必要时把输出拆成更小的共同记录，保留采样率和所有样本时刻，最终仍执行 61,440 字节检查。重切分须同时满足各通道整数采样数、有限小数时刻和8字节时长字段，无法满足时明确报错。合法的 EDF+D/BDF+D 零时长、每普通通道单样本记录可按记录起点裁剪，保留精确时间、16/24位原值与事件持续时间；裁入空区间仍明确报错。

0.4.3 修复八字节数值头字段的可写性：标定值可用等值整数尾数加指数，例如 `12345e-9`，避免因强制写成更长的标准化形式而让创建、恒等标定或裁剪失败。数值头字段必要时可省略小数点前的零，例如 `.1234567` 秒；TAL 的符号、小数和分隔符规则不变。无法精确容纳的值仍报错，不缩短有效数字。

## CLI

读命令：`node tools/edf.mjs COMMAND INPUT [OPTIONS.json]`。
写命令：`COMMAND INPUT OUTPUT [OPTIONS.json]`；拼接：`append INPUT NEXT OUTPUT [OPTIONS.json]`；新建：`create OUTPUT OPTIONS.json`。

读命令包括 inspect、validate、annotations、annotations-window、gaps、stats、channel、flat、csv、window、window-csv、epoch。写命令见上表，另有 copy、plus。CLI中已有数字时间参数在Node24入口保留原词法，也接受原来的字符串；具体字段与TAL符号要求见上节。输出必须是新路径，失败退出 2。

```json
{"start":"0.5","end":"1.5"}
```

```json
{"onset":"+0.000000000000000000001","duration":"0.000000000000000000003","text":"trigger","signal":2}
```

window 接受 signal/start/end；window-csv 接受 signals/start/end/physical；epoch 接受 annotation/signals/before/after/include_duration/allow_partial；annotations-window 接受 start/end/include_duration/max_annotations。显式 max_samples 是调用者预算，默认按可寻址结果大小；超预算报错，不截断。calibrate 接受 signal/scale/offset/unit；rename 接受 signal/label。API 完整签名见 [pkg.generated.mbti](pkg.generated.mbti)。

## 独立核验

```sh
python -m pip install -r tools/requirements.txt
python tools/check-deep-features.py --output evidence/NEW-deep-features-report.json
python tools/differential.py
python tools/test-time-window.py
python tools/example-smoke.py
node tools/test-host-input.mjs
python tools/check-record-size.py --output evidence/record-size-local.json
python tools/check-crop-repair.py --output work/NEW-crop-repair.json
python tools/check-header-numeric.py --output work/NEW-header-numeric.json
python tools/generate-time-projection.py --check
python tools/check-exponent-input.py --output work/NEW-exponent-input.json
python tools/check-append.py --output work/NEW-append.json --reference-c
python tools/check-cli-time-input.py --output work/NEW-cli-time-input.json
python tools/check-session-workflow.py --output work/NEW-session-workflow.json --reference-c
python tools/check-statistics.py --output work/NEW-statistics.json
python tools/check-recording-identity.py --output work/NEW-identity.json --reference-c
python tools/check-annotation-query.py --output work/NEW-annotation-query.json
python tools/check-annotation-batch.py --output work/NEW-annotation-batch.json
```

历史精确时间功能用原始定宽字节构造器和 Python Fraction 读者交叉验证，包括 5001 位小数、超过 68 年的相对时刻、亚 100ns 严格/容差检查、双注释通道、EDF/BDF 部分记录裁剪和编辑扩容。历史环境为 Python 3.12.14、PyEDFlib 0.1.42、NumPy 2.5.3（开发依赖见 `tools/requirements.txt`）。PyEDFlib 独立读取连续文件的裁剪、重命名及物理标定输出；该版本的时间单位不足以认证亚 100ns，也拒绝间断文件。极细时间与 gap 由独立定宽读者加 Fraction 算术核对，不能推广为所有版本/工具的限制。

Fraction 只作精确数值参考，从原始十进制字符串或整数构建，不先转 float。它接受的指数、空白及 `n/d` 等语法不自动成为合法 TAL；TAL 词法、分隔符与字节结构另由解析器校验。数学一致、格式合法与第三方互操作是不同的检查。

历史成果分别为：16组合成矩阵的190项EDFlib对照、898项窗口检查、6组30个精确写出产品、另一份公开EEG的128万原始数字样本，以及外部BDF回归；这些不是同一批输入或本期新执行。0.4.1本地回执为JS/Wasm-GC各32项及14项独立记录边界检查；此前文档校准阶段未重复运行这些套件。

0.4.2 当轮实际执行JS/Wasm-GC各20项相关回归（含3项新增裁剪回归），以及 `tools/check-crop-repair.py` 的56项独立检查。后者自行构造定宽输入并逐样本枚举Fraction时刻，核对裁剪、事件窗、gap、负事件、注释通道身份、有符号极值与失败路径；不使用本库写入器生成参考输入，也不下载新数据。

0.4.3 当轮执行JS/Wasm-GC各17项相关回归（含3项新增数值头字段回归）；独立脚本对16份原始EDF/BDF输入执行50项转换/错误检查，并以PyEDFlib0.1.42复读原始输入及成功输出。字段值用Fraction精确比较，数字样本字节不变。参考C读者对原始`12345e-9`已有1 ULP浮点解析差异，其物理量视图仅按相对1e-12核对，不将浮点差异说成头字段丢精度。

0.4.4 当轮JS/Wasm-GC各6项相关测试通过，其中新增浮点视图测试逐项对照23个由Python Fraction/float/struct生成的IEEE754位模式（旧实现8项不符，修复后0项）。双后端的公开API消费者共4次输出也与独立位模式一致；期望数据可用 `python tools/generate-time-projection.py --check` 重验。

0.4.5 当轮JS/Wasm-GC各23项相关测试及16项真实CLI检查通过；CLI子进程限定64MiB堆与8秒期限，用Python整数独立核对标度边界、Fraction枚举样本时刻。覆盖明确的Limit/Invalid、极端指数零值、未加引号JSON零值、新建与失败不写出，并保留`1e-5000`窗口精度；原始合成输入SHA256保持一致。

0.5.0 当轮JS/Wasm-GC各20项相关测试（含5项新增拼接测试）、双端示例及9项既有host输入检查通过。独立定宽/Fraction验收共14份成功产品、178个样本的字节和精确时刻、16条拒绝路径、42次CLI调用；其中10份在补齐新命令裸数字偏移原文前已通过，原实现不变的已通过案例复用回执。两个连续EDF/BDF输出另由PyEDFlib0.1.42复读48个数字样本；间断和极细时间由独立读者核对。

0.5.1 当轮61项真实旧CLI检查与独立Fraction/定宽预期一致，包含EDF/BDF的数字/字符串对照、窗口/CSV/事件/裁剪、嵌套创建、带符号注释、容差阈值、1e-5000、检查后的Limit、null、转义/重复键、样本预算及非时间参数；源文件哈希不变。JS/Wasm-GC各13项相关回归、9项host检查、4条拼接兼容路径和一个可运行CLI消费者通过。

0.5.2 当轮双端各23项相关测试（含3项新增标定回归）及双端会话消费者通过。独立定宽/Fraction核验44条CLI路径，完成12份“截取→拼接→写出”会话；包含跨2020闰日的连续/间断、多率、普通格式提升、零时长单样本、仅注释与第二注释通道。原始标定字节、数字值、精确时刻和事件均核对，实际标定变化仍拒绝。两份连续EDF/BDF输出另由PyEDFlib0.1.42复读48个数字样本；不以该Double参考认证极小标定或亚100ns。复用了当轮10条已执行命令的结果。

0.5.2核验发现本机固定PyEDFlib0.1.42的`getStartdatetime()`另有首亚秒单位换算差异：原始输入及拼接输出的首TAL均为`+0.25`，原生返回值均为2,500,000个[100ns单位](https://github.com/holgern/pyedflib/blob/v0.1.42/pyedflib/_extensions/c/edflib.h)，Python日期封装却除以100得到25,000微秒，显示为0.025秒。该轮仅将其数字样本回读作为第三方证据，精确时钟单独用原始TAL/Fraction核对；没有修改依赖。这是本机该固定版本的实测，不推及其他版本。

0.5.3 当轮双端各8项相关测试（含3项新增统计回归）及双端统计消费者通过。独立定宽/Fraction与90位Decimal核验28条CLI路径、20组统计预期，覆盖EDF/BDF极小/极大常量、有限大方差、前缀稀释、负增益、范围计数、空/零记录和真正溢出，并验证截取后拼接再统计。参考计算在最后才投影float，不先用float平方；有限数值按相对1e-12核对，零值/None/计数另查。复用当轮9条已执行命令结果；源文件哈希不变，未重跑旧大矩阵或下载新数据。

0.5.4 当轮JS/Wasm-GC各12项相关回归（含3项新增标识测试）及双端公开消费者通过。独立定宽/Fraction/日历核对56条真实CLI路径：26份裁剪产品的156个数字样本、22个事件及绝对时刻、标定字节符合预期，26条checked错误无部分输出，4条inspect兼容读取保持；26份源输入SHA256不变。覆盖空/缺字段/错误前缀、完整与未知日期、额外尾字段、多空格、满80字节、跨日、跨2084/2085年边界、2100年+D与普通格式自由标识。PyEDFlib0.1.42另回读2产品共12个数字样本及整秒日期；未重跑此前大矩阵、统计或公开下载。

0.6.0 当轮有限旧功能审查10条CLI组合通过，未发现新确证缺陷；新增查询用JS/Wasm-GC各7项相关测试及双端公开消费者核验。独立原始定宽/Fraction执行40条真实CLI调用、29组查询预期、6条checked错误，覆盖负onset、点/零时长、相触边界、1/3、超Double精度的裸数字、双注释通道同名及乱序/跨记录存储、gap、plain和annotation-only；查询索引再实际用于epoch和annotation-update。4份原始输入哈希不变，两份编辑产品保留其他事件、数字样本和标定字节。旧标识/日期/裁剪、大矩阵与公开数据下载没有重复执行。

0.7.0功能交付轮（第15轮）新增旧链路审查6条CLI通过：多文本TAL/Unicode更新、重查、单项删除、重查和epoch，未发现新确证缺陷。批量操作另用30条真实CLI/Node示例调用验证15份产品、9条checked失败或防覆盖路径，4份原输入哈希不变；逐字核对幸存元数据、原始数字块/头字段及Fraction时刻。包含非连续/乱序/重复选择、全部/空选择、单项兼容、极小标定、定义事件拒绝和编辑后重查。Node示例另核省略文本及零选中分支，复用当轮28条已执行命令结果。双端各7项当轮相关测试与双端批量消费者通过；这7项为新增4项及既有注释重写3项，没有重跑0.6.0的7项或50条CLI。历史大矩阵、日期/裁剪及公开下载均未重跑。

第16轮有限合同审查保持0.7.0：9条新CLI调用、2份重读产品、2条checked Invalid与两组新增回归/双端消费者通过；原始定宽输入不依赖MoonEDF writer，核对定义文本合法接续、次通道不能替代主定义、BDF零时长点样本的查询→批删→重查→partial epoch。2份输入哈希不变。未发现新确证缺陷或必须新增API的需求，库/CLI实现与生成接口不变；第15轮36条/双端7项只核证据，不重复运行。

0.7.1修复交付轮（第17轮）先查5条未知计数/显式容差链路，后验收发现并独立复现文件空删除改计数字段；修复后19条真实调用、10份产品及8条拒绝/防覆盖路径通过。核对EDF/BDF的1e-21阈值与一个投影Double相同但更小的阈值、原时钟/样本/gap、非空计数完成与空操作原字节、旧字面flag文本、默认严格和输出保护。修前4次调用留存，其中2个已过非空路径因同一桥接分支实际改变而重验；未重跑第16轮9条/双端2项或旧大矩阵。核心库与公开API保持；当轮变更在JS桥接文件操作和Node消费者，由真实文件回读核验，不编造新的MoonBit单元测试数量。

第18轮保持0.7.1，仅审查交错通道的inspect→select→查询→编辑→重查→epoch链。6条真实CLI、2份回读产品、JS/Wasm各1项新合同回归及双端公开消费者通过；原始定宽BDF不由MoonEDF writer生成，独立核对普通通道头/24位样本、双注释通道映射/TAL和Fraction时刻，源哈希不变。未发现新缺陷，未选择新功能；核心/CLI/API/版本不变。第17轮19调用/10产品、阈值/容差/gap/空操作套件不重跑。

第19轮保持0.7.1，UTF-8多文本TAL→查询→JSON更新→文件精确文本删除→重查→epoch链通过5条真实调用、2份回读产品、JS/Wasm各1项新合同回归及双端公开消费者。逐字核对幸存Unicode文本、record/signal/onset/duration、普通头/样本与Fraction时刻，1份源输入哈希不变；未发现新缺陷，核心/CLI/API不变。第18轮及更早套件仅核冻结证据，不重复运行。

第20轮保持0.7.1，单通道负比例标定→事件时长更新→重查→多率epoch链通过5条真实CLI、2份产品回读、JS/Wasm各1项新增合同回归及双端公开消费者。9个数字样本、原通道身份/文本和Fraction时刻保持，目标物理映射与另通道不变符合预期；1份输入哈希不变。未发现新缺陷，核心/CLI/API不变；第19轮Unicode、18轮通道重排及更早矩阵未重跑。

第21轮保持0.7.1，显式偏移拼接→按事件时间查询→指定记录文本更新→重查→跨接缝epoch通过5条真实CLI、2份产品回读、JS/Wasm各1项新增合同回归及双端公开消费者。8个数字样本和普通头/标定字节保持，事件时间与存储record/signal分别核对，2份输入哈希不变；未发现新缺陷，核心/CLI/API不变。第20轮负比例标定、19轮Unicode、18轮通道选择与旧矩阵未重跑。

MIT；PyEDFlib/NumPy 仅作开发核验依赖。项目不作生理信号诊断。

上述百万样本与精确时间数字均为仓库保留的历史验证，不能算作 0.4.1 新执行。新增记录边界核验只需 Python 标准库；包括 EDF+C/D 合法边界、非法输入与编辑扩容、普通 EDF/BDF+ 对照。有限案例和本地通过不构成“所有合法输入/全规范认证”；BDF 的设备 Status 位仍只原样交换。
