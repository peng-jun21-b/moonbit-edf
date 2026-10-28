"""Fetch fixed upstream test files for local verification; do not redistribute."""
from pathlib import Path
import argparse
import hashlib
import urllib.request
# Constants are kept here to avoid importing the verifier's NumPy dependencies
# merely to download files; the verifier independently pins the same hashes.
COMMIT = '47d5be239f12eb310e7799b5119baf24bed89d05'
FILES = {
    'test_bdf_stim_channel.bdf': 'd555c9550069c0402835092ac3b2136ac238c8b8996069e11594350826d765a3',
    'test.bdf': 'd97eb2809b8314bf097493b8e2b04140b86722e0de749a563fa6bab2bc63554a',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        target = args.directory/name
        if target.exists():
            assert hashlib.sha256(target.read_bytes()).hexdigest() == expected, f'Existing file differs: {name}'
        else:
            url = f'https://raw.githubusercontent.com/mne-tools/mne-python/{COMMIT}/mne/io/edf/tests/data/{name}'
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(1000001)
            assert len(data) <= 1000000 and hashlib.sha256(data).hexdigest() == expected, name
            with target.open('xb') as output:
                output.write(data)
        print(f'Verified {name}: {expected}')


if __name__ == '__main__':
    main()
