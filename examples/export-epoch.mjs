#!/usr/bin/env node
// File handoff only: MoonBit selects the event/window and renders native CSV.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {readFile,epochCsvFromSnapshot} from '../tools/edf.mjs';

try {
  if(process.argv.length!==5)throw Error('usage: node examples/export-epoch.mjs INPUT.edf NEW_OUTPUT_DIRECTORY OPTIONS.json');
  const [input,output,optionsPath]=process.argv.slice(2);
  if(fs.existsSync(output))throw Error('output directory exists; choose a new path');
  const snapshot=readFile(input),options=readFile(optionsPath).toString('utf8');
  const {result,csv,request,csvPhysical}=epochCsvFromSnapshot(snapshot,options);
  const source={path:path.resolve(input),bytes:snapshot.length,sha256:createHash('sha256').update(snapshot).digest('hex')};
  const document={source,request,result,csv:{file:'samples.csv',sha256:createHash('sha256').update(csv).digest('hex'),physical:csvPhysical}};
  fs.mkdirSync(output);
  fs.writeFileSync(path.join(output,'epoch.json'),JSON.stringify(document,null,2)+'\n',{flag:'wx'});
  fs.writeFileSync(path.join(output,'samples.csv'),csv,{flag:'wx'});
  console.log(JSON.stringify({output:path.resolve(output),sourceSha256:source.sha256,annotation:result.annotation_index,samples:result.samples,complete:result.complete}));
}catch(error){console.error(`MoonEDF epoch export: ${error.message??error}`);process.exitCode=2;}
