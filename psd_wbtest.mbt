///|
fn psd_identity_signal(per : Int) -> Signal {
  {
    label: "PSD,\"A\"",
    transducer: "",
    unit: "uV",
    physical_min: -32768.0,
    physical_max: 32767.0,
    digital_min: -32768,
    digital_max: 32767,
    prefilter: "",
    samples_per_record: per,
    reserved: "",
  }
}

///|
fn psd_record(values : Array[Int]) -> Recording raise EdfError {
  create(
    [psd_identity_signal(values.length())],
    [{ onset: "0", samples: [values], events: [], }],
    "1",
  )
}

///|
fn psd_close(actual : Double, expected : Double) -> Unit raise {
  assert_true((actual - expected).abs() <= 1.0e-9 * (1.0 + expected.abs()))
}

///|
// Independent O(N^2) DFT oracle. No MoonSpectrum helpers are used here.
fn psd_direct_dft(
  values : Array[Double],
  fs : Double,
  n : Int,
  overlap : Int,
  kind : PsdWindow,
) -> Array[Double] {
  let weights = Array::makei(n, i => {
    if kind == Rectangular {
      1.0
    } else {
      0.5 -
      0.5 * @math.cos(2.0 * @math.PI * i.to_double() / (n - 1).to_double())
    }
  })
  let energy = weights.fold(init=0.0, (sum, w) => sum + w * w)
  let frames = 1 + (values.length() - n) / (n - overlap)
  Array::makei(n / 2 + 1, k => {
    let mut total = 0.0
    for frame in 0..<frames {
      let mut re = 0.0
      let mut im = 0.0
      for j in 0..<n {
        let angle = 2.0 * @math.PI * (k * j).to_double() / n.to_double()
        let x = values[frame * (n - overlap) + j] * weights[j]
        re += x * @math.cos(angle)
        im -= x * @math.sin(angle)
      }
      total += (re * re + im * im) /
        (fs * energy) *
        (if k == 0 || k == n / 2 { 1.0 } else { 2.0 })
    }
    total / frames.to_double()
  })
}

///|
test "PSD analytic tones DC Nyquist zero and disjoint band endpoints" {
  for
    (input, expected) in [
      ([0, 2, 0, -2, 0, 2, 0, -2], [0.0, 0.0, 2.0, 0.0, 0.0]),
      ([3, 3, 3, 3, 3, 3, 3, 3], [9.0, 0.0, 0.0, 0.0, 0.0]),
      ([3, -3, 3, -3, 3, -3, 3, -3], [0.0, 0.0, 0.0, 0.0, 9.0]),
      ([0, 0, 0, 0, 0, 0, 0, 0], [0.0, 0.0, 0.0, 0.0, 0.0]),
      ([2, 2, 2, -2, 2, 2, 2, -2], [1.0, 0.0, 2.0, 0.0, 1.0]),
    ] {
    let r = psd_record(input)
    let p = r.welch_psd(
      0,
      "0",
      "1",
      segment_length=8,
      overlap_samples=0,
      window=Rectangular,
      bands=[
        { name: "lower", low_hz: 0.0, high_hz: 2.0, },
        { name: "upper", low_hz: 2.0, high_hz: 4.0, },
      ],
    )
    assert_eq(p.frequencies_hz, [0.0, 1.0, 2.0, 3.0, 4.0])
    for i in 0..<5 {
      psd_close(p.density[i], expected[i])
    }
    let mean_square = input.fold(init=0.0, (sum, v) => sum + (v * v).to_double()) /
      8.0
    psd_close(
      p.density.fold(init=0.0, (a, b) => a + b) * p.bin_width_hz,
      mean_square,
    )
    psd_close(p.bands[0].power + p.bands[1].power, mean_square)
    assert_eq(p.bands.map(b => b.bins), [2, 3])
  }
}

///|
test "PSD matches independent DFT with overlap symmetric Hann and trailing tail" {
  let values = [2, -1, 4, 0, -3, 5, 1, -2, 7, 0, 3, -4, 1, 6, -2, 3, 9, -8]
  let r = psd_record(values)
  for kind in [Rectangular, HannSymmetric] {
    let p = r.welch_psd(
      0,
      "0",
      "1",
      segment_length=8,
      overlap_samples=4,
      window=kind,
    )
    let expected = psd_direct_dft(
      values.map(v => v.to_double()),
      18.0,
      8,
      4,
      kind,
    )
    for i in 0..<expected.length() {
      psd_close(p.density[i], expected[i])
    }
    assert_eq((p.segments, p.used_samples, p.dropped_tail_samples), (3, 16, 2))
    assert_eq(p.analyzed_end.text(), "8/9")
    let doubled = psd_record(values.map(v => v * 2)).welch_psd(
      0,
      "0",
      "1",
      segment_length=8,
      overlap_samples=4,
      window=kind,
    )
    for i in 0..<expected.length() {
      psd_close(doubled.density[i], 4.0 * p.density[i])
    }
  }
}

///|
test "PSD preserves source rate and accepts a continuous EDF D island only" {
  let r = create(
    [psd_identity_signal(8), psd_identity_signal(4)],
    [
      {
        onset: "0.25",
        samples: [[0, 2, 0, -2, 0, 2, 0, -2], [1, -1, 1, -1]],
        events: [],
      },
      {
        onset: "2.25",
        samples: [[0, 2, 0, -2, 0, 2, 0, -2], [1, -1, 1, -1]],
        events: [],
      },
    ],
    "1",
    continuity=Discontinuous,
  )
  for (signal, rate) in [(0, "8"), (1, "4")] {
    let p = r.welch_psd(
      signal,
      "2.25",
      "3.25",
      segment_length=4,
      overlap_samples=0,
      window=Rectangular,
    )
    assert_eq(p.sample_rate.text(), rate)
    assert_eq(p.first_sample_time.text(), "2.25")
    assert_eq(p.analyzed_end.text(), "3.25")
    assert_eq(p.psd_unit, "(uV)^2/Hz")
    assert_eq(p.calibration.physical_min_text, "-32768")
  }
  assert_true(
    try {
      ignore(
        r.welch_psd(
          0,
          "0.25",
          "3.25",
          segment_length=4,
          overlap_samples=0,
          window=Rectangular,
        ),
      )
      false
    } catch {
      Invalid(_) => true
      _ => false
    },
  )
}
