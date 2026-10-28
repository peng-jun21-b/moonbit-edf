///|
/// Decode complete records; unknown (-1) count is inferred only when no partial record remains.
pub fn decode(
  data : Bytes,
  time_policy? : TimePolicy = Strict,
) -> Recording raise EdfError {
  let h = parse_header(data)
  let payload = data.length() - h.bytes
  if payload % h.record_bytes != 0 {
    raise Invalid("partial trailing data record")
  }
  let records = payload / h.record_bytes
  if h.declared_records != -1 && h.declared_records != records {
    raise Invalid("declared record count disagrees with file length")
  }
  let starts = []
  let annotations : Array[Annotation] = []
  let exact_starts : Array[DecimalSeconds] = []
  let exact_duration = DecimalSeconds::number(h.duration)
  let tolerance = match time_policy {
    Strict => DecimalSeconds::number("0")
    Tolerance(text) => DecimalSeconds::number(text)
  }
  if tolerance.coefficient.compare_int(0) < 0 {
    raise Invalid("negative time tolerance")
  }
  let annotation_only = h.signals.all(s => s.is_annotation())
  for r = 0; r < records; r = r + 1 {
    let mut exact_onset = exact_duration.times(r)
    let mut first = true
    for s = 0; s < h.signals.length(); s = s + 1 {
      let signal = h.signals[s]
      if !signal.is_annotation() {
        continue
      }
      let bytes = part(
        data,
        h.bytes + r * h.record_bytes + h.offsets[s],
        signal.samples_per_record * h.format.width(),
      )
      let tals = parse_tals(bytes)
      if first {
        if tals.is_empty() ||
          tals[0].texts.is_empty() ||
          tals[0].texts[0] != "" ||
          tals[0].duration is Some(_) {
          raise Invalid("missing first timekeeping TAL")
        }
        exact_onset = DecimalSeconds::parse(tals[0].onset, true)
        if annotation_only &&
          (tals[0].texts.length() < 2 || tals[0].texts[1].is_empty()) {
          raise Invalid(
            "annotation-only record needs an event in its first TAL",
          )
        }
        first = false
      }
      for tal in tals {
        let time = tal.onset
        let duration = match tal.duration {
          Some(d) => Some(d)
          None => None
        }
        for text in tal.texts {
          if text.is_empty() {
            continue
          }
          annotations.push({
            record: r,
            signal: s,
            onset: time,
            duration,
            text,
          })
        }
      }
    }
    if h.continuity != Plain &&
      r == 0 &&
      (
        exact_onset.coefficient.compare_int(0) < 0 ||
        exact_onset.compare(DecimalSeconds::number("1")) >= 0
      ) {
      raise Invalid(
        "first record onset must be a nonnegative fraction of a second",
      )
    }
    if r > 0 {
      let expected = exact_starts[r - 1].add(exact_duration)
      if exact_onset.compare(expected.sub(tolerance)) < 0 {
        raise Invalid("record times overlap or go backwards")
      }
      let delta = exact_onset.sub(expected)
      if h.continuity == Continuous &&
        (
          delta.compare(tolerance) > 0 ||
          delta.compare(DecimalSeconds::number("0").sub(tolerance)) < 0
        ) {
        raise Invalid("continuous marker contradicts exact timekeeping TALs")
      }
    }
    starts.push(exact_onset.text(true))
    exact_starts.push(exact_onset)
  }
  {
    header: h,
    data,
    records,
    starts,
    annotations,
    time_policy,
    exact_starts,
    exact_duration,
  }
}

///|
/// Preserve original header spelling, padding and TAL bytes; finalize unknown record count.
pub fn Recording::encode(self : Recording) -> Bytes raise EdfError {
  let out = self.data.to_array()
  put_text(out, 236, 8, self.records.to_string())
  Bytes::from_array(out)
}

///|
pub fn Recording::digital(
  self : Recording,
  signal : Int,
  record : Int,
  sample : Int,
) -> Int raise EdfError {
  let h = self.header
  if signal < 0 ||
    signal >= h.signals.length() ||
    record < 0 ||
    record >= self.records {
    raise Invalid("signal or record index out of range")
  }
  let s = h.signals[signal]
  if s.is_annotation() {
    raise Invalid("annotation channel is not a numeric signal")
  }
  if sample < 0 || sample >= s.samples_per_record {
    raise Invalid("sample index out of range")
  }
  read_sample(
    self.data,
    h.bytes +
    record * h.record_bytes +
    h.offsets[signal] +
    sample * h.format.width(),
    h.format.width(),
  )
}

