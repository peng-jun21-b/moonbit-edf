"""Original fixed-width EDF/BDF bytes, independent of MoonEDF and EDFlib.

The original synthetic signals and annotations are MIT licensed. Decimal
strings are deliberately finer than IEEE Double and 100-nanosecond ticks.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def field(text, width):
    value = str(text).encode('ascii')
    assert len(value) <= width
    return value.ljust(width, b' ')


def tal(onset, events):
    result = (onset+'\x14\x14\0').encode()
    for event in events:
        result += (event['onset']+('' if event['duration'] is None else '\x15'+event['duration'])
                   +'\x14'+event['text']+'\x14\0').encode('utf-8')
    return result


def build(case):
    bdf = case['format'] == 'bdf'
    width, low, high = (3, -8388608, 8388607) if bdf else (2, -32768, 32767)
    blocks = [tal(r['onset'], r['events']) for r in case['records']]
    capacity = (max(map(len, blocks))+width-1)//width
    signals = case['signals']+[dict(label='BDF Annotations' if bdf else 'EDF Annotations', samples_per_record=capacity)]
    ns = len(signals)
    header = (b'\xffBIOSEMI' if bdf else b'0       ')+field('X X X X',80)+field('Startdate 01-JAN-2020 X X X',80)
    header += field('01.01.20',8)+field('00.00.00',8)+field(256*(ns+1),8)
    header += field(('BDF+' if bdf else 'EDF+')+('C' if case['continuity']=='continuous' else 'D'),44)
    header += field(len(blocks),8)+field(case['duration'],8)+field(ns,4)
    columns = [(16, lambda s:s['label']), (80,lambda s:''), (8,lambda s:'' if 'Annotations' in s['label'] else 'uV'),
               (8,lambda s:-1 if 'Annotations' in s['label'] else -100),
               (8,lambda s:1 if 'Annotations' in s['label'] else 100),
               (8,lambda s:low), (8,lambda s:high), (80,lambda s:''),
               (8,lambda s:s['samples_per_record']), (32,lambda s:'')]
    for length, getter in columns:
        header += b''.join(field(getter(s),length) for s in signals)
    assert len(header) == 256*(ns+1)
    data = b''
    for record, annotations in zip(case['records'], blocks, strict=True):
        for samples in record['samples']:
            data += b''.join(n.to_bytes(width, 'little', signed=True) for n in samples)
        data += annotations.ljust(capacity*width,b'\0')
    return header+data


def cases():
    def event(onset, duration, text='edge'): return dict(onset=onset,duration=duration,text=text)
    def record(onset, samples, events=()): return dict(onset=onset,samples=samples,events=list(events))
    def signal(per, label='Fast'): return dict(label=label,samples_per_record=per)
    def query(command, **options): return dict(command=command,**options)
    result = []
    def add(name, signals, records, queries, *, format='edf', continuity='continuous', crop_first=0, rejects=()):
        c = dict(name=name,format=format,continuity=continuity,duration='1',signals=signals,records=records,
                 queries=queries,crop_first=crop_first,select=list(reversed(range(len(signals)))),rejects=list(rejects))
        raw = build(c)
        c.update(sourceBase64=base64.b64encode(raw).decode(), sourceSha256=hashlib.sha256(raw).hexdigest())
        result.append(c)
    add('edf_beyond_double_boundary', [signal(10)],
        [record('+0',[list(range(10))],[event('+0.100000000000000000001','0.1')])],
        [query('epoch-exact',annotation=0,signals=[0],before='0',after='0'),
         query('window-exact',signal=0,start='0.1',end='0.2'),
         query('window-exact',signal=0,start='0.1',end='0.200000000000000000001')],
        rejects=[query('window-exact',signal=0,start='',end='1'),
                 query('window-exact',signal=0,start='NaN',end='1'),
                 query('window-exact',signal=0,start='0',end='1/0'),
                 query('epoch-exact',annotation=0,signals=[0],before='-0.1',after='1')])
    add('bdf_fractional_crop_multirate', [signal(3),signal(2,'Slow')],
        [record('+0.999999999999999999999',[[-8388608,0,8388607],[1,2]]),
         record('+1.999999999999999999999',[[3,4,5],[6,7]],
                [event('+1.123456789012345678901','0.000000000000000000001','fine'),event('-0.000000000000000000001',None,'prior')])],
        [query('window-exact',signal=0,start='0',end='3'),query('window-exact',signal=1,start='1',end='2.5')],
        format='bdf',crop_first=1)
    add('edf_sub_tick_gap', [signal(2)],
        [record('+0',[[1,2]],[event('+0.5','1','gap')]),record('+1.000000000000000000001',[[3,4]])],
        [query('epoch-exact',annotation=0,signals=[0],before='0',after='0',allow_partial=True),
         query('window-exact',signal=0,start='0.5',end='1.5')],continuity='discontinuous',crop_first=1,
        rejects=[query('epoch-exact',annotation=0,signals=[0],before='0',after='0'),
                 query('epoch-exact',annotation=0,signals=[0],before='0',after='0',allow_partial=True,max_samples=1)])
    add('edf_rational_sample_grid', [signal(3)],
        [record('+0',[[10,11,12]],[event('+0.333333333333333333334',None,'third')])],
        [query('epoch-exact',annotation=0,signals=[0],before='0',after='0.333333333333333333333'),
         query('window-exact',signal=0,start='0',end='1')])
    tiny = '+0.'+'0'*180+'1'
    add('edf_long_fraction', [signal(10)], [record('+0',[list(range(10))],[event(tiny,None,'long')])],
        [query('epoch-exact',annotation=0,signals=[0],before='0',after='0.1')])
    add('edf_crop_annotation_growth', [signal(1)],
        [record('+0',[[1]]),record('+12345678.000000000000000000001',[[2]],
          [event('-0.'+'0'*42+'1',None,'a'),event('-0.'+'0'*42+'2',None,'b')]),
         record('+12345679.000000000000000000001',[[3]],[event('+12345679.123456789012345678901',None,'c')])],
        [query('window-exact',signal=0,start='12345678',end='12345681')],continuity='discontinuous',crop_first=1)
    return result


def main():
    manifest = dict(source='Original synthetic data, MIT; EDF+ section 2.2.2 arbitrary accuracy',
                    reference='https://www.edfplus.info/specs/edfplus.html',cases=cases())
    output = ROOT/'examples/exact-time/INPUTS.json'
    text = json.dumps(manifest,indent=2)+'\n'
    if '--check' in sys.argv:
        assert output.read_text('utf-8') == text
    else:
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(text,encoding='utf-8',newline='\n')
    print(json.dumps({'fixtures':len(manifest['cases']), 'checked':'--check' in sys.argv}))


if __name__ == '__main__': main()
