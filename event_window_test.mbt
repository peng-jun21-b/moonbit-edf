///|
test "event windows add decimal event durations before half-open sampling" {
  let r = @edf.create(
    [signal(160, @edf.Edf)],
    Array::makei(26, i => {
      onset: i.to_double(),
      samples: [Array::makei(160, j => i * 160 + j)],
      events: if i == 20 {
        [{ onset: 20.8, duration: Some(4.1), text: "decimal", }]
      } else {
        []
      },
    }),
    1.0,
  )
  let w = r.event_window(0, [0], before=0.25, after=0.25)
  assert_eq((w.start, w.end, w.samples), ("20.55", "25.15", 736))
  assert_eq(w.channels[0].samples[735].digital, 4023)
  assert_eq(
    r.event_window(0, [0], before=0.00000003, after=0.25).start,
    "20.79999997",
  )
}

///|
test "event windows retain annotation identity and multirate shared budget" {
  let r = @edf.create(
    [signal(4, @edf.Edf), signal(2, @edf.Edf)],
    [
      {
        onset: 0.0,
        samples: [[1, 2, 3, 4], [10, 20]],
        events: [
          { onset: 0.25, duration: Some(0.5), text: "T1", },
          { onset: 0.5, duration: None, text: "T1", },
        ],
      },
    ],
    1.0,
  )
  let w = r.event_window(0, [0, 1], before=0.25, after=0.25, max_samples=6)
  assert_eq((w.start, w.end, w.samples, w.complete), ("0", "1", 6, true))
  assert_eq(w.annotation.text, "T1")
  assert_eq(w.channels[0].samples.map(s => (s.record, s.sample, s.digital)), [
    (0, 0, 1),
    (0, 1, 2),
    (0, 2, 3),
    (0, 3, 4),
  ])
  let other = r.event_window(1, [0], before=0.0, after=0.25)
  assert_eq(other.channels[0].samples.map(s => s.digital), [3])
  assert_eq(
    r.event_window(0, [0], before=0.0, after=0.25, include_duration=false).end,
    "0.5",
  )
  assert_true(
    try {
      ignore(r.event_window(0, [0, 1], before=0.25, after=0.25, max_samples=5))
      false
    } catch {
      _ => true
    },
  )
  assert_true(
    try {
      ignore(r.event_window(0, [0, 0], before=0.0, after=0.25))
      false
    } catch {
      _ => true
    },
  )
  assert_true(
    try {
      ignore(r.event_window(0, [], before=0.0, after=0.25))
      false
    } catch {
      _ => true
    },
  )
  assert_true(
    try {
      ignore(r.event_window(2, [0], before=0.0, after=0.25))
      false
    } catch {
      _ => true
    },
  )
}

///|
test "event windows reject missing recording time unless explicitly partial" {
  let r = @edf.create(
    [signal(2, @edf.Edf)],
    [
      {
        onset: 0.0,
        samples: [[1, 2]],
        events: [{ onset: 0.75, duration: Some(1.5), text: "cross-gap", }],
      },
      { onset: 2.0, samples: [[3, 4]], events: [], },
    ],
    1.0,
    continuity=@edf.Discontinuous,
  )
  assert_true(
    try {
      ignore(r.event_window(0, [0], before=0.0, after=0.0))
      false
    } catch {
      _ => true
    },
  )
  let w = r.event_window(0, [0], before=0.0, after=0.0, allow_partial=true)
  assert_false(w.complete)
  assert_eq(
    w.channels[0].samples.map(s => (s.record, s.time.text(), s.digital)),
    [(1, "2", 3)],
  )
  assert_eq(w.channels[0].gaps.map(g => (g.start, g.end)), [("1", "2")])
  assert_true(
    try {
      ignore(r.event_window(0, [0], before=1.0, after=0.0))
      false
    } catch {
      _ => true
    },
  )
  assert_false(
    r.event_window(0, [0], before=1.0, after=0.0, allow_partial=true).complete,
  )
  assert_true(
    try {
      ignore(r.event_window(0, [0], before=-1.0, after=0.0))
      false
    } catch {
      _ => true
    },
  )
  assert_true(
    try {
      ignore(
        r.event_window(0, [0], before=0.0, after=0.0, include_duration=false),
      )
      false
    } catch {
      _ => true
    },
  )
}
