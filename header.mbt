///|
fn validate_signal(s : Signal, format : Format) -> Unit raise EdfError {
  let low = if format == Edf { -32768 } else { -8388608 }
  let high = if format == Edf { 32767 } else { 8388607 }
  if s.digital_min < low ||
    s.digital_max > high ||
    s.digital_max <= s.digital_min {
    raise Invalid("invalid digital calibration bounds")
  }
  if !finite(s.physical_min) ||
    !finite(s.physical_max) ||
    s.physical_min == s.physical_max ||
    !finite(s.physical_max - s.physical_min) {
    raise Invalid("invalid physical calibration bounds")
  }
  if s.samples_per_record < 1 ||
    s.samples_per_record > 2147483647 / format.width() {
    raise Limit("samples per record out of bounds")
  }
  if s.is_annotation() {
    if s.label !=
      (if format == Edf { "EDF Annotations" } else { "BDF Annotations" }) ||
      s.digital_min != low ||
      s.digital_max != high {
      raise Invalid("invalid annotation channel metadata")
    }
  }
}

///|
pub fn parse_header(data : Bytes) -> Header raise EdfError {
  need(data, 0, 256)
  let format = if part(data, 0, 8) == b"0       " {
    Edf
  } else if part(data, 0, 8) == b"\xffBIOSEMI" {
    Bdf
  } else {
    raise Invalid("not an EDF or BDF signature")
  }
  let ns = integer(text_field(data, 252, 4))
  if ns < 1 {
    raise Invalid("signal count must be positive")
  }
  let bytes = integer(text_field(data, 184, 8))
  if bytes != 256 + ns * 256 {
    raise Invalid("header byte count disagrees with signal count")
  }
  need(data, 0, bytes)
  let reserved = text_field(data, 192, 44)
  let continuity = if reserved.has_prefix("EDF+C") ||
    reserved.has_prefix("BDF+C") {
    Continuous
  } else if reserved.has_prefix("EDF+D") || reserved.has_prefix("BDF+D") {
    Discontinuous
  } else {
    Plain
  }
  if (format == Edf && reserved.has_prefix("BDF+")) ||
    (format == Bdf && reserved.has_prefix("EDF+")) {
    raise Invalid("format and plus signature disagree")
  }
  let patient = text_field(data, 8, 80)
  let recording = text_field(data, 88, 80)
  let date = text_field(data, 168, 8)
  let time = text_field(data, 176, 8)
  let start = parse_recording_datetime(date, time, recording, continuity)
  let declared_records = integer(text_field(data, 236, 8))
  if declared_records < -1 {
    raise Invalid("record count out of range")
  }
  let duration = text_field(data, 244, 8)
  let duration_value = DecimalSeconds::number(duration)
  if duration_value.coefficient.compare_int(0) < 0 {
    raise Invalid("negative record duration")
  }
  let signals = []
  let offsets = []
  let mut record_bytes = 0
  let mut ann = 0
  let mut ordinary = 0
  let mut all_single = true
  for i = 0; i < ns; i = i + 1 {
    let signal : Signal = {
      label: text_field(data, 256 + i * 16, 16),
      transducer: text_field(data, 256 + ns * 16 + i * 80, 80),
      unit: text_field(data, 256 + ns * 96 + i * 8, 8),
      physical_min: number(text_field(data, 256 + ns * 104 + i * 8, 8)),
      physical_max: number(text_field(data, 256 + ns * 112 + i * 8, 8)),
      digital_min: integer(text_field(data, 256 + ns * 120 + i * 8, 8)),
      digital_max: integer(text_field(data, 256 + ns * 128 + i * 8, 8)),
      prefilter: text_field(data, 256 + ns * 136 + i * 80, 80),
      samples_per_record: integer(text_field(data, 256 + ns * 216 + i * 8, 8)),
      reserved: text_field(data, 256 + ns * 224 + i * 32, 32),
    }
    validate_signal(signal, format)
    let size = signal.samples_per_record * format.width()
    if size > 2147483647 - record_bytes {
      raise Limit("record size exceeds runtime address space")
    }
    offsets.push(record_bytes)
    record_bytes += size
    if signal.is_annotation() {
      ann += 1
    } else {
      ordinary += 1
      if signal.samples_per_record != 1 {
        all_single = false
      }
    }
    signals.push(signal)
  }
  if continuity != Plain && ann == 0 {
    raise Invalid("plus recording needs an annotation channel")
  }
  // EDF+ 2.1.2 / programming guidelines item 4: mandatory for EDF+,
  // only a recommendation for plain EDF. Do not infer a BDF+ limit here.
  if format == Edf && continuity != Plain && record_bytes > 61440 {
    raise Invalid("EDF+ data record exceeds 61440 bytes")
  }
  if continuity == Plain && ann > 0 {
    raise Invalid("annotation channel requires plus format marker")
  }
  if duration_value.coefficient.is_zero() &&
    !(continuity != Plain &&
    (ordinary == 0 || (continuity == Discontinuous && all_single))) {
    raise Invalid("zero duration is not allowed for this recording")
  }
  {
    format,
    continuity,
    patient,
    recording,
    date,
    time,
    start,
    reserved,
    declared_records,
    duration,
    signals,
    bytes,
    record_bytes,
    offsets,
  }
}

