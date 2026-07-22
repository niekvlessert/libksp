#!/usr/bin/env python3
"""Source-aware Fray C000h-FFFFh -> 4000h-7FFFh KSP1 rebuild.

The original Fray KSP has a 0x2000-0xFFFF logical image.  This tool extracts
the original C000h-FFFFh runtime, applies only the reviewed pointer map below,
installs the page-1 INIT wrapper, and emits a normal KSP1 sparse-overlay pack.

This is intentionally a checked-in rebuild/validation tool rather than a
one-off byte patch.  Every relocation site has an expected source value; a
changed source image or an accidental overlay over a code pointer fails the
build.
"""
from __future__ import annotations

import argparse
import binascii
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "ksp/msx/fmpac/FRAY_KSP1_COMPRESSED.ksp"
DEFAULT_OUTPUT = ROOT / "ksp/msx/fmpac/FRAY_KSP1_PAGE1_SAFE.ksp"

SOURCE_IMAGE_BASE = 0x2000
SOURCE_RUNTIME_BASE = 0xC000
SOURCE_RUNTIME_OFFSET = SOURCE_RUNTIME_BASE - SOURCE_IMAGE_BASE
RUNTIME_SIZE = 0x4000
RELOCATION_DELTA = -0x8000
PAGE_LOAD = 0x4000
INIT_ADDRESS = 0x4CAB
PLAY_ADDRESS = 0x4E00
PLAY_DISPATCHER_ADDRESS = 0x4E2A
FRAY_FMPAC_BANK = 0x7F

