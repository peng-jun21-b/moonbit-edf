"""Exact header-value oracle + pinned PyEDFlib interoperability (MIT fixtures).

After building the JS bridge, pass --output /a/new/report.json. The retained
<stem>-cases directory contains raw fixed-width inputs, commands, responses and
products. Reuses the original byte fixture writer, never the MoonBit writer.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import platform
import runpy
import subprocess
import pyedflib

ROOT = Path(__file__).resolve().parents[1]
fixture = runpy.run_path(str(ROOT / "tools/check-crop-repair.py"))["fixture"]


def fields(path):
    data = path.read_bytes()
    ns, header = int(data[252:256]), int(data[184:192])
    width = 3 if data[:8] == b"\xffBIOSEMI" else 2
    lower = F(data[256 + ns * 104:264 + ns * 104].decode().strip())
    upper = F(data[256 + ns * 112:264 + ns * 112].decode().strip())
    duration = F(data[244:252].decode().strip())
    raw = data[header:header + 4 * width]
    digital = [int.from_bytes(raw[i:i+width], "little", signed=True) for i in range(0,len(raw),width)]
    return lower, upper, duration, raw, digital


def interop(path, expected):
    lower, upper, _, _, digital = expected
    with pyedflib.EdfReader(str(path)) as reader:
        # EDFlib's decimal conversion differs from Python by one ULP already
        # for the original 12345e-9 fixture. Exact preservation is asserted on
        # Fraction(header bytes), not by demanding identical parser rounding.
        assert math.isclose(reader.getPhysicalMinimum(0),float(lower),rel_tol=1e-12,abs_tol=0)
        assert math.isclose(reader.getPhysicalMaximum(0),float(upper),rel_tol=1e-12,abs_tol=0)
        assert reader.readSignal(0, digital=True).tolist() == digital
        physical = reader.readSignal(0)
        # Independent C reader for supported continuous calibration/sample IO;
        # exact decimal fields and rational clock are checked above, not here.
        magnitude = max(abs(float(lower)),abs(float(upper)))
        assert math.isclose(float(physical[0]),float(lower),rel_tol=1e-12,abs_tol=magnitude*1e-12)
        assert math.isclose(float(physical[-1]),float(upper),rel_tol=1e-12,abs_tol=magnitude*1e-12)


def main():
    parser = argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    work=args.output.parent/(args.output.stem+"-cases");work.mkdir()
    cases=[("0","12345e-9","1"),("-1234e-8","0","1"),
           ("-.123456",".1234567",".1234567"),("0","1e-100","1"),
           ("-1e100","1e100","1"),("-1234567","12345678","1"),
           ("100","-100","12345e-9"),("0","1234e8","1")]
    tasks=[];expected=[];sources=[];source_interop=[]
    for fmt in ["edf","bdf"]:
        for i,(lo,hi,duration) in enumerate(cases):
            source=work/f"source-{fmt}-{i}.{fmt}"
            fixture(source,fmt,[4],["+0"],duration=duration,mode="C")
            data=bytearray(source.read_bytes());ns=int(data[252:256])
            for offset,value in [(256+ns*104,lo),(256+ns*112,hi)]:
                assert len(value)<=8;data[offset:offset+8]=value.encode().ljust(8,b" ")
            source.write_bytes(data);known=fields(source)
            interop(source,known);source_interop.append(source.name)
            sources.append(dict(path=str(source),sha256=hashlib.sha256(data).hexdigest()))
            for command in ["calibrate","crop-time","create"]:
                out=work/f"{fmt}-{i}-{command}.{fmt}"
                options=dict(command=command,signal=0,scale=1,start="0",end=duration)
                if command=="create":
                    options=dict(command="create",format=fmt,duration=duration,signals=[dict(label="raw0",samples_per_record=4,physical_min=float(F(lo)),physical_max=float(F(hi)))],records=[dict(onset="0",samples=[known[4]],events=[])])
                tasks.append(dict(kind="transform",input=None if command=="create" else str(source),output=str(out),options=options))
                expected.append((out,known,None))
    for name,options,message in [
        ("unwritable-physical",dict(command="calibrate",signal=0,scale=1,offset=1.23456789012345),"eight-byte"),
        ("unwritable-duration",dict(command="create",duration=".123456789012345",signals=[dict(label="raw",samples_per_record=1)],records=[dict(onset="0",samples=[[0]],events=[])]),"eight-byte")]:
        out=work/(name+".edf")
        tasks.append(dict(kind="transform",input=sources[0]["path"] if options["command"]!="create" else None,output=str(out),options=options))
        expected.append((out,None,message))
    request,response=work/"tasks.json",work/"results.json"
    request.write_text(json.dumps(tasks),encoding="utf-8")
    subprocess.run(["node",str(ROOT/"tools/reference-batch.mjs"),str(request),str(response)],cwd=ROOT,check=True)
    results=json.loads(response.read_text());receipts=[]
    for (out,known,error),result in zip(expected,results,strict=True):
        assert result["ok"]==(error is None),(out.name,result)
        if error:
            assert error in result["error"] and not out.exists(),(out.name,result)
        else:
            actual=fields(out)
            assert actual==known,(out.name,actual,known)
            interop(out,actual)
        receipts.append(dict(name=out.name,passed=True,expected_error=error,sha256=hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else None))
    for source in sources:
        assert hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest()==source["sha256"]
    args.output.write_text(json.dumps(dict(status="passed",python=platform.python_version(),pyedflib=pyedflib.__version__,oracle="Original raw header fixtures, exact Fraction field values, independent C reader for continuous calibration/digital IO",sourceInterop=source_interop,checks=receipts,sources=sources,artifacts=str(work)),indent=2),encoding="utf-8")
    print(f"Passed {len(receipts)} transformations/error checks and {len(source_interop)} source interoperability checks")


if __name__=="__main__":
    main()
