# KSP1PLAY 0.20.0 — standalone MSX-DOS1 edition

This edition removes the MSX-DOS2 dependency from the graphical KSP player.
It is an **MSX-DOS1 `.COM` program** and uses only the traditional FCB disk API
available in MSX-DOS1.

It accepts backward-compatible KSP 1.00 and 1.01 files.

## Requirements

- MSX2 or newer, because the interface uses SCREEN 5.
- MSX-DOS1 at address `0005h`.
- A memory mapper with at least 128 KiB.
- KSP files in the current directory using DOS 8.3 filenames.
- Do not use a RAM disk or another resident tool that privately occupies hidden
  mapper segments while this standalone build is running.

MSX-DOS1 has no mapper-segment ownership API. KSP1PLAY therefore detects the
primary mapper size and reserves unused high segments itself, excluding the four
segments mapped when the program starts. Packages that need more segments than
are available fail cleanly with an insufficient-memory message.

Use the v0.19.1 DOS2 edition when running under MSX-DOS2/Nextor and mapper
ownership must be coordinated with the operating system.

## Start

Open the graphical package menu:

```text
KSP1PLAY
```

Direct launch:

```text
KSP1PLAY FILE.KSP [track] [SCC-A-slot] [SCC-B-slot]
```

DOS1 restrictions:

- filenames are limited to 8.3;
- no subdirectories;
- an optional drive prefix such as `B:NEMESIS3.KSP` is accepted.

## DOS1 disk backend

The player uses these MSX-DOS1 calls:

```text
0Fh  open FCB
10h  close FCB
11h  search first
12h  search next
1Ah  set DTA
27h  random block read
```

The opened FCB uses a record size of one byte. The four-byte random-record field
therefore acts as a byte offset. KSP1PLAY retains its 24-bit file-offset limit and
can read templates, descriptors, ZX0 streams, cold HPOL slabs, metadata and track
titles directly from disk at arbitrary offsets.

Large KSP files do **not** have to fit in conventional RAM. Sparse files up to the
existing VRAM-cache limit may still be cached; larger and HPOL packages remain
disk-backed.

## Interface

- The startup menu lists up to 40 `*.KSP` files and displays 18 at once.
- Enter opens the track selector.
- The selector displays 15 titled tracks.
- Enter or Space starts the chosen track.
- During playback, 13 nearby tracks remain visible.
- Escape stops and unloads the package and returns to the package menu.
- Escape from the package menu restores native 80-column SCREEN 0, clears the
  BIOS keyboard buffer and returns to MSX-DOS1.

## Supported KSP/player features

- KSP 1.00 and 1.01
- sparse, complete and HPOL/hybrid pages
- raw, ZX0 and blocked-ZX0 resources
- disk-backed large-KSP loading
- automatic 50/60 Hz selection
- PSG, SCC, SCC+, dual normal SCC and YM2413/FMPAC
- MoonSound/OPL4 and MWK upload
- FMPAC key-off before blocking disk reads
- declarative `PAGE2_RUNTIME` and `PAGE3_WORKRAM`
- Screen 5 package menu, track selector and incremental repaint

## Memory layout

```text
0100-1BF9  core loader/player and DOS1 FCB backend
1C00-1FFF  KSP descriptors and I/O buffers
2000-2142  dynamic-page and dual-SCC gateways
2143-21F2  DOS1 8.3-to-FCB builder overlay
2200-34FC  Screen 5 UI and compact font
3500-36FF  HPOL position cache
3700-38FF  current HPOL map-row cache
3900-39EF  stack
3A00-3FF8  MoonSound/MWK module and lifecycle reset
```

## Build

```text
python3 build.py
```

The bundled assembler and model tests require only Python 3.

Generated files include:

- `build/KSP1PLAY.COM`
- `build/KSP1MENU.DSK`
- sparse, hybrid and PAGE3_WORKRAM regression disks

The `.DSK` files are data disks rather than complete boot disks. Mount one next
to an MSX-DOS1 system disk or DOS1 cartridge.

## Validation status

All inherited KSP, ZX0, HPOL, KSP 1.01, dual-SCC, MoonSound, FMPAC and graphical
UI model tests pass. A new DOS1 backend test checks:

- absence of DOS2 handles and EXTBIO mapper calls;
- FCB 8.3 conversion;
- FCB byte-record random reads;
- DOS1 directory scanning;
- direct mapper detection and segment-pool construction;
- fixed memory boundaries.

No MSX emulator is installed in the build environment, so the final DOS1 runtime
must still be tested on openMSX or physical hardware.
