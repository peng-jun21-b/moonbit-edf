"""Receive full signal-merge files against independent pre-implementation bytes.

No MoonEDF writer or internal merge helper constructs the oracle. Independently
parse every fixed-width column, signed sample and TAL, then check complete public
and physical-file products, original source blocks, exact Fraction clocks and IO.
"""
import argparse
from fractions import Fraction
import hashlib,json,os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1];FIX=ROOT/'tools/fixtures/signal-merge'
COLUMNS=[('label',16),('transducer',80),('unit',8),('physical_min',8),('physical_max',8),('digital_min',8),('digital_max',8),('prefilter',80),('samples_per_record',8),('reserved',32)]
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def decimal(v):
    v=Fraction(v);d=v.denominator;a=b=0
    while d%2==0:a+=1;d//=2
    while d%5==0:b+=1;d//=5
    assert d==1;s=max(a,b);digits=str(abs(v.numerator)*(10**s//v.denominator)).zfill(s+1)
    t=(digits[:-s]+'.'+digits[-s:]).rstrip('0').rstrip('.') if s else digits
    return ('-' if v<0 else '+')+t
def parse(data):
    assert data[:8] in (b'0       ',b'\xffBIOSEMI');width=2 if data[:8]==b'0       ' else 3
    text=lambda at,n:data[at:at+n].decode('ascii').strip(' ')
    ns=int(text(252,4));hs=int(text(184,8));assert hs==256+ns*256
    fields=[{} for _ in range(ns)];columns=[[] for _ in range(ns)];offset=256
    for key,size in COLUMNS:
        for signal in range(ns):
            raw=data[offset+signal*size:offset+(signal+1)*size];columns[signal].append(raw);fields[signal][key]=raw.decode('ascii').strip(' ')
        offset+=ns*size
    sizes=[int(s['samples_per_record'])*width for s in fields];stride=sum(sizes);assert (len(data)-hs)%stride==0
    nr=(len(data)-hs)//stride;assert int(text(236,8)) in (-1,nr)
    starts=[];events=[];blocks=[];digital=[]
    for record in range(nr):
        row=[];row_digital=[];start=None;at=hs+record*stride
        for signal,(s,size) in enumerate(zip(fields,sizes)):
            block=data[at:at+size];at+=size;row.append(block)
            if s['label'] in ('EDF Annotations','BDF Annotations'):
                parts=block.split(b'\0')
                for j,p in enumerate(parts):
                    if not p:assert all(not x for x in parts[j:]);break
                    clock,*texts=p.split(b'\x14');assert texts[-1]==b'';texts.pop();values=clock.split(b'\x15')
                    onset=values[0].decode('ascii');duration=values[1].decode('ascii') if len(values)==2 else None
                    if start is None:start=Fraction(onset)
                    for text_value in texts:
                        if text_value:
                            e=dict(record=record,signal=signal,onset=onset,text=text_value.decode('utf-8'))
                            if duration is not None:e['duration']=duration
                            events.append(e)
                row_digital.append(None)
            else:row_digital.append([int.from_bytes(block[i:i+width],'little',signed=True) for i in range(0,len(block),width)])
        starts.append(start if start is not None else Fraction(text(244,8))*record);blocks.append(row);digital.append(row_digital)
    duration=Fraction(text(244,8));samples=[];gaps=[]
    for record,row in enumerate(digital):
        for signal,values in enumerate(row):
            if values is None:continue
            for sample,value in enumerate(values):
                t=starts[record]+duration*sample/len(values)
                samples.append(dict(signal=signal,record=record,sample=sample,digital=value,time=dict(numerator=str(t.numerator),denominator=str(t.denominator))))
    for r in range(1,nr):
        end=starts[r-1]+duration
        if starts[r]>end:gaps.append(dict(after_record=r-1,start=decimal(end).lstrip('+'),end=decimal(starts[r]).lstrip('+')))
    return dict(columns=columns,blocks=blocks,plain=not text(192,44).startswith(('EDF+','BDF+')),native=dict(records=nr,signals=ns,starts=[decimal(v) for v in starts],gaps=gaps,annotations=events,samples=samples))
def preserved(left,right,output):
    a,b,c=map(parse,(left,right,output));promote=not(a['plain'] and b['plain']);right_at=len(a['columns'])+(1 if promote and a['plain'] else 0)
    for source,base in ((a,0),(b,right_at)):
        for signal,column in enumerate(source['columns']):
            assert column==c['columns'][base+signal],(signal,base,'raw header column')
            for r,row in enumerate(source['blocks']):assert row[signal]==c['blocks'][r][base+signal],(r,signal,'entire raw signal/TAL block')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True);ap.add_argument('--public-output',type=Path,action='append',required=True)
    args=ap.parse_args();assert not args.output.exists() and not args.work_dir.exists(),'choose fresh output paths';args.work_dir.mkdir(parents=True)
    work=args.work_dir.resolve();model=json.loads((FIX/'EXPECTED.json').read_bytes());cases=model['cases'];errors=model['errors'];before={p.name:sha(p.read_bytes()) for p in FIX.iterdir() if p.is_file()}
    for name in {c[k] for c in cases+errors for k in ('left','right')}:
        if name!='partial.edf':parse((FIX/name).read_bytes())
    for c in cases:
        l=(FIX/c['left']).read_bytes();r=(FIX/c['right']).read_bytes();out=(FIX/c['expected']).read_bytes()
        assert parse(out)['native']==c['native'];preserved(l,r,out)
    selected=cases+[e for e in errors if e['public']];byname={c['name']:c for c in cases};errorby={e['name']:e for e in errors};public=[]
    for path in args.public_output:
        rows=json.loads(path.read_bytes());assert [r['name'] for r in rows]==[c['name'] for c in selected]
        for row in rows:
            if row['name'] in byname:
                c=byname[row['name']];assert set(row)=={'name','output','left_after','right_after','native'}
                assert bytes(row['output'])==(FIX/c['expected']).read_bytes();assert row['native']==c['native']
                for side in ('left','right'):assert bytes(row[side+'_after'])==(FIX/c[side]).read_bytes()
            else:assert set(row)=={'name','error'} and errorby[row['name']]['error'] in row['error']
        public.append(dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=sha(path.read_bytes()),completeProducts=len(cases),expectedErrors=len(selected)-len(cases)))
    commands=[]
    def invoke(name,command,success,error=None):
        p=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=90)
        so=work/(name+'.stdout');se=work/(name+'.stderr');so.write_bytes(p.stdout);se.write_bytes(p.stderr)
        commands.append(dict(name=name,command=list(map(str,command)),exitCode=p.returncode,stdout=str(so),stderr=str(se)));save(work/'COMMANDS.json',commands)
        assert (p.returncode==0)==success,(name,p.returncode,p.stderr.decode('utf-8',errors='replace'))
        if error:assert error in p.stderr.decode('utf-8'),(name,error,p.stderr.decode('utf-8'))
        return p
    products=[];first=None
    for c in cases:
        folder=work/c['name'];folder.mkdir();l=folder/('left #.'+Path(c['left']).suffix.lstrip('.'));r=folder/('right #.'+Path(c['right']).suffix.lstrip('.'));o=folder/('merged'+Path(c['expected']).suffix)
        l.write_bytes((FIX/c['left']).read_bytes());r.write_bytes((FIX/c['right']).read_bytes());op=folder/'read.json';op.write_bytes((FIX/c['readOptions']).read_bytes());initial={str(p):sha(p.read_bytes()) for p in (l,r,op)}
        p=invoke(c['name'],['node','tools/edf.mjs','merge-signals',str(l),str(r),str(o),str(op)],True)
        data=o.read_bytes();assert data==(FIX/c['expected']).read_bytes();assert parse(data)['native']==c['native'];preserved(l.read_bytes(),r.read_bytes(),data)
        receipt=json.loads(p.stdout);source=lambda p:dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
        lp={} if c['leftTolerance'] is None else {'time_tolerance':c['leftTolerance']};rp={} if c['rightTolerance'] is None else {'time_tolerance':c['rightTolerance']}
        assert receipt==dict(output=str(o),bytes=len(data),sha256=sha(data),left=source(l),right=source(r),common_clock=True,read_policy=dict(left=lp,right=rp,output=lp))
        assert initial=={str(p):sha(p.read_bytes()) for p in (l,r,op)}
        products.append(dict(name=c['name'],output=str(o),bytes=len(data),sha256=sha(data),native=c['native'],receipt=receipt))
        if first is None:first=(l,r,o,op)
    l,r,o,op=first;initial={str(p):sha(p.read_bytes()) for p in (l,r,o,op)}
    invoke('occupied',['node','tools/edf.mjs','merge-signals',str(l),str(r),str(o),str(op)],False,'output exists')
    assert initial=={str(p):sha(p.read_bytes()) for p in (l,r,o,op)}
    for e in errors:
        o=work/('error-'+e['name']+'.edf');invoke(e['name'],['node','tools/edf.mjs','merge-signals',str(FIX/e['left']),str(FIX/e['right']),str(o),str(FIX/e['readOptions'])],False,e['error']);assert not o.exists()
    o=work/'missing-parent'/'out.edf';invoke('missing-parent',['node','tools/edf.mjs','merge-signals',str(l),str(r),str(o),str(op)],False,'ENOENT');assert not o.exists() and not o.parent.exists()
    assert before=={p.name:sha(p.read_bytes()) for p in FIX.iterdir() if p.is_file()}
    result=dict(status='passed',publicOutputs=public,fileProducts=products,completeIndependentRawProducts=len(cases),allOriginalSignalHeaderColumnsAndBlocksPreserved=True,checkedErrors=len(errors),occupiedOutputControls=1,missingParentControls=1,commands=commands,inputFilesUnchanged=True,exactNativeContextsChecked=True,clockConfirmationIsCallerDeclarationNotProof=True)
    save(args.output,result);print(json.dumps(dict(status='passed',publicCompleteProducts=len(cases)*len(public),publicExpectedErrors=(len(selected)-len(cases))*len(public),actualFileProducts=len(products),checkedErrors=len(errors),outputControls=2)))

if __name__=='__main__':main()
