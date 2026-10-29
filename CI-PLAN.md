# Required CI and public-package receiving plan

The owned module is `peng-jun21-b/edf`; its existing public examples and Node
bridge are compiled from that namespace. Account alignment preserves all
required product steps below, without changing the recording algorithms,
third-party dependency identities or source fixture expectations.

The required workflow is `.github/workflows/ci.yml`, job **EDF format, time and PSD contracts**. All existing named steps remain required; the recording inventory adds **Single-snapshot recording inventory public-package and file receivers**. A result is tied to the exact final push head, not an earlier commit or a separately rerun auxiliary workflow.

The inventory gate runs the actual separate public package on JS and Wasm-GC, then runs the real arbitrary-file entry and reads every saved sidecar:

```sh
moon run examples/recording_inventory --target js --deny-warn > work/inventory-public-js.json
moon run examples/recording_inventory --target wasm-gc --deny-warn > work/inventory-public-wasm-gc.json
python tools/check-recording-inventory.py --output work/inventory-verification.json --work-dir work/inventory-cases --public-output work/inventory-public-js.json --public-output work/inventory-public-wasm-gc.json
```

Complete independent fixed-width/TAL input bytes and expectations are in `tools/fixtures/recording-inventory`. The standard-library reference uses Fraction calibration/population moments and exact native adjacency for flat runs, with a 100-digit final RMS square root. Full inspection and annotation objects, count/range fields, omitted empty fields and rational run endpoints must match. Nonzero physical numeric fields use the frozen max(5e-12 relative, 8 ULP) tolerance; expected zero is exact.

The file receiver verifies source SHA and original bytes, every existing-model sidecar and its manifest hash, explicit sample threshold/read policy, exact output membership, annotation-only/empty channels, all-query-before-directory errors and occupied-directory protection. Authored integration cases are not new MoonBit unit declarations or evidence of third-party adoption.

Relevant local checks are formatting, all supported-target warning-denied check, generated-interface review, a real release bridge, both public runs, the full new receiver, final format and the unchanged dependency pin check. Existing scientific/reference generators need no extra local rerun when their implementations are unchanged; the required real CI still runs all old necessary gates. SDK/dependency pins and reference environments remain unchanged.

Local source/worktree bytes, actual locally executed/compiled artifacts, raw complete outputs and final source archive have separate identities. CI success is remote run/job/step metadata unless cloud artifact bytes have actually been downloaded; it does not establish local/cloud binary equality.
