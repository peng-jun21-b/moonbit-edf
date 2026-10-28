///|
fn deep_signal(per : Int) -> @edf.Signal {
  {
    label: "raw",
    transducer: "",
    unit: "uV",
    physical_min: -100.0,
    physical_max: 100.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: per,
    reserved: "",
  }
}

///|
test "main clock is exact and strict below one hundred nanoseconds" {
  let r = @edf.create(
    [deep_signal(1)],
    [
      { onset: "0", samples: [[1]], events: [], },
      { onset: "1.000000000000000000001", samples: [[2]], events: [], },
    ],
    "1",
    continuity=@edf.Discontinuous,
  )
  assert_eq(r.gaps()[0].end, "1.000000000000000000001")
  assert_eq(r.gaps_exact().to_json(), r.gaps().to_json())
  let data = r.encode().to_array()
  data[196] = b'C'
  assert_true(
    try {
      ignore(@edf.decode(Bytes::from_array(data)))
      false
    } catch {
      _ => true
    },
  )
  let tolerant = @edf.decode(
    Bytes::from_array(data),
    time_policy=@edf.Tolerance("0.000000000000000000001"),
  )
  assert_eq(tolerant.record_onset(1), "+1.000000000000000000001")
  assert_eq(tolerant.gaps().length(), 1)
}

///|
test "no floating conversion or fixed TAL precision bound in main decode" {
  let tiny = "0." + Array::make(5000, "0").join("") + "1"
  let r = @edf.create(
    [deep_signal(1)],
    [
      {
        onset: "0",
        samples: [[1]],
        events: [{ onset: tiny, duration: Some(tiny), text: "tiny", }],
      },
      {
        onset: "10000000000.000000000000000000001",
        samples: [[2]],
        events: [],
      },
    ],
    "1",
    continuity=@edf.Discontinuous,
  )
  let decoded = @edf.decode(r.encode())
  assert_eq(decoded.annotations[0].onset, "+" + tiny)
  assert_eq(decoded.record_onset(1), "+10000000000.000000000000000000001")
  assert_eq(
    decoded.sample_time(0, 1, 0).text(),
    "10000000000.000000000000000000001",
  )
}

///|
test "multiple annotation channels retain identity and exact TALs through editing" {
  let original = @edf.create(
    [deep_signal(2)],
    [{ onset: "0", samples: [[1, 2]], events: [], }],
    "1",
  )
  let edited = original
    .add_annotation_signal()
    .add_annotation("+0.0000000000000000000001", "secondary", signal=2)
    .add_annotation("+0.5", "primary", duration="0.000000000000000000002")
  assert_eq(edited.annotations.length(), 2)
  let secondary = edited.annotations.filter(a => a.text == "secondary")[0]
  assert_eq(secondary.signal, 2)
  let moved = edited
    .update_annotation(0, { ..edited.annotations[0], text: "changed", })
    .remove_annotation(1)
  assert_eq(moved.annotations.length(), 1)
  assert_eq(moved.annotations[0].text, "changed")
  assert_eq(moved.digital(0, 0, 1), 2)
  assert_eq(@edf.decode(edited.encode()).annotations[1].onset, secondary.onset)
}

///|
test "annotation edits grow capacity and affine physical mapping preserves raw samples" {
  let r = @edf.create(
    [deep_signal(2)],
    [{ onset: "0", samples: [[-100, 100]], events: [], }],
    "1",
  )
  let text = Array::make(1000, "event").join("")
  let edited = r
    .add_annotation("+0.2", text)
    .rename_signal(0, "new")
    .map_physical(0, 2.0, offset=3.0, unit="mV")
  assert_eq(edited.annotations[0].text, text)
  assert_eq(edited.header.signals[0].physical_min, -197.0)
  assert_eq(edited.header.signals[0].label, "new")
  assert_eq(edited.header.signals[0].unit, "mV")
  assert_eq(edited.digital(0, 0, 0), r.digital(0, 0, 0))
  assert_eq(edited.digital(0, 0, 1), r.digital(0, 0, 1))
}

