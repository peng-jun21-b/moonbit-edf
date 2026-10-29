///|
fn channels(recording : @edf.Recording) -> Array[Json] raise @edf.EdfError {
  let results : Array[Json] = []
  for signal in 0..<recording.header.signals.length() {
    let channel = recording.header.signals[signal]
    if channel.is_annotation() {
      continue
    }
    let per = channel.samples_per_record
    let total = recording.records * per
    results.push({
      "signal": signal.to_json(),
      "values": Array::makei(total, i => {
        recording.digital(signal, i / per, i % per)
      }).to_json(),
      "times": Array::makei(total, i => {
        recording.sample_time(signal, i / per, i % per)
      }).to_json(),
    })
  }
  results
}

///|
fn receive(
  name : String,
  data : Bytes,
  signal : Int,
  first_sample : Int,
  values : Array[Int],
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
  let edited = source.with_digital_samples(signal, first_sample, values) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  let encoded = edited.encode() catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  let received = channels(edited) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  {
    "name": name.to_json(),
    "data": edited.data.to_array().map(b => b.to_int()).to_json(),
    "encoded": encoded.to_array().map(b => b.to_int()).to_json(),
    "source": source.data.to_array().map(b => b.to_int()).to_json(),
    "channels": received.to_json(),
    "metadata": {
      "patient": edited.header.patient.to_json(),
      "recording": edited.header.recording.to_json(),
      "declared_records": edited.header.declared_records.to_json(),
      "starts": edited.starts.to_json(),
      "annotations": edited.annotations.to_json(),
      "gaps": edited.gaps().to_json(),
    },
  }
}
