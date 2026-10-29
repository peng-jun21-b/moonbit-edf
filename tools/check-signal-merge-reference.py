"""Independent installed EDFlib/PyEDFlib readback of the two NEW plain outputs.

No fixture generation or old reference matrix is run. Only digital sample
readback is claimed; exact subsecond/TAL clocks remain independently checked
by the fixed-width/Fraction receiver.
"""
import argparse,hashlib,json
from pathlib import Path
import pyedflib

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--receipt',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();assert not args.output.exists();receipt=json.loads(args.receipt.read_bytes());assert receipt['status']=='passed'
verified=[]
for product in receipt['fileProducts']:
    if product['name'] not in ('plain-edf','plain-bdf'):continue
    p=Path(product['output']);assert hashlib.sha256(p.read_bytes()).hexdigest()==product['sha256']
    with pyedflib.EdfReader(str(p)) as reader:
        assert reader.signals_in_file==product['native']['signals'];count=0
        for signal in range(reader.signals_in_file):
            expected=[row['digital'] for row in product['native']['samples'] if row['signal']==signal]
            actual=[int(v) for v in reader.readSignal(signal,digital=True)]
            assert actual==expected,(p,signal);count+=len(actual)
    verified.append(dict(name=product['name'],output=str(p),digitalSamples=count,sha256=product['sha256']))
assert len(verified)==2
args.output.write_text(json.dumps(dict(status='passed',reference='PyEDFlib/EDFlib',pyedflib=pyedflib.__version__,products=verified,exactClockOrDiscontinuousCertificationClaimed=False),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='passed',products=len(verified),digitalSamples=sum(p['digitalSamples'] for p in verified),pyedflib=pyedflib.__version__)))
