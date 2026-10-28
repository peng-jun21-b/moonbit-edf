///|
test "annotation overlap is half open and zero durations remain point markers" {
  for format in [@edf.Edf, @edf.Bdf] {
    let source = @edf.create(
      [signal(4, format)],
      [
        {
          onset: "0",
          samples: [[1, 2, 3, 4]],
          events: [
            { onset: "-1", duration: Some("2"), text: "span", },
            { onset: "0", duration: None, text: "point", },
            { onset: "0.25", duration: Some("0"), text: "zero", },
            { onset: "0.5", duration: None, text: "right", },
            { onset: "0.75", duration: Some("0.25"), text: "ends", },
          ],
        },
      ],
      "1",
      format~,
    )
    assert_eq(
      source.find_annotations("0", "0.5").map(m => m.annotation_index),
      [0, 1, 2],
    )
    assert_eq(
      source
      .find_annotations("0", "0.5", include_duration=false)
      .map(m => m.annotation_index),
      [1, 2],
    )
    assert_eq(
      source.find_annotations("-0.5", "0").map(m => m.annotation_index),
      [0],
    )
    assert_eq(source.find_annotations("1", "2").length(), 0)
    assert_eq(source.find_annotations("0", "0").length(), 0)
    assert_eq(
      source.find_annotations("0.75", "1").map(m => m.annotation_index),
      [0, 4],
    )
    assert_eq(source.find_annotations("0", "0.5")[0].annotation.onset, "-1")
    assert_eq(
      source.find_annotations("0", "0.5")[0].annotation.duration,
      Some("2"),
    )
  }
}

///|
test "rational annotation queries keep storage indices and duplicate channel identities" {
  let seed = @edf.create(
    [signal(4, @edf.Edf)],
    [
      { onset: "0", samples: [[1, 2, 3, 4]], events: [], },
      { onset: "2", samples: [[5, 6, 7, 8]], events: [], },
    ],
    "1",
    continuity=@edf.Discontinuous,
  ).add_annotation_signal()
  let source = seed.with_annotations([
    {
      record: 1,
      signal: 1,
      onset: "+0.333333333333333333333",
      duration: None,
      text: "same",
    },
    {
      record: 0,
      signal: 2,
      onset: "+0.333333333333333333334",
      duration: None,
      text: "same",
    },
    {
      record: 0,
      signal: 1,
      onset: "+0.333333333333333333333",
      duration: None,
      text: "same",
    },
    {
      record: 0,
      signal: 1,
      onset: "+0.25",
      duration: Some("0.1"),
      text: "same",
    },
  ])
  let before = source.encode()
  let third = @edf.Time::parse("1/3")
  assert_eq(
    source.find_annotations(third, "0.34").map(m => m.annotation_index),
    [1, 2],
  )
  assert_eq(
    source
    .find_annotations("1/3", "0.34", include_duration=false)
    .map(m => m.annotation_index),
    [2],
  )
  let found = source.find_annotations("0.3", third)
  assert_eq(found.map(m => m.annotation_index), [0, 1, 3])
  assert_eq(found.map(m => (m.annotation.record, m.annotation.signal)), [
    (0, 1),
    (0, 1),
    (1, 1),
  ])
  assert_eq(source.encode(), before)
}

///|
test "a gap overlap match feeds an epoch and an edit without guessing an index" {
  let source = @edf.create(
    [signal(4, @edf.Edf), signal(2, @edf.Edf)],
    [
      {
        onset: "0",
        samples: [[1, 2, 3, 4], [10, 20]],
        events: [{ onset: "0.75", duration: Some("1.5"), text: "same", }],
      },
      { onset: "2", samples: [[5, 6, 7, 8], [30, 40]], events: [], },
    ],
    "1",
    continuity=@edf.Discontinuous,
  )
  let before = source.encode()
  let found = source.find_annotations(1.0, 2.0, max_annotations=1)
  assert_eq(found.length(), 1)
  let index = found[0].annotation_index
  assert_eq(
    source.event_window(
      index,
      [0, 1],
      before="0",
      after="0",
      allow_partial=true,
    ).samples,
    3,
  )
  assert_true(
    try {
      ignore(source.event_window(index, [0], before="0", after="0"))
      false
    } catch {
      @edf.Invalid(_) => true
      _ => false
    },
  )
  let edited = source.update_annotation(index, {
    ..found[0].annotation,
    text: "reviewed",
  })
  assert_eq(edited.find_annotations("1", "2")[0].annotation.text, "reviewed")
  assert_eq(edited.digital(0, 1, 3), 8)
  assert_eq(source.encode(), before)
}

///|
test "annotation queries support metadata only and plain files with checked limits" {
  let source = @edf.create(
    [],
    [
      {
        onset: "0",
        samples: [],
        events: [
          { onset: "0", duration: None, text: "origin", },
          { onset: "0", duration: Some("2"), text: "stage", },
        ],
      },
      {
        onset: "2",
        samples: [],
        events: [{ onset: "2", duration: None, text: "marker", }],
      },
    ],
    "0",
    continuity=@edf.Discontinuous,
  )
  assert_eq(source.find_annotations("1", "2").map(m => m.annotation_index), [1])
  assert_eq(source.find_annotations("2", "3").map(m => m.annotation_index), [2])
  assert_true(
    try {
      ignore(source.find_annotations("-1", "3", max_annotations=2))
      false
    } catch {
      @edf.Limit(_) => true
      _ => false
    },
  )
  for (start, end, budget) in [("2", "1", 1), ("bad", "1", 1), ("0", "1", 0)] {
    assert_true(
      try {
        ignore(source.find_annotations(start, end, max_annotations=budget))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
  }
  let plain = @edf.create(
    [signal(1, @edf.Edf)],
    [{ onset: "0", samples: [[1]], events: [], }],
    "1",
    continuity=@edf.Plain,
  )
  assert_eq(plain.find_annotations("-1", "3").length(), 0)
}
