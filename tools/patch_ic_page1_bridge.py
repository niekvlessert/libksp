#!/usr/bin/env python3
"""Make the Illusion City page-1 wrapper work without mapper-port mirroring."""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ksp/msx/fmpac/ILLUSION_CITY_KSP1_PAGE1_SAFE.ksp"
LOAD_ADDRESS = 0x4000

# Old INIT aliases the page-1 mapper segment into page 2, then jumps into it.
OLD_INIT = bytes.fromhex("db fd d3 fe c3 00 9f")
# New INIT calls an ordinary RAM copy and retains the same original entry.
NEW_INIT = bytes.fromhex("cd 20 52 c3 00 9f 00")
COPY_ADDRESS = 0x5220
COPY_ROUTINE = bytes.fromhex(
    "f5"          # PUSH AF: preserve KSP song id
    "21 00 40"    # LD HL,4000h
    "11 00 80"    # LD DE,8000h
    "01 00 40"    # LD BC,4000h
    "ed b0"       # LDIR
    "f1"          # POP AF
    "c9"          # RET
)


def load_helpers():
    path = ROOT / "tools/patch_ym2413_timing.py"
    spec = importlib.util.spec_from_file_location("timing_patch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load KSP patch helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    h = load_helpers()
    decode_object = h.load_decoder()
    data = bytearray(PACKAGE.read_bytes())
    if data[:4] != b"KSP1" or h.u16(data, 4) != 80 or h.u32(data, 0x0C) != len(data):
        raise ValueError("invalid KSP1 package")

    engine_offset = h.u32(data, 0x10)
    engine = data[engine_offset:engine_offset + h.u16(data, 0x16)]
    if h.u16(engine, 0x0C) != LOAD_ADDRESS or h.u16(engine, 0x0E) != 0x4000:
        raise ValueError("unexpected Illusion City engine profile")
    template_offset = h.u32(engine, 0x24)
    template_size = h.u32(engine, 0x2C)
    template = bytearray(data[template_offset:template_offset + template_size])
    pages, overlays = h.decode_sparse_pages(bytes(data), bytes(template), decode_object)

    init_offset = 0x5201 - LOAD_ADDRESS
    copy_offset = COPY_ADDRESS - LOAD_ADDRESS
    if bytes(template[init_offset:init_offset + len(OLD_INIT)]) != OLD_INIT:
        raise ValueError("unexpected Illusion City page-1 INIT wrapper")
    if any(template[copy_offset:copy_offset + len(COPY_ROUTINE)]):
        raise ValueError("copy-routine destination is not free")
    for index, page in enumerate(pages):
        if page[init_offset:init_offset + len(OLD_INIT)] != OLD_INIT:
            raise ValueError(f"page {index} overlays the INIT wrapper")
        if any(page[copy_offset:copy_offset + len(COPY_ROUTINE)]):
            raise ValueError(f"page {index} overlays the copy-routine destination")

    template[init_offset:init_offset + len(NEW_INIT)] = NEW_INIT
    template[copy_offset:copy_offset + len(COPY_ROUTINE)] = COPY_ROUTINE
    data[template_offset:template_offset + template_size] = template
    struct.pack_into("<I", data, engine_offset + 0x30, h.crc32(template))

    page_offset = h.u32(data, 0x18)
    page_size = h.u16(data, 0x1E)
    for index, overlay in enumerate(overlays):
        page = bytearray(template)
        cursor = 0
        while cursor < len(overlay):
            offset, count = struct.unpack_from("<HH", overlay, cursor)
            cursor += 4
            page[offset:offset + count] = overlay[cursor:cursor + count]
            cursor += count
        struct.pack_into("<I", data, page_offset + index * page_size + 20, h.crc32(page))

    struct.pack_into("<I", data, 0x44, h.crc32(h.index_bytes(data)))
    struct.pack_into("<I", data, 0x40, 0)
    struct.pack_into("<I", data, 0x40, h.crc32(data[:0x50]))
    PACKAGE.write_bytes(data)

    # Re-open and validate every modified CRC and reconstructed page.
    check = PACKAGE.read_bytes()
    if h.crc32(check[:0x40] + bytes(4) + check[0x44:0x50]) != h.u32(check, 0x40):
        raise ValueError("header CRC validation failed")
    if h.crc32(h.index_bytes(check)) != h.u32(check, 0x44):
        raise ValueError("index CRC validation failed")
    check_engine = check[engine_offset:engine_offset + h.u16(check, 0x16)]
    check_template = check[template_offset:template_offset + template_size]
    if h.crc32(check_template) != h.u32(check_engine, 0x30):
        raise ValueError("template CRC validation failed")
    check_pages, _ = h.decode_sparse_pages(check, check_template, decode_object)
    for index, page in enumerate(check_pages):
        expected = h.u32(check, page_offset + index * page_size + 20)
        if h.crc32(page) != expected:
            raise ValueError(f"page {index} CRC validation failed")

    print(f"Illusion City: installed self-copy INIT bridge; validated {len(check_pages)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