# These are instruction addresses and the expected absolute source operand.
# They were reviewed from the original Fray runtime disassembly.  The tool
# finds the operand at +1 or +2 only after checking the expected word; it does
# not scan arbitrary bytes for high-valued words.
DIRECT_POINTERS = (
    (0xCE00, 0xCF76),
    (0xCE13, 0xCE2E),
    (0xCE22, 0xCE2C),
    (0xCE42, 0xCECD),
    (0xCE46, 0xCECD),
    (0xCE4A, 0xCECD),
    (0xCE4D, 0xC000),
    (0xCE50, 0xCEFC),
    (0xCE55, 0xCECD),
    (0xCE59, 0xCEFC),
    (0xCE5D, 0xCECD),
    (0xCE60, 0xCF66),
    (0xCE67, 0xD815),
    (0xCE6D, 0xD80F),
    (0xCE71, 0xD810),
    (0xCE79, 0xD815),
    (0xCE7E, 0xD814),
    (0xCE82, 0xD810),
    (0xCE86, 0xD80D),
    (0xCE8A, 0xD815),
    (0xCEA3, 0xCF2D),
    (0xCEA8, 0xD811),
    (0xCEBE, 0xCECB),
    (0xCECD, 0xD80D),
    (0xCED0, 0xD80E),
    (0xCEDC, 0xDAA3),
    (0xCEE1, 0xDA9F),
    (0xCEE6, 0xDAA0),
    (0xCEEB, 0xD80D),
    (0xCEF0, 0xCEB5),
    (0xCEF5, 0xD817),
    (0xCEF8, 0xCEAD),
    (0xCEFC, 0xD875),
    (0xCF2E, 0xD819),
    (0xCF31, 0xD81A),
    (0xCF3C, 0xD819),
    (0xCF51, 0xD757),
    (0xCF58, 0xD817),
    (0xCF5D, 0xD817),
    (0xCF62, 0xD811),
    (0xCF6C, 0xCEBB),
    (0xCF73, 0xCEEE),
    (0xCF76, 0xD813),
    (0xCF79, 0xD815),
    (0xCF8F, 0xD815),
    (0xCFA9, 0xD80F),
    (0xCFAF, 0xD810),
    (0xCFB3, 0xD815),
    (0xCFB6, 0xCF66),
    (0xCFBC, 0xD80D),
    (0xCFBF, 0xCECD),
    (0xCFC2, 0xCF66),
    (0xCFC7, 0xD80E),
    (0xCFCA, 0xD811),
    (0xCFCD, 0xD812),
    (0xCFD0, 0xDAA4),
    (0xCFD4, 0xDAA3),
    (0xCFDF, 0xD847),
    (0xCFE4, 0xD80E),
    (0xCFE9, 0xD055),
    (0xCFEE, 0xD055),
    (0xCFF3, 0xD055),
    (0xCFF7, 0xD055),
    (0xCFFC, 0xD055),
    (0xD001, 0xD055),
    (0xD006, 0xD055),
    (0xD00B, 0xD055),
    (0xD010, 0xD055),
    (0xD015, 0xD055),
    (0xD01A, 0xD055),
    (0xD01F, 0xD055),
    (0xD025, 0xDAA4),
    (0xD028, 0xD811),
    (0xD02E, 0xD80E),
    (0xD033, 0xD80D),
    (0xD037, 0xD7EB),
    (0xD03C, 0xD80E),
    (0xD03F, 0xD812),
    (0xD044, 0xD055),
    (0xD049, 0xD055),
    (0xD04C, 0xD80E),
    (0xD051, 0xD811),
    (0xD05A, 0xD816),
    (0xD06B, 0xD4D5),
    (0xD070, 0xD80E),
    (0xD073, 0xD63A),
    (0xD08A, 0xD816),
    (0xD090, 0xD4D5),
    (0xD0BD, 0xD3B9),
    (0xD0C8, 0xD815),
    (0xD0D0, 0xD3B9),
    (0xD0F4, 0xD546),
    (0xD112, 0xD4D5),
    (0xD11D, 0xD133),
    (0xD12D, 0xD10A),
    (0xD175, 0xD775),
    (0xD178, 0xD74F),
    (0xD17B, 0xD816),
    (0xD1A5, 0xD546),
    (0xD1AB, 0xD3B9),
    (0xD1B7, 0xD1BD),
    (0xD1BD, 0xD4D5),
    (0xD1C0, 0xD439),
    (0xD1CF, 0xD4D5),
    (0xD214, 0xD5AD),
    (0xD224, 0xD1A5),
    (0xD236, 0xD818),
    (0xD23F, 0xD80B),
    (0xD248, 0xCEBB),
    (0xD251, 0xD5AD),
    (0xD2A0, 0xD805),
    (0xD2A3, 0xD757),
    (0xD2C1, 0xD807),
    (0xD2C4, 0xD757),
    (0xD2E1, 0xD5AD),
    (0xD309, 0xD75D),
    (0xD310, 0xD5AD),
    (0xD314, 0xD5AD),
    (0xD317, 0xCEBB),
    (0xD31A, 0xD5AD),
    (0xD31D, 0xD809),
    (0xD320, 0xD74F),
    (0xD336, 0xD5BC),
    (0xD339, 0xD5AD),
    (0xD33C, 0xD347),
    (0xD33F, 0xD753),
    (0xD36A, 0xD4D5),
    (0xD377, 0xDAA0),
    (0xD37A, 0xD816),
    (0xD38B, 0xDAA0),
    (0xD38E, 0xD816),
    (0xD3A9, 0xD5AD),
    (0xD3AC, 0xDAA3),
    (0xD3B0, 0xD5AD),
    (0xD3BD, 0xD815),
    (0xD3C4, 0xD814),
    (0xD3DD, 0xD810),
    (0xD3E3, 0xD816),
    (0xD3EB, 0xD812),
    (0xD3F6, 0xCEAD),
    (0xD402, 0xDAA2),
    (0xD40A, 0xDAA1),
    (0xD410, 0xDAA1),
    (0xD413, 0xDAA2),
    (0xD41D, 0xCEBB),
    (0xD432, 0xCEBB),
    (0xD439, 0xD810),
    (0xD43F, 0xD816),
    (0xD44A, 0xD534),
    (0xD44E, 0xDA9F),
    (0xD452, 0xDA9F),
    (0xD457, 0xCEBB),
    (0xD45A, 0xD532),
    (0xD463, 0xCEBB),
    (0xD473, 0xCEBB),
    (0xD47D, 0xD812),
    (0xD4A7, 0xD817),
    (0xD4AC, 0xD817),
    (0xD4B1, 0xCEAD),
    (0xD4CC, 0xD5BC),
    (0xD4D2, 0xD6EC),
    (0xD4D6, 0xD816),
    (0xD4DE, 0xD812),
    (0xD4F8, 0xD817),
    (0xD4FC, 0xD817),
    (0xD501, 0xCEAD),
    (0xD50A, 0xD534),
    (0xD50F, 0xDA9F),
    (0xD513, 0xDA9F),
    (0xD518, 0xCEBB),
    (0xD52B, 0xCEBB),
    (0xD53A, 0xDAA0),
    (0xD547, 0xD816),
    (0xD55E, 0xD563),
    (0xD564, 0xD816),
    (0xD56C, 0xD812),
    (0xD579, 0xCEAD),
    (0xD583, 0xCEAD),
    (0xD58C, 0xDAA0),
    (0xD59B, 0xCEBB),
    (0xD5A8, 0xCEBB),
    (0xD5C1, 0xD5CC),
    (0xD5C4, 0xD753),
    (0xD5F5, 0xD600),
    (0xD60F, 0xD5D4),
    (0xD616, 0xD620),
    (0xD630, 0xD747),
    (0xD647, 0xD5BC),
    (0xD653, 0xD65E),
    (0xD656, 0xD753),
    (0xD674, 0xD731),
    (0xD67E, 0xD747),
    (0xD685, 0xD6EC),
    (0xD6A2, 0xD6EC),
    (0xD6C0, 0xD731),
    (0xD6D4, 0xD747),
    (0xD6E2, 0xD6EC),
    (0xD6FA, 0xD816),
    (0xD708, 0xD3B9),
    (0xD71F, 0xD816),
    (0xD72C, 0xD563),
)

