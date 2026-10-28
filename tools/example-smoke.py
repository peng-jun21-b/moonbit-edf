"""Execute documented CLI examples and independently inspect written outputs."""
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import pyedflib
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='moonedf-example-') as tmp:
    p=Path(tmp)
    def command(*args):
        return subprocess.check_output(['node',str(ROOT/'tools/edf.mjs'),*map(str,args)],text=True,encoding='utf-8',cwd=ROOT)
    command('create',p/'demo.edf',ROOT/'examples/create.json')
    assert json.loads(command('inspect',p/'demo.edf'))['records']==3
    assert json.loads(command('annotations',p/'demo.edf'))[0]['text']=='合成标记'
    assert json.loads(command('stats',p/'demo.edf',ROOT/'examples/stats.json'))['samples']==12
    assert json.loads(command('flat',p/'demo.edf',ROOT/'examples/flat.json'))[0]['samples']==4
    for op in ('select','crop'):
        command(op,p/'demo.edf',p/f'{op}.edf',ROOT/f'examples/{op}.json')
        with pyedflib.EdfReader(str(p/f'{op}.edf')) as reader:
            assert reader.signals_in_file==(1 if op=='select' else 2)
            assert reader.datarecords_in_file==(3 if op=='select' else 2)
    rows=list(csv.DictReader(io.StringIO(command('csv',p/'demo.edf',ROOT/'examples/csv.json'))))
    assert len(rows)==18
    window=json.loads(command('window',p/'demo.edf',ROOT/'examples/window.json'))
    assert [(v['record'],v['sample']) for v in window['samples']]==[(0,2),(0,3),(1,0),(1,1),(1,2),(1,3),(2,0)]
    assert window['gaps']==[]
    window_rows=list(csv.DictReader(io.StringIO(command('window-csv',p/'demo.edf',ROOT/'examples/window-csv.json'))))
    assert len(window_rows)==11
    assert all(.5<=float(row['time_seconds'])<2.25 for row in window_rows)
    with pyedflib.EdfReader(str(p/'demo.edf')) as reader:
        np.testing.assert_array_equal(reader.readSignal(0,digital=True),[-32768,0,0,32767,10,10,10,10,1,2,3,4])
        assert reader.readAnnotations()[2][0]=='合成标记'
print('Documented CLI workflows passed; files independently read by pyedflib.')
