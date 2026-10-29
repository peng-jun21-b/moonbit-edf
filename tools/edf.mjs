#!/usr/bin/env node
// The host owns file paths and process IO; binary and signal work is MoonBit.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
// Explicit alternate build directory, useful when the source volume is small.
const bridgeUrl=process.env.MOON_EDF_BRIDGE
  ? pathToFileURL(path.resolve(process.env.MOON_EDF_BRIDGE))
  : new URL('../_build/js/release/build/cmd/bridge/bridge.js',import.meta.url);
const { report, transform, append_recordings, review_annotations }=await import(bridgeUrl.href);
// Snapshot consumers share the same selected bridge as the CLI and file APIs.
export { report, transform };

// One exact multiset review of two complete byte snapshots. Per-side read
// policies use the same original numeric lexeme handling as the other readers.
export function annotationReviewFromSnapshots(left,right,options='{}') {
  const parsed=typeof options==='string'?JSON.parse(options):options;
  if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw Error('options must be an object');
  for(const key of Object.keys(parsed))if(key!=='left'&&key!=='right')throw Error(`unsupported comparison option: ${key}`);
  for(const side of ['left','right'])if(Object.hasOwn(parsed,side)) {
    const fields=parsed[side];
    if(!fields||Array.isArray(fields)||typeof fields!=='object')throw Error(`${side} read options must be an object`);
    for(const key of Object.keys(fields))if(key!=='time_tolerance')throw Error(`unsupported ${side} read option: ${key}`);
  }
  // Decode the complete original JSON text again, preserving nested number
  // tokens before any Number rounding can affect the effective tolerance.
  const raw=typeof options==='string'?options:JSON.stringify(options);
  const exact=JSON.parse(raw,(key,value,context)=>key==='time_tolerance'&&typeof value==='number'?context.source:value);
  const result=JSON.parse(review_annotations(left,right,JSON.stringify(exact)));
  const implementation={module:'peng-jun21-b/edf',version:'0.13.0',
    bridge_sha256:createHash('sha256').update(readFile(fileURLToPath(bridgeUrl))).digest('hex')};
  return {result,implementation};
}

function readBounded(filename,limit) {
  const fd=fs.openSync(filename,'r');
  try {
    const stat=fs.fstatSync(fd);
    if (!stat.isFile() || !Number.isSafeInteger(stat.size) || stat.size<0 || stat.size>limit)
      throw new Error(`input must be a regular file <= ${limit} bytes`);
    // Read from the checked descriptor, bounded by the observed size plus one
    // sentinel byte. A separate path stat cannot cap readFileSync allocation.
    const buffer=Buffer.alloc(stat.size+1);
    let length=0;
    while (length<buffer.length) {
      const count=fs.readSync(fd,buffer,length,buffer.length-length,null);
      if (count===0) break;
      length+=count;
    }
    if (length!==stat.size) throw new Error('input changed size during read; retry a stable file');
    return buffer.subarray(0,length);
  } finally {fs.closeSync(fd);}
}

export function readFile(filename) {
  return readBounded(filename,2147483646);
}

function exactOptions(options,command=null) {
  const text=typeof options==='string'?options:JSON.stringify(options);
  const candidates=new Set(['start','end','before','after','onset','duration','offset','time_tolerance']);
  const sources=new WeakMap();
  const exact=JSON.parse(text,function(key,value,context) {
    if (typeof value==='number' && candidates.has(key)) {
      let fields=sources.get(this);
      if (!fields) {fields=new Map();sources.set(this,fields);}
      fields.set(key,context.source);
    }
    return value;
  });
  if (!exact || Array.isArray(exact) || typeof exact!=='object') throw new Error('options must be an object');
  const cmd=command??exact.command;
  function times(object,keys) {
    if (!object || Array.isArray(object) || typeof object!=='object') return;
    for (const key of keys) {
      if (typeof object[key]==='number') object[key]=sources.get(object).get(key);
    }
  }
  // Preserve number lexemes only where the command accepts a time. In
  // particular, channel.start is an Int and calibrate.offset is a Double.
  times(exact,['time_tolerance']);
  if (['window','window-exact','window-csv','window-stats','crop-time','annotations-window','psd'].includes(cmd)) times(exact,['start','end']);
  if (['epoch','epoch-exact'].includes(cmd)) times(exact,['before','after']);
  if (cmd==='annotation-add') times(exact,['onset','duration']);
  if (cmd==='append') times(exact,['offset']);
  if (cmd==='create') {
    times(exact,['duration']);
    if (Array.isArray(exact.records)) for (const record of exact.records) {
      times(record,['onset']);
      if (Array.isArray(record?.events)) for (const event of record.events) times(event,['onset','duration']);
    }
  }
  // The new digital editor validates Int values from original number lexemes.
  return {options:exact,text:cmd==='samples-set'?text:JSON.stringify(exact)};
}

export function writeTransform(input,output,options) {
  if (fs.existsSync(output)) throw new Error('output exists; choose a new path');
  const exact=exactOptions(options);
  const data=exact.options.command==='create' ? new Uint8Array() : readFile(input);
  const result=transform(data,exact.text);
  fs.writeFileSync(output,result,{flag:'wx'});
  return {output,bytes:result.length};
}

