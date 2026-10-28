"""Independent EDF/DFT + fixed SciPy 1.16.2 Welch acceptance (development only).

Creates raw EDF fixtures without the MoonBit writer. Needs numpy==2.3.4 and
scipy==1.16.2. Build the JS bridge first; MOON_EDF_BRIDGE may select another build.
Public data is read only, never copied into the source distribution.
"""
import argparse
import cmath
import csv
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SHA = "3427c8d01bff1380bc9ab9f27a35ece2af5dfadf3e291bbc05eb66e4dadbfe2e"


def field(v, n):
    b = str(v).encode("ascii")
    assert len(b) <= n
    return b.ljust(n, b" ")


def fixture(path, channels, starts=("+0",), duration="1", mode="C", physical=("-32768", "32767"), digital=(-32768, 32767)):
    per = [len(c[0]) for c in channels]
    assert all(len(c) == len(starts) and all(len(row) == per[s] for row in c) for s, c in enumerate(channels))
    ann = mode != "plain"
    counts = per + ([128] if ann else [])
    ns = len(counts)
    fixed = (b"0       " + field("X X X X", 80) + field("Startdate 01-JAN-2020 X X X", 80)
             + b"01.01.2000.00.00" + field(256 * (ns + 1), 8)
             + field("EDF+" + mode if ann else "", 44) + field(len(starts), 8)
             + field(duration, 8) + field(ns, 4))
    columns = [(16, ['PSD,"A"'] * len(per) + (["EDF Annotations"] if ann else [])),
               (80, [""] * ns), (8, ["uV"] * len(per) + ([""] if ann else [])),
               (8, [physical[0]] * len(per) + (["-1"] if ann else [])),
               (8, [physical[1]] * len(per) + (["1"] if ann else [])),
               (8, [digital[0]] * len(per) + ([-32768] if ann else [])),
               (8, [digital[1]] * len(per) + ([32767] if ann else [])), (80, [""] * ns),
               (8, counts), (32, [""] * ns)]
    data = bytearray(fixed + b"".join(field(v, width) for width, values in columns for v in values))
    for r, start in enumerate(starts):
        for c in channels:
            for value in c[r]:
                data.extend(value.to_bytes(2, "little", signed=True))
        if ann:
            data.extend((start.encode() + b"\x14\x14\0").ljust(256, b"\0"))
    path.write_bytes(data)


def raw_window(path, signal, lower, upper):
    """Read only the selected raw channel, using Fraction clock/calibration."""
    data = path.read_bytes()
    width = 3 if data[:8] == b"\xffBIOSEMI" else 2
    ns, nr, hs = int(data[252:256]), int(data[236:244]), int(data[184:192])
    def column(offset, size):
        return [data[256 + ns * offset + s * size:256 + ns * offset + (s + 1) * size].decode().strip() for s in range(ns)]
    labels, units = column(0, 16), column(96, 8)
    pmin, pmax = column(104, 8), column(112, 8)
    dmin, dmax = column(120, 8), column(128, 8)
    per = list(map(int, column(216, 8)))
    offsets = [width * sum(per[:s]) for s in range(ns)]
    stride = width * sum(per)
    assert len(data) == hs + stride * nr
    duration = F(data[244:252].decode().strip())
    annotation = next((s for s, label in enumerate(labels) if label in ("EDF Annotations", "BDF Annotations")), None)
    lo, hi = F(lower), F(upper)
    points = []
    gain = (F(pmax[signal]) - F(pmin[signal])) / (int(dmax[signal]) - int(dmin[signal]))
    for r in range(nr):
        base = hs + r * stride
        onset = r * duration
        if annotation is not None:
            block = data[base + offsets[annotation]:base + offsets[annotation] + width * per[annotation]]
            onset = F(block.split(b"\x14", 1)[0].decode())
        if onset + duration <= lo or onset >= hi:
            continue
        for j in range(per[signal]):
            t = onset + duration * F(j, per[signal])
            if lo <= t < hi:
                at = base + offsets[signal] + j * width
                digital = int.from_bytes(data[at:at + width], "little", signed=True)
                physical = F(pmin[signal]) + (digital - int(dmin[signal])) * gain
                points.append((t, float(physical)))
    return dict(points=points, rate=F(per[signal]) / duration, label=labels[signal], unit=units[signal],
                calibration=dict(physical_min_text=pmin[signal], physical_max_text=pmax[signal],
                                 digital_min=int(dmin[signal]), digital_max=int(dmax[signal])))


