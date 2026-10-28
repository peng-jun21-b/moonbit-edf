///|
fn tal_payload(tals : Array[Tal]) -> Bytes raise EdfError {
  let chunks = []
  let mut size = 0
  for tal in tals {
    ignore(DecimalSeconds::parse(tal.onset, true))
    if tal.duration is Some(value) {
      ignore(DecimalSeconds::parse(value, false))
    }
    if tal.texts.is_empty() {
      raise Invalid("TAL requires a text entry")
    }
    for text in tal.texts {
      for c in text.iter() {
        if c.to_int() < 32 && c != '\t' && c != '\n' && c != '\r' {
          raise Invalid("forbidden TAL control character")
        }
      }
    }
    let data = @utf8.encode(
      tal.onset +
      (match tal.duration {
        None => ""
        Some(d) => "\u0015" + d
      }) +
      "\u0014" +
      tal.texts.join("\u0014") +
      "\u0014\u0000",
    )
    if data.length() > 2147483647 - size {
      raise Invalid("TAL bytes exceed runtime address space")
    }
    size += data.length()
    chunks.push(data)
  }
  let out = Array::make(size, b'\x00')
  let mut at = 0
  for data in chunks {
    copy_bytes(out, at, data, 0, data.length())
    at += data.length()
  }
  Bytes::from_array(out)
}

