///|
// Gregorian whole seconds, used only for validated file-header dates. Int64
// covers 1985..9999 without passing through floating-point or Unix time APIs.
fn DateTime::civil_seconds(self : DateTime) -> Int64 {
  let y = self.year - 1
  let mut days = 365 * y + y / 4 - y / 100 + y / 400 + self.day - 1
  for month in 1..<self.month {
    days += month_days(self.year, month)
  }
  days.to_int64() * 86400L +
  (self.hour * 3600 + self.minute * 60 + self.second).to_int64()
}

///|
fn append_signal_compatible(
  left : Recording,
  right : Recording,
  index : Int,
) -> Bool raise EdfError {
  let a = left.header.signals[index]
  let b = right.header.signals[index]
  if a.is_annotation() || b.is_annotation() {
    return a.is_annotation() && b.is_annotation() && a.label == b.label
  }
  if a.label != b.label ||
    a.transducer != b.transducer ||
    a.unit != b.unit ||
    a.digital_min != b.digital_min ||
    a.digital_max != b.digital_max ||
    a.prefilter != b.prefilter ||
    a.reserved != b.reserved ||
    a.samples_per_record != b.samples_per_record {
    return false
  }
  // The Double convenience fields can hide a difference (e.g. subnormals).
  // Compare the original eight-byte physical calibration fields exactly.
  let n = left.header.signals.length()
  for column in [104, 112] {
    let a = DecimalSeconds::number(
      text_field(left.data, 256 + n * column + index * 8, 8),
    )
    let b = DecimalSeconds::number(
      text_field(right.data, 256 + n * column + index * 8, 8),
    )
    if a.compare(b) != 0 {
      return false
    }
  }
  true
}

///|
/// Append a compatible nonempty recording, preserving exact sample clocks and
/// gaps. offset is the second file-header zero relative to the first file-header
/// zero; by default use their Gregorian header date/time difference. Header
/// clocks must refer to the same clock. Overlaps are rejected even for inputs
/// decoded with a tolerance. The first header's identification is retained.
pub fn Recording::append(
  self : Recording,
  other : Recording,
  offset? : String,
) -> Recording raise EdfError {
  if self.records == 0 || other.records == 0 {
    raise Invalid("append requires two nonempty recordings")
  }
  if self.header.format != other.header.format {
    raise Invalid("append requires the same EDF/BDF format")
  }
  if self.header.patient != other.header.patient {
    raise Invalid("append patient identification differs")
  }
  if self.exact_duration.compare(other.exact_duration) != 0 {
    raise Invalid("append record durations differ")
  }
  if self.records > 99999999 || other.records > 99999999 - self.records {
    raise Limit("append record count exceeds eight-byte header field")
  }
  let shift = DecimalSeconds::number(
    offset.unwrap_or_else(() => {
      (other.header.start.civil_seconds() - self.header.start.civil_seconds()).to_string()
    }),
  )
  let left = self.to_plus()
  let right = other.to_plus()
  let h = left.header
  let n = h.signals.length()
  if n != right.header.signals.length() {
    raise Invalid("append signal layouts differ")
  }
  for s in 0..<n {
    if !append_signal_compatible(left, right, s) {
      raise Invalid("append signal configuration differs at \{s}")
    }
  }
  let sources = [left, right]
  let shifts = [DecimalSeconds::number("0"), shift]
  let mut previous_end : DecimalSeconds? = None
  let mut continuity = if h.signals.any(s => !s.is_annotation()) &&
    self.exact_duration.coefficient.is_zero() {
    Discontinuous
  } else {
    Continuous
  }
  for k in 0..<2 {
    for r in 0..<sources[k].records {
      let onset = sources[k].exact_starts[r].add(shifts[k])
      if previous_end is Some(end) {
        let order = onset.compare(end)
        if order < 0 {
          raise Invalid("append record times overlap or go backwards")
        }
        if order > 0 {
          continuity = Discontinuous
        }
      }
      previous_end = Some(onset.add(self.exact_duration))
    }
  }
  let count = left.records + right.records
  let counts = h.signals.map(s => s.samples_per_record)
  let blocks : Array[Array[Array[Tal]]] = Array::makei(n, _ => [])
  for s in 0..<n {
    if !h.signals[s].is_annotation() {
      continue
    }
    counts[s] = counts[s].max(right.header.signals[s].samples_per_record)
    for k in 0..<2 {
      let source = sources[k]
      let source_header = source.header
      for r in 0..<source.records {
        let tals = parse_tals(
          part(
            source.data,
            source_header.bytes +
            r * source_header.record_bytes +
            source_header.offsets[s],
            source_header.signals[s].samples_per_record * h.format.width(),
          ),
        )
        let changed = tals.map(t => {
          onset: DecimalSeconds::parse(t.onset, true).add(shifts[k]).text(true),
          duration: t.duration,
          texts: t.texts,
        })
        let size = tal_payload(changed).length()
        let width = h.format.width()
        counts[s] = counts[s].max(
          size / width + (if size % width == 0 { 0 } else { 1 }),
        )
        blocks[s].push(changed)
      }
    }
  }
  // Copy ordinary signal fields verbatim, including exact calibration text.
  let header = Array::make(h.bytes, b' ')
  copy_bytes(header, 0, left.data, 0, h.bytes)
  put_text(header, 236, 8, count.to_string())
  let marker = (if h.format == Edf { "EDF+" } else { "BDF+" }) +
    (if continuity == Continuous { "C" } else { "D" })
  put_text(header, 192, 44, marker + h.reserved[5:].to_owned())
  for s in 0..<n {
    if h.signals[s].is_annotation() {
      put_text(header, 256 + n * 216 + s * 8, 8, counts[s].to_string())
    }
  }
  let header = Bytes::from_array(header)
  let parsed = parse_header(header)
  if count > (2147483647 - parsed.bytes) / parsed.record_bytes {
    raise Limit("appended recording exceeds runtime address space")
  }
  let out = Array::make(parsed.bytes + count * parsed.record_bytes, b'\x00')
  copy_bytes(out, 0, header, 0, header.length())
  for k in 0..<2 {
    let source = sources[k]
    for r in 0..<source.records {
      let record = (if k == 0 { 0 } else { left.records }) + r
      for s in 0..<n {
        let destination = parsed.bytes +
          record * parsed.record_bytes +
          parsed.offsets[s]
        let capacity = counts[s] * h.format.width()
        if h.signals[s].is_annotation() {
          let data = encode_tals(blocks[s][record], capacity)
          copy_bytes(out, destination, data, 0, data.length())
        } else {
          copy_bytes(
            out,
            destination,
            source.data,
            source.header.bytes +
            r * source.header.record_bytes +
            source.header.offsets[s],
            capacity,
          )
        }
      }
    }
  }
  decode(Bytes::from_array(out))
}
