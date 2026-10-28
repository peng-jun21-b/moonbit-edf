///|
fn interleaved_source() -> @edf.Recording raise {
  let fast : @edf.Signal = {
    label: "fast",
    transducer: "",
    unit: "uV",
    physical_min: -100.0,
    physical_max: 100.0,
    digital_min: -8388608,
    digital_max: 8388607,
    prefilter: "",
    samples_per_record: 4,
    reserved: "",
  }
  let source = @edf.create(
      [fast, { ..fast, label: "slow", samples_per_record: 2, }],
      [
        {
          onset: "0",
          samples: [[1, 2, 3, 4], [100000, -200000]],
          events: [{ onset: "0.25", duration: Some("0.5"), text: "same", }],
        },
        {
          onset: "1",
          samples: [[5, 6, 7, 8], [300000, -400000]],
          events: [{ onset: "1.25", duration: Some("0.5"), text: "later", }],
        },
      ],
      "1",
      format=@edf.Bdf,
    )
    .add_annotation_signal()
    .add_annotation("+0.25", "same", record=0, signal=3)
    .add_annotation("+1.5", "same", record=1, signal=3)
  // Build an imported layout [fast, primary TAL, slow, secondary TAL].
  // The fixture keeps four channels; the tested projection later uses three.
  let raw = source.encode()
  let data = raw.to_array()
  let order = [0, 2, 1, 3]
  for
    (base, width) in [
      (0, 16),
      (16, 80),
      (96, 8),
      (104, 8),
      (112, 8),
      (120, 8),
      (128, 8),
      (136, 80),
      (216, 8),
      (224, 32),
    ] {
    for s in 0..<4 {
      for j in 0..<width {
        data[256 + 4 * base + s * width + j] = raw[256 +
          4 * base +
          order[s] * width +
          j]
      }
    }
  }
  let h = source.header
  for r in 0..<source.records {
    let mut offset = 0
    for old in order {
      let length = h.signals[old].samples_per_record * 3
      for j in 0..<length {
        data[h.bytes + r * h.record_bytes + offset + j] = raw[h.bytes +
          r * h.record_bytes +
          h.offsets[old] +
          j]
      }
      offset += length
    }
  }
  @edf.decode(Bytes::from_array(data))
}

///|
fn main raise {
  let selected = interleaved_source().select([2])
  let matches = selected.find_annotations("0.25", "0.75")
  println("selected \{selected.header.signals[0].label}")
  println(
    "matches \{matches.length()} \{matches[0].annotation.signal} \{matches[1].annotation.signal}",
  )
  let edited = @edf.decode(
    selected.remove_annotations([matches[1].annotation_index]).encode(),
  )
  let fresh = edited.find_annotations("0.25", "0.75")[0]
  let epoch = edited.event_window(
    fresh.annotation_index,
    [0],
    before="0",
    after="0",
    max_samples=1,
  )
  println(
    "epoch \{epoch.samples} \{epoch.channels[0].samples[0].digital} \{epoch.channels[0].samples[0].time.text()}",
  )
}
