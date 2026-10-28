/// Explicit promotion keeps the existing method API under MoonBit 0079.
/// Algorithms and data representation are unchanged; do not suppress the warning.

///|
pub extend SignalStatistics with @debug.Debug::{to_repr}

///|
pub extend Gap with @debug.Debug::{to_repr}

///|
pub extend FlatRun with @debug.Debug::{to_repr}

///|
pub extend DateTime with @debug.Debug::{to_repr}

///|
pub extend Format with @debug.Debug::{to_repr}

///|
pub extend Continuity with @debug.Debug::{to_repr}

///|
pub extend EdfError with @debug.Debug::{to_repr}

///|
pub extend Signal with @debug.Debug::{to_repr}

///|
pub extend Header with @debug.Debug::{to_repr}

///|
pub extend Tal with @debug.Debug::{to_repr}

///|
pub extend Annotation with @debug.Debug::{to_repr}

///|
pub extend Recording with @debug.Debug::{to_repr}

///|
pub extend Event with @debug.Debug::{to_repr}

///|
pub extend Record with @debug.Debug::{to_repr}

///|
pub extend Format with Eq::{equal, not_equal}

///|
pub extend Continuity with Eq::{equal, not_equal}

///|
pub extend SignalStatistics with ToJson::{to_json}

///|
pub extend Gap with ToJson::{to_json}

///|
pub extend FlatRun with ToJson::{to_json}

///|
pub extend DateTime with ToJson::{to_json}

///|
pub extend Format with ToJson::{to_json}

///|
pub extend Continuity with ToJson::{to_json}

///|
pub extend Signal with ToJson::{to_json}

///|
pub extend Tal with ToJson::{to_json}

///|
pub extend Annotation with ToJson::{to_json}

///|
pub extend Event with ToJson::{to_json}

///|
pub extend Event with @json.FromJson::{from_json}
