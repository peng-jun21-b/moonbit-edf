///|
fn receive(
  name : String,
  data : Bytes,
  patient : String?,
  recording : String?,
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
  let edited = source.with_identification(patient?, recording?) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  let encoded = edited.encode() catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  {
    "name": name.to_json(),
    "data": edited.data.to_array().map(b => b.to_int()).to_json(),
    "encoded": encoded.to_array().map(b => b.to_int()).to_json(),
    "source": source.data.to_array().map(b => b.to_int()).to_json(),
    "metadata": {
      "patient": edited.header.patient.to_json(),
      "recording": edited.header.recording.to_json(),
      "start": edited.header.start.to_json(),
      "declared_records": edited.header.declared_records.to_json(),
      "starts": edited.starts.to_json(),
      "annotations": edited.annotations.to_json(),
      "gaps": edited.gaps().to_json(),
    },
  }
}
