"""One raw BDF interleaved-channel select -> query -> edit -> epoch (MIT).

Build the bridge; choose a new --output. Reference inputs are original byte
fixtures, not MoonEDF writer products. No downloads or extra dependencies.
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
    src = work / "interleaved.bdf"
    make(src, "bdf", [4, 2], ["+0", "+1"], events={
        (0, 0): [("+0.25", "0.5", "same")], (0, 1): [("+0.25", None, "same")],
        (1, 0): [("+1.25", "0.5", "later")], (1, 1): [("+1.5", None, "same")],
    })
    raw = read(src); order = [0, 2, 1, 3]; data = bytearray(raw["data"][:raw["hs"]])
    for column, (base, width) in enumerate(h["COLUMNS"]):
        for s, old in enumerate(order):
            at = 256 + raw["ns"] * base + s * width
            data[at:at + width] = raw["columns"][column][old]
    for blocks in raw["blocks"]:
        for old in order:
            data.extend(blocks[old])
    src.write_bytes(data)
    change(src, 0, 0, "fast", 16); change(src, 0, 2, "slow", 16)
    change(src, 224, 1, "primary-ann", 32); change(src, 224, 3, "secondary-ann", 32)
    raw = read(src); data = bytearray(src.read_bytes())
    record_bytes = sum(raw["per"]) * 3
    for r, values in enumerate([(100000, -200000), (300000, -400000)]):
        at = raw["hs"] + r * record_bytes + sum(raw["per"][:2]) * 3
        data[at:at + 6] = b"".join(v.to_bytes(3, "little", signed=True) for v in values)
    src.write_bytes(data); raw = read(src); input_hash = sha(src)
    assert raw["ordinary"] == [0, 2] and raw["ann"] == [1, 3]
    rows, products = [], []
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            bridgeSha256=sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js"),
            oracle="Original interleaved header/payload bytes, signal identity mapping and Fraction sample clocks",
            inputs=[dict(path=str(src), sha256=input_hash)], commands=rows, products=products, confirmedDefects=[]), indent=2), encoding="utf-8")
    def run(name, argv, options=None):
        if options is not None:
            path = work / (name + ".json"); path.write_text(json.dumps(options)); argv = [*argv, path]
        cmd = ["node", str(ROOT / "tools/edf.mjs"), *map(str, argv)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr); save()
        assert result.returncode == 0, row
        return json.loads(row["stdout"])
    def verify(path, expected_events):
        got = read(path)
        assert got["nr"] == raw["nr"] and got["starts"] == raw["starts"] and got["duration"] == raw["duration"]
        assert got["clock"] == raw["clock"] and got["ordinary"] == [0] and got["ann"] == [1, 2]
        assert got["points"][0] == raw["points"][2]
        assert all(got["columns"][c][0] == raw["columns"][c][2] for c in range(10))
        assert all(got["blocks"][r][0] == raw["blocks"][r][2] for r in range(2))
        assert got["columns"][9][1:] == [raw["columns"][9][1], raw["columns"][9][3]]
        assert annotations(got) == expected_events
        products.append(dict(path=str(path), sha256=sha(path), ordinarySamplesPreserved=4, annotationChannels=2, exactIdentityMap=True))
        save(); return got
    info = run("inspect", ["inspect", src]); assert info["signals"][2]["label"] == "slow"
    selected = work / "selected.bdf"; run("select", ["select", src, selected], dict(signals=[2]))
    mapping = {1: 1, 3: 2}
    expected = [dict(a, signal=mapping[a["signal"]]) for a in annotations(raw)]
    got = verify(selected, expected)
    for s, old in [(1, 1), (2, 3)]:
        assert all(got["columns"][c][s] == raw["columns"][c][old] for c in range(10))
        assert all(got["blocks"][r][s] == raw["blocks"][r][old] for r in range(2))
    found = run("query", ["annotations-window", selected], dict(start="0.25", end="0.75"))
    assert [(v["annotation_index"], v["annotation"]["signal"], v["annotation"]["text"]) for v in found] == [(0, 1, "same"), (1, 2, "same")]
    edited = work / "edited.bdf"; run("remove-secondary", ["annotations-remove", selected, edited], dict(indices=[found[1]["annotation_index"]]))
    verify(edited, [a for i, a in enumerate(expected) if i != found[1]["annotation_index"]])
    fresh = run("requery", ["annotations-window", edited], dict(start="0.25", end="0.75"))
    assert len(fresh) == 1 and fresh[0]["annotation_index"] == 0 and fresh[0]["annotation"]["signal"] == 1
    epoch = run("epoch", ["epoch", edited], dict(annotation=fresh[0]["annotation_index"], signals=[0], before="0", after="0", max_samples=1))
    assert epoch["complete"] and epoch["samples"] == 1 and epoch["channels"][0]["label"] == "slow"
    assert [(v["record"], v["sample"], v["digital"], F(v["time_numerator"]) / F(v["time_denominator"])) for v in epoch["channels"][0]["samples"]] == [(0, 1, -200000, F("0.5"))]
    assert sha(src) == input_hash; save(True)
    print(json.dumps(dict(status="passed", calls=len(rows), products=len(products), confirmedDefects=[])))


if __name__ == "__main__":
    main()
