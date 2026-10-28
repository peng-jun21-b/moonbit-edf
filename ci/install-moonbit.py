"""Install the pinned official distribution into a new, isolated directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", type=Path, required=True)
    ap.add_argument("--download-cache", type=Path, required=True)
    args = ap.parse_args()
    lock = json.loads((ROOT / "ci/toolchain.lock.json").read_text(encoding="utf-8"))
    assert (ROOT / ".moonbit-version").read_text().strip() == lock["version"]
    assert platform.machine().lower() in ("amd64", "x86_64")
    target = {"Windows": "windows", "Linux": "linux"}[platform.system()]
    assert not args.home.exists(), "choose a new isolated MOON_HOME"
    args.download_cache.mkdir(parents=True, exist_ok=True)
    archives = []
    for name in (target, "core"):
        item = lock[name]
        archive = args.download_cache / item["cacheFile"]
        if not archive.exists():
            with urllib.request.urlopen(item["url"], timeout=180) as response:
                with archive.open("xb") as output:
                    while block := response.read(1024 * 1024):
                        output.write(block)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == item["sha256"], name + " distribution checksum mismatch"
        print(json.dumps(dict(distribution=name, sha256=item["sha256"], bytes=archive.stat().st_size)), flush=True)
        archives.append(archive)
    args.home.mkdir(parents=True)
    if target == "windows":
        with zipfile.ZipFile(archives[0]) as z:
            assert all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in z.namelist())
            z.extractall(args.home)
    else:
        with tarfile.open(archives[0]) as t:
            t.extractall(args.home, filter="data")
        # The official installer explicitly enables these executables and
        # installs the moonx alias after extracting the distribution.
        for binary in (args.home / "bin").iterdir():
            if binary.is_file():
                binary.chmod(binary.stat().st_mode | 0o111)
        tcc = args.home / "bin/internal/tcc"
        tcc.chmod(tcc.stat().st_mode | 0o111)
        if not (args.home / "bin/moonx").exists():
            (args.home / "bin/moonx").symlink_to("moon")
    with tarfile.open(archives[1]) as t:
        t.extractall(args.home / "lib", filter="data")
    env = dict(os.environ, MOON_HOME=str(args.home.resolve()))
    env["PATH"] = str(args.home.resolve() / "bin") + os.pathsep + env["PATH"]
    moon = args.home.resolve() / "bin" / ("moon.exe" if target == "windows" else "moon")
    # Same core bundling commands as the official unix installer. Project
    # warnings are checked separately with --deny-warn.
    for options in (["--all"], ["--target", "wasm-gc"]):
        subprocess.run([str(moon), "-C", str(args.home.resolve() / "lib/core"), "bundle", "--warn-list", "-a", *options], env=env, check=True)
    compiler = args.home.resolve() / "bin" / ("moonc.exe" if target == "windows" else "moonc")
    version = subprocess.check_output([str(compiler), "-v"], env=env, text=True).strip()
    assert lock["version"] in version, version
    subprocess.run([str(moon), "version", "--all"], env=env, check=True)


if __name__ == "__main__":
    main()
