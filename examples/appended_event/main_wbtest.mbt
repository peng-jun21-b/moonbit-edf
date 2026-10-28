///|
test "appended event before its storage record queries and epochs across the seam" {
  let left = append_part(false)
  let right = append_part(true)
  let before_left = left.encode()
  let before_right = right.encode()
  let joined = @edf.decode(left.append(right, offset="1.5").encode())
  assert_eq(joined.starts, ["+0", "+1.5"])
  assert_eq(
    joined.annotations.map(a => {
      (a.record, a.signal, a.onset, a.duration, a.text)
    }),
    [
      (0, 2, "+1", Some("1"), "left-stage"),
      (0, 3, "+0.25", None, "left"),
      (1, 2, "+1", Some("1"), "late-note"),
      (1, 3, "+2", None, "other"),
    ],
  )
  let matches = joined.find_annotations("1.25", "1.75")
  assert_eq(matches.map(m => (m.annotation_index, m.annotation.record)), [
    (0, 0),
    (2, 1),
  ])
  let edited = @edf.decode(
    joined
    .update_annotation(matches[1].annotation_index, {
      ..matches[1].annotation,
      text: "reviewed-right",
    })
    .encode(),
  )
  assert_eq(edited.annotations.map(a => a.text), [
    "left-stage", "left", "reviewed-right", "other",
  ])
  assert_eq(calibration_min(joined), b"1e-324  ")
  assert_eq(calibration_min(edited), calibration_min(left))
  for r in 0..<2 {
    let original = if r == 0 { left } else { right }
    let shift = @edf.Time::parse(if r == 0 { "0" } else { "1.5" })
    for s in 0..<2 {
      for j in 0..<original.header.signals[s].samples_per_record {
        assert_eq(edited.digital(s, r, j), original.digital(s, 0, j))
        assert_eq(
          edited.sample_time(s, r, j),
          original.sample_time(s, 0, j).add(shift),
        )
      }
    }
  }
  let fresh = edited.find_annotations("1.25", "1.75")
  assert_eq(fresh[1].annotation_index, 2)
  assert_eq(fresh[1].annotation.record, 1)
  assert_eq(fresh[1].annotation.signal, 2)
  assert_eq(fresh[1].annotation.onset, "+1")
  assert_eq(fresh[1].annotation.duration, Some("1"))
  let epoch = edited.event_window(
    fresh[1].annotation_index,
    [0, 1],
    before="0",
    after="0",
    max_samples=3,
  )
  assert_true(epoch.complete)
  assert_eq(epoch.samples, 3)
  assert_eq(epoch.channels[0].samples.map(s => (s.record, s.digital)), [
    (0, 13),
    (1, 14),
  ])
  assert_eq(epoch.channels[1].samples[0].digital, 22)
  assert_eq(epoch.channels[0].samples.map(s => s.time.text()), ["1", "1.5"])
  assert_eq(epoch.channels[1].samples[0].time.text(), "1.5")
  assert_eq(left.encode(), before_left)
  assert_eq(right.encode(), before_right)
}
