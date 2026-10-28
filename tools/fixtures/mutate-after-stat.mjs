import fs from 'node:fs';
import path from 'node:path';
// A test-only preload. Mutate a real temporary file immediately after metadata
// observation; avoid timing sleeps and fabricated stat sizes.
const file=path.resolve(process.env.MOON_TEST_INPUT_PATH);
const mode=process.env.MOON_TEST_INPUT_MODE;
const open=fs.openSync,stat=fs.statSync,fstat=fs.fstatSync,read=fs.readSync,close=fs.closeSync;
const descriptors=new Set();
let changed=false;
function mutate() {
  if(changed) return;
  changed=true;
  if(mode==='grow') fs.appendFileSync(file,Buffer.alloc(1000001,0x20));
  if(mode==='shrink') fs.truncateSync(file,0);
}
fs.openSync=function(name,...args) {
  const fd=open.call(this,name,...args);
  if(typeof name==='string'&&path.resolve(name)===file) descriptors.add(fd);
  return fd;
};
fs.closeSync=function(fd) {
  try {return close.call(this,fd);} finally {descriptors.delete(fd);}
};
fs.statSync=function(name,...args) {
  const result=stat.call(this,name,...args);
  if(typeof name==='string'&&path.resolve(name)===file) mutate();
  return result;
};
fs.fstatSync=function(fd,...args) {
  const result=fstat.call(this,fd,...args);
  if(descriptors.has(fd)) mutate();
  return result;
};
fs.readSync=function(fd,buffer,offset,length,position) {
  if(descriptors.has(fd)) {
    if(mode==='read-error') throw new Error('injected input read failure');
    if(mode==='short-read') length=Math.min(length,7);
  }
  return read.call(this,fd,buffer,offset,length,position);
};
