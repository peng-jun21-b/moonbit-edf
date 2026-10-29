///|
/// Complete clock and storage context; times remain relative to this header.
pub struct AnnotationReviewContext {
  format : String
  continuity : String
  patient : String
  recording : String
  date : String
  time : String
  start : DateTime
  timezone : String
  records : Int
  declared_records : Int
  duration : String
  signals : Array[Signal]
  starts : Array[String]
  gaps : Array[Gap]
  annotations : Int
  time_tolerance : String?
} derive(Debug)

///|
pub struct AnnotationReviewSource {
  context : AnnotationReviewContext
  annotations : Array[Annotation]
} derive(Debug)

///|
/// All occurrence indices are local to their respective input snapshot.
/// Counts do not identify which indistinguishable duplicate was removed.
pub struct AnnotationReviewGroup {
  onset : Time
  duration : Time?
  text : String
  left_indices : Array[Int]
  right_indices : Array[Int]
  left : Int
  right : Int
  retained : Int
  removed : Int
  added : Int
} derive(Debug)

///|
pub struct AnnotationReviewTotals {
  left : Int
  right : Int
  retained : Int
  removed : Int
  added : Int
  groups : Int
} derive(Debug, ToJson)

///|
pub struct AnnotationReview {
  frame : String
  status : String
  header_zero_equal : Bool
  header_civil_delta_seconds : String
  needs_clock_review : Bool
  left : AnnotationReviewSource
  right : AnnotationReviewSource
  groups : Array[AnnotationReviewGroup]
  totals : AnnotationReviewTotals
} derive(Debug, ToJson)

///|
pub extend AnnotationReviewContext with @debug.Debug::{to_repr}

///|
pub extend AnnotationReviewContext with ToJson::{to_json}

///|
pub extend AnnotationReviewSource with @debug.Debug::{to_repr}

///|
pub extend AnnotationReviewSource with ToJson::{to_json}

///|
pub extend AnnotationReviewGroup with @debug.Debug::{to_repr}

///|
pub extend AnnotationReviewGroup with ToJson::{to_json}

///|
pub extend AnnotationReviewTotals with @debug.Debug::{to_repr}

///|
pub extend AnnotationReviewTotals with ToJson::{to_json}

///|
pub extend AnnotationReview with @debug.Debug::{to_repr}

///|
pub extend AnnotationReview with ToJson::{to_json}

///|
pub impl ToJson for AnnotationReviewContext with fn to_json(self) -> Json {
  {
    "format": self.format.to_json(),
    "continuity": self.continuity.to_json(),
    "patient": self.patient.to_json(),
    "recording": self.recording.to_json(),
    "date": self.date.to_json(),
    "time": self.time.to_json(),
    "start": self.start.to_json(),
    "timezone": self.timezone.to_json(),
    "records": self.records.to_json(),
    "declared_records": self.declared_records.to_json(),
    "duration": self.duration.to_json(),
    "signals": self.signals.to_json(),
    "starts": self.starts.to_json(),
    "gaps": self.gaps.to_json(),
    "annotations": self.annotations.to_json(),
    "time_tolerance": match self.time_tolerance {
      None => Json::null()
      Some(value) => value.to_json()
    },
  }
}

///|
pub impl ToJson for AnnotationReviewSource with fn to_json(self) -> Json {
  // The review's complete witnesses explicitly encode absence as null. This
  // does not alter Annotation::to_json or the existing annotations command.
  let annotations : Array[Json] = self.annotations.map(a => {
    "record": a.record.to_json(),
    "signal": a.signal.to_json(),
    "onset": a.onset.to_json(),
    "duration": match a.duration {
      None => Json::null()
      Some(value) => value.to_json()
    },
    "text": a.text.to_json(),
  })
  { "context": self.context.to_json(), "annotations": annotations.to_json() }
}

///|
pub impl ToJson for AnnotationReviewGroup with fn to_json(self) -> Json {
  {
    "onset": self.onset.to_json(),
    "duration": match self.duration {
      None => Json::null()
      Some(value) => value.to_json()
    },
    "text": self.text.to_json(),
    "left_indices": self.left_indices.to_json(),
    "right_indices": self.right_indices.to_json(),
    "left": self.left.to_json(),
    "right": self.right.to_json(),
    "retained": self.retained.to_json(),
    "removed": self.removed.to_json(),
    "added": self.added.to_json(),
  }
}

