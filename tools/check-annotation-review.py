"""Receive complete real annotation reviews against pre-implementation manual tables.

Standard library only. No product writer, comparator/helper, reference generator,
window filtering or result-derived expectations. Fraction validates the original
fixed-width/TAL files independently, including every duplicate occurrence.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tools/fixtures/annotation-review'
ENTRY=ROOT/'examples/annotation-review.mjs'

def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
def same(actual,expected,path='result'):
    if isinstance(expected,float):
        assert type(actual) in (int,float) and math.isfinite(actual) and actual==expected,(path,actual,expected)
    else:
        assert type(actual) is type(expected),(path,type(actual).__name__,type(expected).__name__)
        if isinstance(expected,dict):
            assert actual.keys()==expected.keys(),(path,actual.keys(),expected.keys())
            for k in expected:same(actual[k],expected[k],path+'.'+k)
        elif isinstance(expected,list):
            assert len(actual)==len(expected),(path,len(actual),len(expected))
            for i,(a,e) in enumerate(zip(actual,expected)):same(a,e,path+'['+str(i)+']')
        else:assert actual==expected,(path,actual,expected)

def decimal(value,signed=False):
    value=Fraction(value);n,d=value.numerator,value.denominator
    twos=fives=0
    while d%2==0:twos+=1;d//=2
    while d%5==0:fives+=1;d//=5
    assert d==1
    scale=max(twos,fives);coeff=abs(n)*(10**scale//value.denominator)
    digits=str(coeff).zfill(scale+1)
    text=(digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.') if scale else digits
    return ('-' if n<0 else '+' if signed else '')+text

def raw_source(path,policy):
    data=path.read_bytes();fmt='edf' if data[:8]==b'0       ' else 'bdf'
    assert data[:8] in (b'0       ',b'\xffBIOSEMI')
    width=2 if fmt=='edf' else 3
    text=lambda a,n:data[a:a+n].decode('ascii').strip(' ')
    ns=int(text(252,4));hs=int(text(184,8));assert hs==256+ns*256
    columns=[('label',16),('transducer',80),('unit',8),('physical_min',8),('physical_max',8),('digital_min',8),('digital_max',8),('prefilter',80),('samples_per_record',8),('reserved',32)]
    signals=[{} for _ in range(ns)];offset=256
    for field,size in columns:
        for signal in range(ns):
            value=text(offset+signal*size,size)
            if field.startswith('physical_'):value=float(value)
            if field.startswith('digital_') or field=='samples_per_record':value=int(value)
            signals[signal][field]=value
        offset+=size*ns
    stride=width*sum(s['samples_per_record'] for s in signals)
    assert (len(data)-hs)%stride==0
    records=(len(data)-hs)//stride
    assert int(text(236,8)) in (-1,records)
    starts=[];annotations=[]
    for record in range(records):
        offset=hs+record*stride;first=True
        for signal,s in enumerate(signals):
            size=width*s['samples_per_record'];block=data[offset:offset+size];offset+=size
            if s['label'] not in ('EDF Annotations','BDF Annotations'):continue
            blocks=block.split(b'\0')
            for j,b in enumerate(blocks):
                if not b:
                    assert all(not x for x in blocks[j:])
                    break
                clock,*texts=b.split(b'\x14');assert texts and texts[-1]==b'';texts.pop()
                parts=clock.split(b'\x15');assert len(parts) in (1,2)
                onset=parts[0].decode('ascii');duration=parts[1].decode('ascii') if len(parts)==2 else None
                if first:starts.append(Fraction(onset));first=False
                for value in texts:
                    value=value.decode('utf-8')
                    if value:annotations.append(dict(record=record,signal=signal,onset=onset,duration=duration,text=value))
    if not starts:starts=[Fraction(text(244,8))*r for r in range(records)]
    duration=text(244,8);gaps=[]
    for r in range(1,records):
        end=starts[r-1]+Fraction(duration)
        if starts[r]>end:gaps.append(dict(after_record=r-1,start=decimal(end),end=decimal(starts[r])))
    dd,mm,yy=map(int,text(168,8).split('.'));hour,minute,second=map(int,text(176,8).split('.'))
    reserve=text(192,44)
    context=dict(format=fmt,continuity='continuous' if reserve.endswith('+C') else 'discontinuous' if reserve.endswith('+D') else 'plain',patient=text(8,80),recording=text(88,80),date=text(168,8),time=text(176,8),start=dict(year=1900+yy if yy>=85 else 2000+yy,month=mm,day=dd,hour=hour,minute=minute,second=second),timezone='unspecified_local_civil',records=records,declared_records=int(text(236,8)),duration=duration,signals=signals,starts=[decimal(s,True) for s in starts],gaps=gaps,annotations=len(annotations),time_tolerance=policy)
    return dict(context=context,annotations=annotations)

def key(annotation):
    return (Fraction(annotation['onset']),None if annotation['duration'] is None else Fraction(annotation['duration']),annotation['text'])
def exact_time(value):return Fraction(int(value['numerator']),int(value['denominator']))
def receive(review,expected):
    same(review,expected)
    witnessed={'left':[],'right':[]}
    for group in review['groups']:
        k=(exact_time(group['onset']),None if group['duration'] is None else exact_time(group['duration']),group['text'])
        for side in witnessed:
            entries=review[side]['annotations'];indices=group[side+'_indices']
            assert indices==[i for i,a in enumerate(entries) if key(a)==k]
            assert group[side]==len(indices)
            witnessed[side]+=indices
        assert group['left']==group['retained']+group['removed']
        assert group['right']==group['retained']+group['added']
    for side in witnessed:assert sorted(witnessed[side])==list(range(len(review[side]['annotations'])))
    for count in ('retained','removed','added'):assert review['totals'][count]==sum(g[count] for g in review['groups'])
    assert review['totals']['left']==review['totals']['retained']+review['totals']['removed']
    assert review['totals']['right']==review['totals']['retained']+review['totals']['added']

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True)
    ap.add_argument('--public-output',type=Path,action='append',required=True)
    args=ap.parse_args();assert not args.output.exists() and not args.work_dir.exists(),'choose fresh output paths'
    args.work_dir.mkdir(parents=True);work=args.work_dir.resolve();model=json.loads((FIXTURES/'EXPECTED.json').read_bytes())
    cases=model['cases'];expected={c['name']:c for c in cases};errors={e['name']:e for e in model['errors']}
    input_before={p.name:sha(p.read_bytes()) for p in FIXTURES.iterdir() if p.is_file()}
    for name,item in model['rawIdentities'].items():assert len((FIXTURES/name).read_bytes())==item['bytes'] and input_before[name]==item['sha256']
    for c in cases:
        for side in ('left','right'):
            actual=raw_source(FIXTURES/c[side],c[side+'Tolerance'])
            same(actual,c['expected'][side],c['name']+'.independent_raw.'+side)
        receive(c['expected'],c['expected'])
    public=[]
    for path in args.public_output:
        data=json.loads(path.read_bytes());assert len(data)==len(cases)+sum(e['public'] for e in errors.values())
        assert [row['name'] for row in data]==list(expected)+[e['name'] for e in errors.values() if e['public']]
        for row in data:
            if row['name'] in expected:
                c=expected[row['name']];assert set(row)=={'name','result','left_source','right_source','left_after','right_after'}
                receive(row['result'],c['expected'])
                for side in ('left','right'):
                    raw=(FIXTURES/c[side]).read_bytes();assert bytes(row[side+'_source'])==bytes(row[side+'_after'])==raw
            else:
                assert row==dict(name=row['name'],error=errors[row['name']]['error'])
        public.append(dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=sha(path.read_bytes()),completeResults=len(cases),completeErrors=sum(e['public'] for e in errors.values())))
    commands=[]
    def invoke(name,args,success,error=None,extra_env=None):
        env=dict(os.environ,**(extra_env or {}));p=subprocess.run(['node',*map(str,args)],cwd=ROOT,env=env,capture_output=True,timeout=90)
        stdout=work/(name+'.stdout');stderr=work/(name+'.stderr');stdout.write_bytes(p.stdout);stderr.write_bytes(p.stderr)
        row=dict(name=name,command=['node',*map(str,args)],exitCode=p.returncode,stdout=str(stdout),stderr=str(stderr));commands.append(row);save(work/'COMMANDS.json',commands)
        assert (p.returncode==0)==success,(name,p.returncode,p.stderr.decode('utf-8',errors='replace'))
        if error:assert error in p.stderr.decode('utf-8'),(name,error,p.stderr.decode('utf-8'))
        return p
    bundles=[];sidecars=0;first=None
    bridge=Path(os.environ.get('MOON_EDF_BRIDGE',ROOT/'_build/js/release/build/cmd/bridge/bridge.js')).resolve();bridge_hash=sha(bridge.read_bytes())
    for c in cases:
        folder=work/c['name'];folder.mkdir();left=folder/('修订前 #.'+Path(c['left']).suffix.lstrip('.'));right=folder/('修订后 #.'+Path(c['right']).suffix.lstrip('.'))
        shutil.copyfile(FIXTURES/c['left'],left);shutil.copyfile(FIXTURES/c['right'],right)
        options=folder/'read.json';shutil.copyfile(FIXTURES/c['readOptions'],options);output=folder/'review'
        before=(left.read_bytes(),right.read_bytes(),options.read_bytes())
        invoke(c['name'],[ENTRY,left,right,output,options],True)
        assert {p.name for p in output.iterdir()}=={'left-inspect.json','right-inspect.json','left-annotations.json','right-annotations.json','comparison.json','manifest.json'}
        manifest=json.loads((output/'manifest.json').read_bytes());review=json.loads((output/'comparison.json').read_bytes());receive(review,c['expected'])
        assert manifest.keys()=={'sources','frame','status','totals','read_options_sha256','implementation','files'}
        for field in ('frame','status','totals'):same(manifest[field],review[field])
        assert manifest['read_options_sha256']==sha(before[2])
        same(manifest['implementation'],dict(module='peng-jun21-b/edf',version='0.14.0',bridge_sha256=bridge_hash))
        assert len(manifest['files'])==5 and {r['file'] for r in manifest['files']}=={p.name for p in output.iterdir()}-{'manifest.json'}
        for item in manifest['files']:
            data=(output/item['file']).read_bytes();assert len(data)==item['bytes'] and sha(data)==item['sha256'];sidecars+=1
        for side,path,raw in [('left',left,before[0]),('right',right,before[1])]:
            same(json.loads((output/(side+'-inspect.json')).read_bytes()),review[side]['context'])
            same(json.loads((output/(side+'-annotations.json')).read_bytes()),review[side]['annotations'])
            same(manifest['sources'][side],dict(path=str(path.resolve()),bytes=len(raw),sha256=sha(raw),annotations=len(review[side]['annotations']),time_tolerance=review[side]['context']['time_tolerance']))
        assert (left.read_bytes(),right.read_bytes(),options.read_bytes())==before
        bundles.append(dict(name=c['name'],output=str(output),manifestSha256=sha((output/'manifest.json').read_bytes()),totals=review['totals'],status=review['status']))
        if first is None:first=(left,right,options,output)
    left,right,options,output=first
    snapshot={p.name:sha(p.read_bytes()) for p in output.iterdir()}
    invoke('occupied',[ENTRY,left,right,output,options],False,'output directory exists')
    assert snapshot=={p.name:sha(p.read_bytes()) for p in output.iterdir()}
    for e in errors.values():
        output=work/('error-'+e['name'])
        invoke(e['name'],[ENTRY,FIXTURES/e['left'],FIXTURES/e['right'],output,FIXTURES/e['readOptions']],False,e['error'])
        assert not output.exists()
    absent=work/'missing-input.edf';output=work/'missing-input-output'
    invoke('missing-input',[ENTRY,left,absent,output],False,'ENOENT');assert not output.exists()
    output=work/'absent-parent'/'review'
    invoke('missing-parent',[ENTRY,left,right,output],False,'ENOENT');assert not output.exists() and not output.parent.exists()
    output=work/'injected-io-output'
    invoke('injected-write',['--import',(FIXTURES/'fail-write.mjs').resolve().as_uri(),ENTRY,left,right,output],False,'injected review write failure',{'MOON_REVIEW_FAIL_OUTPUT':str(output)})
    assert output.is_dir() and not (output/'manifest.json').exists()
    assert {p.name for p in output.iterdir()}=={'left-inspect.json','right-inspect.json','left-annotations.json'}
    assert input_before=={p.name:sha(p.read_bytes()) for p in FIXTURES.iterdir() if p.is_file()}
    result=dict(status='passed',publicOutputs=public,independentlyParsedCompletePairs=len(cases),manualExpectationsFrozen=True,fileBundles=bundles,completeSavedPayloads=sidecars,completeManifests=len(bundles),fileErrors=len(errors),occupiedOutputControls=1,missingInputControls=1,missingParentControls=1,injectedWriteFailureControls=1,injectedFaultIsNotPhysicalDiskFailure=True,commands=commands,bridge=dict(path=str(bridge),sha256=bridge_hash),inputFilesUnchanged=True,biologicalOrClinicalAdoptionClaim=False)
    save(args.output,result)
    print(json.dumps(dict(status='passed',publicCompleteResults=len(cases)*len(public),publicErrors=sum(e['public'] for e in errors.values())*len(public),actualFilePairs=len(cases),completeSavedPayloads=sidecars,completeManifests=len(bundles),fileErrors=len(errors),ioAndOccupiedControls=4)))

if __name__=='__main__':main()
