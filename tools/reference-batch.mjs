import fs from 'node:fs';
import {performance} from 'node:perf_hooks';
import {report} from '../_build/js/release/build/cmd/bridge/bridge.js';
import {readFile,writeTransform} from './edf.mjs';
const tasks=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const results=[];
for (const t of tasks) {
  const start=performance.now();
  try {
    const result=t.kind==='transform'?writeTransform(t.input,t.output,t.options):JSON.parse(report(readFile(t.input),JSON.stringify(t.options)));
    results.push({ok:true,result,ms:performance.now()-start});
  } catch(e) {results.push({ok:false,error:String(e.message??e),ms:performance.now()-start});}
}
fs.writeFileSync(process.argv[3],JSON.stringify(results));
