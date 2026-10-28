///|
pub(all) struct DateTime {
  year : Int
  month : Int
  day : Int
  hour : Int
  minute : Int
  second : Int
} derive(Debug, ToJson)

///|
fn month_days(year : Int, month : Int) -> Int {
  if month == 2 {
    if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) {
      29
    } else {
      28
    }
  } else if month == 4 || month == 6 || month == 9 || month == 11 {
    30
  } else {
    31
  }
}

///|
fn DateTime::validate(self : DateTime) -> Unit raise EdfError {
  if self.year < 1985 ||
    self.year > 9999 ||
    self.month < 1 ||
    self.month > 12 ||
    self.day < 1 ||
    self.day > month_days(self.year, self.month) ||
    self.hour < 0 ||
    self.hour > 23 ||
    self.minute < 0 ||
    self.minute > 59 ||
    self.second < 0 ||
    self.second > 59 {
    raise Invalid("date/time outside supported Gregorian EDF date range")
  }
}

///|
fn two(n : Int) -> String {
  if n < 10 {
    "0" + n.to_string()
  } else {
    n.to_string()
  }
}

///|
pub fn DateTime::date_field(self : DateTime) -> String raise EdfError {
  self.validate()
  "\{two(self.day)}.\{two(self.month)}." +
  (if self.year > 2084 { "yy" } else { two(self.year % 100) })
}

///|
pub fn DateTime::time_field(self : DateTime) -> String raise EdfError {
  self.validate()
  "\{two(self.hour)}.\{two(self.minute)}.\{two(self.second)}"
}

///|
fn DateTime::long_date(self : DateTime) -> String {
  let months = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
    "DEC",
  ]
  "\{two(self.day)}-\{months[self.month-1]}-\{self.year}"
}

///|
fn DateTime::update_recording_id(
  self : DateTime,
  identity : String,
) -> String raise EdfError {
  let fields = identity
    .split(" ")
    .filter(x => !x.is_empty())
    .map(x => x.to_owned())
    .to_array()
  if fields.length() < 5 || fields[0] != "Startdate" {
    raise Invalid("cannot update malformed plus recording identification")
  }
  let unknown = fields[1] == "X"
  fields[1] = self.long_date()
  let rewritten = fields.join(" ")
  // EDF+ allows an unknown recording date. Keep its tail within the existing
  // field when the ordinary date header can still supply the complete year.
  // After 2084 the literal yy header needs the full date; let the writer report
  // a real width error if the updated identity cannot be represented.
  if unknown && self.year <= 2084 && rewritten.length() > 80 {
    fields[1] = "X"
    fields.join(" ")
  } else {
    rewritten
  }
}

///|
pub fn parse_datetime(date : String, time : String) -> DateTime raise EdfError {
  if (date.length() != 8 && date.length() != 10) ||
    time.length() != 8 ||
    date[2] != '.' ||
    date[5] != '.' ||
    time[2] != '.' ||
    time[5] != '.' {
    raise Invalid("date/time must be dd.mm.yy and hh.mm.ss")
  }
  let yy = integer(date[6:].to_owned())
  let dt : DateTime = {
    year: if date.length() == 10 {
      yy
    } else if yy >= 85 {
      1900 + yy
    } else {
      2000 + yy
    },
    month: integer(date[3:5].to_owned()),
    day: integer(date[0:2].to_owned()),
    hour: integer(time[0:2].to_owned()),
    minute: integer(time[3:5].to_owned()),
    second: integer(time[6:8].to_owned()),
  }
  dt.validate()
  dt
}

///|
pub fn DateTime::advance(
  self : DateTime,
  seconds : Int,
) -> DateTime raise EdfError {
  self.advance_seconds(seconds.to_string())
}

///|
pub fn DateTime::advance_seconds(
  self : DateTime,
  seconds : String,
) -> DateTime raise EdfError {
  self.validate()
  let seconds = DecimalSeconds::number(seconds)
  if seconds.compare(
      DecimalSeconds::number(seconds.floor_seconds().to_string()),
    ) !=
    0 {
    raise Invalid("calendar shift requires whole seconds")
  }
  let total = seconds.coefficient / ten_power(seconds.scale) +
    @bigint.BigInt::from_int(self.hour * 3600 + self.minute * 60 + self.second)
  let day = @bigint.BigInt::from_int(86400)
  let mut delta = total / day
  let mut remainder = total % day
  if remainder.compare_int(0) < 0 {
    delta = delta - @bigint.BigInt::from_int(1)
    remainder = remainder + day
  }
  if delta.compare_int(-3652059) < 0 || delta.compare_int(3652059) > 0 {
    raise Invalid(
      "EDF four-digit start date cannot represent this calendar shift",
    )
  }
  let mut days = delta.to_int()
  let rest = remainder.to_int()
  let mut y = self.year
  let mut m = self.month
  let mut d = self.day
  while days > 0 {
    let left = month_days(y, m) - d
    if days <= left {
      d += days
      days = 0
    } else {
      days -= left + 1
      d = 1
      m += 1
      if m == 13 {
        m = 1
        y += 1
      }
    }
    if y > 9999 {
      raise Invalid("EDF four-digit start year overflow")
    }
  }
  while days < 0 {
    if -days < d {
      d += days
      days = 0
    } else {
      days += d
      m -= 1
      if m == 0 {
        m = 12
        y -= 1
      }
      if y < 1985 {
        raise Invalid("EDF start year precedes 1985")
      }
      d = month_days(y, m)
    }
  }
  let value : DateTime = {
    year: y,
    month: m,
    day: d,
    hour: rest / 3600,
    minute: rest % 3600 / 60,
    second: rest % 60,
  }
  value.validate()
  value
}

///|
fn parse_recording_datetime(
  date : String,
  time : String,
  recording : String,
  continuity : Continuity,
) -> DateTime raise EdfError {
  if date.length() != 8 || !date.has_suffix("yy") {
    return parse_datetime(date, time)
  }
  if continuity == Plain {
    raise Invalid("post-2084 yy date requires EDF+ Startdate")
  }
  let tokens = recording
    .split(" ")
    .filter(s => !s.is_empty())
    .map(s => s.to_owned())
    .collect()
  if tokens.length() < 2 || tokens[0] != "Startdate" {
    raise Invalid("missing full recording start date")
  }
  let full = tokens[1].split("-").map(s => s.to_owned()).to_array()
  if full.length() != 3 || full[0].length() != 2 || full[2].length() != 4 {
    raise Invalid("invalid full recording start date")
  }
  let months = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
    "DEC",
  ]
  let mut month = 0
  for i in 0..<12 {
    if months[i] == full[1] {
      month = i + 1
    }
  }
  let year = integer(full[2])
  if month == 0 ||
    year <= 2084 ||
    integer(date[:2].to_owned()) != integer(full[0]) ||
    integer(date[3:5].to_owned()) != month {
    raise Invalid("header and full start date disagree")
  }
  parse_datetime(full[0] + "." + two(month) + "." + full[2], time)
}
