// Query one byte snapshot, delete selected original indices, then re-query.
import fs from 'node:fs';
import { readFile, report, transform } from '../tools/edf.mjs';

try {
  const [input,output,start,end,...tail]=process.argv.slice(2);
  let text, timeTolerance;
  if (tail.length===1) text=tail[0];
  else if (tail.length===2 && tail[0]==='--time-tolerance') timeTolerance=tail[1];
  else if (tail.length===3 && tail[1]==='--time-tolerance') [text,,timeTolerance]=tail;
  else if (tail.length) throw new Error('usage: node examples/remove-window.mjs INPUT NEW_OUTPUT START END [EXACT_TEXT] [--time-tolerance SECONDS]');
  if (!input || !output || start===undefined || end===undefined)
    throw new Error('usage: node examples/remove-window.mjs INPUT NEW_OUTPUT START END [EXACT_TEXT] [--time-tolerance SECONDS]');
  const policy=timeTolerance===undefined?{}:{time_tolerance:timeTolerance};
  const data=readFile(input);
  const query=JSON.stringify({command:'annotations-window',start,end,...policy});
  const matches=JSON.parse(report(data,query));
  const selected=text===undefined?matches:matches.filter(m=>m.annotation.text===text);
  const result=transform(data,JSON.stringify({command:'annotations-remove',indices:selected.map(m=>m.annotation_index),...policy}));
  const remaining=JSON.parse(report(result,query));
  fs.writeFileSync(output,result,{flag:'wx'});
  console.log(JSON.stringify({output,matched:matches.length,removed:selected.length,remaining_in_window:remaining.length}));
} catch(error) {
  console.error(`MoonEDF example: ${error.message??error}`);
  process.exitCode=2;
}
