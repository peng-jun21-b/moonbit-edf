///|
fn calibration_source() -> @edf.Recording raise {
  let fast : @edf.Signal = {
    label: "fast",
    transducer: "",
    unit: "uV",
    physical_min: -32768.0,
    physical_max: 32767.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: 6,
    reserved: "",
  }
  @edf.create(
    [fast, { ..fast, label: "slow", samples_per_record: 3, }],
    [
      {
        onset: "0",
        samples: [[-4, -2, 0, 2, 4, 6], [10, 20, 30]],
        events: [{ onset: "0.5", duration: Some("0.75"), text: "stage", }],
      },
    ],
    "2",
  )
  .add_annotation_signal()
  .add_annotation("+0.75", "keep", record=0, signal=3)
}

///|
fn close_to(actual : Double, expected : Double) -> Bool {
  (actual - expected).abs() <= 1.0e-8
}

///|
fn main raise {
  let source = calibration_source()
  let mapped = @edf.decode(
    source.map_physical(0, -2.0, offset=5.0, unit="arb").encode(),
  )
  let original = mapped.find_annotations("1/3", "4/3")[0]
  let edited = @edf.decode(
    mapped
    .update_annotation(original.annotation_index, {
      ..original.annotation,
      duration: Some("1"),
    })
    .encode(),
  )
  let fresh = edited.find_annotations("1/3", "4/3")[0]
  let epoch = edited.event_window(
    fresh.annotation_index,
    [0, 1],
    before="0",
    after="0",
    max_samples=5,
  )
  let fast = epoch.channels[0].samples
  let slow = epoch.channels[1].samples
  println("units \{epoch.channels[0].unit} \{epoch.channels[1].unit}")
  println(
    "epoch \{epoch.samples} \{fast[0].digital} \{fast[1].digital} \{fast[2].digital} \{slow[0].digital} \{slow[1].digital}",
  )
  let mapped_ok = close_to(fast[0].physical, 5.0) &&
    close_to(fast[1].physical, 1.0) &&
    close_to(fast[2].physical, -3.0)
  let untouched_ok = close_to(slow[0].physical, 20.0) &&
    close_to(slow[1].physical, 30.0)
  println("physical \{mapped_ok} \{untouched_ok}")
}