# Pointer fields in data tables.  These are not inferred from byte patterns.
TABLE_POINTERS = (
    (0xCE2E, (0xCE42, 0xCE46, 0xCE4A, 0xCE5D, 0xCE64,
              0xCE71, 0xCE86, 0xCE8F, 0xCEA8, 0xCE54)),
    (0xD134, (0xD16F, 0xD1CB, 0xD1E5, 0xD1EE, 0xD1F2,
              0xD1FB, 0xD217, 0xD254, 0xD272, 0xD29D,
              0xD2BE, 0xD2D9, 0xD2E4, 0xD2E9, 0xD2E1,
              0xD251, 0xD214, 0xD310, 0xD31A, 0xD339)),
    (0xD347, (0xD35D, 0xD362, 0xD36D, 0xD372, 0xD377,
              0xD38B, 0xD39F, 0xD3A4, 0xD3A9, 0xD3B0, 0xD3B7)),
    (0xD5CC, (0xD5D4, 0xD5DF, 0xD60F, 0xD60F)),
    (0xD65E, (0xD666, 0xD68F, 0xD6B2, 0xD6B2)),
)

DATA_POINTERS = (
    (0xD805, 0xCC00),
    (0xD807, 0xCC30),
    (0xD809, 0xCC60),
    (0xD80B, 0xCCE0),
)

# The split driver expects an optional lookup workspace at B800h in mapper
# page 2. Every source track leaves B800h-BFFFh zero, disabling the lookup via
# its zero entry count. A normal page-1 engine cannot retain that mapper-bank
# contract, so redirect both reads to an immutable zero byte in the wrapper
# tail instead of interpreting arbitrary DOS/player page-2 RAM.
SOURCE_WORKSPACE = 0xB800
ZERO_WORKSPACE_SENTINEL = 0x4CBA
WORKSPACE_POINTERS = (0xCE8F, 0xCE9F)

# Fray's original YM2413 writer is fast enough on a Z80 but violates the OPLL
# address/data and data/recovery times on the turbo-R's R800. openMSX models
# the resulting lost writes. Keep the original entry address and redirect it
# to an expanded writer in the remaining free wrapper tail.
FM_WRITE_ENTRY = 0x4EBB
FM_WRITE_DELAY_ROUTINE = 0x4CBB
FM_WRITE_ORIGINAL = bytes((
    0xC5,                         # PUSH BC
    0xF5,                         # PUSH AF
    0x78,                         # LD A,B
    0xED, 0x4B, 0xCB, 0x4E,       # LD BC,(4ECBh)
    0xED, 0x79,                   # OUT (C),A: YM2413 address
    0x00,                         # NOP
    0x0C,                         # INC C
    0xF1,                         # POP AF
    0xED, 0x79,                   # OUT (C),A: YM2413 data
    0xC1,                         # POP BC
    0xC9,                         # RET
))
FM_WRITE_DELAY_BYTES = bytes((
    0xC5,                         # PUSH BC
    0xF5,                         # PUSH AF
    0x78,                         # LD A,B
    0xED, 0x4B, 0xCB, 0x4E,       # LD BC,(4ECBh)
    0xED, 0x79,                   # OUT (C),A: YM2413 address
    0x06, 0x10,                   # LD B,16
    0x10, 0xFE,                   # DJNZ $: address settling delay
    0x0C,                         # INC C: 7Ch -> 7Dh
    0xF1,                         # POP AF
    0xED, 0x79,                   # OUT (C),A: YM2413 data
    0x06, 0x40,                   # LD B,64
    0x10, 0xFE,                   # DJNZ $: data recovery delay
    0xC1,                         # POP BC
    0xC9,                         # RET
))

INIT_WRAPPER = bytes((
    0x3E, FRAY_FMPAC_BANK,  # LD A,7Fh: original Fray FM-PAC bank
    0xD3, 0xFE,             # OUT (0FEh): select the external Fray data bank
    0x3E, 0x03,             # LD A,3
    0xCD, 0x03, 0x4E,       # CALL 4E03h: relocated Fray dispatcher
    0x3E, 0x02,             # LD A,2
    0xC3, 0x03, 0x4E,       # JP 4E03h: tail-call dispatcher
))
INIT_CLEAR_BYTES = bytes((
    0x21, 0x0D, 0x58,       # LD HL,580Dh
    0x11, 0x0E, 0x58,       # LD DE,580Eh
    0x01, 0x97, 0x02,       # LD BC,0297h
    0x36, 0x00,             # LD (HL),0
    0xED, 0xB0,             # LDIR: clear through 5AA4h
))


