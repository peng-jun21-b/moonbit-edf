///|
/// Replace a sample-index range in one ordinary channel, retaining all other
/// bytes and the original reading policy. Values follow create's digital bounds.
/// Indices follow recorded samples across records; no samples are added in gaps.
pub fn Recording::with_digital_samples(
  self : Recording,
  signal : Int,
  first_sample : Int,
  values : Array[Int],
) -> Recording raise EdfError {
  if signal < 0 ||
    signal >= self.header.signals.length() ||
    self.header.signals[signal].is_annotation() {
    raise Invalid("ordinary signal index required")
  }
  let channel = self.header.signals[signal]
  let per = channel.samples_per_record
  let total = self.records * per
  if first_sample < 0 ||
    first_sample > total ||
    values.length() > total - first_sample {
    raise Invalid("invalid digital replacement range")
  }
  for value in values {
    if value < channel.digital_min || value > channel.digital_max {
      raise Invalid("sample outside digital calibration limits")
    }
  }
  if values.is_empty() {
    return self
  }
  let out = self.data.to_array()
  let width = self.header.format.width()
  for i, value in values {
    let index = first_sample + i
    put_sample(
      out,
      self.header.bytes +
      index / per * self.header.record_bytes +
      self.header.offsets[signal] +
      index % per * width,
      width,
      value,
    )
  }
  decode(Bytes::from_array(out), time_policy=self.time_policy)
}
