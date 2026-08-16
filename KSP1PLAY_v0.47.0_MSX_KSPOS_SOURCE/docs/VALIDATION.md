# Validation

## Binary-equivalence gate

The normal build validates the three final runtime artifacts against hard-coded canonical hashes:

```sh
python3 build.py
```

Expected result:

```text
KSPPLAYER.BIN: EXACT canonical v0.47.0
KSPMENU.BIN:   EXACT canonical v0.47.0
KSPBOOT.BIN:   EXACT canonical v0.47.0
```

With the original base DSK available:

```sh
python3 build.py --reference-dsk KSP1PLAY_v0.47.1_BASE.DSK
```

also validates the executable boot-sector bytes.

## Verified canonical sizes

| Artifact | Bytes |
|---|---:|
| player core | 30,464 |
| menu module | 2,048 |
| KSPOS resident | 369 |
| finalizer | 50 |
| KSPBOOT.BIN | 31,043 |
| executable boot-sector loader | 215 |

## No-COM KSPOS boot test

The source-generated `KSP1PLAY_v0.47.0_SOURCE_BASE_NO_COM.DSK` was booted with openMSX 21.0 using a Panasonic FS-A1GT profile. A debugger breakpoint at `$0100` was reached from cold boot.

That proves the generated disk boots through the KSPOS boot sector and `KSPBOOT.BIN` into the source-built player core **without `KSP1PLAY.COM` being present on disk**.

The base test disk intentionally contains no KSP package. It is a source/build smoke test, not a replacement for the music regression disks.

## Runtime regression policy for future edits

Binary identity proves this recovered release equals v0.47.0. Once source changes are intentionally made, binary identity will of course no longer apply. At that point keep the following gates:

- cold KSPOS boot and menu return;
- SCC, SCC+, and dual-SCC hardware selection;
- expanded-slot return safety;
- FM-PAC/YM2413 package playback;
- PAGE2_RUNTIME track replacement (Xak-style regression);
- PAGE3_WORKRAM packages;
- dynamic-page packages with no disk I/O in the PLAY hot path;
- high track indices to exercise VDP index pacing;
- menu -> game -> menu -> other game -> menu lifecycle;
- 50/60 Hz timing and track-change behavior.

Use the canonical v0.47 binary as the A/B reference for any behavioral investigation.
