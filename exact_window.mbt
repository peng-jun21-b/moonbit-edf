///|
pub struct TimedSample {
  record : Int
  sample : Int
  time : Time
  time_numerator : String
  time_denominator : String
  digital : Int
  physical : Double
} derive(Debug, ToJson)

///|
pub extend TimedSample with @debug.Debug::{to_repr}

///|
pub extend TimedSample with ToJson::{to_json}

///|
pub struct SignalWindow {
  signal : Int
  label : String
  unit : String
  start : String
  end : String
  samples : Array[TimedSample]
  gaps : Array[Gap]
} derive(Debug, ToJson)

///|
pub extend SignalWindow with @debug.Debug::{to_repr}

///|
pub extend SignalWindow with ToJson::{to_json}

///|
pub struct EventWindow {
  annotation_index : Int
  annotation : Annotation
  start : String
  end : String
  complete : Bool
  samples : Int
  channels : Array[SignalWindow]
} derive(Debug, ToJson)

///|
pub extend EventWindow with @debug.Debug::{to_repr}

///|
pub extend EventWindow with ToJson::{to_json}

///|
fn exact_lower_bound(
  onset : Time,
  duration : Time,
  per : Int,
  bound : Time,
) -> Int raise EdfError {
  let mut lo = 0
  let mut hi = per
  while lo < hi {
    let middle = lo + (hi - lo) / 2
    if onset.add(duration.scale(middle, denominator=per)).compare(bound) < 0 {
      lo = middle + 1
    } else {
      hi = middle
    }
  }
  lo
}

///|
fn Recording::window_spans(
  self : Recording,
  signal : Int,
  start : Time,
  end : Time,
  budget : Int,
) -> (Array[(Int, Int, Int)], Int) raise EdfError {
  if signal < 0 ||
    signal >= self.header.signals.length() ||
    self.header.signals[signal].is_annotation() {
    raise Invalid("ordinary signal index required")
  }
  let spans = []
  let mut count = 0
  if start.compare(end) == 0 {
    return (spans, count)
  }
  let per = self.header.signals[signal].samples_per_record
  let duration = self.exact_duration.as_time()
  for r in 0..<self.records {
    let onset = self.exact_starts[r].as_time()
    let first = exact_lower_bound(onset, duration, per, start)
    let last = exact_lower_bound(onset, duration, per, end)
    if last - first > budget - count {
      raise Limit("window exceeds requested sample limit")
    }
    if first < last {
      spans.push((r, first, last))
      count += last - first
    }
  }
  (spans, count)
}

///|
fn Recording::window_gaps(
  self : Recording,
  start : Time,
  end : Time,
) -> Array[Gap] raise EdfError {
  let result = []
  if start.compare(end) >= 0 {
    return result
  }
  for gap in self.gaps() {
    let lower = Time::parse(gap.start)
    let upper = Time::parse(gap.end)
    let lower = if lower.compare(start) < 0 { start } else { lower }
    let upper = if upper.compare(end) > 0 { end } else { upper }
    if lower.compare(upper) < 0 {
      result.push({
        after_record: gap.after_record,
        start: lower.text(),
        end: upper.text(),
      })
    }
  }
  result
}

///|
fn Recording::materialize_window(
  self : Recording,
  signal : Int,
  start : Time,
  end : Time,
  spans : Array[(Int, Int, Int)],
) -> SignalWindow raise EdfError {
  let channel = self.header.signals[signal]
  let samples : Array[TimedSample] = []
  for (r, first, last) in spans {
    for j in first..<last {
      let digital = self.digital(signal, r, j)
      let time = self.sample_time(signal, r, j)
      samples.push({
        record: r,
        sample: j,
        time,
        time_numerator: time.numerator,
        time_denominator: time.denominator,
        digital,
        physical: channel.to_physical(digital),
      })
    }
  }
  {
    signal,
    label: channel.label,
    unit: channel.unit,
    start: start.text(),
    end: end.text(),
    samples,
    gaps: self.window_gaps(start, end),
  }
}

///|
#alias(time_window_exact)
pub fn[A : TimeInput, B : TimeInput] Recording::time_window(
  self : Recording,
  signal : Int,
  start : A,
  end : B,
  max_samples? : Int = 2147483647,
) -> SignalWindow raise EdfError {
  if max_samples < 1 {
    raise Invalid("sample budget must be positive")
  }
  let start = Time::parse(TimeInput::to_time_text(start))
  let end = Time::parse(TimeInput::to_time_text(end))
  if start.compare(end) > 0 {
    raise Invalid("window requires start <= end")
  }
  let (spans, _) = self.window_spans(signal, start, end, max_samples)
  self.materialize_window(signal, start, end, spans)
}

///|
#alias(event_window_exact)
pub fn[A : TimeInput, B : TimeInput] Recording::event_window(
  self : Recording,
  annotation_index : Int,
  signals : Array[Int],
  before~ : A,
  after~ : B,
  include_duration? : Bool = true,
  allow_partial? : Bool = false,
  max_samples? : Int = 2147483647,
) -> EventWindow raise EdfError {
  if max_samples < 1 {
    raise Invalid("sample budget must be positive")
  }
  if annotation_index < 0 || annotation_index >= self.annotations.length() {
    raise Invalid("event window annotation index")
  }
  let before = Time::parse(TimeInput::to_time_text(before))
  let after = Time::parse(TimeInput::to_time_text(after))
  let zero = Time::parse("0")
  if before.compare(zero) < 0 || after.compare(zero) < 0 {
    raise Invalid("event padding requires nonnegative seconds")
  }
  if signals.is_empty() || self.records == 0 {
    raise Invalid("event window requires signals and records")
  }
  let annotation = self.annotations[annotation_index]
  let onset = Time::parse(annotation.onset)
  let duration = Time::parse(
    if include_duration {
      annotation.duration.unwrap_or("0")
    } else {
      "0"
    },
  )
  let start = onset.sub(before)
  let end = onset.add(duration).add(after)
  if start.compare(end) >= 0 {
    raise Invalid("event window must have positive duration")
  }
  let complete = start.compare(self.exact_starts[0].as_time()) >= 0 &&
    end.compare(
      self.exact_starts[self.records - 1].add(self.exact_duration).as_time(),
    ) <=
    0 &&
    self.window_gaps(start, end).is_empty()
  if !complete && !allow_partial {
    raise Invalid(
      "event window crosses missing recording time; explicitly allow_partial to retain it",
    )
  }
  let seen : Map[Int, Bool] = Map([])
  let selections = []
  let mut samples = 0
  for signal in signals {
    if seen.contains(signal) {
      raise Invalid("event window signals must be distinct")
    }
    seen[signal] = true
    let (spans, count) = self.window_spans(
      signal,
      start,
      end,
      max_samples - samples,
    )
    samples += count
    selections.push((signal, spans))
  }
  let channels = selections.map(pair => {
    self.materialize_window(pair.0, start, end, pair.1)
  })
  {
    annotation_index,
    annotation,
    start: start.text(),
    end: end.text(),
    complete,
    samples,
    channels,
  }
}
