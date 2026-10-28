// Build the JS bridge first, then pass a new output directory.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {writeTransform} from '../tools/edf.mjs';

if (process.argv.length!==3) throw new Error('usage: node examples/cli-time-input.mjs NEW_DIRECTORY');
const directory=path.resolve(process.argv[2]);
fs.mkdirSync(directory);
const source=path.join(directory,'synthetic.edf');
writeTransform(null,source,`{"command":"create","duration":1,
  "signals":[{"label":"Synthetic","samples_per_record":4}],
  "records":[{"onset":0,"samples":[[10,20,30,40]],"events":[
    {"onset":0.500000000000000000001,"duration":null,"text":"marker"}]}]}`);
const query=path.join(directory,'window.json');
fs.writeFileSync(query,'{"signal":0,"start":0.250000000000000000001,"end":0.750000000000000000001}');
const cli=fileURLToPath(new URL('../tools/edf.mjs',import.meta.url));
const run=args=>JSON.parse(execFileSync(process.execPath,[cli,...args],{encoding:'utf8'}));
const window=run(['window',source,query]);
const annotations=run(['annotations',source]);
console.log(JSON.stringify({source,annotationOnset:annotations[0].onset,start:window.start,end:window.end,
  samples:window.samples.map(s=>({sample:s.sample,digital:s.digital,numerator:s.time_numerator,denominator:s.time_denominator}))},null,2));
