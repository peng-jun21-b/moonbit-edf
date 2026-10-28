///|
test "surviving primary defining events make metadata batch removal legal" {
  let source = @edf.create(
      [],
      [
        {
          onset: "0.25",
          samples: [],
          events: [
            { onset: "0.25", duration: None, text: "A", },
            { onset: "0.25", duration: None, text: "B", },
            { onset: "0.25", duration: Some("1"), text: "stage", },
          ],
        },
        {
          onset: "2.25",
          samples: [],
          events: [
            { onset: "2.25", duration: None, text: "C", },
            { onset: "2.25", duration: None, text: "D", },
            { onset: "2.5", duration: Some("0.25"), text: "stage", },
          ],
        },
      ],
      "0",
      continuity=@edf.Discontinuous,
    )
    .add_annotation_signal()
    .add_annotation("+0.25", "secondary", record=0, signal=1)
    .add_annotation("+2.25", "secondary", record=1, signal=1)
  let before = source.encode()
  let selected = source
    .find_annotations("0.25", "2.5")
    .filter(m => m.annotation.text == "A" || m.annotation.text == "C")
    .map(m => m.annotation_index)
  assert_eq(selected, [0, 4])
  let edited = @edf.decode(source.remove_annotations([4, 0, 4]).encode())
  assert_eq(edited.records, 2)
  assert_eq(edited.starts, ["+0.25", "+2.25"])
  assert_eq(
    edited.annotations
    .filter(a => a.signal == 0 && a.duration is None)
    .map(a => a.text),
    ["B", "D"],
  )
  assert_eq(
    edited.find_annotations("0.25", "2.5").map(m => m.annotation_index),
    [0, 1, 2, 3, 5],
  )
  assert_true(
    try {
      ignore(edited.remove_annotations([0]))
      false
    } catch {
      @edf.Invalid(message) =>
        message ==
        "annotation-only record needs its defining event at record start"
      _ => false
    },
  )
  assert_eq(source.encode(), before)
}

///|
test "zero duration BDF point records survive query batch edit and partial epoch" {
  let source = @edf.create(
      [signal(1, @edf.Bdf), signal(1, @edf.Bdf)],
      [
        {
          onset: "0.25",
          samples: [[111], [-222]],
          events: [{ onset: "0.25", duration: None, text: "left", }],
        },
        { onset: "2.25", samples: [[333], [-444]], events: [], },
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
    .add_annotation_signal()
    .add_annotation("+2.25", "target", duration="0", record=1, signal=3)
  let before = source.encode()
  let selected = source
    .find_annotations("0.25", "4.5")
    .filter(m => m.annotation.text != "target")
    .map(m => m.annotation_index)
  assert_eq(selected, [0, 2])
  let edited = @edf.decode(source.remove_annotations([2, 0]).encode())
  assert_eq(edited.starts, source.starts)
  let found = edited.find_annotations("2.25", "2.35")[0]
  assert_eq((found.annotation_index, found.annotation.signal), (0, 3))
  let epoch = edited.event_window(
    found.annotation_index,
    [0, 1],
    before="0",
    after="0.1",
    allow_partial=true,
    max_samples=2,
  )
  assert_false(epoch.complete)
  assert_eq(epoch.samples, 2)
  assert_eq(epoch.channels.map(c => c.samples[0].digital), [333, -444])
  assert_eq(epoch.channels[0].samples[0].time.text(), "2.25")
  assert_eq(epoch.channels[0].gaps.map(g => (g.start, g.end)), [
    ("2.25", "2.35"),
  ])
  assert_true(
    try {
      ignore(
        edited.event_window(
          found.annotation_index,
          [0, 1],
          before="0",
          after="0.1",
        ),
      )
      false
    } catch {
      @edf.Invalid(_) => true
      _ => false
    },
  )
  assert_eq(source.encode(), before)
}
