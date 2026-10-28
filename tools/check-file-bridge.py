"""Exercise real file consumers with an alternate build and no default bridge.

Development-only standard library. Copies only this project's host entrypoints
and the selected real compiled bridge into a fresh isolated layout. It does not
build, download, mock DSP or use the MoonBit writer for input expectations.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SHA = "3427c8d01bff1380bc9ab9f27a35ece2af5dfadf3e291bbc05eb66e4dadbfe2e"
RAW = runpy.run_path(str(ROOT/"tools/check-psd.py"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(directory):
    return {str(p.relative_to(directory)):sha(p) for p in directory.rglob("*") if p.is_file()}


def read_raw(path):
    """Independent tiny EDF+ reader: ordinary headers, signed samples and TALs."""
    data = path.read_bytes()
    ns, nr, hs = int(data[252:256]), int(data[236:244]), int(data[184:192])
    assert ns==2 and nr==2
    at, ordinary, per = 256, [], None
    for width in [16,80,8,8,8,8,8,80,8,32]:
        ordinary.append(data[at:at+width]); at+=ns*width
    assert at==hs
    per=[int(data[256+216*ns+s*8:256+216*ns+(s+1)*8]) for s in range(ns)]
    assert per[0]==4 and len(data)==hs+2*nr*sum(per)
    samples,starts,events=[],[],[]
    for record in range(nr):
        pos=hs+record*2*sum(per)
        samples.append([int.from_bytes(data[pos+2*j:pos+2*j+2],"little",signed=True) for j in range(4)])
        block=data[pos+8:pos+8+2*per[1]]
        for i,tal in enumerate(filter(None,block.split(b"\0"))):
            clock,*texts=tal.split(b"\x14");parts=clock.split(b"\x15")
            onset=F(parts[0].decode("ascii"));duration=F(parts[1].decode("ascii")) if len(parts)==2 else None
            if i==0:starts.append(onset)
            for text in filter(None,texts):events.append((record,onset,duration,text.decode("utf-8")))
    return dict(ordinary=ordinary,samples=samples,starts=starts,events=events)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bridge",type=Path,default=ROOT/"_build/js/release/build/cmd/bridge/bridge.js")
    ap.add_argument("--public-input",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--work-dir",type=Path,required=True)
    args=ap.parse_args()
    assert args.bridge.is_file() and sha(args.public_input)==PUBLIC_SHA
    assert not args.output.exists() and not args.work_dir.exists(),"choose fresh output paths"
    args.work_dir.mkdir(parents=True)
    work=args.work_dir.resolve();layout=work/"host-layout"
    host_files=[]
    for rel in ["tools/edf.mjs","examples/remove-window.mjs","examples/run-public-epochs.mjs"]:
        dest=layout/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dest)
        assert sha(dest)==sha(ROOT/rel)
        host_files.append(dict(source=str(ROOT/rel),copy=str(dest),sha256=sha(dest)))
    alternate=work/"alternate build # source/bridge.js"
    alternate.parent.mkdir();shutil.copyfile(args.bridge,alternate)
    default=layout/"_build/js/release/build/cmd/bridge/bridge.js"
    assert not default.exists() and sha(alternate)==sha(args.bridge)
    source=work/"events.edf"
    RAW["fixture"](source,[[[1,-2,3,-4],[5,-6,7,-8]]],starts=("+0","+1"))
    data=bytearray(source.read_bytes());hs=int(data[184:192]);stride=2*(4+128)
    for record,tail in [(0,b"+0.25\x150.5\x14drop\x14\0"),(1,b"+1.25\x14keep\x14\0")]:
        block=(f"+{record}".encode()+b"\x14\x14\0"+tail).ljust(256,b"\0")
        pos=hs+record*stride+8;data[pos:pos+256]=block
    source.write_bytes(data);source_sha=sha(source);original=read_raw(source)
    assert original["events"]==[(0,F(1,4),F(1,2),"drop"),(1,F(5,4),None,"keep")]
    commands=[]

    def run(name,entry,arguments,bridge):
        env=os.environ.copy();env.pop("MOON_EDF_BRIDGE",None)
        if bridge is not None:env["MOON_EDF_BRIDGE"]=str(bridge)
        command=["node",str(layout/entry),*map(str,arguments)]
        p=subprocess.run(command,cwd=work,env=env,capture_output=True,text=True,encoding="utf-8",timeout=90)
        commands.append(dict(name=name,command=command,bridgeSelection=str(bridge) if bridge is not None else "default",exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        return p

    edited=work/"alternate-edited.edf"
    p=run("alternate-delete","examples/remove-window.mjs",[source,edited,"0","1","drop"],alternate)
    assert p.returncode==0,p.stderr
    assert {k:v for k,v in json.loads(p.stdout).items() if k!="output"}==dict(matched=1,removed=1,remaining_in_window=0)
    result=read_raw(edited)
    assert result==dict(ordinary=original["ordinary"],samples=original["samples"],starts=[F(0),F(1)],events=[(1,F(5,4),None,"keep")])
    noop=work/"alternate-noop.edf"
    p=run("alternate-noop","examples/remove-window.mjs",[source,noop,"0","1","missing"],alternate)
    assert p.returncode==0 and noop.read_bytes()==source.read_bytes(),p.stderr
    public=work/"alternate-public"
    p=run("alternate-public-relative-path","examples/run-public-epochs.mjs",[args.public_input.resolve(),public],alternate.relative_to(work))
    assert p.returncode==0,p.stderr
    assert json.loads(p.stdout)["epochs"]==8
    # Apply the existing independent raw-EDF/Fraction checker only to these new
    # exports from the changed consumer; no old generator or download is rerun.
    public_receipt=work/"public-readback.json"
    p=subprocess.run([sys.executable,str(ROOT/"tools/verify-public-export.py"),str(args.public_input.resolve()),str(public),"--output",str(public_receipt)],
                     cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=90)
    assert p.returncode==0,p.stderr
    independent=json.loads(public_receipt.read_text(encoding="utf-8"));assert independent["rows"]==17664
    assert not default.exists(),"alternate cases must succeed without a default bridge"
    # Retain the ordinary default-build behavior, without mutating the checkout.
    default.parent.mkdir(parents=True);shutil.copyfile(args.bridge,default)
    default_edited=work/"default-edited.edf"
    p=run("default-delete","examples/remove-window.mjs",[source,default_edited,"0","1","drop"],None)
    assert p.returncode==0 and default_edited.read_bytes()==edited.read_bytes(),p.stderr
    default_public=work/"default-public"
    p=run("default-public","examples/run-public-epochs.mjs",[args.public_input.resolve(),default_public],None)
    assert p.returncode==0 and snapshot(default_public)==snapshot(public),p.stderr
    # An explicitly invalid alternate path must not silently use a valid default.
    invalid=work/"missing # bridge.js"
    for name,entry,arguments,output in [
        ("invalid-delete","examples/remove-window.mjs",[source,work/"invalid.edf","0","1"],work/"invalid.edf"),
        ("invalid-public","examples/run-public-epochs.mjs",[args.public_input.resolve(),work/"invalid-public"],work/"invalid-public")]:
        p=run(name,entry,arguments,invalid)
        assert p.returncode!=0 and "ERR_MODULE_NOT_FOUND" in p.stderr and not output.exists(),p.stderr
    before=sha(edited)
    p=run("existing-delete","examples/remove-window.mjs",[source,edited,"0","1","drop"],alternate)
    assert p.returncode==2 and "EEXIST" in p.stderr and sha(edited)==before,p.stderr
    before=snapshot(public)
    p=run("existing-public","examples/run-public-epochs.mjs",[args.public_input.resolve(),public],alternate)
    assert p.returncode!=0 and "EEXIST" in p.stderr and snapshot(public)==before,p.stderr
    unpinned=work/"unpinned-public"
    p=run("unpinned-public","examples/run-public-epochs.mjs",[source,unpinned],alternate)
    assert p.returncode!=0 and "Expected the pinned PhysioNet" in p.stderr and not unpinned.exists(),p.stderr
    assert sha(source)==source_sha and sha(args.public_input)==PUBLIC_SHA
    report=dict(status="passed",bridgeSHA256=sha(args.bridge),hostFiles=host_files,layout=str(layout),alternatePath=str(alternate),
                isolatedWithoutDefaultForAlternateCases=True,realConsumerCommands=commands,successes=5,checkedErrors=5,
                sourceSHA256=source_sha,sourceUnchanged=True,rawEditOracle="Original fixed-width ordinary headers and signed samples; TAL set subtraction with Fraction onsets/duration",
                publicReadback=independent,defaultAndAlternateProductsByteEqual=True,explicitInvalidOverrideDidNotFallback=True,
                outputProtectionPreserved=True,pinnedPublicInputGuardPreserved=True,unchangedGeneratorsOrDownloadsRun=0)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(status="passed",successes=5,checkedErrors=5,publicEpochs=8,publicRows=17664,defaultAndAlternateProductsByteEqual=True)))


if __name__=="__main__":
    main()
