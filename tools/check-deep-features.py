"""Original byte-layout/Fraction oracle plus the independent EDFlib C reader."""
import argparse, datetime, hashlib, json, runpy, subprocess, sys, tempfile
from fractions import Fraction as F
from pathlib import Path
import numpy as np
import pyedflib

sys.set_int_max_str_digits(0)
ROOT=Path(__file__).resolve().parents[1]
read=runpy.run_path(str(ROOT/'tools/verify-exact-time.py'))['read']

def field(v,n):
    b=str(v).encode('ascii');assert len(b)<=n;return b.ljust(n,b' ')

def fixture(path,fmt='edf',starts=('+0','+1'),marker='C',events=None,ann=2,date='01.01.20',longdate='01-JAN-2020'):
    width=2 if fmt=='edf' else 3;lo,hi=(-32768,32767) if width==2 else (-8388608,8388607)
    labels=['Fast','Slow']+[fmt.upper()+' Annotations']*ann
    per=[4,2]+[max(128,max((len(e[2].encode())+len(e[0])+len(e[1] or '')+20 for group in (events or {}).values() for e in group),default=0)//width+1)]*ann
    ns=len(labels)
    fixed=(b'0       ' if width==2 else b'\xffBIOSEMI')+field('X X X X',80)+field('Startdate '+longdate+' X X X',80)+field(date,8)+b'00.00.00'+field(256*(ns+1),8)+field(fmt.upper()+'+'+marker,44)+field(len(starts),8)+field(1,8)+field(ns,4)
    cols=[(16,labels),(80,['']*ns),(8,['uV','uV']+['']*ann),(8,[-100,-100]+[-1]*ann),(8,[100,100]+[1]*ann),(8,[lo]*ns),(8,[hi]*ns),(80,['']*ns),(8,per),(32,['']*ns)]
    out=bytearray(fixed+b''.join(field(v,n) for n,vs in cols for v in vs))
    for r,onset in enumerate(starts):
        for s,count in enumerate(per[:2]):
            for j in range(count):out.extend((r*10+s*100+j).to_bytes(width,'little',signed=True))
        for a in range(ann):
            tal=onset.encode()+b'\x14\x14\0' if a==0 else b''
            for t,d,text in (events or {}).get((r,a),[]):
                tal+=t.encode()+(b'\x15'+d.encode() if d is not None else b'')+b'\x14'+text.encode()+b'\x14\0'
            assert len(tal)<=per[2+a]*width
            out.extend(tal.ljust(per[2+a]*width,b'\0'))
    path.write_bytes(out)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    checks=[];tasks=[];products=[];cases=[]
    with tempfile.TemporaryDirectory(prefix='edf-deep-') as td:
        work=Path(td)
        def add(name,src,options,check,output=None,error=False):
            tasks.append(dict(kind='transform' if output else 'report',input=str(src) if src else None,options=options,**({'output':str(output)} if output else {})))
            checks.append((name,check,error));cases.append(name)
            if output:products.append(output)
        for fmt in ['edf','bdf']:
            src=work/('multi.'+fmt)
            fixture(src,fmt,events={(0,0):[('+0.500000000000000000001','0.000000000000000000003','tiny')],(1,1):[('+1.25',None,'secondary')]})
            known=read(src.read_bytes())
            def annotations(v):
                assert len(v)==2 and v[1]['signal']==3
                assert F(v[0]['onset'])==F('0.500000000000000000001')
                assert F(v[0]['duration'])==F('0.000000000000000000003')
            add(fmt+'-multi',src,dict(command='annotations'),annotations)
            out=work/('cropped.'+fmt)
            def crop(v,out=out,known=known):
                k=read(out.read_bytes());assert k['duration']==F('0.5')
                assert [r['samples'] for r in k['records']]==[[[2,3],[101]],[[10,11],[110]]]
                assert [r['starts'][0] for r in k['records']]==[F('.5'),F('1')]
                assert k['annotations']==[{**known['annotations'][0],'record':0},{**known['annotations'][1],'record':1}]
                with pyedflib.EdfReader(str(out)) as reader:
                    np.testing.assert_array_equal(reader.readSignal(0,digital=True),[2,3,10,11])
                    np.testing.assert_array_equal(reader.readSignal(1,digital=True),[101,110])
                    assert reader.datarecord_duration==.5
            add(fmt+'-partial-crop',src,dict(command='crop-time',start='.5',end='1.5'),crop,out)
            edit=work/('edited.'+fmt);renamed=work/('renamed.'+fmt);cal=work/('cal.'+fmt)
            def added(v,edit=edit):
                k=read(edit.read_bytes());assert any(a['text']=='x'*2000 and a['signal']==3 for a in k['annotations'])
            add(fmt+'-add-capacity',src,dict(command='annotation-add',onset='+0.000000000000000000001',text='x'*2000,signal=3),added,edit)
            add(fmt+'-rename',edit,dict(command='rename',signal=0,label='Voltage'),lambda v,renamed=renamed:None,renamed)
            def calibration(v,cal=cal):
                k=read(cal.read_bytes());assert k['signals'][0]['physical_min']==-197 and k['signals'][0]['physical_max']==203
                assert k['signals'][0]['unit']=='mV' and k['signals'][0]['label']=='Voltage'
                assert k['records'][0]['samples'][0]==[0,1,2,3]
                with pyedflib.EdfReader(str(cal)) as reader:np.testing.assert_array_equal(reader.readSignal(0,digital=True),[0,1,2,3,10,11,12,13])
            add(fmt+'-calibration',renamed,dict(command='calibrate',signal=0,scale=2,offset=3,unit='mV'),calibration,cal)
            remove=work/('remove.'+fmt)
            add(fmt+'-remove',edit,dict(command='annotation-remove',index=1),lambda v,remove=remove:assert_count(read(remove.read_bytes())['annotations'],2),remove)
            for kind,onset in [('gap','+1.000000000000000000001'),('overlap','+0.999999999999999999999')]:
                bad=work/(fmt+kind+'.'+fmt);fixture(bad,fmt,starts=('+0',onset),ann=1)
                add(fmt+'-'+kind+'-strict',bad,dict(command='inspect'),lambda v:None,error=True)
                add(fmt+'-'+kind+'-tolerant',bad,dict(command='inspect',time_tolerance='0.000000000000000000001'),lambda v,onset=onset:assert_equal(v['starts'][1],onset))
            disc=work/('disc.'+fmt);fixture(disc,fmt,starts=('+0.25','+4.25'),marker='D',events={(1,1):[('+4.750000000000000000001',None,'retained')]})
            outd=work/('disc-crop.'+fmt)
            def cropped_d(v,outd=outd):
                k=read(outd.read_bytes());assert k['time']=='00.00.04' and k['records'][0]['starts'][0]==F('.75')
                assert k['records'][0]['samples']==[[12,13],[111]] and F(k['annotations'][0]['onset'])==F('.750000000000000000001')
            add(fmt+'-gap-crop',disc,dict(command='crop-time',start='4.75',end='5.25'),cropped_d,outd)
        long=work/'long.edf';tiny='0.'+'0'*5000+'1'
        fixture(long,starts=('+0','+10000000000.000000000000000000001'),marker='D',ann=1,events={(0,0):[('+'+tiny,tiny,'small')]})
        add('long-span-and-5001-digits',long,dict(command='annotations'),lambda v:assert_equal(v[0]['onset'],'+'+tiny))
        future=work/'future.edf';fixture(future,starts=('+0','+2'),marker='D',ann=1,date='31.12.yy',longdate='31-DEC-2119')
        out=work/'future-crop.edf'
        def future_check(v):
            k=read(out.read_bytes());assert k['date']=='31.12.yy' and k['time']=='00.00.02' and k['recording'].startswith('Startdate 31-DEC-2119')
        add('future-date',future,dict(command='crop-time',start='2',end='2.5'),future_check,out)
        req=work/'tasks.json';res=work/'results.json';req.write_text(json.dumps(tasks),encoding='utf-8')
        subprocess.run(['node',str(ROOT/'tools/reference-batch.mjs'),str(req),str(res)],check=True,cwd=ROOT)
        result=json.loads(res.read_text('utf-8'))
        for (name,check,error),r in zip(checks,result,strict=True):
            assert r['ok'] != error,(name,r)
            if not error:
                try:check(r['result'])
                except Exception as e:raise AssertionError(name) from e
        report=dict(status='passed',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),oracle='Original fixed-width writer and Fraction reader; pyEDFlib '+pyedflib.__version__,checks=len(checks),cases=cases,products=[dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in products],edflib_acceptance='Partial crops, channel edits and calibration on EDF+C and BDF+C; exact sub-tick values checked only with Fraction')
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n','utf-8');print(json.dumps({k:v for k,v in report.items() if k not in ['cases','products']}))

def assert_equal(a,b):assert a==b,(a,b)
def assert_count(a,b):assert len(a)==b
if __name__=='__main__':main()
