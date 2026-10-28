from numeric_view import view
"""Verify unchanged upstream BDF bytes against pyEDFlib, including transformations.

Inputs stay external: these are MNE test corpus files, not established recordings
from customers. The second input records a reference rejection, never a pass.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import subprocess
import tempfile

import numpy as np
import pyedflib

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '47d5be239f12eb310e7799b5119baf24bed89d05'
FILES = {
    'test_bdf_stim_channel.bdf': 'd555c9550069c0402835092ac3b2136ac238c8b8996069e11594350826d765a3',
    'test.bdf': 'd97eb2809b8314bf097493b8e2b04140b86722e0de749a563fa6bab2bc63554a',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = {}
    for name, expected in FILES.items():
        path = (args.directory / name).resolve()
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected, name
        sources[name] = dict(bytes=len(raw), sha256=expected,
            url=f'https://raw.githubusercontent.com/mne-tools/mne-python/{COMMIT}/mne/io/edf/tests/data/{name}')
    source = (args.directory / 'test_bdf_stim_channel.bdf').resolve()
    rejected = (args.directory / 'test.bdf').resolve()
    try:
        with pyedflib.EdfReader(str(rejected)):
            raise AssertionError('Reference behavior changed; review the recorded boundary')
    except OSError as error:
        reference_rejection = str(error).replace(str(rejected), rejected.name)

    with pyedflib.EdfReader(str(source)) as reader:
        headers = reader.getSignalHeaders()
        digital = [reader.readSignal(i, digital=True) for i in range(reader.signals_in_file)]
        physical = [reader.readSignal(i) for i in range(3)]  # no device-specific Status interpretation
        rates = reader.getSampleFrequencies()
        start_time = reader.getStartdatetime()
        assert reader.signals_in_file == 4 and reader.datarecords_in_file == 10
        assert reader.datarecord_duration == 1 and reader.file_duration == 10
    tasks, checks = [], []
    def add(options, check, input=source, kind='report', output=None):
        task = dict(kind=kind, input=str(input), options=options)
        if output is not None:
            task['output'] = str(output)
        tasks.append(task)
        checks.append(check)
    def inspect(value):
        assert value['format'] == 'bdf' and value['continuity'] == 'plain'
        assert value['records'] == 10 and value['duration'] == 1
        assert value['starts'] == list(range(10)) and value['annotations'] == 0 and value['gaps'] == []
        assert len(value['signals']) == 4
        for actual, expected in zip(value['signals'], headers, strict=True):
            assert actual['label'] == expected['label'] and actual['unit'] == expected['dimension']
            assert actual['samples_per_record'] == expected['sample_frequency'] == 500
            for key in ['digital_min', 'digital_max', 'physical_min', 'physical_max']:
                assert actual[key] == expected[key], key
    add(dict(command='inspect'), inspect)
    for signal in range(4):
        def samples(value, signal=signal):
            np.testing.assert_array_equal(value['values'], digital[signal])
            np.testing.assert_allclose(value['times'], np.arange(5000)/rates[signal], rtol=0, atol=2e-15)
        add(dict(command='channel', signal=signal, count=5000), samples)
    for signal in range(3):
        add(dict(command='channel', signal=signal, count=5000, physical=True),
            lambda v, signal=signal: np.testing.assert_allclose(v['values'], physical[signal], rtol=1e-12, atol=1e-10))
    window_samples = 0
    for signal in range(4):
        for left, right in [(0, .002), (.999, 2.001), (9.998, 10)]:
            indices = np.flatnonzero((np.arange(5000)/500 >= left) & (np.arange(5000)/500 < right))
            window_samples += len(indices)
            def window(value, signal=signal, indices=indices):
                rows = value['samples']
                np.testing.assert_array_equal([v['digital'] for v in rows], digital[signal][indices])
                np.testing.assert_array_equal([v['record']*500+v['sample'] for v in rows], indices)
                np.testing.assert_allclose([v['time'] for v in rows], indices/500, rtol=0, atol=2e-15)
                assert value['gaps'] == []
            add(dict(command='window', signal=signal, start=left, end=right), window)
    # Capture a compatibility boundary separately. This file is not admitted to
    # the independently validated sample count merely because MoonEDF reads it.
    def rejected_metadata(value):
        assert value['format'] == 'bdf' and value['records'] == 1 and len(value['signals']) == 73
    add(dict(command='inspect'), rejected_metadata, input=rejected)
    with tempfile.TemporaryDirectory(prefix='external-bdf-') as folder:
        temp = Path(folder)
        transformations = [
            ('copy', {}, [0, 1, 2, 3], 0, 5000),
            ('select', {'signals': [3, 0]}, [3, 0], 0, 5000),
            ('crop', {'first_record': 2, 'records': 3}, [0, 1, 2, 3], 1000, 2500),
            ('plus', {}, [0, 1, 2, 3], 0, 5000),
        ]
        for name, options, _, _, _ in transformations:
            add(dict(command=name, **options), lambda v: None, kind='transform', output=temp/(name+'.bdf'))
        request, response = temp/'request.json', temp/'response.json'
        request.write_text(json.dumps(tasks), encoding='utf-8')
        subprocess.run(['node', 'tools/reference-batch.mjs', str(request), str(response)], cwd=ROOT, check=True)
        results = json.loads(response.read_text(encoding='utf-8'))
        for task, check, result in zip(tasks, checks, results, strict=True):
            assert result['ok'], (task, result)
            check(view(result['result']))
        assert (temp/'copy.bdf').read_bytes() == source.read_bytes()
        transformed_samples = 0
        for name, _, selected, first, end in transformations:
            with pyedflib.EdfReader(str(temp/(name+'.bdf'))) as output:
                assert output.signals_in_file == len(selected)
                assert output.file_duration == (end-first)/500
                assert output.getStartdatetime() == start_time + datetime.timedelta(seconds=first/500)
                for index, original in enumerate(selected):
                    assert output.getSignalHeader(index) == headers[original]
                    np.testing.assert_array_equal(output.readSignal(index, digital=True), digital[original][first:end])
                    transformed_samples += end-first
                    if original < 3:
                        np.testing.assert_allclose(output.readSignal(index), physical[original][first:end], rtol=1e-12, atol=1e-10)
    result = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        reference='pyEDFlib '+pyedflib.__version__, sources=sources, sourceModified=False,
        externalDigitalSamples=20000, externalPhysicalSamples=15000, timeWindows=12,
        windowSamples=window_samples, transformations=4, transformedDigitalSamples=transformed_samples,
        copyByteIdentical=True, statusRawPreserved=True, checks=len(tasks),
        referenceRejection=dict(file='test.bdf', error=reference_rejection,
            headerDataRecords=repr(rejected.read_bytes()[236:244]), candidateAccepted=True,
            countedAsReferencePass=False),
        limits=['MNE upstream test corpus; acquisition provenance and clinical validity not established',
            'No negative digital samples in this external fixture; signed extremes retain prior synthetic coverage',
            'Status is preserved as raw channel data; no BioSemi trigger-bit interpretation',
            'No external discontinuous BDF coverage; inputs not redistributed'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
