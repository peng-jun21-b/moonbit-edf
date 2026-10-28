///|
test "exact source events select the correct side of a sub-Double boundary" {
  let r = @edf.create_exact(
    [signal(10, @edf.Edf)],
    [
      {
        onset: "+0",
        samples: [Array::makei(10, i => i)],
        events: [
          {
            onset: "+0.100000000000000000001",
            duration: Some("0.1"),
            text: "edge",
          },
        ],
      },
    ],
    "1",
  )
  let source = r.annotations_exact()[0]
  assert_eq(source.onset, "+0.100000000000000000001")
  let exact = r.event_window_exact(0, [0], before="0", after="0")
  assert_eq(exact.start, "0.100000000000000000001")
  assert_eq(exact.end, "0.200000000000000000001")
  assert_eq(exact.channels[0].samples.map(s => s.digital), [2])
  assert_eq(
    r.event_window(0, [0], before=0.0, after=0.0).channels[0].samples.map(s => {
      s.digital
    }),
    [2],
  )
  assert_eq(r.time_window_exact(0, "0.1", "0.2").samples.map(s => s.digital), [
    1,
  ])
  assert_eq(
    r.time_window_exact(0, "0.1", "0.200000000000000000001").samples.map(s => {
      s.digital
    }),
    [1, 2],
  )
}

///|
test "exact crop uses decimal floor near a second and retains onset and duration digits" {
  let r = @edf.create_exact(
    [signal(2, @edf.Edf)],
    [
      { onset: "+0.999999999999999999999", samples: [[10, 11]], events: [], },
      {
        onset: "+1.999999999999999999999",
        samples: [[20, 21]],
        events: [
          {
            onset: "+1.123456789012345678901",
            duration: Some("0.000000000000000000001"),
            text: "fine",
          },
        ],
      },
    ],
    "1",
  )
  let cropped = r.crop(1, 1)
  assert_eq(cropped.header.time, "00.00.01")
  assert_eq(cropped.record_onset_exact(0), "+0.999999999999999999999")
  assert_eq(cropped.annotations_exact()[0].onset, "+0.123456789012345678901")
  assert_eq(
    cropped.annotations_exact()[0].duration,
    Some("0.000000000000000000001"),
  )
  assert_eq(cropped.digital(0, 0, 0), 20)
  assert_eq(
    @edf.decode(cropped.encode()).annotations_exact()[0].onset,
    "+0.123456789012345678901",
  )
}

///|
test "long fractional TAL and negative onset survive creation selection and copy" {
  let time = "-0." + String::make(180, '0') + "1"
  let r = @edf.create_exact(
    [signal(3, @edf.Bdf), signal(2, @edf.Bdf)],
    [
      {
        onset: "+0",
        samples: [[-8388608, 0, 8388607], [1, 2]],
        events: [{ onset: time, duration: None, text: "negative", }],
      },
    ],
    "1",
    format=@edf.Bdf,
  )
  assert_eq(r.annotations_exact()[0].onset, time)
  assert_eq(@edf.decode(r.encode()).annotations_exact()[0].onset, time)
  assert_eq(r.select([1]).annotations_exact()[0].onset, time)
  let thirds = r.time_window_exact(0, "0", "1").samples
  assert_eq((thirds[1].time_numerator, thirds[1].time_denominator), ("1", "3"))
  assert_eq(thirds.map(s => s.digital), [-8388608, 0, 8388607])
}

///|
test "exact windows expose sub-100ns missing time and retain shared budgets" {
  let r = @edf.create_exact(
    [signal(2, @edf.Edf)],
    [
      {
        onset: "+0",
        samples: [[1, 2]],
        events: [{ onset: "+0.5", duration: Some("1"), text: "gap", }],
      },
      { onset: "+1.000000000000000000001", samples: [[3, 4]], events: [], },
    ],
    "1",
    continuity=@edf.Discontinuous,
  )
  try r.event_window_exact(0, [0], before="0", after="0") catch {
    @edf.Invalid(_) => ()
    _ => fail("unexpected missing-time error kind")
  } noraise {
    _ => fail("a tiny real gap must not be rounded away")
  }
  let w = r.event_window_exact(
    0,
    [0],
    before="0",
    after="0",
    allow_partial=true,
  )
  assert_false(w.complete)
  assert_eq(w.channels[0].gaps[0].start, "1")
  assert_eq(w.channels[0].gaps[0].end, "1.000000000000000000001")
  assert_eq(w.channels[0].samples.map(s => s.digital), [2, 3])
  try
    r.event_window_exact(
      0,
      [0],
      before="0",
      after="0",
      allow_partial=true,
      max_samples=1,
    )
  catch {
    @edf.Limit(_) => ()
    _ => fail("unexpected budget error kind")
  } noraise {
    _ => fail("budget must reject instead of truncating")
  }
}

///|
test "exact crop grows TAL capacity when rebasing lengthens multiple negative events" {
  let r = @edf.create_exact(
    [signal(1, @edf.Edf)],
    [
      { onset: "+0", samples: [[1]], events: [], },
      {
        onset: "+12345678.000000000000000000001",
        samples: [[2]],
        events: [
          {
            onset: "-0.000000000000000000000000000000000000000000001",
            duration: None,
            text: "a",
          },
          {
            onset: "-0.000000000000000000000000000000000000000000002",
            duration: None,
            text: "b",
          },
        ],
      },
      {
        onset: "+12345679.000000000000000000001",
        samples: [[3]],
        events: [
          {
            onset: "+12345679.123456789012345678901",
            duration: None,
            text: "c",
          },
        ],
      },
    ],
    "1",
    continuity=@edf.Discontinuous,
  )
  let cropped = r.crop(1, 2)
  assert_eq(
    cropped.annotations_exact()[0].onset,
    "-12345678.000000000000000000000000000000000000000000001",
  )
  assert_eq(cropped.digital(0, 0, 0), 2)
  assert_true(cropped.header.record_bytes > r.header.record_bytes)
  assert_eq(cropped.annotations_exact()[2].onset, "+1.123456789012345678901")
  assert_eq(cropped.digital(0, 1, 0), 3)
}
