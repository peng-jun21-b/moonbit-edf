"""Regression for byte-exact empty file edits, after normal input validation.

Synthetic fixed-width inputs (MIT), independent of MoonEDF's writer. Choose a
new --output after building the JS bridge. No downloads/extra dependencies.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
h = runpy.run_path(str(ROOT / "tools/check-append.py"))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    source = work / "unknown.edf"; h["make"](source, "edf", [2, 1], ["+0", "+1"])
    data = bytearray(source.read_bytes()); data[236:244] = h["field"](-1, 8); source.write_bytes(data)
    padded = work / "padded.edf"; known = bytearray(data); known[236:244] = b"00000002"; padded.write_bytes(known)
    invalid = work / "truncated.edf"; invalid.write_bytes(data[:-1])
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    inputs = [dict(path=str(p), sha256=sha(p)) for p in [source, padded, invalid]]
    options = work / "empty.json"; options.write_text('{"indices":[]}')
    rows, products = [], []
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            bridgeSha256=sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js"), inputs=inputs,
            commands=rows, products=products, checkedInvalidPaths=sum(v["exitCode"] == 2 for v in rows)), indent=2), encoding="utf-8")
    for src in [source, padded, invalid]:
        out = work / (src.stem + "-output.edf")
        cmd = ["node", str(ROOT / "tools/edf.mjs"), "annotations-remove", str(src), str(out), str(options)]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=src.stem, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
        rows.append(row); save()
        (work / (src.stem + ".stdout")).write_bytes(result.stdout); (work / (src.stem + ".stderr")).write_bytes(result.stderr)
        if src == invalid:
            assert result.returncode == 2 and "Invalid(" in row["stderr"] and not out.exists(), row
        else:
            assert result.returncode == 0 and out.read_bytes() == src.read_bytes(), row
            products.append(dict(path=str(out), sha256=sha(out), byteIdentical=True, recordField=out.read_bytes()[236:244].decode()))
        assert sha(src) == next(v["sha256"] for v in inputs if v["path"] == str(src))
    save(True)
    print(json.dumps(dict(status="passed", calls=len(rows), products=len(products), checkedInvalidPaths=1)))


if __name__ == "__main__":
    main()
