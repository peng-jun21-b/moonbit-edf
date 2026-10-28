///|
fn main raise {
  println("format action result")
  for format in [@edf.Edf, @edf.Bdf] {
    let name = if format == @edf.Edf { "EDF" } else { "BDF" }
    let signal : @edf.Signal = {
      label: "Query demo",
      transducer: "",
      unit: "uV",
      physical_min: -100.0,
      physical_max: 100.0,
      digital_min: if format == @edf.Edf {
        -32768
      } else {
        -8388608
      },
      digital_max: if format == @edf.Edf {
        32767
      } else {
        8388607
      },
      prefilter: "",
      samples_per_record: 4,
      reserved: "",
    }
    let source = @edf.create(
        [signal, { ..signal, label: "slow", samples_per_record: 2, }],
        [
          {
            onset: "0",
            samples: [[1, 2, 3, 4], [10, 20]],
            events: [{ onset: "0.75", duration: Some("1.5"), text: "same", }],
          },
          { onset: "2", samples: [[5, 6, 7, 8], [30, 40]], events: [], },
        ],
        "1",
        format~,
        continuity=@edf.Discontinuous,
      )
      .add_annotation_signal()
      .add_annotation("+2.25", "same", duration="0.25", record=1, signal=3)
    let gap = source.find_annotations("1", "2")
    let epoch = source.event_window(
      gap[0].annotation_index,
      [0, 1],
      before="0",
      after="0",
      allow_partial=true,
    )
    println("\{name} gap \{gap.length()} \{epoch.complete} \{epoch.samples}")
    println(
      "\{name} onset-only \{source.find_annotations("1", "2", include_duration=false).length()}",
    )
    let matched = source.find_annotations(@edf.Time::parse("9/4"), "5/2")[0]
    let edited = source.update_annotation(matched.annotation_index, {
      ..matched.annotation,
      text: "reviewed",
    })
    println(
      "\{name} edit \{matched.annotation_index} \{matched.annotation.signal} \{edited.annotations[matched.annotation_index].text}",
    )
  }
}
