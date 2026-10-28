"""Independent legal-definition replacement and point-record consumers (MIT).

Use a new --output after building the JS bridge. Original fixed-width inputs
and Fraction expectations do not use MoonEDF's writer or extra dependencies.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, read = h["make"], h["read_raw"]
original_annotations = runpy.run_path(str(ROOT / "tools/check-annotation-query.py"))["original_annotations"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    rows, inputs, products, rejected = [], [], [], []
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            python=platform.python_version(), bridgeSha256=sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js"),
            oracle="Original TAL/point-record bytes, original-index subtraction and Fraction clocks",
            commands=rows, inputs=inputs, products=products, checkedErrors=rejected, confirmedDefects=[]), indent=2), encoding="utf-8")
    def run(name, command, options):
        params = work / (name + ".json"); params.write_text(json.dumps(options), encoding="utf-8")
        cmd = ["node", str(ROOT / "tools/edf.mjs"), *map(str, command), str(params)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr); save()
        return row
    def good(row):
        assert row["exitCode"] == 0, row
        return json.loads(row["stdout"])
    def product(path, raw, removed):
        got = read(path)
        assert original_annotations(got) == [v for i, v in enumerate(original_annotations(raw)) if i not in set(removed)]
        assert got["starts"] == raw["starts"] and got["duration"] == raw["duration"] and got["clock"] == raw["clock"]
        assert got["nr"] == raw["nr"] and got["ns"] == raw["ns"]
        for s in raw["ordinary"]:
            assert got["points"][s] == raw["points"][s]
            assert all(got["columns"][c][s] == raw["columns"][c][s] for c in range(10))
            assert all(got["blocks"][r][s] == raw["blocks"][r][s] for r in range(raw["nr"]))
        products.append(dict(path=str(path), sha256=sha(path), events=len(got["events"]), ordinarySamples=sum(len(v) for v in got["points"].values())))
        return got

    metadata = work / "definitions.edf"
    make(metadata, "edf", [], ["+0.25", "+2.25"], mode="D", duration="0", events={
        (0, 0): [("+0.25", None, "A"), ("+0.25", None, "B"), ("+0.25", "1", "stage")],
        (0, 1): [("+0.25", None, "secondary")],
        (1, 0): [("+2.25", None, "C"), ("+2.25", None, "D"), ("+2.5", "0.25", "stage")],
        (1, 1): [("+2.25", None, "secondary")],
    })
    raw = read(metadata); data = bytearray(metadata.read_bytes())
    for r, stamp, first, second in [(0, "+0.25", "A", "B"), (1, "+2.25", "C", "D")]:
        payload = (stamp + "\x14\x14" + first + "\x14" + second + "\x14\0").encode()
        payload += (stamp + "\x151\x14stage\x14\0").encode() if r == 0 else b"+2.5\x150.25\x14stage\x14\0"
        at = raw["hs"] + r * sum(raw["per"]) * 2
        data[at:at + 256] = payload.ljust(256, b"\0")
    metadata.write_bytes(data); raw = read(metadata)
    inputs.append(dict(path=str(metadata), sha256=sha(metadata)))
    matches = good(run("metadata-query", ["annotations-window", metadata], dict(start="0.25", end="2.5")))
    chosen = [v["annotation_index"] for v in matches if v["annotation"]["text"] in ["A", "C"]]
    assert chosen == [0, 4]
    edited = work / "definitions-edited.edf"
    good(run("metadata-remove", ["annotations-remove", metadata, edited], dict(indices=[4, 0, 4])))
    got = product(edited, raw, chosen)
    firsts = []
    for block in got["blocks"]:
        first_tal = block[0].split(b"\0")[0].split(b"\x14")
        assert first_tal[1] == b"" and first_tal[2] in [b"B", b"D"]
        firsts.append(first_tal[2])
    assert firsts == [b"B", b"D"]
    fresh = good(run("metadata-requery", ["annotations-window", edited], dict(start="0.25", end="2.5")))
    assert [v["annotation"]["text"] for v in fresh] == ["B", "stage", "secondary", "D", "secondary"]
    assert [v["annotation_index"] for v in fresh] == [0, 1, 2, 3, 5]
    invalid = work / "definitions-invalid.edf"
    row = run("metadata-lost-primary", ["annotations-remove", edited, invalid], dict(indices=[fresh[0]["annotation_index"]]))
    assert row["exitCode"] == 2 and "annotation-only record needs its defining event" in row["stderr"] and not invalid.exists(), row
    rejected.append(dict(name=row["name"], checkedInvalid=True, noPartialOutput=True))

    points = work / "points.bdf"
    make(points, "bdf", [1, 1], ["+0.25", "+2.25", "+4.25"], mode="D", duration="0", events={
        (0, 0): [("+0.25", None, "left")], (1, 1): [("+2.25", "0", "target")], (2, 0): [("+4.25", None, "right")],
    })
    raw = read(points); data = bytearray(points.read_bytes())
    for r, values in enumerate([(111, -222), (333, -444), (555, -666)]):
        at = raw["hs"] + r * sum(raw["per"]) * 3
        data[at:at + 6] = b"".join(v.to_bytes(3, "little", signed=True) for v in values)
    points.write_bytes(data); raw = read(points)
    inputs.append(dict(path=str(points), sha256=sha(points)))
    matches = good(run("points-query", ["annotations-window", points], dict(start="0.25", end="4.5")))
    chosen = [v["annotation_index"] for v in matches if v["annotation"]["text"] != "target"]
    assert chosen == [0, 2]
    edited = work / "points-edited.bdf"
    good(run("points-remove", ["annotations-remove", points, edited], dict(indices=[2, 0])))
    product(edited, raw, chosen)
    fresh = good(run("points-requery", ["annotations-window", edited], dict(start="2.25", end="2.35")))
    assert len(fresh) == 1 and fresh[0]["annotation_index"] == 0 and fresh[0]["annotation"]["signal"] == 3
    options = dict(annotation=fresh[0]["annotation_index"], signals=[0, 1], before="0", after="0.1", allow_partial=True, max_samples=2)
    epoch = good(run("points-epoch", ["epoch", edited], options))
    assert epoch["samples"] == 2 and not epoch["complete"]
    for s, value in enumerate([333, -444]):
        samples = epoch["channels"][s]["samples"]
        assert [(v["record"], v["sample"], v["digital"], F(v["time_numerator"]) / F(v["time_denominator"])) for v in samples] == [(1, 0, value, F("2.25"))]
        assert epoch["channels"][s]["gaps"] == [dict(after_record=1, start="2.25", end="2.35")]
    row = run("points-strict-epoch", ["epoch", edited], dict(options, allow_partial=False))
    assert row["exitCode"] == 2 and "Invalid(" in row["stderr"] and not row["stdout"], row
    rejected.append(dict(name=row["name"], checkedInvalid=True, noPartialResult=True))
    assert all(sha(Path(v["path"])) == v["sha256"] for v in inputs)
    save(True)
    print(json.dumps(dict(status="passed", calls=len(rows), products=len(products), checkedErrors=len(rejected), confirmedDefects=[])))


if __name__ == "__main__":
    main()