def direct_dft(values, fs, n, overlap, hann):
    weights = [0.5 - 0.5 * math.cos(2 * math.pi * j / (n - 1)) if hann else 1.0 for j in range(n)]
    norm = fs * sum(w * w for w in weights)
    frames = [values[i:i + n] for i in range(0, len(values) - n + 1, n - overlap)]
    return [sum(abs(sum(frame[j] * weights[j] * cmath.exp(-2j * math.pi * k * j / n)
                        for j in range(n))) ** 2 / norm * (1 if k in (0, n // 2) else 2)
                for frame in frames) / len(frames) for k in range(n // 2 + 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--public-input", type=Path)
    ap.add_argument("--consumer-dir", type=Path)
    a = ap.parse_args()
    assert not a.output.exists(), "choose a new output report"
    assert not a.work_dir.exists(), "choose a new work directory"
    a.work_dir.mkdir(parents=True)
    import numpy as np
    import scipy
    from scipy.signal import welch
    assert (np.__version__, scipy.__version__) == ("2.3.4", "1.16.2")
    evidence = dict(status="in_progress", python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
                    bridge=os.environ.get("MOON_EDF_BRIDGE", "default product _build"),
                    relativeTolerance=5e-11, absoluteTolerance=1e-9, numerical=[], rejected=[])
    counter = 0

    def run(path, options, error=None):
        nonlocal counter
        counter += 1
        opts = a.work_dir / f"options-{counter}.json"
        opts.write_text(options if isinstance(options, str) else json.dumps(options), encoding="utf-8")
        proc = subprocess.run(["node", str(ROOT / "tools/edf.mjs"), "psd", str(path), str(opts)],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
        if error:
            assert proc.returncode == 2 and error in proc.stderr, (error, proc.returncode, proc.stderr)
            evidence["rejected"].append(dict(case=counter, expected=error, stderr=proc.stderr.strip()))
            return None
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    def compare(name, path, options, dft=True):
        value = run(path, options)
        raw = raw_window(path, options["signal"], options["start"], options["end"])
        n, overlap = options["segment_length"], options["overlap_samples"]
        x = np.array([p[1] for p in raw["points"]], dtype=np.float64)
        window = np.array([0.5 - 0.5 * math.cos(2 * math.pi * j / (n - 1))
                           if options["window"] == "hann_symmetric" else 1.0 for j in range(n)])
        freq, density = welch(x, fs=float(raw["rate"]), window=window, nperseg=n, noverlap=overlap,
                              nfft=n, detrend=False, return_onesided=True, scaling="density", average="mean")
        np.testing.assert_allclose(value["frequencies_hz"], freq, rtol=5e-15, atol=1e-14)
        np.testing.assert_allclose(value["density"], density, rtol=5e-11, atol=1e-9)
        if dft:
            np.testing.assert_allclose(value["density"], direct_dft(x.tolist(), float(raw["rate"]), n, overlap,
                                       options["window"] == "hann_symmetric"), rtol=5e-11, atol=1e-9)
        frames = [x[i:i + n] for i in range(0, len(x) - n + 1, n - overlap)]
        energy = sum(float(np.sum((frame * window) ** 2) / np.sum(window ** 2)) for frame in frames) / len(frames)
        np.testing.assert_allclose(sum(value["density"]) * value["bin_width_hz"], energy, rtol=5e-11, atol=1e-9)
        used = n + (len(frames) - 1) * (n - overlap)
        assert (value["selected_samples"], value["used_samples"], value["dropped_tail_samples"], value["segments"]) == (len(x), used, len(x) - used, len(frames))
        assert F(int(value["sample_rate"]["numerator"]), int(value["sample_rate"]["denominator"])) == raw["rate"]
        assert value["label"] == raw["label"] and value["unit"] == raw["unit"]
        assert value["calibration"] == raw["calibration"]
        assert F(int(value["first_sample_time"]["numerator"]), int(value["first_sample_time"]["denominator"])) == raw["points"][0][0]
        assert F(int(value["analyzed_end"]["numerator"]), int(value["analyzed_end"]["denominator"])) == raw["points"][0][0] + F(used) / raw["rate"]
        assert value["detrend"] == "none" and value["scaling"] == "density" and value["average"] == "mean"
        for band in value["bands"]:
            bins = [i for i, f in enumerate(freq) if band["low_hz"] <= f < band["high_hz"]
                    or (band["high_hz"] == float(raw["rate"]) / 2 and i == len(freq) - 1)]
            assert band["bins"] == len(bins)
            np.testing.assert_allclose(band["power"], sum(density[bins]) * value["bin_width_hz"], rtol=5e-11, atol=1e-9)
        evidence["numerical"].append(dict(name=name, bins=len(freq), samples=len(x), segments=len(frames),
            independentDft=dft, scipyMaxAbsoluteError=float(np.max(np.abs(np.array(value["density"]) - density)))))
        return value

    base = dict(signal=0, start="0", end="1", segment_length=8, overlap_samples=0, window="rectangular")
    analytic = [([0,2,0,-2,0,2,0,-2], [0,0,2,0,0]), ([3]*8, [9,0,0,0,0]),
                ([3,-3]*4, [0,0,0,0,9]), ([0]*8, [0]*5), ([2,2,2,-2]*2, [1,0,2,0,1])]
    for i, (samples, expected) in enumerate(analytic):
        p = a.work_dir / f"analytic-{i}.edf"
        fixture(p, [[samples]])
        result = compare(f"analytic-{i}", p, dict(base, bands=[dict(name="low", low_hz=0, high_hz=2), dict(name="high", low_hz=2, high_hz=4)]))
        np.testing.assert_allclose(result["density"], expected, rtol=1e-10, atol=1e-9)
    p = a.work_dir / "rect-two.edf"; fixture(p, [[[1,-1]]])
    compare("two-sample-DC-Nyquist", p, dict(base, segment_length=2))
    waves = [[round(2000 * math.sin(2 * math.pi * 3 * i / 32) + 700 * math.cos(2 * math.pi * 7 * i / 32) + 23) for i in range(93)],
             [round(500 * math.sin(2 * math.pi * 2 * i / 16)) for i in range(45)]]
    p = a.work_dir / "multirate.edf"; fixture(p, [[waves[0]], [waves[1]]], duration="3")
    for signal, n in [(0,32),(1,16)]:
        for window in ("rectangular", "hann_symmetric"):
            compare(f"multirate-{signal}-{window}", p, dict(base, signal=signal, end="3", segment_length=n, overlap_samples=n//2-4, window=window))
    doubled = a.work_dir / "double.edf"; fixture(doubled, [[[2*v for v in waves[0]]]], duration="3")
    first = run(p, dict(base, end="3", segment_length=32, overlap_samples=12))
    twice = compare("amplitude-times-two", doubled, dict(base, end="3", segment_length=32, overlap_samples=12))
    np.testing.assert_allclose(twice["density"], 4*np.array(first["density"]), rtol=5e-11, atol=1e-9)
    reversed_gain = a.work_dir / "negative-gain.edf"
    fixture(reversed_gain, [[waves[0]]], duration="3", physical=("100", "-100"))
    compare("negative-calibration-gain", reversed_gain, dict(base, end="3", segment_length=32, overlap_samples=12, window="hann_symmetric"))
    gap = a.work_dir / "gap.edf"; fixture(gap, [[analytic[0][0],analytic[0][0]]], starts=("+0.25","+2.25"), mode="D")
    compare("EDF-D-single-island", gap, dict(base, start="2.25", end="3.25"))
    run(gap, dict(base, start="0.25", end="3.25"), "crosses missing recording time")
    run(gap, dict(base, start="1.25", end="2.25"), "crosses missing recording time")
    jitter = a.work_dir / "tolerated-overlap.edf"; fixture(jitter, [[analytic[0][0],analytic[0][0]]], starts=("+0","+0.99"), mode="D")
    run(jitter, dict(base, end="1.99", time_tolerance="0.02"), "not uniformly spaced")
    short = a.work_dir / "analytic-0.edf"
    exact = run(short, '{"signal":0,"start":0.000000000000000000001,"end":1,"segment_length":4,"overlap_samples":0,"window":"rectangular"}')
    assert exact["start"] == "0.000000000000000000001" and exact["selected_samples"] == 7
    for extra, error in [({"end":"0.25"}, "shorter than"), ({"start":"-0.1"}, "missing recording time"),
        ({"signal":1}, "ordinary signal"), ({"segment_length":3}, "power of two"),
        ({"segment_length":2,"window":"hann_symmetric"}, "at least four"), ({"overlap_samples":8}, "overlap_samples"),
        ({"overlap_samples":-1}, "overlap_samples"), ({"nfft":16}, "nfft must equal"),
        ({"max_samples":7}, "sample limit"), ({"max_samples":1048577}, "budgets must"),
        ({"detrend":"constant"}, "detrend=none"), ({"window":"hann_periodic"}, "window requires"),
        ({"scaling":"spectrum"}, "scaling=density"), ({"unknown":True}, "unknown PSD option"),
        ({"bands":[dict(name="bad",low_hz=-1,high_hz=2)]}, "PSD band requires"),
        ({"bands":[dict(name="bad",low_hz=0,high_hz=5)]}, "PSD band requires")]:
        run(short, dict(base, **extra), error)
    run(p, dict(base, end="3", segment_length=32, overlap_samples=31, max_segments=1), "transform-point budget")
    work = a.work_dir / "work-budget.edf"; fixture(work, [[[0]*11000]])
    run(work, dict(base, segment_length=8192, overlap_samples=8191), "transform-point budget")
    for name, physical, digital, sample, error in [
        ("header-calibration-overflow",("-1e308","1e308"),(-32768,32767),1,"invalid physical calibration bounds"),
        ("physical-overflow",("0","1e308"),(0,1),32767,"physical calibration overflow"),
        ("spectral-overflow",("0","1e200"),(0,1),1,"PSD or frequency grid")]:
        f = a.work_dir / (name + ".edf"); fixture(f, [[[sample]*8]], physical=physical, digital=digital)
        run(f, base, error)
    rate = a.work_dir / "rate-overflow.edf"; fixture(rate, [[[1]*8]], duration="1e-307")
    run(rate, dict(base, end="1e-307"), "normalization is not representable")
    zero = a.work_dir / "zero-duration.edf"; fixture(zero, [[[1],[2]]], starts=("+0","+1"), duration="0", mode="D")
    run(zero, dict(base, end="2", segment_length=2), "positive duration")
    if a.public_input:
        assert a.consumer_dir is not None and not a.consumer_dir.exists()
        assert hashlib.sha256(a.public_input.read_bytes()).hexdigest() == PUBLIC_SHA
        opts = dict(base, end="4", segment_length=256, overlap_samples=128, window="hann_symmetric", bands=[dict(name="requested-8-12-Hz",low_hz=8,high_hz=12)])
        public = compare("PhysioNet-S001R03-channel-0-0-to-4s", a.public_input, opts, dft=False)
        optfile = a.work_dir / "public-options.json"; optfile.write_text(json.dumps(opts), encoding="utf-8")
        proc = subprocess.run(["node", str(ROOT/"examples/edf-psd.mjs"), str(a.public_input), str(a.consumer_dir), str(optfile)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        document = json.loads((a.consumer_dir/"psd.json").read_text(encoding="utf-8"))
        assert document["source"]["sha256"] == PUBLIC_SHA and document["result"] == public
        with (a.consumer_dir/"psd.csv").open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
        assert len(rows) == len(public["density"])
        for i,row in enumerate(rows):
            assert row["source_sha256"] == PUBLIC_SHA and row["label"] == public["label"] and row["psd_unit"] == public["psd_unit"]
            assert float(row["frequency_hz"]) == public["frequencies_hz"][i] and float(row["density"]) == public["density"][i]
        attribution=dict(dataset="EEG Motor Movement/Imagery Dataset 1.0.0", creators="Schalk et al.; PhysioNet",
            url="https://physionet.org/content/eegmmidb/1.0.0/S001/S001R03.edf", doi="10.13026/C28G6P", license="ODC-By 1.0",
            licenseUrl="https://physionet.org/content/eegmmidb/view-license/1.0.0/", inputSha256=PUBLIC_SHA,
            clinicalInterpretation=False, rawInputDistributed=False)
        (a.consumer_dir/"source-attribution.json").write_text(json.dumps(attribution,indent=2)+"\n",encoding="utf-8")
        evidence["publicConsumer"]=dict(directory=str(a.consumer_dir), bins=len(rows), source=attribution,
            files=[dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted(a.consumer_dir.iterdir())])
    evidence.update(status="complete", cliCalls=counter, exactJsonTimeLexemePreserved=True,
                    physicalOracle="raw fixed-width bytes + Fraction clock/calibration; nearest Double view", energyChecks=True)
    a.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status=evidence["status"], numericalCases=len(evidence["numerical"]), rejectedCases=len(evidence["rejected"]), cliCalls=counter)))


if __name__ == "__main__":
    main()
