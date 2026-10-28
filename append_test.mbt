///|
fn append_test_signal(format : @edf.Format, count : Int) -> @edf.Signal {
  {
    label: "Synthetic append",
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
    samples_per_record: count,
    reserved: "",
  }
}

///|
fn append_test_piece(
  format : @edf.Format,
  duration? : String = "1",
  start? : @edf.DateTime,
  patient? : String,
) -> @edf.Recording raise {
  @edf.create(
    [append_test_signal(format, 4)],
    [{ onset: "0", samples: [[1, 2, 3, 4]], events: [], }],
    duration,
    format~,
    start?,
    patient?,
  )
}

///|
test "append promotes plain multirate files and retains continuous sample clocks" {
  for format in [@edf.Edf, @edf.Bdf] {
    let s = append_test_signal(format, 4)
    let t = { ..s, label: "Slow", samples_per_record: 2, }
    let a = @edf.create(
      [s, t],
      [
        {
          onset: "0",
          samples: [[s.digital_min, 2, 3, s.digital_max], [10, 20]],
          events: [],
        },
      ],
      "1",
      format~,
      continuity=@edf.Plain,
    )
    let b = @edf.create(
      [s, t],
      [{ onset: "0", samples: [[4, 5, 6, 7], [30, 40]], events: [], }],
      "1",
      format~,
      continuity=@edf.Plain,
      start=@edf.parse_datetime("01.01.20", "00.00.01"),
    )
    let before = a.encode()
    let result = @edf.decode(a.append(b).encode())
    assert_eq(result.header.continuity, @edf.Continuous)
    assert_eq(result.records, 2)
    assert_eq(result.digital(0, 0, 0), s.digital_min)
    assert_eq(result.digital(0, 0, 3), s.digital_max)
    assert_eq(result.digital(0, 1, 3), 7)
    assert_eq(result.digital(1, 1, 1), 40)
    assert_eq(result.sample_time(0, 1, 1).text(), "1.25")
    assert_eq(result.sample_time(1, 1, 1).text(), "1.5")
    assert_eq(result.gaps().length(), 0)
    assert_eq(a.encode(), before)
  }
}

///|
test "append exact offset preserves sub-Double gap and secondary negative events" {
  for format in [@edf.Edf, @edf.Bdf] {
    let signals = [append_test_signal(format, 4), append_test_signal(format, 2)]
    let a = @edf.create(
      signals,
      [{ onset: "0.25", samples: [[1, 2, 3, 4], [5, 6]], events: [], }],
      "1",
      format~,
    ).add_annotation_signal()
    let b = @edf.create(
        signals,
        [{ onset: "0.25", samples: [[7, 8, 9, 10], [11, 12]], events: [], }],
        "1",
        format~,
      )
      .add_annotation_signal()
      .add_annotation(
        "-0.25",
        "secondary",
        duration="0.000000000000000000003",
        record=0,
        signal=3,
      )
    let result = @edf.decode(
      a.append(b, offset="1.000000000000000000001").encode(),
    )
    assert_eq(result.header.continuity, @edf.Discontinuous)
    assert_eq(result.record_onset(1), "+1.250000000000000000001")
    let gap = result.gaps()[0]
    assert_eq(
      @edf.Time::parse(gap.end).sub(@edf.Time::parse(gap.start)).text(),
      "0.000000000000000000001",
    )
    let event = result.annotations[0]
    assert_eq(event.record, 1)
    assert_eq(event.signal, 3)
    assert_eq(event.onset, "+0.750000000000000000001")
    assert_eq(event.duration, Some("0.000000000000000000003"))
    assert_eq(result.digital(1, 1, 0), 11)
    assert_eq(
      result.time_window(0, "1.25", "1.250000000000000000001").samples.length(),
      0,
    )
  }
}

///|
test "append header clocks cross leap dates and exceed 32-bit seconds" {
  for
    (a_date, b_date) in [("28.02.20", "29.02.20"), ("28.02.2100", "01.03.2100")] {
    let a = append_test_piece(
      @edf.Edf,
      start=@edf.parse_datetime(a_date, "23.59.59"),
    )
    let b = append_test_piece(
      @edf.Edf,
      start=@edf.parse_datetime(b_date, "00.00.00"),
    )
    assert_eq(a.append(b).record_onset(1), "+1")
  }
  let a = append_test_piece(@edf.Edf)
  let b = append_test_piece(
    @edf.Edf,
    start=@edf.parse_datetime("01.01.2100", "00.00.00"),
  )
  assert_eq(a.append(b).record_onset(1), "+2524608000")
}

///|
test "append zero-duration single-sample and annotation-only records" {
  for format in [@edf.Edf, @edf.Bdf] {
    let a = @edf.create(
      [append_test_signal(format, 1)],
      [{ onset: "0", samples: [[-1]], events: [], }],
      "0",
      format~,
      continuity=@edf.Discontinuous,
    )
    let b = @edf.create(
      [append_test_signal(format, 1)],
      [{ onset: "0.25", samples: [[1]], events: [], }],
      "0",
      format~,
      continuity=@edf.Discontinuous,
    )
    let joined = a.append(b, offset="2")
    assert_eq(joined.header.continuity, @edf.Discontinuous)
    assert_eq(joined.sample_time(0, 1, 0).text(), "2.25")
    let a = @edf.create(
      [],
      [
        {
          onset: "0",
          samples: [],
          events: [{ onset: "0", duration: None, text: "left", }],
        },
      ],
      "0",
      format~,
    )
    let b = @edf.create(
      [],
      [
        {
          onset: "0.25",
          samples: [],
          events: [{ onset: "0.25", duration: None, text: "right", }],
        },
      ],
      "0",
      format~,
    )
    let joined = @edf.decode(a.append(b, offset="2").encode())
    assert_eq(joined.annotations[1].record, 1)
    assert_eq(joined.annotations[1].onset, "+2.25")
    assert_eq(joined.annotations[1].text, "right")
  }
}

///|
test "append rejects incompatible records and overlapping time without modifying inputs" {
  let a = append_test_piece(@edf.Edf)
  let variants = [
    append_test_piece(@edf.Bdf),
    append_test_piece(@edf.Edf, duration="2"),
    append_test_piece(@edf.Edf, patient="other X X X"),
    a.rename_signal(0, "Different"),
    a.map_physical(0, 1.0, unit="mV"),
    a.map_physical(0, 2.0),
    a.add_annotation_signal(),
    @edf.create(
      [append_test_signal(@edf.Edf, 2)],
      [{ onset: "0", samples: [[1, 2]], events: [], }],
      "1",
    ),
    @edf.create([append_test_signal(@edf.Edf, 4)], [], "1"),
  ]
  let before = a.encode()
  for b in variants {
    assert_true(
      try {
        ignore(a.append(b, offset="1"))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
  }
  for offset in ["0.999999999999999999999", "-1", "1/3"] {
    assert_true(
      try {
        ignore(a.append(a, offset~))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
  }
  assert_eq(a.encode(), before)
}
