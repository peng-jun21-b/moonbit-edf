///|
test "negative physical map survives duration editing and a fresh multirate epoch" {
  let source = calibration_source()
  let before = source.encode()
  let mapped = @edf.decode(
    source.map_physical(0, -2.0, offset=5.0, unit="arb").encode(),
  )
  assert_eq(mapped.header.signals[0].physical_min, 65541.0)
  assert_eq(mapped.header.signals[0].physical_max, -65529.0)
  assert_eq(mapped.header.signals[0].unit, "arb")
  assert_eq(mapped.header.signals[1].physical_min, -32768.0)
  assert_eq(mapped.header.signals[1].physical_max, 32767.0)
  assert_eq(mapped.header.signals[1].unit, "uV")
  assert_eq(
    mapped.annotations.map(a => {
      (a.record, a.signal, a.onset, a.duration, a.text)
    }),
    source.annotations.map(a => {
      (a.record, a.signal, a.onset, a.duration, a.text)
    }),
  )
  let original = mapped.find_annotations("1/3", "4/3")
  assert_eq(original.map(m => (m.annotation_index, m.annotation.signal)), [
    (0, 2),
    (1, 3),
  ])
  let edited = @edf.decode(
    mapped
    .update_annotation(original[0].annotation_index, {
      ..original[0].annotation,
      duration: Some("1"),
    })
    .encode(),
  )
  assert_eq(edited.header.signals[0].physical_min, 65541.0)
  assert_eq(edited.header.signals[0].physical_max, -65529.0)
  let fresh = edited.find_annotations("1/3", "4/3")
  assert_eq(
    fresh.map(m => {
      (
        m.annotation_index,
        m.annotation.record,
        m.annotation.signal,
        m.annotation.onset,
        m.annotation.duration,
        m.annotation.text,
      )
    }),
    [(0, 0, 2, "+0.5", Some("1"), "stage"), (1, 0, 3, "+0.75", None, "keep")],
  )
  for s in 0..<2 {
    for j in 0..<source.header.signals[s].samples_per_record {
      let d = source.digital(s, 0, j)
      assert_eq(edited.digital(s, 0, j), d)
      assert_eq(edited.sample_time(s, 0, j), source.sample_time(s, 0, j))
      let expected = if s == 0 {
        -2.0 * d.to_double() + 5.0
      } else {
        d.to_double()
      }
      assert_true(close_to(edited.physical(s, 0, j), expected))
    }
  }
  let epoch = edited.event_window(
    fresh[0].annotation_index,
    [0, 1],
    before="0",
    after="0",
    max_samples=5,
  )
  assert_true(epoch.complete)
  assert_eq(epoch.samples, 5)
  assert_eq(epoch.channels[0].unit, "arb")
  assert_eq(epoch.channels[1].unit, "uV")
  assert_eq(epoch.channels[0].samples.map(s => s.digital), [0, 2, 4])
  assert_eq(epoch.channels[1].samples.map(s => s.digital), [20, 30])
  assert_eq(epoch.channels[0].samples.map(s => s.time.text()), [
    "2/3", "1", "4/3",
  ])
  assert_eq(epoch.channels[1].samples.map(s => s.time.text()), ["2/3", "4/3"])
  for i in 0..<3 {
    assert_true(
      close_to(epoch.channels[0].samples[i].physical, [5.0, 1.0, -3.0][i]),
    )
  }
  assert_eq(source.encode(), before)
}
