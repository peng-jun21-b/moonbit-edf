///|
fn inventory(recording : @edf.Recording, minimum : Int) -> Json raise {
  if minimum < 1 {
    raise Failure("minimum_samples must be a positive Int")
  }
  let h = recording.header
  let channels : Array[Json] = []
  for signal in 0..<h.signals.length() {
    if h.signals[signal].is_annotation() {
      continue
    }
    channels.push({
      "signal": signal.to_json(),
      "statistics": recording.statistics(signal).to_json(),
      "flat_runs": recording.flat_runs(signal, minimum).to_json(),
    })
  }
  {
    "inspection": {
      "format": (if h.format == @edf.Edf { "edf" } else { "bdf" }).to_json(),
      "continuity": (match h.continuity {
        @edf.Plain => "plain"
        @edf.Continuous => "continuous"
        @edf.Discontinuous => "discontinuous"
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
    },
    "annotations": recording.annotations.to_json(),
    "channels": channels.to_json(),
  }
}

///|
fn receive(
  name : String,
  data : Bytes,
  minimum : Int,
  tolerance : String?,
) -> Json {
  let policy = match tolerance {
    None => @edf.Strict
    Some(value) => @edf.Tolerance(value)
  }
  let source = @edf.decode(data, time_policy=policy) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  let result = inventory(source, minimum) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  {
    "name": name.to_json(),
    "result": result,
    "source": source.data.to_array().map(b => b.to_int()).to_json(),
  }
}
