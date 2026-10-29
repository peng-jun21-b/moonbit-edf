///|
fn receive(
  name : String,
  left_data : Bytes,
  right_data : Bytes,
  common_clock : Bool,
  left_tolerance : String?,
  right_tolerance : String?,
) -> Json {
  let left = @edf.decode(
    left_data,
    time_policy=match left_tolerance {
      None => @edf.Strict
      Some(v) => @edf.Tolerance(v)
    },
  ) catch {
    e =>
      return {
        "name": name.to_json(),
        "error": ("left: " + @debug.to_string(e)).to_json(),
      }
  }
  let right = @edf.decode(
    right_data,
    time_policy=match right_tolerance {
      None => @edf.Strict
      Some(v) => @edf.Tolerance(v)
    },
  ) catch {
    e =>
      return {
        "name": name.to_json(),
        "error": ("right: " + @debug.to_string(e)).to_json(),
      }
  }
  let merged = left.merge_signals(right, common_clock~) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  let samples : Array[Json] = []
  for record in 0..<merged.records {
    for signal, s in merged.header.signals {
      if s.is_annotation() {
        continue
      }
      for sample in 0..<s.samples_per_record {
        let digital = merged.digital(signal, record, sample) catch {
          e => abort(@debug.to_string(e))
        }
        let time = merged.sample_time(signal, record, sample) catch {
          e => abort(@debug.to_string(e))
        }
        samples.push({
          "signal": signal.to_json(),
          "record": record.to_json(),
          "sample": sample.to_json(),
          "digital": digital.to_json(),
          "time": time.to_json(),
        })
      }
    }
  }
  {
    "name": name.to_json(),
    "output": merged.data.to_array().map(b => b.to_int()).to_json(),
    "left_after": left.data.to_array().map(b => b.to_int()).to_json(),
    "right_after": right.data.to_array().map(b => b.to_int()).to_json(),
    "native": {
      "records": merged.records.to_json(),
      "signals": merged.header.signals.length().to_json(),
      "starts": merged.starts.to_json(),
      "gaps": merged.gaps().to_json(),
      "annotations": merged.annotations.to_json(),
      "samples": samples.to_json(),
    },
  }
}
