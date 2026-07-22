#!/usr/bin/env python3
"""Mark page-1 engines requiring writable page-2 runtime RAM as KSP 1.01."""

from __future__ import annotations

import argparse
import binascii
import struct
from pathlib import Path


PAGE2_RUNTIME = 1 << 3


def u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def crc32(data: bytes | bytearray) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def index_bytes(data: bytes | bytearray) -> bytes:
    chunks = []
    for offset_field, count_field, size_field in (
        (0x10, 0x14, 0x16), (0x18, 0x1C, 0x1E),
        (0x20, 0x24, 0x26), (0x28, 0x2C, 0x2E),
    ):
        offset = u32(data, offset_field)
        size = u16(data, count_field) * u16(data, size_field)
        chunks.append(bytes(data[offset:offset + size]))
    offset, size = u32(data, 0x30), u32(data, 0x34)
    chunks.append(bytes(data[offset:offset + size]))
    return b"".join(chunks)


def migrate(path: Path) -> None:
    data = bytearray(path.read_bytes())
    if data[:4] != b"KSP1" or u16(data, 4) != 80 or u32(data, 0x0C) != len(data):
        raise ValueError(f"{path}: invalid KSP package")
    if u16(data, 0x14) != 1:
        raise ValueError(f"{path}: migration expects exactly one engine")
    engine = u32(data, 0x10)
    if u16(data, engine + 0x0C) != 0x4000 or u16(data, engine + 0x0E) != 0x4000:
        raise ValueError(f"{path}: engine is not a 4000h 16 KiB page")
    if u32(data, engine + 4) & 0x0E:
        raise ValueError(f"{path}: page-2 runtime conflicts with SCC hardware")

    struct.pack_into("<H", data, 6, 1)
    struct.pack_into("<I", data, engine, u32(data, engine) | PAGE2_RUNTIME)
    struct.pack_into("<I", data, 0x44, crc32(index_bytes(data)))
    struct.pack_into("<I", data, 0x40, 0)
    struct.pack_into("<I", data, 0x40, crc32(data[:80]))
    path.write_bytes(data)

    check = path.read_bytes()
    header = bytearray(check[:80])
    struct.pack_into("<I", header, 0x40, 0)
    if crc32(header) != u32(check, 0x40) or crc32(index_bytes(check)) != u32(check, 0x44):
        raise ValueError(f"{path}: CRC verification failed")
    print(f"{path}: KSP 1.01, engine flags 0x{u32(check, engine):08X}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="+", type=Path)
    args = parser.parse_args()
    for package in args.packages:
        migrate(package)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
