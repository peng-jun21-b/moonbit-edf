///|
test "time windows retain partial records multirate source indices and clipped gaps" {
  for format in [@edf.Edf, @edf.Bdf] {
    let r = @edf.create(
      [signal(4, format), signal(2, format)],
      [
        { onset: 0.25, samples: [[1, 2, 3, 4], [10, 20]], events: [], },
        { onset: 2.25, samples: [[5, 6, 7, 8], [30, 40]], events: [], },
      ],
      1.0,
      format~,
      continuity=@edf.Discontinuous,
    )
    let w = r.time_window(0, 0.5, 2.5, max_samples=4)
    assert_eq(w.samples.map(s => s.digital), [2, 3, 4, 5])
    assert_eq(w.samples.map(s => (s.record, s.sample)), [
      (0, 1),
      (0, 2),
      (0, 3),
      (1, 0),
    ])
    assert_eq(w.samples.map(s => s.time.text()), ["0.5", "0.75", "1", "2.25"])
    assert_eq(w.samples[0].physical, signal(4, format).to_physical(2))
    assert_eq(r.time_window(1, 0.5, 2.5).samples.map(s => s.digital), [20, 30])
    assert_eq(w.gaps.map(g => (g.after_record, g.start, g.end)), [
      (0, "1.25", "2.25"),
    ])
    let gap_only = r.time_window(0, 1.5, 2.0)
    assert_eq(gap_only.samples.length(), 0)
    assert_eq(gap_only.gaps.map(g => (g.start, g.end)), [("1.5", "2")])
    assert_eq(r.time_window(0, -2.0, 0.25).gaps.length(), 0)
    assert_eq(r.time_window(0, 9.0, 10.0).gaps.length(), 0)
    assert_eq(r.time_window(0, 1.5, 1.5).gaps.length(), 0)
  }
}

///|
test "time window half open endpoints agree with exhaustive sample enumeration" {
  let r = @edf.create(
    [signal(3, @edf.Edf)],
    [
      { onset: 0.1, samples: [[1, 2, 3]], events: [], },
      { onset: 0.8, samples: [[4, 5, 6]], events: [], },
    ],
    0.7,
  )
  let all = Array::makei(6, i => r.sample_time(0, i / 3, i % 3))
  for start in all {
    for end in all {
      if start <= end {
        let expected = all.filter(t => t >= start && t < end)
        assert_eq(
          r.time_window(0, start, end).samples.map(s => s.time),
          expected,
        )
      }
    }
  }
}

///|
test "zero duration event records are points and retain duplicate timestamps" {
  let r = @edf.create(
    [signal(1, @edf.Edf)],
    [
      { onset: 0.0, samples: [[1]], events: [], },
      { onset: 0.0, samples: [[2]], events: [], },
      { onset: 2.0, samples: [[3]], events: [], },
    ],
    0.0,
    continuity=@edf.Discontinuous,
  )
  assert_eq(r.time_window(0, 0.0, 2.0).samples.map(s => s.digital), [1, 2])
  assert_eq(r.time_window(0, 2.0, 3.0).samples.map(s => s.record), [2])
  assert_eq(r.time_window(0, 0.0, 0.0).samples.length(), 0)
}

///|
test "window input and shared row budgets fail explicitly without truncation" {
  let r = @edf.create(
    [signal(2, @edf.Edf), signal(1, @edf.Edf)],
    [{ onset: 0.0, samples: [[1, 2], [3]], events: [], }],
    1.0,
  )
  assert_true(
    try {
      ignore(r.time_window(0, 0.0, 1.0, max_samples=1))
      false
    } catch {
      @edf.Limit(_) => true
      _ => false
    },
  )
  for
    (s, start, end, limit) in [
      (0, 1.0, 0.0, 10),
      (-1, 0.0, 1.0, 10),
      (2, 0.0, 1.0, 10),
      (0, 0.0, 1.0, 0),
      (0, 0.0, 1.0, -1),
    ] {
    assert_true(
      try {
        ignore(r.time_window(s, start, end, max_samples=limit))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
  }
  assert_true(
    try {
      ignore(r.window_csv([0, 1], 0.0, 1.0, max_samples=2))
      false
    } catch {
      @edf.Limit(_) => true
      _ => false
    },
  )
  for channels in [[0, 0], [], [2]] {
    assert_true(
      try {
        ignore(r.window_csv(channels, 0.0, 1.0))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
  }
  for
    value in [
      0x7FF0000000000000L.reinterpret_as_double(),
      0xFFF0000000000000L.reinterpret_as_double(),
      0x7FF8000000000000L.reinterpret_as_double(),
    ] {
    assert_true(
      try {
        ignore(r.time_window(0, value, 1.0))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
    assert_true(
      try {
        ignore(r.time_window(0, 0.0, value))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
  }
  // Exactly full is accepted even when a later selected channel has no rows.
  assert_eq(
    r.window_csv([0, 1], 0.5, 1.0, physical=false, max_samples=1),
    "signal,label,record,sample,time_seconds,time_numerator,time_denominator,value,unit\n0,\"Synthetic\",0,1,0.5,1,2,2,\"digital\"\n",
  )
}
