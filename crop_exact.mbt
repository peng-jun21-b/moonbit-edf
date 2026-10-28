///|
/// Crop whole records and rebase TAL decimals exactly. Annotation capacity may
/// grow when several negative onsets get longer after the integer-second shift.
pub fn Recording::crop(
  self : Recording,
  first : Int,
  count : Int,
) -> Recording raise EdfError {
  if first < 0 ||
    count < 1 ||
    first >= self.records ||
    count > self.records - first {
    raise Invalid("crop record range out of bounds")
  }
  let h = self.header
  let start = self.exact_starts[first]
  let shift = start.floor_seconds()
  let shifted = DecimalSeconds::number(shift.to_string())
  if h.continuity == Plain && start.compare(shifted) != 0 {
    return self.to_plus().crop(first, count)
  }
  let date = h.start.advance_seconds(shift.to_string())
  if h.continuity == Plain && date.year > 2084 {
    return self.to_plus().crop(first, count)
  }
  let capacities = h.signals.map(s => s.samples_per_record * h.format.width())
  let blocks : Map[Int, Array[Array[Tal]]] = Map([])
  for s in 0..<h.signals.length() {
    if !h.signals[s].is_annotation() {
      continue
    }
    let source_capacity = h.signals[s].samples_per_record * h.format.width()
    let records : Array[Array[Tal]] = []
    for r in 0..<count {
      let source = parse_tals(
        part(
          self.data,
          h.bytes + (first + r) * h.record_bytes + h.offsets[s],
          source_capacity,
        ),
      )
      let changed : Array[Tal] = source.map(t => {
        onset: DecimalSeconds::parse(t.onset, true).sub(shifted).text(true),
        duration: t.duration,
        texts: t.texts,
      })
      let mut bytes = 0
      for tal in changed {
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
      capacities[s] = capacities[s].max(
        (bytes + h.format.width() - 1) / h.format.width() * h.format.width(),
      )
      records.push(changed)
    }
    blocks[s] = records
  }
  let offsets = []
  let mut record_bytes = 0
  for capacity in capacities {
    if capacity > 2147483647 - record_bytes {
      raise Limit("cropped record exceeds runtime address space")
    }
    offsets.push(record_bytes)
    record_bytes += capacity
  }
  if count > (2147483647 - h.bytes) / record_bytes {
    raise Limit("cropped output exceeds runtime address space")
  }
  let out = Array::make(h.bytes + count * record_bytes, b'\x00')
  copy_bytes(out, 0, self.data, 0, h.bytes)
  put_text(out, 168, 8, date.date_field())
  put_text(out, 176, 8, date.time_field())
  put_text(out, 236, 8, count.to_string())
  if h.continuity != Plain {
    put_text(out, 88, 80, date.update_recording_id(h.recording))
  }
  for s in 0..<h.signals.length() {
    if h.signals[s].is_annotation() {
      put_text(
        out,
        256 + h.signals.length() * 216 + s * 8,
        8,
        (capacities[s] / h.format.width()).to_string(),
      )
    }
    for r in 0..<count {
      let destination = h.bytes + r * record_bytes + offsets[s]
      if blocks.get(s) is Some(records) {
        let bytes = encode_tals(records[r], capacities[s])
        copy_bytes(out, destination, bytes, 0, bytes.length())
      } else {
        copy_bytes(
          out,
          destination,
          self.data,
          h.bytes + (first + r) * h.record_bytes + h.offsets[s],
          capacities[s],
        )
      }
    }
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}
