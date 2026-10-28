"""Verify native-channel PSD JSON/CSV semantics using raw EDF/BDF files.

Development only; Python standard library and the existing Node file consumer.
Uses exact four-point DFT formulae and rational clocks/calibration, with no
MoonBit writer, production DSP, FFT or external numerical reference as oracle.
Choose fresh output paths; generated inputs, options and exports are retained.
"""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RAW = runpy.run_path(str(ROOT / "tools/check-psd.py"))
COLUMNS = ["source_sha256", "signal", "label", "physical_unit", "psd_unit",
           "start", "end", "sample_rate_numerator", "sample_rate_denominator",
           "segment_length", "overlap_samples", "window", "detrend", "nfft",
           "frequency_hz", "density"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(path, width):
    """Two plain records; distinct clocks, fields and calibration per channel."""
    field = RAW["field"]
    limit = 1 << (8 * width - 1)
    channels = [
        dict(label='EEG,"A","B"', unit="mV", physical=("-100", "100"),
             digital=(-1000, 1000), records=[[3,-5,9,2,-4,7,1,-6], [5,1,-7,3,8,-2,4,-9]]),
        dict(label='NO UNIT,"X"', unit="", physical=("10", "-10"),
             digital=(-100, 100), records=[[4,7,1,-5,2,-8,3,-1,6,9,-4,0],
                                          [2,-6,8,1,-3,5,-9,4,7,-2,0,3]]),
        dict(label='ECG,"C"', unit='uV,"Q"', physical=(str(-limit), str(limit-1)),
             digital=(-limit, limit-1), records=[]),
    ]
    # The BDF channel really exercises signed 24-bit values beyond Int16.
    factor = 64 if width == 3 else 1
    wave = [-30000,15000,-12000,8000,20000,-9000,25000,-16000,
            11000,-23000,6000,18000,-14000,27000,-7000,3000]
    channels[2]["records"] = [[v*factor for v in wave], [v*factor for v in reversed(wave)]]
    ns = len(channels)
    fixed = ((b"0       " if width == 2 else b"\xffBIOSEMI")
             + field("X X X X", 80) + field("X", 80) + b"01.01.2000.00.00"
             + field(256*(ns+1), 8) + field("", 44) + field(2, 8)
             + field("1.5", 8) + field(ns, 4))
    columns = [(16, [c["label"] for c in channels]), (80, [""]*ns),
               (8, [c["unit"] for c in channels]),
               (8, [c["physical"][0] for c in channels]),
               (8, [c["physical"][1] for c in channels]),
               (8, [c["digital"][0] for c in channels]),
               (8, [c["digital"][1] for c in channels]), (80, [""]*ns),
               (8, [len(c["records"][0]) for c in channels]), (32, [""]*ns)]
    data = bytearray(fixed + b"".join(field(v, size) for size, values in columns for v in values))
    for record in range(2):
        for channel in channels:
            for value in channel["records"][record]:
                data.extend(value.to_bytes(width, "little", signed=True))
    path.write_bytes(data)
    return channels


def exact_dft4(points, rate, hann):
    """N=4 roots are 1, -i, -1, i; symmetric Hann is [0,3/4,3/4,0]."""
    weights = [F(0), F(3,4), F(3,4), F(0)] if hann else [F(1)]*4
    norm = rate * sum(w*w for w in weights)
    frames = [points[i:i+4] for i in range(0, len(points)-3, 2)]
    density = [F(0)]*3
    for frame in frames:
        a,b,c,d = [F.from_float(point[1])*w for point,w in zip(frame,weights)]
        powers = [(a+b+c+d)**2, 2*((a-c)**2+(d-b)**2), (a-b+c-d)**2]
        density = [total+power/norm for total,power in zip(density,powers)]
    return [value/len(frames) for value in density], len(frames)


def close(actual, expected):
    want = float(expected)
    assert math.isfinite(actual) and actual >= 0
    assert abs(actual-want) <= max(abs(want)*5e-11, 1e-12), (actual,want)


def rational(value):
    return F(int(value["numerator"]), int(value["denominator"]))


def snapshot(directory):
    return {str(p.relative_to(directory)):sha(p) for p in directory.rglob("*") if p.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    args = ap.parse_args()
    assert not args.output.exists() and not args.work_dir.exists(), "choose fresh output paths"
    args.work_dir.mkdir(parents=True)
    cases, errors, rates = [], [], {}

    def consume(source, options, output, *, options_name=None):
        options_path = args.work_dir/((options_name or output.name)+"-options.json")
        options_path.write_text(json.dumps(options,indent=2)+"\n",encoding="utf-8")
        return subprocess.run(["node",str(ROOT/"examples/edf-psd.mjs"),str(source),str(output),str(options_path)],
                              cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=60)

    for format_name, width in [("edf",2),("bdf",3)]:
        source = args.work_dir/("native-channels."+format_name)
        channels = fixture(source,width)
        source_sha = sha(source)
        for signal, channel in enumerate(channels):
            raw = RAW["raw_window"](source,signal,"0.1","2.9")
            rate = F(len(channel["records"][0]),1)/F("1.5")
            assert raw["rate"]==rate and raw["label"]==channel["label"] and raw["unit"]==channel["unit"]
            rates[str(signal)] = str(rate)
            for window in ["rectangular","hann_symmetric"]:
                name = f"{format_name}-channel-{signal}-{window}"
                options = dict(signal=signal,start="0.1",end="2.9",segment_length=4,overlap_samples=2,
                               window=window,bands=[dict(name="native-full-band",low_hz=0,high_hz=float(rate)/2)])
                output = args.work_dir/name
                proc = consume(source,options,output)
                assert proc.returncode==0,proc.stderr
                document = json.loads((output/"psd.json").read_text(encoding="utf-8"))
                value = document["result"]
                assert document["schema"]=="MoonEDF-PSD/1"
                assert document["source"]==dict(path=str(source.resolve()),bytes=source.stat().st_size,sha256=source_sha)
                assert sha(source)==source_sha
                display_unit = channel["unit"] or "unspecified"
                psd_unit, power_unit = f"({display_unit})^2/Hz", f"({display_unit})^2"
                assert (value["signal"],value["label"],value["unit"])==(signal,channel["label"],channel["unit"])
                assert value["unit_specified"]==bool(channel["unit"])
                assert (value["psd_unit"],value["power_unit"])==(psd_unit,power_unit)
                assert value["calibration"]==raw["calibration"]
                assert value["calibration"]==dict(physical_min_text=channel["physical"][0],physical_max_text=channel["physical"][1],
                                                   digital_min=channel["digital"][0],digital_max=channel["digital"][1])
                assert rational(value["sample_rate"])==rate and value["sample_rate_hz"]==float(rate)
                assert F(value["start"])==F("0.1") and F(value["end"])==F("2.9")
                assert rational(value["first_sample_time"])==raw["points"][0][0]
                assert rational(value["last_selected_sample_time"])==raw["points"][-1][0]
                expected, segments = exact_dft4(raw["points"],rate,window=="hann_symmetric")
                used = 4+(segments-1)*2
                assert (value["selected_samples"],value["used_samples"],value["dropped_tail_samples"],value["segments"])==(len(raw["points"]),used,len(raw["points"])-used,segments)
                assert rational(value["analyzed_end"])==raw["points"][0][0]+F(used)/rate
                assert (value["segment_length"],value["overlap_samples"],value["nfft"],value["window"])==(4,2,4,window)
                assert (value["detrend"],value["scaling"],value["sides"],value["average"])==("none","density","one-sided","mean")
                assert len(value["density"])==len(value["frequencies_hz"])==3
                assert value["bin_width_hz"]==float(rate/4)
                for k,(density,want) in enumerate(zip(value["density"],expected)):
                    close(density,want)
                    assert value["frequencies_hz"][k]==float(k*rate/4)
                assert value["bands"][0]["bins"]==3
                close(value["bands"][0]["power"],sum(expected)*rate/4)
                with (output/"psd.csv").open(encoding="utf-8",newline="") as f:
                    reader = csv.DictReader(f);assert reader.fieldnames==COLUMNS;rows=list(reader)
                assert len(rows)==3
                for k,row in enumerate(rows):
                    assert set(row)==set(COLUMNS) and None not in row
                    assert row["source_sha256"]==source_sha and row["signal"]==str(signal)
                    assert (row["label"],row["physical_unit"],row["psd_unit"])==(channel["label"],channel["unit"],psd_unit)
                    assert F(row["start"])==F("0.1") and F(row["end"])==F("2.9")
                    assert (row["sample_rate_numerator"],row["sample_rate_denominator"])==(str(rate.numerator),str(rate.denominator))
                    assert (row["segment_length"],row["overlap_samples"],row["nfft"],row["window"],row["detrend"])==("4","2","4",window,"none")
                    assert float(row["frequency_hz"])==float(k*rate/4)
                    close(float(row["density"]),expected[k])
                    assert float(row["density"])==value["density"][k]
                cases.append(dict(name=name,signal=signal,label=channel["label"],unit=channel["unit"],sampleRate=str(rate),
                                  selectedSamples=len(raw["points"]),segments=segments,csvRows=len(rows),sourceSha256=source_sha,
                                  expectedDensity=[str(v) for v in expected],actualDensity=value["density"],output=str(output)))
        # Actual consumer errors must not create an output directory or alter input.
        base = dict(signal=0,start="0.1",end="2.9",segment_length=4,overlap_samples=2,window="rectangular")
        for name, extra, message in [("signal",dict(signal=3),"ordinary signal"),("short",dict(start="0",end="0.1"),"shorter than")]:
            output = args.work_dir/f"{format_name}-error-{name}"
            proc = consume(source,dict(base,**extra),output)
            assert proc.returncode==2 and message in proc.stderr and not output.exists(),proc.stderr
            assert sha(source)==source_sha
            errors.append(dict(name=f"{format_name}-{name}",exitCode=2,noOutput=True,sourceUnchanged=True))
        existing = args.work_dir/f"{format_name}-channel-0-rectangular"
        (existing/"user-note.txt").write_bytes(b"retain existing exports\r\n")
        before = snapshot(existing)
        proc = consume(source,dict(base,signal=1),existing,options_name=format_name+"-existing-output")
        assert proc.returncode==2 and "output directory exists" in proc.stderr,proc.stderr
        assert snapshot(existing)==before and sha(source)==source_sha
        errors.append(dict(name=f"{format_name}-existing-output",exitCode=2,existingOutputUnchanged=True,sourceUnchanged=True))

    assert rates=={"0":"16/3","1":"8","2":"32/3"}
    report = dict(status="complete",oracle="Independent raw 16/24-bit fixtures and Fraction clocks/calibration; exact rational N4 DFT with rectangular or [0,3/4,3/4,0] symmetric Hann; existing Double physical view",
                  relativeTolerance=5e-11,absoluteTolerance=1e-12,cases=cases,errors=errors,csvColumns=COLUMNS,nativeRates=rates,
                  formats=["plain EDF 16-bit","plain BDF 24-bit"],resampling=False,unitConversion=False,
                  emptyUnit="Raw empty string; unit_specified=false; (unspecified)^2/Hz display; no inferred uV",
                  ordinaryAndSmallScaleGates="Unchanged check-psd.py and check-psd-scale.py retained separately")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status="complete",cases=len(cases),csvRows=sum(c["csvRows"] for c in cases),errors=len(errors),nativeRates=rates)))


if __name__=="__main__":
    main()
