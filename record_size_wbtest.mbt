///|
test "EDF+ record boundary includes annotation storage and applies on create" {
  let signal : Signal = { ..test_signal(), samples_per_record: 30688, }
  for continuity in [Continuous, Discontinuous] {
    let r = create(
      [signal],
      [{ onset: "+0", samples: [Array::make(30688, 0)], events: [], }],
      "1",
      continuity~,
    )
    assert_eq(r.header.record_bytes, 61440)
    assert_eq(decode(r.encode()).digital(0, 0, 30687), 0)
    assert_true(
      try {
        ignore(
          create(
            [{ ..signal, samples_per_record: 30689, }],
            [{ onset: "+0", samples: [Array::make(30689, 0)], events: [], }],
            "1",
            continuity~,
          ),
        )
        false
      } catch {
        Invalid(message) => message == "EDF+ data record exceeds 61440 bytes"
        _ => false
      },
    )
    // Auto-expanding TAL storage must not silently produce an invalid record.
    assert_true(
      try {
        ignore(r.add_annotation("+0", String::make(100, 'x')))
        false
      } catch {
        Invalid(message) => message == "EDF+ data record exceeds 61440 bytes"
        _ => false
      },
    )
    assert_eq(r.header.record_bytes, 61440)
    assert_eq(r.annotations.length(), 0)
  }
}

///|
test "EDF+ mandatory record size is not imposed on plain EDF or BDF+" {
  let plain = create(
    [{ ..test_signal(), samples_per_record: 30721, }],
    [{ onset: "+0", samples: [Array::make(30721, 0)], events: [], }],
    "1",
    continuity=Plain,
  )
  assert_eq(plain.header.record_bytes, 61442)
  let bdf_signal : Signal = {
    ..test_signal(),
    samples_per_record: 20449,
    digital_min: -8388608,
    digital_max: 8388607,
  }
  let bdf = create(
    [bdf_signal],
    [{ onset: "+0", samples: [Array::make(20449, 0)], events: [], }],
    "1",
    format=Bdf,
  )
  assert_eq(bdf.header.record_bytes, 61443)
}
