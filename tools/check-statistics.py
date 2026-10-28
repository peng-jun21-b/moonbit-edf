"""Independent physical statistics checks using Fraction and 90-digit Decimal.

Reference EDF/BDF inputs are constructed as raw fixed-width bytes. --inputs
can reuse the retained pre-repair EDF fixtures. No floating square/sum is used
to obtain the expected results, and no MoonBit writer creates source fixtures.
"""
import argparse
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import platform
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
H = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, change, read = H["make"], H["change"], H["read_raw"]
PROFILES = [
    ("tiny-constant", "1e-200", "2e-200", 0, 1, [[0] * 4]),
    ("large-constant", "1e200", "2e200", 0, 1, [[0] * 4]),
    ("finite-variance", "-1e154", "1e154", -1, 1, [[-1, 1]]),
    ("diluted-prefix", "-1e155", "1e155", -1, 1, [[-1, 1] + [0] * 2000]),
    ("genuine-overflow", "-1e200", "1e200", -1, 1, [[-1, 1]]),
    ("zero", "-1", "1", -1, 1, [[0] * 4]),
    ("range-flags", "1e-200", "2e-200", -1, 1, [[-2, -1, 0, 1, 2]]),
    ("negative-gain", "2e-200", "1e-200", -1, 1, [[-1, 0, 1, 0]]),
    ("empty", "-1", "1", -1, 1, []),
]


def fixture(path, fmt, lo, hi, dlo, dhi, rows):
    count = len(rows[0]) if rows else 4
    make(path, fmt, [count], ["+" + str(i) for i in range(len(rows))])
    for col, value in [(104, lo), (112, hi), (120, dlo), (128, dhi)]: change(path, col, 0, value)
    raw = read(path); data = bytearray(raw["data"]); size = sum(raw["per"]) * raw["width"]
    for r, row in enumerate(rows):
        for j, value in enumerate(row):
            at = raw["hs"] + r * size + j * raw["width"]
            data[at:at + raw["width"]] = value.to_bytes(raw["width"], "little", signed=True)
    path.write_bytes(data)


def oracle(path):
    raw = read(path); digital = [v[2] for v in raw["points"][0]]
    lo, hi = [F(raw["columns"][c][0].decode().strip()) for c in [3, 4]]
    dlo, dhi = [int(raw["columns"][c][0]) for c in [5, 6]]
    physical = [lo + F(v - dlo, dhi - dlo) * (hi - lo) for v in digital]
    counts = dict(samples=len(digital), below_range=sum(v < dlo for v in digital), above_range=sum(v > dhi for v in digital),
                  at_minimum=digital.count(dlo), at_maximum=digital.count(dhi))
    fields = dict.fromkeys(["minimum", "maximum", "mean", "variance", "rms"])
    if physical:
        mean = sum(physical) / len(physical)
        variance = sum((v - mean) ** 2 for v in physical) / len(physical)
        square = sum(v * v for v in physical) / len(physical)
        with localcontext() as ctx:
            ctx.prec = 90
            dec = lambda f: Decimal(f.numerator) / Decimal(f.denominator)
            fields = {k: str(dec(v)) for k, v in dict(minimum=min(physical), maximum=max(physical), mean=mean, variance=variance).items()}
            fields["rms"] = str(dec(square).sqrt())
    representable = all(v is None or math.isfinite(float(v)) for v in fields.values())
    return dict(counts=counts, fields=fields, representable=representable)


