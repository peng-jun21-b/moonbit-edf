from numeric_view import view
"""Independent pyEDFlib checks of a fixed PhysioNet EDF+ recording; no diagnosis."""
from pathlib import Path
import argparse, hashlib, json, subprocess, tempfile, datetime
from decimal import Decimal
import numpy as np
import pyedflib

ROOT=Path(__file__).resolve().parents[1]
SHA='3427c8d01bff1380bc9ab9f27a35ece2af5dfadf3e291bbc05eb66e4dadbfe2e'
def main():
 p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 source=a.input.resolve();assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA
 tasks=[];checks=[]
 def add(options,check,kind='report',input=source):
  tasks.append(dict(kind=kind,input=str(input),options=options));checks.append(check)
 with pyedflib.EdfReader(str(source)) as reader, tempfile.TemporaryDirectory(prefix='edf-public-') as td:
  temp=Path(td);onsets,durations,texts=reader.readAnnotations();count=reader.signals_in_file
  digital=[reader.readSignal(i,digital=True) for i in range(count)]
  physical={i:reader.readSignal(i) for i in [0,8,32]}
  headers=[reader.getSignalHeader(i) for i in range(count)]
  rates=reader.getSampleFrequencies();record_duration=reader.datarecord_duration
  def inspect(value):
   assert value['records']==reader.datarecords_in_file==125
   assert value['duration']==record_duration==1.0
   assert len(value['signals'])==65 and value['annotations']==len(onsets)==30
   for i,h in enumerate(headers):
    actual=value['signals'][i]
    assert actual['label']==h['label'] and actual['unit']==h['dimension']
    assert actual['samples_per_record']/record_duration==rates[i]==160.0
  add({'command':'inspect'},inspect)
  def annotations(value):
   assert len(value)==len(onsets)
   for i,row in enumerate(value):
    assert row['text']==texts[i]
    np.testing.assert_allclose([row['onset'],row['duration']],[onsets[i],durations[i]],rtol=0,atol=1e-12)
  add({'command':'annotations'},annotations)
  for i in range(count):
   add(dict(command='channel',signal=i,count=len(digital[i])),lambda v,i=i:np.testing.assert_array_equal(v['values'],digital[i]))
  for i in physical:
   add(dict(command='channel',signal=i,count=len(physical[i]),physical=True),lambda v,i=i:np.testing.assert_allclose(v['values'],physical[i],rtol=1e-12,atol=1e-10))
  total_epoch_samples=0
  for event in range(len(onsets)):
   # Decimal event times from the independent reader: avoid reproducing the
   # candidate's original binary-sum endpoint bug in this oracle.
   start=float(Decimal(str(onsets[event]))-Decimal('.25'))
   end=float(Decimal(str(onsets[event]))+Decimal(str(durations[event]))+Decimal('.25'))
   def epoch(v,event=event,start=start,end=end):
    assert v['annotation_index']==event and v['annotation']['text']==texts[event]
    assert v['start']==start and abs(v['end']-end)<1e-12
    assert v['complete']==(start>=0 and end<=125)
    total=0
    for result,i in zip(v['channels'],[0,8,32],strict=True):
     # Independent sample grid from the reference reader's sample rate.
     times=np.arange(len(digital[i]))/rates[i]
     indices=np.flatnonzero((times>=start)&(times<end));rows=result['samples'];total+=len(rows)
     np.testing.assert_array_equal([x['digital'] for x in rows],digital[i][indices])
     np.testing.assert_allclose([x['physical'] for x in rows],physical[i][indices],rtol=1e-12,atol=1e-10)
     np.testing.assert_array_equal([x['record']*160+x['sample'] for x in rows],indices)
     np.testing.assert_allclose([x['time'] for x in rows],times[indices],rtol=0,atol=3e-14)
     assert result['unit']==headers[i]['dimension'] and result['gaps']==[]
    assert v['samples']==total
   add(dict(command='epoch',annotation=event,signals=[0,8,32],before=.25,after=.25,allow_partial=True),epoch)
   total_epoch_samples+=sum(np.count_nonzero((np.arange(len(digital[i]))/rates[i]>=start)&(np.arange(len(digital[i]))/rates[i]<end)) for i in [0,8,32])
  bad=[dict(annotation=0,signals=[0],before=.25,after=.25),dict(annotation=1,signals=[0,8],before=0,after=0,max_samples=2),dict(annotation=1,signals=[0,0],before=0,after=0),dict(annotation=30,signals=[0],before=0,after=0)]
  for options in bad:add(dict(command='epoch',**options),None)
  raw=source.read_bytes()
  for suffix,data in [('truncated',raw[:-1]),('extra-byte',raw+b'\0')]:
   broken=temp/(suffix+'.edf');broken.write_bytes(data);add(dict(command='validate'),None,input=broken)
  request=temp/'requests.json';response=temp/'response.json';request.write_text(json.dumps(tasks),encoding='utf-8')
  subprocess.run(['node','tools/reference-batch.mjs',str(request),str(response)],cwd=ROOT,check=True)
  values=json.loads(response.read_text(encoding='utf-8'))
  for task,check,value in zip(tasks,checks,values,strict=True):
   if check is None:assert not value['ok'],task
   else:
    assert value['ok'],(task,value)
    check(view(value['result']))
  result=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),inputSha256=SHA,inputBytes=len(raw),
   dataset='PhysioNet EEG Motor Movement/Imagery 1.0.0 S001/S001R03.edf',license='ODC-By-1.0',
   source='https://physionet.org/content/eegmmidb/1.0.0/',doi='10.13026/C28G6P',reference='pyEDFlib '+pyedflib.__version__,
   signals=count,records=reader.datarecords_in_file,durationSeconds=reader.file_duration,annotations=len(onsets),
   digitalValuesCompared=sum(len(x) for x in digital),physicalValuesCompared=sum(len(x) for x in physical.values()),
   eventWindowsCompared=len(onsets),eventSamplesCompared=int(total_epoch_samples),rejections=len(bad)+2,checks=len(tasks),
   scope='Public deidentified research file, not user adoption or diagnostic validation; no filtering/classification; raw source not bundled')
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
