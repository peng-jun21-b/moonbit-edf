///|
/// Existing population statistics for the native samples in an exact window.
/// Gaps describe missing recorded time; samples are not filled or time-weighted.
pub struct WindowStatistics {
  signal : Int
  label : String
  unit : String
  start : String
  end : String
  gaps : Array[Gap]
  statistics : SignalStatistics
} derive(Debug, ToJson)

///|
pub extend WindowStatistics with @debug.Debug::{to_repr}

///|
pub extend WindowStatistics with ToJson::{to_json}

///|
pub fn[A : TimeInput, B : TimeInput] Recording::window_statistics(
  self : Recording,
  signal : Int,
  start : A,
  end : B,
  max_samples? : Int = 2147483647,
) -> WindowStatistics raise EdfError {
  if max_samples < 1 {
    raise Invalid("sample budget must be positive")
  }
  let start = Time::parse(TimeInput::to_time_text(start))
  let end = Time::parse(TimeInput::to_time_text(end))
  if start.compare(end) > 0 {
    raise Invalid("window requires start <= end")
  }
  let (spans, _) = self.window_spans(signal, start, end, max_samples)
  let statistics = self.statistics_for_spans(signal, spans)
  let channel = self.header.signals[signal]
  {
    signal,
    label: channel.label,
    unit: channel.unit,
    start: start.text(),
    end: end.text(),
    gaps: self.window_gaps(start, end),
    statistics,
  }
}

///|
// Keep the established centered/scaled two-pass strategy. Only the traversal
// changes to exact native spans; the whole-signal statistics body stays intact.
fn Recording::statistics_for_spans(
  self : Recording,
  signal : Int,
  spans : Array[(Int, Int, Int)],
) -> SignalStatistics raise EdfError {
  let s = self.header.signals[signal]
  let mut n = 0
  let mut low = 0.0
  let mut high = 0.0
  let mut mean = 0.0
  let mut below = 0
  let mut above = 0
  let mut at_min = 0
  let mut at_max = 0
  for (r, first, last) in spans {
    for j in first..<last {
      let digital = self.digital(signal, r, j)
      if digital < s.digital_min {
        below += 1
      } else if digital == s.digital_min {
        at_min += 1
      }
      if digital > s.digital_max {
        above += 1
      } else if digital == s.digital_max {
        at_max += 1
      }
      let v = s.to_physical(digital)
      n += 1
      if n == 1 {
        low = v
        high = v
      } else {
        low = low.min(v)
        high = high.max(v)
      }
      mean += (v - mean) / n.to_double()
      if !finite(mean) {
        raise Limit("signal statistics overflow")
      }
    }
  }
  let mut variance = 0.0
  let mut rms = 0.0
  if n > 0 {
    let amplitude = low.abs().max(high.abs())
    let spread = (low - mean).abs().max((high - mean).abs())
    if !finite(spread) {
      raise Limit("signal statistics overflow")
    }
    let mut seen = 0
    let mut center = 0.0
    let mut m2 = 0.0
    let mut squares = 0.0
    if amplitude > 0.0 || spread > 0.0 {
      for (r, first, last) in spans {
        for j in first..<last {
          let v = s.to_physical(self.digital(signal, r, j))
          seen += 1
          if amplitude > 0.0 {
            let normalized = v / amplitude
            squares += normalized * normalized
          }
          if spread > 0.0 {
            let normalized = (v - mean) / spread
            let delta = normalized - center
            center += delta / seen.to_double()
            m2 += delta * (normalized - center)
          }
        }
      }
    }
    variance = spread * (spread * (m2 / n.to_double()).max(0.0))
    rms = amplitude * (squares / n.to_double()).sqrt()
    if !finite(variance) || !finite(rms) {
      raise Limit("signal statistics overflow")
    }
  }
  {
    samples: n,
    minimum: if n == 0 {
      None
    } else {
      Some(low)
    },
    maximum: if n == 0 {
      None
    } else {
      Some(high)
    },
    mean: if n == 0 {
      None
    } else {
      Some(mean)
    },
    variance: if n == 0 {
      None
    } else {
      Some(variance)
    },
    rms: if n == 0 {
      None
    } else {
      Some(rms)
    },
    below_range: below,
    above_range: above,
    at_minimum: at_min,
    at_maximum: at_max,
  }
}
