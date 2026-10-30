import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const walk=dir=>fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(dir,e.name)):[path.join(dir,e.name)]);
let count=0;
for(const file of walk(path.join(root,'app')).filter(p=>/\.m?js$/.test(p))){
  const syntax=spawnSync(process.execPath,['--check',file],{encoding:'utf8'});if(syntax.status)throw Error(syntax.stderr);
  const text=fs.readFileSync(file,'utf8');
  for(const match of text.matchAll(/(?:from\s*|import\s*\()\s*['"](\.[^'"]+)['"]/g)){
    const dependency=path.resolve(path.dirname(file),match[1]);if(!fs.existsSync(dependency))throw Error(`${path.relative(root,file)}: missing ${match[1]}`);
  }
  count++;
}
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
for(const id of ['serial','terminal','rttcdc','scope','flash','dbg','etm','gen'])if(!html.includes(`id="tab-${id}"`))throw Error('Missing required page: '+id);
if(!fs.existsSync(path.join(root,'app/etm/opencsd.wasm')))throw Error('Missing browser decoder');
console.log(`PASS ${count} browser modules: syntax, local imports, eight required pages, WASM asset`);
