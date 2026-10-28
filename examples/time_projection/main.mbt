///|
// A plotting/export consumer should get finite/subnormal values here, while
// all decisions about sample and event time continue to use the exact Time.
fn main raise {
  for text in ["1e324/9007199254740991", "9007199254740991/3e339"] {
    let time = @edf.Time::parse(text)
    let value = time.to_double()
    println("projection,\{text},\{value},\{value.reinterpret_as_uint64()}")
  }
}
