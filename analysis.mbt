///|
pub struct SignalStatistics {
  samples : Int
  minimum : Double?
  maximum : Double?
  mean : Double?
  variance : Double?
  rms : Double?
  below_range : Int
  above_range : Int
  at_minimum : Int
  at_maximum : Int
} derive(Debug, ToJson)

///|
pub fn Recording::statistics(
  self : Recording,
  signal : Int,
) -> SignalStatistics raise EdfError {
  if signal < 0 ||
    signal >= self.header.signals.length() ||
    self.header.signals[signal].is_annotation() {
    raise Invalid("ordinary signal index required")
  }
  let s = self.header.signals[signal]
  let mut n = 0
  let mut low = 0.0
  let mut high = 0.0
  let mut mean = 0.0
  let mut below = 0
  let mut above = 0
  let mut at_min = 0
  let mut at_max = 0
  for r = 0; r < self.records; r = r + 1 {
    for j = 0; j < s.samples_per_record; j = j + 1 {
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
      let d = v - mean
      mean += d / n.to_double()
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
    // Normalized values keep squares and M2 bounded. Centering first also
    // retains small differences around a large physical offset.
    let mut seen = 0
    let mut center = 0.0
    let mut m2 = 0.0
    let mut squares = 0.0
    if amplitude > 0.0 || spread > 0.0 {
      for r in 0..<self.records {
        for j in 0..<s.samples_per_record {
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
    // Multiply the normalized variance before the second scale factor;
    // spread^2 or an unnormalized total can overflow despite a finite result.
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

///|
pub struct Gap {
  after_record : Int
  start : String
  end : String
} derive(Debug, ToJson)

///|
#alias(gaps_exact)
pub fn Recording::gaps(self : Recording) -> Array[Gap] {
  let result = []
  for r in 1..<self.records {
    let start = self.exact_starts[r - 1].add(self.exact_duration)
    let end = self.exact_starts[r]
    if start.compare(end) < 0 {
      result.push({
        after_record: r - 1,
        start: start.text(false),
        end: end.text(false),
      })
    }
  }
  result
}

///|
pub struct FlatRun {
  first_sample : Int
  samples : Int
  digital_value : Int
  start : Time
  end : Time
} derive(Debug, ToJson)

///|
/// Find repeated digital values; runs never bridge a discontinuous time gap.
#alias(flat_runs_exact)
pub fn Recording::flat_runs(
  self : Recording,
  signal : Int,
  minimum_samples : Int,
) -> Array[FlatRun] raise EdfError {
  if minimum_samples < 1 {
    raise Invalid("flat run threshold must be positive")
  }
  if signal < 0 ||
    signal >= self.header.signals.length() ||
    self.header.signals[signal].is_annotation() {
    raise Invalid("ordinary signal index required")
  }
  let per = self.header.signals[signal].samples_per_record
  let total = self.records * per
  let out = []
  let mut first = 0
  let mut length = 0
  let mut value = 0
  for i = 0; i <= total; i = i + 1 {
    let next = if i < total {
      self.digital(signal, i / per, i % per)
    } else {
      0
    }
    let gap = i > 0 &&
      i < total &&
      i % per == 0 &&
      self.exact_starts[i / per].compare(
        self.exact_starts[i / per - 1].add(self.exact_duration),
      ) !=
      0
    if i == total || (length > 0 && (next != value || gap)) {
      if length >= minimum_samples {
        out.push({
          first_sample: first,
          samples: length,
          digital_value: value,
          start: self.sample_time(signal, first / per, first % per),
          end: self
          .sample_time(signal, (i - 1) / per, (i - 1) % per)
          .add(self.exact_duration.as_time().scale(1, denominator=per)),
        })
      }
      first = i
      length = 0
    }
    if i < total {
      value = next
      length += 1
    }
  }
  out
}

///|
/// Long-form CSV respects each channel's sampling rate and discontinuous timestamps.
pub fn Recording::csv(
  self : Recording,
  indices : Array[Int],
  first_record? : Int = 0,
  records? : Int,
  physical? : Bool = true,
) -> String raise EdfError {
  let count = records.unwrap_or(self.records - first_record)
  if first_record < 0 ||
    count < 0 ||
    first_record > self.records ||
    count > self.records - first_record {
    raise Invalid("CSV record range out of bounds")
  }
  let mut rows = 0
  for s in indices {
    if s < 0 ||
      s >= self.header.signals.length() ||
      self.header.signals[s].is_annotation() {
      raise Invalid("CSV requires ordinary signals")
    }
    let n = self.header.signals[s].samples_per_record
    if count > 0 && n > (2147483647 - rows) / count {
      raise Limit("CSV exceeds runtime row address space")
    }
    rows += n * count
  }
  let lines = [
    "signal,label,record,sample,time_seconds,time_numerator,time_denominator,value,unit",
  ]
  for r = first_record; r < first_record + count; r = r + 1 {
    for s in indices {
      let signal = self.header.signals[s]
      let label = csv_quote(signal.label)
      let unit = csv_quote(if physical { signal.unit } else { "digital" })
      for j = 0; j < signal.samples_per_record; j = j + 1 {
        let value = if physical {
          self.physical(s, r, j).to_string()
        } else {
          self.digital(s, r, j).to_string()
        }
        let time = self.sample_time(s, r, j)
        lines.push(
          "\{s},\{label},\{r},\{j},\{time.text()},\{time.numerator},\{time.denominator},\{value},\{unit}",
        )
      }
    }
  }
  lines.join("\n") + "\n"
}

///|
fn csv_quote(s : String) -> String {
  "\"" + s.replace_all(old="\"", new="\"\"") + "\""
}
