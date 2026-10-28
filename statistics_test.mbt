///|
fn statistics_source(
  minimum : Double,
  maximum : Double,
  values : Array[Int],
  format : @edf.Format,
) -> @edf.Recording raise {
  let signal : @edf.Signal = {
    label: "Synthetic stats",
    transducer: "",
    unit: "uV",
    physical_min: minimum,
    physical_max: maximum,
    digital_min: -1,
    digital_max: 1,
    prefilter: "",
    samples_per_record: values.length().max(1),
    reserved: "",
  }
  @edf.create(
    [signal],
    if values.is_empty() {
      []
    } else {
      [{ onset: "0", samples: [values], events: [], }]
    },
    "1",
    format~,
  )
}

///|
fn statistics_near(actual : Double?, expected : Double) -> Unit raise {
  match actual {
    Some(value) => assert_true((value / expected - 1.0).abs() < 1.0e-12)
    None => assert_true(false)
  }
}

///|
test "statistics RMS retains tiny and large finite constants" {
  for format in [@edf.Edf, @edf.Bdf] {
    for (minimum, maximum) in [(1.0e-200, 2.0e-200), (1.0e200, 2.0e200)] {
      let stats = statistics_source(minimum, maximum, [-1, -1, -1, -1], format).statistics(
        0,
      )
      assert_eq(stats.samples, 4)
      assert_eq(stats.variance, Some(0.0))
      statistics_near(stats.rms, minimum)
      statistics_near(stats.mean, minimum)
      assert_eq(stats.at_minimum, 4)
    }
  }
}

///|
test "statistics population variance avoids overflowing intermediate totals" {
  for format in [@edf.Edf, @edf.Bdf] {
    let pair = statistics_source(-1.0e154, 1.0e154, [-1, 1], format).statistics(
      0,
    )
    assert_eq(pair.mean, Some(0.0))
    statistics_near(pair.variance, 1.0e308)
    statistics_near(pair.rms, 1.0e154)
    let values = Array::makei(2002, i => {
      if i == 0 {
        -1
      } else if i == 1 {
        1
      } else {
        0
      }
    })
    let diluted = statistics_source(-1.0e155, 1.0e155, values, format).statistics(
      0,
    )
    assert_eq(diluted.samples, 2002)
    assert_eq(diluted.mean, Some(0.0))
    // Independent 90-digit Decimal oracle: 2*10^310/2002 and its square root.
    statistics_near(diluted.variance, 9.99000999000999001e306)
    statistics_near(diluted.rms, 3.16069770620506984e153)
  }
}

///|
test "statistics retains empty zero and genuine overflow contracts" {
  for format in [@edf.Edf, @edf.Bdf] {
    let empty = statistics_source(-1.0, 1.0, [], format).statistics(0)
    assert_eq(empty.samples, 0)
    assert_eq(empty.mean, None)
    assert_eq(empty.variance, None)
    assert_eq(empty.rms, None)
    let zero = statistics_source(-1.0, 1.0, [0, 0, 0], format).statistics(0)
    assert_eq(zero.mean, Some(0.0))
    assert_eq(zero.variance, Some(0.0))
    assert_eq(zero.rms, Some(0.0))
    assert_true(
      try {
        ignore(
          statistics_source(-1.0e200, 1.0e200, [-1, 1], format).statistics(0),
        )
        false
      } catch {
        @edf.Limit(_) => true
        _ => false
      },
    )
  }
}
