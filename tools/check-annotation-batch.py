"""Independent raw-byte query -> batch delete -> re-query consumers (MIT).

Build the JS bridge and choose a new --output. No downloads/extra dependencies.
--resume reuses retained calls after harness-only corrections if the bridge,
inputs and products have the same hashes. Inputs never use MoonEDF's writer.
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
make, read, change = h["make"], h["read_raw"], h["change"]
original_annotations = runpy.run_path(str(ROOT / "tools/check-annotation-query.py"))["original_annotations"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases")
    bridge_hash = sha(ROOT / "_build/js/release/build/cmd/bridge/bridge.js")
    previous = json.loads(args.output.read_text(encoding="utf-8")) if args.resume else None
    if previous:
        assert previous["bridgeSha256"] == bridge_hash
    else:
        work.mkdir()
    rows = previous["commands"] if previous else []
    cached = {v["name"]: v for v in rows}
    inputs, products, failures, reused = [], [], [], []

    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            python=platform.python_version(), bridgeSha256=bridge_hash,
            oracle="Original fixed-width/TAL bytes, original-index set subtraction, Fraction samples",
            commands=rows, inputs=inputs, products=products, checkedErrors=failures,
            reusedCommands=reused), indent=2), encoding="utf-8")

    def run(name, arguments, out=None, example=False):
        entry = ROOT / ("examples/remove-window.mjs" if example else "tools/edf.mjs")
        command = ["node", str(entry), *map(str, arguments)]
        if name in cached:
            row = cached[name]; assert row["command"] == command
            if row.get("outputSha256"):
                assert out and sha(out) == row["outputSha256"]
            reused.append(name)
            return row
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=command, exitCode=result.returncode,
                   stdout=result.stdout.decode(), stderr=result.stderr.decode())
        if out and out.exists():
            row["outputSha256"] = sha(out)
        rows.append(row)
        (work / (name + ".stdout")).write_bytes(result.stdout)
        (work / (name + ".stderr")).write_bytes(result.stderr)
        save()
        return row

    def source(name, fmt, per, starts, grouped=False, **kwargs):
        path = work / (name + "." + fmt)
        if path.exists():
            assert args.resume
        else:
            make(path, fmt, per, starts, **kwargs)
            if grouped:
                raw = read(path); width = raw["width"]; cap = 128 * width
                data = bytearray(path.read_bytes()); at = raw["hs"] + sum(per) * width
                tal = b"+0\x14\x14\0+0.25\x150.5\x14drop\x14" + "保留".encode("utf-8") + b"\x14\0+0.5\x14keep\x14\0"
                data[at:at + cap] = tal.ljust(cap, b"\0"); path.write_bytes(data)
                change(path, 104, 0, "1e-324"); change(path, 112, 0, "1")
        item = dict(path=str(path), sha256=sha(path))
        if previous:
            assert item == next(v for v in previous["inputs"] if v["path"] == str(path))
        inputs.append(item)
        return path, read(path)

    def verify_product(name, out, raw, indices, *, noop=False):
        got = read(out)
        excluded = set(indices)
        expected = [v for i, v in enumerate(original_annotations(raw)) if i not in excluded]
        assert original_annotations(got) == expected
        assert got["starts"] == raw["starts"] and got["duration"] == raw["duration"]
        assert got["clock"] == raw["clock"] and got["ns"] == raw["ns"] and got["nr"] == raw["nr"]
        for s in raw["ordinary"]:
            assert got["points"][s] == raw["points"][s]
            assert all(got["columns"][c][s] == raw["columns"][c][s] for c in range(10))
            assert all(got["blocks"][r][s] == raw["blocks"][r][s] for r in range(raw["nr"]))
        if noop:
            assert got["data"] == raw["data"]
        products.append(dict(name=name, path=str(out), sha256=sha(out), removedIndices=sorted(excluded),
            eventsRemaining=len(expected), ordinarySamples=sum(len(v) for v in got["points"].values()),
            rawOrdinaryColumnsAndBlocksPreserved=True, noopBytesIdentical=noop))
        save(); print("verified", name, flush=True)
        return got

    def transform(name, src, raw, indices, *, legacy=False):
        options = work / (name + ".json")
        options.write_text(json.dumps(dict(index=indices[0]) if legacy else dict(indices=indices)))
        out = work / (name + (".edf" if raw["width"] == 2 else ".bdf"))
        row = run(name, ["annotation-remove" if legacy else "annotations-remove", src, out, options], out)
        assert row["exitCode"] == 0, row
        got = verify_product(name, out, raw, indices, noop=not indices)
        return out, got

    def query(name, path, lower, upper):
        options = work / (name + ".json"); options.write_text(json.dumps(dict(start=lower, end=upper)))
        row = run(name, ["annotations-window", path, options]); assert row["exitCode"] == 0, row
        return json.loads(row["stdout"])

    for fmt in ["edf", "bdf"]:
        src, raw = source("source-" + fmt, fmt, [4, 2], ["+0", "+2"], grouped=True, mode="D", events={
            (0, 1): [("+0.25", "0.5", "drop")],
            (1, 0): [("+2.000000000000000000001", "0.499999999999999999999", "drop"), ("+2.5", None, "keep")],
            (1, 1): [("+0.125", None, "keep-late")],
        })
        assert len(raw["events"]) == 7
        matches = query("query-" + fmt, src, "0.25", "2.5")
        chosen = [v["annotation_index"] for v in matches if v["annotation"]["text"] == "drop"]
        assert chosen == [0, 3, 4]
        out, got = transform("batch-" + fmt, src, raw, [4, 0, 3, 0])
        fresh = query("fresh-" + fmt, out, "2.5", "2.75")
        assert len(fresh) == 1 and fresh[0]["annotation_index"] == 2
        assert fresh[0]["annotation"]["text"] == "keep"
        options = work / ("epoch-" + fmt + ".json")
        options.write_text(json.dumps(dict(annotation=fresh[0]["annotation_index"], signals=[0, 1], before="0", after="0.25", max_samples=2)))
        row = run("epoch-" + fmt, ["epoch", out, options]); assert row["exitCode"] == 0, row
        epoch = json.loads(row["stdout"]); assert epoch["complete"] and epoch["samples"] == 2
        for s, window in enumerate(epoch["channels"]):
            want = [(r, j, v, t) for r, j, v, t in raw["points"][s] if F("2.5") <= t < F("2.75")]
            assert [(v["record"], v["sample"], v["digital"], F(v["time_numerator"]) / F(v["time_denominator"])) for v in window["samples"]] == want
        transform("noop-" + fmt, src, raw, [])
        transform("all-" + fmt, src, raw, list(range(7)))
        single, _ = transform("single-batch-" + fmt, src, raw, [2])
        legacy, _ = transform("single-legacy-" + fmt, src, raw, [2], legacy=True)
        assert single.read_bytes() == legacy.read_bytes()
        if fmt == "edf":
            for label, value, kind in [
                ("mixed", dict(indices=[0, 7]), "Invalid("),
                ("negative", dict(indices=[0, -1]), "Invalid("),
                ("max-int", dict(indices=[2147483647]), "Invalid("),
                ("not-array", dict(indices="all"), "JsonDecodeError("),
                ("missing", {}, "missing option: indices"),
            ]:
                options = work / (label + ".json"); options.write_text(json.dumps(value))
                rejected = work / (label + ".edf")
                row = run(label, ["annotations-remove", src, rejected, options])
                assert row["exitCode"] == 2 and (kind is None or kind in row["stderr"]) and not rejected.exists(), row
                assert not row["stdout"]
                failures.append(dict(name=label, checkedFailure=True, noPartialOutput=True))
            digest = sha(out)
            options = work / "existing.json"; options.write_text('{"indices":[0]}')
            row = run("existing-output", ["annotations-remove", src, out, options], out)
            assert row["exitCode"] == 2 and "output exists" in row["stderr"] and sha(out) == digest
            failures.append(dict(name="existing-output", checkedFailure=True, existingOutputUnchanged=True))
        else:
            example = work / "node-example.bdf"
            row = run("node-example", [src, example, "0.25", "2.5", "drop"], example, example=True)
            assert row["exitCode"] == 0, row
            assert json.loads(row["stdout"]) == dict(output=str(example), matched=5, removed=3, remaining_in_window=2)
            verify_product("node-example", example, raw, chosen)
            all_matches = work / "node-all-matches.bdf"
            row = run("node-all-matches", [src, all_matches, "0.25", "2.5"], all_matches, example=True)
            assert row["exitCode"] == 0, row
            assert json.loads(row["stdout"]) == dict(output=str(all_matches), matched=5, removed=5, remaining_in_window=0)
            verify_product("node-all-matches", all_matches, raw, [v["annotation_index"] for v in matches])
            no_matches = work / "node-no-selection.bdf"
            row = run("node-no-selection", [src, no_matches, "0.25", "2.5", "not-present"], no_matches, example=True)
            assert row["exitCode"] == 0, row
            assert json.loads(row["stdout"]) == dict(output=str(no_matches), matched=5, removed=0, remaining_in_window=5)
            verify_product("node-no-selection", no_matches, raw, [], noop=True)
            digest = sha(example)
            row = run("node-existing-output", [src, example, "0.25", "2.5", "drop"], example, example=True)
            assert row["exitCode"] == 2 and "EEXIST" in row["stderr"] and sha(example) == digest
            failures.append(dict(name="node-existing-output", checkedFailure=True, existingOutputUnchanged=True))
    plain, raw = source("plain", "edf", [2], ["+0"], mode="plain")
    transform("plain-noop", plain, raw, [])
    metadata, raw = source("metadata", "edf", [], ["+0", "+2"], mode="D", duration="0", events={
        (0, 0): [("+0", None, "origin"), ("+1", "0.5", "drop")],
        (1, 0): [("+2", None, "marker")],
    })
    transform("metadata-remove", metadata, raw, [1])
    for label, src, indices, reason in [
        ("plain-nonempty", plain, [0], "annotation index"),
        ("metadata-defining", metadata, [0, 1], "annotation-only record needs its defining event"),
    ]:
        options = work / (label + ".json"); options.write_text(json.dumps(dict(indices=indices)))
        out = work / (label + ".edf")
        row = run(label, ["annotations-remove", src, out, options])
        assert row["exitCode"] == 2 and reason in row["stderr"] and not out.exists(), row
        failures.append(dict(name=label, checkedFailure=True, noPartialOutput=True))
    assert all(sha(Path(v["path"])) == v["sha256"] for v in inputs)
    save(True)
    print(json.dumps(dict(status="passed", cliChecks=len(rows), products=len(products),
                          checkedErrors=len(failures), inputsUnchanged=len(inputs))))


if __name__ == "__main__":
    main()
