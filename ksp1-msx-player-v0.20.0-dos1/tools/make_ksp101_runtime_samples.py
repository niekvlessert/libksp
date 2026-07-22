#!/usr/bin/env python3
"""Create deterministic KSP 1.01 runtime-profile regression packs."""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def u16(data: bytes | bytearray, off: int) -> int:
    return struct.unpack_from('<H', data, off)[0]


def u32(data: bytes | bytearray, off: int) -> int:
    return struct.unpack_from('<I', data, off)[0]


def recalc_crcs(data: bytearray) -> None:
    ranges = []
    for off_off, count_off, size_off in (
        (0x10, 0x14, 0x16),
        (0x18, 0x1C, 0x1E),
        (0x20, 0x24, 0x26),
        (0x28, 0x2C, 0x2E),
    ):
        off, count, size = u32(data, off_off), u16(data, count_off), u16(data, size_off)
        ranges.append(bytes(data[off:off + count * size]))
    so, ss = u32(data, 0x30), u32(data, 0x34)
    ranges.append(bytes(data[so:so + ss]))
    struct.pack_into('<I', data, 0x44, zlib.crc32(b''.join(ranges)) & 0xFFFFFFFF)
    struct.pack_into('<I', data, 0x40, 0)
    struct.pack_into('<I', data, 0x40, zlib.crc32(bytes(data[:80])) & 0xFFFFFFFF)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--page3-output', type=Path, required=True)
    ns = ap.parse_args()
    data = bytearray(ns.source.read_bytes())
    if data[:4] != b'KSP1' or u16(data, 4) != 80:
        raise SystemExit('source is not a KSP1 package')
    engine_off = u32(data, 0x10)
    struct.pack_into('<H', data, 0x06, 1)
    struct.pack_into('<I', data, engine_off, u32(data, engine_off) | 0x10)
    recalc_crcs(data)
    ns.page3_output.parent.mkdir(parents=True, exist_ok=True)
    ns.page3_output.write_bytes(data)
    print(f'wrote {ns.page3_output} ({len(data)} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
