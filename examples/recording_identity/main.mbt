///|
fn with_identity(
  source : @edf.Recording,
  identity : String,
) -> @edf.Recording raise {
  let bytes = source.encode().to_array()
  let text = @utf8.encode(identity)
  for i in 0..<80 {
    bytes[88 + i] = if i < text.length() { text[i] } else { b' ' }
  }
  @edf.decode(Bytes::from_array(bytes))
}

///|
fn main raise {
  println("format kind date time retained_tail last_sample")
  let identity = "Startdate X Adm Tech Dev " + String::make(55, 'N')
  for format in [@edf.Edf, @edf.Bdf] {
    let name = if format == @edf.Edf { "EDF" } else { "BDF" }
    let signal : @edf.Signal = {
      label: "Identity demo",
      transducer: "",
      unit: "uV",
      physical_min: -100.0,
      physical_max: 100.0,
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
      format~,
      start={ year: 2020, month: 1, day: 1, hour: 23, minute: 59, second: 59, },
    )
    let source = with_identity(seed, identity)
    for
      (kind, cropped) in [
        ("crop", source.crop(1, 1)),
        ("crop-time", source.crop_time_window("1", "2")),
      ] {
      println(
        "\{name} \{kind} \{cropped.header.date} \{cropped.header.time} \{cropped.header.recording == identity} \{cropped.digital(0, 0, 3)}",
      )
    }
    let checked = try {
      ignore(with_identity(seed, "").crop_time_window("1", "2"))
      false
    } catch {
      @edf.Invalid(message) =>
        message == "cannot update malformed plus recording identification"
      _ => false
    }
    println("\{name} invalid \{checked}")
  }
}
