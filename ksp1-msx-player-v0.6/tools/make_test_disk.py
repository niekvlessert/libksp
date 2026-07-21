#!/usr/bin/env python3
"""Create a deterministic 720 KiB FAT12 data disk for KSP1PLAY."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

SECTOR = 512
TOTAL_SECTORS = 1440
SECTORS_PER_CLUSTER = 2
RESERVED = 1
FATS = 2
SECTORS_PER_FAT = 3
ROOT_ENTRIES = 112
ROOT_SECTORS = (ROOT_ENTRIES * 32 + SECTOR - 1) // SECTOR
DATA_START = RESERVED + FATS * SECTORS_PER_FAT + ROOT_SECTORS
CLUSTER_BYTES = SECTOR * SECTORS_PER_CLUSTER


def short_name(name: str) -> bytes:
    stem, dot, ext = name.upper().partition('.')
    if not stem or len(stem) > 8 or len(ext) > 3 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$~!#%&-{}()@'`" for c in stem + ext):
        raise ValueError(f'not a valid deterministic 8.3 name: {name}')
    return stem.ljust(8).encode('ascii') + ext.ljust(3).encode('ascii')


def set_fat12(fat: bytearray, cluster: int, value: int) -> None:
    off = cluster + cluster // 2
    if cluster & 1:
        fat[off] = (fat[off] & 0x0F) | ((value << 4) & 0xF0)
        fat[off + 1] = (value >> 4) & 0xFF
    else:
        fat[off] = value & 0xFF
        fat[off + 1] = (fat[off + 1] & 0xF0) | ((value >> 8) & 0x0F)


def build(files: list[tuple[str, bytes]]) -> bytes:
    image = bytearray(TOTAL_SECTORS * SECTOR)
    boot = memoryview(image)[:SECTOR]
    boot[0:3] = b'\xEB\x3C\x90'
    boot[3:11] = b'KSP1PLAY'
    struct.pack_into('<H', boot, 11, SECTOR)
    boot[13] = SECTORS_PER_CLUSTER
    struct.pack_into('<H', boot, 14, RESERVED)
    boot[16] = FATS
    struct.pack_into('<H', boot, 17, ROOT_ENTRIES)
    struct.pack_into('<H', boot, 19, TOTAL_SECTORS)
    boot[21] = 0xF9
    struct.pack_into('<H', boot, 22, SECTORS_PER_FAT)
    struct.pack_into('<H', boot, 24, 9)
    struct.pack_into('<H', boot, 26, 2)
    struct.pack_into('<I', boot, 28, 0)
    boot[38] = 0x29
    struct.pack_into('<I', boot, 39, 0x4B535031)
    boot[43:54] = b'KSP1 TEST  '
    boot[54:62] = b'FAT12   '
    boot[510:512] = b'\x55\xAA'

    fat = bytearray(SECTORS_PER_FAT * SECTOR)
    fat[0:3] = b'\xF9\xFF\xFF'
    root = bytearray(ROOT_SECTORS * SECTOR)
    next_cluster = 2

    # Fixed 2026-07-21 12:00:00 timestamp.
    dos_date = ((2026 - 1980) << 9) | (7 << 5) | 21
    dos_time = (12 << 11)

    for index, (name, content) in enumerate(files):
        clusters = max(1, (len(content) + CLUSTER_BYTES - 1) // CLUSTER_BYTES)
        first = next_cluster
        for i in range(clusters):
            cluster = next_cluster + i
            set_fat12(fat, cluster, 0xFFF if i == clusters - 1 else cluster + 1)
            data_off = DATA_START * SECTOR + (cluster - 2) * CLUSTER_BYTES
            chunk = content[i * CLUSTER_BYTES:(i + 1) * CLUSTER_BYTES]
            image[data_off:data_off + len(chunk)] = chunk
        next_cluster += clusters
        entry = index * 32
        root[entry:entry + 11] = short_name(name)
        root[entry + 11] = 0x20
        struct.pack_into('<H', root, entry + 22, dos_time)
        struct.pack_into('<H', root, entry + 24, dos_date)
        struct.pack_into('<H', root, entry + 26, first)
        struct.pack_into('<I', root, entry + 28, len(content))

    if next_cluster >= 0xFF0:
        raise ValueError('disk content does not fit FAT12 image')
    fat1 = RESERVED * SECTOR
    fat2 = fat1 + SECTORS_PER_FAT * SECTOR
    root_off = fat2 + SECTORS_PER_FAT * SECTOR
    image[fat1:fat1 + len(fat)] = fat
    image[fat2:fat2 + len(fat)] = fat
    image[root_off:root_off + len(root)] = root
    return bytes(image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--com', required=True, type=Path)
    parser.add_argument('--ksp', required=True, type=Path)
    parser.add_argument('--ksp-name', default=None, help='8.3 name stored on disk')
    parser.add_argument('--track', type=int, default=0)
    parser.add_argument('--slot', type=int, default=2)
    args = parser.parse_args()
    ksp_name = (args.ksp_name or args.ksp.name).upper()
    short_name(ksp_name)  # validate before building
    command = f'KSP1PLAY {ksp_name} {args.track} {args.slot}\r\n'
    readme = (
        'KSP1PLAY MSX-DOS2 test data disk\r\n'
        'Not bootable: mount with an MSX-DOS2 system disk/cartridge.\r\n'
        f'Run: {command}'
        'SPACE selects the next track; ESC exits.\r\n'
    ).encode('ascii')
    autoexec = command.encode('ascii')
    image = build([
        ('KSP1PLAY.COM', args.com.read_bytes()),
        (ksp_name, args.ksp.read_bytes()),
        ('README.TXT', readme),
        ('AUTOEXEC.BAT', autoexec),
    ])
    args.output.write_bytes(image)
    print(f'wrote {args.output} ({len(image)} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
