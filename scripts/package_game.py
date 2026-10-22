#!/usr/bin/env python3
"""Build seekable web archives from Hyper DBZ ZIPs; originals stay untouched."""
import argparse, concurrent.futures, io, json, math, re, struct, subprocess, warnings, wave, zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

CHUNK = 20 * 1024 * 1024

def compact_wav(data):
    # scipy handles both integer PCM and the IEEE-float WAVs in this game.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', wavfile.WavFileWarning)
        rate, pcm = wavfile.read(io.BytesIO(data))
    if pcm.dtype == np.uint8 and pcm.ndim == 1 and rate <= 16000:
        return data
    if pcm.dtype.kind == 'f':
        samples = pcm.astype(np.float32)
    elif pcm.dtype.kind == 'i':
        samples = pcm.astype(np.float32) / (2 ** (pcm.dtype.itemsize * 8 - 1))
    elif pcm.dtype == np.uint8:
        samples = (pcm.astype(np.float32) - 128) / 128
    else:
        raise ValueError('Unsupported WAV type: ' + str(pcm.dtype))
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = np.nan_to_num(samples)
    target = min(rate, 16000)
    if target != rate and len(samples):
        g = math.gcd(rate, target)
        samples = resample_poly(samples, target // g, rate // g)
    raw = np.clip(np.rint(samples * 127 + 128), 0, 255).astype(np.uint8).tobytes()
    out = io.BytesIO()
    with wave.open(out, 'wb') as dest:
        dest.setnchannels(1); dest.setsampwidth(1); dest.setframerate(target); dest.writeframes(raw)
    return out.getvalue()

def compact_snd(data):
    assert data.startswith(b'ElecbyteSnd'), 'Invalid SND signature'
    count, pos = struct.unpack_from('<II', data, 16)
    sounds, seen = [], set()
    for _ in range(count):
        assert pos not in seen and pos + 16 <= len(data), 'Invalid SND sample offset'
        seen.add(pos)
        nxt, size, group, index = struct.unpack_from('<IIII', data, pos)
        assert pos + 16 + size <= len(data), 'Truncated SND sample'
        sounds.append((group, index, compact_wav(data[pos+16:pos+16+size])))
        pos = nxt
    out = io.BytesIO()
    header = bytearray(data[:512]); header.extend(b'\0' * max(0, 512-len(header)))
    struct.pack_into('<II', header, 16, len(sounds), 512); out.write(header)
    for i, (group, index, wav) in enumerate(sounds):
        nxt = out.tell()+16+len(wav) if i+1 < len(sounds) else 0
        out.write(struct.pack('<IIII', nxt, len(wav), group, index)); out.write(wav)
    return out.getvalue()

def package_group(item, dest):
    label, entries = item
    print('Packaging ' + label, flush=True)
    path = dest/(label+'.zip')
    sources = {}
    try:
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as out:
            for source_path, original, relative in entries:
                if source_path not in sources: sources[source_path] = zipfile.ZipFile(source_path)
                data = sources[source_path].read(original)
                if relative.lower().endswith('.snd'):
                    data = compact_snd(data)
                elif relative.lower().endswith('.mp3'):
                    music = subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i','pipe:0','-map_metadata','-1','-ac','2','-ar','32000','-b:a','64k','-f','mp3','pipe:1'],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
                    if len(music) < len(data): data = music
                out.writestr(relative, data)
        size, parts = path.stat().st_size, []
        with path.open('rb') as src:
            i = 0
            while data := src.read(CHUNK):
                name = f'{label}.{i:03d}.pak'; (dest/name).write_bytes(data)
                parts.append({'url': name, 'size': len(data)}); i += 1
        path.unlink()
        print('Completed ' + label + ': ' + str(size), flush=True)
        return {'label':label, 'size':size, 'parts':parts}
    finally:
        for src in sources.values(): src.close()

def main():
    p = argparse.ArgumentParser(); p.add_argument('input',type=Path); p.add_argument('--output',type=Path,default=Path('dist')); p.add_argument('--workers',type=int,default=3); args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    sources=sorted(args.input.glob('*.zip')); prefix=None; groups=defaultdict(list)
    for path in sources:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith('/data/system.def'): prefix=name[:-len('data/system.def')]
                if name.endswith('/READ ME.txt'): (args.output/'TEAM-Z2-README.txt').write_bytes(z.read(name))
    if prefix is None: raise ValueError('Missing complete game root')
    seen=set()
    for path in sources:
        with zipfile.ZipFile(path) as z:
            for e in z.infolist():
                if e.is_dir() or not e.filename.startswith(prefix): continue
                name=e.filename[len(prefix):]; parts=name.split('/')
                if parts[0].lower() not in {'chars','data','font','stages','sound','music'}: continue
                if Path(name).suffix.lower() in {'.exe','.dll','.psd','.js','.html','.css','.bak','.log'}: continue
                if name.lower() in seen: raise ValueError('Duplicate file: '+name)
                seen.add(name.lower()); group='char-'+parts[1].lower() if parts[0]=='chars' and len(parts)>2 else parts[0].lower()
                groups[group].append((str(path),e.filename,name))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        bundles=list(pool.map(lambda item:package_group(item,args.output),sorted(groups.items())))
    manifest={'version':'Hyper DBZ 6.0c — Wicked Ambition','audio':'Compact web audio; original ZIP import also supported','bundles':bundles}
    (args.output/'game-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('TOTAL '+str(sum(b['size'] for b in bundles)),flush=True)

if __name__=='__main__': main()
