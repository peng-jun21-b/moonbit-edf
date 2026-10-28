///|
/// Internal decimal seconds. Limits are allocation budgets, never a fixed tick.
priv struct DecimalSeconds {
  coefficient : @bigint.BigInt
  scale : Int
} derive(Debug)

///|
fn ten_power(n : Int) -> @bigint.BigInt {
  @bigint.BigInt::from_int(10).pow(@bigint.BigInt::from_int(n))
}

///|
fn DecimalSeconds::parse(
  text : String,
  onset : Bool,
) -> DecimalSeconds raise EdfError {
  if text.is_empty() {
    raise Invalid("empty TAL timestamp")
  }
  let first = if onset {
    if text[0] != '+' && text[0] != '-' {
      raise Invalid("TAL onset requires sign")
    }
    1
  } else {
    0
  }
  let mut dot = -1
  let digits = StringBuilder()
  for i in first..<text.length() {
    let c = text[i]
    if c == '.' {
      if dot >= 0 || i == first || i + 1 == text.length() {
        raise Invalid("malformed TAL decimal")
      }
      dot = i
    } else if c >= '0' && c <= '9' {
      digits.write_char(c.to_int().to_char().unwrap())
    } else {
      raise Invalid("TAL time must be a plain decimal")
    }
  }
  if digits.to_string().is_empty() {
    raise Invalid("empty TAL timestamp")
  }
  let value = @bigint.BigInt::from_string(digits.to_string())
  {
    coefficient: if first == 1 && text[0] == '-' {
      -value
    } else {
      value
    },
    scale: if dot < 0 {
      0
    } else {
      text.length() - dot - 1
    },
  }
}

///|
/// Header numbers and Double convenience arguments may use exponent notation.
fn DecimalSeconds::number(text : String) -> DecimalSeconds raise EdfError {
  let pieces = text.to_lower().split("e").to_array()
  if pieces.length() > 2 {
    raise Invalid("malformed decimal exponent")
  }
  let raw = pieces[0].to_owned()
  let mantissa = if raw.has_prefix(".") {
    "0" + raw
  } else if raw.has_prefix("+.") {
    "+0" + raw[1:].to_owned()
  } else if raw.has_prefix("-.") {
    "-0" + raw[1:].to_owned()
  } else {
    raw
  }
  let value = DecimalSeconds::parse(
    if mantissa.has_prefix("+") || mantissa.has_prefix("-") {
      mantissa
    } else {
      "+" + mantissa
    },
    true,
  )
  let exponent = if pieces.length() == 2 {
    integer(pieces[1].to_owned())
  } else {
    0
  }
  // Validate exponent syntax before the zero shortcut; zero does not require
  // constructing a power of ten, regardless of an otherwise valid exponent.
  if value.coefficient.is_zero() {
    return { coefficient: value.coefficient, scale: 0, }
  }
  let scale = value.scale.to_int64() - exponent.to_int64()
  // Decimal text needs a digit before the point, the point and an optional
  // sign. Check the Int-indexed representation before narrowing or allocating.
  if scale > 2147483644L {
    raise Limit("decimal scale exceeds runtime string address space")
  }
  if scale < 0L {
    let digits = value.coefficient.to_string()
    let count = digits.length() - (if digits.has_prefix("-") { 1 } else { 0 })
    if count.to_int64() - scale + 1L > 2147483647L {
      raise Limit("decimal coefficient exceeds runtime string address space")
    }
    { coefficient: value.coefficient * ten_power((-scale).to_int()), scale: 0, }
  } else {
    { ..value, scale: scale.to_int(), }
  }
}

///|
fn DecimalSeconds::units(self : DecimalSeconds, scale : Int) -> @bigint.BigInt {
  self.coefficient * ten_power(scale - self.scale)
}

///|
fn DecimalSeconds::compare(
  self : DecimalSeconds,
  other : DecimalSeconds,
) -> Int {
  let scale = self.scale.max(other.scale)
  self.units(scale).compare(other.units(scale))
}

///|
fn DecimalSeconds::add(
  self : DecimalSeconds,
  other : DecimalSeconds,
) -> DecimalSeconds {
  let scale = self.scale.max(other.scale)
  { coefficient: self.units(scale) + other.units(scale), scale, }
}

///|
fn DecimalSeconds::sub(
  self : DecimalSeconds,
  other : DecimalSeconds,
) -> DecimalSeconds {
  let scale = self.scale.max(other.scale)
  { coefficient: self.units(scale) - other.units(scale), scale, }
}

///|
fn DecimalSeconds::times(self : DecimalSeconds, n : Int) -> DecimalSeconds {
  { ..self, coefficient: self.coefficient * @bigint.BigInt::from_int(n), }
}

///|
fn DecimalSeconds::floor_seconds(self : DecimalSeconds) -> @bigint.BigInt {
  let denominator = ten_power(self.scale)
  let quotient = self.coefficient / denominator
  if self.coefficient.compare_int(0) < 0 &&
    !(self.coefficient % denominator).is_zero() {
    quotient - @bigint.BigInt::from_int(1)
  } else {
    quotient
  }
}

///|
fn DecimalSeconds::text(self : DecimalSeconds, signed : Bool) -> String {
  let raw = self.coefficient.to_string()
  let negative = raw.has_prefix("-")
  let digits = if negative { raw[1:].to_owned() } else { raw }
  let padded = if digits.length() <= self.scale {
    String::make(self.scale + 1 - digits.length(), '0') + digits
  } else {
    digits
  }
  let split = padded.length() - self.scale
  let mut end = padded.length()
  while end > split && padded[end - 1] == '0' {
    end -= 1
  }
  (if negative { "-" } else if signed { "+" } else { "" }) +
  padded[:split].to_owned() +
  (if end == split { "" } else { "." + padded[split:end].to_owned() })
}

///|
#alias(annotations_exact)
pub fn Recording::annotation_info(self : Recording) -> Array[Annotation] {
  self.annotations.copy()
}

///|
#alias(record_onset_exact)
pub fn Recording::record_onset(
  self : Recording,
  record : Int,
) -> String raise EdfError {
  if record < 0 || record >= self.records {
    raise Invalid("record index out of bounds")
  }
  self.exact_starts[record].text(true)
}
