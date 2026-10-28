"""Original rational edge fixtures; Python Fraction -> float is the oracle.

No MoonBit algorithm is copied. --check verifies the committed IEEE-754 bit
vectors and black-box inputs without rewriting files. MIT project fixtures.
"""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]


def cases():
    maximum = (2**53 - 1) * 2**971
    overflow_midpoint = maximum + 2**970
    definitions = [
        ("subnormal scaled from two large integers", 2**53 - 1, 2**1127),
        ("negative subnormal", -(2**53 - 1), 2**1127),
        ("finite upper range with intermediate exponent 1024", 2**1077, 2**54 - 1),
        ("negative upper range", -2**1077, 2**54 - 1),
        ("half subnormal tie to zero", 1, 2**1075),
        ("above half subnormal", 2**54 + 1, 2**1129),
        ("below half subnormal", 2**54 - 1, 2**1129),
        ("negative underflow retains sign", -1, 2**1076),
        ("minimum subnormal", 1, 2**1074),
        ("minimum normal", 1, 2**1022),
        ("maximum finite", maximum, 1),
        ("below overflow midpoint", overflow_midpoint - 1, 1),
        ("overflow midpoint", overflow_midpoint, 1),
        ("negative overflow", -overflow_midpoint, 1),
        ("normal tie to even lower", 2**53 + 1, 2**53),
        ("normal tie to even upper", 2**53 + 3, 2**53),
        ("recurring third", 1, 3),
        ("negative recurring third", -1, 3),
        ("decimal tenth", 1, 10),
        ("both integers exceed floating range", 10**400 + 1, 10**400 - 1),
        ("true positive overflow", 10**400, 1),
        ("true underflow", 1, 10**400),
        ("zero", 0, 1),
    ]
    result = []
    for name, numerator, denominator in definitions:
        value = Fraction(numerator, denominator)
        try:
            approximate = float(value)
        except OverflowError:
            approximate = math.inf if value > 0 else -math.inf
        bits = struct.unpack(">Q", struct.pack(">d", approximate))[0]
        result.append(dict(name=name, rational=f"{numerator}/{denominator}", bits=str(bits)))
    return result


def main():
    parser = argparse.ArgumentParser();parser.add_argument("--check",action="store_true");args=parser.parse_args()
    values=cases();fixture=ROOT/"examples/time-projection/IEEE754.json";test=ROOT/"time_projection_test.mbt"
    if args.check:
        assert json.loads(fixture.read_text())==values
        pairs=re.findall(r'"([-0-9/]+)"\s*,\s*"([0-9]+)"',test.read_text())
        assert pairs==[(v["rational"],v["bits"]) for v in values]
        print(f"Verified {len(values)} independent Fraction/IEEE754 vectors")
        return
    fixture.parent.mkdir(parents=True,exist_ok=True)
    fixture.write_text(json.dumps(values,indent=2),encoding="utf-8")
    source='///|\n// Independent vectors: tools/generate-time-projection.py --check\ntest "Time approximate view preserves range and nearest-even rounding" {\n  let cases : Array[(String, String)] = [\n'
    source+=''.join(f'    ("{v["rational"]}", "{v["bits"]}"),\n' for v in values)
    source+='  ]\n  let mut failures = 0\n  for i in 0..<cases.length() {\n    let (text, expected_bits) = cases[i]\n    let actual = @edf.Time::parse(text).to_double().reinterpret_as_uint64().to_string()\n    if actual != expected_bits {\n      println("projection case \\{i}: actual=\\{actual}, expected=\\{expected_bits}")\n      failures += 1\n    }\n  }\n  assert_eq(failures, 0)\n}\n'
    test.write_text(source,encoding="utf-8")
    print(f"Wrote {len(values)} independent boundary vectors")


if __name__=="__main__":
    main()
