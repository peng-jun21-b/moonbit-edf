///|
test "Unicode text identities survive edit, exact selection and fresh epoch" {
  let source = unicode_source()
  let before = source.encode()
  assert_true(text_a() != text_b())
  let original = source.find_annotations("0.25", "0.75")
  assert_eq(original.map(m => m.annotation.text), [text_a(), text_b(), "other"])
  let target = "\uFEFF" + text_a()
  let updated = @edf.decode(
    source
    .update_annotation(original[0].annotation_index, {
      ..original[0].annotation,
      text: target,
    })
    .encode(),
  )
  assert_eq(updated.annotations.map(a => a.text), [target, text_b(), "other"])
  let indices = updated
    .find_annotations("0.25", "0.75")
    .filter(m => m.annotation.text == target)
    .map(m => m.annotation_index)
  assert_eq(indices, [0])
  let edited = @edf.decode(updated.remove_annotations(indices).encode())
  assert_eq(
    edited.annotations.map(a => {
      (a.record, a.signal, a.onset, a.duration, a.text)
    }),
    source.annotations[1:]
    .to_owned()
    .map(a => (a.record, a.signal, a.onset, a.duration, a.text)),
  )
  for s in 0..<2 {
    for j in 0..<source.header.signals[s].samples_per_record {
      assert_eq(edited.digital(s, 0, j), source.digital(s, 0, j))
      assert_eq(edited.sample_time(s, 0, j), source.sample_time(s, 0, j))
    }
  }
  let fresh = edited.find_annotations("0.25", "0.75")
  assert_eq(fresh.map(m => (m.annotation_index, m.annotation.signal)), [
    (0, 2),
    (1, 3),
  ])
  assert_eq(fresh[0].annotation.text, text_b())
  assert_eq(fresh[0].annotation.duration, Some("0.5"))
  let epoch = edited.event_window(
    fresh[0].annotation_index,
    [0, 1],
    before="0",
    after="0",
    max_samples=3,
  )
  assert_true(epoch.complete)
  assert_eq(epoch.samples, 3)
  assert_eq(epoch.channels[0].samples.map(s => s.digital), [20, 30])
  assert_eq(epoch.channels[1].samples.map(s => s.digital), [200])
  assert_eq(epoch.channels[0].samples.map(s => s.time.text()), ["0.25", "0.5"])
  assert_eq(epoch.channels[1].samples[0].time.text(), "0.5")
  assert_eq(source.encode(), before)
}
