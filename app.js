const $=id=>document.getElementById(id), mount='/ikemen';
const encoder=new TextEncoder(), decoder=new TextDecoder();
const allowed=new Set(['chars','data','font','stages','sound','music']);
let manifest=null, selected=null, running=false, timer=null;
const wholeParts=new Map();
window.__ikemenBootLog=[];
function log(text){window.__ikemenBootLog.push(String(text));if(window.__ikemenBootLog.length>500)window.__ikemenBootLog.splice(0,100);}
function status(text,fraction){$('status').textContent=text;if(Number.isFinite(fraction))$('progress').value=fraction;else $('progress').removeAttribute('value');}
function fail(error){console.error(error);log(error?.stack||error);$('loading').hidden=false;$('load-title').textContent='A file did not load.';status('The game could not finish starting.');$('error').hidden=false;$('error').textContent=(error?.message||String(error))+'\n\n'+window.__ikemenBootLog.slice(-12).join('\n');$('retry').hidden=false;if(timer)clearInterval(timer);}
const fsCall=(name,...args)=>new Promise((resolve,reject)=>fs[name](...args,(err,value)=>err?reject(err):resolve(value)));
async function readText(path){const fd=await fsCall('open',path,0,0);try{const st=await fsCall('fstat',fd), bytes=new Uint8Array(st.size);let off=0;while(off<bytes.length){const n=await fsCall('read',fd,bytes,off,bytes.length-off,off);if(!n)break;off+=n;}return decoder.decode(bytes.subarray(0,off));}finally{await fsCall('close',fd);}}
async function writeText(path,text){const bytes=encoder.encode(text),fd=await fsCall('open',path,1|64|512,0o644);try{await fsCall('write',fd,bytes,0,bytes.length,0);}finally{await fsCall('close',fd);}}
async function mkdir(path){try{await fsCall('mkdir',path,0o755);}catch(e){if(e.code!=='EEXIST')throw e;}}

// Seekable ZIP across hosted shards. Large files never require one giant
// startup download; on a host without ranges only individual shards load.
function bundleSource(bundle){
 let cursor=0;
 const parts=bundle.parts.map(p=>{const part={...p,start:cursor,end:cursor+p.size};cursor+=p.size;return part;});
 if(cursor!==bundle.size)throw new Error('Invalid bundle size: '+bundle.label);
 async function readPart(part,start,end){
  if(wholeParts.has(part.url))return wholeParts.get(part.url).subarray(start,end);
  const r=await fetch(part.url,{headers:{Range:`bytes=${start}-${end-1}`}});
  if(!r.ok)throw new Error(`Game file ${part.url}: HTTP ${r.status}. Reload and try again.`);
  const bytes=new Uint8Array(await r.arrayBuffer());
  if(r.status===206){const range=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(r.headers.get('Content-Range')||'');if(!range||Number(range[1])!==start||bytes.length<end-start)throw new Error('Incomplete byte range: '+part.url);return bytes.subarray(0,end-start);}
  if(bytes.length!==part.size)throw new Error('Incomplete game file: '+part.url);
  wholeParts.set(part.url,bytes);while(wholeParts.size>2)wholeParts.delete(wholeParts.keys().next().value);
  return bytes.subarray(start,end);
 }
 return {size:bundle.size,async read(start,end){
  if(start<0||end>bundle.size||end<start)throw new Error('Invalid archive range');
  const slices=await Promise.all(parts.filter(p=>p.start<end&&p.end>start).map(p=>readPart(p,Math.max(start,p.start)-p.start,Math.min(end,p.end)-p.start)));
  const out=new Uint8Array(end-start);let off=0;for(const slice of slices){out.set(slice,off);off+=slice.length;}if(off!==out.length)throw new Error('Missing archive shard');return out;
 }};
}

