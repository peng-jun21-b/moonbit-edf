# EDF物理窗口到Welch PSD

本功能用于非临床信号检查，不作状态分类或诊断。容器、精确时钟与标定由MoonEDF提供，FFT/窗/periodogram/Welch由固定MoonSpectrum发布包提供。该包0.2.2已用本项目固定工具链在JS和Wasm-GC运行最小算例；未对其它工具链承诺兼容性。模块元数据、SHA与作者提交见根目录SPECTRUM-DEPENDENCY.json。

```moonbit
let result = recording.welch_psd(
  0, "0", "4",
  segment_length=256,
  overlap_samples=128,
  window=@edf.HannSymmetric,
  nfft=256,
  bands=[{name: "requested-8-12-Hz", low_hz: 8.0, high_hz: 12.0}],
)
```

`start/end`沿用TimeInput（Time、十进制/有理数字符串或Double）；需要保留十进制原意时传字符串。Node 24的CLI也保留这些JSON数字的源词法。窗口按时间戳选择`start <= t < end`，在既有精确样本跨度选择与物理标定之上适配，普通通道的索引属于当前Recording。不得把注释通道当成数值信号。

窗口必须完整位于采集首记录起点到末记录终点内，期间无相交gap，记录时长正；每个相邻样本的精确差必须等于`record_duration/samples_per_record`。容差读取不免除该检查。不重采样、不拼接缺口，也不把部分覆盖当完整PSD输入。同一EDF的不同采样率通道分别调用；EDF+D的连续岛可以单独调用。

| 参数 | 合同 |
| --- | --- |
| segment_length | 必填，2..65,536内的2次幂；对称Hann最小为4，拒绝N=2的零能量窗 |
| overlap_samples | 必填整数，0..N-1；step=N-overlap，精确映射上游overlap/N |
| window | 必填Rectangular或HannSymmetric；CLI名rectangular/hann_symmetric |
| nfft | 默认N且必须等于N；不补零，不支持其它FFT长度 |
| detrend/scaling/sides/average | 固定none/density/one-sided/mean；CLI显式请求其它值会拒绝 |
| max_samples/max_segments | 默认及硬上限1,048,576/8,192；调用者只能降低预算，值必须正 |
| 总计算预算 | `segments*N <= 16,777,216`；频带最多256个 |

矩形窗`w[j]=1`；对称Hann为`0.5-0.5*cos(2*pi*j/(N-1))`。每段密度为`abs(FFT(x*w))^2/(fs*sum(w^2))`，DC和Nyquist保持，其余正频点乘2，再对完整段求算术均值。上游不去均值；若调用者先变换数据，应保留自己的变换来源，不能把原始标定PSD误标为处理后数据。

频率格为`k*fs/N, k=0..N/2`，`df=fs/N`。段数为`1+floor((L-N)/step)`，实际使用的唯一时间跨度有`N+(segments-1)*step`个样本，末尾不足一段的样本不参与计算。`selected_samples`含全部选择样本，`used_samples/dropped_tail_samples/segments`说明该差别；`analyzed_end`为最后完整段末样本再加一个精确采样周期的名义右端点。请求边界不必对齐采样点，所以该名义端点与请求end可不同。

JSON保留信号索引/标签、unit、精确sample_rate、Double sample_rate_hz、请求start/end、实际首和末个选择样本时间、analyzed_end、原始物理极值文本与数字极值。数值密度单位为`(unit)^2/Hz`；频带为`(unit)^2`。空物理单位保留空串并设置`unit_specified=false`，显示单位为`(unspecified)^2/Hz`，不会猜测为伏特或无量纲。EDF单位标签不自动换算。

频带名称由调用者给出，边界须有限且`0 <= low < high <= fs/2`。按bin中心选择`[low,high)`，仅在high恰等于Nyquist时含最后一个bin；不对边界插值。选中密度乘df求和，空bin集合的功率为0。相邻频带在普通边界不重复计数；同名、重叠频带是调用者各自的请求。没有默认疾病/睡眠/麻醉频带。

非法参数、短窗、缺失覆盖和非均匀时钟返回Invalid；不支持的nfft返回Unsupported；采样/分段/计算预算、物理标定溢出、不可表示的采样率/归一化/谱/频带功率返回Limit。Double的舍入和下溢仍遵循浮点运算，精确时钟不意味着谱浮点精确。只检查当前有限窗口，未认证任意大数或任意EDF/BDF文件的科学适用性。

0.9.0增加有限的小量级预条件，不将0.8.0允许下溢的行为改称旧契约回归。若完整物理窗口的非零峰值`M <= 2^-512`，选择整数`e=floor(log2(M))`，通过`scalbn(x,-e)`逐样本放大，再调用原MoonSpectrum Welch（内部sample_rate=1）。数学单位还原为`P=P_unit*2^(2e)/fs`；实现将P_unit与fs分离成量级为1的尾数和整数指数，避免先形成会下溢的幅度平方或会溢出的1/fs。log2只选择尺度，数值关系由scalbn完成。上游窗、重叠、完整段均值、尾部策略均保持，没有裁幅、丢弃额外样本或重写FFT/Welch。

输出仍按原`k*fs/N`计算实际Hz格，精确/近似采样率、物理单位、原标定、JSON结构和CSV列不变。零窗口与峰值大于阈值时保持旧路径；原准入条件、预算与fs/df/N*fs、窗归一化、非有限检查不变。这是保护微小信号整体量级的有限策略，不保证极大动态跨度中的细微分量或接近零的抵消项。最终Double舍入/下溢仍存在：例如上述1e-160密度可表示，积分的1e-360功率仍不能表示；不会将其冒称为非零精确功率。物理标定已舍入为0的信息也无法恢复。

独立验收（开发环境固定numpy==2.3.4、scipy==1.16.2，不用于运行时）：

```sh
moon test --target js --deny-warn
moon test --target wasm-gc --deny-warn
moon build --target js --release --deny-warn
python tools/check-psd.py --output NEW.json --work-dir NEW_CASE_DIRECTORY
python tools/check-psd-scale.py --output NEW_SCALE.json --work-dir NEW_SCALE_CASES
```

验证器从独立定宽字节构造EDF，以Fraction解释时钟/标定，小N使用独立O(N²)直接DFT，并逐bin比较SciPy的显式窗数组、detrend=False、相同noverlap/nfft、density/mean/one-sided。覆盖解析单/双音、DC/Nyquist/零、能量与幅度缩放、两类窗、重叠/尾样本、多采样率、gap、不均匀/短窗/非有限/预算及精确JSON时间词法。

小量级验证对矩形恒幅谱使用解析DC公式及其余bin精确为0的正交关系；其余场景用100位Decimal直接DFT、N=4/8代数单位根和N=4对称Hann精确权重，不借生产缩放算法或FFT给出预期。正密度按相对3e-12或2 ULP核对，预期0要求0，避免绝对1e-9误收全零谱。覆盖DC平方尺度律、Nyquist、零、非恒样本、段均值/尾部、次正规密度、最终真下溢与阈值两侧合法对照，并实际回读原JSON/CSV每bin及元数据。原普通范围DFT/SciPy和错误验收保留。

如有既有固定S001R03.edf，可增加`--public-input PATH --consumer-dir NEW_OUTPUT_DIRECTORY`：仅接受源码工具钉住的SHA256，分析通道0的[0,4)秒并回读真实JSON/CSV。输出附数据来源/署名/许可文件，原始数据不随源码分发。消费者的一般调用为`node examples/edf-psd.mjs INPUT.edf NEW_OUTPUT_DIRECTORY examples/psd.json`，输出目录必须不存在。
