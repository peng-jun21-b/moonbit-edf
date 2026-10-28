///|
/// Explicit windows supported by the EDF adapter. Hann is symmetric, not periodic.
pub(all) enum PsdWindow {
  Rectangular
  HannSymmetric
} derive(Eq, Debug)

///|
pub extend PsdWindow with Eq::{equal, not_equal}

///|
pub extend PsdWindow with @debug.Debug::{to_repr}

///|
pub(all) struct PsdBand {
  name : String
  low_hz : Double
  high_hz : Double
} derive(Debug)

///|
pub extend PsdBand with @debug.Debug::{to_repr}

///|
pub struct PsdBandPower {
  name : String
  low_hz : Double
  high_hz : Double
  bins : Int
  power : Double
} derive(Debug, ToJson)

///|
pub extend PsdBandPower with ToJson::{to_json}

///|
pub extend PsdBandPower with @debug.Debug::{to_repr}

///|
pub struct PsdCalibration {
  physical_min_text : String
  physical_max_text : String
  digital_min : Int
  digital_max : Int
} derive(Debug, ToJson)

///|
pub extend PsdCalibration with ToJson::{to_json}

///|
pub extend PsdCalibration with @debug.Debug::{to_repr}

///|
/// Floating density on an explicit frequency grid, with exact source timing.
pub struct PsdResult {
  signal : Int
  label : String
  unit : String
  unit_specified : Bool
  psd_unit : String
  power_unit : String
  start : String
  end : String
  first_sample_time : Time
  last_selected_sample_time : Time
  analyzed_end : Time
  sample_rate : Time
  sample_rate_hz : Double
  calibration : PsdCalibration
  selected_samples : Int
  used_samples : Int
  dropped_tail_samples : Int
  segments : Int
  segment_length : Int
  overlap_samples : Int
  nfft : Int
  window : String
  window_definition : String
  detrend : String
  scaling : String
  sides : String
  average : String
  endpoint_policy : String
  band_policy : String
  engine : String
  bin_width_hz : Double
  frequencies_hz : Array[Double]
  density : Array[Double]
  bands : Array[PsdBandPower]
} derive(Debug, ToJson)

///|
pub extend PsdResult with ToJson::{to_json}

///|
pub extend PsdResult with @debug.Debug::{to_repr}

