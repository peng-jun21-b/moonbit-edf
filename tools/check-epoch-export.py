"""Independent raw EDF/BDF/Fraction acceptance of the generic epoch file handoff.

Development-only standard library. No MoonBit writer, downloads, resampling or
reference implementation supplies expected samples. All files/calls are kept.
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

ROOT=Path(__file__).resolve().parents[1]
RAW=runpy.run_path(str(ROOT/"tools/check-append.py"))
annotations=runpy.run_path(str(ROOT/"tools/check-annotation-query.py"))["original_annotations"]
COLUMNS="signal,label,record,sample,time_seconds,time_numerator,time_denominator,value,unit".split(",")


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def text(raw,column,signal):return raw["columns"][column][signal].decode("ascii").strip()
def rational(value):return F(int(value["numerator"]),int(value["denominator"]))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",type=Path,required=True);ap.add_argument("--work-dir",type=Path,required=True)
    args=ap.parse_args();assert not args.output.exists() and not args.work_dir.exists(),"choose fresh paths"
    args.work_dir.mkdir(parents=True);work=args.work_dir.resolve();sources={}
    for name,fmt,starts,mode,events in [
        ("continuous","edf",["+0","+1"],"C",{(0,0):[("+0.5",None,'选择,\t"甲"\n换行\r结束'),("+0.5","0","zero"),("+0.5","0.5","duration")]}),
        ("islands","bdf",["+0","+2"],"D",{(0,0):[("+2.25","0","island"),("+1.25",None,"gap")]}),
        ("tolerance","edf",["+0","+1.000000000000000000001"],"C",{(0,0):[("+0.5",None,"tolerated")]})]:
        path=work/(name+"."+fmt);RAW["make"](path,fmt,[3,4],starts,mode=mode,events=events)
        RAW["change"](path,0,0,'EEG,"A"',16);RAW["change"](path,0,1,'ECG,"B"',16)
        RAW["change"](path,96,0,"");RAW["change"](path,96,1,"mV")
        sources[name]=dict(path=path,raw=RAW["read_raw"](path),sha256=sha(path))
    commands=[]

    def run(name,source,options,output=None):
        output=output or work/(name+"-output")
        options_path=work/(name+".json")
        options_path.write_text(options if isinstance(options,str) else json.dumps(options),encoding="utf-8")
        cmd=["node",str(ROOT/"examples/export-epoch.mjs"),str(source["path"]),str(output),str(options_path)]
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=60)
        commands.append(dict(name=name,command=cmd,exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        assert sha(source["path"])==source["sha256"]
        return p,output

    base=dict(annotation=0,signals=[1,0],before="0.25",after="0.25",max_samples=100)
    long_options=json.dumps(base).replace('"after": "0.25"','"after": 0.250000000000000000001')
    cases=[("bare-exact-padding","continuous",long_options),
           ("zero-duration-digital","continuous",dict(base,annotation=1,before="1/3",after="1/3",physical=False)),
           ("ignore-duration","continuous",dict(base,annotation=2,include_duration=False)),
           ("include-duration","continuous",dict(base,annotation=2)),
           ("continuous-island","islands",dict(base,before="0.25",after="0.5")),
           ("retain-gap","islands",dict(base,before="1.5",after="0.5",allow_partial=True)),
           ("empty-gap","islands",dict(base,annotation=1,before="0",after="0.25",allow_partial=True)),
           ("forward-tolerance","tolerance",dict(base,time_tolerance=1e-21))]
    verified=[]
    for name,source_name,options in cases:
        source=sources[source_name];raw=source["raw"]
        requested=json.loads(options,parse_float=str) if isinstance(options,str) else options
        p,output=run(name,source,options);assert p.returncode==0,p.stderr
        document=json.loads((output/"epoch.json").read_text(encoding="utf-8"));got=document["result"]
        assert document["source"]==dict(path=str(source["path"].resolve()),bytes=source["path"].stat().st_size,sha256=source["sha256"])
        event=annotations(raw)[requested["annotation"]]
        onset=F(event["onset"]);duration=F(event.get("duration","0")) if requested.get("include_duration",True) else F(0)
        lower=onset-F(str(requested["before"]));upper=onset+duration+F(str(requested["after"]))
        gaps=[dict(after_record=r-1,start=max(lower,raw["starts"][r-1]+raw["duration"]),end=min(upper,raw["starts"][r]))
              for r in range(1,raw["nr"]) if max(lower,raw["starts"][r-1]+raw["duration"])<min(upper,raw["starts"][r])]
        complete=lower>=raw["starts"][0] and upper<=raw["starts"][-1]+raw["duration"] and not gaps
        assert got["annotation_index"]==requested["annotation"] and got["annotation"]==event
        assert F(got["start"])==lower and F(got["end"])==upper and got["complete"]==complete
        assert [c["signal"] for c in got["channels"]]==requested["signals"]
        expected_rows=[]
        for channel,signal in zip(got["channels"],requested["signals"],strict=True):
            expected=[v for v in raw["points"][signal] if lower<=v[3]<upper]
            assert (channel["label"],channel["unit"])==(text(raw,0,signal),text(raw,2,signal))
            assert F(channel["start"])==lower and F(channel["end"])==upper
            assert [(v["after_record"],F(v["start"]),F(v["end"])) for v in channel["gaps"]]==[(v["after_record"],v["start"],v["end"]) for v in gaps]
            assert len(channel["samples"])==len(expected)
            pmin,pmax=F(text(raw,3,signal)),F(text(raw,4,signal));dmin,dmax=F(text(raw,5,signal)),F(text(raw,6,signal))
            for sample,(record,j,digital,t) in zip(channel["samples"],expected,strict=True):
                physical=pmin+(digital-dmin)*(pmax-pmin)/(dmax-dmin)
                assert (sample["record"],sample["sample"],sample["digital"],rational(sample["time"]))==(record,j,digital,t)
                assert F(int(sample["time_numerator"]),int(sample["time_denominator"]))==t
                assert math.isclose(sample["physical"],float(physical),rel_tol=1e-12,abs_tol=1e-10)
                expected_rows.append((signal,record,j,digital,t,physical))
        assert got["samples"]==len(expected_rows)
        csv_path=output/"samples.csv"
        assert document["csv"]==dict(file="samples.csv",sha256=sha(csv_path),physical=requested.get("physical",True))
        assert document["request"]["command"]=="epoch"
        for key in ["before","after","time_tolerance"]:
            if key in requested:assert F(str(document["request"][key]))==F(str(requested[key]))
        with csv_path.open(encoding="utf-8",newline="") as f:
            reader=csv.DictReader(f);assert reader.fieldnames==COLUMNS;rows=list(reader)
        assert len(rows)==len(expected_rows)
        for row,(signal,record,j,digital,t,physical) in zip(rows,expected_rows,strict=True):
            assert (int(row["signal"]),row["label"],int(row["record"]),int(row["sample"]))==(signal,text(raw,0,signal),record,j)
            assert F(row["time_seconds"])==F(int(row["time_numerator"]),int(row["time_denominator"]))==t
            assert row["unit"]==(text(raw,2,signal) if requested.get("physical",True) else "digital")
            if requested.get("physical",True):assert math.isclose(float(row["value"]),float(physical),rel_tol=1e-12,abs_tol=1e-10)
            else:assert int(row["value"])==digital
        verified.append(dict(name=name,source=str(source["path"]),output=str(output),rows=len(rows),complete=complete,annotation=event,start=str(lower),end=str(upper),files=[dict(path=str(q),sha256=sha(q)) for q in sorted(output.iterdir())]))
    by_name={v["name"]:v for v in verified}
    assert by_name["bare-exact-padding"]["rows"]>by_name["ignore-duration"]["rows"],"bare after lexeme must include the 0.75 sample"
    assert by_name["include-duration"]["rows"]>by_name["ignore-duration"]["rows"]
    assert by_name["empty-gap"]["rows"]==0 and by_name["empty-gap"]["complete"] is False
    errors=[]
    for name,source_name,options,message in [
        ("strict-gap","islands",dict(base,before="1.5"),"missing recording time"),
        ("strict-clock","tolerance",base,"continuous marker"),
        ("bad-annotation","continuous",dict(base,annotation=999),"annotation index"),
        ("duplicate-signals","continuous",dict(base,signals=[0,0]),"distinct"),
        ("annotation-channel","continuous",dict(base,signals=[2]),"ordinary signal"),
        ("shared-budget","continuous",dict(base,max_samples=1),"sample limit"),
        ("negative-padding","continuous",dict(base,before="-1"),"nonnegative")]:
        p,output=run(name,sources[source_name],options)
        assert p.returncode==2 and message in p.stderr and not output.exists(),p.stderr
        errors.append(dict(name=name,exitCode=p.returncode,noOutput=True,message=message))
    existing=work/"bare-exact-padding-output";(existing/"user.txt").write_bytes(b"retain\r\n")
    before={q.name:sha(q) for q in existing.iterdir()}
    p,_=run("existing-output",sources["continuous"],base,existing)
    assert p.returncode==2 and "output directory exists" in p.stderr and before=={q.name:sha(q) for q in existing.iterdir()}
    errors.append(dict(name="existing-output",exitCode=2,allExistingFilesUnchanged=True))
    report=dict(status="passed",oracle="Independent fixed-width/TAL raw reader, exhaustive Fraction native-clock enumeration and rational calibration; no MoonBit writer",cases=verified,errors=errors,csvColumns=COLUMNS,
                sources=[dict(path=str(s["path"]),sha256=s["sha256"],unchanged=sha(s["path"])==s["sha256"]) for s in sources.values()],oldGeneratorsOrDownloadsRun=0)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status="passed",exports=len(verified),csvRows=sum(v["rows"] for v in verified),errors=len(errors),sourceFiles=3)))


if __name__=="__main__":main()
