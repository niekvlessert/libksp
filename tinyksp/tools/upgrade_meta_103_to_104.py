#!/usr/bin/env python3
"""Upgrade an uncompressed KSP 1.03 META payload to strict KSP 1.04.

The conversion is size-preserving: header minor 3 -> 4 and
metadata_version=1 -> metadata_version=2. CRCs are recomputed.
"""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def checked_range(total: int, offset: int, size: int, what: str) -> None:
    if offset < 0 or size < 0 or offset > total or size > total - offset:
        raise ValueError(f"{what} is outside the file")


def upgrade(source: Path, destination: Path) -> None:
    data = bytearray(source.read_bytes())
    if len(data) < 80 or data[:4] != b"KSP1" or u16(data, 4) != 80:
        raise ValueError("not a supported KSP1 file")
    if u16(data, 6) != 3:
        raise ValueError("input must declare KSP minor version 3")
    if u32(data, 12) != len(data):
        raise ValueError("header file size does not match the input")

    resource_offset = u32(data, 0x28)
    resource_count = u16(data, 0x2C)
    resource_size = u16(data, 0x2E)
    meta_index = u16(data, 0x3A)
    if resource_size < 32 or meta_index == 0xFFFF or meta_index >= resource_count:
        raise ValueError("package has no valid META header reference")
    checked_range(len(data), resource_offset, resource_count * resource_size, "resource table")

    entry = resource_offset + meta_index * resource_size
    if data[entry:entry + 4] != b"META":
        raise ValueError("META header reference does not point to a META resource")
    compression = data[entry + 6]
    payload_offset = u32(data, entry + 8)
    packed_size = u32(data, entry + 12)
    unpacked_size = u32(data, entry + 16)
    if compression != 0 or packed_size != unpacked_size:
        raise ValueError("upgrade tool currently requires an uncompressed META resource")
    checked_range(len(data), payload_offset, packed_size, "META payload")

    payload = bytes(data[payload_offset:payload_offset + packed_size])
    old_line = b"metadata_version=1"
    new_line = b"metadata_version=2"
    lines = payload.split(b"\n")
    matches = [i for i, line in enumerate(lines) if line == old_line]
    if len(matches) != 1:
        raise ValueError("META must contain exactly one metadata_version=1 line")
    lines[matches[0]] = new_line
    upgraded_payload = b"\n".join(lines)
    if len(upgraded_payload) != len(payload):
        raise AssertionError("metadata upgrade unexpectedly changed payload size")
    data[payload_offset:payload_offset + packed_size] = upgraded_payload

    struct.pack_into("<H", data, 6, 4)
    struct.pack_into("<I", data, entry + 20, zlib.crc32(upgraded_payload) & 0xFFFFFFFF)

    index_parts = []
    for off_field, count_field, size_field, label in (
        (0x10, 0x14, 0x16, "engine table"),
        (0x18, 0x1C, 0x1E, "page table"),
        (0x20, 0x24, 0x26, "track table"),
        (0x28, 0x2C, 0x2E, "resource table"),
    ):
        offset = u32(data, off_field)
        count = u16(data, count_field)
        entry_size = u16(data, size_field)
        size = count * entry_size
        checked_range(len(data), offset, size, label)
        index_parts.append(bytes(data[offset:offset + size]))
    string_offset = u32(data, 0x30)
    string_size = u32(data, 0x34)
    checked_range(len(data), string_offset, string_size, "string table")
    index_parts.append(bytes(data[string_offset:string_offset + string_size]))
    struct.pack_into("<I", data, 0x44, zlib.crc32(b"".join(index_parts)) & 0xFFFFFFFF)

    struct.pack_into("<I", data, 0x40, 0)
    struct.pack_into("<I", data, 0x40, zlib.crc32(data[:80]) & 0xFFFFFFFF)
    destination.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    output = args.output or args.input.with_name(args.input.stem + "_KSP1_1.04" + args.input.suffix)
    upgrade(args.input, output)
    print(output)


if __name__ == "__main__":
    main()
