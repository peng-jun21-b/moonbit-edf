///|
fn text_a() -> String {
  "\u00e9🙂,\t\"quoted\"\r\n"
}

///|
fn text_b() -> String {
  "e\u0301🙂,\t\"quoted\"\r\n"
}

///|
fn unicode_source() -> @edf.Recording raise {
  let fast : @edf.Signal = {
    label: "fast",
    transducer: "",
    unit: "uV",
    physical_min: -100.0,
    physical_max: 100.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: 4,
    reserved: "",
  }
  @edf.create(
    [fast, { ..fast, label: "slow", samples_per_record: 2, }],
    [
      {
        onset: "0",
        samples: [[10, 20, 30, 40], [100, 200]],
        events: [
          { onset: "0.25", duration: Some("0.5"), text: text_a(), },
          { onset: "0.25", duration: Some("0.5"), text: text_b(), },
        ],
      },
    ],
    "1",
  )
  .add_annotation_signal()
  .add_annotation("+0.5", "other", record=0, signal=3)
}

///|
fn main raise {
  let source = unicode_source()
  let original = source.find_annotations("0.25", "0.75")[0]
  let target = "\uFEFF" + text_a()
  let updated = @edf.decode(
    source
    .update_annotation(original.annotation_index, {
      ..original.annotation,
      text: target,
    })
    .encode(),
  )
  println(
    "text \{updated.annotations[0].text == target} \{updated.annotations[1].text == text_b()}",
  )
  let indices = updated
    .find_annotations("0.25", "0.75")
    .filter(m => m.annotation.text == target)
    .map(m => m.annotation_index)
  let edited = @edf.decode(updated.remove_annotations(indices).encode())
  println(
    "remaining \{edited.annotations.length()} \{edited.annotations[0].text == text_b()}",
  )
  let fresh = edited.find_annotations("0.25", "0.75")[0]
  let epoch = edited.event_window(
    fresh.annotation_index,
    [0, 1],
    before="0",
    after="0",
    max_samples=3,
  )
  println(
    "epoch \{epoch.samples} \{epoch.channels[0].samples[0].digital} \{epoch.channels[0].samples[1].digital} \{epoch.channels[1].samples[0].digital}",
  )
}
