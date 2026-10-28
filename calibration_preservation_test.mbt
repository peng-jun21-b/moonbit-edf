///|
fn calibration_source(
  format : @edf.Format,
  upper : Bool,
  zero? : Bool = false,
) -> @edf.Recording raise {
  let count = if zero { 1 } else { 4 }
  let slow_count = if zero { 1 } else { 2 }
  let signal : @edf.Signal = {
    label: "fast",
    transducer: "",
    unit: "uV",
    physical_min: 0.0,
    physical_max: 1.0,
    digital_min: if format == @edf.Edf {
      -32768
    } else {
      -8388608
    },
    digital_max: if format == @edf.Edf {
      32767
    } else {
      8388607
    },
    prefilter: "",
    samples_per_record: count,
    reserved: "",
  }
  let source = @edf.create(
    [signal, { ..signal, label: "slow", samples_per_record: slow_count, }],
    [
      {
        onset: if zero {
          "0.25"
        } else {
          "0"
        },
        samples: [
          Array::makei(count, j => j + 1),
          Array::makei(slow_count, j => j + 11),
        ],
        events: [{ onset: "0.5", duration: None, text: "left", }],
      },
      {
        onset: if zero {
          "2.25"
        } else {
          "1"
        },
        samples: [
          Array::makei(count, j => j + 5),
          Array::makei(slow_count, j => j + 15),
        ],
        events: [],
      },
    ],
    if zero {
      "0"
    } else {
      "1"
    },
    format~,
    continuity=if zero { @edf.Discontinuous } else { @edf.Continuous },
  )
  let data = source.encode().to_array()
  let fields = if upper { b"1       3e-324  " } else { b"1e-324  1       " }
  let n = source.header.signals.length()
  for i in 0..<16 {
    data[256 + n * (if i < 8 { 104 } else { 112 }) + i % 8] = fields[i]
  }
  @edf.decode(Bytes::from_array(data))
}

///|
fn calibration_fields(source : @edf.Recording) -> Bytes raise {
  let data = source.encode()
  let n = source.header.signals.length()
  Bytes::makei(16, i => data[256 + n * (if i < 8 { 104 } else { 112 }) + i % 8])
}

///|
test "time crop preserves original calibration before appending a sibling record" {
  for format in [@edf.Edf, @edf.Bdf] {
    let source = calibration_source(format, false)
    let left = source.crop_time_window("0", "1")
    let right = source.crop(1, 1)
    assert_eq(calibration_fields(left), calibration_fields(source))
    let joined = @edf.decode(left.append(right).encode())
    assert_eq(calibration_fields(joined), calibration_fields(source))
    assert_eq(joined.records, 2)
    assert_eq(joined.digital(0, 1, 0), 5)
    assert_eq(joined.sample_time(0, 1, 0).text(), "1")
  }
}

///|
test "annotation rewriting and a new annotation channel retain exact calibration" {
  for format in [@edf.Edf, @edf.Bdf] {
    let source = calibration_source(format, true)
    let added = source.add_annotation("+0.75", "added", duration="0.125")
    assert_eq(calibration_fields(added), calibration_fields(source))
    assert_eq(
      calibration_fields(added.remove_annotation(0)),
      calibration_fields(source),
    )
    let expanded = source.add_annotation_signal()
    assert_eq(
      expanded.header.signals.length(),
      source.header.signals.length() + 1,
    )
    assert_eq(calibration_fields(expanded), calibration_fields(source))
    assert_eq(expanded.digital(0, 1, 3), source.digital(0, 1, 3))
  }
}

///|
test "zero-duration time crop and append retain calibration and fractional clock" {
  for format in [@edf.Edf, @edf.Bdf] {
    let source = calibration_source(format, false, zero=true)
    let left = source.crop_time_window("0.25", "1")
    let right = source.crop_time_window("2.25", "3")
    assert_eq(calibration_fields(left), calibration_fields(source))
    assert_eq(calibration_fields(right), calibration_fields(source))
    let joined = @edf.decode(left.append(right).encode())
    assert_eq(calibration_fields(joined), calibration_fields(source))
    assert_eq(joined.sample_time(0, 1, 0).text(), "2.25")
    assert_eq(joined.digital(0, 1, 0), 5)
  }
}
