///|
fn main raise {
  println("kind mean variance rms")
  for
    (name, minimum, maximum, values) in [
      ("tiny", 1.0e-200, 2.0e-200, [-1, -1, -1, -1]),
      ("large", 1.0e200, 2.0e200, [-1, -1, -1, -1]),
      ("spread", -1.0e154, 1.0e154, [-1, 1]),
    ] {
    let signal : @edf.Signal = {
      label: "Synthetic stats",
      transducer: "",
      unit: "uV",
      physical_min: minimum,
      physical_max: maximum,
      digital_min: -1,
      digital_max: 1,
      prefilter: "",
      samples_per_record: values.length(),
      reserved: "",
    }
    let source = @edf.create(
      [signal],
      [{ onset: "0", samples: [values], events: [], }],
      "1",
    )
    let stats = @edf.decode(source.encode()).statistics(0)
    println(
      "\{name} \{stats.mean.unwrap()} \{stats.variance.unwrap()} \{stats.rms.unwrap()}",
    )
  }
}
