#!/usr/bin/env python3
"""Install turbo-R-safe YM2413 writers in known page-1 Micro Cabin packs."""

from __future__ import annotations

import argparse
import binascii
import importlib.util
import struct
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Patch:
    source: Path
    output: Path
    entry: int
    original: bytes
    destination: int
    delayed: bytes


XAK_WRITER = bytes.fromhex("c5 f5 78 ed 4b 9f 50 ed 79 00 0c f1 ed 79 c1 c9")
XAK_DELAYED = bytes.fromhex(
    "c5 f5 78 ed 4b 9f 50 ed 79 06 10 10 fe 0c f1 ed 79 06 40 10 fe c1 c9"
)
XAK2_WRITER = bytes.fromhex("c5 f5 78 ed 4b c1 4e ed 79 00 0c f1 ed 79 c1 c9")
XAK2_DELAYED = bytes.fromhex(
    "c5 f5 78 ed 4b c1 4e ed 79 06 10 10 fe 0c f1 ed 79 06 40 10 fe c1 c9"
)
IC_WRITER = bytes.fromhex("c5 4f 78 d3 7c 79 d3 7d c1 c9")
IC_DELAYED = bytes.fromhex(
    "c5 4f 78 d3 7c 06 10 10 fe 79 d3 7d 06 40 10 fe c1 c9"
)

PATCHES = {
    "xak1": Patch(
        ROOT / "ksp/msx/fmpac/XAK1_KSP1_PAGE1_SAFE.ksp",
        ROOT / "ksp/msx/fmpac/XAK1_KSP1_PAGE1_SAFE.ksp",
        0x508F,
        XAK_WRITER,
        0x45E0,
        XAK_DELAYED,
    ),
    "ic": Patch(
        ROOT / "ksp/msx/fmpac/ILLUSION_CITY_KSP1_PAGE1_SAFE.ksp",
        ROOT / "ksp/msx/fmpac/ILLUSION_CITY_KSP1_PAGE1_SAFE.ksp",
        0x40D8,
        IC_WRITER,
        0x40E2,
        IC_DELAYED,
    ),
    "xak2": Patch(
        ROOT / "ksp/msx/fmpac/XAK2_KSP1_PAGE1_SAFE.ksp",
        ROOT / "ksp/msx/fmpac/XAK2_KSP1_PAGE1_SAFE.ksp",
        0x4EB1,
        XAK2_WRITER,
        0x5805,
        XAK2_DELAYED,
    ),
    "gazell": Patch(
        ROOT / "ksp/msx/fmpac/XAK_GAZELL_KSP1_PAGE1_SAFE.ksp",
        ROOT / "ksp/msx/fmpac/XAK_GAZELL_KSP1_PAGE1_SAFE.ksp",
        0x4EB1,
        XAK2_WRITER,
        0x5805,
        XAK2_DELAYED,
    ),
}