class RebuildError(ValueError):
    pass


def u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def crc32(data: bytes | bytearray) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


class ZX0Reader:
    def __init__(self, packed: bytes, output_size: int):
        self.packed = packed
        self.output_size = output_size
        self.ip = 0
        self.bit_value = 0
        self.bit_mask = 0
        self.last_byte = 0
        self.backtrack = False
        self.out = bytearray()

    def byte(self) -> int:
        if self.ip >= len(self.packed):
            raise RebuildError("truncated ZX0 stream")
        self.last_byte = self.packed[self.ip]
        self.ip += 1
        return self.last_byte

    def bit(self) -> int:
        if self.backtrack:
            self.backtrack = False
            return self.last_byte & 1
        if not self.bit_mask:
            self.bit_value = self.byte()
            self.bit_mask = 0x80
        result = 1 if self.bit_value & self.bit_mask else 0
        self.bit_mask >>= 1
        return result

    def gamma(self, invert: int) -> int:
        value = 1
        while not self.bit():
            value = (value << 1) | (self.bit() ^ invert)
            if value > 0x7FFFFFFF:
                raise RebuildError("ZX0 gamma overflow")
        return value

    def literal(self, count: int) -> None:
        for _ in range(count):
            if len(self.out) >= self.output_size:
                raise RebuildError("ZX0 output overflow")
            self.out.append(self.byte())

    def match(self, offset: int, count: int) -> None:
        if offset <= 0 or offset > len(self.out):
            raise RebuildError(f"invalid ZX0 offset {offset}")
        for _ in range(count):
            if len(self.out) >= self.output_size:
                raise RebuildError("ZX0 output overflow")
            self.out.append(self.out[-offset])

    def decode(self) -> bytes:
        offset = 1
        self.literal(self.gamma(0))
        while True:
            if not self.bit():
                self.match(offset, self.gamma(0))
                if not self.bit():
                    self.literal(self.gamma(0))
                    continue
            while True:
                msb = self.gamma(1)
                if msb == 256:
                    if len(self.out) != self.output_size:
                        raise RebuildError("ZX0 output size mismatch")
                    return bytes(self.out)
                lsb = self.byte()
                offset = msb * 128 - (lsb >> 1)
                self.backtrack = True
                self.match(offset, self.gamma(0) + 1)
                if not self.bit():
                    self.literal(self.gamma(0))
                    break


def decode_object(data: bytes, offset: int, packed: int, raw: int, compression: int) -> bytes:
    payload = data[offset:offset + packed]
    if len(payload) != packed:
        raise RebuildError("object outside source file")
    if compression == 0:
        if packed != raw:
            raise RebuildError("raw object size mismatch")
        return payload
    if compression == 1:
        return ZX0Reader(payload, raw).decode()
    raise RebuildError(f"unsupported compression {compression}")


def decode_source(path: Path) -> tuple[bytes, bytes, list[bytes]]:
    data = path.read_bytes()
    if data[:4] != b"KSP1" or u16(data, 4) != 80:
        raise RebuildError(f"{path}: not a KSP1 source")
    if u32(data, 0x0C) != len(data):
        raise RebuildError("source file-size field mismatch")
    engine = data[80:144]
    if (u16(engine, 0x0C), u16(engine, 0x0E),
            u16(engine, 0x10), u16(engine, 0x12)) != (0x2000, 0xE000, 0x2001, 0xCE00):
        raise RebuildError("source is not the expected Fray split image")
    template = decode_object(data, u32(engine, 0x24), u32(engine, 0x28),
                             u32(engine, 0x2C), engine[0x20])
    if len(template) != 0xE000:
        raise RebuildError("unexpected source template size")

    pages: list[bytes] = []
    page_count = u16(data, 0x1C)
    page_size = u16(data, 0x1E)
    if page_count != 59 or page_size != 24:
        raise RebuildError("unexpected source page table")
    for index in range(page_count):
        entry = data[144 + index * page_size:144 + (index + 1) * page_size]
        raw = decode_object(data, u32(entry, 8), u32(entry, 12), u32(entry, 16), entry[3])
        page = bytearray(template)
        cursor = 0
        previous_end = 0
        while cursor < len(raw):
            if cursor + 4 > len(raw):
                raise RebuildError(f"source page {index}: truncated sparse record")
            destination, count = struct.unpack_from("<HH", raw, cursor)
            cursor += 4
            if not count or destination < previous_end or destination + count > len(page):
                raise RebuildError(f"source page {index}: invalid sparse record")
            if cursor + count > len(raw):
                raise RebuildError(f"source page {index}: sparse data outside payload")
            page[destination:destination + count] = raw[cursor:cursor + count]
            cursor += count
            previous_end = destination + count
        expected_crc = u32(entry, 20)
        if expected_crc and crc32(page) != expected_crc:
            raise RebuildError(f"source page {index}: CRC mismatch")
        pages.append(bytes(page))
    return data, template, pages


