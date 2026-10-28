"""Fixed-width/Fraction oracle for imported identity crop rewrites (MIT).

Build the JS bridge, then pass a new --output receipt. Reference inputs use
original raw EDF/BDF constructors, not MoonEDF's writer. --reference-c also
reads two continuous outputs with the fixed development PyEDFlib dependency.
After a harness-only failure, --resume reuses unchanged recorded CLI calls.
"""
import argparse
from datetime import datetime, timedelta
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
helpers = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, read_raw, field = (helpers[key] for key in ["make", "read_raw", "field"])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-c", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases")
    bridge = ROOT / "_build/js/release/build/cmd/bridge/bridge.js"
    bridge_hash = sha(bridge)
    previous = json.loads(args.output.read_text()) if args.resume else None
    if previous:
        assert previous["bridgeSha256"] == bridge_hash
    else:
        work.mkdir()
    rows = previous["commands"] if previous else []
    cached = {row["name"]: row for row in rows}
    products, errors, inputs, references = [], [], [], []
    reused = []

    def save(complete=False):
        args.output.write_text(json.dumps(dict(
            status="passed" if complete else "in_progress",
            python=platform.python_version(), bridgeSha256=bridge_hash,
            oracle="Original fixed-width bytes, Gregorian datetime, Fraction sample/event clocks",
            commands=rows, products=products, checkedErrors=errors,
            inputs=inputs, referenceC=references, reusedCommands=reused,
        ), indent=2), encoding="utf-8")

    def run(name, arguments, output=None):
        command = ["node", str(ROOT / "tools/edf.mjs"), *map(str, arguments)]
        if name in cached:
            row = cached[name]
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

    def source(name, fmt, identity, *, future=False, plain=False, clock=None):
        path = work / (name + "-input." + fmt)
        if not path.exists():
            shift = "2524608000" if future else "1"
            make(path, fmt, [4, 2], ["+0", "+" + shift],
                 mode="plain" if plain else "D" if future else "C",
                 clock=clock or datetime(2020, 1, 1, 0 if future else 23,
                                         0 if future else 59, 0 if future else 59),
                 events=None if plain else {(1, 1): [("+2524608000.5" if future else "+1.5", "0.25", "right")]})
            data = bytearray(path.read_bytes())
            data[88:168] = field(identity, 80)
            path.write_bytes(data)
        else:
            assert args.resume
        raw = read_raw(path)
        assert raw["data"][88:168] == field(identity, 80)
        item = dict(path=str(path), sha256=sha(path), recordingId=identity)
        old = next((v for v in previous["inputs"] if v["path"] == str(path)), None) if previous else None
        if old:
            assert old == item
        inputs.append(item)
        return path, raw

    def crop(name, src, raw, operation, *, expected=None, invalid=None, c_reader=False):
        shift = raw["starts"][1]
        assert shift.denominator == 1
        options = work / (name + ".json")
        options.write_text(json.dumps(dict(first_record=1, records=1) if operation == "crop"
                                      else dict(start=str(shift), end=str(shift + 1))))
        out = work / (name + (".edf" if raw["width"] == 2 else ".bdf"))
        row = run(name, [operation, src, out, options], out)
        if invalid:
            assert row["exitCode"] == 2 and invalid in row["stderr"], row
            assert row["stderr"].startswith("MoonEDF: Invalid("), row
            assert not out.exists(), out
            errors.append(dict(name=name, reason=invalid, checkedInvalid=True, noPartialOutput=True))
        else:
            assert row["exitCode"] == 0, row
            got = read_raw(out)
            assert got["data"][88:168].decode().strip() == expected
            assert got["clock"] == raw["clock"] + timedelta(seconds=int(shift))
            delta = got["clock"] - raw["clock"]
            calendar_shift = F(delta.days * 86400 + delta.seconds)
            assert calendar_shift == shift and got["starts"] == [F(0)]
            assert got["nr"] == 1 and got["duration"] == raw["duration"]
            samples = 0
            for s in raw["ordinary"]:
                want = [(v, t) for _, _, v, t in raw["points"][s] if shift <= t < shift + 1]
                actual = [(v, t + calendar_shift) for _, _, v, t in got["points"][s]]
                assert actual == want
                assert got["blocks"][0][s] == raw["blocks"][1][s]
                assert all(got["columns"][c][s] == raw["columns"][c][s] for c in range(10))
                samples += len(actual)
            want_events = [(s, t, d, text) for _, s, t, d, text in raw["events"] if shift <= t < shift + 1]
            actual_events = [(s, t + calendar_shift, d, text) for _, s, t, d, text in got["events"]]
            assert actual_events == want_events
            products.append(dict(name=name, output=str(out), sha256=sha(out),
                                 recordingId=expected, clock=got["clock"].isoformat(),
                                 samples=samples, events=len(actual_events), exactAbsoluteClocks=True))
            if c_reader and args.reference_c:
                import pyedflib
                with pyedflib.EdfReader(str(out)) as reader:
                    assert reader.signals_in_file == len(got["ordinary"])
                    for index, s in enumerate(got["ordinary"]):
                        assert list(reader.readSignal(index, digital=True)) == [v[2] for v in got["points"][s]]
                    assert reader.getStartdatetime() == got["clock"]
                references.append(dict(name=name, reader="PyEDFlib", version=pyedflib.__version__,
                                       samples=samples, digitalExact=True, wholeSecondClockExact=True))
        assert sha(src) == next(v["sha256"] for v in inputs if v["path"] == str(src))
        save()
        print("verified", name, flush=True)

    malformed = "cannot update malformed plus recording identification"
    unknown = "Startdate X Adm Tech Dev " + "N" * 55
    known = "Startdate 01-JAN-2020 Adm Tech Dev " + "N" * 45
    assert len(unknown) == len(known) == 80
    for fmt in ["edf", "bdf"]:
        for index, identity in enumerate(["", "X", "Startdate X", "Other X X X X"]):
            name = f"malformed-{index}-{fmt}"
            src, raw = source(name, fmt, identity)
            if index == 2:
                row = run(name + "-inspect", ["inspect", src])
                assert row["exitCode"] == 0, row
            for op in ["crop", "crop-time"]:
                crop(name + "-" + op, src, raw, op, invalid=malformed)
        name = "partial-future-" + fmt
        src, raw = source(name, fmt, "Startdate 01-JAN-2100", clock=datetime(2100, 1, 1))
        assert run(name + "-inspect", ["inspect", src])["exitCode"] == 0
        for op in ["crop", "crop-time"]:
            crop(name + "-" + op, src, raw, op, invalid=malformed)
        for label, identity, expected in [
            ("unknown", "Startdate X X X X", "Startdate 02-JAN-2020 X X X"),
            ("tail", "Startdate 01-JAN-2020 Adm Tech Dev Extra_notes", "Startdate 02-JAN-2020 Adm Tech Dev Extra_notes"),
            ("spaces", "  Startdate   X  Adm Tech   Dev  Tail", "Startdate 02-JAN-2020 Adm Tech Dev Tail"),
            ("full-unknown", unknown, unknown),
        ]:
            name = label + "-" + fmt
            src, raw = source(name, fmt, identity)
            for op in ["crop", "crop-time"]:
                crop(name + "-" + op, src, raw, op, expected=expected,
                     c_reader=label == "unknown" and op == "crop-time")
        name = "plain-" + fmt
        src, raw = source(name, fmt, "free recording identity", plain=True)
        crop(name + "-crop", src, raw, "crop", expected="free recording identity")
        crop(name + "-crop-time", src, raw, "crop-time", expected="Startdate 02-JAN-2020 X X X")
        for label, identity, expected in [("unknown", unknown, None),
                                           ("known", known, known.replace("2020", "2100"))]:
            name = "full-future-" + label + "-" + fmt
            src, raw = source(name, fmt, identity, future=True)
            for op in ["crop", "crop-time"]:
                crop(name + "-" + op, src, raw, op, expected=expected,
                     invalid="header text exceeds field width 80:" if expected is None else None)
    for day in [30, 31]:
        name = f"year-boundary-{day}"
        src, raw = source(name, "edf", unknown, clock=datetime(2084, 12, day, 23, 59, 59))
        for op in ["crop", "crop-time"]:
            crop(name + "-" + op, src, raw, op, expected=unknown,
                 invalid="header text exceeds field width 80:" if day == 31 else None)
    assert all(sha(Path(v["path"])) == v["sha256"] for v in inputs)
    save(True)
    print(json.dumps(dict(status="passed", cliChecks=len(rows), products=len(products),
                          checkedErrors=len(errors), referenceC=len(references), inputsUnchanged=len(inputs))))


if __name__ == "__main__":
    main()
