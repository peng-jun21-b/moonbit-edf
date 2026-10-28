"""Read back the fixed public epoch CSVs against raw EDF and Fraction (MIT).

No MoonBit writer, reference-batch run, external Python dependency or download.
Run the public consumer first; this checker only reads its completed output.
"""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

SHA = "3427c8d01bff1380bc9ab9f27a35ece2af5dfadf3e291bbc05eb66e4dadbfe2e"
HEADER = "annotation,event,signal,label,record,sample,time_seconds,event_relative_seconds,digital,physical,unit,time_numerator,time_denominator".split(",")
sha = lambda data: hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("input", type=Path); parser.add_argument("export", type=Path); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); data = args.input.read_bytes(); assert sha(data) == SHA and len(data) == 2596896
    ns, nr, hs = [int(data[a:b]) for a, b in [(252, 256), (236, 244), (184, 192)]]
    columns, at = [], 256
    for width in [16, 80, 8, 8, 8, 8, 8, 80, 8, 32]:
        columns.append([data[at + s * width:at + (s + 1) * width].decode().strip() for s in range(ns)]); at += ns * width
    per = list(map(int, columns[8])); duration = F(data[244:252].decode().strip()); offsets = [2 * sum(per[:s]) for s in range(ns)]; record_bytes = 2 * sum(per)
    assert hs == at and len(data) == hs + nr * record_bytes
    annotations, starts = [], []
    ann = [s for s in range(ns) if columns[0][s] == "EDF Annotations"]
    for r in range(nr):
        for s in ann:
            pos = hs + r * record_bytes + offsets[s]
            for i, tal in enumerate(filter(None, data[pos:pos + per[s] * 2].split(b"\0"))):
                clock, *texts = tal.split(b"\x14"); parts = clock.split(b"\x15")
                if s == ann[0] and i == 0: starts.append(F(parts[0].decode()))
                for text in filter(None, texts):
                    event = dict(record=r, signal=s, onset=parts[0].decode(), text=text.decode("utf-8"))
                    if len(parts) == 2: event["duration"] = parts[1].decode()
                    annotations.append(event)
    assert len(starts) == nr
    selected = [i for i, event in enumerate(annotations) if event["text"] == "T1"]
    manifest_path = args.export / "manifest.json"; manifest_bytes = manifest_path.read_bytes(); manifest = json.loads(manifest_bytes)
    assert manifest["inputSha256"] == SHA and manifest["license"] == "ODC-By-1.0" and manifest["doi"] == "10.13026/C28G6P"
    assert manifest["timeColumns"]["exact"] == ["time_numerator", "time_denominator"]
    assert manifest["timeColumns"]["exact_event_onset"] == "files[].annotation.onset"
    assert len(manifest["files"]) == len(selected) == 8
    products, count = [], 0
    grids = {s: [(r, j, start + duration * F(j, per[s])) for r, start in enumerate(starts) for j in range(per[s])] for s in [0, 8, 32]}
    for item, index in zip(manifest["files"], selected, strict=True):
        event = annotations[index]; onset = F(event["onset"]); start = onset - F(1, 4); end = onset + F(event["duration"]) + F(1, 4)
        assert item["annotation"] == event and item["options"] == dict(command="epoch", annotation=index, signals=[0, 8, 32], before=0.25, after=0.25, max_samples=10000)
        assert F(item["start"]) == start and F(item["end"]) == end and item["complete"]
        path = args.export / item["file"]; content = path.read_bytes(); assert sha(content) == item["sha256"]
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f); assert reader.fieldnames == HEADER; rows = list(reader)
        expected = [(s, r, j, t) for s in [0, 8, 32] for r, j, t in grids[s] if start <= t < end]
        assert len(rows) == len(expected) == item["samples"]
        for row, (s, r, j, t) in zip(rows, expected, strict=True):
            pos = hs + r * record_bytes + offsets[s] + 2 * j; digital = int.from_bytes(data[pos:pos + 2], "little", signed=True)
            assert (int(row["annotation"]), row["event"], int(row["signal"]), row["label"], int(row["record"]), int(row["sample"]), int(row["digital"]), row["unit"]) == (index, "T1", s, columns[0][s], r, j, digital, columns[2][s])
            n, d = int(row["time_numerator"]), int(row["time_denominator"]); assert d > 0 and F(n, d) == t
            seconds, relative = float(row["time_seconds"]), float(row["event_relative_seconds"])
            assert math.isfinite(seconds) and math.isfinite(relative)
            assert math.isclose(seconds, float(t), rel_tol=0, abs_tol=1e-12) and math.isclose(relative, float(t - onset), rel_tol=0, abs_tol=1e-12)
            pmin, pmax, dmin, dmax = [F(columns[c][s]) for c in [3, 4, 5, 6]]
            physical = pmin + (digital - dmin) * (pmax - pmin) / (dmax - dmin)
            assert math.isclose(float(row["physical"]), float(physical), rel_tol=1e-12, abs_tol=1e-10)
        count += len(rows); products.append(dict(path=str(path.resolve()), sha256=sha(content), rows=len(rows)))
    assert count == 17664 and sha(args.input.read_bytes()) == SHA
    products.append(dict(path=str(manifest_path.resolve()), sha256=sha(manifest_bytes)))
    receipt = dict(status="passed", oracle="Raw EDF fixed-width samples, TAL annotations and Fraction clocks/calibration", inputSha256=SHA,
        epochs=len(selected), rows=count, exactTimeRows=count, digitalRows=count, physicalRows=count, invalidTimeRows=0, products=products,
        scope="Fixed S001R03 T1 export only; numeric seconds are approximations; fraction columns and annotation onset retain exact time")
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(dict(status="passed", epochs=len(selected), rows=count, products=len(products), invalidTimeRows=0)))


if __name__ == "__main__":
    main()
