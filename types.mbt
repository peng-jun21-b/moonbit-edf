///|
pub(all) enum Format {
  Edf
  Bdf
} derive(Eq, Debug, ToJson)

///|
pub(all) enum Continuity {
  Plain
  Continuous
  Discontinuous
} derive(Eq, Debug, ToJson)

///|
pub suberror EdfError {
  Invalid(String)
  Unsupported(String)
  Limit(String)
} derive(Debug)

///|
pub(all) struct Signal {
  label : String
  transducer : String
  unit : String
  physical_min : Double
  physical_max : Double
  digital_min : Int
  digital_max : Int
  prefilter : String
  samples_per_record : Int
  reserved : String
} derive(Debug, ToJson)

///|
pub struct Header {
  format : Format
  continuity : Continuity
  patient : String
  recording : String
  date : String
  time : String
  start : DateTime
  reserved : String
  declared_records : Int
  duration : String
  signals : Array[Signal]
  bytes : Int
  record_bytes : Int
  offsets : Array[Int]
} derive(Debug)

///|
pub(all) struct Tal {
  onset : String
  duration : String?
  texts : Array[String]
} derive(Debug, ToJson)

///|
pub(all) struct Annotation {
  record : Int
  signal : Int
  onset : String
  duration : String?
  text : String
} derive(Debug, ToJson, FromJson)

///|
pub struct Recording {
  header : Header
  data : Bytes
  records : Int
  starts : Array[String]
  annotations : Array[Annotation]
  priv time_policy : TimePolicy
  priv exact_starts : Array[DecimalSeconds]
  priv exact_duration : DecimalSeconds
} derive(Debug)

///|
pub(all) struct Event[T] {
  onset : T
  duration : T?
  text : String
} derive(Debug, ToJson, FromJson)

///|
/// samples contains ordinary channels only, in the order supplied to create.
pub(all) struct Record[T] {
  onset : T
  samples : Array[Array[Int]]
  events : Array[Event[T]]
} derive(Debug)

///|
pub fn Format::width(self : Format) -> Int {
  if self == Edf {
    2
  } else {
    3
  }
}

///|
pub fn Signal::is_annotation(self : Signal) -> Bool {
  self.label == "EDF Annotations" || self.label == "BDF Annotations"
}

///|
fn finite(x : Double) -> Bool {
  !x.is_nan() && !x.is_inf()
}

///|
fn need(b : Bytes, p : Int, n : Int) -> Unit raise EdfError {
  if p < 0 || n < 0 || p > b.length() || n > b.length() - p {
    raise Invalid("truncated input at \{p}")
  }
}

///|
fn part(b : Bytes, p : Int, n : Int) -> Bytes {
  Bytes::makei(n, i => b[p + i])
}

///|
fn text_field(b : Bytes, p : Int, n : Int) -> String raise EdfError {
  need(b, p, n)
  let out = []
  for i = 0; i < n; i = i + 1 {
    let v = b[p + i].to_int()
    if v < 32 || v > 126 {
      raise Invalid("nonprintable ASCII in header at \{p+i}")
    }
    out.push(v.to_char().unwrap())
  }
  String::from_iter(out.iter()).trim().to_owned()
}

///|
fn integer(s : String) -> Int raise EdfError {
  if s.is_empty() {
    raise Invalid("empty integer field")
  }
  for i = 0; i < s.length(); i = i + 1 {
    let c = s[i]
    if (c < '0' || c > '9') && !(i == 0 && (c == '-' || c == '+')) {
      raise Invalid("invalid decimal integer")
    }
  }
  @string.parse_int(s, base=10) catch {
    _ => raise Invalid("integer field out of range")
  }
}

///|
fn number(s : String) -> Double raise EdfError {
  if s.is_empty() {
    raise Invalid("empty numeric field")
  }
  for c in s.iter() {
    if !(c >= '0' && c <= '9') &&
      c != '+' &&
      c != '-' &&
      c != '.' &&
      c != 'e' &&
      c != 'E' {
      raise Invalid("invalid decimal number")
    }
  }
  let v = @string.parse_double(s) catch {
    _ => raise Invalid("malformed decimal number")
  }
  if !finite(v) {
    raise Invalid("nonfinite numeric field")
  }
  v
}

///|
fn put_text(
  out : Array[Byte],
  p : Int,
  n : Int,
  s : String,
) -> Unit raise EdfError {
  if s.length() > n {
    raise Invalid("header text exceeds field width \{n}: \{s}")
  }
  for i = 0; i < n; i = i + 1 {
    out[p + i] = b' '
  }
  for i = 0; i < s.length(); i = i + 1 {
    let v = s[i].to_int()
    if v < 32 || v > 126 {
      raise Invalid("header text must be printable ASCII")
    }
    out[p + i] = v.to_byte()
  }
}

///|
fn copy_bytes(
  out : Array[Byte],
  p : Int,
  b : Bytes,
  start : Int,
  n : Int,
) -> Unit {
  for i = 0; i < n; i = i + 1 {
    out[p + i] = b[start + i]
  }
}

///|
fn read_sample(b : Bytes, p : Int, w : Int) -> Int raise EdfError {
  need(b, p, w)
  let mut v = 0
  for i = 0; i < w; i = i + 1 {
    v = v | (b[p + i].to_int() << (8 * i))
  }
  let shift = 32 - w * 8
  v << shift >> shift
}

///|
fn put_sample(out : Array[Byte], p : Int, w : Int, v : Int) -> Unit {
  for i = 0; i < w; i = i + 1 {
    out[p + i] = (v >> (8 * i)).to_byte()
  }
}

///|
pub extend Annotation with @json.FromJson::{from_json}
