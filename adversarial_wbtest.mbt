///|
fn test_signal() -> Signal {
  {
    label: "test",
    transducer: "",
    unit: "uV",
    physical_min: -100.0,
    physical_max: 100.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: 2,
    reserved: "",
  }
}

///|
test "truncation bad widths and deterministic malformed headers are bounded" {
  let good = create(
    [test_signal()],
    [{ onset: 0.0, samples: [[1, 2]], events: [], }],
    1.0,
  ).encode()
  for n = 0; n < good.length(); n = n + 1 {
    assert_true(
      try {
        ignore(decode(part(good, 0, n)))
        false
      } catch {
        _ => true
      },
    )
  }
  for
    (pos, text) in [
      (184, "99999999"),
      (236, "99999999"),
      (244, "NaN     "),
      (252, "9999"),
    ] {
    let out = good.to_array()
    put_text(out, pos, text.length(), text)
    assert_true(
      try {
        ignore(decode(Bytes::from_array(out)))
        false
      } catch {
        _ => true
      },
    )
  }
  let mut state = 54321U
  for _case = 0; _case < 1000; _case = _case + 1 {
    let out = good.to_array()
    for _i = 0; _i < 3; _i = _i + 1 {
      state = state * 1664525U + 1013904223U
      let pos = (state % 768U).reinterpret_as_int()
      state = state * 1664525U + 1013904223U
      out[pos] = (state >> 24).to_byte()
    }
    ignore(decode(Bytes::from_array(out))) catch {
      _ => ()
    }
  }
}

///|
test "annotation-only zero duration and BDF discontinuities" {
  let only = create(
    [],
    [
      {
        onset: 0.0,
        samples: [],
        events: [
          { onset: 0.0, duration: None, text: "start", },
          { onset: 5.0, duration: Some(10.0), text: "mark", },
        ],
      },
    ],
    0.0,
  )
  assert_eq(only.annotations.length(), 2)
  assert_eq(only.header.duration, "0")
  let s : Signal = {
    ..test_signal(),
    digital_min: -8388608,
    digital_max: 8388607,
  }
  let discontinuous = create(
    [s],
    [
      { onset: 0.0, samples: [[-8388608, 8388607]], events: [], },
      { onset: 3.5, samples: [[0, 0]], events: [], },
    ],
    1.0,
    format=Bdf,
    continuity=Discontinuous,
  )
  assert_eq(discontinuous.gaps()[0].end, "3.5")
  assert_eq(discontinuous.crop(1, 1).starts, ["+0.5"])
}

///|
test "TAL whitespace fails while exact decimal transforms retain precision" {
  for data in [b" +0\x14\x14\x00", b"+0 \x14\x14\x00", b"+0\x15 1\x14x\x14\x00"] {
    assert_true(
      try {
        ignore(parse_tals(data))
        false
      } catch {
        _ => true
      },
    )
  }
  assert_eq(
    DecimalSeconds::parse("+0.00000001", true).text(true),
    "+0.00000001",
  )
  assert_eq(parse_tals(b"+0.00000001\x14x\x14\x00")[0].onset, "+0.00000001")
}

///|
test "CSV quotes labels and flat detection does not bridge missing time" {
  let s : Signal = { ..test_signal(), label: "a,\"b", }
  let r = create(
    [s],
    [
      { onset: 0.0, samples: [[1, 1]], events: [], },
      { onset: 3.0, samples: [[1, 1]], events: [], },
    ],
    1.0,
    continuity=Discontinuous,
  )
  assert_eq(r.flat_runs(0, 3).length(), 0)
  assert_true(r.csv([0], physical=false).contains("\"a,\"\"b\""))
  assert_true(
    try {
      ignore(r.select([0, 0]))
      false
    } catch {
      _ => true
    },
  )
}
