from fractions import Fraction as F
"""Independent fixed-width EDF/BDF fixtures and exhaustive timestamp oracle.

Uses no MoonBit writer or selection algorithm. EDF+D/BDF+D is verified against
the published record/TAL layout, not represented as pyedflib acceptance.
"""
import csv
import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def field(value, width):
    data = str(value).encode("ascii")
    assert len(data) <= width
    return data.ljust(width, b" ")


def fixture(path, bdf, mode, duration, starts, counts):
    """Write raw fields in specification order; return independently known data."""
    width = 3 if bdf else 2
    low, high = (-8388608, 8388607) if bdf else (-32768, 32767)
    plus = mode != "plain"
    label = 'Fast,"quoted'
    labels = [label, "Slow"][:len(counts)]
    ns = len(counts) + int(plus)
    signature = b"\xffBIOSEMI" if bdf else b"0       "
    prefix = "BDF" if bdf else "EDF"
    marker = prefix + ("+D" if mode == "discontinuous" else "+C") if plus else ""
    fixed = (signature + field("X X X X", 80)
             + field("Startdate 01-JAN-2020 X X X", 80) + b"01.01.2000.00.00"
             + field(256 * (1 + ns), 8) + field(marker, 44)
             + field(len(starts), 8) + field(duration, 8) + field(ns, 4))
    # First signal has negative gain; second has positive gain.
    pmin, pmax = [100, -100][:len(counts)], [-100, 100][:len(counts)]
    def ann(values, extra):
        return values + ([extra] if plus else [])
    fields = [(16, ann(labels, prefix + " Annotations")), (80, [""] * ns),
              (8, ann(["uV"] * len(counts), "")), (8, ann(pmin, -1)),
              (8, ann(pmax, 1)), (8, [low] * ns), (8, [high] * ns),
              (80, [""] * ns), (8, ann(counts, 64)), (32, [""] * ns)]
    data = bytearray(fixed + b"".join(field(v, n) for n, values in fields for v in values))
    known = [[] for _ in counts]
    for r, onset in enumerate(starts):
        for s, per in enumerate(counts):
            for j in range(per):
                digital = [low, high, -100, 0, 100, 1, -1][(r + j + s) % 7]
                data.extend(digital.to_bytes(width, "little", signed=True))
                # Full enumeration is deliberately different from the binary
                # lower-bound selection used in the implementation.
                known[s].append(dict(record=r, sample=j, time=F(str(onset)) + F(str(duration)) * F(j,per),
                                     digital=digital,
                                     physical=pmin[s] + (digital - low) * (pmax[s] - pmin[s]) / (high - low)))
        if plus:
            tal = ("+" + str(onset)).encode("ascii") + b"\x14\x14\x00"
            data.extend(tal.ljust(64 * width, b"\x00"))
    path.write_bytes(data)
    return dict(samples=known, labels=labels, starts=starts, duration=duration)


def selected(known, signal, start, end):
    return [p for p in known["samples"][signal] if F(str(start)) <= p["time"] < F(str(end))]


def expected_gaps(known, start, end):
    out = []
    for r in range(1, len(known["starts"])):
        left = known["starts"][r - 1] + known["duration"]
        right = known["starts"][r]
        a, b = max(start, left), min(end, right)
        if right - left > 1e-7 and a < b:
            out.append(dict(after_record=r - 1, start=a, end=b))
    return out


def check_window(result, known, options):
    s, start, end = options["signal"], options["start"], options["end"]
    assert result["signal"] == s and result["label"] == known["labels"][s]
    assert result["unit"] == "uV" and F(result["start"]) == F(str(start)) and F(result["end"]) == F(str(end))
    expected = selected(known, s, start, end)
    assert len(result["samples"]) == len(expected)
    for actual, point in zip(result["samples"], expected, strict=True):
        assert F(int(actual["time"]["numerator"]),int(actual["time"]["denominator"])) == point["time"]
        for key in ("record", "sample", "digital"):
            assert actual[key] == point[key], (actual, point)
        assert math.isclose(actual["physical"], point["physical"], rel_tol=1e-12, abs_tol=1e-12)
    assert [(x["after_record"],F(x["start"]),F(x["end"])) for x in result["gaps"]] == [(x["after_record"],F(str(x["start"])),F(str(x["end"]))) for x in expected_gaps(known,start,end)]


def check_csv(text, known, options):
    actual = list(csv.DictReader(io.StringIO(text)))
    expected = [(s, p) for s in options["signals"]
                for p in selected(known, s, options["start"], options["end"])]
    assert len(actual) == len(expected)
    for row, (s, point) in zip(actual, expected, strict=True):
        assert int(row["signal"]) == s and row["label"] == known["labels"][s]
        assert int(row["record"]) == point["record"] and int(row["sample"]) == point["sample"]
        assert F(row["time_seconds"]) == point["time"]
        physical = options.get("physical", True)
        assert row["unit"] == ("uV" if physical else "digital")
        assert math.isclose(float(row["value"]), point["physical" if physical else "digital"],
                            rel_tol=1e-12, abs_tol=1e-12)


