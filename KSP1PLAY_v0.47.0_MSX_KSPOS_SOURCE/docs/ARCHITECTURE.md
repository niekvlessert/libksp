# v0.47 KSPOS architecture

## Boot flow

The player is a bootable KSPOS application, not an MSX-DOS program in normal use.

```text
FAT12 boot sector
      |
      | loads KSPBOOT.BIN
      v
0060h  KSPOS gateway / reserved area
0100h  KSPPLAYER core
7800h  KSPOS resident runtime
7971h  finalizer
      |
      +---- runtime disk load ----> KSPMENU.BIN at 8000h
```

Canonical `KSPBOOT.BIN` layout:

| CPU address | Size | Purpose |
|---|---:|---|
| `$0060-$00FF` | 160 | gateway plus reserved padding |
| `$0100-$77FF` | 30,464 | final v0.47 player core |
| `$7800-$7970` | 369 | KSPOS resident runtime |
| `$7971-$79A2` | 50 | finalizer |

The complete file is 31,043 bytes.

## KSPMENU.BIN

`KSPMENU.BIN` is a genuine boot-time/runtime component. The player opens the file, reads exactly `$0800` bytes into CPU address `$8000`, and calls its jump table.

The jump table is:

```text
8000h  VDP/text-mode setup
8003h  browser open/full draw
8006h  update one browser row
8009h  redraw visible browser rows
800Ch  restore/return hook
```

The module contains the game browser and detected-hardware presentation strings. It is therefore retained as a separate source-built runtime module.

## Main player responsibilities

The embedded player owns the KSP container and execution path, including:

- KSP header/table validation;
- engine and hardware-profile selection;
- HVAR/HVR1 resolution;
- mapper-segment allocation and restoration;
- dynamic-page and PAGE2/PAGE3 runtime profiles;
- sparse/complete/HPOL/RMP/PBM paths;
- selected-track preparation and live track changes;
- SCC/SCC+/dual-SCC, PSG, FM-PAC/YM2413, Y8950 and OPL4 plumbing inherited by this player line;
- UI transitions and menu integration;
- KSPOS-safe cleanup/return behavior.

## Final v0.47 fixes represented by the canonical binary

The final v0.47 code includes the release fixes for:

1. refreshing an already allocated writable PAGE2 runtime image when a stopped new track is installed, while preserving writable runtime state during callbacks;
2. return-safe SCC/SCC+ hardware detection without placing helper code in live HVAR workspace;
3. safe pacing for the two-byte VDP-backed track-index cache.

Because the source is binary-identical to the released v0.47 core, these behaviors are present even where a remaining generic label has not yet been renamed semantically.

## Why there is no COM output

The 30,464-byte core historically existed as `KSP1PLAY.COM` because earlier tooling and development branches could launch the same image under DOS. The KSPOS boot image embeds those bytes directly at `$0100`.

The clean source therefore names the standalone build product `KSPPLAYER.BIN` and embeds it in `KSPBOOT.BIN`. A separate COM file adds no runtime value to the bootable architecture.