export function writeAppend(input,next,output,options='{}') {
  if (fs.existsSync(output)) throw new Error('output exists; choose a new path');
  const exact=exactOptions(options,'append');
  const result=append_recordings(readFile(input),readFile(next),exact.text);
  fs.writeFileSync(output,result,{flag:'wx'});
  return {output,bytes:result.length};
}

export function psdFromSnapshot(data,options) {
  const exact=exactOptions(options,'psd');
  exact.options.command='psd';
  return JSON.parse(report(data,JSON.stringify(exact.options)));
}

// Receive existing inspection, annotations and all native channel summaries together.
export function inventoryFromSnapshot(data,minimum,options='{}') {
  if(!Number.isInteger(minimum)||minimum<1||minimum>2147483647)
    throw Error('minimum_samples must be a positive Int');
  const exact=exactOptions(options,'inspect'),readPolicy={};
  if(Object.hasOwn(exact.options,'time_tolerance'))readPolicy.time_tolerance=exact.options.time_tolerance;
  const query=(command,extra={})=>JSON.parse(report(data,JSON.stringify({...readPolicy,command,...extra})));
  const inspection=query('inspect'),annotations=query('annotations'),channels=[];
  for(let signal=0;signal<inspection.signals.length;signal++) {
    const label=inspection.signals[signal].label;
    if(label==='EDF Annotations'||label==='BDF Annotations')continue;
    channels.push({signal,statistics:query('stats',{signal}),flat_runs:query('flat',{signal,minimum_samples:minimum})});
  }
  return {result:{inspection,annotations,channels},readPolicy};
}

// Compose the existing exact epoch and native-window CSV APIs on one snapshot.
export function epochCsvFromSnapshot(data,options) {
  const exact=exactOptions(options,'epoch');
  const request={...exact.options,command:'epoch'};
  const result=JSON.parse(report(data,JSON.stringify(request)));
  const csvOptions={command:'window-csv',signals:result.channels.map(c=>c.signal),start:result.start,end:result.end};
  for(const key of ['max_samples','time_tolerance','physical'])
    if(Object.hasOwn(exact.options,key))csvOptions[key]=exact.options[key];
  const csv=JSON.parse(report(data,JSON.stringify(csvOptions))).text;
  return {result,csv,request,csvPhysical:csvOptions.physical??true};
}

const writes=new Set(['copy','samples-set','identification-set','select','crop','plus','create','crop-time','annotations-set','annotation-add','annotation-remove','annotations-remove','annotation-update','annotation-signal','rename','calibrate']);
const reads=new Set(['inspect','validate','stats','annotations','annotations-exact','annotations-window','gaps','flat','csv','channel','window','window-exact','window-csv','window-stats','epoch','epoch-exact','psd']);
function main(args) {
  if (!args.length || args[0]==='--help') {
    console.log('MoonEDF\n  inspect|validate|stats|annotations|annotations-exact|annotations-window|gaps|flat|csv|channel|window|window-exact|window-csv|window-stats|epoch|epoch-exact|psd INPUT [OPTIONS.json]\n  copy|samples-set|identification-set|select|crop|crop-time|plus|annotations-set|annotation-add|annotation-remove|annotations-remove|annotation-update|annotation-signal|rename|calibrate INPUT OUTPUT [OPTIONS.json]\n  append INPUT NEXT OUTPUT [OPTIONS.json]\n  create OUTPUT OPTIONS.json\nOn Node 24, supported numeric JSON time fields retain their source lexemes; decimal/rational time strings remain supported. Channel indices and physical calibration stay numeric. Annotation onset sign rules still apply. Sample CSV includes rational numerators and denominators. PSD requires explicit segment_length, overlap_samples and window (see examples/psd.json). Existing files are never overwritten.'); return;
  }
  const [command,...rest]=args;
  if (command==='append') {
    if (rest.length<3 || rest.length>4) throw new Error('wrong argument count; use --help');
    const text=rest[3]?readBounded(rest[3],2147483646).toString('utf8').trim():'{}';
    const options=JSON.parse(text);
    if (!options || Array.isArray(options) || typeof options!=='object') throw new Error('options must be an object');
    console.log(JSON.stringify(writeAppend(rest[0],rest[1],rest[2],text))); return;
  }
  if (!writes.has(command) && !reads.has(command)) throw new Error('unknown command; use --help');
  const create=command==='create', write=writes.has(command);
  if (rest.length<(write?2:1) || rest.length>(create?2:write?3:2)) throw new Error('wrong argument count; use --help');
  const optionsPath=create?rest[1]:rest[write?2:1];
  const rawOptions=optionsPath?readBounded(optionsPath,2147483646).toString('utf8').trim():'{}';
  const options=JSON.parse(rawOptions);
  if (!options || Array.isArray(options) || typeof options!=='object') throw new Error('options must be an object');
  const text=rawOptions.slice(0,-1)+(Object.keys(options).length?',':'')+'"command":'+JSON.stringify(command)+'}';
  if (write) console.log(JSON.stringify(writeTransform(create?null:rest[0],create?rest[0]:rest[1],text)));
  else {
    const result=report(readFile(rest[0]),exactOptions(text).text);
    const value=JSON.parse(result);
    process.stdout.write(typeof value?.text==='string'?value.text:result+'\n');
  }
}
if (process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {main(process.argv.slice(2));} catch(e) {console.error(`MoonEDF: ${e.message??e}`);process.exitCode=2;}
}
