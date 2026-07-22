#!/usr/bin/env python3
"""Static/model checks for the standalone MSX-DOS1 FCB and mapper backend."""
from __future__ import annotations
import argparse
from pathlib import Path


def symbols(path: Path) -> dict[str, int]:
    out = {}
    for line in path.read_text().splitlines():
        if ' = ' in line:
            k, v = line.split(' = ', 1)
            out[k] = int(v, 0)
    return out


def fcb_name(name: str) -> bytes:
    drive = 0
    if len(name) >= 2 and name[1] == ':':
        drive = ord(name[0].upper()) - ord('A') + 1
        name = name[2:]
    if '/' in name or '\\' in name or ':' in name or name.count('.') > 1:
        raise ValueError(name)
    stem, dot, ext = name.partition('.')
    stem, ext = stem.upper(), ext.upper()
    if not (1 <= len(stem) <= 8 and len(ext) <= 3):
        raise ValueError(name)
    return bytes([drive]) + stem.ljust(8).encode() + ext.ljust(3).encode()


def pool(mask: int, pages: tuple[int, int, int, int], maximum: int = 12) -> list[int]:
    result = []
    for seg in range(mask, -1, -1):
        if seg not in pages:
            result.append(seg)
            if len(result) == maximum:
                break
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--symbols', type=Path, required=True)
    ns = ap.parse_args()
    src = ns.source.read_text()
    sym = symbols(ns.symbols)

    forbidden = ('EXTBIO', 'DOS_OPEN', 'DOS_CLOSE', 'DOS_READ', 'DOS_SEEK', 'DOS_TERM        equ 0x62')
    for item in forbidden:
        if item in src:
            raise SystemExit(f'DOS2 dependency remains: {item}')
    required = (
        'DOS_FOPEN       equ 0x0F', 'DOS_FCLOSE      equ 0x10',
        'DOS_SFIRST      equ 0x11', 'DOS_SNEXT       equ 0x12',
        'DOS_SETDTA      equ 0x1A', 'DOS_RDBLK       equ 0x27',
        'ld hl,1\n    ld (file_fcb+14),hl', 'ld (file_fcb+33),hl',
        'out (PORT_MAPPER_P1),a', 'out (PORT_MAPPER_P2),a',
        'mapper_probe_loop:', 'mapper_build_pool:', 'fcb_prepare_filename:',
        'ui_scan_wild_name:', 'ld hl,IO_BUFFER+1',
    )
    for item in required:
        if item not in src:
            raise SystemExit(f'missing DOS1 backend marker: {item}')

    if fcb_name('snatcher.ksp') != b'\x00SNATCHERKSP':
        raise SystemExit('8.3 FCB conversion model failed')
    if fcb_name('B:NEM3.KSP') != b'\x02NEM3    KSP':
        raise SystemExit('drive-qualified FCB conversion model failed')
    for bad in ('TOO_LONG9.KSP', 'DIR/FILE.KSP', 'A:B:C.KSP', ''):
        try:
            fcb_name(bad)
        except ValueError:
            pass
        else:
            raise SystemExit(f'invalid DOS1 filename accepted: {bad!r}')

    p = pool(7, (0, 1, 2, 3))
    if p != [7, 6, 5, 4]:
        raise SystemExit(f'128K mapper pool model failed: {p}')
    if len(pool(255, (252, 253, 254, 255))) != 12:
        raise SystemExit('large mapper pool cap failed')

    if sym.get('program_end', 0x1C01) > 0x1C00:
        raise SystemExit('DOS1 core overlaps descriptors')
    if sym.get('dos1_overlay_end', 0x2201) > 0x2200:
        raise SystemExit('DOS1 FCB overlay crosses UI module')
    print('MSX-DOS1 FCB/direct-mapper backend model passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
