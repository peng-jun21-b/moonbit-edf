"""Independent crop -> append -> file/readback workflow checks (synthetic MIT).

The inputs use fixed-width Python byte constructors, never the MoonBit writer.
--inputs may point to retained pre-repair calibration fixtures. --reference-c
also reads two continuous session products with development PyEDFlib.
"""
import argparse
from datetime import datetime
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "tools/check-append.py"))
make, change, read = HELPERS["make"], HELPERS["change"], HELPERS["read_raw"]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def seconds(delta):
    return F(delta.days * 86400 + delta.seconds)


def calibration(source, result):
    for s in source["ordinary"]:
        for col in [3, 4]:
            assert result["columns"][col][s] == source["columns"][col][s], (s, col, source["columns"][col][s], result["columns"][col][s])


def points(source, result, lower=None, upper=None):
    shift = seconds(result["clock"] - source["clock"])
    for s in source["ordinary"]:
        expected = [(v, t) for _, _, v, t in source["points"][s]
                    if (lower is None or lower <= t) and (upper is None or t < upper)]
        assert [(v, t + shift) for _, _, v, t in result["points"][s]] == expected


def complete_session(source, left, right, result):
    points(source, result); calibration(source, result)
    assert result["clock"] == source["clock"] and result["starts"] == source["starts"]
    shift = seconds(right["clock"] - left["clock"])
    expected = left["events"] + [(r + left["nr"], s, t + shift, d, text) for r, s, t, d, text in right["events"]]
    if not right["ann"]:
        # Plain-to-plus promotion retains free-text IDs as annotations.
        signal = len(right["ordinary"])
        for prefix, raw in [("Original recording ID: ", right["data"][88:168]), ("Original patient ID: ", right["data"][8:88])]:
            text = raw.decode().strip()
            if text: expected.append((left["nr"], signal, shift, None, prefix + text))
    assert result["events"] == expected
    expected_absolute = sorted((s, t, d or "", text) for _, s, t, d, text in source["events"])
    actual_absolute = sorted((s, t, d or "", text) for _, s, t, d, text in result["events"]
                             if not text.startswith(("Original patient ID:", "Original recording ID:")))
    assert actual_absolute == expected_absolute


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path); parser.add_argument("--reference-c", action="store_true")
    parser.add_argument("--resume", type=Path, help="Reuse successful command outputs from a retained partial receipt")
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    work = args.output.parent / (args.output.stem + "-cases"); work.mkdir()
    rows, sources, sessions, reference = [], {}, [], []
    reused = []
    if args.resume:
        earlier = json.loads(args.resume.read_text(encoding="utf-8"))
        rows, sources, sessions, reference = earlier["checks"], earlier["sourceHashes"], earlier["sessions"], earlier["referenceC"]
    def save(complete=False):
        args.output.write_text(json.dumps(dict(status="passed" if complete else "in_progress", python=platform.python_version(),
            oracle="Original fixed-width inputs, Fraction sample clocks/calibration and Gregorian datetime", sourceHashes=sources,
            checks=rows, sessions=sessions, referenceC=reference, reusedCommandOutputs=reused,
            resumedFrom=str(args.resume) if args.resume else None), indent=2), encoding="utf-8")
    def register(path):
        sources[str(path)] = sha(path); return read(path)
    def transform(name, command, source, options=None, *, other=None, error=False):
        cached = next((v for v in rows if v["name"] == name), None)
        if cached is not None:
            assert cached["exitCode"] == cached["expectedExitCode"]
            reused.append(name)
            if error:
                assert not Path(cached["output"]).exists(); return None
            output = Path(cached["output"])
            digest = sha(output)
            if "sha256" in cached: assert digest == cached["sha256"]
            cached["sha256"] = digest
            return output
        extension = ".bdf" if source.suffix == ".bdf" else ".edf"
        out = work / (name + extension)
        opts = work / (name + ".json")
        if options is not None: opts.write_text(json.dumps(options), encoding="utf-8")
        cmd = ["node", str(ROOT / "tools/edf.mjs"), command, str(source)]
        if other is not None: cmd.append(str(other))
        cmd.append(str(out))
        if options is not None: cmd.append(str(opts))
        v = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12)
        row = dict(name=name, command=cmd, exitCode=v.returncode, expectedExitCode=2 if error else 0,
                   stdout=v.stdout.decode(), stderr=v.stderr.decode(), output=str(out))
        rows.append(row); save()
        (work / (name + ".stdout")).write_bytes(v.stdout); (work / (name + ".stderr")).write_bytes(v.stderr)
        assert v.returncode == row["expectedExitCode"], row
        if error:
            assert b"configuration differs" in v.stderr and not out.exists()
            row["verified"] = True; save(); return None
        row["sha256"] = sha(out); save(); return out
    def verified(path):
        next(v for v in rows if v["output"] == str(path))["verified"] = True
        print("verified", path.stem, flush=True); save()
    def join(name, source, left, right):
        out = transform(name, "append", left, other=right)
        result = read(out); complete_session(source, read(left), read(right), result)
        verified(out)
        if not any(v["name"] == name for v in sessions):
            sessions.append(dict(name=name, output=str(out), sha256=sha(out), records=result["nr"],
                samples=sum(len(v) for v in result["points"].values()), events=len(result["events"])))
        save(); return out
    for fmt in ["edf", "bdf"]:
        minimum = work / ("minimum-source." + fmt); maximum = work / ("maximum-source." + fmt)
        if args.inputs:
            for path in [minimum, maximum]: path.write_bytes((args.inputs / path.name).read_bytes())
        else:
            make(minimum, fmt, [4, 2], ["+0", "+1"], events={(0, 0): [("+0.5", None, "left")], (1, 1): [("+1.5", "0.125", "right")]})
            change(minimum, 104, 0, "1e-324"); change(minimum, 112, 0, "1")
            make(maximum, fmt, [4, 2], ["+0", "+1"])
            change(maximum, 104, 0, "1"); change(maximum, 112, 0, "3e-324")
        raw = register(minimum); inverse = register(maximum)
        left = transform("time-first-" + fmt, "crop-time", minimum, dict(start="0", end="1"))
        calibration(raw, read(left)); points(raw, read(left), F(0), F(1)); verified(left)
        right = transform("whole-second-" + fmt, "crop", minimum, dict(first_record=1, records=1))
        calibration(raw, read(right)); points(raw, read(right), F(1), F(2)); verified(right)
        join("calibration-session-" + fmt, raw, left, right)
        added = transform("annotation-" + fmt, "annotation-add", maximum, dict(onset="+0.5", text="added", record=0, signal=3))
        calibration(inverse, read(added)); points(inverse, read(added)); assert read(added)["events"] == [(0, 3, F("0.5"), None, "added")]; verified(added)
        expanded = transform("signal-" + fmt, "annotation-signal", maximum)
        calibration(inverse, read(expanded)); points(inverse, read(expanded)); assert read(expanded)["ns"] == inverse["ns"] + 1; verified(expanded)
        mapped = transform("physical-map-" + fmt, "calibrate", minimum, dict(signal=0, scale=2, offset=3))
        value = read(mapped); points(raw, value)
        assert F(value["columns"][3][0].decode().strip()) == 3 and F(value["columns"][4][0].decode().strip()) == 5
        assert value["columns"][3][1] == raw["columns"][3][1] and value["columns"][4][1] == raw["columns"][4][1]
        verified(mapped)
        transform("reject-changed-calibration-" + fmt, "append", minimum, dict(offset="2"), other=mapped, error=True)
        plain = work / ("plain-source." + fmt)
        make(plain, fmt, [4, 2], ["+0", "+1"], mode="plain")
        change(plain, 104, 0, "1e-324"); change(plain, 112, 0, "1"); model = register(plain)
        left = transform("plain-time-first-" + fmt, "crop-time", plain, dict(start="0", end="1"))
        calibration(model, read(left)); points(model, read(left), F(0), F(1)); verified(left)
        right = transform("plain-whole-second-" + fmt, "crop", plain, dict(first_record=1, records=1))
        calibration(model, read(right)); points(model, read(right), F(1), F(2)); verified(right)
        join("plain-session-" + fmt, model, left, right)
        for gapped in [False, True]:
            name = ("gap" if gapped else "continuous") + "-leap-" + fmt
            source = work / (name + "-source." + fmt)
            last = "+4.25" if gapped else "+3.25"
            make(source, fmt, [4, 2], ["+0.25", "+1.25", "+2.25", last], mode="D" if gapped else "C",
                 clock=datetime(2020, 2, 28, 23, 59, 59),
                 events={(0, 0): [("+0.5", None, "start")], (2, 1): [("+2.5", "0.000000000000000000003", "resume")],
                         (3, 0): [("+4.5" if gapped else "+3.5", "0.125", "end")]})
            change(source, 104, 0, "12345e-9"); change(source, 112, 0, "54321e-9"); model = register(source)
            left = transform(name + "-left", "crop-time", source, dict(start="0.25", end="2.25"))
            calibration(model, read(left)); points(model, read(left), F("0.25"), F("2.25")); verified(left)
            end = "5.25" if gapped else "4.25"
            right = transform(name + "-right", "crop-time", source, dict(start="2.25", end=end))
            calibration(model, read(right)); points(model, read(right), F("2.25"), F(end)); verified(right)
            assert read(right)["clock"] == datetime(2020, 2, 29, 0, 0, 1)
            out = join(name + "-joined", model, left, right)
            assert read(out)["data"][196:197] == (b"D" if gapped else b"C")
            if not gapped and args.reference_c:
                import pyedflib
                with pyedflib.EdfReader(str(out)) as reader:
                    assert reader.signals_in_file == 2
                    for i in [0, 1]: assert list(reader.readSignal(i, digital=True)) == [v[2] for v in model["points"][i]]
                    reference.append(dict(name=name, reader="PyEDFlib", version=pyedflib.__version__, digitalSamples=24,
                        observedStart=reader.getStartdatetime().isoformat(), digitalExact=True))
                save()
        for annotation_only in [False, True]:
            name = ("annotation-only" if annotation_only else "zero-duration") + "-" + fmt
            source = work / (name + "-source." + fmt)
            starts = ["+0.25", "+2.25", "+4.25"]
            events = {(i, 0): [(s, None, "defining-" + str(i))] for i, s in enumerate(starts)}
            events[2, 1] = [("+4.5", "0.125", "secondary")]
            make(source, fmt, [] if annotation_only else [1, 1], starts, duration="0", mode="D", events=events)
            if not annotation_only: change(source, 104, 0, "1e-324"); change(source, 112, 0, "1")
            model = register(source)
            left = transform(name + "-left", "crop-time", source, dict(start="0.25", end="3"))
            calibration(model, read(left)); points(model, read(left), F("0.25"), F(3)); verified(left)
            right = transform(name + "-right", "crop-time", source, dict(start="4.25", end="5"))
            calibration(model, read(right)); points(model, read(right), F("4.25"), F(5)); verified(right)
            join(name + "-joined", model, left, right)
    assert all(sha(Path(path)) == digest for path, digest in sources.items())
    assert len(rows) == 44 and all(v.get("verified") for v in rows)
    save(complete=True)
    print(f"Passed {len(rows)} CLI paths, {len(sessions)} complete sessions and {len(reference)} reference-C readbacks; original inputs unchanged", flush=True)


if __name__ == "__main__":
    main()
