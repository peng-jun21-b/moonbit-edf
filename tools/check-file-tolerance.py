"""Real file-consumer checks for explicit timing policy (synthetic MIT).

Build the bridge, then choose a new --output. Raw fixtures and Fraction oracles
are independent of MoonEDF's writer; no downloads or extra dependencies.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import runpy
from types import SimpleNamespace
import subprocess

ROOT = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, raw_read, field = h["make"], h["read_raw"], h["field"]
original_annotations = runpy.run_path(str(ROOT / "tools/check-annotation-query.py"))["original_annotations"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
EPS = "0.000000000000000000001"
SMALL = "0." + "0" * 21 + "9" * 30
assert F(SMALL) < F(EPS) and float(SMALL) == float(EPS)


def read(path):
    data = path.read_bytes(); declared = int(data[236:244])
    if declared == -1:
        ns, hs = int(data[252:256]), int(data[184:192])
        width = 3 if data[:8] == b"\xffBIOSEMI" else 2
        counts = [int(data[256 + ns * 216 + s * 8:256 + ns * 216 + (s + 1) * 8]) for s in range(ns)]
        size = sum(counts) * width
        assert (len(data) - hs) % size == 0
        # Resolve count only in an in-memory shadow header for the independent
        # raw reader. The tested input/output bytes are never changed here.
        shadow = bytearray(data); shadow[236:244] = field((len(data) - hs) // size, 8)
        result = raw_read(SimpleNamespace(read_bytes=lambda: bytes(shadow)))
    else:
        result = raw_read(path)
    result["data"], result["declared"] = data, declared
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    rows, inputs, products, errors = [], [], [], []
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress", python=platform.python_version(),
            bridgeSha256=sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js"),
            oracle="Fixed-width/TAL bytes, body-inferred unknown count, original-index subtraction and Fraction clocks",
            threshold=dict(exact=EPS, below=SMALL, equalAsDouble=True), commands=rows, inputs=inputs,
            products=products, checkedErrors=errors), indent=2), encoding="utf-8")
    def run(name, argv, *, example=True, options=None):
        if options is not None:
            path = work / (name + ".json"); path.write_text(json.dumps(options)); argv = [*argv, path]
        cmd = ["node", str(ROOT / ("examples/remove-window.mjs" if example else "tools/edf.mjs")), *map(str, argv)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr); save()
        return row
    def make_input(fmt, *, clean=False):
        name = ("clean-" if clean else "jitter-") + fmt
        path = work / (name + "." + fmt)
        stamp = "+1" if clean else "+1.000000000000000000001"
        make(path, fmt, [2, 1], ["+0", stamp], events={
            (0, 0): [("+0.75", None if clean else "0.5", "--time-tolerance" if clean else "stage")],
            (1, 1): [(stamp, None, "keep" if clean else "drop")],
        })
        raw = read(path); data = bytearray(path.read_bytes()); width = raw["width"]
        at = raw["hs"] + sum(raw["per"]) * width
        data[at:at + 3 * width] = b"".join(v.to_bytes(width, "little", signed=True) for v in [1234, -2345, 3456])
        data[236:244] = field(-1, 8); path.write_bytes(data)
        inputs.append(dict(path=str(path), sha256=sha(path), clean=clean)); return path, read(path)
    def check_product(name, src, raw, out, removed, expected_counts):
        got = read(out)
        assert original_annotations(got) == [a for i, a in enumerate(original_annotations(raw)) if i not in set(removed)]
        assert got["nr"] == raw["nr"] == 2 and got["starts"] == raw["starts"]
        assert got["clock"] == raw["clock"] and got["duration"] == raw["duration"]
        assert got["data"][192:236] == raw["data"][192:236]
        for s in raw["ordinary"]:
            assert got["points"][s] == raw["points"][s]
            assert all(got["columns"][c][s] == raw["columns"][c][s] for c in range(10))
            assert all(got["blocks"][r][s] == raw["blocks"][r][s] for r in range(2))
        if not removed:
            assert out.read_bytes() == src.read_bytes() and got["declared"] == -1
        else:
            assert got["declared"] == 2
        products.append(dict(name=name, path=str(out), sha256=sha(out), removed=removed, declaredRecords=got["declared"],
            clockAndOrdinaryBytesPreserved=True, ordinarySamples=6, counts=expected_counts, byteIdenticalNoop=not removed))
        save(); print("verified", name, flush=True)
        return got
    def example(name, src, raw, tail, removed, counts):
        out = work / (name + (".edf" if raw["width"] == 2 else ".bdf"))
        row = run(name, [src, out, "0.75", "1.25", *tail]); assert row["exitCode"] == 0, row
        assert json.loads(row["stdout"]) == dict(output=str(out), matched=counts[0], removed=counts[1], remaining_in_window=counts[2])
        return out, check_product(name, src, raw, out, removed, counts)
    for fmt in ["edf", "bdf"]:
        src, raw = make_input(fmt)
        out, got = example("with-text-" + fmt, src, raw, ["drop", "--time-tolerance", EPS], [1], [2, 1, 1])
        example("all-matches-" + fmt, src, raw, ["--time-tolerance", "1e-21"], [0, 1], [2, 2, 0])
        example("no-selection-" + fmt, src, raw, ["missing", "--time-tolerance", EPS], [], [2, 0, 2])
        for label, tail in [("strict-" + fmt, ["drop"]), ("below-" + fmt, ["drop", "--time-tolerance", SMALL])]:
            rejected = work / (label + "." + fmt)
            row = run(label, [src, rejected, "0.75", "1.25", *tail])
            assert row["exitCode"] == 2 and "Invalid(" in row["stderr"] and not rejected.exists() and not row["stdout"], row
            errors.append(dict(name=label, checkedInvalid=True, noPartialOutput=True))
        if fmt == "edf":
            row = run("strict-output", ["annotations-window", out], example=False, options=dict(start="0.75", end="1.25"))
            assert row["exitCode"] == 2 and "Invalid(" in row["stderr"] and not row["stdout"], row
            errors.append(dict(name=row["name"], checkedInvalid=True, rawJitterStillPresent=True))
        else:
            row = run("epoch-output", ["epoch", out], example=False, options=dict(annotation=0, signals=[0, 1], before="0", after="0", allow_partial=True, time_tolerance=EPS, max_samples=2))
            assert row["exitCode"] == 0, row
            epoch = json.loads(row["stdout"]); assert epoch["samples"] == 2 and not epoch["complete"]
            for s, value in enumerate([1234, 3456]):
                assert [(v["digital"], F(v["time_numerator"]) / F(v["time_denominator"])) for v in epoch["channels"][s]["samples"]] == [(value, F("1.000000000000000000001"))]
                assert epoch["channels"][s]["gaps"] == [dict(after_record=0, start="1", end="1.000000000000000000001")]
            digest = sha(out)
            row = run("existing-output", [src, out, "0.75", "1.25", "drop", "--time-tolerance", EPS])
            assert row["exitCode"] == 2 and "EEXIST" in row["stderr"] and sha(out) == digest
            errors.append(dict(name=row["name"], existingOutputUnchanged=True))
    src, raw = make_input("edf", clean=True)
    example("literal-flag-text", src, raw, ["--time-tolerance"], [0], [2, 1, 1])
    example("legacy-no-text", src, raw, [], [0, 1], [2, 2, 0])
    out = work / "bad-suffix.edf"
    row = run("bad-suffix", [src, out, "0.75", "1.25", "--unknown", EPS])
    assert row["exitCode"] == 2 and "usage:" in row["stderr"] and not out.exists() and not row["stdout"], row
    errors.append(dict(name=row["name"], checkedUsage=True, noPartialOutput=True))
    assert all(sha(Path(v["path"])) == v["sha256"] for v in inputs)
    save(True)
    print(json.dumps(dict(status="passed", calls=len(rows), products=len(products), checkedErrors=len(errors), inputsUnchanged=len(inputs))))


if __name__ == "__main__":
    main()
