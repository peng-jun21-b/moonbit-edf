"""Original fixed-width fixtures + exhaustive Fraction sample oracle (MIT).

Build the JS bridge, then use --output /a/new/report.json. Inputs and products
are retained beside the report in <stem>-cases for inspection. No downloads,
patient data, PyEDFlib, or MoonBit writer are used to create reference inputs.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def field(value, n):
    data = str(value).encode("ascii")
    assert len(data) <= n
    return data.ljust(n, b" ")


def fixture(path, fmt, per, starts, duration="1", mode="D", events=None):
    width = 2 if fmt == "edf" else 3
    low, high = (-32768, 32767) if width == 2 else (-8388608, 8388607)
    ann = 0 if mode == "plain" else 2
    counts = per + [128] * ann
    ns = len(counts)
    fixed = (
        (b"0       " if width == 2 else b"\xffBIOSEMI")
        + field("X X X X", 80) + field("Startdate 01-JAN-2020 X X X", 80)
        + b"01.01.2000.00.00" + field(256 * (ns + 1), 8)
        + field("" if not ann else fmt.upper() + "+" + mode, 44)
        + field(len(starts), 8) + field(duration, 8) + field(ns, 4)
    )
    cols = [
        (16, [f"raw{s}" for s in range(len(per))] + [fmt.upper() + " Annotations"] * ann),
        (80, [""] * ns), (8, ["uV"] * len(per) + [""] * ann),
        (8, [-100] * len(per) + [-1] * ann), (8, [100] * len(per) + [1] * ann),
        (8, [low] * ns), (8, [high] * ns), (80, [""] * ns),
        (8, counts), (32, [""] * ns),
    ]
    data = bytearray(fixed + b"".join(field(v, n) for n, values in cols for v in values))
    model = []
    for r, onset in enumerate(starts):
        rows = []
        for s, count in enumerate(per):
            values = [low if j == 0 else high if j == count - 1 else low + (r * 100 + s * 10 + j) % (high - low + 1) for j in range(count)]
            rows.append(values)
            for value in values:
                data.extend(value.to_bytes(width, "little", signed=True))
        for a in range(ann):
            tal = onset.encode() + b"\x14\x14\0" if a == 0 else b""
            entries = (events or {}).get((r, a), [])
            if not per and a == 0:
                time, span, text = entries[0]
                assert time == onset and span is None
                tal = onset.encode() + b"\x14\x14" + text.encode() + b"\x14\0"
                entries = entries[1:]
            for time, span, text in entries:
                tal += time.encode() + (b"\x15" + span.encode() if span is not None else b"") + b"\x14" + text.encode() + b"\x14\0"
            assert len(tal) <= 128 * width
            data.extend(tal.ljust(128 * width, b"\0"))
        model.append((F(onset), rows))
    path.write_bytes(data)
    return dict(per=per, duration=F(duration), rows=model, events=events or {}, ann=ann, sha256=hashlib.sha256(data).hexdigest())


def selected(model, signal, lower, upper):
    return [(r, j, v, start + model["duration"] * F(j, model["per"][signal]))
            for r, (start, rows) in enumerate(model["rows"])
            for j, v in enumerate(rows[signal])
            if lower <= start + model["duration"] * F(j, model["per"][signal]) < upper]


def check_window(value, model, signal, lower, upper):
    expected = selected(model, signal, lower, upper)
    actual = [(s["record"], s["sample"], s["digital"], F(int(s["time_numerator"]), int(s["time_denominator"]))) for s in value["samples"]]
    assert actual == expected, (actual, expected)
    assert F(value["start"]) == lower and F(value["end"]) == upper
    gaps = []
    for r in range(1, len(model["rows"])):
        lo = max(lower, model["rows"][r - 1][0] + model["duration"])
        hi = min(upper, model["rows"][r][0])
        if lo < hi:
            gaps.append((r - 1, lo, hi))
    assert [(g["after_record"], F(g["start"]), F(g["end"])) for g in value["gaps"]] == gaps
    return len(expected)


def read_product(path):
    data = path.read_bytes()
    width = 3 if data[:8] == b"\xffBIOSEMI" else 2
    ns, nr, start = int(data[252:256]), int(data[236:244]), int(data[184:192])
    cols, at = [], 256
    for size in [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]:
        cols.append([data[at + i * size:at + (i + 1) * size].decode().strip() for i in range(ns)])
        at += ns * size
    per = [int(v) for v in cols[8]]
    rs = sum(per) * width
    assert start == 256 * (ns + 1) and len(data) == start + nr * rs
    duration = F(data[244:252].decode().strip())
    hh, mm, ss = map(int, data[176:184].decode().split("."))
    shift = hh * 3600 + mm * 60 + ss
    points = [[] for _ in range(ns)]
    annotations, origins = [], []
    for r in range(nr):
        payloads, at = [], start + r * rs
        for n in per:
            payloads.append(data[at:at + n * width]); at += n * width
        time = None
        for s, raw in enumerate(payloads):
            if "Annotations" not in cols[0][s]:
                continue
            for tal in raw.split(b"\0"):
                if not tal:
                    continue
                parts = tal.split(b"\x14"); assert parts[-1] == b""
                stamp = parts[0].split(b"\x15")
                if time is None:
                    time = F(stamp[0].decode())
                for text in parts[1:-1]:
                    if text:
                        annotations.append((s, F(stamp[0].decode()) + shift, stamp[1].decode() if len(stamp) == 2 else None, text.decode()))
        assert time is not None
        origins.append(time + shift)
        for s, raw in enumerate(payloads):
            if "Annotations" in cols[0][s]:
                continue
            for j in range(per[s]):
                points[s].append((time + shift + duration * F(j, per[s]), int.from_bytes(raw[j * width:(j + 1) * width], "little", signed=True)))
    return dict(points=points, annotations=annotations, origins=origins, duration=duration, record_bytes=rs)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    tasks, checks, models = [], [], []
    def add(name, path, opts, check, out=None, error=None):
        tasks.append(dict(kind="transform" if out else "report", input=str(path), options=opts, **({"output": str(out)} if out else {})))
        checks.append((name, check, error, out))
    def crop(path, model, lower, upper, name, error=None):
        out = work / (name + path.suffix)
        def verify(_):
            actual = read_product(out)
            for s in range(len(model["per"])):
                expect = [(t, v) for _, _, v, t in selected(model, s, F(lower), F(upper))]
                assert actual["points"][s] == expect, (name, s)
            expected_events = [(len(model["per"]) + a, F(t), d, text) for (r, a), events in model["events"].items() for t, d, text in events if F(lower) <= F(t) < F(upper)]
            if model["ann"]:
                assert sorted(actual["annotations"]) == sorted(expected_events), name
            assert actual["duration"] >= 0
        add(name, path, dict(command="crop-time", start=lower, end=upper), verify, out, error)
    for fmt in ["edf", "bdf"]:
        wide = work / ("wide." + fmt)
        model = fixture(wide, fmt, [40000], ["+0"], mode="plain"); models.append((wide, model))
        crop(wide, model, "0", ".5", fmt + "-wide-first-half")
        crop(wide, model, ".5", "1", fmt + "-wide-second-half")
        crop(wide, model, "0", "1", fmt + "-wide-whole")
        if fmt == "edf":
            prime = work / "prime-indivisible.edf"
            model_prime = fixture(prime, fmt, [32771], ["+0"], mode="plain"); models.append((prime,model_prime))
            crop(prime, model_prime, "0", "1", "edf-oversize-indivisible", "61440")
            compact = work / "compact-duration.edf"
            model_compact = fixture(compact,fmt,[40000],["+0"],duration="12345e-9",mode="plain");models.append((compact,model_compact))
            crop(compact,model_compact,"0","12345e-9","edf-header-width-aware-split")
        events = {(0, 0): [("-0.1", None, "negative"), ("+0.75", "0.000000000000000000001", "rational")],
                  (1, 1): [("+1.5", None, "gap"), ("+2.500000000000000000001", "0.1", "later"), ("-0.1", "0.000000000000000000001", "negative-retained")]}
        multi = work / ("multi." + fmt)
        model = fixture(multi, fmt, [4, 2], ["+0.25", "+2.250000000000000000001"], events=events); models.append((multi, model))
        crop(multi, model, ".75", "2.750000000000000000001", fmt + "-multirate-gap-crop")
        crop(multi, model, ".5", "1", fmt + "-phase-mismatch", "different sample origins or extents")
        whole = work / ("whole-second-record." + fmt)
        def whole_check(_, m=model, path=whole):
            actual = read_product(path)
            assert actual["origins"] == [m["rows"][1][0]]
            for s in range(len(m["per"])):
                expected = [(m["rows"][1][0] + m["duration"] * F(j,m["per"][s]),v) for j,v in enumerate(m["rows"][1][1][s])]
                assert actual["points"][s] == expected
            expected_events = [(len(m["per"]) + a,F(t),d,text) for (r,a),es in m["events"].items() if r==1 for t,d,text in es]
            assert sorted(actual["annotations"]) == sorted(expected_events)
        add(fmt + "-whole-crop-negative-annotation", multi, dict(command="crop", first_record=1, records=1), whole_check, whole)
        for signal in [0, 1]:
            for lower, upper in [("-1", "1/3"), ("1/3", "1.25"), ("1.25", "2.250000000000000000001"), ("2.250000000000000000001", "3.25")]:
                add(f"{fmt}-window-{signal}-{lower}", multi, dict(command="window", signal=signal, start=lower, end=upper), lambda v, m=model, s=signal, a=F(lower), b=F(upper): check_window(v, m, s, a, b))
        for index, before, after, partial, error in [(0, "0", "0.5", True, None), (1, "1/3", "1/3", False, None), (2, ".1", ".1", True, None), (2, ".1", ".1", False, "missing recording time")]:
            source_events = [e for key in sorted(events) for e in events[key]]
            t, d, _ = source_events[index]; lower = F(t) - F(before); upper = F(t) + F(d or "0") + F(after)
            def epoch(v, m=model, lo=lower, hi=upper):
                count = sum(check_window(w, m, s, lo, hi) for s, w in enumerate(v["channels"]))
                assert count == v["samples"]
                expected_complete = lo >= m["rows"][0][0] and hi <= m["rows"][-1][0] + m["duration"] and all(not (max(lo, m["rows"][r-1][0]+m["duration"]) < min(hi, m["rows"][r][0])) for r in range(1,len(m["rows"])))
                assert v["complete"] == expected_complete
            add(f"{fmt}-epoch-{index}-{partial}", multi, dict(command="epoch", annotation=index, signals=[0,1], before=before, after=after, allow_partial=partial), epoch, error=error)
        add(fmt + "-shared-budget", multi, dict(command="epoch", annotation=1, signals=[0,1], before="1/3", after="1/3", max_samples=3), lambda _: None, error="sample limit")
        zero = work / ("zero." + fmt)
        model = fixture(zero, fmt, [1,1], ["+0.25", "+2.250000000000000000001"], duration="0", events=events); models.append((zero,model))
        for lo, hi in [("0", "3"), ("2", "3"), ("0", "1")]:
            crop(zero, model, lo, hi, fmt + "-zero-" + lo + "-" + hi)
        crop(zero, model, "1", "2", fmt + "-zero-no-record", "no records")
        only = work / ("annotation-only." + fmt)
        only_events = {(0,0): [("+0.25",None,"first"), ("+0.5","0.25","extra")], (1,0): [("+2.250000000000000000001",None,"second")]}
        model = fixture(only,fmt,[],["+0.25","+2.250000000000000000001"],duration="0",events=only_events);models.append((only,model))
        crop(only,model,"0","3",fmt+"-annotation-only-all")
        crop(only,model,"2","3",fmt+"-annotation-only-last")
        thirds = work / ("thirds." + fmt)
        model = fixture(thirds, fmt, [3,6], ["+0"], mode="C"); models.append((thirds,model))
        crop(thirds, model, "0", "1", fmt + "-thirds-full")
        crop(thirds, model, "1/3", "1", fmt + "-thirds-recurring", "finite decimal")
    request, response = work / "tasks.json", work / "results.json"
    request.write_text(json.dumps(tasks), encoding="utf-8")
    subprocess.run(["node", str(ROOT / "tools/reference-batch.mjs"), str(request), str(response)], cwd=ROOT, check=True)
    values = json.loads(response.read_text())
    receipts = []
    for (name, check, error, out), result in zip(checks, values, strict=True):
        assert result["ok"] == (error is None), (name, result)
        if error:
            assert error in result["error"], (name, result)
            if out:
                assert not out.exists(), name
        else:
            check(result["result"])
        receipts.append(dict(name=name, expected_error=error, passed=True))
    for path, model in models:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == model["sha256"]
    args.output.write_text(json.dumps(dict(status="passed", python=platform.python_version(), oracle="Original fixed-width writer/reader + Fraction exhaustive enumeration", checks=receipts, inputs=[dict(path=str(p),sha256=m["sha256"]) for p,m in models], artifacts=str(work)), indent=2), encoding="utf-8")
    print(f"Passed {len(receipts)} focused crop/window/epoch checks; artifacts: {work}")


if __name__ == "__main__":
    main()
