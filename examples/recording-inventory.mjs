#!/usr/bin/env node
// Deliver existing query models from one read-only source snapshot.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {readFile,inventoryFromSnapshot} from '../tools/edf.mjs';

const sha256=data=>createHash('sha256').update(data).digest('hex');
try {
  if(process.argv.length<5||process.argv.length>6)
    throw Error('usage: node examples/recording-inventory.mjs INPUT NEW_DIRECTORY MINIMUM_SAMPLES [READ_OPTIONS.json]');
  const [input,output,minimumText,optionsPath]=process.argv.slice(2);
  if(!/^[0-9]+$/.test(minimumText))throw Error('minimum_samples must be a positive Int');
  const minimum=Number(minimumText);
  if(!Number.isInteger(minimum)||minimum<1||minimum>2147483647)
    throw Error('minimum_samples must be a positive Int');
  if(fs.existsSync(output))throw Error('output directory exists; choose a new path');
  const snapshot=readFile(input);
  const rawOptions=optionsPath?readFile(optionsPath):Buffer.from('{}');
  const {result,readPolicy}=inventoryFromSnapshot(snapshot,minimum,rawOptions.toString('utf8'));
  const payloads=[['inspect.json',result.inspection],['annotations.json',result.annotations]];
  const channels=result.channels.map(channel=>{
    const statistics=`channel-${channel.signal}-statistics.json`,flat=`channel-${channel.signal}-flat.json`;
    payloads.push([statistics,channel.statistics],[flat,channel.flat_runs]);
    return {signal:channel.signal,statistics,flat_runs:flat};
  });
  const files=payloads.map(([file,value])=>{
    const text=JSON.stringify(value,null,2)+'\n';
    return {file,text,bytes:Buffer.byteLength(text),sha256:sha256(text)};
  });
  const source={path:path.resolve(input),bytes:snapshot.length,sha256:sha256(snapshot)};
  const manifest={source,minimum_samples:minimum,read_policy:readPolicy,read_options_sha256:sha256(rawOptions),
    inspection:'inspect.json',annotations:'annotations.json',channels,
    files:files.map(({file,bytes,sha256})=>({file,bytes,sha256}))};
  // All reads and analyses succeeded before the first output mutation.
  fs.mkdirSync(output);
  for(const file of files)fs.writeFileSync(path.join(output,file.file),file.text,{flag:'wx'});
  fs.writeFileSync(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({output:path.resolve(output),sourceSha256:source.sha256,channels:channels.length,files:files.length+1}));
}catch(error){console.error(`MoonEDF recording inventory: ${error.message??error}`);process.exitCode=2;}
