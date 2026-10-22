# Hyper DBZ in Chrome

An **experimental browser port** of Hyper Dragon Ball Z 6.0c (Wicked Ambition)
using the actual game files and IKEMEN GO's WebAssembly backend.
Players do not need Linux, Winlator, or a Windows executable.

Choose **Start game** for the original menu, or **Quick fight** for a match
against the computer. The hosted game includes the full roster and stages
with smaller audio. Characters, stages and tracks are read on demand.

For original audio, select all four `HyperDBZ_6.0c_Part_N_of_4.zip` files
together with **Choose ZIP files**. No merging is needed. A complete ZIP
and an extracted game folder also work. Nothing is uploaded; imported
files are remembered in IndexedDB when space permits.

| Action | Keys |
| --- | --- |
| Move / jump / crouch | Arrow keys |
| Light / medium / heavy punch | A / S / D |
| Light / medium / heavy kick | Z / X / C |
| Confirm / start | Enter |
| Back / pause | Escape |

Connect a controller before starting for Gamepad input.

## Verification and limits

This is experimental. **A playable match has not yet been verified.**
The available remote test browser has WebGL 2 disabled. Archive checksums,
sound sample headers, roster references, and JavaScript are checked
separately; a successful deployment is not gameplay verification.
MUGEN character scripting and screenpack compatibility may still need fixes.

Requires WebGL 2, WebAssembly, and a recent browser supporting
`DecompressionStream('deflate-raw')`. Device graphics restrictions can
prevent startup. Performance depends on CPU, GPU and available memory.
No browser netplay is implemented.

## Build and host

GitHub Pages can serve this static site from `main` / root. Keep `.nojekyll`.
The checked-in engine and `wasm_exec.js` are a matching prebuilt pair from
[mathmati/fiiight](https://github.com/mathmati/fiiight), revision
`9e4b23c1d49638a631d62bca279137704843edcb`.

To rebuild content from the four original ZIPs (Python, NumPy, SciPy and
FFmpeg required):

```sh
python3 scripts/package_game.py /path/to/original-zips --output .
python3 scripts/validate_dist.py .
```

The packager rebuilds sound banks as mono PCM WAV at up to 16 kHz / 8 bits,
including source IEEE-float WAV samples. Music uses 64 kbps MP3. Sprite and
character code files are unchanged. All emitted shards must be deployed
with their matching `game-manifest.json`.

To regenerate the core runtime, clone the pinned upstream and run:

```sh
python3 scripts/prepare_runtime.py /path/to/fiiight .
```

To rebuild `ikemen.wasm`, use Go 1.24.7 in upstream's `engine` folder:

```sh
GOEXPERIMENT=arenas GOOS=js GOARCH=wasm go build -trimpath -o ikemen.wasm ./src
```

Copy the same toolchain's `lib/wasm/wasm_exec.js` alongside that binary.

## Credits

Original game by **Team Z2**. Dragon Ball by **Akira Toriyama**. This is
free, noncommercial fan work. Support official releases. See CREDITS.txt,
TEAM-Z2-README.txt, LICENSE and ENGINE-LICENSE.txt for notices.
