"""EDF+ normative record bound; original fixed-width fixtures, no library writer.

Run after moon build --target js --release. Only Python's standard library is
required. EDF+ specification 2.1.2 and programming guidelines item 4 define the
expected bound; EDFlib's implementation limits are deliberately not the oracle.
Synthetic data and this script are covered by the project's MIT license.
"""
import argparse
import hashlib
import json
import pathlib
import platform
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def field(value, width):
    data = str(value).encode("ascii")
    assert len(data) <= width
    return data.ljust(width, b" ")


def fixture(fmt, mode, total):
    width = 2 if fmt == "EDF" else 3
    plus = mode != "plain"
    counts = [total // width - (32 if plus else 0)] + ([32] if plus else [])
    assert sum(counts) * width == total
    ns = len(counts)
    low, high = (-32768, 32767) if width == 2 else (-8388608, 8388607)
    fixed = (
        (b"0       " if width == 2 else b"\xffBIOSEMI")
        + field("X X X X", 80)
        + field("Startdate 01-JAN-2020 X X X", 80)
        + b"01.01.2000.00.00"
        + field(256 * (ns + 1), 8)
        + field(fmt + "+" + mode if plus else "", 44)
        + field(1, 8) + field(1, 8) + field(ns, 4)
    )
    cols = [
        (16, ["Signal"] + ([fmt + " Annotations"] if plus else [])),
        (80, [""] * ns), (8, ["uV"] + ([""] if plus else [])),
        (8, [-100] + ([-1] if plus else [])),
        (8, [100] + ([1] if plus else [])),
        (8, [low] * ns), (8, [high] * ns), (80, [""] * ns),
        (8, counts), (32, [""] * ns),
    ]
    header = fixed + b"".join(field(v, n) for n, values in cols for v in values)
    # Known signed endpoints catch accidental payload displacement on copy/edit.
    samples = [low] + [0] * (counts[0] - 2) + [high]
    payload = b"".join(v.to_bytes(width, "little", signed=True) for v in samples)
    if plus:
        payload += b"+0\x14\x14\0".ljust(32 * width, b"\0")
    return header + payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cases = [
        ("EDF", "C", 61440, True), ("EDF", "D", 61440, True),
        ("EDF", "C", 61442, False), ("EDF", "D", 61442, False),
        ("EDF", "plain", 61442, True),
        ("BDF", "C", 61443, True), ("BDF", "D", 61443, True),
    ]
    checks = []
    with tempfile.TemporaryDirectory(prefix="record-size-", dir=args.output.parent) as td:
        work = pathlib.Path(td)
        tasks, expected, sources = [], [], []
        for fmt, mode, size, accepted in cases:
            name = f"{fmt}-{mode}-{size}"
            src = work / (name + "." + fmt.lower())
            data = fixture(fmt, mode, size)
            src.write_bytes(data)
            sources.append((src, data))
            tasks.append(dict(kind="report", input=str(src), options=dict(command="inspect")))
            expected.append((name, accepted, None, data))
            if accepted:
                out = work / (name + "-copy." + fmt.lower())
                tasks.append(dict(kind="transform", input=str(src), output=str(out), options=dict(command="copy")))
                expected.append((name + "-copy", True, out, data))
            if fmt == "EDF" and mode in ("C", "D") and accepted:
                out = work / (name + "-edit.edf")
                tasks.append(dict(kind="transform", input=str(src), output=str(out), options=dict(command="annotation-add", onset="+0", text="x" * 100)))
                expected.append((name + "-tal-overflow", False, out, data))
        request, response = work / "tasks.json", work / "response.json"
        request.write_text(json.dumps(tasks), encoding="utf-8")
        subprocess.run(["node", str(ROOT / "tools/reference-batch.mjs"), str(request), str(response)], cwd=ROOT, check=True)
        results = json.loads(response.read_text("utf-8"))
        for (name, accepted, out, data), result in zip(expected, results, strict=True):
            assert result["ok"] == accepted, (name, result)
            if not accepted:
                assert "EDF+ data record exceeds 61440 bytes" in result["error"], (name, result)
                if out:
                    assert not out.exists(), "failed transform must not write output"
            elif out:
                assert out.read_bytes() == data, "copy must preserve signed sample bytes"
            checks.append(dict(name=name, accepted=accepted, input_sha256=hashlib.sha256(data).hexdigest(), result=result))
        for src, data in sources:
            assert src.read_bytes() == data, "input was changed"
    receipt = dict(status="passed", python=platform.python_version(), oracle="Original fixed-width bytes; EDF+ 2.1.2 / guidelines item 4", checks=checks)
    args.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"Passed {len(checks)} record-size checks")


if __name__ == "__main__":
    main()
