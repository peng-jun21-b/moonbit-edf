///|
/// Parse signed onset or unsigned duration, forbidding exponents/control syntax.
fn tal_number(text : String, onset : Bool) -> DecimalSeconds raise EdfError {
  DecimalSeconds::parse(text, onset)
}

///|
/// Preserve decimal spelling and grouped annotation texts.
pub fn parse_tals(data : Bytes) -> Array[Tal] raise EdfError {
  let result = []
  let mut at = 0
  while at < data.length() && data[at] != b'\x00' {
    let start = at
    while at < data.length() &&
          data[at] != b'\x14' &&
          data[at] != b'\x15' &&
          data[at] != b'\x00' {
      at += 1
    }
    if at == data.length() || data[at] == b'\x00' {
      raise Invalid("TAL missing annotation separator")
    }
    let onset = text_field(data, start, at - start)
    if onset.length() != at - start {
      raise Invalid("spaces are forbidden in TAL onset")
    }
    ignore(tal_number(onset, true))
    let duration = if data[at] == b'\x15' {
      at += 1
      let start = at
      while at < data.length() && data[at] != b'\x14' && data[at] != b'\x00' {
        at += 1
      }
      if at == data.length() || data[at] != b'\x14' {
        raise Invalid("TAL duration missing separator")
      }
      let duration = text_field(data, start, at - start)
      if duration.length() != at - start {
        raise Invalid("spaces are forbidden in TAL duration")
      }
      ignore(tal_number(duration, false))
      Some(duration)
    } else {
      None
    }
    at += 1
    let texts = []
    while true {
      let start = at
      while at < data.length() && data[at] != b'\x14' && data[at] != b'\x00' {
        let b = data[at].to_int()
        if b < 32 && b != 9 && b != 10 && b != 13 {
          raise Invalid("forbidden TAL control character")
        }
        at += 1
      }
      if at == data.length() || data[at] != b'\x14' {
        raise Invalid("TAL text requires final separator")
      }
      let text = @utf8.decode(data[start:at], ignore_bom=false) catch {
        _ => raise Invalid("malformed UTF-8 annotation")
      }
      texts.push(text)
      at += 1
      if at >= data.length() {
        raise Invalid("TAL missing zero terminator")
      }
      if data[at] == b'\x00' {
        at += 1
        break
      }
    }
    result.push({ onset, duration, texts, })
  }
  while at < data.length() {
    if data[at] != b'\x00' {
      raise Invalid("nonzero bytes after TAL padding")
    }
    at += 1
  }
  result
}

///|
pub fn encode_tals(tals : Array[Tal], capacity : Int) -> Bytes raise EdfError {
  if capacity < 0 {
    raise Invalid("negative TAL capacity")
  }
  let out = Array::make(capacity, b'\x00')
  let mut at = 0
  for tal in tals {
    ignore(tal_number(tal.onset, true))
    let duration = match tal.duration {
      Some(d) => {
        ignore(tal_number(d, false))
        "\u0015" + d
      }
      None => ""
    }
    if tal.texts.is_empty() {
      raise Invalid("TAL must contain at least one text, possibly empty")
    }
    for text in tal.texts {
      for c in text.iter() {
        if c.to_int() < 32 && c != '\t' && c != '\n' && c != '\r' {
          raise Invalid("forbidden TAL control character")
        }
      }
    }
    let b = @utf8.encode(
      tal.onset +
      duration +
      "\u0014" +
      tal.texts.join("\u0014") +
      "\u0014\u0000",
    )
    if b.length() > capacity - at {
      raise Limit("annotations do not fit record capacity")
    }
    copy_bytes(out, at, b, 0, b.length())
    at += b.length()
  }
  Bytes::from_array(out)
}
