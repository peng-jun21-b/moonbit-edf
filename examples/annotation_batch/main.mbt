///|
fn main raise {
  println("format action result")
  for format in [@edf.Edf, @edf.Bdf] {
    let name = if format == @edf.Edf { "EDF" } else { "BDF" }
    let signal : @edf.Signal = {
      label: "Batch demo",
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
            events: [
              { onset: "0.25", duration: Some("0.5"), text: "bad", },
              { onset: "0.5", duration: None, text: "keep", },
            ],
          },
          {
            onset: "2",
            samples: [[5, 6, 7, 8], [30, 40]],
            events: [
              { onset: "2.5", duration: None, text: "keep", },
              { onset: "2.25", duration: Some("0.25"), text: "bad", },
            ],
          },
        ],
        "1",
        format~,
        continuity=@edf.Discontinuous,
      )
      .add_annotation_signal()
      .add_annotation("+0.25", "bad", duration="0.5", record=0, signal=3)
    let selected = source
      .find_annotations("0.25", "2.5")
      .filter(m => m.annotation.text == "bad")
      .map(m => m.annotation_index)
    let edited = @edf.decode(source.remove_annotations(selected).encode())
    println(
      "\{name} remove \{selected.length()} \{edited.annotations.length()}",
    )
    let fresh = edited.find_annotations("2.5", "2.75")[0]
    let epoch = edited.event_window(
      fresh.annotation_index,
      [0, 1],
      before="0",
      after="0.25",
    )
    println(
      "\{name} requery \{fresh.annotation_index} \{epoch.complete} \{epoch.samples}",
    )
  }
}