///|
fn Recording::rewrite_annotations(
  self : Recording,
  signals : Array[Signal],
  blocks : Array[Array[Array[Tal]]],
) -> Recording raise EdfError {
  let h = self.header
  let width = h.format.width()
  let chosen = signals.mapi((s, channel) => {
    if !channel.is_annotation() {
      return channel
    }
    let mut bytes = channel.samples_per_record * width
    for r in 0..<self.records {
      bytes = bytes.max(tal_payload(blocks[s][r]).length())
    }
    { ..channel, samples_per_record: (bytes + width - 1) / width, }
  })
  let header = make_header(
    h.format,
    h.continuity,
    h.patient,
    h.recording,
    h.date,
    h.time,
    h.reserved,
    self.records,
    h.duration,
    chosen,
  )
  let header = self.preserve_calibration(header)
  let parsed = parse_header(header)
  if self.records > (2147483647 - parsed.bytes) / parsed.record_bytes {
    raise Invalid("recording exceeds runtime address space")
  }
  let out = Array::make(
    parsed.bytes + self.records * parsed.record_bytes,
    b'\x00',
  )
  copy_bytes(out, 0, header, 0, header.length())
  for r in 0..<self.records {
    for s in 0..<chosen.length() {
      let destination = parsed.bytes +
        r * parsed.record_bytes +
        parsed.offsets[s]
      let capacity = chosen[s].samples_per_record * width
      if chosen[s].is_annotation() {
        let data = encode_tals(blocks[s][r], capacity)
        copy_bytes(out, destination, data, 0, data.length())
      } else {
        copy_bytes(
          out,
          destination,
          self.data,
          h.bytes + r * h.record_bytes + h.offsets[s],
          capacity,
        )
      }
    }
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}

///|
/// Replace events, preserving each event's record and annotation-signal identity.
/// Only the first annotation signal has mandatory timekeeping TALs.
pub fn Recording::with_annotations(
  self : Recording,
  annotations : Array[Annotation],
) -> Recording raise EdfError {
  let source = self.to_plus()
  let h = source.header
  let blocks = Array::makei(h.signals.length(), _ => {
    Array::makei(source.records, _ => [])
  })
  let mut first = -1
  for s in 0..<h.signals.length() {
    if h.signals[s].is_annotation() {
      first = s
      break
    }
  }
  let annotation_only = h.signals.all(s => s.is_annotation())
  for r in 0..<source.records {
    blocks[first][r].push({
      onset: source.exact_starts[r].text(true),
      duration: None,
      texts: [""],
    })
  }
  for event in annotations {
    if event.record < 0 ||
      event.record >= source.records ||
      event.signal < 0 ||
      event.signal >= h.signals.length() ||
      !h.signals[event.signal].is_annotation() {
      raise Invalid("annotation record/signal identity")
    }
    let onset = DecimalSeconds::parse(event.onset, true)
    if event.duration is Some(duration) {
      ignore(DecimalSeconds::parse(duration, false))
    }
    if event.text.is_empty() {
      raise Invalid("event text must be nonempty")
    }
    if annotation_only &&
      event.signal == first &&
      event.duration is None &&
      onset.compare(source.exact_starts[event.record]) == 0 &&
      blocks[first][event.record][0].texts.length() == 1 {
      blocks[first][event.record][0].texts.push(event.text)
    } else {
      blocks[event.signal][event.record].push({
        onset: event.onset,
        duration: event.duration,
        texts: [event.text],
      })
    }
  }
  if annotation_only {
    for r in 0..<source.records {
      if blocks[first][r][0].texts.length() < 2 {
        raise Invalid(
          "annotation-only record needs its defining event at record start",
        )
      }
    }
  }
  source.rewrite_annotations(h.signals, blocks)
}

///|
pub fn Recording::add_annotation(
  self : Recording,
  onset : String,
  text : String,
  duration? : String,
  record? : Int,
  signal? : Int,
) -> Recording raise EdfError {
  let source = self.to_plus()
  let time = DecimalSeconds::parse(onset, true)
  let mut chosen = 0
  for r in 0..<source.records {
    if source.exact_starts[r].compare(time) <= 0 {
      chosen = r
    }
  }
  let mut annotation_signal = -1
  for s in 0..<source.header.signals.length() {
    if source.header.signals[s].is_annotation() {
      annotation_signal = s
      break
    }
  }
  let events = source.annotations.copy()
  events.push({
    record: record.unwrap_or(chosen),
    signal: signal.unwrap_or(annotation_signal),
    onset,
    duration,
    text,
  })
  source.with_annotations(events)
}

///|
pub fn Recording::remove_annotation(
  self : Recording,
  index : Int,
) -> Recording raise EdfError {
  if index < 0 || index >= self.annotations.length() {
    raise Invalid("annotation index")
  }
  self.with_annotations(
    self.annotations
    .mapi((i, event) => (i, event))
    .filter(pair => pair.0 != index)
    .map(pair => pair.1),
  )
}

///|
/// Remove indices from one unchanged annotation array in a single rewrite.
/// Repeated indices select the same event once; an empty selection is a no-op.
pub fn Recording::remove_annotations(
  self : Recording,
  indices : Array[Int],
) -> Recording raise EdfError {
  if indices.is_empty() {
    return self
  }
  let selected : Map[Int, Bool] = Map([])
  for index in indices {
    if index < 0 || index >= self.annotations.length() {
      raise Invalid("annotation index")
    }
    selected[index] = true
  }
  let remaining = []
  for i in 0..<self.annotations.length() {
    if !selected.contains(i) {
      remaining.push(self.annotations[i])
    }
  }
  self.with_annotations(remaining)
}

///|
pub fn Recording::update_annotation(
  self : Recording,
  index : Int,
  annotation : Annotation,
) -> Recording raise EdfError {
  if index < 0 || index >= self.annotations.length() {
    raise Invalid("annotation index")
  }
  let events = self.annotations.copy()
  events[index] = annotation
  self.with_annotations(events)
}

///|
pub fn Recording::add_annotation_signal(
  self : Recording,
) -> Recording raise EdfError {
  let source = self.to_plus()
  let h = source.header
  let signals = h.signals.copy()
  let annotation = h.signals.filter(s => s.is_annotation())[0]
  signals.push({ ..annotation, samples_per_record: 1, })
  let blocks = Array::makei(signals.length(), s => {
    Array::makei(source.records, r => {
      if s >= h.signals.length() || !signals[s].is_annotation() {
        []
      } else {
        parse_tals(
          part(
            source.data,
            h.bytes + r * h.record_bytes + h.offsets[s],
            h.signals[s].samples_per_record * h.format.width(),
          ),
        )
      }
    })
  })
  source.rewrite_annotations(signals, blocks)
}

///|
pub fn Recording::rename_signal(
  self : Recording,
  signal : Int,
  label : String,
) -> Recording raise EdfError {
  if signal < 0 ||
    signal >= self.header.signals.length() ||
    self.header.signals[signal].is_annotation() ||
    label == "EDF Annotations" ||
    label == "BDF Annotations" {
    raise Invalid("ordinary signal rename required")
  }
  let out = self.data.to_array()
  put_text(out, 256 + signal * 16, 16, label)
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}

///|
/// Apply an affine physical-unit map while preserving digital sample bytes.
pub fn Recording::map_physical(
  self : Recording,
  signal : Int,
  scale : Double,
  offset? : Double = 0.0,
  unit? : String,
) -> Recording raise EdfError {
  if signal < 0 ||
    signal >= self.header.signals.length() ||
    self.header.signals[signal].is_annotation() ||
    !finite(scale) ||
    !finite(offset) ||
    scale == 0.0 {
    raise Invalid("invalid physical remapping")
  }
  let h = self.header
  let channel = h.signals[signal]
  let lower = channel.physical_min * scale + offset
  let upper = channel.physical_max * scale + offset
  if !finite(lower) || !finite(upper) || lower == upper {
    raise Invalid("physical remapping is not representable")
  }
  let out = self.data.to_array()
  put_text(
    out,
    256 + h.signals.length() * 104 + signal * 8,
    8,
    header_number(lower),
  )
  put_text(
    out,
    256 + h.signals.length() * 112 + signal * 8,
    8,
    header_number(upper),
  )
  if unit is Some(unit) {
    put_text(out, 256 + h.signals.length() * 96 + signal * 8, 8, unit)
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}

///|
fn header_number(value : Double) -> String raise EdfError {
  let text = value.to_string()
  if text.length() <= 8 {
    return text
  }
  // The normalized a.bcE-n spelling is not always the shortest one:
  // 0.000012345 fits exactly as 12345e-9 in the same eight-byte field.
  compact_decimal(text) catch {
    _ =>
      raise Invalid(
        "physical calibration cannot fit the eight-byte field exactly",
      )
  }
}
