///|
fn batch_source(format : @edf.Format) -> @edf.Recording raise {
  let source = @edf.create(
      [signal(4, format), signal(2, format)],
      [
        {
          onset: "0",
          samples: [[1, 2, 3, 4], [10, 20]],
          events: [
            { onset: "0", duration: None, text: "keep-left", },
            { onset: "0.25", duration: Some("0.5"), text: "bad", },
            { onset: "0.5", duration: Some("0"), text: "keep-mid", },
          ],
        },
        {
          onset: "2",
          samples: [[5, 6, 7, 8], [30, 40]],
          events: [
            {
              onset: "2.000000000000000000001",
              duration: Some("0.499999999999999999999"),
              text: "bad",
            },
            { onset: "2.5", duration: None, text: "keep-right", },
          ],
        },
      ],
      "1",
      format~,
      continuity=@edf.Discontinuous,
    )
    .add_annotation_signal()
    .add_annotation("+0.25", "bad", duration="0.5", record=0, signal=3)
  let data = source.encode().to_array()
  let n = source.header.signals.length()
  let fields = b"1e-324  1       "
  for i in 0..<16 {
    data[256 + n * (if i < 8 { 104 } else { 112 }) + i % 8] = fields[i]
  }
  @edf.decode(Bytes::from_array(data))
}

///|
test "batch annotation indices select one snapshot regardless of order or duplicates" {
  for format in [@edf.Edf, @edf.Bdf] {
    let source = batch_source(format)
    let before = source.encode()
    let found = source
      .find_annotations("0.25", "2.5")
      .filter(m => m.annotation.text == "bad")
      .map(m => m.annotation_index)
    assert_eq(found, [1, 3, 4])
    let result = @edf.decode(source.remove_annotations([4, 1, 3, 1]).encode())
    assert_eq(result.annotations.map(a => a.text), [
      "keep-left", "keep-mid", "keep-right",
    ])
    assert_eq(result.annotations.map(a => (a.record, a.signal)), [
      (0, 2),
      (0, 2),
      (1, 2),
    ])
    assert_eq(result.annotations[1].duration, Some("0"))
    assert_eq(calibration_fields(result), calibration_fields(source))
    for s in 0..<2 {
      for r in 0..<2 {
        for j in 0..<source.header.signals[s].samples_per_record {
          assert_eq(result.digital(s, r, j), source.digital(s, r, j))
          assert_eq(result.sample_time(s, r, j), source.sample_time(s, r, j))
        }
      }
    }
    let fresh = result.find_annotations("2.5", "2.75")[0]
    assert_eq(fresh.annotation_index, 2)
    assert_eq(
      result.event_window(
        fresh.annotation_index,
        [0, 1],
        before="0",
        after="0.25",
      ).samples,
      2,
    )
    assert_eq(source.encode(), before)
  }
}

///|
test "batch annotation invalid indices reject the whole selection" {
  let source = batch_source(@edf.Edf)
  let before = source.encode()
  for indices in [[1, -1], [1, 6], [2147483647, 1], [-1]] {
    assert_true(
      try {
        ignore(source.remove_annotations(indices))
        false
      } catch {
        @edf.Invalid(message) => message == "annotation index"
        _ => false
      },
    )
    assert_eq(source.encode(), before)
  }
}

///|
test "batch annotation empty selections preserve plain plus and empty recording bytes" {
  for format in [@edf.Edf, @edf.Bdf] {
    let plus = batch_source(format)
    let plain = @edf.create(
      [signal(1, format)],
      [{ onset: "0", samples: [[1]], events: [], }],
      "1",
      format~,
      continuity=@edf.Plain,
    )
    let empty = @edf.create(
      [signal(1, format)],
      [],
      "1",
      format~,
      continuity=@edf.Plain,
    )
    for source in [plain, plus, empty] {
      assert_eq(source.remove_annotations([]).encode(), source.encode())
      assert_eq(
        source.remove_annotations([]).header.continuity,
        source.header.continuity,
      )
    }
  }
}

///|
test "batch annotation clearing retains timekeeping and metadata only definitions" {
  let source = batch_source(@edf.Edf)
  let cleared = source.remove_annotations(
    Array::makei(source.annotations.length(), i => i),
  )
  assert_eq(cleared.annotations.length(), 0)
  assert_eq(cleared.starts, source.starts)
  assert_eq(cleared.digital(0, 1, 3), 8)
  let metadata = @edf.create(
    [],
    [
      {
        onset: "0",
        samples: [],
        events: [
          { onset: "0", duration: None, text: "origin", },
          { onset: "1", duration: Some("0.5"), text: "remove", },
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
  assert_eq(metadata.remove_annotations([1]).annotations.map(a => a.text), [
    "origin", "marker",
  ])
  assert_eq(metadata.remove_annotations([1]).starts, ["+0", "+2"])
  let before = metadata.encode()
  assert_true(
    try {
      ignore(metadata.remove_annotations([0, 1]))
      false
    } catch {
      @edf.Invalid(message) =>
        message ==
        "annotation-only record needs its defining event at record start"
      _ => false
    },
  )
  assert_eq(metadata.encode(), before)
}
