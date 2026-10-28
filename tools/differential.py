from numeric_view import view
"""Synthetic EDF/BDF conformance and real CLI workflows against pyedflib/EDFlib."""
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile
import time
import warnings
import argparse
import numpy as np
import pyedflib
from pyedflib import highlevel

ROOT=Path(__file__).resolve().parents[1]

def close(a,b,tol=1e-8):
    np.testing.assert_allclose(a,b,rtol=tol,atol=tol)

def run():
    started=time.time()
    tasks=[];checks=[];matrix=[];benchmarks=[]
    with tempfile.TemporaryDirectory(prefix='moonedf-') as tmp:
        work=Path(tmp)
        def add(kind,input,options,check,output=None,expected_error=False):
            t=dict(kind=kind,input=str(input) if input else None,options=options)
            if output:t['output']=str(output)
            tasks.append(t);checks.append((check,expected_error))

        for filetype in (pyedflib.FILETYPE_EDF,pyedflib.FILETYPE_EDFPLUS,pyedflib.FILETYPE_BDF,pyedflib.FILETYPE_BDFPLUS):
            for negative_gain in (False,True):
                for duration in (1.0,.5):
                    bdf=filetype in (2,3);plus=filetype in (1,3)
                    low,high=(-8388608,8388607) if bdf else (-32768,32767)
                    src=work/f'case-{len(matrix)}.{"bdf" if bdf else "edf"}'
                    headers=[highlevel.make_signal_header('Fast',sample_frequency=8,physical_min=100 if negative_gain else -100,physical_max=-100 if negative_gain else 100,digital_min=low,digital_max=high),highlevel.make_signal_header('Slow',sample_frequency=4,physical_min=-50,physical_max=50,digital_min=low,digital_max=high)]
                    n0,n1=int(8*4*duration),int(4*4*duration)
                    values=[np.resize(np.array([low,high,0,100,100,100,100,10],dtype=np.int32),n0),np.arange(n1,dtype=np.int32)*100-500]
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore')
                        with pyedflib.EdfWriter(str(src),2,file_type=filetype) as writer:
                            writer.setStartdatetime(datetime.datetime(2020,2,28,23,59,59))
                            writer.setDatarecordDuration(duration)
                            writer.setSignalHeaders(headers)
                            writer.writeSamples(values,digital=True)
                            if plus:writer.writeAnnotation(.125,.25,'synthetic α')
                    with pyedflib.EdfReader(str(src)) as reader:
                        digital=[reader.readSignal(i,digital=True) for i in range(2)]
                        physical=[reader.readSignal(i) for i in range(2)]
                        nsamples=reader.samples_in_datarecord(0)
                        records=reader.datarecords_in_file
                        rd=reader.datarecord_duration
                    matrix.append(dict(filetype=filetype,negative_gain=negative_gain,duration=duration,sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
                    def inspect(r,bdf=bdf,plus=plus,records=records,rd=rd):
                        assert r['format']==('bdf' if bdf else 'edf')
                        assert r['continuity']==('continuous' if plus else 'plain')
                        assert r['records']==records
                        close(r['duration'],rd)
                    add('report',src,dict(command='inspect'),inspect)
                    for channel in (0,1):
                        add('report',src,dict(command='channel',signal=channel,count=len(digital[channel])),lambda r,d=digital[channel]:np.testing.assert_array_equal(r['values'],d))
                        add('report',src,dict(command='channel',signal=channel,count=len(physical[channel]),physical=True),lambda r,d=physical[channel]:close(r['values'],d))
                        def stats(r,d=physical[channel]):
                            close([r['minimum'],r['maximum'],r['mean'],r['variance'],r['rms']],[d.min(),d.max(),d.mean(),d.var(),np.sqrt(np.mean(d*d))])
                        add('report',src,dict(command='stats',signal=channel),stats)
                    if plus:
                        def annotation(r):
                            assert len(r)==1 and r[0]['text']=='synthetic α'
                            close([r[0]['onset'],r[0]['duration']],[.125,.25])
                        add('report',src,dict(command='annotations'),annotation)
                    copied=work/f'copy-{len(matrix)}.{"bdf" if bdf else "edf"}'
                    def copy_check(r,copied=copied,digital=digital):
                        with pyedflib.EdfReader(str(copied)) as reader:
                            for i in range(2):np.testing.assert_array_equal(reader.readSignal(i,digital=True),digital[i])
                    add('transform',src,dict(command='copy'),copy_check,copied)
                    selected=work/f'select-{len(matrix)}.{"bdf" if bdf else "edf"}'
                    def select_check(r,selected=selected,d=digital[1]):
                        with pyedflib.EdfReader(str(selected)) as reader:
                            assert reader.signals_in_file==1
                            np.testing.assert_array_equal(reader.readSignal(0,digital=True),d)
                    add('transform',src,dict(command='select',signals=[1]),select_check,selected)
                    # Crop at one second (two records for 0.5s) so plain origin is representable.
                    first=int(1/duration);num=1
                    cropped=work/f'crop-{len(matrix)}.{"bdf" if bdf else "edf"}'
                    def crop_check(r,cropped=cropped,digital=digital,first=first,nsamples=nsamples):
                        with pyedflib.EdfReader(str(cropped)) as reader:
                            np.testing.assert_array_equal(reader.readSignal(0,digital=True),digital[0][first*nsamples:(first+1)*nsamples])
                            assert reader.getStartdatetime()==datetime.datetime(2020,2,29,0,0,0)
                    add('transform',src,dict(command='crop',first_record=first,records=num),crop_check,cropped)
                    if not plus:
                        promoted=work/f'plus-{len(matrix)}.{"bdf" if bdf else "edf"}'
                        def plus_check(r,promoted=promoted,digital=digital):
                            with pyedflib.EdfReader(str(promoted)) as reader:
                                for i in range(2):np.testing.assert_array_equal(reader.readSignal(i,digital=True),digital[i])
                        add('transform',src,dict(command='plus'),plus_check,promoted)

        # Files written from scratch by MoonBit must be consumable by an unrelated C reader.
        for fmt in ('edf','bdf'):
            for mode in ('plain','continuous'):
                out=work/f'created-{fmt}-{mode}.{fmt}'
                low,high=(-32768,32767) if fmt=='edf' else (-8388608,8388607)
                options=dict(command='create',format=fmt,continuity=mode,duration=1,signals=[dict(label='Created',samples_per_record=4)],records=[dict(onset=0,samples=[[low,0,1,high]],events=[]),dict(onset=1,samples=[[5,6,7,8]],events=[] if mode=='plain' else [dict(onset=1.5,duration=.1,text='Created α')])])
                def created(r,out=out,low=low,high=high,mode=mode):
                    with pyedflib.EdfReader(str(out)) as reader:
                        np.testing.assert_array_equal(reader.readSignal(0,digital=True),[low,0,1,high,5,6,7,8])
                        if mode!='plain':assert reader.readAnnotations()[2][0]=='Created α'
                add('transform',None,options,created,out)

        # EDF+D is explicitly unsupported by the chosen C oracle. Independently build
        # fixed-width bytes from the published layout; do not claim C acceptance here.
        plus=work/'discontinuous.edf'
        def field(value,width):
            b=str(value).encode('ascii');assert len(b)<=width;return b.ljust(width,b' ')
        fixed=b'0       '+field('X X X X',80)+field('Startdate 01-JAN-2020 X X X',80)+b'01.01.2000.00.00'+field(768,8)+field('EDF+D',44)+field(2,8)+field(1,8)+field(2,4)
        fields=[(16,['Signal','EDF Annotations']),(80,['','']),(8,['uV','']),(8,[-100,-1]),(8,[100,1]),(8,[-32768,-32768]),(8,[32767,32767]),(80,['','']),(8,[2,64]),(32,['',''])]
        header=fixed+b''.join(field(v,w) for w,vs in fields for v in vs)
        body=b''
        for onset,samples in [(b'+0.25',(1,2)),(b'+4.25',(3,4))]:
            tal=onset+b'\x14\x14\0'+onset+b'\x14independent event\x14\0'
            body+=struct.pack('<hh',*samples)+tal.ljust(128,b'\0')
        plus.write_bytes(header+body)
        try:
            with pyedflib.EdfReader(str(plus)) as reader:
                discontinuous_reference='pyedflib opened EDF+D; manual timeline oracle also used'
        except OSError as exc:
            assert 'discontinuous' in str(exc).lower(),str(exc)
            discontinuous_reference='pyedflib rejects EDF+D as discontinuous; independent struct timeline oracle used'
        add('report',plus,dict(command='gaps'),lambda r:close([r[0]['start'],r[0]['end']],[1.25,4.25]))
        add('report',plus,dict(command='channel',signal=0,count=4),lambda r:close(r['times'],[.25,.75,4.25,4.75]))
        cropped_d=work/'cropped-d.edf'
        def check_d(r):
            data=cropped_d.read_bytes()
            assert data[176:184]==b'00.00.04' and data[236:244].strip()==b'1'
            assert data[768:772]==struct.pack('<hh',3,4)
            assert data[772:].startswith(b'+0.25\x14\x14\0')
        add('transform',plus,dict(command='crop',first_record=1,records=1),check_d,cropped_d)

        # Header-count -1, truncation and a contradictory continuous flag.
        unknown=work/'unknown.edf';b=bytearray(plus.read_bytes());b[236:244]=b'-1      ';unknown.write_bytes(b)
        add('report',unknown,dict(command='inspect'),lambda r:assert_records(r,2))
        for name,mutate in [('truncated',lambda b:b[:-1]),('count',lambda b:b[:236]+b'3       '+b[244:]),('continuous',lambda b:b[:192]+b'EDF+C'+b[197:])]:
            bad=work/f'{name}.edf';bad.write_bytes(mutate(plus.read_bytes()))
            add('report',bad,dict(command='inspect'),lambda r:None,expected_error=True)
        def csv_check(r):
            rows=list(csv.DictReader(io.StringIO(r['text'])))
            assert len(rows)==4
            close([float(x['time_seconds']) for x in rows],[.25,.75,4.25,4.75])
            assert [int(x['value']) for x in rows]==[1,2,3,4]
        add('report',plus,dict(command='csv',signals=[0],physical=False),csv_check)

        for n in (4096,262144):
            data=(np.arange(n,dtype=np.int32)%1000)-500
            filename=work/f'benchmark-{n}.edf'
            h=highlevel.make_signal_header('Benchmark',sample_frequency=256,physical_min=-32768,physical_max=32767)
            highlevel.write_edf(str(filename),[data],[h],digital=True,file_type=pyedflib.FILETYPE_EDF)
            add('report',filename,dict(command='stats',signal=0),lambda r,data=data:close([r['mean'],r['variance']],[data.mean(),data.var()]))
            benchmarks.append((len(tasks)-1,n,filename.stat().st_size))

        taskfile=work/'tasks.json';resultfile=work/'results.json'
        taskfile.write_text(json.dumps(tasks,ensure_ascii=False),encoding='utf-8')
        subprocess.run(['node',str(ROOT/'tools/reference-batch.mjs'),str(taskfile),str(resultfile)],check=True,cwd=ROOT)
        results=json.loads(resultfile.read_text(encoding='utf-8'))
        for i,(t,r,(check,error)) in enumerate(zip(tasks,results,checks)):
            if error:
                assert not r['ok'],f'expected rejection: {t}'
            else:
                assert r['ok'],f'task {i}: {t}: {r}'
                try:check(view(r['result']))
                except Exception as e:raise AssertionError(f'task {i}: {t}: {r}') from e
        cli=ROOT/'tools/edf.mjs'
        p=subprocess.run(['node',str(cli),'inspect',str(plus)],capture_output=True,text=True)
        assert p.returncode==0 and json.loads(p.stdout)['records']==2,p.stderr
        p=subprocess.run(['node',str(cli),'copy',str(plus),str(plus)],capture_output=True,text=True)
        assert p.returncode==2 and 'output exists' in p.stderr
        evidence=dict(status='passed',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=sys.version,platform=platform.platform(),pyedflib=pyedflib.__version__,numpy=np.__version__,generated_cases=len(matrix),checks=len(checks),cli_checks=2,discontinuous_oracle=discontinuous_reference,duration_seconds=time.time()-started,matrix=matrix,benchmarks=[dict(samples=n,file_bytes=size,parse_and_stats_ms=results[i]['ms']) for i,n,size in benchmarks])
        (ROOT/'evidence').mkdir(exist_ok=True)
        result_path = Path(ARGS.output)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in evidence.items() if k not in ('matrix','python')}))

def assert_records(r,n):assert r['records']==n

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT/'evidence/differential.json'))
    ARGS = parser.parse_args()
    run()