function clean(name){name=name.replaceAll('\\','/');return name.startsWith('/')||name.split('/').includes('..')?'':name;}
function findRoot(names){
 const all=names.map(clean).filter(Boolean), lower=new Set(all.map(n=>n.toLowerCase()));
 const roots=all.filter(n=>/(?:^|\/)data\/system\.def$/i.test(n)).map(n=>n.slice(0,-'data/system.def'.length)).filter(p=>lower.has((p+'data/select.def').toLowerCase())&&lower.has((p+'chars/GokuZ2/GokuZ2.def').toLowerCase()));
 if(roots.length!==1)throw new Error('Choose a complete Hyper DBZ ZIP, all four ZIP parts together, or the extracted game folder. The selection needs data/system.def, data/select.def, and GokuZ2.');
 const prefix=roots[0];return name=>{name=clean(name);if(!name.toLowerCase().startsWith(prefix.toLowerCase()))return null;name=name.slice(prefix.length);return allowed.has(name.split('/')[0].toLowerCase())&&!/\.(exe|dll|psd|bak|log)$/i.test(name)?name:null;};
}
async function dbRequest(mode,fn){
 const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('hyperdbz-web-imports',1);r.onupgradeneeded=()=>r.result.createObjectStore('files');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
 try{return await new Promise((resolve,reject)=>{const tx=db.transaction('files',mode),r=fn(tx.objectStore('files'));tx.oncomplete=()=>resolve(r.result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('Browser storage is full'));});}finally{db.close();}
}
function availability(){const ready=Boolean(selected||manifest?.bundles?.length);$('start').disabled=$('quick').disabled=!ready;$('clear-import').hidden=!selected;$('availability').textContent=selected?'Your original game files are ready.':ready?'Full hosted roster · smaller audio · loads on demand':'Choose your Hyper DBZ ZIP files to begin.';}
async function importFiles(files,folder){
 if(!files.length)return;$('import-info').textContent='Checking your files…';
 try{
  const chosen=Array.from(files).map(f=>({name:folder?f.webkitRelativePath:f.name,blob:f}));
  if(!folder&&chosen.some(f=>!f.name.toLowerCase().endsWith('.zip')))throw new Error('Choose ZIP files, or use Choose folder for an extracted game.');
  let names;
  if(folder)names=chosen.map(f=>f.name);
  else{
   const parts=chosen.map(f=>/part[_ -]*(\d+)[_ -]*of[_ -]*(\d+)/i.exec(f.name)).filter(Boolean);
   if(parts.length){const total=Number(parts[0][2]),present=new Set(parts.map(p=>Number(p[1]))),missing=Array.from({length:total},(_,i)=>i+1).filter(i=>!present.has(i));if(missing.length)throw new Error('Select all '+total+' ZIP parts together. Missing: '+missing.join(', ')+'. No merging is needed.');}
   names=(await Promise.all(chosen.map(f=>listZipIndex(f.blob)))).flatMap(i=>i.entries.map(e=>e.name));
  }
  findRoot(names);selected={kind:folder?'folder':'zips',files:chosen};availability();$('import-info').textContent='Files ready. Remembering them for your next visit…';
  try{await dbRequest('readwrite',s=>s.put(selected,'game'));$('import-info').textContent='Original files ready and remembered in this browser. Click Start game or Quick fight.';}
  catch{$('import-info').textContent='Files are ready for this visit. There is not enough browser storage to remember them; choose them again next time.';}
 }catch(e){$('import-info').textContent=e.message;}
}
async function mountGame(){
 if(selected){
  status('Reading your original game files…');
  const names=selected.kind==='folder'?selected.files.map(f=>f.name):(await Promise.all(selected.files.map(f=>listZipIndex(f.blob)))).flatMap(i=>i.entries.map(e=>e.name));
  const mapper=findRoot(names);
  if(selected.kind==='folder')mountFileTree(selected.files,mount,mapper);else for(const file of selected.files)await mountZipIndex(file.blob,mount,{mapName:mapper});
 }else{let n=0;for(const bundle of manifest.bundles){status('Indexing game files… '+(++n)+' / '+manifest.bundles.length,n/manifest.bundles.length);await mountZipIndex(bundleSource(bundle),mount);}}
}
async function start(quick){
 if(running)return;running=true;const began=Date.now();$('launcher').hidden=true;$('game').hidden=false;$('loading').hidden=false;document.body.classList.add('playing');
 try{
  const probe=document.createElement('canvas').getContext('webgl2');if(!probe)throw new Error('WebGL 2 is unavailable in this browser. The game needs WebGL 2 and WebAssembly.');probe.getExtension('WEBGL_lose_context')?.loseContext();
  status('Loading browser engine support…');await mountZip('base.zip',mount);await mountGame();await mkdir(mount+'/save');
  try{await readText(mount+'/save/browser-config.ini');}catch(e){if(e.code!=='ENOENT')throw e;const r=await fetch('default-config.ini');if(!r.ok)throw new Error('Browser configuration is missing');await writeText(mount+'/save/browser-config.ini',await r.text());}
  if($('skip-intro').checked){const system=await readText(mount+'/data/system.def');await writeText(mount+'/data/system.def',system.replace(/^(\s*(?:logo|intro)\.storyboard\s*=).*$/gmi,'$1'));}
  process.chdir(mount);status('Loading fighting engine…');
  const go=new Go();go.argv=['ikemen','-config','save/browser-config.ini'];if(quick)go.argv.push('-p1',$('fighter').value,'-p2',$('opponent').value,'-p2.ai','4','-s','stages/HDBZ_kamehouse.def');
  const r=await fetch('ikemen.wasm');if(!r.ok)throw new Error('The browser engine is missing (HTTP '+r.status+').');let instance;
  try{instance=(await WebAssembly.instantiateStreaming(Promise.resolve(r.clone()),go.importObject)).instance;}catch{instance=(await WebAssembly.instantiate(await r.arrayBuffer(),go.importObject)).instance;}
  let code=0;go.exit=value=>{code=value;};status(quick?'Preparing fighters…':'Opening the game menu…');log('Engine ready; starting '+(quick?'quick fight':'original menu'));
  timer=setInterval(()=>{const fps=Number(window.__ikemenFPS||0);$('boot-log').textContent=window.__ikemenBootLog.slice(-40).join('\n');if(fps>0){$('loading').hidden=true;$('runtime-state').textContent='HYPER DBZ · '+Math.round(fps)+' FPS';}else if(Date.now()-began>25000)$('load-detail').textContent='Still loading. The first launch reads sprites and sounds. Keep this tab open.';},350);
  $('ikemen-canvas').focus();await go.run(instance);clearInterval(timer);if(code)throw new Error('Engine exited with code '+code);$('loading').hidden=true;$('runtime-state').textContent='Game closed · use Launcher to play again';
 }catch(e){fail(e);}
}
window.addEventListener('hdbz-file',e=>{const char=/\/chars\/([^/]+)/i.exec(e.detail)?.[1],text=char?'Loading '+char.replace(/Z2$/i,'').replaceAll('_',' ')+'…':'Loading game assets…';if(running&&!$('loading').hidden)status(text);$('runtime-state').textContent=text;});
window.addEventListener('error',e=>{if(running)fail(e.error||new Error(e.message));});window.addEventListener('unhandledrejection',e=>{if(running)fail(e.reason);});
const resume=()=>window.__ikemenResumeAudio?.();window.addEventListener('pointerdown',resume);window.addEventListener('keydown',resume);
$('start').addEventListener('click',()=>start(false));$('quick').addEventListener('click',()=>start(true));
$('import').addEventListener('click',()=>$('zip-input').click());$('folder').addEventListener('click',()=>$('folder-input').click());
$('zip-input').addEventListener('change',e=>importFiles(e.target.files,false));$('folder-input').addEventListener('change',e=>importFiles(e.target.files,true));
$('clear-import').addEventListener('click',async()=>{selected=null;try{await dbRequest('readwrite',s=>s.delete('game'));}catch{}$('import-info').textContent='Using the hosted web edition.';availability();});
for(const id of ['back','retry'])$(id).addEventListener('click',()=>location.reload());
$('fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('game').requestFullscreen();}catch{$('runtime-state').textContent='Fullscreen is unavailable; the game can still run in this window.';}});
document.addEventListener('dragover',e=>{if(!running)e.preventDefault();});document.addEventListener('drop',e=>{if(!running){e.preventDefault();importFiles(e.dataTransfer.files,false);}});
await Promise.allSettled([fetch('game-manifest.json').then(async r=>{if(r.ok)manifest=await r.json();}),dbRequest('readonly',s=>s.get('game')).then(record=>{if(record?.files?.length){selected=record;$('import-info').textContent='Your original game files are remembered in this browser.';}})]);availability();
