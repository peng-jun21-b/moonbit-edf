"""Independent fixed-width/TAL reader and exhaustive Fraction time oracle.

EDFlib uses 100ns internally, so it cannot certify these finer decimal cases.
This original oracle instead compares rational seconds without quantization.
"""
import argparse
import datetime
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(data):
    bdf = data[:8] == b'\xffBIOSEMI'
    assert bdf or data[:8] == b'0       '
    width = 3 if bdf else 2
    ns, nr, start = int(data[252:256]), int(data[236:244]), int(data[184:192])
    assert start == 256*(ns+1)
    duration = F(data[244:252].decode().strip())
    columns, at = [], 256
    for size in [16,80,8,8,8,8,8,80,8,32]:
        columns.append([data[at+i*size:at+(i+1)*size].decode().strip() for i in range(ns)])
        at += ns*size
    signals = [dict(label=columns[0][s],unit=columns[2][s],physical_min=F(columns[3][s]),physical_max=F(columns[4][s]),
                    digital_min=int(columns[5][s]),digital_max=int(columns[6][s]),per=int(columns[8][s])) for s in range(ns)]
    record_bytes = sum(s['per'] for s in signals)*width
    assert len(data) == start+nr*record_bytes
    records, annotations = [], []
    for r in range(nr):
        record = dict(samples=[],raw=[],starts=[],tals=[])
        at = start+r*record_bytes
        for s, channel in enumerate(signals):
            size = channel['per']*width
            raw = data[at:at+size]; at += size
            record['raw'].append(raw)
            if 'Annotations' not in channel['label']:
                record['samples'].append([int.from_bytes(raw[i:i+width],'little',signed=True) for i in range(0,size,width)])
                continue
            for block in raw.split(b'\0'):
                if not block: continue
                fields = block.split(b'\x14')
                assert fields[-1] == b''
                timestamp = fields[0].split(b'\x15')
                assert len(timestamp) in (1,2)
                onset = timestamp[0].decode()
                duration_text = timestamp[1].decode() if len(timestamp)==2 else None
                texts = [t.decode('utf-8') for t in fields[1:-1]]
                record['tals'].append((s,onset,duration_text,texts))
                if not record['starts']: record['starts'].append(F(onset))
                for text in texts:
                    if text:
                        annotations.append(dict(record=r,signal=s,onset=onset,duration=duration_text,text=text))
        assert record['starts']
        records.append(record)
    return dict(signals=signals,records=records,annotations=annotations,duration=duration,record_bytes=record_bytes,
                date=data[168:176].decode(),time=data[176:184].decode(),recording=data[88:168].decode().strip())