def u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def crc32(data: bytes | bytearray) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def load_decoder():
    path = ROOT / "tools/rebuild_fray_page1.py"
    spec = importlib.util.spec_from_file_location("fray_rebuild", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load KSP decoder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.decode_object


def decode_sparse_pages(data: bytes, template: bytes, decode_object) -> tuple[list[bytes], list[bytes]]:
    page_offset = u32(data, 0x18)
    page_count = u16(data, 0x1C)
    page_size = u16(data, 0x1E)
    pages: list[bytes] = []
    overlays: list[bytes] = []
    for index in range(page_count):
        entry_offset = page_offset + index * page_size
        entry = data[entry_offset:entry_offset + page_size]
        if entry[2] != 0:
            raise ValueError(f"page {index}: expected sparse overlay")
        raw = decode_object(data, u32(entry, 8), u32(entry, 12), u32(entry, 16), entry[3])
        page = bytearray(template)
        cursor = 0
        while cursor < len(raw):
            destination, count = struct.unpack_from("<HH", raw, cursor)
            cursor += 4
            if not count or destination + count > len(page) or cursor + count > len(raw):
                raise ValueError(f"page {index}: invalid sparse record")
            page[destination:destination + count] = raw[cursor:cursor + count]
            cursor += count
        pages.append(bytes(page))
        overlays.append(raw)
    return pages, overlays


def index_bytes(data: bytes | bytearray) -> bytes:
    engine_offset, engine_count, engine_size = u32(data, 0x10), u16(data, 0x14), u16(data, 0x16)
    page_offset, page_count, page_size = u32(data, 0x18), u16(data, 0x1C), u16(data, 0x1E)
    track_offset, track_count, track_size = u32(data, 0x20), u16(data, 0x24), u16(data, 0x26)
    resource_offset, resource_count, resource_size = u32(data, 0x28), u16(data, 0x2C), u16(data, 0x2E)
    string_offset, string_size = u32(data, 0x30), u32(data, 0x34)
    return b"".join((
        bytes(data[engine_offset:engine_offset + engine_count * engine_size]),
        bytes(data[page_offset:page_offset + page_count * page_size]),
        bytes(data[track_offset:track_offset + track_count * track_size]),
        bytes(data[resource_offset:resource_offset + resource_count * resource_size]),
        bytes(data[string_offset:string_offset + string_size]),
    ))


def apply_patch(config: Patch) -> tuple[int, int]:
    decode_object = load_decoder()
    data = bytearray(config.source.read_bytes())
    if data[:4] != b"KSP1" or u16(data, 4) != 80 or u32(data, 0x0C) != len(data):
        raise ValueError(f"{config.source}: invalid KSP1 package")

    engine_offset = u32(data, 0x10)
    engine = data[engine_offset:engine_offset + u16(data, 0x16)]
    if u16(engine, 0x0C) != 0x4000 or u16(engine, 0x0E) != 0x4000 or engine[0x20] != 0:
        raise ValueError("expected an uncompressed normal page-1 template")
    template_offset = u32(engine, 0x24)
    template_size = u32(engine, 0x2C)
    template = bytearray(data[template_offset:template_offset + template_size])
    pages, overlays = decode_sparse_pages(bytes(data), bytes(template), decode_object)

    entry = config.entry - 0x4000
    destination = config.destination - 0x4000
    if bytes(template[entry:entry + len(config.original)]) != config.original:
        raise ValueError(f"unexpected writer at {config.entry:04X}; package may already be patched")
    if any(template[destination:destination + len(config.delayed)]):
        raise ValueError(f"delayed writer destination {config.destination:04X} is not free")
    for index, page in enumerate(pages):
        if page[entry:entry + len(config.original)] != config.original:
            raise ValueError(f"page {index} overlays the YM2413 writer")
        if any(page[destination:destination + len(config.delayed)]):
            raise ValueError(f"page {index} overlays the delayed writer destination")

    template[entry:entry + len(config.original)] = (
        bytes((0xC3, config.destination & 0xFF, config.destination >> 8))
        + bytes(len(config.original) - 3)
    )
    template[destination:destination + len(config.delayed)] = config.delayed
    data[template_offset:template_offset + template_size] = template
    struct.pack_into("<I", data, engine_offset + 0x30, crc32(template))

    page_offset = u32(data, 0x18)
    page_size = u16(data, 0x1E)
    for index, overlay in enumerate(overlays):
        page = bytearray(template)
        cursor = 0
        while cursor < len(overlay):
            offset, count = struct.unpack_from("<HH", overlay, cursor)
            cursor += 4
            page[offset:offset + count] = overlay[cursor:cursor + count]
            cursor += count
        struct.pack_into("<I", data, page_offset + index * page_size + 20, crc32(page))

    struct.pack_into("<I", data, 0x44, crc32(index_bytes(data)))
    struct.pack_into("<I", data, 0x40, 0)
    struct.pack_into("<I", data, 0x40, crc32(data[:0x50]))
    config.output.write_bytes(data)

    # Validate all checks that were changed.
    check = config.output.read_bytes()
    if crc32(check[:0x40] + b"\0\0\0\0" + check[0x44:0x50]) != u32(check, 0x40):
        raise ValueError("header CRC validation failed")
    if crc32(index_bytes(check)) != u32(check, 0x44):
        raise ValueError("index CRC validation failed")
    check_engine_offset = u32(check, 0x10)
    check_engine = check[check_engine_offset:check_engine_offset + u16(check, 0x16)]
    check_template_offset = u32(check_engine, 0x24)
    check_template = check[check_template_offset:check_template_offset + u32(check_engine, 0x2C)]
    if crc32(check_template) != u32(check_engine, 0x30):
        raise ValueError("template CRC validation failed")
    check_pages, _ = decode_sparse_pages(check, check_template, decode_object)
    check_page_offset = u32(check, 0x18)
    check_page_size = u16(check, 0x1E)
    for index, page in enumerate(check_pages):
        expected = u32(check, check_page_offset + index * check_page_size + 20)
        if crc32(page) != expected:
            raise ValueError(f"page {index} CRC validation failed")
    return len(pages), crc32(template)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="+", choices=sorted(PATCHES))
    args = parser.parse_args()
    for name in args.packages:
        pages, template_crc = apply_patch(PATCHES[name])
        print(f"{name}: patched {pages} pages, template CRC {template_crc:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
