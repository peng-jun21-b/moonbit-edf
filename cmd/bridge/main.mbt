///|
extern "js" fn fail_bytes(message : String) -> Bytes =
  #| (message) => { throw new Error(message); }

///|
extern "js" fn fail_string(message : String) -> String =
  #| (message) => { throw new Error(message); }

///|
fn object(text : String) -> Map[String, Json] raise {
  match @json.parse(text) {
    Object(o) => o
    _ => raise Failure("options must be an object")
  }
}

///|
fn[T : @json.FromJson] required(o : Map[String, Json], key : String) -> T raise {
  match o.get(key) {
    Some(j) => @json.from_json(j)
    None => raise Failure("missing option: " + key)
  }
}

///|
fn[T : @json.FromJson] optional(
  o : Map[String, Json],
  key : String,
  fallback : T,
) -> T raise {
  match o.get(key) {
    Some(j) => @json.from_json(j)
    None => fallback
  }
}

///|
fn time_json(value : Json) -> String raise {
  match value {
    String(text) => text
    Number(_, repr=Some(text)) => text
    Number(value, ..) => {
      if value.is_nan() || value.is_inf() {
        raise Failure("non-finite time")
      }
      value.to_string()
    }
    _ => raise Failure("time requires a decimal string or number")
  }
}

///|
fn time_option(o : Map[String, Json], key : String) -> String raise {
  time_json(required(o, key))
}

///|
extern "js" fn digital_edit_options(text : String) -> String =
  #| (text) => {
  #|   const sources = new WeakMap();
  #|   const options = JSON.parse(text, function(key, value, context) {
  #|     if (typeof value === 'number') {
  #|       let fields = sources.get(this);
  #|       if (!fields) { fields = new Map(); sources.set(this, fields); }
  #|       fields.set(key, context.source);
  #|     }
  #|     return value;
  #|   });
  #|   const invalid = () => { throw new Error('samples-set requires Int integers'); };
  #|   function integer(object, key) {
  #|     const value = object[key];
  #|     if (!Number.isInteger(value) || value < -2147483648 || value > 2147483647) invalid();
  #|     const source = sources.get(object)?.get(key);
  #|     if (typeof source !== 'string') invalid();
  #|     const [mantissa, exponent = '0'] = source.toLowerCase().split('e');
  #|     const fraction = (mantissa.split('.')[1] ?? '').length;
  #|     const digits = mantissa.replace('-', '').replace('.', '');
  #|     const scale = fraction - Number(exponent);
  #|     if (scale > 0 && /[1-9]/.test(digits.slice(-scale))) invalid();
  #|   }
  #|   integer(options, 'signal');
  #|   integer(options, 'first_sample');
  #|   if (!Array.isArray(options.values)) invalid();
  #|   for (let i = 0; i < options.values.length; i++) integer(options.values, String(i));
  #|   return text;
  #| }

///|
fn policy(o : Map[String, Json]) -> @lib.TimePolicy raise {
  match o.get("time_tolerance") {
    None => @lib.Strict
    Some(value) => @lib.Tolerance(time_json(value))
  }
}

///|
fn psd_report(recording : @lib.Recording, o : Map[String, Json]) -> Json raise {
  let allowed = [
    "command", "signal", "start", "end", "segment_length", "overlap_samples", "window",
    "nfft", "bands", "max_samples", "max_segments", "time_tolerance", "detrend",
    "scaling", "sides", "average",
  ]
  for key in o.keys() {
    if !allowed.contains(key) {
      raise Failure("unknown PSD option: " + key)
    }
  }
  if optional(o, "detrend", "none") != "none" ||
    optional(o, "scaling", "density") != "density" ||
    optional(o, "sides", "one-sided") != "one-sided" ||
    optional(o, "average", "mean") != "mean" {
    raise Failure(
      "PSD supports detrend=none, scaling=density, sides=one-sided, average=mean",
    )
  }
  let window = match required(o, "window") {
    "rectangular" => @lib.Rectangular
    "hann_symmetric" => @lib.HannSymmetric
    _ => raise Failure("PSD window requires rectangular or hann_symmetric")
  }
  let descriptions : Array[Map[String, Json]] = optional(o, "bands", [])
  let bands : Array[@lib.PsdBand] = descriptions.map(d => {
    name: required(d, "name"),
    low_hz: required(d, "low_hz"),
    high_hz: required(d, "high_hz"),
  })
  let length : Int = required(o, "segment_length")
  recording
  .welch_psd(
    required(o, "signal"),
    time_option(o, "start"),
    time_option(o, "end"),
    segment_length=length,
    overlap_samples=required(o, "overlap_samples"),
    window~,
    nfft=optional(o, "nfft", length),
    bands~,
    max_samples=optional(o, "max_samples", 1048576),
    max_segments=optional(o, "max_segments", 8192),
  )
  .to_json()
}

