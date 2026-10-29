///|
fn main {
  let received : Array[Json] = [
    receive("continuous", raw_continuous_edf(), 2, None),
    receive("longer-threshold", raw_continuous_edf(), 4, None),
    receive("gaps", raw_gaps_bdf(), 2, None),
    receive("tolerant", raw_tolerant_edf(), 2, Some("0.010000000000000000002")),
    receive("empty", raw_empty_edf(), 1, None),
    receive("annotation-only", raw_annotation_only_edf(), 3, None),
    receive("zero-threshold", raw_continuous_edf(), 0, None),
    receive("negative-threshold", raw_annotation_only_edf(), -1, None),
    receive("physical-overflow", raw_overflow_edf(), 2, None),
    receive("partial-source", raw_partial_edf(), 2, None),
    receive("strict-jitter", raw_tolerant_edf(), 2, None),
    receive("negative-tolerance", raw_continuous_edf(), 2, Some("-1")),
  ]
  println(received.to_json().stringify())
}