///|
/// Welch density for one complete, uniform, finite physical window [start,end).
/// Reuses MoonSpectrum's FFT/Welch implementation; no detrending or zero padding.
/// Budgets can only lower the hard limits: 1,048,576 samples, 8,192 segments,
/// 65,536 samples/segment, 16,777,216 total segment points and 256 bands.
pub fn[A : TimeInput, B : TimeInput] Recording::welch_psd(
  self : Recording,
  signal : Int,
  start : A,
  end : B,
  segment_length~ : Int,
  overlap_samples~ : Int,
  window~ : PsdWindow,
  nfft? : Int = segment_length,
  bands? : Array[PsdBand] = [],
  max_samples? : Int = 1048576,
  max_segments? : Int = 8192,
) -> PsdResult raise EdfError {
  if max_samples < 1 ||
    max_samples > 1048576 ||
    max_segments < 1 ||
    max_segments > 8192 {
    raise Invalid(
      "PSD budgets must be within 1..1048576 samples and 1..8192 segments",
    )
  }
  if segment_length < 2 || segment_length > 65536 {
    raise Invalid("PSD segment_length must be a power of two in 2..65536")
  }
  let mut power = segment_length
  while power > 1 {
    if power % 2 != 0 {
      raise Invalid("PSD segment_length must be a power of two")
    }
    power = power / 2
  }
  if window == HannSymmetric && segment_length < 4 {
    raise Invalid("symmetric Hann requires at least four samples")
  }
  if nfft != segment_length {
    raise Unsupported(
      "PSD nfft must equal segment_length; zero padding is not supported",
    )
  }
  if overlap_samples < 0 || overlap_samples >= segment_length {
    raise Invalid("PSD overlap_samples requires 0 <= overlap < segment_length")
  }
  if bands.length() > 256 {
    raise Limit("PSD exceeds 256 requested bands")
  }
  let start = Time::parse(TimeInput::to_time_text(start))
  let end = Time::parse(TimeInput::to_time_text(end))
  if start.compare(end) >= 0 {
    raise Invalid("PSD window requires start < end")
  }
  let (spans, count) = self.window_spans(signal, start, end, max_samples)
  if self.records == 0 || self.exact_duration.coefficient.compare_int(0) <= 0 {
    raise Invalid("PSD requires records with positive duration")
  }
  if start.compare(self.exact_starts[0].as_time()) < 0 ||
    end.compare(
      self.exact_starts[self.records - 1].add(self.exact_duration).as_time(),
    ) >
    0 ||
    !self.window_gaps(start, end).is_empty() {
    raise Invalid("PSD window crosses missing recording time")
  }
  if count < segment_length {
    raise Invalid("PSD window is shorter than segment_length")
  }
  let step = segment_length - overlap_samples
  let segments = 1 + (count - segment_length) / step
  if segments > max_segments || segments > 16777216 / segment_length {
    raise Limit("PSD exceeds segment or total transform-point budget")
  }
  let rate = self.sample_rate(signal)
  let fs = rate.to_double()
  let df = fs / segment_length.to_double()
  let nf = segment_length.to_double() * fs
  if !finite(fs) || fs <= 0.0 || !finite(df) || df <= 0.0 || !finite(nf) {
    raise Limit(
      "PSD sample rate or normalization is not representable in Double",
    )
  }
  let nyquist = fs / 2.0
  for band in bands {
    if !finite(band.low_hz) ||
      !finite(band.high_hz) ||
      band.low_hz < 0.0 ||
      band.low_hz >= band.high_hz ||
      band.high_hz > nyquist {
      raise Invalid("PSD band requires finite 0 <= low_hz < high_hz <= Nyquist")
    }
  }
  let kind = match window {
    Rectangular => @spectrum.Rectangular
    HannSymmetric => @spectrum.Hann
  }
  // Inspect the upstream weights only to reject a degenerate/overflowed norm.
  // The upstream periodogram still owns windowing and density normalization.
  let weights = @spectrum.window(kind, segment_length) catch {
    e => raise Invalid("MoonSpectrum window: " + @debug.to_string(e))
  }
  let mut energy = 0.0
  for weight in weights {
    energy += weight * weight
  }
  let norm = nf * (energy / segment_length.to_double())
  if !finite(norm) || norm <= 0.0 {
    raise Limit("PSD window normalization is not finite and positive")
  }
  let selected = self.materialize_window(signal, start, end, spans)
  let period = self.exact_duration
    .as_time()
    .scale(1, denominator=self.header.signals[signal].samples_per_record)
  for i in 1..<count {
    if selected.samples[i].time
      .sub(selected.samples[i - 1].time)
      .compare(period) !=
      0 {
      raise Invalid(
        "PSD samples are not uniformly spaced; resampling is not implicit",
      )
    }
  }
  let physical = selected.samples.map(s => s.physical)
  // Power-of-two N makes overlap/N exactly representable, so upstream's
  // floor(N*(1-overlap)) is exactly the requested integer step.
  let spectrum = @spectrum.welch_psd(
    physical[:],
    sample_rate=fs,
    segment_length~,
    overlap=overlap_samples.to_double() / segment_length.to_double(),
    window_kind=kind,
  ) catch {
    e => raise Invalid("MoonSpectrum Welch: " + @debug.to_string(e))
  }
  for i in 0..<spectrum.psd.length() {
    if !finite(spectrum.psd[i]) ||
      spectrum.psd[i] < 0.0 ||
      !finite(spectrum.frequencies[i]) ||
      (i > 0 && spectrum.frequencies[i] <= spectrum.frequencies[i - 1]) {
      raise Limit("PSD or frequency grid is not finite and representable")
    }
  }
  let integrated : Array[PsdBandPower] = []
  for band in bands {
    let mut total = 0.0
    let mut bins = 0
    for i in 0..<spectrum.psd.length() {
      let f = spectrum.frequencies[i]
      if f >= band.low_hz &&
        (
          f < band.high_hz ||
          (band.high_hz == nyquist && i == spectrum.psd.length() - 1)
        ) {
        total += spectrum.psd[i] * df
        bins += 1
      }
    }
    if !finite(total) {
      raise Limit("PSD band power overflow")
    }
    integrated.push({
      name: band.name,
      low_hz: band.low_hz,
      high_hz: band.high_hz,
      bins,
      power: total,
    })
  }
  let channel = self.header.signals[signal]
  let unit = if channel.unit.is_empty() { "unspecified" } else { channel.unit }
  let used = segment_length + (segments - 1) * step
  let ns = self.header.signals.length()
  {
    signal,
    label: channel.label,
    unit: channel.unit,
    unit_specified: !channel.unit.is_empty(),
    psd_unit: "(" + unit + ")^2/Hz",
    power_unit: "(" + unit + ")^2",
    start: start.text(),
    end: end.text(),
    first_sample_time: selected.samples[0].time,
    last_selected_sample_time: selected.samples[count - 1].time,
    analyzed_end: selected.samples[0].time.add(period.scale(used)),
    sample_rate: rate,
    sample_rate_hz: fs,
    calibration: {
      physical_min_text: text_field(self.data, 256 + ns * 104 + signal * 8, 8),
      physical_max_text: text_field(self.data, 256 + ns * 112 + signal * 8, 8),
      digital_min: channel.digital_min,
      digital_max: channel.digital_max,
    },
    selected_samples: count,
    used_samples: used,
    dropped_tail_samples: count - used,
    segments,
    segment_length,
    overlap_samples,
    nfft,
    window: if window == Rectangular {
      "rectangular"
    } else {
      "hann_symmetric"
    },
    window_definition: if window == Rectangular {
      "w[n]=1"
    } else {
      "w[n]=0.5-0.5*cos(2*pi*n/(N-1))"
    },
    detrend: "none",
    scaling: "density",
    sides: "one-sided",
    average: "mean",
    endpoint_policy: "DC and Nyquist unchanged; interior positive bins doubled",
    band_policy: "bin centers [low,high); include Nyquist when high=fs/2; sum(density*df); no interpolation",
    engine: "chgttyyr/MoonSpectrum@0.2.2",
    bin_width_hz: df,
    frequencies_hz: spectrum.frequencies,
    density: spectrum.psd,
    bands: integrated,
  }
}
