import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=fileURLToPath(new URL('../',import.meta.url));
const cli=fileURLToPath(new URL('./edf.mjs',import.meta.url));
const hook=new URL('./fixtures/mutate-after-stat.mjs',import.meta.url).href;
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'moon-edf-input-'));
const original=fs.readFileSync(path.join(root,'examples/create.json'));
const limit=1000000;
const checks=[];
function command(args,expected,mode=null,input=null) {
  const childArgs=mode?['--import',hook,cli,...args]:[cli,...args];
  const r=spawnSync(process.execPath,childArgs,{cwd:root,encoding:'utf8',timeout:30000,
    env:{...process.env,...(mode?{MOON_TEST_INPUT_PATH:input,MOON_TEST_INPUT_MODE:mode}:{})}});
  if(r.error) throw r.error;
  assert.equal(r.status,expected,r.stderr);
  return r;
}
try {
  for(const [name,size,mode,error] of [
    ['stable',original.length,null,null],
    ['exact-limit',limit,null,null],
    ['above-old-limit',limit+1,null,null],
    ['grew-after-stat',original.length,'grow',/changed size/],
    ['shrank-after-stat',original.length,'shrink',/changed size/],
    ['short-reads',original.length,'short-read',null],
    ['read-error',original.length,'read-error',/injected input read failure/],
  ]) {
    const options=path.join(tmp,name+'.json'),output=path.join(tmp,name+'.edf');
    fs.writeFileSync(options,Buffer.concat([original,Buffer.alloc(size-original.length,0x20)]));
    const r=command(['create',output,options],error?2:0,mode,options);
    if(error) assert.match(r.stderr,error);
    assert.equal(fs.existsSync(output),!error);
    if(!error) assert.ok(fs.statSync(output).size>0);
    checks.push(name);
  }
  const data=path.join(tmp,'stable.edf');
  const result=command(['inspect',data],2,'grow',data);
  assert.match(result.stderr,/changed size/);
  checks.push('growing-data-file');
  const directory=path.join(tmp,'directory');fs.mkdirSync(directory);
  const output=path.join(tmp,'directory-output.edf');
  command(['create',output,directory],2);
  assert.equal(fs.existsSync(output),false);
  checks.push('options-directory');
  console.log(JSON.stringify({status:'passed',checks:checks.length,cases:checks,platform:process.platform,node:process.version}));
} finally {
  const target=path.resolve(tmp),parent=path.resolve(os.tmpdir());
  if(path.dirname(target)!==parent||!path.basename(target).startsWith('moon-edf-input-')) throw Error('unsafe cleanup target');
  fs.rmSync(target,{recursive:true});
}
