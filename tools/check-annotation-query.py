"""Independent raw-byte/Fraction checks for event queries and consumers (MIT).

Build the JS bridge first. A new --output preserves inputs and CLI receipts;
--resume reuses recorded calls after a harness-only correction if the bridge
and retained inputs/products are unchanged. No downloads or extra dependencies.
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
helpers = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, read = helpers["make"], helpers["read_raw"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def original_annotations(raw):
    events = []
    for r, blocks in enumerate(raw["blocks"]):
        for s in raw["ann"]:
            for tal in filter(None, blocks[s].split(b"\0")):
                clock, *texts = tal.split(b"\x14")
                terms = clock.split(b"\x15")
                for text in filter(None, texts):
                    event = dict(record=r, signal=s, onset=terms[0].decode(), text=text.decode("utf-8"))
                    if len(terms) == 2:
                        event["duration"] = terms[1].decode()
                    events.append(event)
    return events


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
    cache = {v["name"]: v for v in rows}
    queries, errors, inputs, products, reused = [], [], [], [], []

    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress",
            python=platform.python_version(), bridgeSha256=bridge_hash,
            oracle="Original fixed-width inputs; Fraction point/positive-duration interval intersections",
            commands=rows, queries=queries, checkedErrors=errors, inputs=inputs,
            products=products, reusedCommands=reused), indent=2), encoding="utf-8")

    def run(name, arguments, output=None):
        command = ["node", str(ROOT / "tools/edf.mjs"), *map(str, arguments)]
        if name in cache:
            row = cache[name]
            assert row["command"] == command
            if row.get("outputSha256"):
                assert output and sha(output) == row["outputSha256"]
            reused.append(name)
            return row
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=20)
        row = dict(name=name, command=command, exitCode=result.returncode,
                   stdout=result.stdout.decode(), stderr=result.stderr.decode())
        if output and output.exists():
            row["outputSha256"] = sha(output)
        rows.append(row)
        (work / (name + ".stdout")).write_bytes(result.stdout)
        (work / (name + ".stderr")).write_bytes(result.stderr)
        save()
        return row

    def source(name, fmt, per, starts, **kwargs):
        path = work / (name + "." + fmt)
        if path.exists():
            assert args.resume
        else:
            make(path, fmt, per, starts, **kwargs)
        item = dict(path=str(path), sha256=sha(path))
        if previous:
            old = next(v for v in previous["inputs"] if v["path"] == str(path))
            assert old == item
        inputs.append(item)
        return path, read(path)

    def oracle(raw, lower, upper, durations):
        lower, upper = F(lower), F(upper)
        result = []
        for index, (record, signal, onset, duration, text) in enumerate(raw["events"]):
            span = F(duration) if durations and duration is not None else F(0)
            if lower != upper and ((onset < upper and onset + span > lower) if span > 0
                                   else lower <= onset < upper):
                result.append((index, record, signal, onset, duration, text))
        return result

    def query(name, src, raw, lower, upper, *, durations=True, budget=None, numeric=False):
        options = work / (name + ".json")
        value = dict(start=lower, end=upper, include_duration=durations)
        if budget is not None:
            value["max_annotations"] = budget
        text = json.dumps(value)
        if numeric:
            text = text.replace(json.dumps(lower), lower).replace(json.dumps(upper), upper)
        options.write_text(text, encoding="utf-8")
        expected = oracle(raw, lower, upper, durations)
        row = run(name, ["annotations-window", src, options])
        assert row["exitCode"] == 0, row
        actual = json.loads(row["stdout"])
        got = [(v["annotation_index"], a["record"], a["signal"], F(a["onset"]),
                a.get("duration"), a["text"]) for v in actual for a in [v["annotation"]]]
        assert got == expected, (got, expected)
        original = original_annotations(raw)
        for match in actual:
            assert match["annotation"] == original[match["annotation_index"]]
        queries.append(dict(name=name, expectedIndices=[v[0] for v in expected],
                            matches=len(actual), originalIdentityAndDuration=True, numericLexemes=numeric))
        save()
        print("verified", name, flush=True)
        return actual

    events = {
        (0, 0): [("-0.5", "0.5", "ends-at-zero"), ("+0", None, "same"),
                 ("+0.25", "0.75", "stage"), ("+0.5", "0", "zero"),
                 ("+0.333333333333333333333", None, "same")],
        (0, 1): [("+0.333333333333333333334", None, "same"), ("+0.75", "1.5", "cross-gap")],
        (1, 0): [("+0.125", "0.25", "stored-late"),
                 ("+2.000000000000000000001", "0.499999999999999999999", "same")],
        (1, 1): [("+2.25", None, "same")],
    }
    for fmt in ["edf", "bdf"]:
        src, raw = source("source-" + fmt, fmt, [4, 2], ["+0", "+2"], mode="D", events=events)
        assert len(raw["events"]) == 10
        vectors = [("left", "0", "0.5", True), ("point", "0.5", "0.75", True),
                   ("onset-only", "0.5", "0.75", False), ("negative", "-0.5", "0", True),
                   ("gap", "1", "2", True), ("third", "1/3", "0.34", True),
                   ("third-onset", "1/3", "0.34", False), ("empty", "0", "0", True),
                   ("outside", "3", "4", True), ("touching", "2.25", "2.5", True)]
        for label, lo, hi, durations in vectors:
            query(label + "-" + fmt, src, raw, lo, hi, durations=durations)
        tiny = query("numeric-" + fmt, src, raw, "2.0000000000000000000005",
                     "2.0000000000000000000015", durations=False, numeric=True)
        assert len(tiny) == 1 and tiny[0]["annotation_index"] == 8
        count = len(oracle(raw, "0", "1", True))
        query("exact-budget-" + fmt, src, raw, "0", "1", budget=count)
        chosen = tiny[0]
        options = work / ("epoch-" + fmt + ".json")
        options.write_text(json.dumps(dict(annotation=chosen["annotation_index"], signals=[0, 1],
            before="0", after="0", max_samples=1)))
        row = run("epoch-" + fmt, ["epoch", src, options]); assert row["exitCode"] == 0, row
        epoch = json.loads(row["stdout"])
        assert epoch["annotation"] == chosen["annotation"] and epoch["samples"] == 1 and epoch["complete"]
        assert [(v["record"], v["sample"], v["digital"], F(v["time_numerator"]) / F(v["time_denominator"]))
                for v in epoch["channels"][0]["samples"]] == [(1, 1, raw["points"][0][5][2], F("2.25"))]
        assert epoch["channels"][1]["samples"] == []
        target = dict(chosen["annotation"], text="reviewed")
        options = work / ("update-" + fmt + ".json")
        options.write_text(json.dumps(dict(index=chosen["annotation_index"], annotation=target)))
        out = work / ("edited." + fmt)
        row = run("update-" + fmt, ["annotation-update", src, out, options], out)
        assert row["exitCode"] == 0, row
        edited = read(out)
        assert edited["events"][8] == (*raw["events"][8][:4], "reviewed")
        assert edited["events"][:8] + edited["events"][9:] == raw["events"][:8] + raw["events"][9:]
        for s in raw["ordinary"]:
            assert edited["points"][s] == raw["points"][s]
            assert all(edited["columns"][c][s] == raw["columns"][c][s] for c in range(10))
        query("edited-" + fmt, out, edited, "2.0000000000000000000005",
              "2.0000000000000000000015", durations=False)
        products.append(dict(path=str(out), sha256=sha(out), index=8,
                             selectedText="reviewed", ordinarySamplesPreserved=12))
        if fmt == "edf":
            row = run("legacy-annotations", ["annotations", src])
            assert row["exitCode"] == 0 and len(json.loads(row["stdout"])) == 10
            for label, value, kind in [
                ("reverse", dict(start="2", end="1"), "Invalid("),
                ("syntax", dict(start="bad", end="1"), "Invalid("),
                ("denominator", dict(start="1/0", end="1"), "Invalid("),
                ("zero-budget", dict(start="0", end="1", max_annotations=0), "Invalid("),
                ("negative-budget", dict(start="0", end="1", max_annotations=-1), "Invalid("),
                ("limit", dict(start="0", end="1", max_annotations=count - 1), "Limit("),
            ]:
                options = work / (label + ".json"); options.write_text(json.dumps(value))
                row = run(label, ["annotations-window", src, options])
                assert row["exitCode"] == 2 and kind in row["stderr"] and not row["stdout"], row
                errors.append(dict(name=label, checkedError=kind.removesuffix("("), noPartialResult=True))
    plain, raw = source("plain", "edf", [1], ["+0"], mode="plain")
    query("plain", plain, raw, "-1", "3")
    metadata, raw = source("metadata", "edf", [], ["+0", "+2"], mode="D", duration="0",
        events={(0, 0): [("+0", None, "origin"), ("+0", "2", "stage")],
                (1, 0): [("+2", None, "marker")]})
    query("metadata-span", metadata, raw, "1", "2")
    query("metadata-point", metadata, raw, "2", "3")
    assert all(sha(Path(v["path"])) == v["sha256"] for v in inputs)
    save(True)
    print(json.dumps(dict(status="passed", cliChecks=len(rows), queryChecks=len(queries),
                          checkedErrors=len(errors), inputsUnchanged=len(inputs), products=len(products))))


if __name__ == "__main__":
    main()
