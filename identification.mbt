///|
/// Replace selected raw identification fields without rewriting other bytes.
/// Omitted fields stay unchanged; the existing encode count-finalization policy
/// still applies if the caller subsequently calls encode instead of using data.
/// A plus recording keeps its two leading date-bearing identification tokens.
pub fn Recording::with_identification(
  self : Recording,
  patient? : String,
  recording? : String,
) -> Recording raise EdfError {
  if patient is None && recording is None {
    return self
  }
  let out = self.data.to_array()
  if patient is Some(value) {
    put_text(out, 8, 80, value)
  }
  if recording is Some(value) {
    put_text(out, 88, 80, value)
    if self.header.continuity != Plain {
      let previous = self.header.recording
        .split(" ")
        .filter(s => !s.is_empty())
        .map(s => s.to_owned())
        .to_array()
      let next = value
        .split(" ")
        .filter(s => !s.is_empty())
        .map(s => s.to_owned())
        .to_array()
      if previous.length() < 2 ||
        next.length() < 2 ||
        previous[0] != next[0] ||
        previous[1] != next[1] {
        raise Invalid(
          "plus recording identification must retain its start-date prefix",
        )
      }
    }
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}