///|
fn do_report(data : Bytes, text : String) -> String raise {
  let o = object(text)
  let recording = @lib.decode(data, time_policy=policy(o))
  let h = recording.header
  let cmd : String = optional(o, "command", "inspect")
  let result : Json = match cmd {
    "inspect" | "validate" =>
      {
        "format": (if h.format == @lib.Edf { "edf" } else { "bdf" }).to_json(),
        "continuity": (match h.continuity {
          @lib.Plain => "plain"
          @lib.Continuous => "continuous"
          @lib.Discontinuous => "discontinuous"
        }).to_json(),
        "records": recording.records.to_json(),
        "declared_records": h.declared_records.to_json(),
        "duration": h.duration.to_json(),
        "date": h.date.to_json(),
        "time": h.time.to_json(),
        "patient": h.patient.to_json(),
        "recording": h.recording.to_json(),
        "signals": h.signals.to_json(),
        "starts": recording.starts.to_json(),
        "annotations": recording.annotations.length().to_json(),
        "gaps": recording.gaps().to_json(),
      }
    "stats" => recording.statistics(required(o, "signal")).to_json()
    "window-stats" =>
      recording
      .window_statistics(
        required(o, "signal"),
        time_option(o, "start"),
        time_option(o, "end"),
        max_samples=optional(o, "max_samples", 2147483647),
      )
      .to_json()
    "psd" => psd_report(recording, o)
    "epoch" =>
      recording
      .event_window(
        required(o, "annotation"),
        required(o, "signals"),
        before=time_option(o, "before"),
        after=time_option(o, "after"),
        include_duration=optional(o, "include_duration", true),
        allow_partial=optional(o, "allow_partial", false),
        max_samples=optional(o, "max_samples", 2147483647),
      )
      .to_json()
    "window" =>
      recording
      .time_window(
        required(o, "signal"),
        time_option(o, "start"),
        time_option(o, "end"),
        max_samples=optional(o, "max_samples", 2147483647),
      )
      .to_json()
    "window-csv" =>
      {
        "text": recording
        .window_csv(
          required(o, "signals"),
          time_option(o, "start"),
          time_option(o, "end"),
          physical=optional(o, "physical", true),
          max_samples=optional(o, "max_samples", 2147483647),
        )
        .to_json(),
      }
    "annotations" => recording.annotations.to_json()
    "annotations-window" =>
      recording
      .find_annotations(
        time_option(o, "start"),
        time_option(o, "end"),
        include_duration=optional(o, "include_duration", true),
        max_annotations=optional(o, "max_annotations", 2147483647),
      )
      .to_json()
    "annotations-exact" => recording.annotations_exact().to_json()
    "window-exact" =>
      recording
      .time_window_exact(
        required(o, "signal"),
        time_option(o, "start"),
        time_option(o, "end"),
        max_samples=optional(o, "max_samples", 2147483647),
      )
      .to_json()
    "epoch-exact" =>
      recording
      .event_window_exact(
        required(o, "annotation"),
        required(o, "signals"),
        before=time_option(o, "before"),
        after=time_option(o, "after"),
        include_duration=optional(o, "include_duration", true),
        allow_partial=optional(o, "allow_partial", false),
        max_samples=optional(o, "max_samples", 2147483647),
      )
      .to_json()
    "gaps" => recording.gaps().to_json()
    "flat" =>
      recording
      .flat_runs(required(o, "signal"), required(o, "minimum_samples"))
      .to_json()
    "csv" => {
      let first : Int = optional(o, "first_record", 0)
      {
        "text": recording
        .csv(
          required(o, "signals"),
          first_record=first,
          records=optional(o, "records", recording.records - first),
          physical=optional(o, "physical", true),
        )
        .to_json(),
      }
    }
    "channel" => {
      let s : Int = required(o, "signal")
      if s < 0 || s >= h.signals.length() || h.signals[s].is_annotation() {
        raise Failure("ordinary signal index required")
      }
      let per = h.signals[s].samples_per_record
      let start : Int = optional(o, "start", 0)
      let count : Int = optional(o, "count", recording.records * per)
      if start < 0 ||
        count < 0 ||
        start > recording.records * per ||
        count > recording.records * per - start {
        raise Failure("invalid sample range")
      }
      let values = Array::makei(count, i => {
        if optional(o, "physical", false) {
          recording.physical(s, (start + i) / per, (start + i) % per)
        } else {
          recording.digital(s, (start + i) / per, (start + i) % per).to_double()
        }
      })
      let times = Array::makei(count, i => {
        recording.sample_time(s, (start + i) / per, (start + i) % per)
      })
      { "values": values.to_json(), "times": times.to_json() }
    }
    _ => raise Failure("unknown report command")
  }
  result.stringify()
}

