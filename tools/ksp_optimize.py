#!/usr/bin/env python3
"""KSP 1.00/1.01 page-storage optimizer.

Reads standalone KSP 1.00/1.01 packages, materializes pages from every standardized
page representation, and rebuilds the package using the smallest tested valid
strategy. Supported input page encodings:

  0 SPARSE_OVERLAY
  1 COMPLETE
  2 SHARED_BLOCK_MAP (PBM1/PBLK/PBK1)
  3 RESOURCE_MAP (RMP1 with NONE/ZX0/KZB1 sources)
  4 HYBRID_POOL (HPOL/HPL1)

The optimizer tests simple sparse/complete pages, PBLK, resource-map DATA, and
HPOL candidates. Non-page resources are preserved byte-for-byte. Obsolete
PBLK, HPOL and page-only DATA resources are removed and resource references are
renumbered safely.

A deterministic pure-Python forward ZX0 codec is included for desktop-format
work. The native MSX profile requires the reference encoder used by the MSX
runtime; it is auto-detected from the bundled Mac-player build or may be passed
with --zx0 /path/to/zx0pack.
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

NULL16 = 0xFFFF
NULL32 = 0xFFFFFFFF
KSP_HEADER_SIZE = 80
ENGINE_SIZE = 64
PAGE_SIZE_ENTRY = 24
TRACK_SIZE = 32
RESOURCE_SIZE = 32

COMP_NONE = 0
COMP_ZX0 = 1
COMP_ZX0_BLOCKS = 2

PAGE_SPARSE = 0
PAGE_COMPLETE = 1
PAGE_PBLK = 2
PAGE_RMAP = 3
PAGE_HPOL = 4
PAGE_BASE_ZERO = 1

RES_REQUIRED = 1
RES_STREAMABLE = 2
RES_PAGE_SOURCE = 4

RMAP_COPY_RESOURCE = 0
RMAP_COPY_INLINE = 1
RMAP_FILL = 2


class KSPError(ValueError):
    pass


def u8(data: bytes | bytearray, offset: int) -> int:
    if offset < 0 or offset >= len(data):
        raise KSPError(f"u8 outside data at 0x{offset:X}")
    return data[offset]


def u16(data: bytes | bytearray, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise KSPError(f"u16 outside data at 0x{offset:X}")
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise KSPError(f"u32 outside data at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def crc32(data: bytes | bytearray) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_slice(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise KSPError(
            f"{label} outside file: offset=0x{offset:X}, size=0x{size:X}, file=0x{len(data):X}"
        )
    return data[offset:offset + size]


def fmt_size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.2f} KiB"
    return f"{value / (1024 * 1024):.2f} MiB"


# ---------------------------------------------------------------------------
# Forward ZX0 codec
# ---------------------------------------------------------------------------

def zx0_decompress(inp: bytes, outsize: int) -> bytes:
    idx = 0
    bit_mask = 0
    bit_value = 0
    last_byte = 0
    backtrack = False
    out = bytearray()

    def read_byte() -> int:
        nonlocal idx, last_byte
        if idx >= len(inp):
            raise KSPError("truncated ZX0 stream")
        last_byte = inp[idx]
        idx += 1
        return last_byte

    def read_bit() -> int:
        nonlocal backtrack, bit_mask, bit_value
        if backtrack:
            backtrack = False
            return last_byte & 1
        if bit_mask == 0:
            bit_value = read_byte()
            bit_mask = 0x80
        value = 1 if bit_value & bit_mask else 0
        bit_mask >>= 1
        return value

    def gamma(invert: int) -> int:
        value = 1
        while not read_bit():
            value = (value << 1) | (read_bit() ^ invert)
        return value

    def literals(count: int) -> None:
        if count < 0 or count > outsize - len(out):
            raise KSPError("ZX0 literal output exceeds declared size")
        for _ in range(count):
            out.append(read_byte())

    def copy(offset: int, count: int) -> None:
        if offset <= 0 or offset > len(out):
            raise KSPError(f"invalid ZX0 offset {offset}")
        if count < 0 or count > outsize - len(out):
            raise KSPError("ZX0 match output exceeds declared size")
        for _ in range(count):
            out.append(out[-offset])

    offset = 1
    literals(gamma(0))
    while True:
        branch = read_bit()
        if not branch:
            copy(offset, gamma(0))
            branch = read_bit()
            if not branch:
                literals(gamma(0))
                continue
        while True:
            msb = gamma(1)
            if msb == 256:
                if len(out) != outsize:
                    raise KSPError(f"ZX0 size mismatch {len(out)} != {outsize}")
                return bytes(out)
            lsb = read_byte()
            offset = msb * 128 - (lsb >> 1)
            backtrack = True
            copy(offset, gamma(0) + 1)
            branch = read_bit()
            if not branch:
                literals(gamma(0))
                break


def gamma_bits(value: int, invert: int) -> list[int]:
    if value <= 0:
        raise KSPError("ZX0 gamma value must be positive")
    result: list[int] = []
    for digit in bin(value)[3:]:
        result.extend((0, (ord(digit) - 48) ^ invert))
    result.append(1)
    return result


class ZX0Writer:
    def __init__(self) -> None:
        self.output = bytearray()
        self.control_position = -1
        self.control_bit = 8

    def bit(self, value: int) -> None:
        if self.control_bit == 8:
            self.control_position = len(self.output)
            self.output.append(0)
            self.control_bit = 0
        if value:
            self.output[self.control_position] |= 1 << (7 - self.control_bit)
        self.control_bit += 1

    def bits(self, values: Iterable[int]) -> None:
        for value in values:
            self.bit(value)

    def byte(self, value: int) -> None:
        self.output.append(value & 0xFF)

    def data(self, values: bytes) -> None:
        self.output.extend(values)


def zx0_tokens(
    raw: bytes,
    minimum_match: int = 4,
    maximum_candidates: int = 96,
    maximum_offset: int = 32640,
) -> list[tuple]:
    table: dict[bytes, list[int]] = defaultdict(list)
    tokens: list[tuple] = []
    literal_start = 0
    position = 0
    size = len(raw)

    def add(index: int) -> None:
        if index + 2 >= size:
            return
        key = raw[index:index + 3]
        candidates = table[key]
        candidates.append(index)
        if len(candidates) > maximum_candidates * 4:
            cutoff = index - maximum_offset
            candidates[:] = [x for x in candidates if x >= cutoff][-maximum_candidates * 2:]

    while position < size:
        best_length = 0
        best_offset = 0
        if position + 2 < size:
            candidates = table.get(raw[position:position + 3], ())
            for candidate in reversed(candidates[-maximum_candidates:]):
                offset = position - candidate
                if not 1 <= offset <= maximum_offset:
                    continue
                limit = min(size - position, 0xFFFF)
                length = 3
                while length < limit and raw[candidate + length] == raw[position + length]:
                    length += 1
                if length > best_length:
                    best_length = length
                    best_offset = offset
                    if length >= 1024:
                        break
        if best_length >= minimum_match:
            if literal_start < position:
                tokens.append(("literal", raw[literal_start:position]))
            tokens.append(("match", best_offset, best_length))
            for index in range(position, min(size, position + best_length)):
                add(index)
            position += best_length
            literal_start = position
        else:
            add(position)
            position += 1
    if literal_start < size:
        tokens.append(("literal", raw[literal_start:]))
    if not tokens:
        return []
    if tokens[0][0] != "literal":
        raise KSPError("internal ZX0 tokenization error")
    return tokens


def zx0_compress_python(raw: bytes, maximum_offset: int = 32640) -> bytes:
    if not raw:
        return b""
    tokens = zx0_tokens(raw, maximum_offset=maximum_offset)
    if not tokens:
        return b""
    writer = ZX0Writer()
    first = tokens[0][1]
    writer.bits(gamma_bits(len(first), 0))
    writer.data(first)
    previous = "literal"
    for token in tokens[1:]:
        if token[0] == "literal":
            if previous != "match":
                raise KSPError("adjacent ZX0 literal tokens")
            literal = token[1]
            writer.bit(0)
            writer.bits(gamma_bits(len(literal), 0))
            writer.data(literal)
            previous = "literal"
            continue
        writer.bit(1)
        _, offset, length = token
        msb = (offset + 127) // 128
        remainder = msb * 128 - offset
        length_bits = gamma_bits(length - 1, 0)
        writer.bits(gamma_bits(msb, 1))
        writer.byte((remainder << 1) | length_bits[0])
        writer.bits(length_bits[1:])
        previous = "match"
    writer.bit(1)
    writer.bits(gamma_bits(256, 1))
    packed = bytes(writer.output)
    if zx0_decompress(packed, len(raw)) != raw:
        raise KSPError("ZX0 compressor round-trip failed")
    return packed


class ZX0Codec:
    def __init__(self, executable: Optional[Path] = None) -> None:
        self.executable = executable
        self.cache: dict[tuple[bytes, int], bytes] = {}

    def compress(self, raw: bytes, maximum_offset: int = 32640) -> bytes:
        if not raw:
            return b""
        key = (hashlib.sha256(raw).digest(), maximum_offset)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if self.executable is not None and maximum_offset == 32640:
            with tempfile.TemporaryDirectory(prefix="ksp-zx0-") as tmp:
                source = Path(tmp) / "input.bin"
                target = Path(tmp) / "output.zx0"
                source.write_bytes(raw)
                completed = subprocess.run(
                    [str(self.executable), str(source), str(target)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if completed.returncode != 0 or not target.exists():
                    message = completed.stderr.decode("utf-8", errors="replace").strip()
                    raise KSPError(f"external zx0 failed: {message or completed.returncode}")
                packed = target.read_bytes()
        else:
            packed = zx0_compress_python(raw, maximum_offset=maximum_offset)
        if zx0_decompress(packed, len(raw)) != raw:
            raise KSPError("ZX0 output failed round-trip verification")
        self.cache[key] = packed
        return packed

    def best_object(self, raw: bytes) -> tuple[int, bytes]:
        if not raw:
            return COMP_NONE, b""
        packed = self.compress(raw)
        return (COMP_ZX0, packed) if len(packed) < len(raw) else (COMP_NONE, raw)


# ---------------------------------------------------------------------------
# Parsed KSP structures
# ---------------------------------------------------------------------------
@dataclass
class Header:
    minor: int
    flags: int
    default_track: int
    meta_resource: int
    cover_resource: int
    strings: bytes


@dataclass
class Engine:
    flags: int
    hardware: int
    abi: int
    tick_hz: int
    load_address: int
    page_size: int
    init_address: int
    play_address: int
    stop_address: int
    gateway: int
    replace_start: int
    first_page: int
    page_count: int
    default_mwk: int
    first_bank: int
    bank_count: int
    bank_width: int
    name_offset: int
    template: bytes


@dataclass
class PageEntry:
    engine: int
    encoding: int
    compression: int
    flags: int
    offset: int
    packed_size: int
    unpacked_size: int
    final_crc: int


@dataclass
class Track:
    page: int
    song: int
    flags: int
    mwk: int
    image: int
    title_offset: int
    duration: int
    loop_start: int
    loop_end: int
    fade: int


@dataclass
class Resource:
    kind: bytes
    flags: int
    compression: int
    offset: int
    packed_size: int
    unpacked_size: int
    crc: int
    aux0: int
    aux1: int
    physical_payload: bytes


@dataclass
class ParsedKSP:
    source_path: Path
    raw: bytes
    header: Header
    engines: list[Engine]
    page_entries: list[PageEntry]
    pages: list[bytes]
    tracks: list[Track]
    resources: list[Resource]
    logical_resource_cache: dict[int, bytes] = field(default_factory=dict)
    pblk_cache: dict[int, tuple[int, list[bytes]]] = field(default_factory=dict)
    hpol_cache: Optional[dict] = None


# ---------------------------------------------------------------------------
# Input decoding
# ---------------------------------------------------------------------------

def decode_object(payload: bytes, compression: int, unpacked_size: int) -> bytes:
    if compression == COMP_NONE:
        if len(payload) != unpacked_size:
            raise KSPError(f"NONE size mismatch {len(payload)} != {unpacked_size}")
        return payload
    if compression == COMP_ZX0:
        return zx0_decompress(payload, unpacked_size)
    raise KSPError(f"ordinary object uses unsupported compression {compression}")


def decode_kzb1(payload: bytes, expected_size: int, expected_crc: int = 0) -> bytes:
    if len(payload) < 16 or payload[:4] != b"KZB1":
        raise KSPError("invalid KZB1 payload")
    header_size, block_count, total_size, table_offset = struct.unpack_from("<HHII", payload, 4)
    if header_size != 16 or total_size != expected_size:
        raise KSPError("invalid KZB1 header")
    checked_slice(payload, table_offset, block_count * 16, "KZB1 table")
    out = bytearray()
    for index in range(block_count):
        descriptor = table_offset + index * 16
        packed_offset, packed_size, raw_size, block_crc = struct.unpack_from(
            "<IIII", payload, descriptor
        )
        packed = checked_slice(payload, packed_offset, packed_size, f"KZB1 block {index}")
        raw = zx0_decompress(packed, raw_size)
        if block_crc and crc32(raw) != block_crc:
            raise KSPError(f"KZB1 block {index} CRC mismatch")
        out += raw
    if len(out) != expected_size:
        raise KSPError("KZB1 total size mismatch")
    result = bytes(out)
    if expected_crc and crc32(result) != expected_crc:
        raise KSPError("KZB1 resource CRC mismatch")
    return result


def decode_pblk_resource(resource: Resource) -> tuple[int, list[bytes]]:
    payload = resource.physical_payload
    if resource.compression != COMP_NONE or len(payload) < 32 or payload[:4] != b"PBK1":
        raise KSPError("invalid PBLK/PBK1 resource")
    (
        header_size,
        block_desc_size,
        slab_desc_size,
        block_size,
        block_count,
        slab_count,
        flags,
        block_table_offset,
        slab_table_offset,
        reserved,
    ) = struct.unpack_from("<HHHHIHHIII", payload, 4)
    if (
        header_size != 32
        or block_desc_size < 8
        or slab_desc_size < 16
        or block_size == 0
        or flags != 0
        or reserved != 0
        or resource.flags & RES_PAGE_SOURCE
    ):
        raise KSPError("invalid PBK1 header")
    if resource.unpacked_size != block_count * block_size:
        raise KSPError("PBLK logical size mismatch")
    checked_slice(payload, block_table_offset, block_count * block_desc_size, "PBK1 block table")
    checked_slice(payload, slab_table_offset, slab_count * slab_desc_size, "PBK1 slab table")
    slabs: list[bytes] = []
    for index in range(slab_count):
        offset = slab_table_offset + index * slab_desc_size
        packed_offset, packed_size, raw_size, compression, slab_flags, slab_crc = struct.unpack_from(
            "<IIHBBI", payload, offset
        )
        if slab_flags != 0 or raw_size == 0 or raw_size > 16384 or compression not in (0, 1):
            raise KSPError(f"invalid PBK1 slab {index}")
        packed = checked_slice(payload, packed_offset, packed_size, f"PBK1 slab {index}")
        raw = decode_object(packed, compression, raw_size)
        if slab_crc and crc32(raw) != slab_crc:
            raise KSPError(f"PBK1 slab {index} CRC mismatch")
        slabs.append(raw)
    blocks: list[bytes] = []
    for index in range(block_count):
        offset = block_table_offset + index * block_desc_size
        slab_index, source_offset, block_reserved = struct.unpack_from("<HHI", payload, offset)
        if block_reserved != 0 or slab_index >= len(slabs):
            raise KSPError(f"invalid PBK1 block descriptor {index}")
        slab = slabs[slab_index]
        if source_offset + block_size > len(slab):
            raise KSPError(f"PBK1 block {index} outside slab")
        blocks.append(slab[source_offset:source_offset + block_size])
    logical = b"".join(blocks)
    if resource.crc and crc32(logical) != resource.crc:
        raise KSPError("PBLK logical CRC mismatch")
    return block_size, blocks


def decode_hpol_resource(resource: Resource, global_page_count: int) -> dict:
    payload = resource.physical_payload
    if (
        resource.kind != b"HPOL"
        or resource.compression != COMP_NONE
        or (resource.flags & (RES_REQUIRED | RES_PAGE_SOURCE)) != (RES_REQUIRED | RES_PAGE_SOURCE)
        or len(payload) < 96
        or payload[:4] != b"HPL1"
    ):
        raise KSPError("invalid HPOL/HPL1 resource")
    fields = struct.unpack_from("<HHHHHHHHH", payload, 4)
    (
        header_size,
        version,
        block_size,
        position_count,
        page_count,
        hot_count,
        warm_count,
        cold_count,
        cold_slab_count,
    ) = fields
    flags = u16(payload, 0x16)
    if header_size != 96 or version != 1 or block_size == 0 or page_count != global_page_count or flags & ~1:
        raise KSPError("invalid HPL1 header fields")
    position_offset = u32(payload, 0x18)
    map_offset = u32(payload, 0x1C)
    map_packed_size = u32(payload, 0x20)
    map_raw_size = u32(payload, 0x24)
    hot_offset = u32(payload, 0x28)
    hot_packed_size = u32(payload, 0x2C)
    hot_raw_size = u32(payload, 0x30)
    warm_offset = u32(payload, 0x34)
    warm_packed_size = u32(payload, 0x38)
    warm_raw_size = u32(payload, 0x3C)
    cold_table_offset = u32(payload, 0x40)
    cold_data_offset = u32(payload, 0x44)
    cold_packed_total = u32(payload, 0x48)
    cold_raw_size = u32(payload, 0x4C)
    hot_crc = u32(payload, 0x50)
    warm_crc = u32(payload, 0x54)
    cold_crc = u32(payload, 0x58)
    map_crc = u32(payload, 0x5C)
    if (
        hot_raw_size != hot_count * block_size
        or warm_raw_size != warm_count * block_size
        or cold_raw_size != cold_count * block_size
        or map_raw_size != page_count * position_count * 2
        or resource.aux0 < hot_raw_size
        or resource.aux1 < warm_raw_size
    ):
        raise KSPError("HPL1 size equality mismatch")
    positions_raw = checked_slice(payload, position_offset, position_count * 2, "HPL1 positions")
    positions = list(struct.unpack_from(f"<{position_count}H", positions_raw, 0)) if position_count else []
    for a, b in zip(positions, positions[1:]):
        if a + block_size > b:
            raise KSPError("HPL1 destination positions overlap or are unordered")
    map_packed = checked_slice(payload, map_offset, map_packed_size, "HPL1 map stream")
    maps = zx0_decompress(map_packed, map_raw_size) if map_raw_size else b""
    if map_crc and crc32(maps) != map_crc:
        raise KSPError("HPL1 map CRC mismatch")
    if hot_raw_size:
        hot_packed = checked_slice(payload, hot_offset, hot_packed_size, "HPL1 hot stream")
        hot = zx0_decompress(hot_packed, hot_raw_size)
    else:
        hot = b""
    if warm_raw_size:
        warm_packed = checked_slice(payload, warm_offset, warm_packed_size, "HPL1 warm stream")
        warm = zx0_decompress(warm_packed, warm_raw_size)
    else:
        warm = b""
    if hot_crc and crc32(hot) != hot_crc:
        raise KSPError("HPL1 hot CRC mismatch")
    if warm_crc and crc32(warm) != warm_crc:
        raise KSPError("HPL1 warm CRC mismatch")
    checked_slice(payload, cold_table_offset, cold_slab_count * 16, "HPL1 cold slab table")
    cold = bytearray()
    packed_total = 0
    for index in range(cold_slab_count):
        offset = cold_table_offset + index * 16
        packed_offset, packed_size, raw_size, compression, slab_flags, slab_crc = struct.unpack_from(
            "<IIHBBI", payload, offset
        )
        if (
            raw_size == 0
            or raw_size > 16384
            or raw_size % block_size
            or compression not in (0, 1)
            or slab_flags != 0
        ):
            raise KSPError(f"invalid HPL1 cold slab {index}")
        packed = checked_slice(payload, packed_offset, packed_size, f"HPL1 cold slab {index}")
        raw = decode_object(packed, compression, raw_size)
        if slab_crc and crc32(raw) != slab_crc:
            raise KSPError(f"HPL1 cold slab {index} CRC mismatch")
        packed_total += packed_size
        cold += raw
    if len(cold) != cold_raw_size or packed_total != cold_packed_total:
        raise KSPError("HPL1 cold totals mismatch")
    if cold_crc and crc32(cold) != cold_crc:
        raise KSPError("HPL1 cold CRC mismatch")
    all_raw = hot + warm + bytes(cold)
    blocks = [all_raw[i:i + block_size] for i in range(0, len(all_raw), block_size)]
    if any(len(block) != block_size for block in blocks):
        raise KSPError("HPL1 block stream alignment mismatch")
    total_blocks = hot_count + warm_count + cold_count
    if len(blocks) != total_blocks:
        raise KSPError("HPL1 total block count mismatch")
    if maps:
        ids = struct.unpack_from(f"<{len(maps) // 2}H", maps, 0)
        if any(block_id >= total_blocks for block_id in ids):
            raise KSPError("HPL1 map contains invalid block ID")
    canonical = positions_raw + maps + hot + warm + bytes(cold)
    if resource.unpacked_size != len(canonical):
        raise KSPError("HPOL canonical logical size mismatch")
    if resource.crc and crc32(canonical) != resource.crc:
        raise KSPError("HPOL canonical CRC mismatch")
    return {
        "block_size": block_size,
        "positions": positions,
        "maps": maps,
        "blocks": blocks,
        "hot_count": hot_count,
        "warm_count": warm_count,
        "cold_count": cold_count,
        "canonical": canonical,
    }


def apply_sparse(template: bytes, overlay: bytes, *, allow_unordered: bool = False) -> bytes:
    page = bytearray(template)
    cursor = 0
    previous_end = 0
    while cursor < len(overlay):
        if cursor + 4 > len(overlay):
            raise KSPError("truncated sparse overlay")
        destination, count = struct.unpack_from("<HH", overlay, cursor)
        cursor += 4
        if (
            count == 0
            or (not allow_unordered and destination < previous_end)
            or destination + count > len(page)
            or cursor + count > len(overlay)
        ):
            raise KSPError("invalid sparse overlay record")
        page[destination:destination + count] = overlay[cursor:cursor + count]
        cursor += count
        previous_end = destination + count
    return bytes(page)


def relocate_bios_wrtpsg(package: ParsedKSP, destination: int) -> int:
    """Redirect direct BIOS WRTPSG calls to a page-local implementation."""
    stub = bytes.fromhex("f5 d3 a0 7b d3 a1 f1 c9")  # preserve AF; A=register, E=value
    patched = 0
    for engine_index, engine in enumerate(package.engines):
        start = destination - engine.load_address
        if start < 0 or start + len(stub) > engine.page_size:
            raise KSPError(f"WRTPSG destination is outside engine {engine_index}")
        page_range = range(engine.first_page, engine.first_page + engine.page_count)
        expected_sites: Optional[tuple[tuple[int, int], ...]] = None
        for page_index in page_range:
            page = bytearray(package.pages[page_index])
            sites = tuple(
                (offset, page[offset])
                for offset in range(len(page) - 2)
                if page[offset] in (0xCD, 0xC3) and page[offset + 1:offset + 3] == b"\x93\x00"
            )
            if expected_sites is None:
                expected_sites = sites
            elif sites != expected_sites:
                raise KSPError(f"engine {engine_index} WRTPSG sites differ between pages")
            if any(page[start:start + len(stub)]):
                raise KSPError(f"engine {engine_index} WRTPSG destination is not free")
            for offset, _opcode in sites:
                page[offset + 1:offset + 3] = struct.pack("<H", destination)
            page[start:start + len(stub)] = stub
            package.pages[page_index] = bytes(page)
        if expected_sites:
            patched += len(expected_sites)
            template = bytearray(engine.template)
            if any(template[start:start + len(stub)]):
                raise KSPError(f"engine {engine_index} template WRTPSG destination is not free")
            for offset, opcode in expected_sites:
                if template[offset] == opcode and template[offset + 1:offset + 3] == b"\x93\x00":
                    template[offset + 1:offset + 3] = struct.pack("<H", destination)
            template[start:start + len(stub)] = stub
            engine.template = bytes(template)
    if not patched:
        raise KSPError("no direct BIOS WRTPSG calls were found")
    return patched


def relocate_bios_rdvdp(package: ParsedKSP, destination: int) -> int:
    """Redirect direct BIOS RDVDP calls to a page-local status-port read."""
    stub = bytes.fromhex("db 99 c9")  # IN A,(99h); RET
    patched = 0
    for engine_index, engine in enumerate(package.engines):
        start = destination - engine.load_address
        if start < 0 or start + len(stub) > engine.page_size:
            raise KSPError(f"RDVDP destination is outside engine {engine_index}")
        expected_sites: Optional[tuple[tuple[int, int], ...]] = None
        for page_index in range(engine.first_page, engine.first_page + engine.page_count):
            page = bytearray(package.pages[page_index])
            sites = tuple(
                (offset, page[offset])
                for offset in range(len(page) - 2)
                if page[offset] in (0xCD, 0xC3) and page[offset + 1:offset + 3] == b"\x3e\x01"
            )
            if expected_sites is None:
                expected_sites = sites
            elif sites != expected_sites:
                raise KSPError(f"engine {engine_index} RDVDP sites differ between pages")
            if any(page[start:start + len(stub)]):
                raise KSPError(f"engine {engine_index} RDVDP destination is not free")
            for offset, _opcode in sites:
                page[offset + 1:offset + 3] = struct.pack("<H", destination)
            page[start:start + len(stub)] = stub
            package.pages[page_index] = bytes(page)
        if expected_sites:
            patched += len(expected_sites)
            template = bytearray(engine.template)
            if any(template[start:start + len(stub)]):
                raise KSPError(f"engine {engine_index} template RDVDP destination is not free")
            for offset, opcode in expected_sites:
                if template[offset] == opcode and template[offset + 1:offset + 3] == b"\x3e\x01":
                    template[offset + 1:offset + 3] = struct.pack("<H", destination)
            template[start:start + len(stub)] = stub
            engine.template = bytes(template)
    if not patched:
        raise KSPError("no direct BIOS RDVDP calls were found")
    return patched


def patch_ei_to_di(package: ParsedKSP, addresses: Sequence[int]) -> int:
    """Replace verified engine-local EI instructions with DI at call boundaries."""
    patched = 0
    for engine_index, engine in enumerate(package.engines):
        offsets = [address - engine.load_address for address in addresses]
        for address, offset in zip(addresses, offsets):
            if offset < 0 or offset >= engine.page_size:
                raise KSPError(f"EI address 0x{address:04X} is outside engine {engine_index}")
        for page_index in range(engine.first_page, engine.first_page + engine.page_count):
            page = bytearray(package.pages[page_index])
            for address, offset in zip(addresses, offsets):
                if page[offset] != 0xFB:
                    raise KSPError(f"engine {engine_index} page {page_index} has no EI at 0x{address:04X}")
                page[offset] = 0xF3
                patched += 1
            package.pages[page_index] = bytes(page)
        template = bytearray(engine.template)
        for offset in offsets:
            if template[offset] == 0xFB:
                template[offset] = 0xF3
        engine.template = bytes(template)
    return patched


def parse_ksp(path: Path, *, allow_legacy_sparse: bool = False) -> ParsedKSP:
    data = path.read_bytes()
    if len(data) < KSP_HEADER_SIZE or data[:4] != b"KSP1":
        raise KSPError("input is not standalone KSP 1.x")
    minor = u16(data, 6)
    if u16(data, 4) != 80 or minor > 1 or u32(data, 8) != 0:
        raise KSPError("unsupported KSP header version or flags")
    if u32(data, 12) != len(data):
        raise KSPError("KSP file-size field mismatch")
    header_copy = bytearray(data[:80])
    stored_header_crc = u32(header_copy, 64)
    struct.pack_into("<I", header_copy, 64, 0)
    if stored_header_crc and crc32(header_copy) != stored_header_crc:
        raise KSPError("KSP header CRC mismatch")

    engine_offset, engine_count, engine_entry_size = u32(data, 16), u16(data, 20), u16(data, 22)
    page_offset, page_count, page_entry_size = u32(data, 24), u16(data, 28), u16(data, 30)
    track_offset, track_count, track_entry_size = u32(data, 32), u16(data, 36), u16(data, 38)
    resource_offset, resource_count, resource_entry_size = u32(data, 40), u16(data, 44), u16(data, 46)
    string_offset, string_size = u32(data, 48), u32(data, 52)
    if (
        engine_entry_size < ENGINE_SIZE
        or page_entry_size < PAGE_SIZE_ENTRY
        or track_entry_size < TRACK_SIZE
        or resource_entry_size < RESOURCE_SIZE
    ):
        raise KSPError("KSP table entry size is below version-1 minimum")
    engine_table = checked_slice(data, engine_offset, engine_count * engine_entry_size, "engine table")
    page_table = checked_slice(data, page_offset, page_count * page_entry_size, "page table")
    track_table = checked_slice(data, track_offset, track_count * track_entry_size, "track table")
    resource_table = checked_slice(data, resource_offset, resource_count * resource_entry_size, "resource table")
    strings = checked_slice(data, string_offset, string_size, "string table")
    stored_index_crc = u32(data, 68)
    if stored_index_crc:
        compact_index = b"".join(
            [
                b"".join(engine_table[i * engine_entry_size:i * engine_entry_size + ENGINE_SIZE] for i in range(engine_count)),
                b"".join(page_table[i * page_entry_size:i * page_entry_size + PAGE_SIZE_ENTRY] for i in range(page_count)),
                b"".join(track_table[i * track_entry_size:i * track_entry_size + TRACK_SIZE] for i in range(track_count)),
                b"".join(resource_table[i * resource_entry_size:i * resource_entry_size + RESOURCE_SIZE] for i in range(resource_count)),
                strings,
            ]
        )
        if crc32(compact_index) != stored_index_crc:
            # The formal CRC covers complete table byte ranges including extended entries.
            full_index = engine_table + page_table + track_table + resource_table + strings
            if crc32(full_index) != stored_index_crc:
                raise KSPError("KSP index CRC mismatch")

    resources: list[Resource] = []
    for index in range(resource_count):
        entry = resource_table[index * resource_entry_size:index * resource_entry_size + RESOURCE_SIZE]
        kind = entry[:4]
        flags, compression, reserved, offset, packed, unpacked, expected_crc, aux0, aux1 = struct.unpack_from(
            "<HBBIIIIII", entry, 4
        )
        if reserved != 0 or flags & ~7 or compression not in (0, 1, 2):
            raise KSPError(f"invalid resource entry {index}")
        physical = checked_slice(data, offset, packed, f"resource {index}")
        resources.append(Resource(kind, flags, compression, offset, packed, unpacked, expected_crc, aux0, aux1, physical))

    meta_resource = u16(data, 58)
    if meta_resource != NULL16 and meta_resource >= len(resources):
        meta_candidates = [index for index, resource in enumerate(resources) if resource.kind == b"META"]
        if len(meta_candidates) != 1:
            raise KSPError("META resource index is outside the table and cannot be repaired unambiguously")
        meta_resource = meta_candidates[0]

    engines: list[Engine] = []
    for index in range(engine_count):
        entry = engine_table[index * engine_entry_size:index * engine_entry_size + ENGINE_SIZE]
        values = struct.unpack_from("<IIHHHHHHHHHHHHBBBBIIIII", entry, 0)
        (
            flags,
            hardware,
            abi,
            tick_hz,
            load_address,
            runtime_page_size,
            init_address,
            play_address,
            stop_address,
            gateway,
            replace_start,
            first_page,
            engine_page_count,
            default_mwk,
            compression,
            first_bank,
            bank_count,
            bank_width,
            template_offset,
            template_packed,
            template_unpacked,
            template_crc,
            name_offset,
        ) = values
        if flags & ~0x1F or (flags & 0x18 and minor < 1) or compression not in (0, 1) or runtime_page_size == 0:
            raise KSPError(f"invalid engine entry {index}")
        if flags & 0x08 and (load_address != 0x4000 or runtime_page_size != 0x4000 or hardware & 0x0E):
            raise KSPError(f"engine {index} has invalid KSP 1.01 page-2 runtime profile")
        template_payload = checked_slice(data, template_offset, template_packed, f"engine {index} template")
        template = decode_object(template_payload, compression, template_unpacked)
        if len(template) != runtime_page_size:
            raise KSPError(f"engine {index} template does not equal page size")
        if template_crc and crc32(template) != template_crc:
            raise KSPError(f"engine {index} template CRC mismatch")
        if first_page + engine_page_count > page_count:
            raise KSPError(f"engine {index} page range outside page table")
        engines.append(
            Engine(
                flags,
                hardware,
                abi,
                tick_hz,
                load_address,
                runtime_page_size,
                init_address,
                play_address,
                stop_address,
                gateway,
                replace_start,
                first_page,
                engine_page_count,
                default_mwk,
                first_bank,
                bank_count,
                bank_width,
                name_offset,
                template,
            )
        )

    page_entries: list[PageEntry] = []
    for index in range(page_count):
        entry = page_table[index * page_entry_size:index * page_entry_size + PAGE_SIZE_ENTRY]
        owner, encoding, compression, flags, reserved, offset, packed, unpacked, final_crc = struct.unpack(
            "<HBBHHIIII", entry
        )
        if reserved != 0 or owner >= len(engines) or encoding not in range(5):
            raise KSPError(f"invalid page entry {index}")
        if compression not in (0, 1):
            raise KSPError(f"page {index} has invalid compression")
        if encoding in (0, 1, 4) and flags != 0:
            raise KSPError(f"page {index} has invalid flags")
        if encoding in (2, 3) and flags & ~PAGE_BASE_ZERO:
            raise KSPError(f"page {index} has invalid base flags")
        page_entries.append(PageEntry(owner, encoding, compression, flags, offset, packed, unpacked, final_crc))

    tracks: list[Track] = []
    for index in range(track_count):
        entry = track_table[index * track_entry_size:index * track_entry_size + TRACK_SIZE]
        page, song, flags, mwk, image, reserved, title, duration, loop_start, loop_end, fade = struct.unpack(
            "<HHHHHHIIIII", entry
        )
        if reserved != 0 or page >= page_count or flags & ~0xF:
            raise KSPError(f"invalid track entry {index}")
        if title != NULL32:
            if title >= len(strings) or strings.find(b"\0", title) < 0:
                raise KSPError(f"invalid track title offset {index}")
        tracks.append(Track(page, song, flags, mwk, image, title, duration, loop_start, loop_end, fade))

    package = ParsedKSP(
        source_path=path,
        raw=data,
        header=Header(minor, u32(data, 8), u16(data, 56), meta_resource, u16(data, 60), strings),
        engines=engines,
        page_entries=page_entries,
        pages=[],
        tracks=tracks,
        resources=resources,
    )

    def logical_resource(index: int) -> bytes:
        cached = package.logical_resource_cache.get(index)
        if cached is not None:
            return cached
        if index >= len(resources):
            raise KSPError(f"resource index {index} outside table")
        resource = resources[index]
        if resource.kind == b"PBLK":
            block_size, blocks = package.pblk_cache.get(index, (0, []))
            if not blocks:
                block_size, blocks = decode_pblk_resource(resource)
                package.pblk_cache[index] = (block_size, blocks)
            result = b"".join(blocks)
        elif resource.kind == b"HPOL":
            if package.hpol_cache is None:
                package.hpol_cache = decode_hpol_resource(resource, page_count)
            result = package.hpol_cache["canonical"]
        elif resource.compression == COMP_NONE:
            result = decode_object(resource.physical_payload, COMP_NONE, resource.unpacked_size)
        elif resource.compression == COMP_ZX0:
            result = decode_object(resource.physical_payload, COMP_ZX0, resource.unpacked_size)
        elif resource.compression == COMP_ZX0_BLOCKS:
            result = decode_kzb1(resource.physical_payload, resource.unpacked_size, resource.crc)
        else:
            raise KSPError(f"resource {index} compression unsupported")
        if resource.crc and crc32(result) != resource.crc:
            raise KSPError(f"resource {index} CRC mismatch")
        package.logical_resource_cache[index] = result
        return result

    hpol_indices = [index for index, resource in enumerate(resources) if resource.kind == b"HPOL"]
    if len(hpol_indices) > 1:
        raise KSPError("more than one HPOL resource")
    if any(page.encoding == PAGE_HPOL for page in page_entries):
        if len(hpol_indices) != 1:
            raise KSPError("hybrid page without exactly one HPOL resource")
        package.hpol_cache = decode_hpol_resource(resources[hpol_indices[0]], page_count)

    pages: list[bytes] = []
    for index, page_entry in enumerate(page_entries):
        owner = engines[page_entry.engine]
        if not (owner.first_page <= index < owner.first_page + owner.page_count):
            raise KSPError(f"page {index} is outside owning engine range")
        template = owner.template
        payload = checked_slice(data, page_entry.offset, page_entry.packed_size, f"page {index} payload") if page_entry.packed_size else b""
        if page_entry.encoding == PAGE_SPARSE:
            raw = decode_object(payload, page_entry.compression, page_entry.unpacked_size)
            try:
                page = apply_sparse(template, raw, allow_unordered=allow_legacy_sparse)
            except KSPError as exc:
                raise KSPError(f"page {index}: {exc}") from exc
        elif page_entry.encoding == PAGE_COMPLETE:
            page = decode_object(payload, page_entry.compression, page_entry.unpacked_size)
        elif page_entry.encoding == PAGE_PBLK:
            raw = decode_object(payload, page_entry.compression, page_entry.unpacked_size)
            if len(raw) < 16 or raw[:4] != b"PBM1":
                raise KSPError(f"page {index} invalid PBM1")
            header_size, pool_index, record_count, record_size, reserved = struct.unpack_from("<HHHHI", raw, 4)
            if header_size != 16 or record_size < 12 or reserved != 0 or pool_index >= len(resources):
                raise KSPError(f"page {index} invalid PBM1 header")
            resource = resources[pool_index]
            if resource.kind != b"PBLK":
                raise KSPError(f"page {index} PBM1 does not reference PBLK")
            if pool_index not in package.pblk_cache:
                package.pblk_cache[pool_index] = decode_pblk_resource(resource)
            block_size, blocks = package.pblk_cache[pool_index]
            page_buffer = bytearray(b"\0" * owner.page_size if page_entry.flags & PAGE_BASE_ZERO else template)
            previous_end = 0
            checked_slice(raw, 16, record_count * record_size, f"page {index} PBM1 records")
            for record in range(record_count):
                offset = 16 + record * record_size
                destination, count, block_index, source_offset, record_reserved = struct.unpack_from(
                    "<HHIHH", raw, offset
                )
                if (
                    record_reserved != 0
                    or count == 0
                    or destination < previous_end
                    or destination + count > owner.page_size
                    or block_index >= len(blocks)
                    or source_offset + count > block_size
                ):
                    raise KSPError(f"page {index} invalid PBM1 record")
                page_buffer[destination:destination + count] = blocks[block_index][source_offset:source_offset + count]
                previous_end = destination + count
            page = bytes(page_buffer)
        elif page_entry.encoding == PAGE_RMAP:
            raw = decode_object(payload, page_entry.compression, page_entry.unpacked_size)
            if len(raw) < 16 or raw[:4] != b"RMP1":
                raise KSPError(f"page {index} invalid RMP1")
            header_size, record_count, record_size, map_flags, reserved = struct.unpack_from("<HHHHI", raw, 4)
            if header_size != 16 or record_size < 16 or map_flags != 0 or reserved != 0:
                raise KSPError(f"page {index} invalid RMP1 header")
            checked_slice(raw, 16, record_count * record_size, f"page {index} RMP1 records")
            page_buffer = bytearray(b"\0" * owner.page_size if page_entry.flags & PAGE_BASE_ZERO else template)
            previous_end = 0
            for record in range(record_count):
                offset = 16 + record * record_size
                destination, count, record_type, record_flags, resource_index, source_offset, record_reserved = struct.unpack_from(
                    "<HHBBHII", raw, offset
                )
                if (
                    record_flags != 0
                    or record_reserved != 0
                    or count == 0
                    or destination < previous_end
                    or destination + count > owner.page_size
                ):
                    raise KSPError(f"page {index} invalid RMP1 record")
                if record_type == RMAP_COPY_RESOURCE:
                    if resource_index >= len(resources) or not (resources[resource_index].flags & RES_PAGE_SOURCE):
                        raise KSPError(f"page {index} invalid RMP1 resource")
                    source = logical_resource(resource_index)
                    if source_offset + count > len(source):
                        raise KSPError(f"page {index} RMP1 resource range outside source")
                    values = source[source_offset:source_offset + count]
                elif record_type == RMAP_COPY_INLINE:
                    if resource_index != NULL16 or source_offset < 16 + record_count * record_size or source_offset + count > len(raw):
                        raise KSPError(f"page {index} invalid inline RMP1 range")
                    values = raw[source_offset:source_offset + count]
                elif record_type == RMAP_FILL:
                    if resource_index != NULL16 or source_offset > 0xFF:
                        raise KSPError(f"page {index} invalid RMP1 fill")
                    values = bytes([source_offset]) * count
                else:
                    raise KSPError(f"page {index} unknown RMP1 record type")
                page_buffer[destination:destination + count] = values
                previous_end = destination + count
            page = bytes(page_buffer)
        else:
            if page_entry.compression != 0 or page_entry.flags != 0 or page_entry.offset != 0 or page_entry.packed_size != 0 or page_entry.unpacked_size != 0:
                raise KSPError(f"page {index} invalid hybrid entry")
            if package.hpol_cache is None:
                raise KSPError("missing decoded HPOL")
            hpol = package.hpol_cache
            block_size = hpol["block_size"]
            positions = hpol["positions"]
            maps = hpol["maps"]
            row_offset = index * len(positions) * 2
            row = struct.unpack_from(f"<{len(positions)}H", maps, row_offset) if positions else ()
            page_buffer = bytearray(template)
            for destination, block_id in zip(positions, row):
                if destination + block_size > owner.page_size:
                    raise KSPError(f"page {index} hybrid destination outside page")
                page_buffer[destination:destination + block_size] = hpol["blocks"][block_id]
            page = bytes(page_buffer)
        if len(page) != owner.page_size:
            raise KSPError(f"page {index} reconstructed size mismatch")
        if page_entry.final_crc and crc32(page) != page_entry.final_crc:
            raise KSPError(f"page {index} final CRC mismatch")
        pages.append(page)
    package.pages = pages

    for index, engine in enumerate(engines):
        for page_index in range(engine.first_page, engine.first_page + engine.page_count):
            if page_entries[page_index].engine != index:
                raise KSPError(f"engine {index} page range ownership mismatch")
    for index, track in enumerate(tracks):
        for field_name, resource_index in (("MWK", track.mwk), ("IMG5", track.image)):
            if resource_index != NULL16 and resource_index >= len(resources):
                raise KSPError(f"track {index} invalid {field_name} resource")
    return package


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------
@dataclass
class OutputResource:
    kind: bytes
    flags: int
    compression: int
    physical: bytes
    unpacked_size: int
    crc: int
    aux0: int = 0
    aux1: int = 0
    source_old_index: Optional[int] = None


@dataclass
class PagePlan:
    encoding: int
    flags: int
    build_raw: Optional[Callable[[list[int]], bytes]]
    final_page: bytes
    label: str


@dataclass
class EnginePlan:
    engine_index: int
    name: str
    template: bytes
    page_plans: list[PagePlan]
    resources: list[OutputResource]
    stats: dict


@dataclass
class BuildPlan:
    name: str
    engine_plans: list[EnginePlan]
    global_resources: list[OutputResource] = field(default_factory=list)
    report: dict = field(default_factory=dict)


def modal_template_bytes(pages: Sequence[bytes]) -> bytes:
    if not pages:
        raise KSPError("cannot build a template from no pages")
    size = len(pages[0])
    if any(len(page) != size for page in pages):
        raise KSPError("page sizes differ inside one engine")
    output = bytearray(size)
    for position in range(size):
        output[position] = Counter(page[position] for page in pages).most_common(1)[0][0]
    return bytes(output)


def modal_template_blocks(pages: Sequence[bytes], block_size: int) -> bytes:
    if not pages:
        raise KSPError("cannot build a template from no pages")
    size = len(pages[0])
    output = bytearray(size)
    for position in range(0, size, block_size):
        count = min(block_size, size - position)
        values = Counter(page[position:position + count] for page in pages)
        output[position:position + count] = values.most_common(1)[0][0]
    return bytes(output)


def differing_ranges(template: bytes, page: bytes, merge_gap: int) -> list[tuple[int, int]]:
    if len(template) != len(page):
        raise KSPError("template/page size mismatch")
    positions = [index for index, (a, b) in enumerate(zip(template, page)) if a != b]
    if not positions:
        return []
    ranges: list[tuple[int, int]] = []
    start = previous = positions[0]
    for position in positions[1:]:
        if position - previous - 1 <= merge_gap:
            previous = position
        else:
            ranges.append((start, previous + 1))
            start = previous = position
    ranges.append((start, previous + 1))
    return ranges


def sparse_payload(template: bytes, page: bytes, merge_gap: int) -> bytes:
    output = bytearray()
    for start, end in differing_ranges(template, page, merge_gap):
        count = end - start
        if count > 0xFFFF:
            raise KSPError("sparse record exceeds 16-bit length")
        output += struct.pack("<HH", start, count)
        output += page[start:end]
    if apply_sparse(template, bytes(output)) != page:
        raise KSPError("generated sparse overlay failed verification")
    return bytes(output)


def choose_simple_page(codec: ZX0Codec, template: bytes, page: bytes, merge_gaps: Sequence[int]) -> PagePlan:
    candidates: list[tuple[int, int, bytes, str]] = []
    for gap in merge_gaps:
        raw = sparse_payload(template, page, gap)
        compression, packed = codec.best_object(raw)
        candidates.append((len(packed), PAGE_SPARSE, raw, f"sparse-gap{gap}"))
    compression, packed = codec.best_object(page)
    candidates.append((len(packed), PAGE_COMPLETE, page, "complete"))
    _, encoding, raw, label = min(candidates, key=lambda item: (item[0], item[1], item[3]))
    return PagePlan(encoding, 0, lambda _indices, raw=raw: raw, page, label)


def page_payload_size(codec: ZX0Codec, page_plan: PagePlan, resource_indices: list[int]) -> int:
    if page_plan.build_raw is None:
        return 0
    raw = page_plan.build_raw(resource_indices)
    return len(codec.best_object(raw)[1])


def build_simple_engine_plan(
    package: ParsedKSP,
    engine_index: int,
    codec: ZX0Codec,
    level: str,
) -> list[EnginePlan]:
    engine = package.engines[engine_index]
    pages = package.pages[engine.first_page:engine.first_page + engine.page_count]
    merge_gaps = (0, 4, 8, 16, 32) if level == "exhaustive" else ((0, 8, 24) if level == "normal" else (0, 12))
    templates: list[tuple[str, bytes]] = [("original", engine.template)]
    modal = modal_template_bytes(pages)
    if modal != engine.template:
        templates.append(("modal-bytes", modal))
    if level != "quick":
        block_modal = modal_template_blocks(pages, 256)
        if all(block_modal != value for _, value in templates):
            templates.append(("modal-256", block_modal))
    plans = []
    for template_name, template in templates:
        page_plans = [choose_simple_page(codec, template, page, merge_gaps) for page in pages]
        template_comp, template_packed = codec.best_object(template)
        page_bytes = sum(page_payload_size(codec, plan, []) for plan in page_plans)
        plans.append(
            EnginePlan(
                engine_index,
                f"simple:{template_name}",
                template,
                page_plans,
                [],
                {
                    "strategy": "simple",
                    "template": template_name,
                    "template_packed": len(template_packed),
                    "page_payload_packed": page_bytes,
                    "page_encodings": dict(Counter(plan.label for plan in page_plans)),
                    "estimated_storage": len(template_packed) + page_bytes,
                },
            )
        )
    return plans


def make_pbk1(codec: ZX0Codec, blocks: list[bytes], block_size: int, slab_size: int) -> tuple[bytes, dict]:
    if not blocks:
        raise KSPError("cannot build empty PBLK")
    if slab_size <= 0 or slab_size > 16384 or slab_size % block_size:
        raise KSPError("invalid PBLK slab size")
    per_slab = max(1, slab_size // block_size)
    slabs_raw = [b"".join(blocks[index:index + per_slab]) for index in range(0, len(blocks), per_slab)]
    slabs: list[tuple[int, bytes, bytes]] = []
    for raw in slabs_raw:
        compression, packed = codec.best_object(raw)
        slabs.append((compression, packed, raw))
    block_table_offset = 32
    slab_table_offset = block_table_offset + len(blocks) * 8
    data_offset = slab_table_offset + len(slabs) * 16
    output = bytearray(data_offset)
    output[:4] = b"PBK1"
    struct.pack_into(
        "<HHHHIHHIII",
        output,
        4,
        32,
        8,
        16,
        block_size,
        len(blocks),
        len(slabs),
        0,
        block_table_offset,
        slab_table_offset,
        0,
    )
    for block_index in range(len(blocks)):
        slab_index = block_index // per_slab
        source_offset = (block_index % per_slab) * block_size
        struct.pack_into("<HHI", output, block_table_offset + block_index * 8, slab_index, source_offset, 0)
    cursor = data_offset
    for slab_index, (compression, packed, raw) in enumerate(slabs):
        struct.pack_into(
            "<IIHBBI",
            output,
            slab_table_offset + slab_index * 16,
            cursor,
            len(packed),
            len(raw),
            compression,
            0,
            crc32(raw),
        )
        cursor += len(packed)
    for _, packed, _ in slabs:
        output += packed
    return bytes(output), {
        "block_size": block_size,
        "block_count": len(blocks),
        "slab_size": slab_size,
        "slab_count": len(slabs),
        "slab_raw": sum(len(raw) for _, _, raw in slabs),
        "slab_packed": sum(len(packed) for _, packed, _ in slabs),
        "container": len(output),
    }


def build_pblk_plan(
    package: ParsedKSP,
    engine_index: int,
    codec: ZX0Codec,
    template: bytes,
    block_size: int,
    slab_size: int,
    order_mode: str,
    merge_gaps: Sequence[int],
) -> Optional[EnginePlan]:
    engine = package.engines[engine_index]
    pages = package.pages[engine.first_page:engine.first_page + engine.page_count]
    active = set(range(len(pages)))
    final_plan: Optional[EnginePlan] = None
    for _iteration in range(3):
        occurrences: list[tuple[int, int, bytes, int]] = []
        page_rows: list[list[tuple[int, int, bytes]]] = [[] for _ in pages]
        for page_index in sorted(active):
            page = pages[page_index]
            for position in range(0, engine.page_size, block_size):
                count = min(block_size, engine.page_size - position)
                block = page[position:position + count]
                template_block = template[position:position + count]
                if block == template_block:
                    continue
                padded = block + b"\0" * (block_size - count)
                page_rows[page_index].append((position, count, padded))
                occurrences.append((page_index, position, padded, count))
        if not occurrences:
            return None
        frequency = Counter(block for _, _, block, _ in occurrences)
        if order_mode == "frequency":
            occurrences.sort(key=lambda item: (-frequency[item[2]], item[1], item[0]))
        elif order_mode == "position":
            occurrences.sort(key=lambda item: (item[1], item[0]))
        blocks: list[bytes] = []
        block_index_by_value: dict[bytes, int] = {}
        for _, _, block, _ in occurrences:
            if block not in block_index_by_value:
                block_index_by_value[block] = len(blocks)
                blocks.append(block)
        pbk1, pool_stats = make_pbk1(codec, blocks, block_size, slab_size)
        pool_resource = OutputResource(
            b"PBLK",
            RES_REQUIRED,
            COMP_NONE,
            pbk1,
            len(blocks) * block_size,
            crc32(b"".join(blocks)),
        )
        page_plans: list[PagePlan] = []
        new_active: set[int] = set()
        for page_index, page in enumerate(pages):
            simple = choose_simple_page(codec, template, page, merge_gaps)
            row = page_rows[page_index]
            if not row:
                page_plans.append(simple)
                continue

            def build_map(indices: list[int], row=row, index_by_value=block_index_by_value) -> bytes:
                resource_index = indices[0]
                raw = bytearray(16 + len(row) * 12)
                raw[:4] = b"PBM1"
                struct.pack_into("<HHHHI", raw, 4, 16, resource_index, len(row), 12, 0)
                for record_index, (destination, count, block) in enumerate(row):
                    struct.pack_into(
                        "<HHIHH",
                        raw,
                        16 + record_index * 12,
                        destination,
                        count,
                        index_by_value[block],
                        0,
                        0,
                    )
                return bytes(raw)

            pooled = PagePlan(PAGE_PBLK, 0, build_map, page, "pblk")
            pooled_size = page_payload_size(codec, pooled, [0])
            simple_size = page_payload_size(codec, simple, [])
            if pooled_size < simple_size:
                page_plans.append(pooled)
                new_active.add(page_index)
            else:
                page_plans.append(simple)
        if not new_active:
            return None
        plan = EnginePlan(
            engine_index,
            f"pblk:bs{block_size}:slab{slab_size}:{order_mode}",
            template,
            page_plans,
            [pool_resource],
            {
                "strategy": "pblk",
                "order": order_mode,
                **pool_stats,
                "pooled_pages": len(new_active),
            },
        )
        estimated = estimate_engine_plan(codec, plan, 0)
        plan.stats["estimated_storage"] = estimated
        final_plan = plan
        if new_active == active:
            break
        active = new_active
    return final_plan


def make_kzb1(codec: ZX0Codec, raw: bytes, block_limit: int = 16384) -> bytes:
    if not raw:
        raise KSPError("cannot build empty KZB1")
    blocks = [raw[index:index + block_limit] for index in range(0, len(raw), block_limit)]
    packed_blocks = [codec.compress(block) for block in blocks]
    table_offset = 16
    data_offset = table_offset + len(blocks) * 16
    output = bytearray(data_offset)
    output[:4] = b"KZB1"
    struct.pack_into("<HHII", output, 4, 16, len(blocks), len(raw), table_offset)
    cursor = data_offset
    for index, (block, packed) in enumerate(zip(blocks, packed_blocks)):
        struct.pack_into("<IIII", output, table_offset + index * 16, cursor, len(packed), len(block), crc32(block))
        cursor += len(packed)
    for packed in packed_blocks:
        output += packed
    return bytes(output)


def build_data_resource(codec: ZX0Codec, source: bytes) -> OutputResource:
    if not source:
        raise KSPError("empty DATA resource")
    if len(source) <= 16384:
        compression, physical = codec.best_object(source)
    else:
        compression, physical = COMP_ZX0_BLOCKS, make_kzb1(codec, source)
    return OutputResource(
        b"DATA",
        RES_REQUIRED | RES_PAGE_SOURCE,
        compression,
        physical,
        len(source),
        crc32(source),
    )


def build_rmap_plan(
    package: ParsedKSP,
    engine_index: int,
    codec: ZX0Codec,
    template: bytes,
    block_size: int,
    order_mode: str,
    merge_gaps: Sequence[int],
) -> Optional[EnginePlan]:
    engine = package.engines[engine_index]
    pages = package.pages[engine.first_page:engine.first_page + engine.page_count]
    active = set(range(len(pages)))
    final_plan: Optional[EnginePlan] = None
    for _iteration in range(3):
        occurrences: list[tuple[int, int, bytes, int]] = []
        rows: list[list[tuple[int, int, bytes, Optional[int]]]] = [[] for _ in pages]
        for page_index in sorted(active):
            page = pages[page_index]
            for position in range(0, engine.page_size, block_size):
                count = min(block_size, engine.page_size - position)
                block = page[position:position + count]
                if block == template[position:position + count]:
                    continue
                fill_value = block[0] if count >= 4 and all(value == block[0] for value in block) else None
                padded = block + b"\0" * (block_size - count)
                rows[page_index].append((position, count, padded, fill_value))
                if fill_value is None:
                    occurrences.append((page_index, position, padded, count))
        if not any(rows):
            return None
        frequency = Counter(block for _, _, block, _ in occurrences)
        if order_mode == "frequency":
            occurrences.sort(key=lambda item: (-frequency[item[2]], item[1], item[0]))
        elif order_mode == "position":
            occurrences.sort(key=lambda item: (item[1], item[0]))
        source = bytearray()
        source_offset: dict[bytes, int] = {}
        for _, _, block, _ in occurrences:
            if block not in source_offset:
                source_offset[block] = len(source)
                source += block
        data_resource = build_data_resource(codec, bytes(source)) if source else None
        page_plans: list[PagePlan] = []
        new_active: set[int] = set()
        for page_index, page in enumerate(pages):
            simple = choose_simple_page(codec, template, page, merge_gaps)
            row = rows[page_index]
            if not row:
                page_plans.append(simple)
                continue
            records: list[tuple[int, int, int, Optional[int], int]] = []
            for destination, count, block, fill_value in row:
                if fill_value is not None:
                    record = (destination, count, RMAP_FILL, None, fill_value)
                else:
                    record = (destination, count, RMAP_COPY_RESOURCE, 0, source_offset[block])
                if records:
                    previous = records[-1]
                    if (
                        previous[2] == record[2] == RMAP_COPY_RESOURCE
                        and previous[0] + previous[1] == destination
                        and previous[4] + previous[1] == record[4]
                    ):
                        records[-1] = (previous[0], previous[1] + count, previous[2], previous[3], previous[4])
                        continue
                    if (
                        previous[2] == record[2] == RMAP_FILL
                        and previous[0] + previous[1] == destination
                        and previous[4] == record[4]
                    ):
                        records[-1] = (previous[0], previous[1] + count, previous[2], previous[3], previous[4])
                        continue
                records.append(record)

            def build_map(indices: list[int], records=records, has_source=bool(source)) -> bytes:
                resource_index = indices[0] if has_source else NULL16
                raw = bytearray(16 + len(records) * 16)
                raw[:4] = b"RMP1"
                struct.pack_into("<HHHHI", raw, 4, 16, len(records), 16, 0, 0)
                for record_index, (destination, count, kind, _local, value) in enumerate(records):
                    actual_resource = resource_index if kind == RMAP_COPY_RESOURCE else NULL16
                    struct.pack_into(
                        "<HHBBHII",
                        raw,
                        16 + record_index * 16,
                        destination,
                        count,
                        kind,
                        0,
                        actual_resource,
                        value,
                        0,
                    )
                return bytes(raw)

            mapped = PagePlan(PAGE_RMAP, 0, build_map, page, "rmap")
            mapped_size = page_payload_size(codec, mapped, [0] if source else [])
            simple_size = page_payload_size(codec, simple, [])
            if mapped_size < simple_size:
                page_plans.append(mapped)
                new_active.add(page_index)
            else:
                page_plans.append(simple)
        if not new_active:
            return None
        resources = [data_resource] if data_resource is not None else []
        plan = EnginePlan(
            engine_index,
            f"rmap:bs{block_size}:{order_mode}",
            template,
            page_plans,
            resources,
            {
                "strategy": "resource-map",
                "block_size": block_size,
                "order": order_mode,
                "source_raw": len(source),
                "source_physical": len(data_resource.physical) if data_resource else 0,
                "mapped_pages": len(new_active),
            },
        )
        estimated = estimate_engine_plan(codec, plan, 0)
        plan.stats["estimated_storage"] = estimated
        final_plan = plan
        if new_active == active:
            break
        active = new_active
    return final_plan


def estimate_engine_plan(codec: ZX0Codec, plan: EnginePlan, resource_start: int) -> int:
    template_size = len(codec.best_object(plan.template)[1])
    resource_indices = list(range(resource_start, resource_start + len(plan.resources)))
    page_size = sum(page_payload_size(codec, page, resource_indices) for page in plan.page_plans)
    resource_size = sum(RESOURCE_SIZE + len(resource.physical) for resource in plan.resources)
    return template_size + page_size + resource_size


def candidate_parameters(level: str) -> tuple[list[int], list[int], list[str]]:
    if level == "quick":
        return [128, 256], [8192, 16384], ["first"]
    if level == "normal":
        return [64, 128, 256, 512], [8192, 16384], ["first", "frequency"]
    return [64, 128, 256, 512, 1024], [4096, 8192, 16384], ["first", "frequency", "position"]


def choose_engine_plan(
    package: ParsedKSP,
    engine_index: int,
    codec: ZX0Codec,
    level: str,
    base_resource_count: int,
) -> tuple[EnginePlan, list[dict]]:
    simple_plans = build_simple_engine_plan(package, engine_index, codec, level)
    candidates = list(simple_plans)
    block_sizes, slab_sizes, order_modes = candidate_parameters(level)
    merge_gaps = (0, 4, 8, 16, 32) if level == "exhaustive" else ((0, 8, 24) if level == "normal" else (0, 12))
    template_options = [(plan.name, plan.template) for plan in simple_plans[:2]]
    for template_name, template in template_options:
        for block_size in block_sizes:
            if block_size > package.engines[engine_index].page_size:
                continue
            for order_mode in order_modes:
                for slab_size in slab_sizes:
                    if slab_size % block_size:
                        continue
                    plan = build_pblk_plan(
                        package,
                        engine_index,
                        codec,
                        template,
                        block_size,
                        slab_size,
                        order_mode,
                        merge_gaps,
                    )
                    if plan is not None:
                        plan.name += f":template={template_name}"
                        candidates.append(plan)
                plan = build_rmap_plan(
                    package,
                    engine_index,
                    codec,
                    template,
                    block_size,
                    order_mode,
                    merge_gaps,
                )
                if plan is not None:
                    plan.name += f":template={template_name}"
                    candidates.append(plan)
    scored = []
    for candidate in candidates:
        cost = estimate_engine_plan(codec, candidate, base_resource_count)
        candidate.stats["estimated_storage"] = cost
        scored.append({"name": candidate.name, "bytes": cost, **candidate.stats})
    best = min(candidates, key=lambda candidate: (candidate.stats["estimated_storage"], candidate.name))
    return best, sorted(scored, key=lambda item: (item["bytes"], item["name"]))


def build_hpl1(
    codec: ZX0Codec,
    package: ParsedKSP,
    templates: dict[int, bytes],
    hybrid_pages: set[int],
    block_size: int,
    hot_capacity: int,
    warm_capacity: int,
    order_mode: str,
) -> tuple[OutputResource, list[int], dict]:
    if not hybrid_pages:
        raise KSPError("empty HPOL page set")
    page_sizes = {package.engines[package.page_entries[index].engine].page_size for index in hybrid_pages}
    if len(page_sizes) != 1:
        raise KSPError("HPOL pages must share a page size in this optimizer")
    page_size = next(iter(page_sizes))
    if page_size % block_size:
        raise KSPError("HPOL block size must divide page size")
    positions = []
    for position in range(0, page_size, block_size):
        changed = False
        for page_index in hybrid_pages:
            owner = package.page_entries[page_index].engine
            if package.pages[page_index][position:position + block_size] != templates[owner][position:position + block_size]:
                changed = True
                break
        if changed:
            positions.append(position)
    if not positions:
        raise KSPError("HPOL candidate has no differing positions")
    occurrence_order: list[tuple[int, int, bytes]] = []
    page_blocks: dict[int, list[bytes]] = {}
    frequency: Counter[bytes] = Counter()
    for page_index in sorted(hybrid_pages):
        row = []
        page = package.pages[page_index]
        for position in positions:
            block = page[position:position + block_size]
            row.append(block)
            occurrence_order.append((page_index, position, block))
            frequency[block] += 1
        page_blocks[page_index] = row
    if order_mode == "frequency":
        occurrence_order.sort(key=lambda item: (-frequency[item[2]], item[1], item[0]))
    elif order_mode == "position":
        occurrence_order.sort(key=lambda item: (item[1], item[0]))
    blocks: list[bytes] = []
    old_id: dict[bytes, int] = {}
    first_position: dict[bytes, int] = {}
    for _page, position, block in occurrence_order:
        if block not in old_id:
            old_id[block] = len(blocks)
            first_position[block] = position
            blocks.append(block)
    if order_mode == "frequency":
        ordered_blocks = sorted(blocks, key=lambda block: (-frequency[block], first_position[block], old_id[block]))
    elif order_mode == "position":
        ordered_blocks = sorted(blocks, key=lambda block: (first_position[block], old_id[block]))
    else:
        ordered_blocks = blocks
    block_id = {block: index for index, block in enumerate(ordered_blocks)}
    max_hot = min(len(ordered_blocks), hot_capacity // block_size)
    max_warm = min(len(ordered_blocks) - max_hot, warm_capacity // block_size)
    hot_blocks = ordered_blocks[:max_hot]
    warm_blocks = ordered_blocks[max_hot:max_hot + max_warm]
    cold_blocks = ordered_blocks[max_hot + max_warm:]
    hot_raw = b"".join(hot_blocks)
    warm_raw = b"".join(warm_blocks)
    cold_raw = b"".join(cold_blocks)
    hot_packed = codec.compress(hot_raw) if hot_raw else b""
    warm_packed = codec.compress(warm_raw) if warm_raw else b""
    map_raw = bytearray(len(package.pages) * len(positions) * 2)
    fallback_id = 0
    for page_index in range(len(package.pages)):
        row = page_blocks.get(page_index)
        for column in range(len(positions)):
            value = block_id[row[column]] if row is not None else fallback_id
            struct.pack_into("<H", map_raw, (page_index * len(positions) + column) * 2, value)
    map_packed = codec.compress(bytes(map_raw))
    blocks_per_slab = max(1, 16384 // block_size)
    cold_slabs_raw = [
        b"".join(cold_blocks[index:index + blocks_per_slab])
        for index in range(0, len(cold_blocks), blocks_per_slab)
    ]
    cold_slabs = []
    for raw in cold_slabs_raw:
        compression, packed = codec.best_object(raw)
        cold_slabs.append((compression, packed, raw))
    positions_raw = struct.pack(f"<{len(positions)}H", *positions)
    position_offset = 96
    map_offset = position_offset + len(positions_raw)
    hot_offset = map_offset + len(map_packed) if hot_raw else 0
    warm_offset = (hot_offset + len(hot_packed)) if warm_raw else 0
    after_streams = map_offset + len(map_packed) + len(hot_packed) + len(warm_packed)
    cold_table_offset = after_streams
    cold_data_offset = cold_table_offset + len(cold_slabs) * 16
    output = bytearray(cold_data_offset)
    output[:4] = b"HPL1"
    struct.pack_into(
        "<HHHHHHHHH",
        output,
        4,
        96,
        1,
        block_size,
        len(positions),
        len(package.pages),
        len(hot_blocks),
        len(warm_blocks),
        len(cold_blocks),
        len(cold_slabs),
    )
    struct.pack_into("<H", output, 0x16, 0)
    struct.pack_into(
        "<IIIIIIIIIIIIIIIIII",
        output,
        0x18,
        position_offset,
        map_offset,
        len(map_packed),
        len(map_raw),
        hot_offset,
        len(hot_packed),
        len(hot_raw),
        warm_offset,
        len(warm_packed),
        len(warm_raw),
        cold_table_offset,
        cold_data_offset,
        sum(len(packed) for _, packed, _ in cold_slabs),
        len(cold_raw),
        crc32(hot_raw) if hot_raw else 0,
        crc32(warm_raw) if warm_raw else 0,
        crc32(cold_raw) if cold_raw else 0,
        crc32(map_raw),
    )
    output[position_offset:position_offset + len(positions_raw)] = positions_raw
    output[map_offset:map_offset + len(map_packed)] = map_packed
    cursor = map_offset + len(map_packed)
    if hot_raw:
        output[cursor:cursor + len(hot_packed)] = hot_packed
        cursor += len(hot_packed)
    if warm_raw:
        output[cursor:cursor + len(warm_packed)] = warm_packed
        cursor += len(warm_packed)
    cursor = cold_data_offset
    for slab_index, (compression, packed, raw) in enumerate(cold_slabs):
        struct.pack_into(
            "<IIHBBI",
            output,
            cold_table_offset + slab_index * 16,
            cursor,
            len(packed),
            len(raw),
            compression,
            0,
            crc32(raw),
        )
        cursor += len(packed)
    for _, packed, _ in cold_slabs:
        output += packed
    canonical = positions_raw + bytes(map_raw) + hot_raw + warm_raw + cold_raw
    resource = OutputResource(
        b"HPOL",
        RES_REQUIRED | RES_PAGE_SOURCE,
        COMP_NONE,
        bytes(output),
        len(canonical),
        crc32(canonical),
        len(hot_raw),
        len(warm_raw),
    )
    stats = {
        "strategy": "hpol",
        "block_size": block_size,
        "positions": len(positions),
        "hybrid_pages": len(hybrid_pages),
        "unique_blocks": len(ordered_blocks),
        "hot_blocks": len(hot_blocks),
        "warm_blocks": len(warm_blocks),
        "cold_blocks": len(cold_blocks),
        "hot_raw": len(hot_raw),
        "hot_packed": len(hot_packed),
        "warm_raw": len(warm_raw),
        "warm_packed": len(warm_packed),
        "cold_raw": len(cold_raw),
        "cold_packed": sum(len(packed) for _, packed, _ in cold_slabs),
        "cold_slabs": len(cold_slabs),
        "map_raw": len(map_raw),
        "map_packed": len(map_packed),
        "container": len(output),
        "order": order_mode,
    }
    return resource, positions, stats


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------

def keep_resource(resource: Resource) -> bool:
    if resource.kind in (b"PBLK", b"HPOL"):
        return False
    if resource.kind == b"DATA" and (resource.flags & RES_PAGE_SOURCE):
        return False
    return True


def prepare_preserved_resources(package: ParsedKSP) -> tuple[list[OutputResource], dict[int, int]]:
    output: list[OutputResource] = []
    mapping: dict[int, int] = {}
    for old_index, resource in enumerate(package.resources):
        if not keep_resource(resource):
            continue
        mapping[old_index] = len(output)
        output.append(
            OutputResource(
                resource.kind,
                resource.flags,
                resource.compression,
                resource.physical_payload,
                resource.unpacked_size,
                resource.crc,
                resource.aux0,
                resource.aux1,
                old_index,
            )
        )
    return output, mapping


def remap_optional(index: int, mapping: dict[int, int], label: str) -> int:
    if index == NULL16:
        return NULL16
    if index not in mapping:
        raise KSPError(f"{label} references a resource removed as page-only")
    return mapping[index]


@dataclass
class FinalizedPage:
    owner: int
    encoding: int
    compression: int
    flags: int
    raw_size: int
    packed: bytes
    final_crc: int
    label: str


@dataclass
class FinalizedEngine:
    source: Engine
    default_mwk: int
    template_compression: int
    template_packed: bytes
    template_raw: bytes


def build_package_bytes(
    package: ParsedKSP,
    plan: BuildPlan,
    codec: ZX0Codec,
) -> tuple[bytes, dict]:
    preserved, old_to_new = prepare_preserved_resources(package)
    output_resources = list(preserved)
    engine_resource_indices: dict[int, list[int]] = {}
    for engine_plan in plan.engine_plans:
        indices = []
        for resource in engine_plan.resources:
            indices.append(len(output_resources))
            output_resources.append(resource)
        engine_resource_indices[engine_plan.engine_index] = indices
    global_indices = []
    for resource in plan.global_resources:
        global_indices.append(len(output_resources))
        output_resources.append(resource)

    finalized_engines: list[FinalizedEngine] = []
    finalized_pages: list[Optional[FinalizedPage]] = [None] * len(package.pages)
    for engine_plan in plan.engine_plans:
        source_engine = package.engines[engine_plan.engine_index]
        template_compression, template_packed = codec.best_object(engine_plan.template)
        default_mwk = remap_optional(source_engine.default_mwk, old_to_new, f"engine {engine_plan.engine_index} default MWK")
        finalized_engines.append(
            FinalizedEngine(source_engine, default_mwk, template_compression, template_packed, engine_plan.template)
        )
        resource_indices = engine_resource_indices[engine_plan.engine_index]
        if len(engine_plan.page_plans) != source_engine.page_count:
            raise KSPError("engine plan page count mismatch")
        for local_index, page_plan in enumerate(engine_plan.page_plans):
            global_page = source_engine.first_page + local_index
            if page_plan.encoding == PAGE_HPOL:
                compression, packed, raw_size = COMP_NONE, b"", 0
            else:
                if page_plan.build_raw is None:
                    raise KSPError("non-hybrid page has no payload builder")
                raw = page_plan.build_raw(resource_indices)
                compression, packed = codec.best_object(raw)
                raw_size = len(raw)
            finalized_pages[global_page] = FinalizedPage(
                engine_plan.engine_index,
                page_plan.encoding,
                compression,
                page_plan.flags,
                raw_size,
                packed,
                crc32(page_plan.final_page),
                page_plan.label,
            )
    if any(page is None for page in finalized_pages):
        raise KSPError("build plan did not provide every page")
    pages = [page for page in finalized_pages if page is not None]

    engine_offset = KSP_HEADER_SIZE
    page_offset = engine_offset + len(package.engines) * ENGINE_SIZE
    track_offset = page_offset + len(pages) * PAGE_SIZE_ENTRY
    resource_offset = track_offset + len(package.tracks) * TRACK_SIZE
    string_offset = resource_offset + len(output_resources) * RESOURCE_SIZE
    payload_start = string_offset + len(package.header.strings)

    payload_data = bytearray()
    payload_offsets: dict[bytes, int] = {}

    def store(payload: bytes) -> int:
        if not payload:
            return 0
        digest = hashlib.sha256(payload).digest()
        existing = payload_offsets.get(digest)
        if existing is not None:
            absolute, previous = existing >> 32, existing & 0xFFFFFFFF
            if bytes(payload_data[previous:previous + len(payload)]) == payload:
                return absolute
        relative = len(payload_data)
        absolute = payload_start + relative
        payload_data.extend(payload)
        payload_offsets[digest] = (absolute << 32) | relative
        return absolute

    engine_table = bytearray(len(package.engines) * ENGINE_SIZE)
    engine_by_index = {plan.engine_index: finalized_engines[index] for index, plan in enumerate(plan.engine_plans)}
    for index, source in enumerate(package.engines):
        final = engine_by_index[index]
        template_offset = store(final.template_packed)
        struct.pack_into(
            "<IIHHHHHHHHHHHHBBBBIIIII",
            engine_table,
            index * ENGINE_SIZE,
            source.flags,
            source.hardware,
            source.abi,
            source.tick_hz,
            source.load_address,
            source.page_size,
            source.init_address,
            source.play_address,
            source.stop_address,
            source.gateway,
            source.replace_start,
            source.first_page,
            source.page_count,
            final.default_mwk,
            final.template_compression,
            source.first_bank,
            source.bank_count,
            source.bank_width,
            template_offset,
            len(final.template_packed),
            len(final.template_raw),
            crc32(final.template_raw),
            source.name_offset,
        )

    page_table = bytearray(len(pages) * PAGE_SIZE_ENTRY)
    for index, page in enumerate(pages):
        payload_offset = store(page.packed)
        struct.pack_into(
            "<HBBHHIIII",
            page_table,
            index * PAGE_SIZE_ENTRY,
            page.owner,
            page.encoding,
            page.compression,
            page.flags,
            0,
            payload_offset,
            len(page.packed),
            page.raw_size,
            page.final_crc,
        )

    track_table = bytearray(len(package.tracks) * TRACK_SIZE)
    for index, track in enumerate(package.tracks):
        mwk = remap_optional(track.mwk, old_to_new, f"track {index} MWK")
        image = remap_optional(track.image, old_to_new, f"track {index} image")
        struct.pack_into(
            "<HHHHHHIIIII",
            track_table,
            index * TRACK_SIZE,
            track.page,
            track.song,
            track.flags,
            mwk,
            image,
            0,
            track.title_offset,
            track.duration,
            track.loop_start,
            track.loop_end,
            track.fade,
        )

    resource_table = bytearray(len(output_resources) * RESOURCE_SIZE)
    for index, resource in enumerate(output_resources):
        data_offset = store(resource.physical)
        resource_table[index * RESOURCE_SIZE:index * RESOURCE_SIZE + 4] = resource.kind
        struct.pack_into(
            "<HBBIIIIII",
            resource_table,
            index * RESOURCE_SIZE + 4,
            resource.flags,
            resource.compression,
            0,
            data_offset,
            len(resource.physical),
            resource.unpacked_size,
            resource.crc,
            resource.aux0,
            resource.aux1,
        )

    meta = remap_optional(package.header.meta_resource, old_to_new, "META")
    cover = remap_optional(package.header.cover_resource, old_to_new, "cover")
    file_size = payload_start + len(payload_data)
    header = bytearray(KSP_HEADER_SIZE)
    header[:4] = b"KSP1"
    struct.pack_into("<HHII", header, 4, 80, package.header.minor, package.header.flags, file_size)
    struct.pack_into("<IHH", header, 16, engine_offset, len(package.engines), ENGINE_SIZE)
    struct.pack_into("<IHH", header, 24, page_offset, len(pages), PAGE_SIZE_ENTRY)
    struct.pack_into("<IHH", header, 32, track_offset, len(package.tracks), TRACK_SIZE)
    struct.pack_into("<IHH", header, 40, resource_offset, len(output_resources), RESOURCE_SIZE)
    struct.pack_into("<II", header, 48, string_offset, len(package.header.strings))
    struct.pack_into("<HHH", header, 56, package.header.default_track, meta, cover)
    index_bytes = engine_table + page_table + track_table + resource_table + package.header.strings
    struct.pack_into("<I", header, 68, crc32(index_bytes))
    struct.pack_into("<I", header, 64, 0)
    struct.pack_into("<I", header, 64, crc32(header))
    result = bytes(header + engine_table + page_table + track_table + resource_table + package.header.strings + payload_data)
    if len(result) != file_size:
        raise KSPError("internal output file-size mismatch")
    report = {
        "name": plan.name,
        "bytes": len(result),
        "sha256": sha256(result),
        "engine_plans": [
            {"engine": engine_plan.engine_index, "name": engine_plan.name, **engine_plan.stats}
            for engine_plan in plan.engine_plans
        ],
        "global": plan.report,
        "resources": [resource.kind.decode("ascii", errors="replace") for resource in output_resources],
        "page_encodings": dict(Counter(page.encoding for page in pages)),
        "page_labels": dict(Counter(page.label for page in pages)),
    }
    return result, report


def verify_rebuilt(path: Path, expected_pages: list[bytes]) -> ParsedKSP:
    parsed = parse_ksp(path)
    if len(parsed.pages) != len(expected_pages):
        raise KSPError("rebuilt page count mismatch")
    for index, (actual, expected) in enumerate(zip(parsed.pages, expected_pages)):
        if actual != expected:
            raise KSPError(f"rebuilt page {index} differs from source")
    return parsed


# ---------------------------------------------------------------------------
# Optimization driver
# ---------------------------------------------------------------------------

def optimize(
    source: Path,
    output: Path,
    report_path: Path,
    codec: ZX0Codec,
    level: str,
    hot_capacity: int,
    warm_capacity: int,
    force_rebuild: bool,
    repair_legacy_sparse: bool,
    no_hpol: bool,
    msx_player_profile: bool,
    wrtpsg_destination: Optional[int],
    rdvdp_destination: Optional[int],
    ei_to_di_addresses: Sequence[int],
) -> dict:
    package = parse_ksp(source, allow_legacy_sparse=repair_legacy_sparse)
    wrtpsg_patches = 0
    if wrtpsg_destination is not None:
        wrtpsg_patches = relocate_bios_wrtpsg(package, wrtpsg_destination)
    rdvdp_patches = 0
    if rdvdp_destination is not None:
        rdvdp_patches = relocate_bios_rdvdp(package, rdvdp_destination)
    ei_to_di_patches = patch_ei_to_di(package, ei_to_di_addresses) if ei_to_di_addresses else 0
    preserved, _mapping = prepare_preserved_resources(package)
    base_resource_count = len(preserved)
    engine_plans: list[EnginePlan] = []
    engine_candidates: list[dict] = []
    simple_best: dict[int, EnginePlan] = {}
    for engine_index in range(len(package.engines)):
        best, candidates = choose_engine_plan(package, engine_index, codec, level, base_resource_count)
        engine_plans.append(best)
        engine_candidates.append({"engine": engine_index, "selected": best.name, "candidates": candidates})
        simple_candidates = build_simple_engine_plan(package, engine_index, codec, level)
        simple_best[engine_index] = min(simple_candidates, key=lambda plan: estimate_engine_plan(codec, plan, base_resource_count))

    plans: list[BuildPlan] = [
        BuildPlan("best-per-engine", engine_plans, report={"engine_candidates": engine_candidates})
    ]
    plans.append(BuildPlan("simple-only", [simple_best[index] for index in range(len(package.engines))]))
    if msx_player_profile:
        # The current native MSX player implements sparse, complete and HPOL
        # pages. PBLK and RESOURCE_MAP remain valid KSP formats but require a
        # newer runtime, so do not select the unrestricted per-engine plan.
        plans = [plans[-1]]

    hpol_candidate_reports: list[dict] = []
    if not no_hpol:
        block_sizes, _slabs, order_modes = candidate_parameters(level)
        groups: list[tuple[str, set[int]]] = []
        for engine_index, engine in enumerate(package.engines):
            groups.append((f"engine-{engine_index}", set(range(engine.first_page, engine.first_page + engine.page_count))))
        page_sizes = {engine.page_size for engine in package.engines}
        if len(page_sizes) == 1 and len(package.engines) > 1:
            groups.append(("all-engines", set(range(len(package.pages)))))
        seen_groups: set[tuple[int, ...]] = set()
        for group_name, page_set in groups:
            group_key = tuple(sorted(page_set))
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)
            for block_size in block_sizes:
                page_size = package.engines[package.page_entries[next(iter(page_set))].engine].page_size
                if page_size % block_size:
                    continue
                for order_mode in order_modes:
                    templates = {index: simple_best[index].template for index in range(len(package.engines))}
                    try:
                        hpol_resource, _positions, stats = build_hpl1(
                            codec,
                            package,
                            templates,
                            page_set,
                            block_size,
                            hot_capacity,
                            warm_capacity,
                            order_mode,
                        )
                    except KSPError as exc:
                        hpol_candidate_reports.append({"group": group_name, "block_size": block_size, "order": order_mode, "error": str(exc)})
                        continue
                    if msx_player_profile and (
                        stats["map_raw"] > 0x1800 or stats["positions"] * 2 > 0x0200
                    ):
                        hpol_candidate_reports.append(
                            {
                                "group": group_name,
                                "block_size": block_size,
                                "order": order_mode,
                                "error": "native MSX map or position buffer exceeded",
                            }
                        )
                        continue
                    hpol_plans: list[EnginePlan] = []
                    for engine_index, engine in enumerate(package.engines):
                        base = simple_best[engine_index]
                        page_plans = []
                        for local_index, original_plan in enumerate(base.page_plans):
                            global_page = engine.first_page + local_index
                            if global_page in page_set:
                                page_plans.append(PagePlan(PAGE_HPOL, 0, None, package.pages[global_page], "hpol"))
                            else:
                                page_plans.append(original_plan)
                        hpol_plans.append(
                            EnginePlan(engine_index, f"{base.name}+hpol", base.template, page_plans, [], dict(base.stats))
                        )
                    candidate = BuildPlan(
                        f"hpol:{group_name}:bs{block_size}:{order_mode}",
                        hpol_plans,
                        [hpol_resource],
                        report=stats,
                    )
                    plans.append(candidate)
                    hpol_candidate_reports.append({"group": group_name, **stats})

    evaluated: list[tuple[bytes, dict, BuildPlan]] = []
    for plan in plans:
        rebuilt, report = build_package_bytes(package, plan, codec)
        evaluated.append((rebuilt, report, plan))
    best_rebuilt, best_report, best_plan = min(evaluated, key=lambda item: (len(item[0]), item[1]["name"]))
    source_is_smaller = (
        not repair_legacy_sparse
        and wrtpsg_destination is None
        and rdvdp_destination is None
        and not ei_to_di_addresses
        and len(package.raw) <= len(best_rebuilt)
    )
    if source_is_smaller and not force_rebuild:
        selected_bytes = package.raw
        selected_name = "original"
        selected_report = {
            "name": "original",
            "bytes": len(package.raw),
            "sha256": sha256(package.raw),
            "reason": "No tested rebuild was smaller.",
        }
    else:
        selected_bytes = best_rebuilt
        selected_name = best_report["name"]
        selected_report = best_report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(selected_bytes)
    if selected_name != "original":
        verify_rebuilt(output, package.pages)
    else:
        parse_ksp(output)
    full_report = {
        "tool": "ksp_optimize.py",
        "source": str(source),
        "source_bytes": len(package.raw),
        "source_sha256": sha256(package.raw),
        "page_count": len(package.pages),
        "unique_pages": len({hashlib.sha256(page).digest() for page in package.pages}),
        "engine_count": len(package.engines),
        "track_count": len(package.tracks),
        "input_page_encodings": dict(Counter(page.encoding for page in package.page_entries)),
        "repaired_legacy_sparse": repair_legacy_sparse,
        "level": level,
        "msx_player_profile": msx_player_profile,
        "wrtpsg_relocation": (
            {"destination": wrtpsg_destination, "patched_sites_per_page": wrtpsg_patches}
            if wrtpsg_destination is not None else None
        ),
        "rdvdp_relocation": (
            {"destination": rdvdp_destination, "patched_sites_per_page": rdvdp_patches}
            if rdvdp_destination is not None else None
        ),
        "ei_to_di_patches": {
            "addresses": list(ei_to_di_addresses),
            "total_page_patches": ei_to_di_patches,
        },
        "zx0": str(codec.executable) if codec.executable else "built-in conservative Python codec",
        "selected": selected_report,
        "output": str(output),
        "output_bytes": len(selected_bytes),
        "saved_bytes": len(package.raw) - len(selected_bytes),
        "saved_percent": round((len(package.raw) - len(selected_bytes)) * 100 / len(package.raw), 3) if package.raw else 0,
        "byte_identical_page_validation": True,
        "tested_rebuilds": sorted((report for _bytes, report, _plan in evaluated), key=lambda item: (item["bytes"], item["name"])),
        "engine_candidates": engine_candidates,
        "hpol_candidates": hpol_candidate_reports,
        "limitations": [
            "The built-in ZX0 compressor is valid but not an optimal parser; use --zx0 for reference-compressor measurements.",
            "The search is deterministic but finite; --level exhaustive tests more block/slab/order candidates, not every mathematical combination.",
            "Only obsolete PBLK, HPOL, and PAGE_SOURCE DATA resources are removed automatically; unknown resources are preserved conservatively.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(full_report, indent=2), encoding="utf-8")
    return full_report


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test(codec: ZX0Codec) -> None:
    raw = (b"ABCD" * 200) + bytes(range(256)) + (b"\0" * 400)
    packed = codec.compress(raw)
    assert zx0_decompress(packed, len(raw)) == raw
    template = bytes([0]) * 1024
    page = bytearray(template)
    page[10:40] = bytes(range(30))
    page[100:150] = b"X" * 50
    overlay = sparse_payload(template, bytes(page), 4)
    assert apply_sparse(template, overlay) == bytes(page)
    blocks = [bytes([index]) * 128 for index in range(20)]
    pbk1, _stats = make_pbk1(codec, blocks, 128, 1024)
    resource = Resource(b"PBLK", RES_REQUIRED, 0, 0, len(pbk1), len(blocks) * 128, crc32(b"".join(blocks)), 0, 0, pbk1)
    block_size, decoded_blocks = decode_pblk_resource(resource)
    assert block_size == 128 and decoded_blocks == blocks
    source = bytes(range(256)) * 100
    kzb1 = make_kzb1(codec, source)
    assert decode_kzb1(kzb1, len(source), crc32(source)) == source
    print("Self-test passed: ZX0, sparse overlays, PBK1 and KZB1 round-trip correctly.")


def parse_size(text: str) -> int:
    value = text.strip().lower()
    multiplier = 1
    if value.endswith("kib"):
        multiplier = 1024
        value = value[:-3]
    elif value.endswith("kb"):
        multiplier = 1024
        value = value[:-2]
    elif value.endswith("k"):
        multiplier = 1024
        value = value[:-1]
    elif value.endswith("mib"):
        multiplier = 1024 * 1024
        value = value[:-3]
    elif value.endswith("mb"):
        multiplier = 1024 * 1024
        value = value[:-2]
    elif value.endswith("m"):
        multiplier = 1024 * 1024
        value = value[:-1]
    return int(value, 0) * multiplier


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild a standalone KSP 1.00/1.01 package using the smallest tested page-storage representation."
    )
    parser.add_argument("input", nargs="?", type=Path, help="input .ksp")
    parser.add_argument("output", nargs="?", type=Path, help="optimized .ksp")
    parser.add_argument("--report", type=Path, help="JSON report path")
    parser.add_argument("--level", choices=("quick", "normal", "exhaustive"), default="normal")
    parser.add_argument("--zx0", type=Path, help="reference zx0 executable for better compression")
    parser.add_argument("--hot-capacity", type=parse_size, default=48 * 1024)
    parser.add_argument("--warm-capacity", type=parse_size, default=96 * 1024)
    parser.add_argument("--force-rebuild", action="store_true", help="write the smallest rebuilt representation even when the original is smaller")
    parser.add_argument(
        "--repair-legacy-sparse",
        action="store_true",
        help="accept unordered legacy sparse records, then rebuild them as canonical overlays",
    )
    parser.add_argument("--no-hpol", action="store_true", help="skip HPOL candidates")
    parser.add_argument(
        "--msx-player-profile",
        action="store_true",
        help="restrict output to sparse, complete, or HPOL pages supported by the current MSX player",
    )
    parser.add_argument(
        "--relocate-wrtpsg",
        type=lambda value: int(value, 0),
        metavar="ADDRESS",
        help="redirect direct BIOS WRTPSG calls/jumps to an 8-byte page-local wrapper",
    )
    parser.add_argument(
        "--relocate-rdvdp",
        type=lambda value: int(value, 0),
        metavar="ADDRESS",
        help="redirect direct BIOS RDVDP calls/jumps to a 3-byte page-local wrapper",
    )
    parser.add_argument(
        "--patch-ei-to-di",
        action="append",
        default=[],
        type=lambda value: int(value, 0),
        metavar="ADDRESS",
        help="replace a verified engine-local EI with DI in every runtime page",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.msx_player_profile and args.zx0 is None:
        bundled_zx0 = Path(__file__).resolve().parents[1] / "ksp1-mac-player 2/build/vendor-upstream/zx0pack"
        if bundled_zx0.is_file() and os.access(bundled_zx0, os.X_OK):
            args.zx0 = bundled_zx0
        else:
            parser.error("--msx-player-profile requires --zx0 or the bundled zx0pack build target")

    if args.zx0 is not None:
        if not args.zx0.is_file() or not os.access(args.zx0, os.X_OK):
            parser.error("--zx0 must point to an executable file")
    codec = ZX0Codec(args.zx0)
    if args.self_test:
        self_test(codec)
        return 0
    if args.input is None or args.output is None:
        parser.error("input and output are required unless --self-test is used")
    report_path = args.report or args.output.with_suffix(args.output.suffix + ".report.json")
    try:
        report = optimize(
            args.input,
            args.output,
            report_path,
            codec,
            args.level,
            args.hot_capacity,
            args.warm_capacity,
            args.force_rebuild,
            args.repair_legacy_sparse,
            args.no_hpol,
            args.msx_player_profile,
            args.relocate_wrtpsg,
            args.relocate_rdvdp,
            args.patch_ei_to_di,
        )
    except (KSPError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Input:    {fmt_size(report['source_bytes'])}")
    print(f"Output:   {fmt_size(report['output_bytes'])}")
    print(f"Saved:    {fmt_size(report['saved_bytes'])} ({report['saved_percent']:.3f}%)")
    print(f"Selected: {report['selected']['name']}")
    print(f"KSP:      {args.output}")
    print(f"Report:   {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
