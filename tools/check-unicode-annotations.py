"""One UTF-8 TAL -> JSON edit -> exact-text file removal -> epoch (MIT).

Build the bridge and choose a new --output. Inputs use original fixed-width
bytes, not MoonEDF's writer; no downloads or extra dependencies.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, read = h["make"], h["read_raw"]
annotations = runpy.run_path(str(ROOT / "tools/check-annotation-query.py"))["original_annotations"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    a = '\u00e9\U0001f642,\t"quoted"\r\n'; b = 'e\u0301\U0001f642,\t"quoted"\r\n'; updated = '\ufeff' + a
    assert a != b and a.encode() != b.encode() and unicodedata.normalize("NFC", b) == a
    src = work / "unicode.edf"
    make(src, "edf", [4, 2], ["+0"], events={(0, 1): [("+0.5", None, "other")]})
    raw = read(src); data = bytearray(src.read_bytes())
    data[raw["hs"]:raw["hs"] + 12] = b"".join(v.to_bytes(2, "little", signed=True) for v in [10, 20, 30, 40, 100, 200])
    payload = b"+0\x14\x14\0+0.25\x150.5\x14" + a.encode() + b"\x14" + b.encode() + b"\x14\0"
    at = raw["hs"] + 12; data[at:at + 256] = payload.ljust(256, b"\0")
    src.write_bytes(data); raw = read(src); original = annotations(raw); source_hash = sha(src)
    assert [v["text"] for v in original] == [a, b, "other"]
    rows, products = [], []
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            bridgeSha256=sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js"),
            oracle="Original UTF-8 TAL bytes, code-point identity and Fraction sample clocks",
            inputs=[dict(path=str(src), sha256=source_hash)], textCase=dict(composed=a, decomposed=b, updated=updated, nfcEquivalent=True),
            commands=rows, products=products, confirmedDefects=[]), indent=2), encoding="utf-8")
    def run(name, argv, options=None, example=False):
        if options is not None:
            params = work / (name + ".json"); params.write_text(json.dumps(options), encoding="utf-8"); argv = [*argv, params]
        cmd = ["node", str(ROOT / ("examples/remove-window.mjs" if example else "tools/edf.mjs")), *map(str, argv)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr); save()
        assert result.returncode == 0, row
        return json.loads(row["stdout"])
    def verify(path, expected):
        got = read(path)
        assert annotations(got) == expected
        assert got["starts"] == raw["starts"] and got["duration"] == raw["duration"] and got["clock"] == raw["clock"]
        assert got["ns"] == raw["ns"] and got["nr"] == raw["nr"]
        for s in raw["ordinary"]:
            assert got["points"][s] == raw["points"][s]
            assert all(got["columns"][c][s] == raw["columns"][c][s] for c in range(10))
            assert got["blocks"][0][s] == raw["blocks"][0][s]
        products.append(dict(path=str(path), sha256=sha(path), exactUnicodeMetadata=True, ordinarySamplesPreserved=6, annotations=len(expected)))
        save(); return got
    found = run("query", ["annotations-window", src], dict(start="0.25", end="0.75"))
    assert [v["annotation_index"] for v in found] == [0, 1, 2]
    assert [v["annotation"] for v in found] == original
    target = dict(found[0]["annotation"], text=updated)
    edited = work / "updated.edf"
    run("update", ["annotation-update", src, edited], dict(index=found[0]["annotation_index"], annotation=target))
    verify(edited, [target, *original[1:]])
    out = work / "removed.edf"
    response = run("exact-file-remove", [edited, out, "0.25", "0.75", updated], example=True)
    assert response == dict(output=str(out), matched=3, removed=1, remaining_in_window=2)
    verify(out, original[1:])
    fresh = run("requery", ["annotations-window", out], dict(start="0.25", end="0.75"))
    assert [v["annotation"] for v in fresh] == original[1:] and fresh[0]["annotation_index"] == 0
    epoch = run("epoch", ["epoch", out], dict(annotation=fresh[0]["annotation_index"], signals=[0, 1], before="0", after="0", max_samples=3))
    assert epoch["annotation"] == original[1] and epoch["complete"] and epoch["samples"] == 3
    for s, window in enumerate(epoch["channels"]):
        expected = [(r, j, v, t) for r, j, v, t in raw["points"][s] if F("0.25") <= t < F("0.75")]
        assert [(v["record"], v["sample"], v["digital"], F(v["time_numerator"]) / F(v["time_denominator"])) for v in window["samples"]] == expected
    assert sha(src) == source_hash; save(True)
    print(json.dumps(dict(status="passed", calls=len(rows), products=len(products), confirmedDefects=[])))


if __name__ == "__main__":
    main()