def run():
    tasks, checks, fixtures = [], [], []
    with tempfile.TemporaryDirectory(prefix="moonedf-window-") as tmp:
        work = Path(tmp)
        def add(src, known, options, error=None):
            tasks.append(dict(kind="report", input=str(src), options=options))
            checks.append((known, options, error))

        for bdf in (False, True):
            for mode, duration, starts, counts in [
                ("plain", 1, [0, 1, 2], [4, 2]),
                ("continuous", .7, [.1, .8, 1.5], [3, 2]),
                ("discontinuous", 1, [.25, 2.25, 5.25], [4, 2]),
                ("discontinuous", 0, [.25, .25, 2.25], [1, 1]),
                # Allowed sub-100ns timekeeping noise: cannot assume strictly
                # increasing records or break when the first onset exceeds end.
            ]:
                src = work / f"case-{len(fixtures)}.{'bdf' if bdf else 'edf'}"
                known = fixture(src, bdf, mode, duration, starts, counts)
                fixtures.append(dict(name=src.name, mode=mode, duration=duration,
                                     sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
                bounds = {(-1, 9), (0, 0), (.5, 2.5), (1.5, 2), (9, 10)}
                for point in known["samples"][0]:
                    t = point["time"]
                    bounds.update([(t, t), (t, math.nextafter(t, math.inf)),
                                   (math.nextafter(t, -math.inf), t), (-1, t), (t, 9)])
                for start, end in sorted(bounds):
                    for s in range(len(counts)):
                        add(src, known, dict(command="window", signal=s, start=start, end=end))
                for physical in (False, True):
                    add(src, known, dict(command="window-csv", signals=[1, 0], start=.5, end=2.5, physical=physical))
                add(src, known, dict(command="window-csv", signals=[0, 1], start=9, end=10))
                good = dict(command="window", signal=0, start=-1, end=9)
                total = len(known["samples"][0])
                add(src, known, dict(good, max_samples=total))
                add(src, known, dict(good, max_samples=total - 1), "sample limit")
                for change in [dict(signal=-1), dict(signal=2), dict(start=10),
                               dict(max_samples=0), dict(max_samples=-1), dict(start=None)]:
                    add(src, known, dict(good, **change), "")
                for indices in ([], [0, 0], [2]):
                    add(src, known, dict(command="window-csv", signals=indices, start=0, end=9), "")
                add(src, known, dict(command="window-csv", signals=[0, 1], start=-1, end=9,
                                     max_samples=total), "sample limit")

        cli_src, cli_known = src, known
        # Default cap must reject, not return a plausible-looking truncated record.
        large = work / "default-cap.edf"
        large_known = fixture(large, False, "plain", 1, [0], [65537])
        add(large, large_known, dict(command="window", signal=0, start=0, end=1))
        add(large, large_known, dict(command="window", signal=0, start=0, end=1, max_samples=65537))
        taskfile, resultfile = work / "tasks.json", work / "results.json"
        taskfile.write_text(json.dumps(tasks, allow_nan=False, default=str), encoding="utf-8")
        subprocess.run(["node", str(ROOT / "tools/reference-batch.mjs"), str(taskfile), str(resultfile)],
                       cwd=ROOT, check=True, timeout=60)
        results = json.loads(resultfile.read_text(encoding="utf-8"))
        assert len(results) == len(checks)
        for index, (result, (known, options, error)) in enumerate(zip(results, checks, strict=True)):
            try:
                if error is not None:
                    assert not result["ok"] and error in result["error"]
                else:
                    assert result["ok"], result
                    if options["command"] == "window":
                        check_window(result["result"], known, options)
                    else:
                        check_csv(result["result"]["text"], known, options)
            except AssertionError as exc:
                raise AssertionError(f"case {index}: {options}: {str(result)[:1000]}") from exc

        # Invoke the actual CLI too, including rejection with no partial stdout.
        cli_checks = 0
        for options, error in [
            (dict(command="window", signal=0, start=.25, end=2.5), None),
            (dict(command="window-csv", signals=[1, 0], start=.25, end=2.5, physical=False), None),
            (dict(command="window", signal=0, start=0, end=9, max_samples=1), "sample limit"),
            (dict(command="window", signal=0, start=None, end=9), ""),
        ]:
            optfile = work / "options.json"
            optfile.write_text(json.dumps(options), encoding="utf-8")
            p = subprocess.run(["node", str(ROOT / "tools/edf.mjs"), options["command"], str(cli_src), str(optfile)],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
            if error is None:
                assert p.returncode == 0, p.stderr
                if options["command"] == "window":
                    check_window(json.loads(p.stdout), cli_known, options)
                else:
                    check_csv(p.stdout, cli_known, options)
            else:
                assert p.returncode == 2 and p.stdout == "" and error in p.stderr
            cli_checks += 1
        # JSON exponent overflow is syntactically legal but must not turn into
        # an unbounded query. The MoonBit API also has nonfinite unit coverage.
        optfile.write_text('{"signal":0,"start":0,"end":1e999}', encoding="utf-8")
        p = subprocess.run(["node", str(ROOT / "tools/edf.mjs"), "window", str(cli_src), str(optfile)],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert p.returncode == 0 and len(json.loads(p.stdout)["samples"]) == len(cli_known["samples"][0])
        cli_checks += 1

    receipt = dict(status="passed", utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   platform=platform.platform(), oracle="independent fixed-width bytes and exhaustive enumeration",
                   reference_scope="not pyedflib validation of discontinuous files",
                   fixtures=fixtures, additional_large_fixture_samples=65537,
                   checks=len(checks), cli_checks=cli_checks)
    (ROOT / "evidence/window-reference.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "fixtures"}))


if __name__ == "__main__":
    run()
