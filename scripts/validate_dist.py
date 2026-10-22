#!/usr/bin/env python3
"""Check archive CRCs, compact sound samples, required files and roster."""
import io,json,struct,sys,wave,zipfile
from pathlib import Path
r=Path(sys.argv[1] if len(sys.argv)>1 else 'dist');m=json.loads((r/'game-manifest.json').read_text());names=set();texts={};samples=files=total=0
for b in m['bundles']:
    chunks=[]
    for p in b['parts']:
        data=(r/p['url']).read_bytes();assert len(data)==p['size']<=20*1024*1024,p['url'];chunks.append(data)
    data=b''.join(chunks);assert len(data)==b['size'];total+=len(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None,b['label']
        for n in z.namelist():
            assert n.lower() not in names,n;names.add(n.lower());files+=1
            if n.lower()=='data/select.def':texts['select']=z.read(n).decode('utf-8','replace')
            if not n.lower().endswith('.snd'):continue
            raw=z.read(n);assert raw.startswith(b'ElecbyteSnd'),n;count,pos=struct.unpack_from('<II',raw,16);seen=set()
            for _ in range(count):
                assert pos not in seen and pos+16<=len(raw),n;seen.add(pos);nxt,size,g,i=struct.unpack_from('<IIII',raw,pos);sample=raw[pos+16:pos+16+size];assert len(sample)==size,n
                with wave.open(io.BytesIO(sample)) as w:
                    assert w.getnchannels()==1 and w.getsampwidth()==1 and w.getframerate()<=16000,n
                    assert len(w.readframes(w.getnframes()))==w.getnframes(),n
                pos=nxt;samples+=1
for n in ['data/select.def','data/system.def','chars/gokuz2/gokuz2.def','chars/vegetaz2/normal_vegetaz2.def','stages/hdbz_kamehouse.def']:assert n in names,n
assert total<1024**3,'Site exceeds 1 GiB'
section='';characters=0
for line in texts['select'].splitlines():
    line=line.split(';')[0].strip().replace('\\','/')
    if line.startswith('['):section=line.lower()
    elif section=='[characters]' and line and line.lower() not in {'empty','randomselect'}:
        name=line.split(',')[0].strip().lower()
        if not name.endswith('.def'):name+='/'+name.split('/')[-1]+'.def'
        assert 'chars/'+name in names,'Missing roster character: '+name
        characters+=1
print(json.dumps({'bundles':len(m['bundles']),'files_crc_checked':files,'sound_samples_checked':samples,'roster_slots':characters,'compressed_bytes':total}))
