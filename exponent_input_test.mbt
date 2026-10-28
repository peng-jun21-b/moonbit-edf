///|
test "unrepresentable exponent scales return checked limits" {
  for
    text in [
      "1e-2147483648", "0.1e-2147483647", "1.234e-2147483646", "1e2147483647",
    ] {
    assert_true(
      try {
        ignore(@edf.Time::parse(text))
        false
      } catch {
        @edf.Limit(_) => true
        _ => false
      },
    )
  }
}

///|
test "zero coefficients with extreme exponents stay valid exact zero" {
  for
    text in [
      "0e2147483647", "0e-2147483648", "-0e2147483647", "0.000e-2147483648",
    ] {
    let time = @edf.Time::parse(text)
    assert_eq(time.text(), "0")
    assert_eq(time, @edf.Time::parse("0"))
    let date = @edf.parse_datetime("01.01.20", "12.34.56")
    assert_eq(date.advance_seconds(text).time_field(), "12.34.56")
  }
  assert_eq(@edf.Time::parse("1.25e-3"), @edf.Time::parse("1/800"))
  assert_eq(@edf.Time::parse("12.30e2"), @edf.Time::parse("1230"))
  assert_eq(@edf.Time::parse("1e-21/1e-3"), @edf.Time::parse("1e-18"))
  assert_true(@edf.Time::parse("1e-5000") > @edf.Time::parse("0"))
}

///|
test "zero normalization preserves exponent grammar and zero denominator errors" {
  for
    text in [
      "0e+", "0e--1", "0eNaN", "0e2147483648", "0e2147483647/0e-2147483648",
    ] {
    assert_true(
      try {
        ignore(@edf.Time::parse(text))
        false
      } catch {
        @edf.Invalid(_) => true
        _ => false
      },
    )
  }
}
