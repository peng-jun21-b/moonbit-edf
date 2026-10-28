"""One explicit-offset append -> stored-record-independent edit -> epoch (MIT).

Raw EDF input, original calibration bytes and Fraction seam-clock oracles.
Build the JS bridge first; --output must select a new case directory.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
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
    paths = [work / "left.edf", work / "right.edf"]
    events = [
        {(0, 0): [("+1", "1", "left-stage")], (0, 1): [("+0.25", None, "left")]},
        {(0, 0): [("-0.5", "1", "late-note")], (0, 1): [("+0.5", None, "other")]},
    ]
    for k, src in enumerate(paths):
        make(src, "edf", [3, 1], ["+0"], duration="1.5", events=events[k])
        change(src, 104, 0, "1e-324"); change(src, 112, 0, "1")
        raw = read(src); data = bytearray(src.read_bytes())
        values = [11, 12, 13, 21] if k == 0 else [14, 15, 16, 22]
        data[raw["hs"]:raw["hs"] + 8] = b"".join(v.to_bytes(2, "little", signed=True) for v in values)
        src.write_bytes(data)
    sources = [read(src) for src in paths]; hashes = [sha(src) for src in paths]
    original = annotations(sources[0]) + [dict(v, record=1, onset=onset) for v, onset in zip(annotations(sources[1]), ["+1", "+2"], strict=True)]
    expected_points = {s: [(k, j, v, t + F(3, 2) * k) for k, raw in enumerate(sources) for _, j, v, t in raw["points"][s]] for s in sources[0]["ordinary"]}
    rows, products = [], []
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            bridgeSha256=sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js"),
            oracle="Original fixed-width TAL/calibration bytes and Fraction append/seam sample enumeration",
            inputs=[dict(path=str(path), sha256=digest) for path, digest in zip(paths, hashes, strict=True)], commands=rows, products=products,
            expectedEpoch=dict(digital=[[13, 14], [22]], times=[["1", "3/2"], ["3/2"]], annotationRecord=1), confirmedDefects=[]), indent=2), encoding="utf-8")
    def run(name, argv, options):
        params = work / (name + ".json"); params.write_text(json.dumps(options), encoding="utf-8")
        cmd = ["node", str(ROOT / "tools/edf.mjs"), *map(str, argv), str(params)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr); save()
        assert result.returncode == 0, row
        return json.loads(row["stdout"])
    def verify(path, expected):
        got = read(path)
        assert annotations(got) == expected and got["starts"] == [F(0), F(3, 2)]
        assert got["duration"] == F(3, 2) and got["clock"] == sources[0]["clock"] and got["nr"] == 2 and got["ns"] == 4
        for s in sources[0]["ordinary"]:
            assert got["points"][s] == expected_points[s]
            for k, source in enumerate(sources):
                assert got["blocks"][k][s] == source["blocks"][0][s]
                assert all(got["columns"][c][s] == source["columns"][c][s] for c in range(10))
        assert got["columns"][3][0] == b"1e-324  "
        products.append(dict(path=str(path), sha256=sha(path), ordinarySamplesPreserved=8, calibrationBytesPreserved=True, annotationIdentityPreserved=True))
        save(); return got
    joined = work / "joined.edf"
    run("append", ["append", *paths, joined], dict(offset="1.5"))
    verify(joined, original)
    query = dict(start="1.25", end="1.75")
    found = run("query", ["annotations-window", joined], query)
    assert [v["annotation_index"] for v in found] == [0, 2]
    assert [v["annotation"] for v in found] == [original[0], original[2]]
    target = dict(found[1]["annotation"], text="reviewed-right")
    out = work / "edited.edf"
    run("text-update", ["annotation-update", joined, out], dict(index=found[1]["annotation_index"], annotation=target))
    verify(out, [*original[:2], target, original[3]])
    fresh = run("requery", ["annotations-window", out], query)
    assert [v["annotation_index"] for v in fresh] == [0, 2] and fresh[1]["annotation"] == target
    epoch = run("epoch", ["epoch", out], dict(annotation=fresh[1]["annotation_index"], signals=[0, 1], before="0", after="0", max_samples=3))
    assert epoch["annotation"] == target and epoch["complete"] and epoch["samples"] == 3
    assert F(epoch["start"]) == 1 and F(epoch["end"]) == 2
    for s, window in enumerate(epoch["channels"]):
        expected = [(r, j, v, t) for r, j, v, t in expected_points[s] if 1 <= t < 2]
        assert [(v["record"], v["sample"], v["digital"], F(v["time_numerator"]) / F(v["time_denominator"])) for v in window["samples"]] == expected
        assert not window["gaps"]
    assert [sha(src) for src in paths] == hashes; save(True)
    print(json.dumps(dict(status="passed", calls=len(rows), products=len(products), confirmedDefects=[])))


if __name__ == "__main__":
    main()
