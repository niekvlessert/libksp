# KSP1PLAY DSK Builder v0.47.1

Creates a 720 KB MSX FAT12 DSK containing the latest stable normal KSP1PLAY player and every `.KSP` file found in a directory.

The included template uses the player files from the stable v0.47.1 Micro Cabin release. The executable core identifies itself as **KSP1PLAY v0.47.0**; v0.47.1 changed the Xak KSP catalog, not the player binary.

## Basic use

```bash
python3 ksp_dsk_builder.py /path/to/ksps -o MYMUSIC.DSK
```

Overwrite an existing output:

```bash
python3 ksp_dsk_builder.py /path/to/ksps -o MYMUSIC.DSK --force
```

Include KSPs in subdirectories:

```bash
python3 ksp_dsk_builder.py /path/to/ksps -o MYMUSIC.DSK --recursive
```

Use another player/template DSK:

```bash
python3 ksp_dsk_builder.py /path/to/ksps -o MYMUSIC.DSK --template OTHER_BASE.DSK
```

## Menu names

The builder creates `INDEX.TXT` in the exact fixed 80-byte format expected by KSP1PLAY.

Menu titles are selected in this order:

1. `INDEX.TXT` next to the source KSPs, or a file passed with `--title-map`.
2. `title=` (or `game=`) from readable KSP META data.
3. The source filename.

An override file uses the normal KSP1PLAY form:

```text
FONYSNG.KSP |Fony SNG Full Collection
XAK2.KSP    |Xak II: Rising of the Redmoon
```

The left side may also be the original long source filename. This is useful when the generated on-disk name has to be shortened to 8.3.

## 8.3 names

All output KSP filenames are made DOS/MSX-safe automatically. Long names are shortened and collisions use `~1`, `~2`, etc. The original KSP data is never modified.

## Capacity

The disk is a standard 720 KB FAT12 image. The clean included template has roughly 649 KB available for KSP files plus `INDEX.TXT` and `README.TXT`. The builder aborts with a clear `disk full` error rather than creating a truncated image.

## Requirements

Python 3.9 or later. No external Python packages and no `mtools` are required.
