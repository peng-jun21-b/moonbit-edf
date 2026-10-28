///|
/// A match retains its index in this Recording's annotation array. Re-query
/// after editing or selecting channels before reusing an index.
pub struct AnnotationMatch {
  annotation_index : Int
  annotation : Annotation
} derive(Debug, ToJson)

///|
pub extend AnnotationMatch with @debug.Debug::{to_repr}

///|
pub extend AnnotationMatch with ToJson::{to_json}

///|
/// Find events intersecting [start,end), preserving storage order and identity.
/// Positive durations overlap the interval; missing/zero durations are points.
/// Set include_duration=false to select only onsets. Events are not clipped.
pub fn[A : TimeInput, B : TimeInput] Recording::find_annotations(
  self : Recording,
  start : A,
  end : B,
  include_duration? : Bool = true,
  max_annotations? : Int = 2147483647,
) -> Array[AnnotationMatch] raise EdfError {
  if max_annotations < 1 {
    raise Invalid("annotation budget must be positive")
  }
  let start = Time::parse(TimeInput::to_time_text(start))
  let end = Time::parse(TimeInput::to_time_text(end))
  if start > end {
    raise Invalid("annotation window requires start <= end")
  }
  let result = []
  if start == end {
    return result
  }
  let zero = Time::parse("0")
  for index in 0..<self.annotations.length() {
    let annotation = self.annotations[index]
    let onset = Time::parse(annotation.onset)
    let duration = if include_duration {
      Time::parse(annotation.duration.unwrap_or("0"))
    } else {
      zero
    }
    let matches = if duration > zero {
      onset < end && onset.add(duration) > start
    } else {
      start <= onset && onset < end
    }
    if matches {
      if result.length() == max_annotations {
        raise Limit("annotation window exceeds requested annotation limit")
      }
      result.push({ annotation_index: index, annotation, })
    }
  }
  result
}
