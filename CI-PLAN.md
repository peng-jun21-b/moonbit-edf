# Required CI and public-package receiving plan

The owned module is `peng-jun21-b/edf`; its existing public examples and Node
bridge are compiled from that namespace. Account alignment preserves all
required product steps below, without changing the recording algorithms,
third-party dependency identities or source fixture expectations.

The required workflow is `.github/workflows/ci.yml`, job **EDF format, time and PSD contracts**. All existing named steps remain required; the recording inventory adds **Single-snapshot recording inventory public-package and file receivers**. A result is tied to the exact final push head, not an earlier commit or a separately rerun auxiliary workflow.

The exact annotation revision gate **Exact annotation revision public-package and full file receivers** runs both complete public consumers, then receives all actual two-source file bundles against pre-implementation hand tables:

```sh
moon run examples/annotation_review --target js --deny-warn > work/annotation-review-public-js.json
moon run examples/annotation_review --target wasm-gc --deny-warn > work/annotation-review-public-wasm-gc.json
python tools/check-annotation-review.py --output work/annotation-review-verification.json --work-dir work/annotation-review-cases --public-output work/annotation-review-public-js.json --public-output work/annotation-review-public-wasm-gc.json
```

The 15 independent pairs cover EDF/BDF, duplicates across storage locations, exact numeric spelling, absent/zero duration, distinct Unicode normalization, gaps and outside events, mismatched header clocks, empty and annotation-only inputs, unknown count and explicit tolerant admission. Every raw annotation, rational key, witness index, count, context field, source identity and saved payload is received. Nine invalid paths, occupied/missing input/output controls and an explicitly injected write failure must not yield a successful completion manifest. The fixed input bytes and complete manual tables are in `tools/fixtures/annotation-review`; reference construction never calls the product writer/comparator.

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
