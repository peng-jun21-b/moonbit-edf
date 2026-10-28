"""One negative physical map -> duration edit -> multirate epoch (MIT).

Original fixed-width EDF input and Fraction calibration/sample-clock oracles.
Build the JS bridge first; --output must identify a new case directory.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, read, change = h["make"], h["read_raw"], h["change"]
annotations = runpy.run_path(str(ROOT / "tools/check-annotation-query.py"))["original_annotations"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    src = work / "source.edf"
    make(src, "edf", [6, 3], ["+0"], duration="2",
         events={(0, 0): [("+0.5", "0.75", "stage")], (0, 1): [("+0.75", None, "keep")]})
    for s in [0, 1]:
        change(src, 104, s, "-32768"); change(src, 112, s, "32767")
    raw = read(src); data = bytearray(src.read_bytes())
    data[raw["hs"]:raw["hs"] + 18] = b"".join(v.to_bytes(2, "little", signed=True) for v in [-4, -2, 0, 2, 4, 6, 10, 20, 30])
    src.write_bytes(data); raw = read(src); original = annotations(raw); source_hash = sha(src)
    rows, products = [], []
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            bridgeSha256=sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js"),
            oracle="Original fixed-width bytes, Fraction physical calibration and exact sample-clock enumeration",
            inputs=[dict(path=str(src), sha256=source_hash)], commands=rows, products=products,
            expectedEpoch=dict(digital=[[0, 2, 4], [20, 30]], physical=[[5, 1, -3], [20, 30]],
                times=[["2/3", "1", "4/3"], ["2/3", "4/3"]]), confirmedDefects=[]), indent=2), encoding="utf-8")
    def run(name, argv, options):
        params = work / (name + ".json"); params.write_text(json.dumps(options), encoding="utf-8")
        cmd = ["node", str(ROOT / "tools/edf.mjs"), *map(str, argv), str(params)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr); save()
        assert result.returncode == 0, row
        return json.loads(row["stdout"])
    def verify(path, expected, mapped=None):
        got = read(path)
        assert annotations(got) == expected
        assert got["starts"] == raw["starts"] and got["duration"] == raw["duration"] and got["clock"] == raw["clock"]
        assert got["ns"] == raw["ns"] and got["nr"] == raw["nr"]
        for s in raw["ordinary"]:
            assert got["points"][s] == raw["points"][s] and got["blocks"][0][s] == raw["blocks"][0][s]
            for c in range(10):
                if s == 0 and c in [2, 3, 4]:
                    if mapped is not None: assert got["columns"][c][s] == mapped["columns"][c][s]
                else: assert got["columns"][c][s] == raw["columns"][c][s]
        assert got["columns"][2][0].strip() == b"arb"
        assert F(got["columns"][3][0].decode().strip()) == 65541
        assert F(got["columns"][4][0].decode().strip()) == -65529
        products.append(dict(path=str(path), sha256=sha(path), ordinarySamplesPreserved=9,
            untouchedChannelCalibrationPreserved=True, annotationIdentityPreserved=True))
        save(); return got
    mapped_path = work / "mapped.edf"
    run("calibrate", ["calibrate", src, mapped_path], dict(signal=0, scale=-2.0, offset=5.0, unit="arb"))
    mapped = verify(mapped_path, original)
    for s in raw["ann"]:
        assert mapped["blocks"][0][s] == raw["blocks"][0][s]
        assert all(mapped["columns"][c][s] == raw["columns"][c][s] for c in range(10))
    options = dict(start="1/3", end="4/3")
    found = run("query", ["annotations-window", mapped_path], options)
    assert [v["annotation_index"] for v in found] == [0, 1] and [v["annotation"] for v in found] == original
    target = dict(found[0]["annotation"], duration="1")
    out = work / "edited.edf"
    run("duration-update", ["annotation-update", mapped_path, out], dict(index=found[0]["annotation_index"], annotation=target))
    edited = verify(out, [target, original[1]], mapped)
    fresh = run("requery", ["annotations-window", out], options)
    assert [v["annotation"] for v in fresh] == [target, original[1]] and fresh[0]["annotation_index"] == 0
    epoch = run("epoch", ["epoch", out], dict(annotation=fresh[0]["annotation_index"], signals=[0, 1], before="0", after="0", max_samples=5))
    assert epoch["annotation"] == target and epoch["complete"] and epoch["samples"] == 5
    assert F(epoch["start"]) == F("0.5") and F(epoch["end"]) == F("1.5")
    for s, window in enumerate(epoch["channels"]):
        expected = [(r, j, v, t) for r, j, v, t in raw["points"][s] if F("0.5") <= t < F("1.5")]
        assert [(v["record"], v["sample"], v["digital"], F(v["time_numerator"]) / F(v["time_denominator"])) for v in window["samples"]] == expected
        assert window["unit"] == ("arb" if s == 0 else "uV")
        pmin, pmax, dmin, dmax = [F(edited["columns"][c][s].decode().strip()) for c in [3, 4, 5, 6]]
        for sample in window["samples"]:
            physical = pmin + (F(sample["digital"]) - dmin) * (pmax - pmin) / (dmax - dmin)
            assert physical == (-2 * sample["digital"] + 5 if s == 0 else sample["digital"])
            assert math.isclose(sample["physical"], float(physical), rel_tol=0, abs_tol=1e-8)
    assert sha(src) == source_hash; save(True)
    print(json.dumps(dict(status="passed", calls=len(rows), products=len(products), confirmedDefects=[])))


if __name__ == "__main__":
    main()
