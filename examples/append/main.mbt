///|
// Two acquisition segments, one second of missing time, and an event in the
// second segment. A browser/Wasm consumer uses the same pure MoonBit API.
fn main raise {
  let fast : @edf.Signal = {
    label: "Synthetic fast",
    transducer: "",
    unit: "uV",
    physical_min: -32768.0,
    physical_max: 32767.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: 4,
    reserved: "",
  }
  let slow = { ..fast, label: "Synthetic slow", samples_per_record: 2, }
  let first = @edf.create(
    [fast, slow],
    [{ onset: "0.25", samples: [[1, 2, 3, 4], [10, 20]], events: [], }],
    "1",
  )
  let second = @edf.create(
    [fast, slow],
    [
      {
        onset: "0.25",
        samples: [[5, 6, 7, 8], [30, 40]],
        events: [{ onset: "0.5", duration: Some("0.125"), text: "resumed", }],
      },
    ],
    "1",
    start=@edf.parse_datetime("01.01.20", "00.00.02"),
  )
  let joined = first.append(second)
  println("Records: \{joined.records}; starts: " + joined.starts.join(", "))
  for gap in joined.gaps() {
    println("Missing interval: [\{gap.start}, \{gap.end})")
  }
  println(
    "Event: \{joined.annotations[0].text} at \{joined.annotations[0].onset}",
  )
  let epoch = joined.event_window(0, [0, 1], before="0.25", after="0.5")
  println("Event window: \{epoch.samples} samples; complete: \{epoch.complete}")
  println(joined.window_csv([0, 1], "2.25", "3.25", physical=false))
}