def relocate_word(blob: bytearray, address: int, expected: int, label: str) -> None:
    local = address - SOURCE_RUNTIME_BASE
    if not 0 <= local < RUNTIME_SIZE:
        raise RebuildError(f"{label}: source address outside runtime")
    candidates = [
        local + delta for delta in (1, 2)
        if local + delta + 2 <= len(blob)
        and u16(blob, local + delta) == expected
    ]
    if len(candidates) != 1:
        raise RebuildError(
            f"{label}: expected {expected:04X} at operand +1/+2, candidates={candidates}"
        )
    relocated = expected + RELOCATION_DELTA
    if not 0x4000 <= relocated <= 0x7FFF:
        raise RebuildError(f"{label}: relocated address outside page 1")
    struct.pack_into("<H", blob, candidates[0], relocated)


def relocate_pointer_table(
    blob: bytearray, start: int, targets: tuple[int, ...], stride: int, label: str
) -> None:
    for index, expected in enumerate(targets):
        address = start + index * stride
        local = address - SOURCE_RUNTIME_BASE
        if u16(blob, local) != expected:
            raise RebuildError(
                f"{label}[{index}]: expected {expected:04X}, got {u16(blob, local):04X}"
            )
        struct.pack_into("<H", blob, local, expected + RELOCATION_DELTA)


def relocate_runtime(source_image: bytes, label: str) -> bytes:
    if len(source_image) != 0xE000:
        raise RebuildError("source image has wrong logical size")
    blob = bytearray(source_image[SOURCE_RUNTIME_OFFSET:SOURCE_RUNTIME_OFFSET + RUNTIME_SIZE])
    for address, expected in DIRECT_POINTERS:
        relocate_word(blob, address, expected, f"{label}: {address:04X}")
    for start, targets in TABLE_POINTERS:
        stride = 3 if start == 0xD134 else 2
        relocate_pointer_table(blob, start, targets, stride, f"{label}: table {start:04X}")
    for address, expected in DATA_POINTERS:
        local = address - SOURCE_RUNTIME_BASE
        if u16(blob, local) != expected:
            raise RebuildError(
                f"{label}: data {address:04X}: expected {expected:04X}, "
                f"got {u16(blob, local):04X}"
            )
        struct.pack_into("<H", blob, local, expected + RELOCATION_DELTA)

    sentinel_local = ZERO_WORKSPACE_SENTINEL - PAGE_LOAD
    if blob[sentinel_local] != 0:
        raise RebuildError(f"{label}: zero-workspace sentinel is not free")
    for address in WORKSPACE_POINTERS:
        local = address - SOURCE_RUNTIME_BASE
        candidates = [
            local + delta for delta in (1, 2)
            if local + delta + 2 <= len(blob)
            and u16(blob, local + delta) == SOURCE_WORKSPACE
        ]
        if len(candidates) != 1:
            raise RebuildError(
                f"{label}: expected workspace B800 at {address:04X}, "
                f"candidates={candidates}"
            )
        struct.pack_into("<H", blob, candidates[0], ZERO_WORKSPACE_SENTINEL)

    fm_entry_local = FM_WRITE_ENTRY - PAGE_LOAD
    if bytes(blob[fm_entry_local:fm_entry_local + len(FM_WRITE_ORIGINAL)]) != FM_WRITE_ORIGINAL:
        raise RebuildError(f"{label}: unexpected relocated YM2413 writer")
    fm_delay_local = FM_WRITE_DELAY_ROUTINE - PAGE_LOAD
    if any(blob[fm_delay_local:fm_delay_local + len(FM_WRITE_DELAY_BYTES)]):
        raise RebuildError(f"{label}: delayed YM2413 writer destination is not free")
    blob[fm_delay_local:fm_delay_local + len(FM_WRITE_DELAY_BYTES)] = FM_WRITE_DELAY_BYTES
    blob[fm_entry_local:fm_entry_local + len(FM_WRITE_ORIGINAL)] = (
        bytes((0xC3, FM_WRITE_DELAY_ROUTINE & 0xFF, FM_WRITE_DELAY_ROUTINE >> 8))
        + bytes(len(FM_WRITE_ORIGINAL) - 3)
    )

    play_local = PLAY_DISPATCHER_ADDRESS - PAGE_LOAD
    if bytes(blob[play_local:play_local + 2]) != b"\xFB\xC9":
        raise RebuildError(f"{label}: PLAY dispatcher is not EI;RET in source")
    blob[play_local] = 0xF3  # DI;RET prevents the dispatcher from reopening IRQs.

    init_local = INIT_ADDRESS - PAGE_LOAD
    if any(blob[init_local:init_local + len(INIT_WRAPPER)]):
        raise RebuildError(f"{label}: page-1 INIT wrapper destination is not free")
    blob[init_local:init_local + len(INIT_WRAPPER)] = INIT_WRAPPER
    return bytes(blob)


