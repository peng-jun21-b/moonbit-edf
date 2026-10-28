///|
fn identity_source(
  format : @edf.Format,
  identity : String,
  future? : Bool = false,
  plain? : Bool = false,
) -> @edf.Recording raise {
  let signal : @edf.Signal = {
    label: "Identity sample",
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
  let source = @edf.create(
    [signal],
    [
      { onset: "0", samples: [[1, 2, 3, 4]], events: [], },
      {
        onset: if future {
          "2524608000"
        } else {
          "1"
        },
        samples: [[5, 6, 7, 8]],
        events: [],
      },
    ],
    "1",
    format~,
    continuity=if plain {
      @edf.Plain
    } else if future {
      @edf.Discontinuous
    } else {
      @edf.Continuous
    },
    start={
      year: 2020,
      month: 1,
      day: 1,
      hour: if future {
        0
      } else {
        23
      },
      minute: if future {
        0
      } else {
        59
      },
      second: if future {
        0
      } else {
        59
      },
    },
  )
  let data = source.encode().to_array()
  let text = @utf8.encode(identity)
  assert_true(text.length() <= 80)
  for i in 0..<80 {
    data[88 + i] = if i < text.length() { text[i] } else { b' ' }
  }
  @edf.decode(Bytes::from_array(data))
}

///|
test "malformed imported plus identities have checked errors in both crop modes" {
  for format in [@edf.Edf, @edf.Bdf] {
    for identity in ["", "X", "Startdate X", "Other X X X X"] {
      let source = identity_source(format, identity)
      let before = source.encode()
      for time_crop in [false, true] {
        assert_true(
          try {
            ignore(
              if time_crop {
                source.crop_time_window("1", "2")
              } else {
                source.crop(1, 1)
              },
            )
            false
          } catch {
            @edf.Invalid(message) =>
              message == "cannot update malformed plus recording identification"
            _ => false
          },
        )
      }
      assert_eq(source.encode(), before)
    }
  }
}

///|
test "cropping updates the day and preserves valid identity tail fields" {
  for format in [@edf.Edf, @edf.Bdf] {
    for
      (identity, expected) in [
        ("Startdate X X X X", "Startdate 02-JAN-2020 X X X"),
        (
          "Startdate 01-JAN-2020 Adm Tech Dev Extra_notes", "Startdate 02-JAN-2020 Adm Tech Dev Extra_notes",
        ),
        (
          "  Startdate   X  Adm Tech   Dev  Tail", "Startdate 02-JAN-2020 Adm Tech Dev Tail",
        ),
      ] {
      let source = identity_source(format, identity)
      for cropped in [source.crop(1, 1), source.crop_time_window("1", "2")] {
        let got = @edf.decode(cropped.encode())
        assert_eq(got.header.recording, expected)
        assert_eq(got.header.date, "02.01.20")
        assert_eq(got.header.time, "00.00.00")
        assert_eq(got.digital(0, 0, 0), 5)
        assert_eq(got.sample_time(0, 0, 3).text(), "0.75")
      }
    }
    let plain = identity_source(format, "free recording identity", plain=true)
    assert_eq(plain.crop(1, 1).header.recording, "free recording identity")
    assert_eq(
      plain.crop_time_window("1", "2").header.recording,
      "Startdate 02-JAN-2020 X X X",
    )
  }
}

///|
test "full identity fields retain unknown dates only when the header supplies the year" {
  let unknown = "Startdate X Adm Tech Dev " + String::make(55, 'N')
  let known = "Startdate 01-JAN-2020 Adm Tech Dev " + String::make(45, 'N')
  assert_eq(unknown.length(), 80)
  assert_eq(known.length(), 80)
  for format in [@edf.Edf, @edf.Bdf] {
    let source = identity_source(format, unknown)
    for cropped in [source.crop(1, 1), source.crop_time_window("1", "2")] {
      assert_eq(cropped.header.recording, unknown)
      assert_eq(cropped.header.date, "02.01.20")
      assert_eq(cropped.digital(0, 0, 3), 8)
    }
    let future = identity_source(format, unknown, future=true)
    for time_crop in [false, true] {
      assert_true(
        try {
          ignore(
            if time_crop {
              future.crop_time_window("2524608000", "2524608001")
            } else {
              future.crop(1, 1)
            },
          )
          false
        } catch {
          @edf.Invalid(message) =>
            message.has_prefix("header text exceeds field width 80:")
          _ => false
        },
      )
    }
    let future = identity_source(format, known, future=true)
    for
      cropped in [
        future.crop(1, 1),
        future.crop_time_window("2524608000", "2524608001"),
      ] {
      let got = @edf.decode(cropped.encode())
      assert_eq(
        got.header.recording,
        "Startdate 01-JAN-2100 Adm Tech Dev " + String::make(45, 'N'),
      )
      assert_eq(got.header.date, "01.01.yy")
      assert_eq(got.header.start.year, 2100)
      assert_eq(got.digital(0, 0, 3), 8)
    }
  }
}