///|
test "partial record crop repacks multiple rates and secondary events" {
  let r = @edf.create(
      [deep_signal(4), deep_signal(2)],
      [
        {
          onset: "0",
          samples: [[0, 1, 2, 3], [10, 11]],
          events: [
            {
              onset: "0.500000000000000000001",
              duration: Some("0.000000000000000000003"),
              text: "keep",
            },
          ],
        },
        { onset: "1", samples: [[4, 5, 6, 7], [12, 13]], events: [], },
      ],
      "1",
    )
    .add_annotation_signal()
    .add_annotation("+1.25", "second", signal=3)
  let cropped = r.crop_time_window("0.5", "1.5")
  assert_eq(cropped.records, 2)
  assert_eq(cropped.header.duration, "0.5")
  assert_eq(cropped.starts, ["+0.5", "+1"])
  assert_eq(cropped.header.signals[0].samples_per_record, 2)
  assert_eq(cropped.digital(0, 0, 0), 2)
  assert_eq(cropped.digital(0, 1, 1), 5)
  assert_eq(cropped.digital(1, 0, 0), 11)
  assert_eq(cropped.digital(1, 1, 0), 12)
  assert_eq(cropped.annotations[0].onset, "+0.500000000000000000001")
  assert_eq(cropped.annotations[0].duration, Some("0.000000000000000000003"))
  assert_eq(cropped.annotations[1].signal, 3)
}

///|
test "future calendar crop writes literal yy and resolves full plus date" {
  let start = @edf.parse_datetime("31.12.2119", "23.59.59")
  let r = @edf.create(
    [deep_signal(2)],
    [
      { onset: "0", samples: [[1, 2]], events: [], },
      { onset: "2", samples: [[3, 4]], events: [], },
    ],
    "1",
    start~,
    continuity=@edf.Discontinuous,
  )
  let cropped = r.crop_time_window("2", "2.5")
  assert_eq(cropped.header.date, "01.01.yy")
  assert_eq(cropped.header.start.year, 2120)
  assert_eq(cropped.header.time, "00.00.01")
  assert_eq(cropped.digital(0, 0, 0), 3)
}

///|
test "recurring sample clock remains rational in main windows and CSV" {
  let r = @edf.create(
    [deep_signal(3)],
    [{ onset: "0", samples: [[7, 7, 7]], events: [], }],
    "1",
  )
  assert_eq(r.sample_time(0, 0, 1).text(), "1/3")
  assert_eq(r.time_window(0, "1/3", "2/3").samples.length(), 1)
  assert_eq(
    r.window_csv([0], "1/3", "2/3", physical=false),
    r.window_csv_exact([0], "1/3", "2/3", physical=false),
  )
  assert_eq(r.flat_runs(0, 2)[0].end.text(), "1")
  assert_eq(r.flat_runs_exact(0, 2)[0].end.text(), "1")
}

///|
test "unrepresentable cross-channel phase is never silently resampled" {
  let r = @edf.create(
    [deep_signal(4), deep_signal(2)],
    [{ onset: "0", samples: [[1, 2, 3, 4], [5, 6]], events: [], }],
    "1",
  )
  assert_true(
    try {
      ignore(r.crop_time_window("0.25", "0.75"))
      false
    } catch {
      _ => true
    },
  )
}

///|
test "header exponent duration is exact and is written without decimal expansion overflow" {
  let r = @edf.create(
    [deep_signal(2)],
    [
      { onset: "0", samples: [[1, 2]], events: [], },
      { onset: "0.000000001", samples: [[3, 4]], events: [], },
    ],
    "1e-9",
  )
  assert_eq(r.sample_time(0, 1, 1).text(), "0.0000000015")
  assert_eq(@edf.decode(r.encode()).sample_time(0, 1, 1).text(), "0.0000000015")
}
