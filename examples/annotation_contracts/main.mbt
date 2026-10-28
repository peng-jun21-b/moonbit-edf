///|
fn main raise {
  println("scenario result")
  let metadata = @edf.create(
    [],
    [
      {
        onset: "0.25",
        samples: [],
        events: [
          { onset: "0.25", duration: None, text: "A", },
          { onset: "0.25", duration: None, text: "B", },
        ],
      },
      {
        onset: "2.25",
        samples: [],
        events: [
          { onset: "2.25", duration: None, text: "C", },
          { onset: "2.25", duration: None, text: "D", },
        ],
      },
    ],
    "0",
    continuity=@edf.Discontinuous,
  )
  let chosen = metadata
    .find_annotations("0.25", "2.5")
    .filter(m => m.annotation.text == "A" || m.annotation.text == "C")
    .map(m => m.annotation_index)
  let edited = @edf.decode(metadata.remove_annotations(chosen).encode())
  println(
    "metadata \{edited.records} \{edited.annotations.map(a => a.text).join(",")}",
  )
  let signal : @edf.Signal = {
    label: "Point demo",
    transducer: "",
    unit: "uV",
    physical_min: -100.0,
    physical_max: 100.0,
    digital_min: -8388608,
    digital_max: 8388607,
    prefilter: "",
    samples_per_record: 1,
    reserved: "",
  }
  let points = @edf.create(
    [signal, signal],
    [
      {
        onset: "0.25",
        samples: [[111], [-222]],
        events: [{ onset: "0.25", duration: None, text: "left", }],
      },
      {
        onset: "2.25",
        samples: [[333], [-444]],
        events: [{ onset: "2.25", duration: Some("0"), text: "target", }],
      },
      {
        onset: "4.25",
        samples: [[555], [-666]],
        events: [{ onset: "4.25", duration: None, text: "right", }],
      },
    ],
    "0",
    format=@edf.Bdf,
    continuity=@edf.Discontinuous,
  )
  let selected = points
    .find_annotations("0.25", "4.5")
    .filter(m => m.annotation.text != "target")
    .map(m => m.annotation_index)
  let edited = @edf.decode(points.remove_annotations(selected).encode())
  let fresh = edited.find_annotations("2.25", "2.35")[0]
  let epoch = edited.event_window(
    fresh.annotation_index,
    [0, 1],
    before="0",
    after="0.1",
    allow_partial=true,
  )
  println(
    "points \{fresh.annotation_index} \{epoch.complete} \{epoch.channels[0].samples[0].digital} \{epoch.channels[1].samples[0].digital}",
  )
}