def sparse_overlay(template: bytes, page: bytes) -> bytes:
    if len(template) != len(page):
        raise RebuildError("template/page size mismatch")
    records = bytearray()
    index = 0
    while index < len(page):
        if page[index] == template[index]:
            index += 1
            continue
        start = index
        while index < len(page) and page[index] != template[index]:
            index += 1
        count = index - start
        if start > 0xFFFF or count > 0xFFFF:
            raise RebuildError("sparse record exceeds KSP field width")
        records += struct.pack("<HH", start, count)
        records += page[start:index]
    return bytes(records)


def build_package(source_path: Path, output_path: Path) -> dict:
    source, source_template, source_pages = decode_source(source_path)
    relocated_template = relocate_runtime(source_template, "template")
    relocated_pages = [relocate_runtime(page, f"page {index}") for index, page in enumerate(source_pages)]

    # The wrapper lives in the invariant runtime gap and therefore must be
    # identical on every reconstructed page.
    init_local = INIT_ADDRESS - PAGE_LOAD
    for index, page in enumerate(relocated_pages):
        if page[init_local:init_local + len(INIT_WRAPPER)] != relocated_template[
            init_local:init_local + len(INIT_WRAPPER)
        ]:
            raise RebuildError(f"page {index}: overlay overlaps the INIT wrapper")

    page_overlays = [sparse_overlay(relocated_template, page) for page in relocated_pages]
    page_count = len(page_overlays)
    engine = bytearray(source[80:144])
    struct.pack_into("<HHHHH", engine, 0x0C, PAGE_LOAD, RUNTIME_SIZE,
                     INIT_ADDRESS, PLAY_ADDRESS, 0)
    struct.pack_into("<H", engine, 0x18, PAGE_LOAD)
    engine[0x20] = 0  # NONE
    struct.pack_into("<I", engine, 0x24, 9158)
    struct.pack_into("<I", engine, 0x28, len(relocated_template))
    struct.pack_into("<I", engine, 0x2C, len(relocated_template))
    struct.pack_into("<I", engine, 0x30, crc32(relocated_template))

    page_table = bytearray(page_count * 24)
    track_off = 144 + page_count * 24
    track_count = u16(source, 0x24)
    track_size = u16(source, 0x26)
    track_table = source[u32(source, 0x20):u32(source, 0x20) + track_count * track_size]
    resource_off = track_off + len(track_table)
    resource_count = u16(source, 0x2C)
    resource_size = u16(source, 0x2E)
    resource_table = bytearray(
        source[u32(source, 0x28):u32(source, 0x28) + resource_count * resource_size]
    )
    string_off = u32(source, 0x30)
    string_size = u32(source, 0x34)
    strings = source[string_off:string_off + string_size]
    index_end = string_off + string_size
    template_off = index_end
    cursor = template_off + len(relocated_template)

    for index, overlay in enumerate(page_overlays):
        payload_off = cursor
        cursor += len(overlay)
        struct.pack_into("<HBBHHIIII", page_table, index * 24,
                         0, 0, 0, 0, 0, payload_off, len(overlay),
                         len(overlay), crc32(relocated_pages[index]))

    # Preserve the source META logical payload and metadata, moving only its
    # file offset because the rebuilt template/pages have different sizes.
    if resource_count != 1 or resource_table[:4] != b"META":
        raise RebuildError("expected exactly one META resource")
    resource_payload_off = u32(resource_table, 8)
    resource_payload_size = u32(resource_table, 12)
    resource_payload = source[resource_payload_off:resource_payload_off + resource_payload_size]
    if len(resource_payload) != resource_payload_size:
        raise RebuildError("META payload outside source file")
    struct.pack_into("<I", resource_table, 8, cursor)
    struct.pack_into("<I", resource_table, 0x14, crc32(resource_payload))
    cursor += len(resource_payload)

    header = bytearray(source[:80])
    struct.pack_into("<I", header, 0x0C, cursor)
    struct.pack_into("<I", header, 0x40, 0)
    struct.pack_into("<I", header, 0x44, 0)
    index_bytes = bytes(engine) + bytes(page_table) + track_table + bytes(resource_table) + strings
    struct.pack_into("<I", header, 0x44, crc32(index_bytes))
    struct.pack_into("<I", header, 0x40, crc32(header))
    output = bytes(header) + index_bytes + relocated_template
    for overlay in page_overlays:
        output += overlay
    output += resource_payload
    if len(output) != cursor:
        raise RebuildError("internal output cursor mismatch")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output)

    report = {
        "source": str(source_path),
        "output": str(output_path),
        "file_size": len(output),
        "runtime": {
            "source_range": "C000-FFFF",
            "destination_range": "4000-7FFF",
            "delta": "-8000h",
            "init": f"{INIT_ADDRESS:04X}",
            "play": f"{PLAY_ADDRESS:04X}",
            "play_dispatcher": f"{PLAY_DISPATCHER_ADDRESS:04X}=DI;RET",
        },
        "relocation": {
            "direct_instruction_words": len(DIRECT_POINTERS),
            "pointer_table_words": sum(len(t) for _, t in TABLE_POINTERS),
            "data_pointer_words": len(DATA_POINTERS),
            "workspace_words_redirected": [
                {
                    "site": f"{site:04X}",
                    "source_target": f"{SOURCE_WORKSPACE:04X}",
                    "relocated_target": f"{ZERO_WORKSPACE_SENTINEL:04X}",
                }
                for site in WORKSPACE_POINTERS
            ],
            "ym2413_writer": {
                "entry": f"{FM_WRITE_ENTRY:04X}",
                "delayed_routine": f"{FM_WRITE_DELAY_ROUTINE:04X}",
                "address_delay_djnz": 16,
                "data_delay_djnz": 64,
            },
        },
        "pages": {
            "count": page_count,
            "template_crc32": f"{crc32(relocated_template):08X}",
            "page_crc32": [f"{crc32(page):08X}" for page in relocated_pages],
            "maximum_sparse_payload": max((len(x) for x in page_overlays), default=0),
        },
        "init_wrapper": {
            "bytes": INIT_WRAPPER.hex().upper(),
            "behavior": (
                "Select the original Fray FM-PAC bank 7Fh through port FEh, call "
                "relocated Fray dispatch with A=3, then tail-call it with A=2. "
                "It performs no DOS page-3 access."
            ),
        },
        "validation": {
            "source_aware_map_applied": True,
            "all_page_crc_fields_recomputed": True,
            "header_crc_recomputed": True,
            "index_crc_recomputed": True,
            "resource_crc_recomputed": True,
            "page3_accesses_in_wrapper": False,
            "init_wrapper_overlays": False,
            "mutable_state_targets": "player-owned page-1 runtime",
            "init_clear": {
                "dispatch": "A=3 -> 4E5D -> 4ECD",
                "clear_range": "580D-5AA4",
                "verified": True,
            },
        },
    }
    return report


