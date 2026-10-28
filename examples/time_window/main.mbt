///|
/// Extract a marked event's surrounding interval without compressing missing time.
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
  let slow : @edf.Signal = {
    ..fast,
    label: "Synthetic slow",
    samples_per_record: 2,
  }
  let r = @edf.create(
    [fast, slow],
    [
      { onset: 0.25, samples: [[1, 2, 3, 4], [10, 20]], events: [], },
      {
        onset: 2.25,
        samples: [[5, 6, 7, 8], [30, 40]],
        events: [{ onset: 2.5, duration: None, text: "synthetic event", }],
      },
    ],
    1.0,
    continuity=@edf.Discontinuous,
  ) catch {
    e => abort("Cannot create example: " + @debug.to_string(e))
  }
  let event = r.annotations[0]
  let start = @edf.Time::parse(event.onset).sub(@edf.Time::parse("2"))
  let end = @edf.Time::parse(event.onset).add(@edf.Time::parse("0.5"))
  let window = r.time_window(0, start, end) catch {
    e => abort("Cannot query: " + @debug.to_string(e))
  }
  println("Event: \{event.text}; [\{start.text()}, \{end.text()}) seconds")
  println("Fast-channel samples: \{window.samples.length()}")
  for gap in window.gaps {
    println("Missing interval: [\{gap.start}, \{gap.end})")
  }
  let csv = r.window_csv([0, 1], start, end, physical=false) catch {
    e => abort("Cannot export: " + @debug.to_string(e))
  }
  println(csv)
}