///|
// Structured canonical key: no delimiter collision, floating point or text
// normalization. Presence distinguishes absent duration from explicit zero.
priv struct AnnotationReviewKey {
  onset_n : String
  onset_d : String
  duration_present : Bool
  duration_n : String
  duration_d : String
  text : String
} derive(Eq, Hash)

///|
priv struct AnnotationReviewBucket {
  onset : Time
  duration : Time?
  text : String
  left_indices : Array[Int]
  right_indices : Array[Int]
}

///|
fn annotation_review_context(r : Recording) -> AnnotationReviewContext {
  let h = r.header
  {
    format: if h.format == Edf {
      "edf"
    } else {
      "bdf"
    },
    continuity: match h.continuity {
      Plain => "plain"
      Continuous => "continuous"
      Discontinuous => "discontinuous"
    },
    patient: h.patient,
    recording: h.recording,
    date: h.date,
    time: h.time,
    start: h.start,
    timezone: "unspecified_local_civil",
    records: r.records,
    declared_records: h.declared_records,
    duration: h.duration,
    signals: h.signals.copy(),
    starts: r.starts.copy(),
    gaps: r.gaps(),
    annotations: r.annotations.length(),
    time_tolerance: match r.time_policy {
      Strict => None
      Tolerance(text) => Some(text)
    },
  }
}

///|
/// Compare the complete annotation multisets in file-header-relative seconds.
/// Numeric spelling is normalized exactly; text and duration presence are not.
/// Every original annotation and occurrence index is retained as a witness.
/// Record/signal placement is provenance, not cross-edit event identity.
///
/// Different header zeros yield a complete qualified comparison. Their civil
/// second difference is diagnostic only: it is never added to event onsets.
/// Equal headers do not prove common acquisition, timezone or biological events.
pub fn compare_annotations(
  left : Recording,
  right : Recording,
) -> AnnotationReview raise EdfError {
  let sources = [left.annotation_info(), right.annotation_info()]
  let positions : Map[AnnotationReviewKey, Int] = Map([])
  let buckets : Array[AnnotationReviewBucket] = []
  for side in 0..<2 {
    for index, annotation in sources[side] {
      let onset = Time::parse(annotation.onset)
      let duration = match annotation.duration {
        None => None
        Some(value) => Some(Time::parse(value))
      }
      let (duration_present, duration_n, duration_d) = match duration {
        None => (false, "0", "1")
        Some(value) => (true, value.numerator, value.denominator)
      }
      let key : AnnotationReviewKey = {
        onset_n: onset.numerator,
        onset_d: onset.denominator,
        duration_present,
        duration_n,
        duration_d,
        text: annotation.text,
      }
      let group = match positions.get(key) {
        Some(group) => group
        None => {
          let group = buckets.length()
          positions[key] = group
          buckets.push({
            onset,
            duration,
            text: annotation.text,
            left_indices: [],
            right_indices: [],
          })
          group
        }
      }
      if side == 0 {
        buckets[group].left_indices.push(index)
      } else {
        buckets[group].right_indices.push(index)
      }
    }
  }
  let groups : Array[AnnotationReviewGroup] = []
  let mut retained_total = 0
  for bucket in buckets {
    let left = bucket.left_indices.length()
    let right = bucket.right_indices.length()
    let retained = if left < right { left } else { right }
    retained_total += retained
    groups.push({
      onset: bucket.onset,
      duration: bucket.duration,
      text: bucket.text,
      left_indices: bucket.left_indices,
      right_indices: bucket.right_indices,
      left,
      right,
      retained,
      removed: left - retained,
      added: right - retained,
    })
  }
  let delta = right.header.start.civil_seconds() -
    left.header.start.civil_seconds()
  let equal = delta == 0L
  {
    frame: "file_header_relative",
    status: if equal {
      "complete_relative_comparison"
    } else {
      "complete_relative_comparison_clock_context_mismatch"
    },
    header_zero_equal: equal,
    header_civil_delta_seconds: delta.to_string(),
    needs_clock_review: !equal,
    left: { context: annotation_review_context(left), annotations: sources[0], },
    right: {
      context: annotation_review_context(right),
      annotations: sources[1],
    },
    groups,
    totals: {
      left: sources[0].length(),
      right: sources[1].length(),
      retained: retained_total,
      removed: sources[0].length() - retained_total,
      added: sources[1].length() - retained_total,
      groups: groups.length(),
    },
  }
}