///|
pub fn report(data : Bytes, options : String) -> String {
  do_report(data, options) catch {
    e => fail_string(@debug.to_string(e))
  }
}

///|
fn from_options(o : Map[String, Json]) -> @lib.Recording raise {
  let format = match optional(o, "format", "edf") {
    "edf" => @lib.Edf
    "bdf" => @lib.Bdf
    _ => raise Failure("format must be edf or bdf")
  }
  let continuity = match optional(o, "continuity", "continuous") {
    "plain" => @lib.Plain
    "continuous" => @lib.Continuous
    "discontinuous" => @lib.Discontinuous
    _ => raise Failure("invalid continuity")
  }
  let descriptions : Array[Map[String, Json]] = required(o, "signals")
  let signals : Array[@lib.Signal] = descriptions.map(d => {
    label: required(d, "label"),
    transducer: optional(d, "transducer", ""),
    unit: optional(d, "unit", "uV"),
    physical_min: optional(d, "physical_min", -100.0),
    physical_max: optional(d, "physical_max", 100.0),
    digital_min: optional(
      d,
      "digital_min",
      if format == @lib.Edf {
        -32768
      } else {
        -8388608
      },
    ),
    digital_max: optional(
      d,
      "digital_max",
      if format == @lib.Edf {
        32767
      } else {
        8388607
      },
    ),
    prefilter: optional(d, "prefilter", ""),
    samples_per_record: required(d, "samples_per_record"),
    reserved: "",
  })
  let input_records : Array[Map[String, Json]] = required(o, "records")
  let records : Array[@lib.Record[String]] = input_records.map(r => {
    let descriptions : Array[Map[String, Json]] = optional(r, "events", [])
    let events : Array[@lib.Event[String]] = descriptions.map(e => {
      onset: time_option(e, "onset"),
      text: required(e, "text"),
      duration: match e.get("duration") {
        None | Some(Null) => None
        Some(value) => Some(time_json(value))
      },
    })
    { onset: time_option(r, "onset"), samples: required(r, "samples"), events, }
  })
  return @lib.create(
    signals,
    records,
    time_option(o, "duration"),
    format~,
    continuity~,
    start=@lib.parse_datetime(
      optional(o, "date", "01.01.20"),
      optional(o, "time", "00.00.00"),
    ),
    patient=optional(o, "patient", "X X X X"),
  )
}

///|
fn do_transform(data : Bytes, text : String) -> Bytes raise {
  let o = object(text)
  let cmd : String = required(o, "command")
  if cmd == "samples-set" {
    ignore(digital_edit_options(text))
  }
  let recording = if cmd == "create" {
    from_options(o)
  } else {
    let r = @lib.decode(data, time_policy=policy(o))
    match cmd {
      "copy" => r
      "samples-set" =>
        return r.with_digital_samples(
            required(o, "signal"),
            required(o, "first_sample"),
            required(o, "values"),
          ).data
      "identification-set" =>
        // Preserve unknown count spelling and every non-target byte.
        return r.with_identification(
            patient?=match o.get("patient") {
              None => None
              Some(v) => Some(@json.from_json(v))
            },
            recording?=match o.get("recording") {
              None => None
              Some(v) => Some(@json.from_json(v))
            },
          ).data
      "select" => r.select(required(o, "signals"))
      "crop" => r.crop(required(o, "first_record"), required(o, "records"))
      "plus" => r.to_plus()
      "crop-time" =>
        r.crop_time_window(time_option(o, "start"), time_option(o, "end"))
      "annotations-set" => r.with_annotations(required(o, "annotations"))
      "annotation-add" =>
        r.add_annotation(
          time_option(o, "onset"),
          required(o, "text"),
          duration?=match o.get("duration") {
            None | Some(Null) => None
            Some(v) => Some(time_json(v))
          },
          record?=match o.get("record") {
            None => None
            Some(v) => Some(@json.from_json(v))
          },
          signal?=match o.get("signal") {
            None => None
            Some(v) => Some(@json.from_json(v))
          },
        )
      "annotation-remove" => r.remove_annotation(required(o, "index"))
      "annotations-remove" => {
        let indices : Array[Int] = required(o, "indices")
        // Validation above still applies; an empty file edit must not invoke
        // encode's deliberate finalization of an unknown record-count field.
        if indices.is_empty() {
          return data
        }
        r.remove_annotations(indices)
      }
      "annotation-update" =>
        r.update_annotation(required(o, "index"), required(o, "annotation"))
      "annotation-signal" => r.add_annotation_signal()
      "rename" => r.rename_signal(required(o, "signal"), required(o, "label"))
      "calibrate" =>
        r.map_physical(
          required(o, "signal"),
          required(o, "scale"),
          offset=optional(o, "offset", 0.0),
          unit?=match o.get("unit") {
            None => None
            Some(v) => Some(@json.from_json(v))
          },
        )
      _ => raise Failure("unknown transform command")
    }
  }
  recording.encode()
}

