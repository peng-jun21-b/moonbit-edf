///|
// A synthetic acquired header can retain a calibration decimal smaller than
// the Double convenience view. Crop and metadata edits must keep those bytes.
fn main raise {
  let signal : @edf.Signal = {
    label: "Synthetic",
    transducer: "",
    unit: "uV",
    physical_min: 0.0,
    physical_max: 1.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: 4,
    reserved: "",
  }
  let seed = @edf.create(
    [signal],
    [
      { onset: "0", samples: [[1, 2, 3, 4]], events: [], },
      { onset: "1", samples: [[5, 6, 7, 8]], events: [], },
    ],
    "1",
    start=@edf.parse_datetime("28.02.20", "23.59.59"),
  )
  let bytes = seed.encode().to_array()
  let literal = b"1e-324  "
  let n = seed.header.signals.length()
  for i in 0..<8 {
    bytes[256 + n * 104 + i] = literal[i]
  }
  let source = @edf.decode(Bytes::from_array(bytes))
  let first = source.crop_time_window("0", "1")
  let second = source.crop(1, 1)
  let joined = @edf.decode(first.append(second).encode())
  let output = joined.encode()
  let field = Bytes::makei(8, i => {
    output[256 + joined.header.signals.length() * 104 + i]
  })
  assert_eq(field, literal)
  println("Original calibration text retained: 1e-324")
  println(
    "Double convenience minimum: \{joined.header.signals[0].physical_min}",
  )
  println("Second piece starts at \{second.header.date} \{second.header.time}")
  println("Joined record starts: " + joined.starts.join(", "))
  println(joined.window_csv([0], "0", "2", physical=false))
}
