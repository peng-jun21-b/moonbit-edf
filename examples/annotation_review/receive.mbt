///|
fn receive(
  name : String,
  left_data : Bytes,
  right_data : Bytes,
  left_tolerance : String?,
  right_tolerance : String?,
) -> Json {
  let left = @edf.decode(
    left_data,
    time_policy=match left_tolerance {
      None => @edf.Strict
      Some(value) => @edf.Tolerance(value)
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
      Some(value) => @edf.Tolerance(value)
    },
  ) catch {
    e =>
      return {
        "name": name.to_json(),
        "error": ("right: " + @debug.to_string(e)).to_json(),
      }
  }
  let result = @edf.compare_annotations(left, right) catch {
    e =>
      return { "name": name.to_json(), "error": @debug.to_string(e).to_json() }
  }
  {
    "name": name.to_json(),
    "result": result.to_json(),
    "left_source": left_data.to_array().map(b => b.to_int()).to_json(),
    "right_source": right_data.to_array().map(b => b.to_int()).to_json(),
    "left_after": left.data.to_array().map(b => b.to_int()).to_json(),
    "right_after": right.data.to_array().map(b => b.to_int()).to_json(),
  }
}
