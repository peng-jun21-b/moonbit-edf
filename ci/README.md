# Reproducible CI

The `EDF contracts` workflow runs on an ordinary Ubuntu 24.04 GitHub runner with
read-only repository permission. Its checkout, Node and Python actions are pinned
to commits in the official `actions` repositories. Node is 24.11.0; the actual
Python 3.12 patch version is recorded in each run. Numerical references are fixed
to NumPy 2.3.4 and SciPy 1.16.2.

All consumers from the archived workflow remain enabled. Its NumPy 2.5.3 and
PyEDFlib 0.1.42 references are installed in a separate environment, so the PSD
reference does not replace or downgrade them. The original public-recording
checks now also run on pushes, alongside the new PSD consumer and event CSV
readback. Existing fixed source samples and expected outcomes remain intact.

`install-moonbit.py` downloads the versioned official MoonBit distribution and
matching core archive into a new isolated `MOON_HOME`, verifies the hashes in
`toolchain.lock.json`, and uses the core bundling commands from the official
installer. It does not edit a shell profile or an existing SDK. The Windows and
Linux compiler archive hashes were checked against the official `.sha256`
endpoints. The core archive has a recorded download hash; its adjacent checksum
endpoint returned 404. The compiler version must match `.moonbit-version`.

References: [official installation and verification](https://www.moonbitlang.com/download/),
[official installer](https://cli.moonbitlang.com/install/unix.sh),
[checkout action](https://github.com/actions/checkout/blob/11d5960a326750d5838078e36cf38b85af677262/action.yml),
[Node action](https://github.com/actions/setup-node/blob/49933ea5288caeca8642d1e84afbd3f7d6820020/action.yml),
[Python action](https://github.com/actions/setup-python/blob/a26af69be951a213d495a4c3e4e4022e16d87065/action.yml).

CI runs formatting, all-target type checks, the JS and Wasm-GC test suites,
generated interface verification, a release JS file bridge, fixed independent
EDF/DFT/SciPy comparisons with a real JSON/CSV consumer, exact-time/CSV CLI
regressions and independent append consumers. `check-dependency.py` verifies the
actual MoonSpectrum 0.2.2 archive and the pinned source files before the tests.
Failures remain failures. No paid service or self-hosted runner is required.

The public EDF is fetched with the existing fixed size/SHA256 tool; it is not
tracked or uploaded. Consumer attribution remains with the output. Temporary
inputs, reports and build products stay in ignored directories.
