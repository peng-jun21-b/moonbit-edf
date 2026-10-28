///|
fn integer_gcd(left : Int, right : Int) -> Int {
  let mut a = left
  let mut b = right
  while b != 0 {
    let remainder = a % b
    a = b
    b = remainder
  }
  a
}

///|
/// Extract [start,end) using the exact sample clock and repack records. The
/// output retains every selected sample at its original time and digital value.
/// EDF requires a shared record origin and a finite decimal record duration;
/// a selection which cannot express those invariants is rejected explicitly.
pub fn Recording::crop_time_window(
  self : Recording,
  start_seconds : String,
  end_seconds : String,
) -> Recording raise EdfError {
  self.crop_time_window_repack(start_seconds, end_seconds, 1)
}

///|
fn Recording::crop_time_window_repack(
  self : Recording,
  start_seconds : String,
  end_seconds : String,
  split : Int,
) -> Recording raise EdfError {
  let lower = Time::parse(start_seconds)
  let upper = Time::parse(end_seconds)
  if lower >= upper {
    raise Invalid("crop window requires start < end")
  }
  // Inspect source samples before promoting: a large plain EDF record may
  // legitimately crop into a small EDF+ record even when full promotion fails.
  let source = self
  let h = source.header
  let ordinary = Array::makei(h.signals.length(), i => i).filter(i => {
    !h.signals[i].is_annotation()
  })
  if ordinary.is_empty() || source.exact_duration.coefficient.is_zero() {
    let indices = Array::makei(source.records, i => i).filter(i => {
      source.exact_starts[i].as_time() >= lower &&
      source.exact_starts[i].as_time() < upper
    })
    if indices.is_empty() {
      raise Invalid("crop window contains no records")
    }
    let result = source.crop(indices[0], indices.length())
    let shift = source.exact_starts[indices[0]].floor_seconds()
    let origin = Time::parse(shift.to_string())
    return result.with_annotations(
      result.annotations.filter(event => {
        let time = Time::parse(event.onset).add(origin)
        time >= lower && time < upper
      }),
    )
  }
  let reference = ordinary[0]
  let per = h.signals[reference].samples_per_record
  let duration = source.exact_duration.as_time()
  if duration <= Time::parse("0") {
    raise Invalid("ordinary samples require a positive record duration")
  }
  let spans : Array[(Int, Array[Int], Int)] = []
  let mut group = 0
  for r in 0..<source.records {
    let onset = source.exact_starts[r].as_time()
    let firsts = h.signals.map(s => {
      if s.is_annotation() {
        0
      } else {
        exact_lower_bound(onset, duration, s.samples_per_record, lower)
      }
    })
    let lasts = h.signals.map(s => {
      if s.is_annotation() {
        0
      } else {
        exact_lower_bound(onset, duration, s.samples_per_record, upper)
      }
    })
    let count = lasts[reference] - firsts[reference]
    let first = onset.add(duration.scale(firsts[reference], denominator=per))
    let length = duration.scale(count, denominator=per)
    for s in ordinary {
      let n = lasts[s] - firsts[s]
      if (count == 0) != (n == 0) ||
        (
          n > 0 &&
          (
            onset.add(
              duration.scale(
                firsts[s],
                denominator=h.signals[s].samples_per_record,
              ),
            ) !=
            first ||
            duration.scale(n, denominator=h.signals[s].samples_per_record) !=
            length
          )
        ) {
        raise Invalid(
          "selected channels have different sample origins or extents; EDF cannot losslessly express this window without resampling",
        )
      }
    }
    if count > 0 {
      spans.push((r, firsts, count))
      group = integer_gcd(group, count)
    }
  }
  if spans.is_empty() {
    raise Invalid("crop window contains no samples")
  }
  group = group / split
  let channels = h.signals.copy()
  if h.continuity == Plain {
    channels.push({
      label: if h.format == Edf {
        "EDF Annotations"
      } else {
        "BDF Annotations"
      },
      transducer: "",
      unit: "",
      physical_min: -1.0,
      physical_max: 1.0,
      digital_min: if h.format == Edf {
        -32768
      } else {
        -8388608
      },
      digital_max: if h.format == Edf {
        32767
      } else {
        8388607
      },
      prefilter: "",
      samples_per_record: 1,
      reserved: "",
    })
  }
  let record_duration = duration.scale(group, denominator=per)
  let duration_text = record_duration.text()
  if duration_text.contains("/") {
    raise Invalid("EDF record duration requires a finite decimal")
  }
  // Header field constraints are intrinsic to EDF, rather than time precision.
  let header_duration = compact_decimal(duration_text)
  let samples = channels.map(s => {
    if s.is_annotation() {
      1
    } else {
      let numerator = group.to_int64() * s.samples_per_record.to_int64()
      if numerator % per.to_int64() != 0 {
        raise Invalid(
          "selected sample rates cannot share the new record duration",
        )
      }
      (numerator / per.to_int64()).to_int()
    }
  })
  let pieces : Array[(Int, Array[Int], Time)] = []
  for (r, firsts, count) in spans {
    for k in 0..<(count / group) {
      let offsets = firsts.mapi((s, j) => j + k * samples[s])
      let onset = source.exact_starts[r]
        .as_time()
        .add(duration.scale(offsets[reference], denominator=per))
      if onset.text().contains("/") {
        raise Invalid("EDF TAL timekeeping requires a finite decimal origin")
      }
      pieces.push((r, offsets, onset))
    }
  }
  let origin = DecimalSeconds::number(pieces[0].2.text()).floor_seconds()
  let shift = Time::parse(origin.to_string())
  let date = h.start.advance_seconds(origin.to_string())
  let onsets = pieces.map(p => {
    DecimalSeconds::number(p.2.sub(shift).text()).text(true)
  })
  let blocks : Array[Array[Array[Tal]]] = Array::makei(channels.length(), _ => {
    Array::makei(pieces.length(), _ => [])
  })
  let annotation_signals = Array::makei(channels.length(), i => i).filter(i => {
    channels[i].is_annotation()
  })
  for r in 0..<pieces.length() {
    blocks[annotation_signals[0]][r].push({
      onset: onsets[r],
      duration: None,
      texts: [""],
    })
  }
  let events = source.annotations.copy()
  if h.continuity == Plain {
    // Match ordinary to_plus metadata preservation, without constructing an
    // oversized intermediate file. The normal window filter still applies.
    for
      (prefix, text) in [
        ("Original recording ID: ", h.recording),
        ("Original patient ID: ", h.patient),
      ] {
      if !text.is_empty() {
        events.push({
          record: 0,
          signal: annotation_signals[0],
          onset: "+0",
          duration: None,
          text: prefix + text,
        })
      }
    }
  }
  for event in events {
    let time = Time::parse(event.onset)
    if time < lower || time >= upper {
      continue
    }
    let mut record = 0
    for r in 0..<pieces.length() {
      if pieces[r].2 <= time {
        record = r
      }
    }
    blocks[event.signal][record].push({
      onset: DecimalSeconds::number(time.sub(shift).text()).text(true),
      duration: event.duration,
      texts: [event.text],
    })
  }
  let chosen = channels.mapi((s, channel) => {
    if !channel.is_annotation() {
      return { ..channel, samples_per_record: samples[s], }
    }
    let mut bytes = h.format.width()
    for record in blocks[s] {
      bytes = bytes.max(tal_payload(record).length())
    }
    {
      ..channel,
      samples_per_record: (bytes + h.format.width() - 1) / h.format.width(),
    }
  })
  let mut continuity = Continuous
  for r in 1..<pieces.length() {
    if pieces[r - 1].2.add(record_duration) != pieces[r].2 {
      continuity = Discontinuous
    }
  }
  let record_bytes = chosen.fold(init=0, (size, s) => {
    size + s.samples_per_record * h.format.width()
  })
  if h.format == Edf && record_bytes > 61440 {
    let mut common = 0
    for s in ordinary {
      common = integer_gcd(common, samples[s])
    }
    if finite_record_divisor(record_duration, common) is Some(divisor) {
      return self.crop_time_window_repack(
        start_seconds,
        end_seconds,
        split * divisor,
      )
    }
    raise Invalid("EDF+ data record exceeds 61440 bytes")
  }
  let recording = if h.continuity == Plain {
    "Startdate " + date.long_date() + " X X X"
  } else {
    date.update_recording_id(h.recording)
  }
  let header = make_header(
    h.format,
    continuity,
    if h.continuity == Plain {
      "X X X X"
    } else {
      h.patient
    },
    recording,
    date.date_field(),
    date.time_field(),
    "",
    pieces.length(),
    header_duration,
    chosen,
  )
  let header = source.preserve_calibration(header)
  let parsed = parse_header(header)
  if pieces.length() > (2147483647 - parsed.bytes) / parsed.record_bytes {
    raise Invalid("cropped bytes exceed runtime address space")
  }
  let out = Array::make(
    parsed.bytes + pieces.length() * parsed.record_bytes,
    b'\x00',
  )
  copy_bytes(out, 0, header, 0, header.length())
  for r in 0..<pieces.length() {
    for s in 0..<chosen.length() {
      let at = parsed.bytes + r * parsed.record_bytes + parsed.offsets[s]
      let capacity = chosen[s].samples_per_record * h.format.width()
      if chosen[s].is_annotation() {
        let bytes = encode_tals(blocks[s][r], capacity)
        copy_bytes(out, at, bytes, 0, capacity)
      } else {
        copy_bytes(
          out,
          at,
          source.data,
          h.bytes +
          pieces[r].0 * h.record_bytes +
          h.offsets[s] +
          pieces[r].1[s] * h.format.width(),
          capacity,
        )
      }
    }
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}

///|
// Splitting must keep every channel's sample count integral and the record
// duration finite-decimal. Test prime factors only, without a linear scan up
// to a potentially large sample count. Each successful retry reduces group.
fn finite_record_divisor(duration : Time, common : Int) -> Int? raise EdfError {
  let mut remaining = common
  let mut divisor = 2
  while divisor <= remaining / divisor {
    if remaining % divisor == 0 {
      if record_duration_fits(duration.scale(1, denominator=divisor)) {
        return Some(divisor)
      }
      while remaining % divisor == 0 {
        remaining = remaining / divisor
      }
    }
    divisor += 1
  }
  if remaining > 1 &&
    record_duration_fits(duration.scale(1, denominator=remaining)) {
    Some(remaining)
  } else {
    None
  }
}

///|
fn record_duration_fits(duration : Time) -> Bool {
  let text = duration.text()
  if text.contains("/") {
    return false
  }
  try {
    ignore(compact_decimal(text))
    true
  } catch {
    _ => false
  }
}

///|
fn compact_decimal(text : String) -> String raise EdfError {
  let value = DecimalSeconds::number(text)
  let canonical = value.text(false)
  if canonical.length() <= 8 {
    return canonical
  }
  // Header numeric fields allow a leading decimal point. Adding an
  // unnecessary zero must not reject an otherwise exact eight-byte value.
  let without_zero = if canonical.has_prefix("0.") {
    canonical[1:].to_owned()
  } else if canonical.has_prefix("-0.") {
    "-" + canonical[2:].to_owned()
  } else {
    canonical
  }
  if without_zero.length() <= 8 {
    return without_zero
  }
  let digits = value.coefficient.to_string()
  let mut end = digits.length()
  while end > 1 && digits[end - 1] == '0' {
    end -= 1
  }
  let scientific = digits[0:end].to_owned() +
    "e" +
    (digits.length() - end - value.scale).to_string()
  if scientific.length() > 8 {
    raise Invalid("exact record duration cannot fit the eight-byte EDF field")
  }
  scientific
}
