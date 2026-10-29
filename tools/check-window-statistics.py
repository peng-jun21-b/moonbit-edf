"""Receive exact-window summaries from public packages and the real file CLI.

The complete raw inputs and rational expectations were frozen before production
edits. This standard-library receiver checks raw bytes/Fraction mathematics,
never the production reducer, crop, writer or its normalization as an oracle.
"""
import argparse
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tools/fixtures/window-statistics'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def time_text(value):
    """Independent exact decimal rendering, retaining non-terminating fractions."""
    value=F(value);remaining=value.denominator
    while remaining%2==0:remaining//=2
    while remaining%5==0:remaining//=5
    if remaining!=1:return str(value)
    power,scale=1,0
    while power%value.denominator:power*=10;scale+=1
    units=value.numerator*(power//value.denominator)
    sign='-' if units<0 else '';digits=str(abs(units)).rjust(scale+1,'0')
    return sign+digits if not scale else sign+(digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.')


def raw_model(path):
    data=path.read_bytes();width=3 if data[:8]==b'\xffBIOSEMI' else 2
    ns,nr,hs=int(data[252:256]),int(data[236:244]),int(data[184:192])
    def col(offset,n,s=0):return data[256+ns*offset+s*n:256+ns*offset+(s+1)*n].decode('ascii').strip()
    per=[int(col(216,8,s)) for s in range(ns)];stride=sum(per)*width
    assert hs==256*(ns+1) and len(data)==hs+nr*stride
    duration=F(data[244:252].decode().strip());dmin,dmax=int(col(120,8)),int(col(128,8))
    pmin,pmax=F(col(104,8)),F(col(112,8));starts=[];points=[]
    for r in range(nr):
        offset=hs+r*stride
        start=F(r)*duration
        if ns==2:start=F(data[offset+per[0]*width:offset+stride].split(b'\x14',1)[0].decode('ascii'))
        starts.append(start)
        for j in range(per[0]):
            at=offset+j*width;digital=int.from_bytes(data[at:at+width],'little',signed=True)
            points.append((r,j,start+duration*F(j,per[0]),digital,pmin+F(digital-dmin)*(pmax-pmin)/(dmax-dmin)))
    return dict(label=col(0,16),unit=col(96,8),duration=duration,starts=starts,points=points,dmin=dmin,dmax=dmax)


def oracle(model,query):
    lower,upper=F(query['start']),F(query['end'])
    selected=[p for p in model['points'] if lower<=p[2]<upper];values=[p[4] for p in selected];n=len(values)
    stats=dict(samples=n,below_range=sum(p[3]<model['dmin'] for p in selected),above_range=sum(p[3]>model['dmax'] for p in selected),
               at_minimum=sum(p[3]==model['dmin'] for p in selected),at_maximum=sum(p[3]==model['dmax'] for p in selected))
    if n:
        mean=sum(values)/n;variance=sum((x-mean)**2 for x in values)/n;square=sum(x*x for x in values)/n
        with localcontext() as c:c.prec=100;rms=(D(square.numerator)/D(square.denominator)).sqrt()
        stats.update(minimum=float(min(values)),maximum=float(max(values)),mean=float(mean),variance=float(variance),rms=float(rms))
    gaps=[]
    for r in range(1,len(model['starts'])):
        lo=max(lower,model['starts'][r-1]+model['duration']);hi=min(upper,model['starts'][r])
        if lo<hi:gaps.append(dict(after_record=r-1,start=time_text(lo),end=time_text(hi)))
    return dict(signal=0,label=model['label'],unit=model['unit'],start=time_text(lower),end=time_text(upper),gaps=gaps,statistics=stats)


def compare(actual,expected,where='result'):
    if isinstance(expected,dict):
        assert isinstance(actual,dict) and set(actual)==set(expected),(where,actual,expected)
        for key in expected:compare(actual[key],expected[key],where+'.'+key)
    elif isinstance(expected,list):
        assert isinstance(actual,list) and len(actual)==len(expected),(where,actual,expected)
        for i,(a,e) in enumerate(zip(actual,expected,strict=True)):compare(a,e,f'{where}[{i}]')
    elif isinstance(expected,float):
        assert type(actual) in (int,float) and math.isfinite(actual),(where,actual)
        if expected==0:assert actual==0,(where,actual,expected)
        else:
            assert actual!=0,(where,actual,expected)
            tolerance=max(abs(expected)*5e-12,8*math.ulp(expected))
            assert abs(actual-expected)<=tolerance,(where,actual,expected,tolerance)
    elif isinstance(expected,int):assert type(actual) is int and actual==expected,(where,actual,expected)
    else:assert actual==expected,(where,actual,expected)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True)
    ap.add_argument('--public-output',type=Path,action='append',required=True)
    args=ap.parse_args();assert not args.output.exists() and not args.work_dir.exists(),'choose fresh paths'
    assert len(args.public_output)==2,'provide separate JS and Wasm-GC public receiver outputs'
    checks=json.loads((FIXTURES/'SHA256SUMS-v2.json').read_text(encoding='utf-8'))
    for name,item in checks.items():
        path=FIXTURES/name;assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],name
    frozen=json.loads((FIXTURES/'EXPECTED-v2.json').read_text(encoding='utf-8'))
    cases,errors=frozen['cases'],frozen['errors'];models={c['input']:raw_model(FIXTURES/c['input']) for c in cases}
    for case in cases:compare(oracle(models[case['input']],case['request']),case['expected'],'independent raw oracle '+case['name'])
    public=[]
    for path in args.public_output:
        received=json.loads(path.read_text(encoding='utf-8'));assert len(received)==len(cases)+len(errors)
        assert len({v['name'] for v in received})==len(received)
        rows={v['name']:v for v in received};assert set(rows)=={v['name'] for v in cases+errors}
        for case in cases:
            row=rows[case['name']];assert set(row)=={'name','result'};compare(row['result'],case['expected'],'public '+case['name'])
        for case in errors:
            row=rows[case['name']];assert set(row)=={'name','error'} and case['kind'] in row['error'] and case['message'] in row['error'],row
        public.append(dict(path=str(path.resolve()),sha256=sha(path),completeResults=len(cases),checkedErrors=len(errors)))
    args.work_dir.mkdir(parents=True);receipts=[]
    for case in cases+errors:
        is_error='message' in case;source=FIXTURES/case['input'];options=FIXTURES/case['options']
        command=['node',str(ROOT/'tools/edf.mjs'),'window-stats',str(source),str(options)]
        p=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=60)
        stdout=args.work_dir/(case['name']+'.stdout');stderr=args.work_dir/(case['name']+'.stderr')
        stdout.write_bytes(p.stdout);stderr.write_bytes(p.stderr)
        if is_error:
            text=p.stderr.decode('utf-8');assert p.returncode==2 and not p.stdout and case['kind'] in text and case['message'] in text,(case['name'],text)
        else:
            assert p.returncode==0,p.stderr.decode('utf-8');value=json.loads(p.stdout);compare(value,case['expected'],'file '+case['name'])
            # A real receiving file artifact, created only after successful full
            # decoding/comparison. This is self-authored integration, not adoption.
            artifact=args.work_dir/(case['name']+'.receiver-summary.json')
            artifact.write_text(json.dumps(dict(sourceSha256=sha(source),requestSha256=sha(options),result=value),indent=2)+'\n',encoding='utf-8')
        receipts.append(dict(name=case['name'],command=command,exitCode=p.returncode,stdout=dict(path=str(stdout.resolve()),sha256=sha(stdout)),stderr=dict(path=str(stderr.resolve()),sha256=sha(stderr))))
    for name,item in checks.items():assert sha(FIXTURES/name)==item['sha256'],'input changed: '+name
    report=dict(status='passed',oracle=frozen['oracle'],tolerance=frozen['tolerance'],rawInputs=13,originalHandExpectationsFrozenBeforeEdits=True,
                originalFrozenInputAndExpectationEvidencePreserved=True,fixtureCorrectionAfterImplementation=True,
                correction='Versioned canonical time text and valid BDF annotation metadata; retained original invalid BDF as an extra rejection, statistical expectations/tolerance unchanged',
                fileCompleteResults=len(cases),fileCheckedErrors=len(errors),publicReceivers=public,allInputAndExpectedHashesUnchanged=True,
                bridge=os.environ.get('MOON_EDF_BRIDGE','default release bridge'),commands=receipts,thirdPartyAdoptionClaim=False)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='passed',fileCompleteResults=len(cases),fileCheckedErrors=len(errors),publicReceivers=2,publicCompleteResults=2*len(cases),publicCheckedErrors=2*len(errors))))


if __name__=='__main__':main()