def validate_output(path: Path, source_path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != b"KSP1" or u16(data, 4) != 80:
        raise RebuildError("output is not KSP1 1.0")
    if u32(data, 0x0C) != len(data):
        raise RebuildError("output file-size mismatch")
    if crc32(data[:0x40] + b"\x00\x00\x00\x00" + data[0x44:0x50]) != u32(data, 0x40):
        raise RebuildError("output header CRC mismatch")
    engine = data[80:144]
    if (u16(engine, 0x0C), u16(engine, 0x0E), u16(engine, 0x10), u16(engine, 0x12)) != (
        PAGE_LOAD, RUNTIME_SIZE, INIT_ADDRESS, PLAY_ADDRESS
    ):
        raise RebuildError("output engine profile mismatch")
    template_off, template_size = u32(engine, 0x24), u32(engine, 0x2C)
    template = data[template_off:template_off + template_size]
    if len(template) != RUNTIME_SIZE or crc32(template) != u32(engine, 0x30):
        raise RebuildError("output template CRC/size mismatch")
    _, source_template, source_pages = decode_source(source_path)
    expected_template = relocate_runtime(source_template, "output comparison template")
    expected_pages = [
        relocate_runtime(page, f"output comparison page {index}")
        for index, page in enumerate(source_pages)
    ]
    if template != expected_template:
        raise RebuildError("output template differs from source-aware relocation")
    index_bytes = data[80:144] + data[144:144 + u16(data, 0x1C) * 24]
    track_off = u32(data, 0x20)
    index_bytes += data[track_off:track_off + u16(data, 0x24) * u16(data, 0x26)]
    resource_off = u32(data, 0x28)
    resource_table = data[resource_off:resource_off + u16(data, 0x2C) * u16(data, 0x2E)]
    index_bytes += resource_table
    for index in range(u16(data, 0x2C)):
        resource = resource_table[index * u16(data, 0x2E):(index + 1) * u16(data, 0x2E)]
        payload = data[u32(resource, 8):u32(resource, 8) + u32(resource, 12)]
        if len(payload) != u32(resource, 12) or crc32(payload) != u32(resource, 0x14):
            raise RebuildError(f"output resource {index}: CRC mismatch")
    string_off, string_size = u32(data, 0x30), u32(data, 0x34)
    index_bytes += data[string_off:string_off + string_size]
    if crc32(index_bytes) != u32(data, 0x44):
        raise RebuildError("output index CRC mismatch")

    pages = []
    page_count = u16(data, 0x1C)
    for index in range(page_count):
        entry = data[144 + index * 24:144 + (index + 1) * 24]
        if entry[2:4] != b"\x00\x00" or u16(entry, 4) != 0:
            raise RebuildError(f"output page {index}: unsupported encoding")
        raw = data[u32(entry, 8):u32(entry, 8) + u32(entry, 12)]
        page = bytearray(template)
        cursor = 0
        previous_end = 0
        while cursor < len(raw):
            destination, count = struct.unpack_from("<HH", raw, cursor)
            cursor += 4
            if not count or destination < previous_end or destination + count > len(page):
                raise RebuildError(f"output page {index}: invalid sparse record")
            page[destination:destination + count] = raw[cursor:cursor + count]
            cursor += count
            previous_end = destination + count
        page = bytes(page)
        if crc32(page) != u32(entry, 20):
            raise RebuildError(f"output page {index}: page CRC mismatch")
        pages.append(page)

    old_runtime_words = []
    for index, page in enumerate([template, *pages]):
        for address, expected in DIRECT_POINTERS:
            local = address - SOURCE_RUNTIME_BASE
            for delta in (1, 2):
                if u16(page, local + delta) == expected:
                    old_runtime_words.append((index, address, expected))
        for start, targets in TABLE_POINTERS:
            stride = 3 if start == 0xD134 else 2
            for offset, expected in enumerate(targets):
                if u16(page, start - SOURCE_RUNTIME_BASE + offset * stride) == expected:
                    old_runtime_words.append((index, start + offset * stride, expected))
        for address, expected in DATA_POINTERS:
            if u16(page, address - SOURCE_RUNTIME_BASE) == expected:
                old_runtime_words.append((index, address, expected))
    if old_runtime_words:
        raise RebuildError(f"old runtime pointers remain: {old_runtime_words[:5]}")
    if template[PLAY_DISPATCHER_ADDRESS - PAGE_LOAD:PLAY_DISPATCHER_ADDRESS - PAGE_LOAD + 2] != b"\xF3\xC9":
        raise RebuildError("output PLAY dispatcher is not DI;RET")
    init_local = INIT_ADDRESS - PAGE_LOAD
    if template[init_local:init_local + len(INIT_WRAPPER)] != INIT_WRAPPER:
        raise RebuildError("output INIT wrapper mismatch")
    if pages != expected_pages:
        for index, (actual, expected) in enumerate(zip(pages, expected_pages)):
            if actual != expected:
                raise RebuildError(f"output page {index} differs from source-aware relocation")
        raise RebuildError("output page count differs from source-aware relocation")
    for index, page in enumerate(pages):
        if page[init_local:init_local + len(INIT_WRAPPER)] != INIT_WRAPPER:
            raise RebuildError(f"output page {index}: INIT wrapper mismatch")
    clear_local = 0x4ECD - PAGE_LOAD
    if template[clear_local:clear_local + len(INIT_CLEAR_BYTES)] != INIT_CLEAR_BYTES:
        raise RebuildError("relocated INIT clear sequence mismatch")
    return {
        "file": str(path),
        "bytes": len(data),
        "pages": len(pages),
        "all_page_crcs_valid": True,
        "template_crc_valid": True,
        "header_crc_valid": True,
        "index_crc_valid": True,
        "resource_crcs_valid": True,
        "reviewed_old_runtime_pointers": 0,
        "source_aware_page_comparison": True,
        "play_dispatcher": f"{PLAY_DISPATCHER_ADDRESS:04X}=DI;RET",
        "init_clear_sequence": "580D-5AA4",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = build_package(args.source, args.output)
    report["output_validation"] = validate_output(args.output, args.source)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"{args.output.name}: rebuilt {report['pages']['count']} pages, "
        f"template CRC {report['pages']['template_crc32']}, "
        f"max sparse payload {report['pages']['maximum_sparse_payload']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
