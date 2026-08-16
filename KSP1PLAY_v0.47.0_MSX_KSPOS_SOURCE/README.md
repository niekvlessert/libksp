# KSP1PLAY v0.47.0 KSPOS — clean source

This is a **compileable source release of the final KSP1PLAY v0.47.0 player core** used by the v0.47.1 base disk.

It targets the bootable **KSPOS** architecture. It does **not** require MSX-DOS, `MSXDOS.SYS`, `COMMAND.COM`, or a `KSP1PLAY.COM` file on disk.

The final original v0.47 development tree was not preserved as one complete source tree. This release was therefore from:

- the exact v0.47.0 binaries on the supplied v0.47.1 KSPOS disk;
- the complete, exactly rebuildable v0.44 Stage-6 source tree;
- earlier readable KSP1PLAY assembler sources used to restore high-confidence labels and subsystem names;
- the documented v0.47 fixes and runtime contracts.

The important result is deterministic: **the source assembles byte-for-byte to the final v0.47.0 binaries.**

## Build

Python 3 is the only build requirement.

```sh
python3 build.py
```

To additionally compare the generated boot-sector loader against an original v0.47.1 base disk:

```sh
python3 build.py --reference-dsk KSP1PLAY_v0.47.1_BASE.DSK
```

The build aborts if any canonical player binary differs in size or SHA-256.

## Outputs

`build.py` creates:

- `build/KSPPLAYER.BIN` — the 30,464-byte player core loaded at Z80 `$0100`;
- `build/KSPMENU.BIN` — the reloadable 2 KiB menu/UI module loaded at `$8000`;
- `build/KSPBOOT.BIN` — complete KSPOS boot image containing player + resident runtime;
- `build/KSP1PLAY_v0.47.0_SOURCE_BASE_NO_COM.DSK` — bootable 720 KiB FAT12 base disk with **no COM file**;
- `.sym` and `.lst` files for source navigation/debugging;
- `build/SHA256SUMS.txt`.

The generated base DSK contains only:

```text
KSPBOOT.BIN
KSPMENU.BIN
INDEX.TXT
README.TXT
```

Add KSP packages and normal fixed-record `INDEX.TXT` entries with the KSP disk builder.

## Source layout

```text
src/
  KSPPLAYER.asm             final embedded v0.47 player core
  KSPMENU.asm               final reloadable game/hardware menu
  boot/
    KSPOS_BOOT.asm          FAT12 boot-sector loader
    KSPOS_GATEWAY.asm       low-memory KSPOS call gateway
    KSPOS_RESIDENT.asm      mapper/page/engine resident runtime
    KSPOS_FINALIZER.asm     copies resident code and transfers control

tools/
  z80asm.py                 self-contained Z80 assembler
  fat12.py                  deterministic 720 KiB FAT12 image builder

docs/
  ARCHITECTURE.md
  SOURCE_PROVENANCE.md
  RECOVERED_SYMBOLS.md
  STRING_TABLE.md
  VALIDATION.md
```

## Readability / source status

This is **not a fake source file made from `DB` statements**. The final binaries have been losslessly decoded back to Z80 instructions and round-trip through the included assembler.

`KSPPLAYER.asm` is divided into major functional areas and restores many meaningful names such as `validate_header`, `validate_engine_profile`, `cleanup`, `hard_mute_audio`, `write_ym2413_register`, `vram_set_write_address`, mapper state fields, KSP parser state, and UI/runtime data. Labels that cannot be recovered with high confidence deliberately remain `lXXXXh` / `sub_XXXXh` instead of being given invented names.

`KSPMENU.asm` and the KSPOS boot/resident files have additional hand-written comments around their ABI and runtime roles.

For maintainability, improve remaining generic labels as behavior is understood, but keep `python3 build.py` as the binary-equivalence gate.

## Canonical binary hashes

```text
KSPPLAYER.BIN  30464  1f86b9a461de240a8e9665a7d8a3a48eda257e00856876af717887fbd654c0f8
KSPMENU.BIN     2048  afaa2f8501830ee24b9b078647c6a9e7c976ef993886b39beb7ff665605e4304
KSPBOOT.BIN    31043  8b75436e579957a6dc8812b8eea4ff7ca9f3ffb72524d730774bcf1fb156ca3c
```

The historical v0.47 disk also carried the player payload under the filename `KSP1PLAY.COM`. The clean source intentionally calls that same embedded byte stream `KSPPLAYER.BIN`; KSPOS never needs the COM file as a separate runtime file.

## Rule for future edits

Do not make address-level binary patches the new source of truth. Make changes in assembler, rebuild, and add a regression test or documented binary/runtime check for the affected subsystem.
