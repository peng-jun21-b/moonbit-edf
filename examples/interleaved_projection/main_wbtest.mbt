///|
test "interleaved annotation identities follow selection then fresh query and epoch" {
  let source = interleaved_source()
  let before = source.encode()
  assert_eq(source.header.signals[2].label, "slow")
  assert_true(source.header.signals[1].is_annotation())
  let selected = @edf.decode(source.select([2]).encode())
  assert_eq(selected.header.signals.length(), 3)
  assert_eq(selected.header.signals[0].label, "slow")
  assert_eq(selected.annotations.map(a => a.signal), [1, 2, 1, 2])
  for r in 0..<2 {
    for j in 0..<2 {
      assert_eq(selected.digital(0, r, j), source.digital(2, r, j))
      assert_eq(selected.sample_time(0, r, j), source.sample_time(2, r, j))
    }
  }
  let matches = selected.find_annotations("0.25", "0.75")
  assert_eq(matches.map(m => (m.annotation_index, m.annotation.signal)), [
    (0, 1),
    (1, 2),
  ])
  assert_eq(matches.map(m => m.annotation.text), ["same", "same"])
  let edited = @edf.decode(
    selected.remove_annotations([matches[1].annotation_index]).encode(),
  )
  assert_eq(edited.annotations.map(a => a.signal), [1, 1, 2])
  assert_eq(edited.annotations.map(a => a.text), ["same", "later", "same"])
  let fresh = edited.find_annotations("0.25", "0.75")
  assert_eq(fresh.length(), 1)
  let epoch = edited.event_window(
    fresh[0].annotation_index,
    [0],
    before="0",
    after="0",
    max_samples=1,
  )
  assert_true(epoch.complete)
  assert_eq(epoch.samples, 1)
  assert_eq(epoch.channels[0].samples[0].digital, -200000)
  assert_eq(epoch.channels[0].samples[0].time.text(), "0.5")
  assert_eq(source.encode(), before)
}
