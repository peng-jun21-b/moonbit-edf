///|
#alias(window_csv_exact)
pub fn[A : TimeInput, B : TimeInput] Recording::window_csv(
  self : Recording,
  indices : Array[Int],
  start : A,
  end : B,
  physical? : Bool = true,
  max_samples? : Int = 2147483647,
) -> String raise EdfError {
  let start = Time::parse(TimeInput::to_time_text(start))
  let end = Time::parse(TimeInput::to_time_text(end))
  if start.compare(end) > 0 || max_samples < 1 {
    raise Invalid("invalid window or sample budget")
  }
  if indices.is_empty() {
    raise Invalid("window CSV requires ordinary signals")
  }
  let seen : Map[Int, Bool] = Map([])
  let selections = []
  let mut count = 0
  for signal in indices {
    if seen.contains(signal) {
      raise Invalid("window CSV signal indices must be distinct")
    }
    seen[signal] = true
    let (spans, rows) = self.window_spans(
      signal,
      start,
      end,
      max_samples - count,
    )
    count += rows
    selections.push((signal, spans))
  }
  let lines = [
    "signal,label,record,sample,time_seconds,time_numerator,time_denominator,value,unit",
  ]
  for (s, spans) in selections {
    let channel = self.header.signals[s]
    let label = csv_quote(channel.label)
    let unit = csv_quote(if physical { channel.unit } else { "digital" })
    for (r, first, last) in spans {
      for j in first..<last {
        let time = self.sample_time(s, r, j)
        let value = if physical {
          self.physical(s, r, j).to_string()
        } else {
          self.digital(s, r, j).to_string()
        }
        lines.push(
          "\{s},\{label},\{r},\{j},\{time.text()},\{time.numerator},\{time.denominator},\{value},\{unit}",
        )
      }
    }
  }
  lines.join("\n") + "\n"
}
