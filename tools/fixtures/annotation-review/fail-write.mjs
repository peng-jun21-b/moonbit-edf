// Deterministic IO-failure control for the real file receiver, not product code.
import fs from 'node:fs';
import path from 'node:path';
const original=fs.writeFileSync;
fs.writeFileSync=function(file,...args) {
  if(path.basename(file)==='right-annotations.json'&&path.resolve(path.dirname(file))===path.resolve(process.env.MOON_REVIEW_FAIL_OUTPUT))
    throw Object.assign(Error('injected review write failure'),{code:'EIO'});
  return original.call(this,file,...args);
};