///|
pub fn Signal::to_physical(
  self : Signal,
  digital : Int,
) -> Double raise EdfError {
  if self.is_annotation() {
    raise Invalid("cannot scale annotations")
  }
  if self.digital_max <= self.digital_min ||
    self.physical_max == self.physical_min {
    raise Invalid("invalid calibration")
  }
  let v = (digital.to_double() - self.digital_min.to_double()) /
    (self.digital_max.to_double() - self.digital_min.to_double()) *
    (self.physical_max - self.physical_min) +
    self.physical_min
  if !finite(v) {
    raise Limit("physical calibration overflow")
  }
  v
}

///|
/// Round to nearest digital step, rejecting out-of-range values instead of clipping.
pub fn Signal::to_digital(
  self : Signal,
  physical : Double,
) -> Int raise EdfError {
  if !finite(physical) ||
    self.is_annotation() ||
    self.digital_max <= self.digital_min ||
    self.physical_max == self.physical_min {
    raise Invalid("invalid physical value or calibration")
  }
  let fraction = (physical - self.physical_min) /
    (self.physical_max - self.physical_min)
  if !finite(fraction) || fraction < 0.0 || fraction > 1.0 {
    raise Invalid("physical value outside calibration range")
  }
  let value = fraction *
    (self.digital_max.to_double() - self.digital_min.to_double()) +
    self.digital_min.to_double()
  value.round().to_int()
}

///|
pub fn Recording::physical(
  self : Recording,
  signal : Int,
  record : Int,
  sample : Int,
) -> Double raise EdfError {
  let value = self.digital(signal, record, sample)
  self.header.signals[signal].to_physical(value)
}

///|
#alias(sample_time_exact)
pub fn Recording::sample_time(
  self : Recording,
  signal : Int,
  record : Int,
  sample : Int,
) -> Time raise EdfError {
  ignore(self.digital(signal, record, sample))
  self.exact_starts[record]
  .as_time()
  .add(
    self.exact_duration
    .as_time()
    .scale(sample, denominator=self.header.signals[signal].samples_per_record),
  )
}

///|
pub fn Recording::sample_rate(
  self : Recording,
  signal : Int,
) -> Time raise EdfError {
  if signal < 0 ||
    signal >= self.header.signals.length() ||
    self.header.signals[signal].is_annotation() {
    raise Invalid("ordinary signal index required")
  }
  if self.exact_duration.coefficient.is_zero() {
    raise Invalid("zero-duration records have no sampling rate")
  }
  let duration = self.exact_duration.as_time()
  time_ratio(
    @bigint.BigInt::from_int(self.header.signals[signal].samples_per_record) *
    @bigint.BigInt::from_string(duration.denominator),
    @bigint.BigInt::from_string(duration.numerator),
  )
}

