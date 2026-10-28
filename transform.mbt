///|
/// Select ordinary channels, preserving all annotation channels and record timing.
pub fn Recording::select(
  self : Recording,
  indices : Array[Int],
) -> Recording raise EdfError {
  if indices.is_empty() {
    raise Invalid("select at least one ordinary channel")
  }
  let selected = indices.copy()
  let seen : Map[Int, Bool] = Map([])
  for s in indices {
    if s < 0 ||
      s >= self.header.signals.length() ||
      self.header.signals[s].is_annotation() {
      raise Invalid("selection requires ordinary signal indices")
    }
    if seen.contains(s) {
      raise Invalid("duplicate selected signal")
    }
    seen[s] = true
  }
  for s = 0; s < self.header.signals.length(); s = s + 1 {
    if self.header.signals[s].is_annotation() {
      selected.push(s)
    }
  }
  let n = selected.length()
  let oldn = self.header.signals.length()
  let hs = 256 + n * 256
  let mut rs = 0
  for s in selected {
    rs += self.header.signals[s].samples_per_record * self.header.format.width()
  }
  let out = Array::make(hs + rs * self.records, b'\x00')
  copy_bytes(out, 0, self.data, 0, 256)
  put_text(out, 184, 8, hs.to_string())
  put_text(out, 252, 4, n.to_string())
  put_text(out, 236, 8, self.records.to_string())
  let mut cumulative = 0
  for width in [16, 80, 8, 8, 8, 8, 8, 80, 8, 32] {
    for i = 0; i < n; i = i + 1 {
      copy_bytes(
        out,
        256 + n * cumulative + i * width,
        self.data,
        256 + oldn * cumulative + selected[i] * width,
        width,
      )
    }
    cumulative += width
  }
  for r = 0; r < self.records; r = r + 1 {
    let mut at = hs + r * rs
    for s in selected {
      let size = self.header.signals[s].samples_per_record *
        self.header.format.width()
      copy_bytes(
        out,
        at,
        self.data,
        self.header.bytes +
        r * self.header.record_bytes +
        self.header.offsets[s],
        size,
      )
      at += size
    }
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}

///|
/// Promote a plain recording to plus without altering its samples/calibration text.
/// Existing plus files are returned unchanged. Plain identification strings are
/// preserved as annotations; unknown plus patient subfields are explicitly X.
pub fn Recording::to_plus(self : Recording) -> Recording raise EdfError {
  let h = self.header
  if h.continuity != Plain {
    return self
  }
  let ns = h.signals.length()
  if ns >= 9999 {
    raise Invalid("signal count cannot fit the four-character header field")
  }
  let dt = h.start
  let label = if h.format == Edf {
    "EDF Annotations"
  } else {
    "BDF Annotations"
  }
  let payloads = Array::makei(self.records, r => {
    let tals : Array[Tal] = [
      { onset: self.exact_starts[r].text(true), duration: None, texts: [""], },
    ]
    if r == 0 && !h.recording.is_empty() {
      tals.push({
        onset: "+0",
        duration: None,
        texts: ["Original recording ID: " + h.recording],
      })
    }
    if r == 0 && !h.patient.is_empty() {
      tals.push({
        onset: "+0",
        duration: None,
        texts: ["Original patient ID: " + h.patient],
      })
    }
    tals
  })
  let mut capacity = h.format.width()
  for tals in payloads {
    capacity = capacity.max(tal_payload(tals).length())
  }
  let samples = (capacity + h.format.width() - 1) / h.format.width()
  let width = samples * h.format.width()
  let hs = 256 + (ns + 1) * 256
  let rs = h.record_bytes + width
  if rs < h.record_bytes || self.records > (2147483647 - hs) / rs {
    raise Limit("promoted recording exceeds resource limit")
  }
  let out = Array::make(hs + self.records * rs, b'\x00')
  copy_bytes(out, 0, self.data, 0, 256)
  put_text(out, 184, 8, hs.to_string())
  put_text(out, 192, 44, if h.format == Edf { "EDF+C" } else { "BDF+C" })
  put_text(out, 252, 4, (ns + 1).to_string())
  put_text(out, 236, 8, self.records.to_string())
  put_text(out, 88, 80, "Startdate " + dt.long_date() + " X X X")
  // A plain patient field may be empty or free text. It is not a structured
  // plus patient ID: do not infer sex, birthdate or administrative identity.
  put_text(out, 8, 80, "X X X X")
  let vals = [
    label,
    "",
    "",
    "-1",
    "1",
    if h.format == Edf {
      "-32768"
    } else {
      "-8388608"
    },
    if h.format == Edf {
      "32767"
    } else {
      "8388607"
    },
    "",
    samples.to_string(),
    "",
  ]
  let mut cumulative = 0
  let widths = [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]
  for i = 0; i < widths.length(); i = i + 1 {
    let w = widths[i]
    copy_bytes(
      out,
      256 + (ns + 1) * cumulative,
      self.data,
      256 + ns * cumulative,
      ns * w,
    )
    put_text(out, 256 + (ns + 1) * cumulative + ns * w, w, vals[i])
    cumulative += w
  }
  for r = 0; r < self.records; r = r + 1 {
    copy_bytes(
      out,
      hs + r * rs,
      self.data,
      h.bytes + r * h.record_bytes,
      h.record_bytes,
    )
    let b = encode_tals(payloads[r], width)
    copy_bytes(out, hs + r * rs + h.record_bytes, b, 0, width)
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}