///|
pub fn transform(data : Bytes, options : String) -> Bytes {
  do_transform(data, options) catch {
    e => fail_bytes(@debug.to_string(e))
  }
}

///|
fn do_append(left : Bytes, right : Bytes, text : String) -> Bytes raise {
  let o = object(text)
  let a = @lib.decode(left, time_policy=policy(o))
  let b = @lib.decode(right, time_policy=policy(o))
  a
  .append(
    b,
    offset?=match o.get("offset") {
      None => None
      Some(value) => Some(time_json(value))
    },
  )
  .encode()
}

///|
pub fn append_recordings(
  left : Bytes,
  right : Bytes,
  options : String,
) -> Bytes {
  do_append(left, right, options) catch {
    e => fail_bytes(@debug.to_string(e))
  }
}

///|
fn review_policy(
  options : Map[String, Json],
  side : String,
) -> @lib.TimePolicy raise {
  match options.get(side) {
    None => @lib.Strict
    Some(Object(fields)) => {
      for key, _ in fields {
        if key != "time_tolerance" {
          raise Failure("unsupported " + side + " read option: " + key)
        }
      }
      policy(fields)
    }
    _ => raise Failure(side + " read options must be an object")
  }
}

///|
fn do_review_annotations(
  left : Bytes,
  right : Bytes,
  text : String,
) -> String raise {
  let options = object(text)
  for key, _ in options {
    if key != "left" && key != "right" {
      raise Failure("unsupported comparison option: " + key)
    }
  }
  let left_policy = review_policy(options, "left")
  let right_policy = review_policy(options, "right")
  let left = @lib.decode(left, time_policy=left_policy) catch {
    e => raise Failure("left: " + @debug.to_string(e))
  }
  let right = @lib.decode(right, time_policy=right_policy) catch {
    e => raise Failure("right: " + @debug.to_string(e))
  }
  @lib.compare_annotations(left, right).to_json().stringify()
}

///|
pub fn review_annotations(
  left : Bytes,
  right : Bytes,
  options : String,
) -> String {
  do_review_annotations(left, right, options) catch {
    Failure(message) => fail_string(message)
    e => fail_string(@debug.to_string(e))
  }
}

///|
fn do_merge_recordings(
  left : Bytes,
  right : Bytes,
  text : String,
) -> Bytes raise {
  let options = object(text)
  for key, _ in options {
    if key != "common_clock" && key != "left" && key != "right" {
      raise Failure("unsupported merge option: " + key)
    }
  }
  let left_policy = review_policy(options, "left")
  let right_policy = review_policy(options, "right")
  let left = @lib.decode(left, time_policy=left_policy) catch {
    e => raise Failure("left: " + @debug.to_string(e))
  }
  let right = @lib.decode(right, time_policy=right_policy) catch {
    e => raise Failure("right: " + @debug.to_string(e))
  }
  left
  .merge_signals(right, common_clock=optional(options, "common_clock", false))
  .encode()
}

///|
pub fn merge_recordings(left : Bytes, right : Bytes, options : String) -> Bytes {
  do_merge_recordings(left, right, options) catch {
    Failure(message) => fail_bytes(message)
    e => fail_bytes(@debug.to_string(e))
  }
}

///|
fn main {

}
