"""Receive complete edited files and public-package outputs against pre-edit raw bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tools/fixtures/identification'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))

def identity(path):
    data = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(data), sha256=sha(data))

def unchanged_regions(source, result, options):
    assert len(source) == len(result)
    allowed = set()
    for key, start in [('patient', 8), ('recording', 88)]:
        if key in options:
            allowed.update(range(start, start+80))
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result)))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--public-output', type=Path, action='append', default=[])
    args = parser.parse_args()
    assert len(args.public_output) == 2, 'Supply actual JS and Wasm-GC public receiver stdout'
    work = args.work_dir.resolve()
    assert not work.exists(), 'Preserve previous receiver attempts; use a fresh directory'
    work.mkdir(parents=True)
    manifest = json.loads((FIXTURES/'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        data = (FIXTURES/name).read_bytes()
        assert len(data) == expected['bytes'] and sha(data) == expected['sha256'], name
    frozen = json.loads((FIXTURES/'EXPECTED.json').read_text(encoding='utf-8'))
    cases, errors = frozen['cases'], frozen['errors']
    assert len(cases) == 14 and len(errors) == 13 and frozen['frozenBeforeProductEdits']
    public_models = {c['name']: c for c in cases+[e for e in errors if not e['hostOnly']]}
    products, public_receipts, commands = [], [], []
    for index, path in enumerate(args.public_output):
        rows = json.loads(path.read_text(encoding='utf-8'))
        assert len(rows) == len(public_models) and len({r['name'] for r in rows}) == len(rows)
        assert {r['name'] for r in rows} == set(public_models)
        destination = work/('public-'+str(index))
        destination.mkdir()
        for row in rows:
            model = public_models[row['name']]
            if 'errorContains' in model:
                assert set(row) == {'name', 'error'}
                assert model['errorContains'] in row['error'], row['name']
                continue
            assert set(row) == {'name', 'data', 'encoded', 'source', 'metadata'}
            source = (FIXTURES/model['source']).read_bytes()
            options = json.loads((FIXTURES/model['options']).read_text(encoding='utf-8'))
            for key, expected_file in [('data', model['expected']), ('encoded', model['encoded'])]:
                assert all(type(v) is int and 0 <= v <= 255 for v in row[key])
                actual = bytes(row[key])
                result_file = destination/(row['name']+'.'+key+Path(model['source']).suffix)
                result_file.write_bytes(actual)
                products.append(identity(result_file))
                assert actual == (FIXTURES/expected_file).read_bytes(), (row['name'], key)
            assert bytes(row['source']) == source, row['name']
            unchanged_regions(source, bytes(row['data']), options)
            expected = model['model']
            metadata = dict(patient=expected['inspect']['patient'], recording=expected['inspect']['recording'],
                            start=expected['start'], declared_records=expected['inspect']['declared_records'],
                            starts=expected['inspect']['starts'], annotations=expected['annotations'], gaps=expected['inspect']['gaps'])
            assert row['metadata'] == metadata, (row['name'], 'decoded public metadata')
        public_receipts.append(dict(**identity(path), completeDataAndEncodeResults=len(cases), checkedErrors=11))
    inputs = work/'inputs'
    outputs = work/'files'
    raw = work/'raw'
    for p in [inputs, outputs, raw]:
        p.mkdir()
    source_paths = {}
    for name in sorted({c['source'] for c in cases+errors}):
        path = inputs/('raw input # '+name)
        path.write_bytes((FIXTURES/name).read_bytes())
        source_paths[name] = path
    def invoke(name, arguments):
        command = ['node', str(ROOT/'tools/edf.mjs'), *map(str, arguments)]
        p = subprocess.run(command, cwd=ROOT, env=os.environ.copy(), capture_output=True, timeout=90)
        stdout, stderr = raw/(name+'.stdout'), raw/(name+'.stderr')
        stdout.write_bytes(p.stdout)
        stderr.write_bytes(p.stderr)
        commands.append(dict(name=name, command=command, exitCode=p.returncode, stdout=identity(stdout), stderr=identity(stderr)))
        return p
    for case in cases:
        name = case['name']
        options_bytes = (FIXTURES/case['options']).read_bytes()
        options = json.loads(options_bytes)
        option_path = inputs/(name+' options.json')
        option_path.write_bytes(options_bytes)
        target = outputs/(name+' new # output'+Path(case['source']).suffix)
        source_path = source_paths[case['source']]
        p = invoke(name+'-edit', ['identification-set', source_path, target, option_path])
        assert p.returncode == 0 and not p.stderr, (name, p.stderr.decode(errors='replace'))
        assert json.loads(p.stdout) == dict(output=str(target), bytes=target.stat().st_size)
        actual = target.read_bytes()
        assert actual == (FIXTURES/case['expected']).read_bytes(), name
        unchanged_regions(source_path.read_bytes(), actual, options)
        products.append(identity(target))
        read_options = inputs/(name+' read-policy.json')
        save_json(read_options, {k: v for k, v in options.items() if k == 'time_tolerance'})
        reopened = invoke(name+'-inspect', ['inspect', target, read_options])
        assert reopened.returncode == 0 and not reopened.stderr
        assert json.loads(reopened.stdout) == case['model']['inspect'], (name, 'reopened complete inspect')
        annotations = invoke(name+'-annotations', ['annotations', target, read_options])
        assert annotations.returncode == 0 and not annotations.stderr
        assert json.loads(annotations.stdout) == case['model']['annotations'], (name, 'reopened complete annotations')
        save_json(outputs/(name+'.receiver-summary.json'), dict(input=identity(source_path), request=identity(option_path),
                  output=identity(target), completeExpectedBytes=identity(FIXTURES/case['expected']),
                  independentClockSampleView=case['model']['points'], completeInspectAndAnnotationsReceived=True))
    for case in errors:
        name = case['name']
        option_path = inputs/(name+' options.json')
        option_path.write_bytes((FIXTURES/case['options']).read_bytes())
        target = outputs/(name+' rejected.edf')
        p = invoke(name, ['identification-set', source_paths[case['source']], target, option_path])
        assert p.returncode == 2 and not p.stdout and p.stderr and not target.exists(), name
        assert case['errorContains'] in p.stderr.decode('utf-8'), name
    existing = outputs/('patient-only new # output'+Path(cases[0]['source']).suffix)
    before = existing.read_bytes()
    p = invoke('existing-output', ['identification-set', source_paths[cases[0]['source']], existing, inputs/'patient-only options.json'])
    assert p.returncode == 2 and b'output exists' in p.stderr and existing.read_bytes() == before
    for name, path in source_paths.items():
        assert path.read_bytes() == (FIXTURES/name).read_bytes(), name
    for name, expected in manifest.items():
        assert sha((FIXTURES/name).read_bytes()) == expected['sha256'], name
    receipt = dict(status='passed', oracle=frozen['oracle'], frozenFixturesUnchanged=True,
                   publicReceivers=public_receipts, fileCompleteResults=len(cases), fileCheckedErrors=len(errors),
                   existingOutputControls=1, reopenedCompleteInspections=14, reopenedCompleteAnnotationArrays=14,
                   exactWholeFileComparison=True, onlyRequestedFieldsMayDiffer=True,
                   unknownCountRawPreserved=True, existingEncodeFinalizationVerifiedSeparately=True,
                   commands=commands, binaryProducts=products, thirdPartyAdoptionClaim=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, receipt)
    print(json.dumps(dict(status='passed', publicCompleteResults=28, publicCheckedErrors=22,
                          fileCompleteResults=14, fileCheckedErrors=13, existingOutputControls=1)))

if __name__ == '__main__':
    main()
