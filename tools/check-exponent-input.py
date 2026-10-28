"""Bounded real-CLI checks for exponent errors and valid exact zeros.

Uses Python integer metadata arithmetic and Fraction for independent expected
values. Each Node child has a 64MiB heap budget and an eight-second deadline.
Original synthetic fixture bytes/commands/outputs are retained (project MIT).
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.set_int_max_str_digits(0)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--input",type=Path);args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    work=args.output.parent/(args.output.stem+"-cases");work.mkdir()
    source=work/"source.edf"
    if args.input:
        source.write_bytes(args.input.read_bytes())
    else:
        fixture=runpy.run_path(str(ROOT/"tools/check-crop-repair.py"))["fixture"]
        fixture(source,"edf",[4],["+0"],mode="C")
    data=source.read_bytes();before=hashlib.sha256(data).hexdigest()
    ns,header=int(data[252:256]),int(data[184:192]);per=int(data[256+ns*216:264+ns*216])
    assert data[:8]==b"0       " and int(data[236:244])==1
    duration=F(data[244:252].decode().strip())
    digital=[int.from_bytes(data[header+2*j:header+2*j+2],"little",signed=True) for j in range(per)]
    rows=[]
    def run(name,command):
        result=subprocess.run(["node","--max-old-space-size=64","--stack-size=512",str(ROOT/"tools/edf.mjs"),*command],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
        out,err=result.stdout.decode(),result.stderr.decode()
        (work/(name+".stdout")).write_text(out,encoding="utf-8");(work/(name+".stderr")).write_text(err,encoding="utf-8")
        row=dict(name=name,command=["node","--max-old-space-size=64","--stack-size=512",str(ROOT/"tools/edf.mjs"),*command],exitCode=result.returncode,stdout=out,stderr=err)
        rows.append(row);return row
    # Expected scale uses Python's unbounded integers, without huge powers.
    limits=[("1e-2147483648",0,-2147483648),("0.1e-2147483647",1,-2147483647),("1.234e-2147483646",3,-2147483646),("1e2147483647",0,2147483647)]
    metadata=[]
    for i,(text,scale,exponent) in enumerate(limits):
        effective=scale-exponent
        assert effective>2**31-4 or -effective+2>2**31-1
        metadata.append(dict(input=text,effectiveScale=effective,expected="Limit"))
        options=work/f"limit-{i}.json";options.write_text(json.dumps(dict(signal=0,start=text,end="1")))
        result=run(f"limit-{i}",["window",str(source),str(options)])
        assert result["exitCode"]==2 and "Limit(" in result["stderr"],result
        assert "RangeError" not in result["stderr"] and "Maximum BigInt" not in result["stderr"]
    for i,text in enumerate(["0e2147483647","0e-2147483648","-0e2147483647","0.000e-2147483648","1e-5000"]):
        lower=F(0) if i<4 else F(1,10**5000)
        options=work/f"window-{i}.json";options.write_text(json.dumps(dict(signal=0,start=text,end="1",time_tolerance="0e2147483647")))
        result=run(f"window-{i}",["window",str(source),str(options)])
        assert result["exitCode"]==0,result
        value=json.loads(result["stdout"])
        expect=[(j,v,duration*F(j,per)) for j,v in enumerate(digital) if lower<=duration*F(j,per)<1]
        actual=[(s["sample"],s["digital"],F(int(s["time_numerator"]),int(s["time_denominator"]))) for s in value["samples"]]
        assert actual==expect and F(value["start"])==lower
    for i,text in enumerate(["0e+","0eNaN","0e2147483648","0e2147483647/0e-2147483648"]):
        options=work/f"invalid-{i}.json";options.write_text(json.dumps(dict(signal=0,start=text,end="1")))
        result=run(f"invalid-{i}",["window",str(source),str(options)])
        assert result["exitCode"]==2 and "Invalid(" in result["stderr"],result
    # Unquoted JSON number lexemes must also preserve and normalize exact zero.
    raw=work/"raw-zero.json";raw.write_text('{"signal":0,"start":0e2147483647,"end":1}')
    result=run("raw-zero",["window",str(source),str(raw)]);assert result["exitCode"]==0
    assert len(json.loads(result["stdout"])["samples"])==per
    creation=work/"zero-create.json"
    creation.write_text('{"duration":0e2147483647,"signals":[],"records":[{"onset":0e-2147483648,"samples":[],"events":[{"onset":0e2147483647,"text":"zero"}]}]}')
    out=work/"zero-created.edf";result=run("zero-create",["create",str(out),str(creation)]);assert result["exitCode"]==0,result
    made=out.read_bytes();assert F(made[244:252].decode().strip())==0 and int(made[236:244])==1
    assert b"+0\x14\x14zero\x14\0" in made[int(made[184:192]):]
    creation=work/"limited-create.json";creation.write_text('{"duration":"1e-2147483648","signals":[],"records":[]}')
    bad=work/"must-not-exist.edf";result=run("limited-create",["create",str(bad),str(creation)])
    assert result["exitCode"]==2 and "Limit(" in result["stderr"] and not bad.exists(),result
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    args.output.write_text(json.dumps(dict(status="passed",python=platform.python_version(),oracle="Python integer scale arithmetic; zero algebra and Fraction sample-clock enumeration",source=dict(path=str(source),sha256=before,original=str(args.input) if args.input else None),scaleExpectations=metadata,checks=rows,artifacts=str(work)),indent=2),encoding="utf-8")
    print(f"Passed {len(rows)} bounded CLI checks; inputs retained at {work}")


if __name__=="__main__":
    main()