///|
/// Construct EDF/BDF with ordinary channels and optional plus annotations.
#alias(create_exact)
pub fn[T : TimeInput] create(
  signals : Array[Signal],
  records : Array[Record[T]],
  duration : T,
  format? : Format = Edf,
  continuity? : Continuity = Continuous,
  start? : DateTime = {
    year: 2020,
    month: 1,
    day: 1,
    hour: 0,
    minute: 0,
    second: 0,
  },
  patient? : String = "X X X X",
) -> Recording raise EdfError {
  let duration = DecimalSeconds::number(TimeInput::to_time_text(duration)).text(
    false,
  )
  let records : Array[Record[String]] = records.map(record => {
    let events : Array[Event[String]] = record.events.map(event => {
      onset: DecimalSeconds::number(TimeInput::to_time_text(event.onset)).text(
        true,
      ),
      duration: match event.duration {
        None => None
        Some(value) =>
          Some(
            DecimalSeconds::number(TimeInput::to_time_text(value)).text(false),
          )
      },
      text: event.text,
    })
    {
      onset: DecimalSeconds::number(TimeInput::to_time_text(record.onset)).text(
        true,
      ),
      samples: record.samples,
      events,
    }
  })
  start.validate()
  for s in signals {
    validate_signal(s, format)
    if s.is_annotation() {
      raise Invalid("create adds the annotation channel automatically")
    }
  }
  let channels = signals.copy()
  let blocks = []
  let mut annotation_samples = 32
  if continuity != Plain {
    for r in records {
      let tals : Array[Tal] = []
      let first_texts = [""]
      if signals.is_empty() {
        if r.events.is_empty() ||
          DecimalSeconds::parse(r.events[0].onset, true).compare(
            DecimalSeconds::parse(r.onset, true),
          ) !=
          0 ||
          r.events[0].duration is Some(_) ||
          r.events[0].text.is_empty() {
          raise Invalid(
            "annotation-only record requires a first untimed-duration event at record onset",
          )
        }
        first_texts.push(r.events[0].text)
      }
      tals.push({ onset: r.onset, duration: None, texts: first_texts, })
      for event_index = (if signals.is_empty() { 1 } else { 0 })
          event_index < r.events.length()
          event_index = event_index + 1 {
        let event = r.events[event_index]
        tals.push({
          onset: event.onset,
          duration: match event.duration {
            Some(d) => Some(d)
            None => None
          },
          texts: [event.text],
        })
      }
      // Determine byte capacity without a record-sized temporary allocation.
      let mut bytes = 0
      for tal in tals {
        bytes += @utf8.encode(
          tal.onset +
          (match tal.duration {
            Some(d) => "\u0015" + d
            None => ""
          }) +
          "\u0014" +
          tal.texts.join("\u0014") +
          "\u0014\u0000",
        ).length()
      }
      annotation_samples = annotation_samples.max(
        (bytes + format.width() - 1) / format.width(),
      )
      blocks.push(tals)
    }
    channels.push({
      label: if format == Edf {
        "EDF Annotations"
      } else {
        "BDF Annotations"
      },
      transducer: "",
      unit: "",
      physical_min: -1.0,
      physical_max: 1.0,
      digital_min: if format == Edf {
        -32768
      } else {
        -8388608
      },
      digital_max: if format == Edf {
        32767
      } else {
        8388607
      },
      prefilter: "",
      samples_per_record: annotation_samples,
      reserved: "",
    })
  } else {
    for i = 0; i < records.length(); i = i + 1 {
      if !records[i].events.is_empty() ||
        DecimalSeconds::parse(records[i].onset, true).compare(
          DecimalSeconds::number(duration).times(i),
        ) !=
        0 {
        raise Invalid(
          "plain recording cannot store events or discontinuous times",
        )
      }
    }
  }
  let header_bytes = make_header(
    format,
    continuity,
    patient,
    "Startdate " + start.long_date() + " X X X",
    start.date_field(),
    start.time_field(),
    "",
    records.length(),
    duration,
    channels,
  )
  let h = parse_header(header_bytes)
  if records.length() > (2147483647 - h.bytes) / h.record_bytes {
    raise Limit("output exceeds runtime Bytes address space")
  }
  let out = Array::make(h.bytes + records.length() * h.record_bytes, b'\x00')
  copy_bytes(out, 0, header_bytes, 0, header_bytes.length())
  for r = 0; r < records.length(); r = r + 1 {
    let record = records[r]
    if record.samples.length() != signals.length() {
      raise Invalid("record channel count mismatch")
    }
    for s = 0; s < signals.length(); s = s + 1 {
      let values = record.samples[s]
      let signal = signals[s]
      if values.length() != signal.samples_per_record {
        raise Invalid("record sample count mismatch")
      }
      for j = 0; j < values.length(); j = j + 1 {
        let v = values[j]
        if v < signal.digital_min || v > signal.digital_max {
          raise Invalid("sample outside digital calibration limits")
        }
        put_sample(
          out,
          h.bytes + r * h.record_bytes + h.offsets[s] + j * format.width(),
          format.width(),
          v,
        )
      }
    }
    if continuity != Plain {
      let bytes = encode_tals(blocks[r], annotation_samples * format.width())
      copy_bytes(
        out,
        h.bytes + r * h.record_bytes + h.offsets[signals.length()],
        bytes,
        0,
        bytes.length(),
      )
    }
  }
  decode(Bytes::from_array(out))
}
