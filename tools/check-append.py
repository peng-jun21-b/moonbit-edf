"""Independent fixed-width/Fraction oracle for the real append CLI (MIT).

No MoonBit writer generates reference inputs. Raw inputs and command receipts
are retained beside --output. Optional --reference-c also reads two supported
continuous outputs with the development PyEDFlib dependency.
"""
import argparse
from datetime import datetime
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
field = runpy.run_path(str(ROOT / "tools/check-crop-repair.py"))["field"]
fixture = runpy.run_path(str(ROOT / "tools/check-crop-repair.py"))["fixture"]
COLUMNS = [(0, 16), (16, 80), (96, 8), (104, 8), (112, 8),
           (120, 8), (128, 8), (136, 80), (216, 8), (224, 32)]


def read_raw(path):
    data = path.read_bytes()
    width = 3 if data[:8] == b"\xffBIOSEMI" else 2
    ns, nr, hs = int(data[252:256]), int(data[236:244]), int(data[184:192])
    columns = [[data[256 + ns * c + s * w:256 + ns * c + (s + 1) * w]
                for s in range(ns)] for c, w in COLUMNS]
    per = [int(v) for v in columns[8]]
    ann = [s for s in range(ns) if columns[0][s].strip().endswith(b"Annotations")]
    ordinary = [s for s in range(ns) if s not in ann]
    rs = sum(per) * width
    assert hs == 256 * (ns + 1) and len(data) == hs + nr * rs
    duration = F(data[244:252].decode().strip())
    blocks, starts, events, points = [], [], [], {s: [] for s in ordinary}
    for r in range(nr):
        row, at = [], hs + r * rs
        for count in per:
            row.append(data[at:at + count * width]); at += count * width
        blocks.append(row)
        start = F(r) * duration
        for s in ann:
            for i, tal in enumerate(t for t in row[s].split(b"\0") if t):
                terms = tal.split(b"\x14")
                clock = terms[0].split(b"\x15")
                onset = F(clock[0].decode())
                span = clock[1].decode() if len(clock) == 2 else None
                if s == ann[0] and i == 0:
                    assert terms[1] == b"" and span is None
                    start = onset
                events += [(r, s, onset, span, text.decode("utf-8"))
                           for text in terms[1:] if text]
        starts.append(start)
        for s in ordinary:
            for j in range(per[s]):
                value = int.from_bytes(row[s][j * width:(j + 1) * width], "little", signed=True)
                points[s].append((r, j, value, start + duration * F(j, per[s])))
    dd, mm, yy = data[168:176].decode().split(".")
    if yy == "yy":
        year = int(data[88:168].decode().split()[1].split("-")[2])
    else:
        year = int(yy) + (1900 if int(yy) >= 85 else 2000)
    clock = datetime(year, int(mm), int(dd), *map(int, data[176:184].decode().split(".")))
    return dict(data=data, width=width, ns=ns, nr=nr, hs=hs, per=per, columns=columns,
                ann=ann, ordinary=ordinary, duration=duration, blocks=blocks,
                starts=starts, events=events, points=points, clock=clock)


def change(path, column, index, value, size=8):
    data = bytearray(path.read_bytes()); ns = int(data[252:256])
    at = 256 + ns * column + index * size
    data[at:at + size] = field(value, size); path.write_bytes(data)


def resize_annotations(path, count):
    raw = read_raw(path); data = bytearray(raw["data"][:raw["hs"]])
    for s in raw["ann"]:
        at = 256 + raw["ns"] * 216 + s * 8
        data[at:at + 8] = field(count, 8)
    for row in raw["blocks"]:
        for s, block in enumerate(row):
            if s in raw["ann"]:
                capacity = count * raw["width"]
                assert not block[capacity:].strip(b"\0")
                block = block[:capacity].ljust(capacity, b"\0")
            data.extend(block)
    path.write_bytes(data)


