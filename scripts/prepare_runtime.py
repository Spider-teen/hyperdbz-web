#!/usr/bin/env python3
"""Prepare the pinned IKEMEN browser runtime and its small core archive."""
from pathlib import Path
import re, shutil, sys, zipfile
upstream=Path(sys.argv[1]); dest=Path(sys.argv[2]); dest.mkdir(parents=True,exist_ok=True)
s=(upstream/'web/fs-shim.js').read_text().replace('const LS_PREFIX = "ikemenfs:";','const LS_PREFIX = "hyperdbzfs-v1:";')
s=s.replace('async function fetchRange(url, start, end, ifRange) {','''async function fetchRange(url, start, end, ifRange) {
        if (url && typeof url.read === "function") return {buf: new Uint8Array(await url.read(start, Math.min(end+1, url.size))), partial: true};
        if (url instanceof Blob) return {buf: new Uint8Array(await url.slice(start, end+1).arrayBuffer()), partial: true};''')
s=s.replace('async function fetchZipIndex(url) {','''async function fetchZipIndex(url) {
        if (url instanceof Blob || (url && typeof url.read === "function")) {
            const total=url.size, start=Math.max(0,total-INDEX_TAIL);
            const tail=(await fetchRange(url,start,total-1)).buf;
            const e=findEOCD(tail);
            if(e.cdOffset+e.cdSize>total) throw new Error("Invalid ZIP directory range");
            const cd=e.cdOffset>=start ? tail.subarray(e.cdOffset-start,e.cdOffset-start+e.cdSize) : (await fetchRange(url,e.cdOffset,e.cdOffset+e.cdSize-1)).buf;
            return {entries:parseCentralDirectory(cd,e.count),total,ifRange:null};
        }''')
old='''		for (const e of idx.entries) {
			if (e.name.includes("..")) continue; // hostile path, skip
			const target = mountPoint + "/" + e.name;'''
new='''        for (const original of idx.entries) {
            let name=original.name.replace(/\\\\/g,"/");
            if(opts.mapName) name=opts.mapName(name);
            if(!name || name.startsWith("/") || name.split("/").includes("..")) continue;
            const e={...original,name};
            const target=mountPoint+"/"+name;'''
assert old in s;s=s.replace(old,new)
s=s.replace('''			let data;
			if (l.compSize === 0 && l.size === 0) {''','''            let data;
            if(l.load) data=new Uint8Array(await l.load());
            else if (l.compSize === 0 && l.size === 0) {''')
s=s.replace('''		const l = node.lazy;
		node.lazyFetch''','''        const l=node.lazy;
        if(globalThis.dispatchEvent) globalThis.dispatchEvent(new CustomEvent("hdbz-file",{detail:path}));
        node.lazyFetch''')
s=s.replace('''				delete node.lazy;
				lazyState.hydrated++;''','''                if(data.length>512*1024) node.archiveSource=l;
                delete node.lazy;
                lazyState.hydrated++;''')
s=s.replace('''				const accmode = flags & 3;
				let node = r.node;''','''                const accmode=flags&3;
                let node=r.node;
                if(node && accmode!==constants.O_RDONLY) delete node.archiveSource;''')
old='''		close: cbWrap((fd) => {
			if (!fds.delete(fd) && fd > 2) throw errnoError("EBADF", "fd " + fd);
			return null;
		}),'''
new='''        close: cbWrap((fd)=>{
            const record=fds.get(fd);
            if(!fds.delete(fd)&&fd>2) throw errnoError("EBADF","fd "+fd);
            if(record && record.node.archiveSource && !record.writable && !Array.from(fds.values()).some(f=>f.node===record.node)) {
                record.node.lazy=record.node.archiveSource;
                record.node.buf=null;
            }
            return null;
        }),'''
assert old in s;s=s.replace(old,new)
s=s.replace('globalThis.mountZipIndex = mountZipIndex;','''globalThis.mountZipIndex = mountZipIndex;
    globalThis.listZipIndex=fetchZipIndex;
    globalThis.mountFileTree=function(files,mountPoint,mapper) {
        mkdirAt(mountPoint);
        for(const file of files) {
            const name=mapper(file.name);
            if(!name||name.endsWith("/")) continue;
            setFileAt(mountPoint+"/"+name,makeLazyFile({size:file.blob.size,compSize:file.blob.size,load:()=>file.blob.arrayBuffer()}));
        }
    };''')
(dest/'fs-shim.js').write_text(s);shutil.copy(upstream/'web/wasm_exec.js',dest/'wasm_exec.js')
with zipfile.ZipFile(dest/'base.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for folder in ['data','external','font']:
        for f in sorted((upstream/'engine'/folder).rglob('*')):
            if f.is_file() and f.suffix not in {'.ico','.spv'} and 'icon-src' not in f.parts:z.write(f,f.relative_to(upstream/'engine').as_posix())
cfg=(upstream/'engine/src/resources/defaultConfig.ini').read_text()
for key,value in {'Motif':'data/system.def','FirstRun':'0','GameWidth':'640','GameHeight':'480','WindowWidth':'640','WindowHeight':'480','BootLoadingMode':'2','WindowTitle':'Hyper DBZ — Browser Edition','StartStage':'stages/HDBZ_kamehouse.def'}.items():
    cfg=re.sub(r'(?m)^('+re.escape(key)+r'\s*=).*$',lambda m:m.group(1)+' '+value,cfg)
(dest/'default-config.ini').write_text(cfg)
shutil.copy(upstream/'LICENSE',dest/'LICENSE');shutil.copy(upstream/'engine/LICENCE.txt',dest/'ENGINE-LICENSE.txt')
(dest/'.nojekyll').touch()
print('Prepared runtime; base archive bytes:',(dest/'base.zip').stat().st_size)
