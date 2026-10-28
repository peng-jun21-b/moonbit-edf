"""Fetch one fixed public EDF+ file; no whole-dataset download or overwrite."""
from pathlib import Path
import argparse, urllib.request, hashlib
URL='https://physionet-open.s3.amazonaws.com/eegmmidb/1.0.0/S001/S001R03.edf'
SIZE=2596896
SHA='3427c8d01bff1380bc9ab9f27a35ece2af5dfadf3e291bbc05eb66e4dadbfe2e'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
if a.output.exists():
 data=a.output.read_bytes()
else:
 with urllib.request.urlopen(URL,timeout=30) as response:data=response.read(SIZE+1)
assert len(data)==SIZE and hashlib.sha256(data).hexdigest()==SHA,'Incomplete or changed source; original file preserved'
if not a.output.exists():
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('xb') as output:output.write(data)
print(str(a.output.resolve()))
