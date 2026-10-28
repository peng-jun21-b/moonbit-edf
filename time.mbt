///|
/// Exact rational seconds. JSON always uses decimal strings for both integers.
pub struct Time {
  numerator : String
  denominator : String
} derive(Debug, ToJson)

///|
pub extend Time with @debug.Debug::{to_repr}

///|
pub extend Time with ToJson::{to_json}

///|
fn time_ratio(n : @bigint.BigInt, d : @bigint.BigInt) -> Time raise EdfError {
  if d.compare_int(0) == 0 {
    raise Invalid("zero time denominator")
  }
  let n = if d.compare_int(0) < 0 { -n } else { n }
  let d = if d.compare_int(0) < 0 { -d } else { d }
  let mut a = if n.compare_int(0) < 0 { -n } else { n }
  let mut b = d
  while !b.is_zero() {
    let remainder = a % b
    a = b
    b = remainder
  }
  { numerator: (n / a).to_string(), denominator: (d / a).to_string(), }
}

///|
fn DecimalSeconds::as_time(self : DecimalSeconds) -> Time {
  // Decimal denominator is nonzero by construction.
  time_ratio(self.coefficient, ten_power(self.scale)) catch {
    _ => abort("decimal denominator")
  }
}

///|
pub fn Time::parse(text : String) -> Time raise EdfError {
  let fields = text.split("/").to_array()
  if fields.length() == 1 {
    return DecimalSeconds::number(text).as_time()
  }
  if fields.length() != 2 {
    raise Invalid("malformed rational seconds")
  }
  let n = DecimalSeconds::number(fields[0].to_owned())
  let d = DecimalSeconds::number(fields[1].to_owned())
  time_ratio(
    n.coefficient * ten_power(d.scale),
    d.coefficient * ten_power(n.scale),
  )
}

///|
fn compare_time(left : Time, right : Time) -> Int {
  (@bigint.BigInt::from_string(left.numerator) *
  @bigint.BigInt::from_string(right.denominator)).compare(
    @bigint.BigInt::from_string(right.numerator) *
    @bigint.BigInt::from_string(left.denominator),
  )
}

///|
pub impl Eq for Time with fn equal(self, other) {
  compare_time(self, other) == 0
}

///|
pub impl Compare for Time with fn compare(self, other) {
  compare_time(self, other)
}

///|
pub extend Time with Eq::{equal, not_equal}

///|
pub extend Time with Compare::{compare, op_lt, op_le, op_gt, op_ge}

///|
pub fn Time::add(self : Time, other : Time) -> Time {
  let a = @bigint.BigInt::from_string(self.numerator)
  let b = @bigint.BigInt::from_string(self.denominator)
  let c = @bigint.BigInt::from_string(other.numerator)
  let d = @bigint.BigInt::from_string(other.denominator)
  time_ratio(a * d + c * b, b * d) catch {
    _ => abort("positive rational denominators")
  }
}

///|
pub fn Time::sub(self : Time, other : Time) -> Time {
  self.add({
    ..other,
    numerator: (-@bigint.BigInt::from_string(other.numerator)).to_string(),
  })
}

///|
pub fn Time::scale(
  self : Time,
  numerator : Int,
  denominator? : Int = 1,
) -> Time raise EdfError {
  time_ratio(
    @bigint.BigInt::from_string(self.numerator) *
    @bigint.BigInt::from_int(numerator),
    @bigint.BigInt::from_string(self.denominator) *
    @bigint.BigInt::from_int(denominator),
  )
}

///|
/// Finite decimal when possible; an irreducible recurring time is n/d.
pub fn Time::text(self : Time) -> String {
  let denominator = @bigint.BigInt::from_string(self.denominator)
  let mut remaining = denominator
  let two = @bigint.BigInt::from_int(2)
  let five = @bigint.BigInt::from_int(5)
  let mut twos = 0
  let mut fives = 0
  while (remaining % two).is_zero() {
    remaining = remaining / two
    twos += 1
  }
  while (remaining % five).is_zero() {
    remaining = remaining / five
    fives += 1
  }
  if remaining.compare_int(1) != 0 {
    return self.numerator + "/" + self.denominator
  }
  let scale = twos.max(fives)
  let value : DecimalSeconds = {
    coefficient: @bigint.BigInt::from_string(self.numerator) *
    (ten_power(scale) / denominator),
    scale,
  }
  value.text(false)
}

///|
/// Explicit approximate view for plots, never used for time decisions or IO.
/// Rounds the exact ratio to nearest binary64, with ties to even.
pub fn Time::to_double(self : Time) -> Double {
  let n = @bigint.BigInt::from_string(self.numerator)
  let d = @bigint.BigInt::from_string(self.denominator)
  if n.is_zero() {
    return 0.0
  }
  let absolute = if n.compare_int(0) < 0 { -n } else { n }
  // Determine the actual binary exponent before rounding. Scaling a rounded
  // leading-word ratio by pow(2, exponent) can overflow/underflow prematurely.
  let mut exponent = absolute.bit_length() - d.bit_length()
  if (if exponent >= 0 {
      absolute.compare(d << exponent) < 0
    } else {
      (absolute << -exponent).compare(d) < 0
    }) {
    exponent -= 1
  }
  if exponent > 1023 {
    let infinity = @math.scalbn(1.0, 1024)
    return if n.compare_int(0) < 0 { -infinity } else { infinity }
  }
  if exponent < -1075 {
    return if n.compare_int(0) < 0 { -0.0 } else { 0.0 }
  }
  // Round the exact quotient to 53 significant bits, or to the fixed
  // subnormal quantum. Halfway cases choose an even significand.
  let quantum = (exponent - 52).max(-1074)
  let numerator = if quantum < 0 { absolute << -quantum } else { absolute }
  let denominator = if quantum > 0 { d << quantum } else { d }
  let mut quotient = numerator / denominator
  let twice_remainder = (numerator % denominator) << 1
  let halfway = twice_remainder.compare(denominator)
  if halfway > 0 ||
    (halfway == 0 && !(quotient % @bigint.BigInt::from_int(2)).is_zero()) {
    quotient = quotient + @bigint.BigInt::from_int(1)
  }
  let value = @math.scalbn(quotient.to_uint64().to_double(), quantum)
  if n.compare_int(0) < 0 {
    -value
  } else {
    value
  }
}

///|
pub trait TimeInput {
  fn to_time_text(Self) -> String raise EdfError
}

///|
pub impl TimeInput for String with fn to_time_text(self) {
  self
}

///|
pub impl TimeInput for Double with fn to_time_text(self) {
  if !finite(self) {
    raise Invalid("non-finite time input")
  }
  self.to_string()
}

///|
pub impl TimeInput for Time with fn to_time_text(self) {
  self.text()
}

///|
pub extend Time with TimeInput::{to_time_text}

///|
pub(all) enum TimePolicy {
  Strict
  Tolerance(String)
} derive(Debug)

///|
pub extend TimePolicy with @debug.Debug::{to_repr}
