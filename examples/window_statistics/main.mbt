///|
fn[A : @edf.TimeInput, B : @edf.TimeInput] receive(
  name : String,
  data : Bytes,
  signal : Int,
  start : A,
  end : B,
  budget : Int,
) -> Json {
  let value = @edf.decode(data).window_statistics(
    signal,
    start,
    end,
    max_samples=budget,
  ) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  { "name": name.to_json(), "result": value.to_json() }
}

///|
fn main raise {
  let received = [
    receive(
      "fractional",
      input_identity(),
      0,
      @edf.Time::parse("1/4"),
      "3/4",
      100,
    ),
    receive("singleton", input_identity(), 0, "1/3", "2/3", 100),
    receive("whole", input_identity(), 0, 0.0, "1", 100),
    receive("equal", input_identity(), 0, "1/3", "1/3", 100),
    receive("between", input_identity(), 0, "1/100", "1/4", 100),
    receive("outside", input_identity(), 0, "-1", "0", 100),
    receive("partial-outside", input_identity(), 0, "-1/2", "1/2", 100),
    receive("gap-window", input_gaps(), 0, "1/2", "5/2", 100),
    receive("gap-only", input_gaps(), 0, "5/4", "7/4", 100),
    receive("gap-equal", input_gaps(), 0, "1", "1", 100),
    receive(
      "bare-number",
      input_identity(),
      0,
      "0.333333333333333333334",
      "2/3",
      100,
    ),
    receive("bdf-negative", input_bdf_negative_valid(), 0, "0", "1", 100),
    receive("range-counters", input_range_counters(), 0, "0", "1", 100),
    receive("tiny", input_tiny(), 0, "0", "1", 100),
    receive("large", input_large(), 0, "0", "1", 100),
    receive("finite-variance", input_finite_variance(), 0, "0", "1", 100),
    receive("zero", input_zero(), 0, "0", "1", 100),
    receive("no-records", input_no_records(), 0, "0", "1", 100),
    receive("point-records", input_point_records(), 0, "0", "1", 100),
    receive("negative-signal", input_identity(), -1, "0", "1", 100),
    receive("annotation-signal", input_gaps(), 1, "0", "1", 100),
    receive("annotation-empty", input_gaps(), 1, "0", "0", 100),
    receive("reversed", input_identity(), 0, "1", "0", 100),
    receive("budget-zero", input_identity(), 0, "0", "1", 0),
    receive("budget-empty", input_identity(), 0, "0", "0", 0),
    receive("budget-exceeded", input_identity(), 0, "0", "1", 2),
    receive("physical-overflow", input_physical_overflow(), 0, "0", "1", 100),
    receive("unrepresentable", input_unrepresentable(), 0, "0", "1", 100),
    receive("original-bdf-metadata", input_bdf_negative(), 0, "0", "1", 100),
  ]
  println(received.to_json().stringify())
}
