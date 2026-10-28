#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = new URL('../', import.meta.url);
const engine = new URL('_build/js/release/build/cmd/bridge/bridge.js', root);
const api = await import(engine.href);
const manifest = JSON.parse(fs.readFileSync(new URL('examples/exact-time/INPUTS.json', root)));
const output = path.resolve(process.argv[2] ?? 'work/exact-time');
fs.mkdirSync(output, {recursive:false});
const sha = b => createHash('sha256').update(b).digest('hex');
const report = (bytes, options) => JSON.parse(api.report(bytes, JSON.stringify(options)));
const receipt = {status:'passed', engineSha256:sha(fs.readFileSync(engine)), cliChecks:0, cases:[]};
for (const c of manifest.cases) {
  const source = Buffer.from(c.sourceBase64,'base64');
  assert.equal(sha(source),c.sourceSha256);
  const queries = c.queries.map(options => ({options,result:report(source,options)}));
  const rejected = [];
  for (const options of c.rejects) {
    assert.throws(() => report(source,options),/\b(?:Invalid|Limit)\(/);
    rejected.push(options);
  }
  const copy = Buffer.from(api.transform(source,'{"command":"copy"}'));
  assert.deepEqual(copy,source,'copy is byte-identical');
  const selected = Buffer.from(api.transform(source,JSON.stringify({command:'select',signals:c.select})));
  const cropped = Buffer.from(api.transform(source,JSON.stringify({command:'crop',first_record:c.crop_first,records:c.records.length-c.crop_first})));
  const created = Buffer.from(api.transform(new Uint8Array(),JSON.stringify({command:'create',exact_time:true,
    format:c.format,continuity:c.continuity,duration:c.duration,signals:c.signals,records:c.records})));
  const files = {};
  for (const [key,bytes] of Object.entries({source,copy,selected,cropped,created})) {
    const file = `${c.name}-${key}.${c.format}`;
    fs.writeFileSync(path.join(output,file),bytes,{flag:'wx'});
    files[key] = {file,sha256:sha(bytes),bytes:bytes.length,annotations:report(bytes,{command:'annotations-exact'})};
  }
  // Numeric padding is a convenience input, but source event membership must
  // still use its complete lexical time. Skip nonrepresentable pad strings.
  const legacy = [];
  for (const q of c.queries.filter(q => q.command==='epoch-exact' && ['0','0.1'].includes(q.after))) {
    const options = {...q,command:'epoch',before:Number(q.before),after:Number(q.after)};
    legacy.push({options,result:report(source,options)});
  }
  receipt.cases.push({name:c.name,files,queries,rejected,legacy});
}
// Exercise the actual host command syntax, plus output protection.
const c = manifest.cases[0];
const sourcePath = path.join(output,receipt.cases[0].files.source.file);
const cli = (args) => spawnSync(process.execPath,[fileURLToPath(new URL('tools/edf.mjs',root)),...args],{encoding:'utf8',timeout:30000});
for (const options of [{command:'annotations-exact'},...c.queries.slice(0,2)]) {
  const optionsPath = path.join(output,`cli-${receipt.cliChecks}.json`);
  fs.writeFileSync(optionsPath,JSON.stringify(options),{flag:'wx'});
  const p = cli([options.command,sourcePath,optionsPath]);
  assert.equal(p.status,0,p.stderr);
  assert.deepEqual(JSON.parse(p.stdout),report(Buffer.from(c.sourceBase64,'base64'),options));
  receipt.cliChecks++;
}
const createOptions = path.join(output,'cli-create.json');
fs.writeFileSync(createOptions,JSON.stringify({...c,exact_time:true}),{flag:'wx'});
const createdPath = path.join(output,'cli-created.edf');
const p = cli(['create',createdPath,createOptions]);
assert.equal(p.status,0,p.stderr);
const before = fs.readFileSync(createdPath);
assert.deepEqual(report(before,{command:'annotations-exact'}),receipt.cases[0].files.created.annotations);
const again = cli(['create',createdPath,createOptions]);
assert.equal(again.status,2);
assert.deepEqual(fs.readFileSync(createdPath),before);
receipt.cliChecks += 2;
fs.writeFileSync(path.join(output,'ENGINE.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:'passed',cases:receipt.cases.length,cliChecks:receipt.cliChecks,output}));
