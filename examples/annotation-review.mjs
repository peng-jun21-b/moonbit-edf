#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {readFile,annotationReviewFromSnapshots} from '../tools/edf.mjs';

const sha256=data=>createHash('sha256').update(data).digest('hex');

export function writeAnnotationReview(leftPath,rightPath,output,optionsPath=null) {
  if(fs.existsSync(output))throw Error('output directory exists; choose a new path');
  const left=readFile(leftPath),right=readFile(rightPath);
  const rawOptions=optionsPath?readFile(optionsPath):Buffer.from('{}');
  const {result:review,implementation}=annotationReviewFromSnapshots(left,right,rawOptions.toString('utf8'));
  const source=(input,data,side)=>({path:path.resolve(input),bytes:data.length,sha256:sha256(data),annotations:review[side].annotations.length,time_tolerance:review[side].context.time_tolerance});
  const sources={left:source(leftPath,left,'left'),right:source(rightPath,right,'right')};
  const payloads=[['left-inspect.json',review.left.context],['right-inspect.json',review.right.context],
    ['left-annotations.json',review.left.annotations],['right-annotations.json',review.right.annotations],['comparison.json',review]];
  const files=payloads.map(([file,value])=>{
    const text=JSON.stringify(value,null,2)+'\n';
    return {file,text,bytes:Buffer.byteLength(text),sha256:sha256(text)};
  });
  const manifest={sources,frame:review.frame,status:review.status,totals:review.totals,read_options_sha256:sha256(rawOptions),
    implementation,
    files:files.map(({file,bytes,sha256})=>({file,bytes,sha256}))};
  // Both full decodes and all grouping succeed before output creation.
  // A failed write leaves no completed manifest and is never reported success.
  fs.mkdirSync(output);
  for(const file of files)fs.writeFileSync(path.join(output,file.file),file.text,{flag:'wx'});
  fs.writeFileSync(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
  return {output:path.resolve(output),sources,status:review.status,totals:review.totals,files:files.length+1};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {
    if(process.argv.length<5||process.argv.length>6)throw Error('usage: node examples/annotation-review.mjs LEFT RIGHT NEW_DIRECTORY [READ_OPTIONS.json]');
    console.log(JSON.stringify(writeAnnotationReview(...process.argv.slice(2))));
  }catch(error){console.error(`MoonEDF annotation review: ${error.message??error}`);process.exitCode=2;}
}
