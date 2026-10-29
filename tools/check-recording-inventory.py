"""Receive complete existing-query inventories against independent pre-execution models."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,localcontext
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tools/fixtures/recording-inventory'
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
def identity(path):
    data=path.read_bytes();return dict(path=str(path.resolve()),bytes=len(data),sha256=sha(data))
def number(actual,expected):
    assert type(actual) in (int,float) and math.isfinite(actual)
    with localcontext() as context:
        context.prec=110
        target=Decimal(expected) if '/' not in expected else Decimal(F(expected).numerator)/Decimal(F(expected).denominator)
        if target==0:assert actual==0
        else:
            tolerance=max(abs(target)*Decimal('5e-12'),Decimal.from_float(math.ulp(float(target)))*8)
            assert abs(Decimal.from_float(float(actual))-target)<=tolerance,(actual,expected)
def statistics(actual,expected):
    keys=set(expected['counters'])|set(expected['moments'])|({'rms'} if expected['rms'] is not None else set())
    assert set(actual)==keys
    for key,value in expected['counters'].items():assert type(actual[key]) is int and actual[key]==value,(key,actual[key],value)
    for key,value in expected['moments'].items():number(actual[key],value)
    if expected['rms'] is not None:number(actual['rms'],expected['rms']['decimal'])
def inventory(actual,expected):
    assert set(actual)=={'inspection','annotations','channels'}
    assert actual['inspection']==expected['inspection']
    assert actual['annotations']==expected['annotations']
    assert len(actual['channels'])==len(expected['channels'])
    for received,reference in zip(actual['channels'],expected['channels']):
        assert set(received)=={'signal','statistics','flat_runs'} and received['signal']==reference['signal']
        statistics(received['statistics'],reference['statistics'])
        assert received['flat_runs']==reference['flat_runs']

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--public-output',type=Path,action='append',default=[])
    args=parser.parse_args();assert len(args.public_output)==2
    work=args.work_dir.resolve();assert not work.exists(),'Use a fresh directory; preserve earlier attempts'
    work.mkdir(parents=True)
    hashes=json.loads((FIXTURES/'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name,expected in hashes.items():
        data=(FIXTURES/name).read_bytes();assert len(data)==expected['bytes'] and sha(data)==expected['sha256'],name
    model=json.loads((FIXTURES/'EXPECTED.json').read_text(encoding='utf-8'))
    assert model['frozenBeforeProductExecution'] and len(model['cases'])==6 and len(model['errors'])==10
    cases=model['cases'];errors=model['errors'];public_models={c['name']:c for c in cases+[e for e in errors if not e['hostOnly']]}
    public=[];commands=[];products=[];bundles=[]
    for path in args.public_output:
        rows=json.loads(path.read_text(encoding='utf-8'))
        assert len(rows)==12 and {r['name'] for r in rows}==set(public_models)
        for row in rows:
            reference=public_models[row['name']]
            if 'errorContains' in reference:
                assert set(row)=={'name','error'} and reference['errorContains'] in row['error'],row['name']
            else:
                assert set(row)=={'name','result','source'}
                assert all(type(b) is int and 0<=b<=255 for b in row['source'])
                assert bytes(row['source'])==(FIXTURES/reference['source']).read_bytes()
                inventory(row['result'],reference['expected'])
        public.append(dict(**identity(path),completeResults=6,checkedErrors=6))
    inputs=work/'inputs';outputs=work/'outputs';raw=work/'raw'
    for p in [inputs,outputs,raw]:p.mkdir()
    source_paths={}
    for source in sorted({c['source'] for c in cases+errors}):
        path=inputs/('raw input # '+source);path.write_bytes((FIXTURES/source).read_bytes());source_paths[source]=path
    def invoke(name,source,target,minimum,options):
        command=['node',str(ROOT/'examples/recording-inventory.mjs'),str(source),str(target),str(minimum),str(options)]
        p=subprocess.run(command,cwd=ROOT,env=os.environ.copy(),capture_output=True,timeout=90)
        stdout,stderr=raw/(name+'.stdout'),raw/(name+'.stderr');stdout.write_bytes(p.stdout);stderr.write_bytes(p.stderr)
        commands.append(dict(name=name,command=command,exitCode=p.returncode,stdout=identity(stdout),stderr=identity(stderr)))
        return p
    for case in cases:
        name=case['name'];source=source_paths[case['source']];options=inputs/(name+' read options.json');options.write_bytes((FIXTURES/case['options']).read_bytes())
        target=outputs/(name+' inventory # new')
        p=invoke(name,source,target,case['minimum_samples'],options)
        assert p.returncode==0 and not p.stderr,(name,p.stderr.decode(errors='replace'))
        manifest=json.loads((target/'manifest.json').read_text(encoding='utf-8'))
        assert set(manifest)=={'source','minimum_samples','read_policy','read_options_sha256','inspection','annotations','channels','files'}
        assert manifest['source']==dict(path=str(source.resolve()),bytes=source.stat().st_size,sha256=sha(source.read_bytes()))
        assert manifest['minimum_samples']==case['minimum_samples']
        assert manifest['read_policy']==({} if case['policyText'] is None else dict(time_tolerance=case['policyText']))
        assert manifest['read_options_sha256']==sha(options.read_bytes())
        assert manifest['inspection']=='inspect.json' and manifest['annotations']=='annotations.json'
        expected_paths={'inspect.json','annotations.json'}
        expected_channels=[]
        for channel in case['expected']['channels']:
            s=channel['signal'];statistics_file=f'channel-{s}-statistics.json';flat_file=f'channel-{s}-flat.json'
            expected_channels.append(dict(signal=s,statistics=statistics_file,flat_runs=flat_file));expected_paths.update([statistics_file,flat_file])
        assert manifest['channels']==expected_channels
        assert {f['file'] for f in manifest['files']}==expected_paths and len(manifest['files'])==len(expected_paths)
        assert {p.name for p in target.iterdir()}==expected_paths|{'manifest.json'}
        for item in manifest['files']:
            data=(target/item['file']).read_bytes()
            assert set(item)=={'file','bytes','sha256'} and item['bytes']==len(data) and item['sha256']==sha(data)
        received=dict(inspection=json.loads((target/'inspect.json').read_text(encoding='utf-8')),
                      annotations=json.loads((target/'annotations.json').read_text(encoding='utf-8')),channels=[])
        for channel in expected_channels:
            received['channels'].append(dict(signal=channel['signal'],statistics=json.loads((target/channel['statistics']).read_text(encoding='utf-8')),
                                            flat_runs=json.loads((target/channel['flat_runs']).read_text(encoding='utf-8'))))
        inventory(received,case['expected'])
        assert json.loads(p.stdout)==dict(output=str(target.resolve()),sourceSha256=manifest['source']['sha256'],channels=len(expected_channels),files=len(expected_paths)+1)
        product_files=[identity(p) for p in sorted(target.iterdir())];products.extend(product_files)
        summary=outputs/(name+'.receiver-summary.json')
        save(summary,dict(source=identity(source),readOptions=identity(options),manifest=identity(target/'manifest.json'),
                          completeSidecars=product_files,wholeInspectionAnnotationsAndNativeChannelQueriesReceived=True))
        bundles.append(dict(name=name,directory=str(target),sidecars=len(expected_paths),summary=identity(summary)))
    for case in errors:
        name=case['name'];source=source_paths[case['source']];options=inputs/(name+' read options.json');options.write_bytes((FIXTURES/case['options']).read_bytes())
        target=outputs/(name+' rejected')
        p=invoke(name,source,target,case.get('minimum_samples',case.get('minimum_arg')),options)
        assert p.returncode==2 and not p.stdout and case['errorContains'] in p.stderr.decode('utf-8') and not target.exists(),name
    existing=outputs/'occupied inventory';existing.mkdir();sentinel=existing/'keep.txt';sentinel.write_bytes(b'keep exact existing directory\n')
    before=identity(sentinel)
    p=invoke('occupied-output',source_paths[cases[0]['source']],existing,2,inputs/'continuous read options.json')
    assert p.returncode==2 and b'output directory exists' in p.stderr and identity(sentinel)==before and {p.name for p in existing.iterdir()}=={'keep.txt'}
    for source,path in source_paths.items():assert path.read_bytes()==(FIXTURES/source).read_bytes()
    for name,expected in hashes.items():assert sha((FIXTURES/name).read_bytes())==expected['sha256']
    receipt=dict(status='passed',oracle=model['oracle'],numericTolerance=model['numericTolerance'],originalFixturesUnchanged=True,
                 publicReceivers=public,fileCompleteBundles=6,fileCheckedErrors=10,existingDirectoryControls=1,
                 completeSavedSidecars=sum(b['sidecars'] for b in bundles),sourceBytesUnchanged=True,
                 bundles=bundles,commands=commands,products=products,thirdPartyAdoptionClaim=False)
    args.output.parent.mkdir(parents=True,exist_ok=True);save(args.output,receipt)
    print(json.dumps(dict(status='passed',publicCompleteResults=12,publicErrors=12,fileCompleteBundles=6,fileErrors=10,
                          completeSavedSidecars=receipt['completeSavedSidecars'],existingDirectoryControls=1)))
if __name__=='__main__':main()
