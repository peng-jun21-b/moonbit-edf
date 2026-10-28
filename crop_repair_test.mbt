///|
test "crop large plain EDF before applying the output EDF+ record limit" {
  let signal : @edf.Signal = { ..deep_signal(40000), label: "wide", }
  let values = Array::makei(40000, i => i % 65536 - 32768)
  let source = @edf.create(
    [signal],
    [{ onset: "0", samples: [values], events: [], }],
    "1",
    continuity=@edf.Plain,
  )
  assert_eq(source.header.record_bytes, 80000)
  let cropped = source.crop_time_window("0", "0.5")
  assert_eq(cropped.header.signals[0].samples_per_record, 20000)
  assert_true(cropped.header.record_bytes <= 61440)
  assert_eq(cropped.digital(0, 0, 0), -32768)
  assert_eq(cropped.digital(0, 0, 19999), values[19999])
  assert_eq(cropped.sample_time(0, 0, 19999), @edf.Time::parse("19999/40000"))
  // A full selection can also be expressed by splitting into smaller records.
  let full = source.crop_time_window("0", "1")
  assert_eq(full.records, 2)
  assert_eq(full.header.duration, "0.5")
  assert_eq(full.digital(0, 1, 19999), values[39999])
  assert_eq(full.sample_time(0, 1, 19999), @edf.Time::parse("39999/40000"))
  // A prime sample count cannot be split while retaining finite-decimal TALs
  // and the original sampling rate; its actual oversized output stays invalid.
  let indivisible = @edf.create(
    [{ ..signal, samples_per_record: 32771, }],
    [{ onset: "0", samples: [Array::make(32771, 0)], events: [], }],
    "1",
    continuity=@edf.Plain,
  )
  assert_true(
    try {
      ignore(indivisible.crop_time_window("0", "1"))
      false
    } catch {
      @edf.Invalid(message) => message == "EDF+ data record exceeds 61440 bytes"
      _ => false
    },
  )
}

///|
test "record splitting skips a duration which cannot fit the EDF header" {
  let source = @edf.create(
    [deep_signal(40000)],
    [{ onset: "0", samples: [Array::make(40000, 123)], events: [], }],
    "12345e-9",
    continuity=@edf.Plain,
  )
  let cropped = source.crop_time_window("0", "12345e-9")
  // Half the duration needs nine header bytes (61725e-10), but a fifth
  // fits exactly (2469e-9); both choices retain finite decimal time.
  assert_eq(cropped.records, 5)
  assert_eq(cropped.header.signals[0].samples_per_record, 8000)
  assert_eq(
    @edf.Time::parse(cropped.header.duration),
    @edf.Time::parse("2469e-9"),
  )
  assert_eq(cropped.digital(0, 4, 7999), 123)
  assert_eq(cropped.sample_time(0, 4, 7999), source.sample_time(0, 0, 39999))
}

///|
test "crop EDF+D zero-duration single-sample records without moving time" {
  for format in [@edf.Edf, @edf.Bdf] {
    let low = if format == @edf.Edf { -32768 } else { -8388608 }
    let high = if format == @edf.Edf { 32767 } else { 8388607 }
    let signal : @edf.Signal = {
      ..deep_signal(1),
      digital_min: low,
      digital_max: high,
    }
    let source = @edf.create(
      [signal, signal],
      [
        { onset: "+0.25", samples: [[low], [high]], events: [], },
        {
          onset: "+2.250000000000000000001",
          samples: [[high], [low]],
          events: [
            { onset: "-0.1", duration: None, text: "before", },
            {
              onset: "+2.250000000000000000001",
              duration: Some("0.000000000000000000001"),
              text: "impulse",
            },
          ],
        },
      ],
      "0",
      format~,
      continuity=@edf.Discontinuous,
    )
    let cropped = source.crop_time_window("2", "3")
    assert_eq(cropped.records, 1)
    assert_eq(cropped.header.duration, "0")
    assert_eq(cropped.header.time, "00.00.02")
    assert_eq(cropped.sample_time(0, 0, 0).text(), "0.250000000000000000001")
    assert_eq(cropped.digital(0, 0, 0), high)
    assert_eq(cropped.digital(1, 0, 0), low)
    assert_eq(cropped.annotations.length(), 1)
    assert_eq(cropped.annotations[0].onset, "+0.250000000000000000001")
    assert_eq(cropped.annotations[0].duration, Some("0.000000000000000000001"))
    assert_eq(source.time_window(0, "2", "3").samples.length(), 1)
  }
}
