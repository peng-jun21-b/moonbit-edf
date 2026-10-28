///|
fn append_part(right : Bool) -> @edf.Recording raise {
  let fast : @edf.Signal = {
    label: "fast",
    transducer: "",
    unit: "uV",
    physical_min: 0.0,
    physical_max: 1.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: 3,
    reserved: "",
  }
  let source = @edf.create(
      [fast, { ..fast, label: "slow", samples_per_record: 1, }],
      [
        {
          onset: "0",
          samples: if right {
            [[14, 15, 16], [22]]
          } else {
            [[11, 12, 13], [21]]
          },
          events: [
            {
              onset: if right {
                "-0.5"
              } else {
                "1"
              },
              duration: Some("1"),
              text: if right {
                "late-note"
              } else {
                "left-stage"
              },
            },
          ],
        },
      ],
      "1.5",
    )
    .add_annotation_signal()
    .add_annotation(
      if right {
        "+0.5"
      } else {
        "+0.25"
      },
      if right {
        "other"
      } else {
        "left"
      },
      record=0,
      signal=3,
    )
  // Model an acquired calibration spelling below the Double minimum view.
  let data = source.encode().to_array()
  let literal = b"1e-324  "
  for i in 0..<8 {
    data[256 + source.header.signals.length() * 104 + i] = literal[i]
  }
  @edf.decode(Bytes::from_array(data))
}

///|
fn calibration_min(source : @edf.Recording) -> Bytes raise {
  let data = source.encode()
  Bytes::makei(8, i => data[256 + source.header.signals.length() * 104 + i])
}

///|
fn main raise {
  let joined = @edf.decode(
    append_part(false).append(append_part(true), offset="1.5").encode(),
  )
  let matches = joined.find_annotations("1.25", "1.75")
  println(
    "matches \{matches.length()} \{matches[0].annotation.record} \{matches[1].annotation.record}",
  )
  let edited = @edf.decode(
    joined
    .update_annotation(matches[1].annotation_index, {
      ..matches[1].annotation,
      text: "reviewed-right",
    })
    .encode(),
  )
  let fresh = edited.find_annotations("1.25", "1.75")[1]
  let epoch = edited.event_window(
    fresh.annotation_index,
    [0, 1],
    before="0",
    after="0",
    max_samples=3,
  )
  let calibration_ok = calibration_min(edited) == b"1e-324  "
  println("calibration \{calibration_ok}")
  println(
    "epoch \{epoch.samples} \{epoch.channels[0].samples[0].digital} \{epoch.channels[0].samples[1].digital} \{epoch.channels[1].samples[0].digital}",
  )
}
