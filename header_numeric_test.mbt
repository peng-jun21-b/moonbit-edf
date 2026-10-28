///|
fn numeric_field(data : Bytes, offset : Int, value : String) -> Bytes {
  let out = data.to_array()
  for i in 0..<8 {
    out[offset + i] = if i < value.length() { value[i].to_byte() } else { b' ' }
  }
  Bytes::from_array(out)
}

///|
test "create compact calibration fields without rounding their values" {
  for (minimum, maximum) in [(0.0, 0.000012345), (-0.00001234, 0.0)] {
    let signal : @edf.Signal = {
      ..deep_signal(2),
      physical_min: minimum,
      physical_max: maximum,
    }
    let r = @edf.create(
      [signal],
      [{ onset: "0", samples: [[-32768, 32767]], events: [], }],
      "1",
    )
    assert_eq(r.header.signals[0].physical_min, minimum)
    assert_eq(r.header.signals[0].physical_max, maximum)
    assert_eq(r.physical(0, 0, 0), minimum)
    assert_eq(r.physical(0, 0, 1), maximum)
  }
}

///|
test "valid compact calibration survives identity remapping and time crop" {
  let base = @edf.create(
    [deep_signal(2)],
    [{ onset: "0", samples: [[-32768, 32767]], events: [], }],
    "1",
  ).encode()
  let raw = numeric_field(
    numeric_field(base, 256 + 2 * 104, "0"),
    256 + 2 * 112,
    "12345e-9",
  )
  let source = @edf.decode(raw)
  let mapped = source.map_physical(0, 1.0)
  let cropped = source.crop_time_window("0", "1")
  for r in [mapped, cropped] {
    assert_eq(
      r.header.signals[0].physical_max,
      source.header.signals[0].physical_max,
    )
    assert_eq(r.digital(0, 0, 0), -32768)
    assert_eq(r.digital(0, 0, 1), 32767)
    assert_eq(r.physical(0, 0, 1), source.physical(0, 0, 1))
  }
}

///|
test "eight-byte leading-dot duration remains writable after crop" {
  let base = @edf.create(
    [deep_signal(2)],
    [{ onset: "0", samples: [[-32768, 32767]], events: [], }],
    "1",
  ).encode()
  let source = @edf.decode(numeric_field(base, 244, ".1234567"))
  let cropped = source.crop_time_window("0", ".1234567")
  assert_eq(
    @edf.Time::parse(cropped.header.duration),
    @edf.Time::parse(".1234567"),
  )
  assert_eq(cropped.sample_time(0, 0, 1), source.sample_time(0, 0, 1))
  let created = @edf.create(
    [deep_signal(2)],
    [{ onset: "0", samples: [[-32768, 32767]], events: [], }],
    ".1234567",
  )
  assert_eq(created.sample_time(0, 0, 1), source.sample_time(0, 0, 1))
}
