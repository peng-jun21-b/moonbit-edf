#!/usr/bin/env node
// Host IO/serialization only; selection, calibration and PSD run in MoonBit.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {readFile,psdFromSnapshot} from '../tools/edf.mjs';

function csv(value) {
  const s=String(value);
  return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;
}
try {
  if (process.argv.length!==5) throw new Error('usage: node examples/edf-psd.mjs INPUT.edf NEW_OUTPUT_DIRECTORY OPTIONS.json');
  const [input,output,optionsPath]=process.argv.slice(2);
  if (fs.existsSync(output)) throw new Error('output directory exists; choose a new path');
  const snapshot=readFile(input);
  const rawOptions=readFile(optionsPath).toString('utf8');
  const result=psdFromSnapshot(snapshot,rawOptions);
  const source={path:path.resolve(input),bytes:snapshot.length,sha256:createHash('sha256').update(snapshot).digest('hex')};
  const document={schema:'MoonEDF-PSD/1',source,result};
  const columns=['source_sha256','signal','label','physical_unit','psd_unit','start','end','sample_rate_numerator','sample_rate_denominator','segment_length','overlap_samples','window','detrend','nfft','frequency_hz','density'];
  const rows=[columns.join(',')];
  for (let i=0;i<result.density.length;i++) {
    rows.push([source.sha256,result.signal,result.label,result.unit,result.psd_unit,result.start,result.end,result.sample_rate.numerator,result.sample_rate.denominator,result.segment_length,result.overlap_samples,result.window,result.detrend,result.nfft,result.frequencies_hz[i],result.density[i]].map(csv).join(','));
  }
  fs.mkdirSync(output);
  fs.writeFileSync(path.join(output,'psd.json'),JSON.stringify(document,null,2)+'\n',{flag:'wx'});
  fs.writeFileSync(path.join(output,'psd.csv'),rows.join('\n')+'\n',{flag:'wx'});
  console.log(JSON.stringify({output:path.resolve(output),sourceSha256:source.sha256,bins:result.density.length,segments:result.segments}));
} catch(e) {console.error(`MoonEDF PSD: ${e.message??e}`);process.exitCode=2;}
