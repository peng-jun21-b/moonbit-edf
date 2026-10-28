"""Real CLI numeric-time regression with independent fixed-width/Fraction inputs.

--baseline records mismatches before repair; normal mode requires every check
to pass. Use --inputs PREVIOUS-cases to retain the exact original input bytes.
Only Python's standard library is required. All generated data are synthetic MIT.
"""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import io
import json
from pathlib import Path
import platform
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RAW = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, read_raw = RAW["make"], RAW["read_raw"]
sys.set_int_max_str_digits(0)


def render(template, numeric, **values):
    for key, value in values.items():
        template = template.replace("@" + key + "@", value if numeric else json.dumps(value))
    return template


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--only", help="Run only case names beginning with this prefix")
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    sources = {}
    for fmt in ["edf", "bdf"]:
        for label, starts in [("source", ["+0", "+1"]), ("tolerance", ["+0", "+1.000000000000000000001"])]:
            path = work / (label + "." + fmt)
            if args.inputs:
                path.write_bytes((args.inputs / path.name).read_bytes())
            else:
                make(path, fmt, [4, 2], starts, events={(0, 0): [("+0.5", None, "anchor")]})
            sources[label, fmt] = path
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.values()}
    rows = []
    def save(complete=False):
        mismatches = [v["name"] for v in rows if not v["matchedIndependentExpected"]]
        args.output.write_text(json.dumps(dict(status=("baseline_recorded" if args.baseline else "passed" if not mismatches else "failed") if complete else "in_progress",
            python=platform.python_version(), oracle="Original fixed-width bytes and Python Fraction; no MoonBit writer for source fixtures",
            sourceHashes=hashes, sourceDirectory=str(work), originalInputs=str(args.inputs) if args.inputs else None,
            checks=rows, mismatches=mismatches), indent=2), encoding="utf-8")
    def run(name, command, source, text, check=None, *, writes=False, error=None):
        if args.only and not name.startswith(args.only): return
        options = work / (name + ".json"); options.write_text(text, encoding="utf-8")
        product = work / (name + (".bdf" if source and str(source).endswith(".bdf") else ".edf"))
        argv = [command, str(product), str(options)] if command == "create" else [command, str(source), *([str(product)] if writes else []), str(options)]
        cmd = ["node", "--max-old-space-size=64", "--stack-size=512", str(ROOT / "tools/edf.mjs"), *argv]
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        row = dict(name=name, command=cmd, exitCode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode(),
                   options=str(options), product=str(product) if writes or command == "create" else None)
        (work / (name + ".stdout")).write_bytes(result.stdout); (work / (name + ".stderr")).write_bytes(result.stderr)
        try:
            if error is not None:
                assert result.returncode == 2 and error in row["stderr"] and not product.exists(), (result.returncode, row["stderr"])
            else:
                assert result.returncode == 0, row["stderr"]
                check(product if writes or command == "create" else row["stdout"])
            row["matchedIndependentExpected"] = True
        except AssertionError as exc:
            row["matchedIndependentExpected"] = False; row["mismatch"] = str(exc)
        rows.append(row); save()
        print(("MATCH " if row["matchedIndependentExpected"] else "MISMATCH ") + name, flush=True)

    lower, upper = "0.250000000000000000001", "0.750000000000000000001"
    before, after = "0.249999999999999999999", "0.250000000000000000001"
    threshold = "9.99999999999999999999e-22"
    assert F(threshold) < F("1e-21")
    for fmt in (["edf"] if args.baseline else ["edf", "bdf"]):
        source = sources["source", fmt]; raw = read_raw(source)
        expected = lambda s, lo=F(lower), hi=F(upper): [v for v in raw["points"][s] if lo <= v[3] < hi]
        def window(stdout, lo=F(lower), hi=F(upper)):
            value = json.loads(stdout)
            actual = [(s["record"], s["sample"], s["digital"], F(int(s["time_numerator"]), int(s["time_denominator"]))) for s in value["samples"]]
            expect = [v for v in raw["points"][0] if lo <= v[3] < hi]
            assert actual == expect, (actual, expect)
            assert F(value["start"]) == lo and F(value["end"]) == hi
        def epoch(stdout):
            value = json.loads(stdout)
            assert F(value["start"]) == F(lower) and F(value["end"]) == F(upper), (value["start"], value["end"])
            for channel in value["channels"]:
                actual = [(s["record"], s["sample"], s["digital"], F(int(s["time_numerator"]), int(s["time_denominator"]))) for s in channel["samples"]]
                assert actual == expected(channel["signal"])
        def window_csv(stdout):
            values = list(csv.DictReader(io.StringIO(stdout)))
            actual = [(int(v["signal"]), int(v["record"]), int(v["sample"]), int(v["value"]), F(int(v["time_numerator"]), int(v["time_denominator"]))) for v in values]
            expect = [(s, r, j, v, t) for s in [0, 1] for r, j, v, t in expected(s)]
            assert actual == expect, (actual, expect)
        def crop(path):
            value = read_raw(path)
            delta = value["clock"] - raw["clock"]; shift = F(delta.days * 86400 + delta.seconds)
            for s in [0, 1]:
                assert [(v, t + shift) for _, _, v, t in value["points"][s]] == [(v, t) for _, _, v, t in expected(s)]
            assert [(t + shift, d, text) for _, _, t, d, text in value["events"]] == [(F("0.5"), None, "anchor")]
        def created(path):
            value = read_raw(path)
            assert value["starts"] == [F("0.250000000000000000001"), F("0.373456700000000000001")], value["starts"]
            assert value["duration"] == F("0.1234567")
            assert [(r, t, F(d) if d is not None else None, text) for r, _, t, d, text in value["events"]] == [
                (0, F("-0.125000000000000000001"), F("0.125000000000000000001"), "nested"),
                (1, F("0.373456700000000000003"), None, "later")]
            low, high = (-32768, 32767) if fmt == "edf" else (-8388608, 8388607)
            assert [v[2] for v in value["points"][0]] == [low, 1, 2, high, 3, 4, 5, 6]
            assert [v[2] for v in value["points"][1]] == [11, 12, 13, 14]
            assert F(value["columns"][3][0].decode().strip()) == F("12345e-9")
        def added(path):
            value = read_raw(path)
            assert value["events"] == raw["events"] + [(0, 3, F("-0.125000000000000000001"), "0.125000000000000000001", "added")], value["events"]
            for s in [0, 1]: assert value["points"][s] == raw["points"][s]
        for numeric in [True, False]:
            tag = fmt + ("-number" if numeric else "-string")
            text = render('{"signal":0,"start":@LO@,"end":@HI@,"max_samples":2}', numeric, LO=lower, HI=upper)
            run("window-" + tag, "window", source, text, window)
            if not args.baseline:
                run("window-exact-" + tag, "window-exact", source, text, window)
                run("window-csv-" + tag, "window-csv", source, render('{"signals":[0,1],"start":@LO@,"end":@HI@,"physical":false}', numeric, LO=lower, HI=upper), window_csv)
                run("crop-time-" + tag, "crop-time", source, text, crop, writes=True)
                text = render('{"annotation":0,"signals":[0,1],"before":@BEFORE@,"after":@AFTER@,"max_samples":3}', numeric, BEFORE=before, AFTER=after)
                run("epoch-" + tag, "epoch", source, text, epoch)
                run("epoch-exact-" + tag, "epoch-exact", source, text, epoch)
            low, high = (-32768, 32767) if fmt == "edf" else (-8388608, 8388607)
            template = '{"format":"' + fmt + '","duration":@D@,"signals":[{"label":"fast","samples_per_record":4,"physical_min":0.000012345,"physical_max":0.000054321},{"label":"slow","samples_per_record":2}],"records":[{"onset":@R0@,"samples":[[' + str(low) + ',1,2,' + str(high) + '],[11,12]],"events":[{"onset":@E0@,"duration":@SPAN@,"text":"nested"}]},{"onset":@R1@,"samples":[[3,4,5,6],[13,14]],"events":[{"onset":@E1@,"duration":null,"text":"later"}]}]}'
            text = render(template, numeric, D="0.1234567", R0="0.250000000000000000001", R1="0.373456700000000000001", E0="-0.125000000000000000001", SPAN="0.125000000000000000001", E1="0.373456700000000000003")
            run("create-" + tag, "create", source, text, created)
            run("annotation-add-negative-" + tag, "annotation-add", source, render('{"onset":@ONSET@,"duration":@SPAN@,"text":"added","record":0,"signal":3}', numeric, ONSET="-0.125000000000000000001", SPAN="0.125000000000000000001"), added, writes=True)
            run("tolerance-below-" + tag, "inspect", sources["tolerance", fmt], render('{"time_tolerance":@TOL@}', numeric, TOL=threshold), error="Invalid(")
            if not args.baseline:
                run("tolerance-equal-" + tag, "inspect", sources["tolerance", fmt], render('{"time_tolerance":@TOL@}', numeric, TOL="1e-21"), lambda s: (json.loads(s)["records"] == 2) or (_ for _ in []).throw(AssertionError("record count")))
                run("negative-tolerance-" + tag, "inspect", source, render('{"time_tolerance":@TOL@}', numeric, TOL="-1e-5000"), error="Invalid(")
        def channel(stdout):
            value = json.loads(stdout)
            assert value["values"] == [v[2] for v in raw["points"][0][1:3]]
        run("channel-index-" + fmt, "channel", source, '{"signal":0,"start":1.0,"count":2,"physical":false}', channel)
        def calibrated(path):
            value = read_raw(path)
            assert F(value["columns"][3][0].decode().strip()) == F("-150.25")
            assert F(value["columns"][4][0].decode().strip()) == F("149.75")
            assert value["columns"][2][0].strip() == b"mV"
            for r, row in enumerate(raw["blocks"]):
                for s in [0, 1]: assert value["blocks"][r][s] == row[s]
        run("calibrate-physical-offset-" + fmt, "calibrate", source, '{"signal":0,"scale":1.5,"offset":-0.25,"unit":"mV"}', calibrated, writes=True)
        if not args.baseline:
            def typed(path):
                value = read_raw(path)
                assert value["events"] == [(0, 3, F("-0.125000000000000000001"), "0.125000000000000000001", "typed")]
            annotation = '{"record":0,"signal":3,"onset":"-0.125000000000000000001","duration":"0.125000000000000000001","text":"typed"}'
            run("annotations-set-" + fmt, "annotations-set", source, '{"annotations":[' + annotation + ']}', typed, writes=True)
            run("annotation-update-" + fmt, "annotation-update", source, '{"index":0,"annotation":' + annotation + '}', typed, writes=True)
    if not args.baseline:
        source = sources["source", "edf"]; raw = read_raw(source)
        def tiny_window(stdout):
            value = json.loads(stdout)
            lo = F("1e-5000")
            assert F(value["start"]) == lo
            assert [(v["record"], v["sample"]) for v in value["samples"]] == [(r, j) for r, j, _, t in raw["points"][0] if lo <= t < 2]
        for numeric in [True, False]:
            tag = "number" if numeric else "string"
            run("underflow-" + tag, "window", source, render('{"signal":0,"start":@LO@,"end":2}', numeric, LO="1e-5000"), tiny_window)
            run("limit-" + tag, "window", source, render('{"signal":0,"start":@LO@,"end":2}', numeric, LO="1e-2147483648"), error="Limit(")
        text = render('{"signal":0,"start":0,"\\u0073tart":@LO@,"end":@HI@}', True, LO=lower, HI=upper)
        run("escaped-duplicate-time-key", "window", source, text, window)
        def rational(stdout):
            value = json.loads(stdout); assert F(value["start"]) == F(1, 3) and F(value["end"]) == F(5, 6)
            assert [(s["record"], s["sample"]) for s in value["samples"]] == [(0, 2), (0, 3)]
        run("rational-string-query", "window", source, '{"signal":0,"start":"1/3","end":"5/6"}', rational)
        run("sample-budget-error", "window", source, render('{"signal":0,"start":@LO@,"end":@HI@,"max_samples":1}', True, LO=lower, HI=upper), error="Limit(")
        def zero(path):
            value = read_raw(path); assert value["duration"] == 0 and value["starts"] == [F(0)]
            assert value["events"] == [(0, 0, F(0), None, "zero")]
        run("extreme-zero-create", "create", source, '{"signals":[],"duration":0e2147483647,"records":[{"onset":0e-2147483648,"samples":[],"events":[{"onset":-0e2147483647,"duration":null,"text":"zero"}]}]}', zero)
        def positive(path):
            assert read_raw(path)["events"] == raw["events"] + [(0, 3, F("0.500000000000000000001"), None, "positive")]
        run("annotation-add-positive-string", "annotation-add", source, '{"onset":"+0.500000000000000000001","duration":null,"text":"positive","record":0,"signal":3}', positive, writes=True)
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.values()}
    save(complete=True)
    bad = [v["name"] for v in rows if not v["matchedIndependentExpected"]]
    if args.baseline:
        expected_bad = ["window-edf-number", "create-edf-number", "annotation-add-negative-edf-number", "tolerance-below-edf-number"]
        if args.only: expected_bad = [n for n in expected_bad if n.startswith(args.only)]
        assert bad == expected_bad, bad
    print(f"{len(rows)} CLI checks; {len(bad)} mismatches; original source hashes unchanged", flush=True)
    if bad and not args.baseline: raise SystemExit(1)


if __name__ == "__main__":
    main()