///|
/// Serialize a complete header, rejecting rather than truncating overwide fields.
fn make_header(
  format : Format,
  continuity : Continuity,
  patient : String,
  recording : String,
  date : String,
  time : String,
  reserved : String,
  count : Int,
  duration : String,
  signals : Array[Signal],
) -> Bytes raise EdfError {
  if signals.length() < 1 {
    raise Invalid("signal count must be positive")
  }
  let ns = signals.length()
  let out = Array::make(256 + ns * 256, b' ')
  copy_bytes(
    out,
    0,
    if format == Edf {
      b"0       "
    } else {
      b"\xffBIOSEMI"
    },
    0,
    8,
  )
  put_text(out, 8, 80, patient)
  put_text(out, 88, 80, recording)
  put_text(out, 168, 8, date)
  put_text(out, 176, 8, time)
  put_text(out, 184, 8, out.length().to_string())
  let marker = if continuity == Plain {
    reserved
  } else {
    (if format == Edf { "EDF+" } else { "BDF+" }) +
    (if continuity == Continuous { "C" } else { "D" })
  }
  put_text(
    out,
    192,
    44,
    if continuity == Plain || reserved.has_prefix(marker) {
      reserved
    } else {
      marker
    },
  )
  put_text(out, 236, 8, count.to_string())
  put_text(out, 244, 8, compact_decimal(duration))
  put_text(out, 252, 4, ns.to_string())
  for i = 0; i < ns; i = i + 1 {
    let s = signals[i]
    put_text(out, 256 + i * 16, 16, s.label)
    put_text(out, 256 + ns * 16 + i * 80, 80, s.transducer)
    put_text(out, 256 + ns * 96 + i * 8, 8, s.unit)
    put_text(out, 256 + ns * 104 + i * 8, 8, header_number(s.physical_min))
    put_text(out, 256 + ns * 112 + i * 8, 8, header_number(s.physical_max))
    put_text(out, 256 + ns * 120 + i * 8, 8, s.digital_min.to_string())
    put_text(out, 256 + ns * 128 + i * 8, 8, s.digital_max.to_string())
    put_text(out, 256 + ns * 136 + i * 80, 80, s.prefilter)
    put_text(out, 256 + ns * 216 + i * 8, 8, s.samples_per_record.to_string())
    put_text(out, 256 + ns * 224 + i * 32, 32, s.reserved)
  }
  let b = Bytes::from_array(out)
  ignore(parse_header(b))
  b
}

///|
// Metadata edits and record repacking do not change ordinary calibration.
// Keep the source fields instead of serializing the approximate Double view.
// Ordinary indices stay in place; an annotation channel may have been added.
fn Recording::preserve_calibration(
  self : Recording,
  header : Bytes,
) -> Bytes raise EdfError {
  let out = header.to_array()
  let old_count = self.header.signals.length()
  let new_count = integer(text_field(header, 252, 4))
  for s in 0..<old_count {
    if self.header.signals[s].is_annotation() {
      continue
    }
    for column in [104, 112] {
      copy_bytes(
        out,
        256 + new_count * column + s * 8,
        self.data,
        256 + old_count * column + s * 8,
        8,
      )
    }
  }
  Bytes::from_array(out)
}