def make(path, fmt, per, starts, *, duration="1", mode="C", clock=None, events=None):
    fixture(path, fmt, per, starts, duration=duration, mode=mode, events=events)
    dt = clock or datetime(2020, 1, 1)
    data = bytearray(path.read_bytes())
    data[88:168] = field("Startdate " + dt.strftime("%d-%b-%Y").upper() + " X X X", 80)
    data[168:176] = field(f"{dt.day:02}.{dt.month:02}." + (f"{dt.year % 100:02}" if dt.year <= 2084 else "yy"), 8)
    data[176:184] = field(dt.strftime("%H.%M.%S"), 8)
    data[192:236] = field((fmt.upper() + "+" + mode if mode != "plain" else "raw") + " first-reserved", 44)
    path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-c", action="store_true")
    parser.add_argument("--resume", type=Path, help="Reuse verified, unaffected products from a previous partial receipt")
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    rows, products, reference = [], [], []
    reused = []
    if args.resume:
        previous = json.loads(args.resume.read_text(encoding="utf-8"))
        products, reference = previous["products"], previous["referenceC"]
        reused = [v["name"] for v in products]
        rows = [v for v in previous["commands"] if v["name"] in reused or v["name"].removesuffix("-window") in reused]
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            python=platform.python_version(), oracle="Original fixed-width bytes, Python Gregorian datetime, Fraction sample enumeration",
            commands=rows, products=products, referenceC=reference, reusedProducts=reused,
            resumedFrom=str(args.resume) if args.resume else None), indent=2), encoding="utf-8")
    def run(name, command):
        result = subprocess.run(["node", str(ROOT / "tools/edf.mjs"), *map(str, command)], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=["node", str(ROOT / "tools/edf.mjs"), *map(str, command)],
                   exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); save()
        (work / (name + ".stdout")).write_bytes(result.stdout)
        (work / (name + ".stderr")).write_bytes(result.stderr)
        return row
    def pair(name, fmt, per, starts_a, starts_b, **kwargs):
        a, b = work / (name + "-a." + fmt), work / (name + "-b." + fmt)
        for path, starts in [(a, starts_a), (b, starts_b)]:
            make(path, fmt, per, starts, **kwargs)
        return a, b
    def verify(name, a, b, offset=None, *, raw_offset=False, c_reader=False):
        if name in reused:
            return Path(next(v["output"] for v in products if v["name"] == name))
        left, right = read_raw(a), read_raw(b)
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in [a, b]]
        delta = right["clock"] - left["clock"]
        shift = F(offset) if offset is not None else F(delta.days * 86400 + delta.seconds)
        options = work / (name + ".json")
        options.write_text("{}" if offset is None else ('{"offset":' + offset + '}' if raw_offset else json.dumps(dict(offset=offset))))
        out = work / (name + "." + ("edf" if left["width"] == 2 else "bdf"))
        row = run(name, ["append", a, b, out, options]); assert row["exitCode"] == 0, row
        got = read_raw(out)
        expected_starts = left["starts"] + [t + shift for t in right["starts"]]
        assert got["starts"] == expected_starts and got["duration"] == left["duration"]
        assert got["nr"] == left["nr"] + right["nr"]
        assert got["clock"] == left["clock"]
        mode = b"D" if (left["duration"] == 0 and left["ordinary"]) or any(
            x != y + left["duration"] for y, x in zip(expected_starts, expected_starts[1:])) else b"C"
        assert got["data"][196:197] == mode
        assert got["data"][197:236] == left["data"][197:236] if left["ann"] else True
        if left["ann"]:
            assert got["data"][8:184] == left["data"][8:184]
        samples = 0
        for s in left["ordinary"]:
            expected = left["points"][s] + [(r + left["nr"], j, v, t + shift) for r, j, v, t in right["points"][s]]
            assert got["points"][s] == expected
            samples += len(expected)
            for r, source in enumerate(left["blocks"] + right["blocks"]):
                assert got["blocks"][r][s] == source[s]
            for column in range(10):
                assert got["columns"][column][s] == left["columns"][column][s]
        expected_events = left["events"] + [(r + left["nr"], s, t + shift, d, text) for r, s, t, d, text in right["events"]]
        if left["ann"] and right["ann"]:
            assert got["events"] == expected_events, (got["events"], expected_events)
        else:
            assert sum(t[4].startswith("Original patient ID:") for t in got["events"]) == 2
            assert sum(t[4].startswith("Original recording ID:") for t in got["events"]) == 2
        if left["ordinary"]:
            s = left["ordinary"][0]
            query = work / (name + "-window.json")
            query.write_text(json.dumps(dict(signal=s, start="0", end=str(expected_starts[-1] + left["duration"] + 1))))
            result = run(name + "-window", ["window", out, query]); assert result["exitCode"] == 0, result
            value = json.loads(result["stdout"])
            actual = [(v["record"], v["sample"], v["digital"], F(int(v["time_numerator"]), int(v["time_denominator"]))) for v in value["samples"]]
            assert actual == got["points"][s]
            expected_gaps = [(r, t + left["duration"], expected_starts[r + 1]) for r, t in enumerate(expected_starts[:-1]) if t + left["duration"] < expected_starts[r + 1]]
            assert [(g["after_record"], F(g["start"]), F(g["end"])) for g in value["gaps"]] == expected_gaps
        assert hashes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in [a, b]]
        product = dict(name=name, sourceHashes=hashes, output=str(out), sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                       records=got["nr"], samples=samples, events=len(got["events"]), offset=str(shift), mode=mode.decode())
        products.append(product); save(); print("verified", name, flush=True)
        if c_reader and args.reference_c:
            import pyedflib
            with pyedflib.EdfReader(str(out)) as reader:
                assert reader.signals_in_file == len(got["ordinary"])
                for index, s in enumerate(got["ordinary"]):
                    assert list(reader.readSignal(index, digital=True)) == [v[2] for v in got["points"][s]]
                assert reader.getStartdatetime() == left["clock"]
                reference.append(dict(name=name, reader="PyEDFlib", version=pyedflib.__version__, samples=samples, digitalExact=True))
            save()
        return out

    for fmt in ["edf", "bdf"]:
        for label, a_starts, b_starts, gap in [("continuous", ["+0", "+1"], ["+0", "+1"], False),
                                            ("gaps", ["+0.25", "+2.25"], ["+0.25", "+3.25"], True)]:
            name = label + "-" + fmt
            a, b = pair(name, fmt, [4, 2], a_starts, b_starts, mode="D" if gap else "C")
            make(b, fmt, [4, 2], b_starts, mode="D" if gap else "C", clock=datetime(2020, 1, 1, 0, 0, 5 if gap else 2),
                 events={(0, 1): [("-0.125", "0.000000000000000000003", "resumed α")], (1, 0): [(b_starts[1], None, "late")]})
            resize_annotations(b, 96)
            verify(name, a, b, c_reader=not gap)
        a, b = pair("zero-" + fmt, fmt, [1, 1], ["+0", "+1"], ["+0.25", "+2.25"], duration="0", mode="D")
        verify("zero-" + fmt, a, b, "2")
        a, b = pair("plain-" + fmt, fmt, [4, 2], ["+0", "+1"], ["+0", "+1"], mode="plain")
        verify("plain-" + fmt, a, b, "2")
        name = "annotations-" + fmt
        a, b = work / (name + "-a." + fmt), work / (name + "-b." + fmt)
        make(a, fmt, [], ["+0", "+1"], duration="0", mode="D", events={(0, 0): [("+0", None, "left")], (1, 0): [("+1", None, "left2")]})
        make(b, fmt, [], ["+0.25"], duration="0", mode="D", events={(0, 0): [("+0.25", None, "right")], (0, 1): [("-0.125", None, "secondary")]})
        verify(name, a, b, "2")
    a, b = pair("precise", "edf", [3, 1], ["+0.25"], ["+0.25"])
    for path in [a, b]:
        change(path, 104, 0, "12345e-9"); change(path, 112, 0, "54321e-9")
    change(b, 104, 0, "12345E-9")
    data = bytearray(b.read_bytes()); data[244:252] = field("10e-1", 8); b.write_bytes(data)
    verify("precise", a, b, "1.000000000000000000001", raw_offset=True)
    a, b = pair("growth", "edf", [1], ["+0"], ["+0"])
    make(b, "edf", [1], ["+0"], events={(0, 0): [("+0", None, "r")]})
    for path in [a, b]: resize_annotations(path, 8)
    out = verify("growth", a, b, "1000000000000000000.0001")
    assert read_raw(out)["per"][1] > 8
    a, b = pair("future", "bdf", [2], ["+0.25"], ["+0.25"])
    make(b, "bdf", [2], ["+0.25"], clock=datetime(2100, 1, 1))
    verify("future", a, b)
    a, b = pair("leap", "edf", [2], ["+0"], ["+0"], clock=datetime(2100, 2, 28, 23, 59, 59))
    make(b, "edf", [2], ["+0"], clock=datetime(2100, 3, 1))
    verify("leap", a, b)

    def reject(name, a, b, *, offset="1", tolerance=None, error="Invalid("):
        out = work / ("rejected-" + name + ".edf"); options = work / ("rejected-" + name + ".json")
        value = dict(offset=offset)
        if tolerance is not None: value["time_tolerance"] = tolerance
        options.write_text(json.dumps(value)); hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in [a, b]]
        row = run("reject-" + name, ["append", a, b, out, options])
        assert row["exitCode"] == 2 and error in row["stderr"] and not out.exists(), row
        assert hashes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in [a, b]]
    for name in ["label", "unit", "rate", "calibration", "underflow-calibration", "patient", "layout", "duration", "format", "empty", "overlap", "tolerated-overlap", "bad-offset", "limit-offset", "record-limit"]:
        per = [30464] if name == "record-limit" else [4]
        a, b = pair("error-" + name, "edf", per, ["+0"], ["+0"])
        if name == "label": change(b, 0, 0, "other", 16)
        elif name == "unit": change(b, 96, 0, "mV")
        elif name == "rate": make(b, "edf", [2], ["+0"])
        elif name == "calibration": change(b, 104, 0, "-101")
        elif name == "underflow-calibration":
            change(a, 104, 0, "1e-324"); change(b, 104, 0, "2e-324")
        elif name == "patient":
            data = bytearray(b.read_bytes()); data[8:88] = field("other X X X", 80); b.write_bytes(data)
        elif name == "layout": make(b, "edf", [4, 1], ["+0"])
        elif name == "duration": make(b, "edf", [4], ["+0"], duration="2")
        elif name == "format": make(b, "bdf", [4], ["+0"])
        elif name == "empty": make(b, "edf", [4], [])
        elif name == "tolerated-overlap": make(a, "edf", [4], ["+0", "+0.999999999999999999999"], mode="D")
        offset = "0.999999999999999999999" if name == "overlap" else "1/3" if name == "bad-offset" else "1e-2147483648" if name == "limit-offset" else "1e300" if name == "record-limit" else "3" if name == "tolerated-overlap" else "1"
        reject(name, a, b, offset=offset, tolerance="0.0001" if name == "tolerated-overlap" else None, error="Limit(" if name == "limit-offset" else "Invalid(")
    existing = Path(products[0]["output"]); previous = existing.read_bytes()
    row = run("reject-existing", ["append", work / "continuous-edf-a.edf", work / "continuous-edf-b.edf", existing])
    assert row["exitCode"] == 2 and "output exists" in row["stderr"] and existing.read_bytes() == previous
    save(complete=True)
    print(f"Passed {len(products)} products, 16 rejection paths, {len(rows)} CLI calls; {sum(p['samples'] for p in products)} exact sample checks", flush=True)


if __name__ == "__main__":
    main()
