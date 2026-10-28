"""Verify the actual published DSP dependency used by the build."""
import hashlib
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pin = json.loads((root / "SPECTRUM-DEPENDENCY.json").read_text(encoding="utf-8"))
dependency = root / ".mooncakes/chgttyyr/MoonSpectrum"
for item in pin["sourceFiles"]:
    actual = hashlib.sha256((dependency / item["path"]).read_bytes()).hexdigest()
    assert actual == item["releaseSha256"], "MoonSpectrum source identity differs: " + item["path"]
archive = Path(os.environ["MOON_HOME"]) / "registry/cache/chgttyyr/MoonSpectrum/0.2.2.zip"
assert hashlib.sha256(archive.read_bytes()).hexdigest() == pin["releaseSha256"]
print(json.dumps(dict(dependency="chgttyyr/MoonSpectrum", version=pin["version"],
                     commit=pin["commit"], verifiedFiles=len(pin["sourceFiles"]),
                     releaseSha256=pin["releaseSha256"])))
