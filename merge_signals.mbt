///|
/// Combine channels on an already identical native record grid. The caller
/// must explicitly confirm a common clock; equality of headers is not proof.
/// No offsets, resampling, label matching or inferred synchronization occurs.
/// Original signal header columns and complete record signal blocks are copied
/// verbatim. Mixed plain/plus inputs reuse to_plus's documented promotion.
/// The effective left global header and reading policy are retained, apart
/// from required header-size/signal-count/final-count/continuity fields.
pub fn Recording::merge_signals(
  self : Recording,
  other : Recording,
  common_clock~ : Bool,
) -> Recording raise EdfError {
  if !common_clock {
    raise Invalid("merge signals requires confirmed common clock")
  }
  if self.header.format != other.header.format {
    raise Invalid("merge signals requires the same EDF/BDF format")
  }
  if self.header.start.civil_seconds() != other.header.start.civil_seconds() {
    raise Invalid("merge signals header zeros differ")
  }
  if self.records != other.records {
    raise Invalid("merge signals record counts differ")
  }
  if self.exact_duration.compare(other.exact_duration) != 0 {
    raise Invalid("merge signals record durations differ")
  }
  for r in 0..<self.records {
    if self.exact_starts[r].compare(other.exact_starts[r]) != 0 {
      raise Invalid("merge signals record starts differ at \{r}")
    }
  }
  let plain = self.header.continuity == Plain &&
    other.header.continuity == Plain
  let left = if plain { self } else { self.to_plus() }
  let right = if plain { other } else { other.to_plus() }
  let ln = left.header.signals.length()
  let rn = right.header.signals.length()
  if ln > 9999 - rn {
    raise Limit("merged signal count exceeds four-byte header field")
  }
  if self.records > 99999999 {
    raise Limit("merged record count exceeds eight-byte header field")
  }
  if right.header.record_bytes > 2147483647 - left.header.record_bytes {
    raise Limit("merged record exceeds runtime address space")
  }
  let n = ln + rn
  let hs = 256 + n * 256
  let header = Array::make(hs, b' ')
  copy_bytes(header, 0, left.data, 0, 256)
  put_text(header, 184, 8, hs.to_string())
  put_text(header, 236, 8, self.records.to_string())
  put_text(header, 252, 4, n.to_string())
  if !plain {
    let discontinuous = left.header.continuity == Discontinuous ||
      right.header.continuity == Discontinuous
    let marker = if left.header.format == Edf {
      if discontinuous {
        b"EDF+D"
      } else {
        b"EDF+C"
      }
    } else if discontinuous {
      b"BDF+D"
    } else {
      b"BDF+C"
    }
    // Change only the required marker, retaining all 39 original suffix bytes.
    copy_bytes(header, 192, marker, 0, 5)
  }
  let mut column = 0
  for width in [16, 80, 8, 8, 8, 8, 8, 80, 8, 32] {
    copy_bytes(
      header,
      256 + n * column,
      left.data,
      256 + ln * column,
      ln * width,
    )
    copy_bytes(
      header,
      256 + n * column + ln * width,
      right.data,
      256 + rn * column,
      rn * width,
    )
    column += width
  }
  let header = Bytes::from_array(header)
  // Existing header validation enforces EDF+ record size and metadata rules;
  // no new BDF bound or narrower legal input range is substituted here.
  let parsed = parse_header(header)
  if self.records > (2147483647 - hs) / parsed.record_bytes {
    raise Limit("merged recording exceeds runtime address space")
  }
  let out = Array::make(hs + self.records * parsed.record_bytes, b'\x00')
  copy_bytes(out, 0, header, 0, hs)
  for r in 0..<self.records {
    let destination = hs + r * parsed.record_bytes
    copy_bytes(
      out,
      destination,
      left.data,
      left.header.bytes + r * left.header.record_bytes,
      left.header.record_bytes,
    )
    copy_bytes(
      out,
      destination + left.header.record_bytes,
      right.data,
      right.header.bytes + r * right.header.record_bytes,
      right.header.record_bytes,
    )
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}