def plain(value, signed=True):
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0: denominator //= 2; twos += 1
    while denominator % 5 == 0: denominator //= 5; fives += 1
    assert denominator == 1
    scale = max(twos,fives)
    coefficient = abs(value.numerator)*10**scale//value.denominator
    digits = str(coefficient).rjust(scale+1,'0')
    text = digits if scale == 0 else (digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.')
    return ('-' if value < 0 else '+' if signed else '')+text


def normalized(annotation):
    return {**annotation,'duration':annotation.get('duration')}


def gaps(known,start,end):
    result = []
    for r in range(1,len(known['records'])):
        previous = known['records'][r-1]['starts'][0]+known['duration']
        next_start = known['records'][r]['starts'][0]
        lo,hi = max(previous,start),min(next_start,end)
        if lo < hi: result.append((r-1,lo,hi))
    return result


def check_window(result,known,signal,start,end,exact=True):
    expected = []
    channel = known['signals'][signal]
    for r, record in enumerate(known['records']):
        for j,digital in enumerate(record['samples'][signal]):
            time = record['starts'][0]+known['duration']*F(j,channel['per'])
            if start <= time < end: expected.append((r,j,digital,time))
    assert len(result['samples']) == len(expected), (result,expected)
    for sample,(r,j,digital,time) in zip(result['samples'],expected,strict=True):
        assert (sample['record'],sample['sample'],sample['digital']) == (r,j,digital)
        if exact:
            assert F(int(sample['time_numerator']),int(sample['time_denominator'])) == time
        else:
            assert F(int(sample['time']['numerator']),int(sample['time']['denominator'])) == time
        physical = (F(digital)-channel['digital_min'])/(channel['digital_max']-channel['digital_min'])*(channel['physical_max']-channel['physical_min'])+channel['physical_min']
        assert math.isclose(sample['physical'],float(physical),rel_tol=1e-11,abs_tol=1e-11)
    if exact:
        assert F(result['start']) == start and F(result['end']) == end
        assert [(g['after_record'],F(g['start']),F(g['end'])) for g in result['gaps']] == gaps(known,start,end)
    return len(expected)


def check_query(options,result,known,exact=True):
    if options['command'] == 'window-exact':
        return check_window(result,known,options['signal'],F(options['start']),F(options['end']))
    event = known['annotations'][options['annotation']]
    start = F(event['onset'])-F(str(options['before']))
    end = F(event['onset'])+(F(event['duration']) if event['duration'] is not None and options.get('include_duration',True) else 0)+F(str(options['after']))
    complete = (start >= known['records'][0]['starts'][0] and
                end <= known['records'][-1]['starts'][0]+known['duration'] and not gaps(known,start,end))
    assert result['complete'] == complete
    if exact:
        assert normalized(result['annotation']) == event
        assert F(result['start']) == start and F(result['end']) == end
    count = sum(check_window(channel,known,signal,start,end,exact) for channel,signal in zip(result['channels'],options['signals'],strict=True))
    assert result['samples'] == count
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT/'examples/exact-time/INPUTS.json').read_text())
    receipt = json.loads((args.directory/'ENGINE.json').read_text())
    checks, cases = 0, []
    for c,item in zip(manifest['cases'],receipt['cases'],strict=True):
        assert c['name'] == item['name']
        parsed = {}
        for key,file in item['files'].items():
            data = (args.directory/file['file']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == file['sha256']
            parsed[key] = read(data)
            assert [normalized(a) for a in file['annotations']] == parsed[key]['annotations']
        known = parsed['source']
        expected_events = [dict(record=r,signal=len(c['signals']),**e) for r,record in enumerate(c['records']) for e in record['events']]
        assert known['annotations'] == expected_events
        for r,record in enumerate(c['records']):
            assert known['records'][r]['samples'] == record['samples']
            assert known['records'][r]['starts'][0] == F(record['onset'])
        for q in item['queries']:
            check_query(q['options'],q['result'],known); checks += 1
        for q in item['legacy']:
            check_query(q['options'],q['result'],known,False); checks += 1
        for key in ['copy','created']:
            output = parsed[key]
            assert output['annotations'] == expected_events
            assert output['duration'] == F(c['duration'])
            for original,actual in zip(known['records'],output['records'],strict=True):
                assert actual['samples'] == original['samples'] and actual['starts'] == original['starts']
                assert actual['raw'][:-1] == original['raw'][:-1]
        selected = parsed['selected']
        for original,actual in zip(known['records'],selected['records'],strict=True):
            assert actual['samples'] == [original['samples'][s] for s in c['select']]
            assert actual['raw'][:-1] == [original['raw'][s] for s in c['select']]
            assert actual['tals'] == original['tals']
        cropped = parsed['cropped']
        first = c['crop_first']
        shift = math.floor(F(c['records'][first]['onset']))
        date = datetime.datetime(2020,1,1)+datetime.timedelta(seconds=shift)
        assert cropped['date'] == date.strftime('%d.%m.%y') and cropped['time'] == date.strftime('%H.%M.%S')
        assert cropped['recording'].startswith('Startdate '+date.strftime('%d-%b-%Y').upper())
        for original,actual in zip(known['records'][first:],cropped['records'],strict=True):
            assert actual['samples'] == original['samples'] and actual['raw'][:-1] == original['raw'][:-1]
            assert actual['starts'][0] == original['starts'][0]-shift
            assert actual['tals'] == [(s,plain(F(onset)-shift),duration,texts) for s,onset,duration,texts in original['tals']]
        if c['name'] == 'edf_crop_annotation_growth':
            assert cropped['record_bytes'] > known['record_bytes']
        cases.append(dict(name=c['name'],products=len(item['files']),queries=len(item['queries']),legacy_queries=len(item['legacy']),
                          rejected=len(item['rejected']),sourceSha256=c['sourceSha256']))
    report = dict(status='passed',oracle='original Python fixed-width/TAL parser and exhaustive fractions.Fraction',
                  not_an_edflib_subtick_validation=True,engineSha256=receipt['engineSha256'],cases=cases,
                  products=sum(c['products'] for c in cases),queries=checks,cliChecks=receipt['cliChecks'])
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['cases','engineSha256']}))


if __name__ == '__main__': main()