def verify(value, expected):
    for key, count in expected["counts"].items(): assert value[key] == count, (key, value[key], count)
    for key, text in expected["fields"].items():
        actual = value.get(key)
        if text is None: assert actual is None; continue
        want = float(text)
        assert actual is not None and math.isfinite(actual)
        assert actual == 0 if want == 0 else math.isclose(actual, want, rel_tol=1e-12, abs_tol=0), (key, actual, text)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--inputs", type=Path)
    parser.add_argument("--resume", type=Path, help="Reuse already executed command results from a retained partial receipt")
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    rows, sources, stats = [], {}, []
    reused = []
    if args.resume:
        earlier = json.loads(args.resume.read_text(encoding="utf-8"))
        rows, sources, stats = earlier["checks"], earlier["sourceHashes"], earlier["statistics"]
    def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress", python=platform.python_version(),
            oracle="Exact Fraction calibration, population variance and 90-digit Decimal RMS; float projection only for final values",
            sourceHashes=sources, checks=rows, statistics=stats, reusedCommandResults=reused,
            resumedFrom=str(args.resume) if args.resume else None), indent=2), encoding="utf-8")
    def run(name, command):
        cached = next((v for v in rows if v["name"] == name), None)
        if cached is not None:
            reused.append(name); return cached
        cmd = ["node", "--max-old-space-size=64", str(ROOT / "tools/edf.mjs"), *map(str, command)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); save(); (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr)
        return row
    def check_stats(name, source):
        expected = oracle(source); options = work / (name + ".json"); options.write_text('{"signal":0}')
        row = run(name, ["stats", source, options])
        if row.get("verified"): return
        if expected["representable"]:
            assert row["exitCode"] == 0, row
            verify(json.loads(row["stdout"]), expected)
        else:
            assert row["exitCode"] == 2 and "Limit(" in row["stderr"], row
        row["verified"] = True; row["expectedExitCode"] = 0 if expected["representable"] else 2
        stats.append(dict(name=name, source=str(source), expected=expected, actual=json.loads(row["stdout"]) if row["stdout"] else None))
        print("verified", name, flush=True); save()
    for fmt in ["edf", "bdf"]:
        for name, lo, hi, dlo, dhi, values in PROFILES:
            path = work / (name + "." + fmt)
            old = args.inputs / path.name if args.inputs else None
            if old and old.exists(): path.write_bytes(old.read_bytes())
            else: fixture(path, fmt, lo, hi, dlo, dhi, values)
            sources[str(path)] = sha(path)
            check_stats(name + "-" + fmt, path)
        source = work / ("session-source." + fmt)
        fixture(source, fmt, "1e200", "2e200", 0, 1, [[0] * 4, [0] * 4]); sources[str(source)] = sha(source)
        products = []
        for label, command, options in [("first", "crop-time", dict(start="0", end="1")), ("tail", "crop", dict(first_record=1, records=1))]:
            output = work / ("session-" + label + "." + fmt); opt = work / ("session-" + label + "-" + fmt + ".json"); opt.write_text(json.dumps(options))
            row = run("session-" + label + "-" + fmt, [command, source, output, opt]); assert row["exitCode"] == 0, row
            row.update(verified=True, expectedExitCode=0); products.append(output)
        joined = work / ("session-joined." + fmt)
        row = run("session-append-" + fmt, ["append", *products, joined]); assert row["exitCode"] == 0, row
        value, original = read(joined), read(source)
        assert value["points"][0] == original["points"][0]
        assert value["columns"][3][0] == original["columns"][3][0] and value["columns"][4][0] == original["columns"][4][0]
        row.update(verified=True, expectedExitCode=0)
        check_stats("session-stats-" + fmt, joined)
        options = work / ("invalid-signal-" + fmt + ".json"); options.write_text('{"signal":1}')
        row = run("invalid-signal-" + fmt, ["stats", source, options]); assert row["exitCode"] == 2 and "Invalid(" in row["stderr"]
        row.update(verified=True, expectedExitCode=2)
    assert all(sha(Path(path)) == digest for path, digest in sources.items())
    assert len(rows) == 28 and len(stats) == 20 and all(v.get("verified") for v in rows)
    save(complete=True); print(f"Passed {len(rows)} CLI checks and {len(stats)} independent statistics expectations; original inputs unchanged", flush=True)


if __name__ == "__main__":
    main()
