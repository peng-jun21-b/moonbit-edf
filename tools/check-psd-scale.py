"""Small-amplitude range checks with Decimal DFT and real JSON/CSV readback.

Development-only, standard library. No FFT, SciPy or production conditioning
helper supplies expected values. Raw EDF construction/reading reuses this
project's independent fixed-width fixture utilities. Choose fresh output paths.
"""
import argparse
import csv
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RAW = runpy.run_path(str(ROOT / "tools/check-psd.py"))
COLUMNS = ['source_sha256','signal','label','physical_unit','psd_unit','start','end',
           'sample_rate_numerator','sample_rate_denominator','segment_length',
           'overlap_samples','window','detrend','nfft','frequency_hz','density']


def oracle(values, fs, n, overlap, hann):
    """Analytical rectangular DC; otherwise 100-digit algebraic direct DFT."""
    with localcontext() as c:
        c.prec = 100
        q = (D(1) / 2).sqrt()
        cosine = [D(1), q, D(0), -q, D(-1), -q, D(0), q]
        sine = [D(0), q, D(1), q, D(0), -q, D(-1), -q]
        assert n in (4, 8) and (not hann or n == 4)
        weights = [D(0), D(3)/4, D(3)/4, D(0)] if hann else [D(1)] * n
        energy = sum(w*w for w in weights)
        frames = [values[i:i+n] for i in range(0, len(values)-n+1, n-overlap)]
        if not hann and all(x == values[0] for x in values):
            # Exact orthogonality: a constant rectangular frame has only DC.
            # Do not turn Decimal sqrt-rounding residue into a fictitious bin
            # after division by an extremely small sample rate.
            return [D(n)*values[0]*values[0]/fs]+[D(0)]*(n//2), len(frames)
        output = []
        for k in range(n//2+1):
            total = D(0)
            for frame in frames:
                re, im = D(0), D(0)
                for j, x in enumerate(frame):
                    phase = (k*j*(8//n)) % 8
                    re += x * weights[j] * cosine[phase]
                    im -= x * weights[j] * sine[phase]
                total += (re*re+im*im)/(fs*energy) * (1 if k in (0,n//2) else 2)
            output.append(total/len(frames))
        return output, len(frames)


def close(actual, expected):
    want = float(expected)
    assert math.isfinite(actual) and actual >= 0
    if want == 0:
        assert actual == 0, (actual, str(expected))
    else:
        # Absolute 1e-9 would falsely accept a zero spectrum here.
        assert actual > 0
        tolerance = max(abs(want)*3e-12, 2*math.ulp(want))
        assert abs(actual-want) <= tolerance, (actual, want, tolerance)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--work-dir', type=Path, required=True)
    a = ap.parse_args()
    assert not a.output.exists() and not a.work_dir.exists(), 'choose fresh paths'
    a.work_dir.mkdir(parents=True)
    cases = [
        ('dc', [1]*8, '0','1e-180',0,1,'1e200',8,0,'rectangular'),
        ('dc-times-two', [1]*8, '0','2e-180',0,1,'1e200',8,0,'rectangular'),
        ('dc-overlap-tail', [1]*18, '0','1e-180',0,1,'2.25e200',8,4,'rectangular'),
        ('nyquist', [1,-1]*4, '-1e-180','1e-180',-1,1,'1e200',8,0,'rectangular'),
        ('periodic-nonconstant', [1,0,-1,0]*2, '-1e-180','1e-180',-1,1,'1e200',8,0,'rectangular'),
        ('hann-four', [1,2,-1,3], '-1e-180','3e-180',-1,3,'1e200',4,0,'hann_symmetric'),
        ('zero', [0]*8, '0','1e-180',0,1,'1e200',8,0,'rectangular'),
        ('subnormal-density', [1]*8, '0','1e-310',0,1,'1e308',8,0,'rectangular'),
        ('final-density-underflow', [1]*8, '0','1e-320',0,1,'1e308',8,0,'rectangular'),
        ('small-amplitude-normal-rate', [1]*8, '0','1e-180',0,1,'1',8,0,'rectangular'),
        ('threshold-below', [1]*8, '0','7.4e-155',0,1,'1e200',8,0,'rectangular'),
        ('threshold-above', [1]*8, '0','7.5e-155',0,1,'1e200',8,0,'rectangular'),
    ]
    rows, products = [], {}
    for name, samples, low, high, dlow, dhigh, duration, n, overlap, window in cases:
        source = a.work_dir/(name+'.edf')
        RAW['fixture'](source, [[samples]], duration=duration, physical=(low,high), digital=(dlow,dhigh))
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        raw = RAW['raw_window'](source,0,'0',duration)
        values = [D.from_float(point[1]) for point in raw['points']]
        expected, frames = oracle(values,D.from_float(float(raw['rate'])),n,overlap,window=='hann_symmetric')
        opts = dict(signal=0,start='0',end=duration,segment_length=n,overlap_samples=overlap,window=window,
                    bands=[dict(name='all-requested-bins',low_hz=0,high_hz=float(raw['rate'])/2)])
        options = a.work_dir/(name+'.json'); options.write_text(json.dumps(opts),encoding='utf-8')
        output = a.work_dir/(name+'-output')
        v = subprocess.run(['node',str(ROOT/'examples/edf-psd.mjs'),str(source),str(output),str(options)],
                           cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert v.returncode == 0, v.stderr
        document = json.loads((output/'psd.json').read_text(encoding='utf-8')); result=document['result']
        assert document['source']['sha256']==before==hashlib.sha256(source.read_bytes()).hexdigest()
        assert document['source']['bytes']==source.stat().st_size
        assert result['signal']==0 and result['label']==raw['label'] and result['unit']==raw['unit']
        assert result['psd_unit']=='(uV)^2/Hz' and result['power_unit']=='(uV)^2'
        assert result['calibration']==raw['calibration'] and result['sample_rate_hz']==float(raw['rate'])
        assert F(int(result['sample_rate']['numerator']),int(result['sample_rate']['denominator']))==raw['rate']
        assert F(result['start'])==0 and F(result['end'])==F(duration)
        used=n+(frames-1)*(n-overlap)
        assert (result['selected_samples'],result['used_samples'],result['dropped_tail_samples'],result['segments'])==(len(samples),used,len(samples)-used,frames)
        assert result['detrend']=='none' and result['scaling']=='density' and result['average']=='mean'
        for actual, want in zip(result['density'],expected): close(actual,want)
        for k,f in enumerate(result['frequencies_hz']):
            want=float(raw['rate']*F(k,n));assert abs(f-want)<=2*math.ulp(want)
        with (output/'psd.csv').open(encoding='utf-8',newline='') as f:
            reader=csv.DictReader(f);assert reader.fieldnames==COLUMNS; csv_rows=list(reader)
        assert len(csv_rows)==len(expected)==len(result['density'])
        for i,row in enumerate(csv_rows):
            assert row['source_sha256']==before and row['label']==raw['label'] and row['physical_unit']==raw['unit']
            assert row['psd_unit']==result['psd_unit'] and row['sample_rate_numerator']==result['sample_rate']['numerator']
            assert row['sample_rate_denominator']==result['sample_rate']['denominator']
            assert row['signal']=='0' and F(row['start'])==0 and F(row['end'])==F(duration)
            assert (int(row['segment_length']),int(row['overlap_samples']),int(row['nfft']))==(n,overlap,n)
            assert row['window']==window and row['detrend']=='none'
            assert float(row['frequency_hz'])==result['frequencies_hz'][i] and float(row['density'])==result['density'][i]
        with localcontext() as c:
            c.prec=100;power=sum(expected)*D.from_float(result['bin_width_hz'])
        close(result['bands'][0]['power'],power)
        rows.append(dict(name=name,expectedDensityDecimal=[str(x) for x in expected],actualDensity=result['density'],
                         sourceSha256=before,output=str(output),csvRows=len(csv_rows),segments=frames))
        products[name]=result
    ratio=products['dc-times-two']['density'][0]/products['dc']['density'][0]
    assert abs(ratio-4)<=1e-12
    errors=[]
    for name,extra,message in [('nfft',dict(nfft=16),'nfft must equal'),('short',dict(end='5e199'),'shorter than')]:
        source=a.work_dir/'dc.edf'; options=a.work_dir/('error-'+name+'.json'); output=a.work_dir/('error-'+name+'-output')
        opts=dict(signal=0,start='0',end='1e200',segment_length=8,overlap_samples=0,window='rectangular')
        opts.update(extra)
        options.write_text(json.dumps(opts),encoding='utf-8')
        v=subprocess.run(['node',str(ROOT/'examples/edf-psd.mjs'),str(source),str(output),str(options)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert v.returncode==2 and message in v.stderr and not output.exists(),v.stderr
        assert hashlib.sha256(source.read_bytes()).hexdigest()==rows[0]['sourceSha256']
        errors.append(dict(name=name,expected=message,exitCode=v.returncode,noOutput=True,sourceUnchanged=True))
    report=dict(status='complete',oracle='Analytical constant rectangular spectrum; otherwise 100-digit Decimal direct DFT with algebraic N=4/8 roots and exact N=4 symmetric Hann weights; raw Fraction calibration rounded to the existing Double view',
                tolerance='positive: max(3e-12 relative, 2 ULP); expected zero: exact zero',cases=rows,errors=errors,amplitudeSquaredRatio=ratio,
                csvColumns=COLUMNS,ordinaryRangeReference='Retained separate check-psd.py DFT/SciPy suite; no default change',fullDoubleDomainClaim=False)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='complete',cases=len(rows),errors=len(errors),csvRows=sum(r['csvRows'] for r in rows),dcDensity=products['dc']['density'][0],amplitudeSquaredRatio=ratio)))


if __name__=='__main__':main()
