#!/usr/bin/env python3
"""
ksp_info.py - dependency-free KSP 1.x package inspector.

Shows:
- KSP header and table layout
- engine configuration and required hardware
- page encoding statistics, optionally every page
- tracks and titles from the UTF-8 string table
- resources and nested KZB1/PBK1/HPL1 container details
- HPOL hot/warm/cold tier sizes, capacities, positions, and slabs

This tool is read-only. It does not decompress ZX0 streams or validate final
reconstructed pages.
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class KSPError(Exception):
    pass


def u8(data: bytes, offset: int) -> int:
    require_range(data, offset, 1, "u8")
    return data[offset]


def u16(data: bytes, offset: int) -> int:
    require_range(data, offset, 2, "u16")
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    require_range(data, offset, 4, "u32")
    return struct.unpack_from("<I", data, offset)[0]


def require_range(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise KSPError(
            f"{label}: range 0x{offset:X}..0x{offset + size:X} "
            f"is outside file size 0x{len(data):X}"
        )


def slice_checked(data: bytes, offset: int, size: int, label: str) -> bytes:
    require_range(data, offset, size, label)
    return data[offset : offset + size]


def format_size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.2f} KiB"
    return f"{value / (1024 * 1024):.2f} MiB"


def ratio(packed: int, raw: int) -> str:
    if raw == 0:
        return "-"
    return f"{packed / raw * 100:.1f}%"


def hex_or_none(value: int, width: int = 4, null: int | None = None) -> str:
    if null is not None and value == null:
        return "none"
    return f"0x{value:0{width}X}"


def join_flags(value: int, names: dict[int, str]) -> str:
    parts = [name for bit, name in names.items() if value & bit]
    known = 0
    for bit in names:
        known |= bit
    unknown = value & ~known
    if unknown:
        parts.append(f"unknown=0x{unknown:X}")
    return ", ".join(parts) if parts else "none"


COMPRESSION_NAMES = {
    0: "NONE",
    1: "ZX0",
    2: "ZX0_BLOCKS",
}

PAGE_ENCODING_NAMES = {
    0: "SPARSE_OVERLAY",
    1: "COMPLETE",
    2: "SHARED_BLOCK_MAP",
    3: "RESOURCE_MAP",
    4: "HYBRID_POOL",
}

ENGINE_FLAGS = {
    1 << 0: "dynamic-pages",
    1 << 1: "banked-data",
    1 << 2: "MWK-required",
    1 << 3: "page2-runtime",
}

HARDWARE_FLAGS = {
    1 << 0: "PSG",
    1 << 1: "SCC",
    1 << 2: "SCC+",
    1 << 3: "dual-SCC",
    1 << 4: "YM2413/FMPAC",
    1 << 5: "Y8950/MSX-AUDIO",
    1 << 6: "OPL4/MoonSound",
    1 << 7: "SN76489",
    1 << 8: "Game-Gear-stereo",
}

TRACK_FLAGS = {
    1 << 0: "hidden",
    1 << 1: "sound-effect",
    1 << 2: "one-shot",
    1 << 3: "no-auto-advance",
}

RESOURCE_FLAGS = {
    1 << 0: "required",
    1 << 1: "streamable",
    1 << 2: "page-source",
}

HPL_FLAGS = {
    1 << 0: "warm-quick-offset",
}


@dataclass
class Header:
    header_size: int
    minor: int
    flags: int
    declared_file_size: int
    engine_offset: int
    engine_count: int
    engine_entry_size: int
    page_offset: int
    page_count: int
    page_entry_size: int
    track_offset: int
    track_count: int
    track_entry_size: int
    resource_offset: int
    resource_count: int
    resource_entry_size: int
    string_offset: int
    string_size: int
    default_track: int
    meta_resource: int
    cover_resource: int
    header_crc: int
    index_crc: int


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
    template_compression: int
    bank_base: int
    bank_count: int
    bank_width: int
    template_offset: int
    template_packed: int
    template_unpacked: int
    template_crc: int
    name_offset: int


@dataclass
class Page:
    engine: int
    encoding: int
    compression: int
    flags: int
    payload_offset: int
    packed_size: int
    unpacked_size: int
    crc: int


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
    fourcc: str
    flags: int
    compression: int
    data_offset: int
    packed_size: int
    unpacked_size: int
    crc: int
    aux0: int
    aux1: int


def parse_header(data: bytes) -> Header:
    require_range(data, 0, 80, "KSP header")
    if data[:4] != b"KSP1":
        found = data[:4].decode("ascii", errors="replace")
        raise KSPError(f"not KSP 1.x: magic is {found!r}, expected 'KSP1'")

    return Header(
        header_size=u16(data, 0x04),
        minor=u16(data, 0x06),
        flags=u32(data, 0x08),
        declared_file_size=u32(data, 0x0C),
        engine_offset=u32(data, 0x10),
        engine_count=u16(data, 0x14),
        engine_entry_size=u16(data, 0x16),
        page_offset=u32(data, 0x18),
        page_count=u16(data, 0x1C),
        page_entry_size=u16(data, 0x1E),
        track_offset=u32(data, 0x20),
        track_count=u16(data, 0x24),
        track_entry_size=u16(data, 0x26),
        resource_offset=u32(data, 0x28),
        resource_count=u16(data, 0x2C),
        resource_entry_size=u16(data, 0x2E),
        string_offset=u32(data, 0x30),
        string_size=u32(data, 0x34),
        default_track=u16(data, 0x38),
        meta_resource=u16(data, 0x3A),
        cover_resource=u16(data, 0x3C),
        header_crc=u32(data, 0x40),
        index_crc=u32(data, 0x44),
    )


def validate_table(data: bytes, offset: int, count: int, entry_size: int,
                   minimum: int, label: str) -> None:
    if entry_size < minimum:
        raise KSPError(
            f"{label}: entry size {entry_size} is below KSP 1.0 minimum {minimum}"
        )
    require_range(data, offset, count * entry_size, label)


def parse_engines(data: bytes, h: Header) -> list[Engine]:
    validate_table(
        data, h.engine_offset, h.engine_count, h.engine_entry_size, 64, "engine table"
    )
    result = []
    for i in range(h.engine_count):
        o = h.engine_offset + i * h.engine_entry_size
        result.append(
            Engine(
                flags=u32(data, o + 0x00),
                hardware=u32(data, o + 0x04),
                abi=u16(data, o + 0x08),
                tick_hz=u16(data, o + 0x0A),
                load_address=u16(data, o + 0x0C),
                page_size=u16(data, o + 0x0E),
                init_address=u16(data, o + 0x10),
                play_address=u16(data, o + 0x12),
                stop_address=u16(data, o + 0x14),
                gateway=u16(data, o + 0x16),
                replace_start=u16(data, o + 0x18),
                first_page=u16(data, o + 0x1A),
                page_count=u16(data, o + 0x1C),
                default_mwk=u16(data, o + 0x1E),
                template_compression=u8(data, o + 0x20),
                bank_base=u8(data, o + 0x21),
                bank_count=u8(data, o + 0x22),
                bank_width=u8(data, o + 0x23),
                template_offset=u32(data, o + 0x24),
                template_packed=u32(data, o + 0x28),
                template_unpacked=u32(data, o + 0x2C),
                template_crc=u32(data, o + 0x30),
                name_offset=u32(data, o + 0x34),
            )
        )
    return result


def parse_pages(data: bytes, h: Header) -> list[Page]:
    validate_table(
        data, h.page_offset, h.page_count, h.page_entry_size, 24, "page table"
    )
    result = []
    for i in range(h.page_count):
        o = h.page_offset + i * h.page_entry_size
        result.append(
            Page(
                engine=u16(data, o + 0x00),
                encoding=u8(data, o + 0x02),
                compression=u8(data, o + 0x03),
                flags=u16(data, o + 0x04),
                payload_offset=u32(data, o + 0x08),
                packed_size=u32(data, o + 0x0C),
                unpacked_size=u32(data, o + 0x10),
                crc=u32(data, o + 0x14),
            )
        )
    return result


def parse_tracks(data: bytes, h: Header) -> list[Track]:
    validate_table(
        data, h.track_offset, h.track_count, h.track_entry_size, 32, "track table"
    )
    result = []
    for i in range(h.track_count):
        o = h.track_offset + i * h.track_entry_size
        result.append(
            Track(
                page=u16(data, o + 0x00),
                song=u16(data, o + 0x02),
                flags=u16(data, o + 0x04),
                mwk=u16(data, o + 0x06),
                image=u16(data, o + 0x08),
                title_offset=u32(data, o + 0x0C),
                duration=u32(data, o + 0x10),
                loop_start=u32(data, o + 0x14),
                loop_end=u32(data, o + 0x18),
                fade=u32(data, o + 0x1C),
            )
        )
    return result


def parse_resources(data: bytes, h: Header) -> list[Resource]:
    validate_table(
        data,
        h.resource_offset,
        h.resource_count,
        h.resource_entry_size,
        32,
        "resource table",
    )
    result = []
    for i in range(h.resource_count):
        o = h.resource_offset + i * h.resource_entry_size
        fourcc_raw = slice_checked(data, o, 4, f"resource {i} FourCC")
        result.append(
            Resource(
                fourcc=fourcc_raw.decode("ascii", errors="replace"),
                flags=u16(data, o + 0x04),
                compression=u8(data, o + 0x06),
                data_offset=u32(data, o + 0x08),
                packed_size=u32(data, o + 0x0C),
                unpacked_size=u32(data, o + 0x10),
                crc=u32(data, o + 0x14),
                aux0=u32(data, o + 0x18),
                aux1=u32(data, o + 0x1C),
            )
        )
    return result


def read_string(data: bytes, h: Header, relative_offset: int) -> str | None:
    if relative_offset == 0xFFFFFFFF:
        return None
    if relative_offset >= h.string_size:
        return f"<invalid string offset 0x{relative_offset:X}>"
    start = h.string_offset + relative_offset
    end_limit = h.string_offset + h.string_size
    require_range(data, h.string_offset, h.string_size, "string table")
    end = data.find(b"\0", start, end_limit)
    if end < 0:
        return "<unterminated string>"
    return data[start:end].decode("utf-8", errors="replace")


def compression_name(value: int) -> str:
    return COMPRESSION_NAMES.get(value, f"UNKNOWN({value})")


def page_encoding_name(value: int) -> str:
    return PAGE_ENCODING_NAMES.get(value, f"UNKNOWN({value})")


def time_value(value: int, unknown_text: str = "unknown") -> str:
    if value == 0xFFFFFFFF:
        return unknown_text
    minutes, rem_ms = divmod(value, 60_000)
    seconds = rem_ms / 1000
    if minutes:
        return f"{minutes}:{seconds:06.3f}"
    return f"{seconds:.3f}s"


def print_header(path: Path, data: bytes, h: Header) -> None:
    print(f"KSP package: {path}")
    print("=" * 78)
    print(f"Actual file size:   {len(data):>10} bytes  ({format_size(len(data))})")
    print(
        f"Declared file size: {h.declared_file_size:>10} bytes  "
        f"({'OK' if h.declared_file_size == len(data) else 'MISMATCH'})"
    )
    print(f"Format:             KSP 1.{h.minor:02d}")
    print(f"Header size:        {h.header_size} bytes")
    print(f"File flags:         0x{h.flags:08X}")
    print(f"Header CRC32:       0x{h.header_crc:08X}" if h.header_crc else "Header CRC32:       not present")
    print(f"Index CRC32:        0x{h.index_crc:08X}" if h.index_crc else "Index CRC32:        not present")
    print(
        f"Objects:            {h.engine_count} engine(s), {h.page_count} page(s), "
        f"{h.track_count} track(s), {h.resource_count} resource(s)"
    )
    print(
        f"Default track:      {h.default_track} | "
        f"META: {hex_or_none(h.meta_resource, null=0xFFFF)} | "
        f"cover: {hex_or_none(h.cover_resource, null=0xFFFF)}"
    )
    print("Tables:")
    print(
        f"  engines   offset=0x{h.engine_offset:08X} count={h.engine_count:<5} "
        f"entry={h.engine_entry_size}"
    )
    print(
        f"  pages     offset=0x{h.page_offset:08X} count={h.page_count:<5} "
        f"entry={h.page_entry_size}"
    )
    print(
        f"  tracks    offset=0x{h.track_offset:08X} count={h.track_count:<5} "
        f"entry={h.track_entry_size}"
    )
    print(
        f"  resources offset=0x{h.resource_offset:08X} count={h.resource_count:<5} "
        f"entry={h.resource_entry_size}"
    )
    print(
        f"  strings   offset=0x{h.string_offset:08X} size={h.string_size} "
        f"({format_size(h.string_size)})"
    )


def print_engines(data: bytes, h: Header, engines: list[Engine]) -> None:
    print("\nENGINES")
    print("-" * 78)
    for i, e in enumerate(engines):
        name = read_string(data, h, e.name_offset) or "<unnamed>"
        bank_width = {0: "none", 1: "8 KiB", 2: "16 KiB"}.get(
            e.bank_width, f"unknown({e.bank_width})"
        )
        print(f"[{i}] {name}")
        print(f"  flags/hardware: {join_flags(e.flags, ENGINE_FLAGS)} | {join_flags(e.hardware, HARDWARE_FLAGS)}")
        print(
            f"  ABI/timing:     ABI {e.abi}, {e.tick_hz} Hz, "
            f"load=0x{e.load_address:04X}, page={format_size(e.page_size)}"
        )
        print(
            f"  entry points:   INIT=0x{e.init_address:04X}, PLAY=0x{e.play_address:04X}, "
            f"STOP={hex_or_none(e.stop_address)}, gateway={hex_or_none(e.gateway)}"
        )
        print(
            f"  pages:          global {e.first_page}.."
            f"{e.first_page + max(e.page_count - 1, 0)} ({e.page_count}), "
            f"replace-start=0x{e.replace_start:04X}"
        )
        print(
            f"  template:       {compression_name(e.template_compression)}, "
            f"{format_size(e.template_packed)} -> {format_size(e.template_unpacked)}, "
            f"ratio={ratio(e.template_packed, e.template_unpacked)}, "
            f"offset=0x{e.template_offset:08X}, CRC=0x{e.template_crc:08X}"
        )
        print(
            f"  banks/MWK:      base={e.bank_base}, count={e.bank_count}, width={bank_width}, "
            f"default MWK={hex_or_none(e.default_mwk, null=0xFFFF)}"
        )


def print_page_summary(pages: list[Page]) -> None:
    print("\nPAGE ENCODINGS")
    print("-" * 78)
    counts = Counter(page_encoding_name(p.encoding) for p in pages)
    for name in PAGE_ENCODING_NAMES.values():
        if counts[name]:
            print(f"  {name:<22} {counts[name]}")
    for name, count in sorted(counts.items()):
        if name not in PAGE_ENCODING_NAMES.values():
            print(f"  {name:<22} {count}")
    packed = sum(p.packed_size for p in pages)
    raw = sum(p.unpacked_size for p in pages)
    print(
        f"  table payload totals: {format_size(packed)} packed, "
        f"{format_size(raw)} declared unpacked"
    )


def print_pages(pages: list[Page]) -> None:
    print("\nPAGES")
    print("-" * 78)
    for i, p in enumerate(pages):
        print(
            f"[{i:5}] engine={p.engine:<4} encoding={page_encoding_name(p.encoding):<18} "
            f"comp={compression_name(p.compression):<10} flags=0x{p.flags:04X} "
            f"offset=0x{p.payload_offset:08X} "
            f"{p.packed_size}->{p.unpacked_size} CRC=0x{p.crc:08X}"
        )


def print_tracks(
    data: bytes, h: Header, tracks: list[Track], pages: list[Page], limit: int | None
) -> None:
    print("\nTRACKS")
    print("-" * 78)
    shown = tracks if limit is None else tracks[:limit]
    for i, t in enumerate(shown):
        title = read_string(data, h, t.title_offset) or "<untitled>"
        engine = pages[t.page].engine if t.page < len(pages) else "invalid"
        timing = f"duration={time_value(t.duration)}"
        if t.loop_start != 0xFFFFFFFF or t.loop_end != 0xFFFFFFFF:
            timing += (
                f", loop={time_value(t.loop_start, 'none')}.."
                f"{time_value(t.loop_end, 'none')}"
            )
        if t.fade != 0xFFFFFFFF:
            timing += f", fade={time_value(t.fade)}"
        print(
            f"[{i:5}] {title}\n"
            f"        page={t.page}, engine={engine}, song={t.song}, "
            f"flags={join_flags(t.flags, TRACK_FLAGS)}, MWK={hex_or_none(t.mwk, null=0xFFFF)}, "
            f"IMG5={hex_or_none(t.image, null=0xFFFF)}\n"
            f"        {timing}"
        )
    if limit is not None and len(tracks) > limit:
        print(f"... {len(tracks) - limit} more track(s); use --all or --track-limit 0")


def print_meta_if_plain(data: bytes, h: Header, resources: list[Resource]) -> None:
    if h.meta_resource == 0xFFFF or h.meta_resource >= len(resources):
        return
    r = resources[h.meta_resource]
    if r.fourcc != "META":
        return
    print("\nMETADATA")
    print("-" * 78)
    if r.compression != 0:
        print(
            f"META is {compression_name(r.compression)} compressed; "
            "this lightweight inspector does not decompress ZX0."
        )
        return
    raw = slice_checked(data, r.data_offset, r.packed_size, "META resource")
    print(raw.rstrip(b"\0").decode("utf-8", errors="replace"))


def print_kzb1(data: bytes, r: Resource, indent: str, show_slabs: bool) -> None:
    base = r.data_offset
    require_range(data, base, min(r.packed_size, 16), "KZB1 header")
    if data[base : base + 4] != b"KZB1":
        print(f"{indent}container: expected KZB1, found {data[base:base+4]!r}")
        return
    header_size = u16(data, base + 0x04)
    block_count = u16(data, base + 0x06)
    total_raw = u32(data, base + 0x08)
    table_offset = u32(data, base + 0x0C)
    print(
        f"{indent}KZB1: header={header_size}, blocks={block_count}, "
        f"raw={format_size(total_raw)}, table=+0x{table_offset:X}"
    )
    table = base + table_offset
    require_range(data, table, block_count * 16, "KZB1 block table")
    packed_total = 0
    raw_total = 0
    entries = []
    for i in range(block_count):
        o = table + i * 16
        packed_offset = u32(data, o + 0x00)
        packed_size = u32(data, o + 0x04)
        raw_size = u32(data, o + 0x08)
        crc = u32(data, o + 0x0C)
        packed_total += packed_size
        raw_total += raw_size
        entries.append((packed_offset, packed_size, raw_size, crc))
    print(
        f"{indent}      block totals={format_size(packed_total)} -> "
        f"{format_size(raw_total)}, ratio={ratio(packed_total, raw_total)}"
    )
    if show_slabs:
        for i, (off, packed, raw, crc) in enumerate(entries):
            print(
                f"{indent}      [{i}] +0x{off:08X} {packed}->{raw} "
                f"({ratio(packed, raw)}) CRC=0x{crc:08X}"
            )


def print_pbk1(data: bytes, r: Resource, indent: str, show_slabs: bool) -> None:
    base = r.data_offset
    require_range(data, base, min(r.packed_size, 32), "PBK1 header")
    if data[base : base + 4] != b"PBK1":
        print(f"{indent}container: expected PBK1, found {data[base:base+4]!r}")
        return
    header_size = u16(data, base + 0x04)
    block_desc_size = u16(data, base + 0x06)
    slab_desc_size = u16(data, base + 0x08)
    block_size = u16(data, base + 0x0A)
    block_count = u32(data, base + 0x0C)
    slab_count = u16(data, base + 0x10)
    flags = u16(data, base + 0x12)
    block_table_offset = u32(data, base + 0x14)
    slab_table_offset = u32(data, base + 0x18)
    print(
        f"{indent}PBK1: header={header_size}, block={block_size} B, "
        f"blocks={block_count}, slabs={slab_count}, flags=0x{flags:04X}"
    )
    print(
        f"{indent}      descriptor sizes: block={block_desc_size}, slab={slab_desc_size}; "
        f"tables=+0x{block_table_offset:X}/+0x{slab_table_offset:X}"
    )
    if slab_desc_size < 16:
        print(f"{indent}      invalid slab descriptor size")
        return
    table = base + slab_table_offset
    require_range(data, table, slab_count * slab_desc_size, "PBK1 slab table")
    packed_total = 0
    raw_total = 0
    none_count = 0
    zx0_count = 0
    entries = []
    for i in range(slab_count):
        o = table + i * slab_desc_size
        packed_offset = u32(data, o + 0x00)
        packed_size = u32(data, o + 0x04)
        raw_size = u16(data, o + 0x08)
        compression = u8(data, o + 0x0A)
        slab_flags = u8(data, o + 0x0B)
        crc = u32(data, o + 0x0C)
        packed_total += packed_size
        raw_total += raw_size
        none_count += compression == 0
        zx0_count += compression == 1
        entries.append(
            (packed_offset, packed_size, raw_size, compression, slab_flags, crc)
        )
    print(
        f"{indent}      slab totals={format_size(packed_total)} -> "
        f"{format_size(raw_total)}, ratio={ratio(packed_total, raw_total)}, "
        f"NONE={none_count}, ZX0={zx0_count}"
    )
    if show_slabs:
        for i, (off, packed, raw, comp, flags2, crc) in enumerate(entries):
            print(
                f"{indent}      [{i}] +0x{off:08X} {compression_name(comp)} "
                f"{packed}->{raw} ({ratio(packed, raw)}) "
                f"flags=0x{flags2:02X} CRC=0x{crc:08X}"
            )


def print_hpl1(data: bytes, r: Resource, indent: str, show_slabs: bool) -> None:
    base = r.data_offset
    require_range(data, base, min(r.packed_size, 96), "HPL1 header")
    if data[base : base + 4] != b"HPL1":
        print(f"{indent}container: expected HPL1, found {data[base:base+4]!r}")
        return

    header_size = u16(data, base + 0x04)
    version = u16(data, base + 0x06)
    block_size = u16(data, base + 0x08)
    position_count = u16(data, base + 0x0A)
    page_count = u16(data, base + 0x0C)
    hot_count = u16(data, base + 0x0E)
    warm_count = u16(data, base + 0x10)
    cold_count = u16(data, base + 0x12)
    cold_slab_count = u16(data, base + 0x14)
    flags = u16(data, base + 0x16)

    position_offset = u32(data, base + 0x18)
    map_offset = u32(data, base + 0x1C)
    map_packed = u32(data, base + 0x20)
    map_raw = u32(data, base + 0x24)
    hot_offset = u32(data, base + 0x28)
    hot_packed = u32(data, base + 0x2C)
    hot_raw = u32(data, base + 0x30)
    warm_offset = u32(data, base + 0x34)
    warm_packed = u32(data, base + 0x38)
    warm_raw = u32(data, base + 0x3C)
    cold_table_offset = u32(data, base + 0x40)
    cold_data_offset = u32(data, base + 0x44)
    cold_packed = u32(data, base + 0x48)
    cold_raw = u32(data, base + 0x4C)
    hot_crc = u32(data, base + 0x50)
    warm_crc = u32(data, base + 0x54)
    cold_crc = u32(data, base + 0x58)
    map_crc = u32(data, base + 0x5C)

    total_blocks = hot_count + warm_count + cold_count
    print(
        f"{indent}HPL1 v{version}: header={header_size}, block={block_size} B, "
        f"positions={position_count}, pages={page_count}"
    )
    print(
        f"{indent}      flags={join_flags(flags, HPL_FLAGS)}, "
        f"global blocks={total_blocks} "
        f"(hot={hot_count}, warm={warm_count}, cold={cold_count})"
    )
    print(
        f"{indent}      map:  {format_size(map_packed)} -> {format_size(map_raw)} "
        f"({ratio(map_packed, map_raw)}), offset=+0x{map_offset:X}, CRC=0x{map_crc:08X}"
    )
    print(
        f"{indent}      hot:  {format_size(hot_packed)} -> {format_size(hot_raw)} "
        f"({ratio(hot_packed, hot_raw)}), capacity={format_size(r.aux0)}, "
        f"offset=+0x{hot_offset:X}, CRC=0x{hot_crc:08X}"
    )
    print(
        f"{indent}      warm: {format_size(warm_packed)} -> {format_size(warm_raw)} "
        f"({ratio(warm_packed, warm_raw)}), capacity={format_size(r.aux1)}, "
        f"offset=+0x{warm_offset:X}, CRC=0x{warm_crc:08X}"
    )
    print(
        f"{indent}      cold: {format_size(cold_packed)} -> {format_size(cold_raw)} "
        f"({ratio(cold_packed, cold_raw)}), slabs={cold_slab_count}, "
        f"data=+0x{cold_data_offset:X}, CRC=0x{cold_crc:08X}"
    )

    expected_map = page_count * position_count * 2
    checks = [
        ("map raw", map_raw, expected_map),
        ("hot raw", hot_raw, hot_count * block_size),
        ("warm raw", warm_raw, warm_count * block_size),
        ("cold raw", cold_raw, cold_count * block_size),
    ]
    check_text = ", ".join(
        f"{label}={'OK' if actual == expected else f'MISMATCH {actual}!={expected}'}"
        for label, actual, expected in checks
    )
    print(f"{indent}      consistency: {check_text}")

    if position_count:
        position_table = base + position_offset
        require_range(
            data, position_table, position_count * 2, "HPL1 destination positions"
        )
        positions = [
            u16(data, position_table + i * 2) for i in range(position_count)
        ]
        display = ", ".join(f"0x{x:04X}" for x in positions[:32])
        if len(positions) > 32:
            display += f", ... ({len(positions)} total)"
        print(f"{indent}      positions: {display}")

    if cold_slab_count:
        table = base + cold_table_offset
        require_range(data, table, cold_slab_count * 16, "HPL1 cold slab table")
        entries = []
        packed_sum = 0
        raw_sum = 0
        for i in range(cold_slab_count):
            o = table + i * 16
            packed_offset = u32(data, o + 0x00)
            packed_size = u32(data, o + 0x04)
            raw_size = u16(data, o + 0x08)
            comp = u8(data, o + 0x0A)
            slab_flags = u8(data, o + 0x0B)
            crc = u32(data, o + 0x0C)
            packed_sum += packed_size
            raw_sum += raw_size
            entries.append(
                (packed_offset, packed_size, raw_size, comp, slab_flags, crc)
            )
        print(
            f"{indent}      slab-table totals: packed={format_size(packed_sum)} "
            f"({'OK' if packed_sum == cold_packed else 'MISMATCH'}), "
            f"raw={format_size(raw_sum)} "
            f"({'OK' if raw_sum == cold_raw else 'MISMATCH'})"
        )
        if show_slabs:
            for i, (off, packed, raw, comp, flags2, crc) in enumerate(entries):
                blocks = raw // block_size if block_size else 0
                print(
                    f"{indent}      [{i}] +0x{off:08X} {compression_name(comp)} "
                    f"{packed}->{raw} ({ratio(packed, raw)}), blocks={blocks}, "
                    f"flags=0x{flags2:02X}, CRC=0x{crc:08X}"
                )


def print_plain_resource_hint(data: bytes, r: Resource, indent: str) -> None:
    if r.compression != 0 or r.packed_size < 4:
        return
    magic = slice_checked(data, r.data_offset, 4, f"{r.fourcc} payload magic")
    if r.fourcc == "IMG5" and magic == b"I5V1" and r.packed_size >= 16:
        width = u16(data, r.data_offset + 0x04)
        height = u16(data, r.data_offset + 0x06)
        stride = u16(data, r.data_offset + 0x08)
        palette = u8(data, r.data_offset + 0x0A)
        pixel_size = u32(data, r.data_offset + 0x0C)
        print(
            f"{indent}I5V1: {width}x{height}, stride={stride}, "
            f"palette={palette}, pixel bytes={pixel_size}"
        )


def print_resources(
    data: bytes, resources: list[Resource], show_slabs: bool
) -> None:
    print("\nRESOURCES")
    print("-" * 78)
    type_counts = Counter(r.fourcc for r in resources)
    if type_counts:
        print("Types: " + ", ".join(f"{k!r}={v}" for k, v in sorted(type_counts.items())))
    for i, r in enumerate(resources):
        print(
            f"[{i:4}] {r.fourcc!r} flags={join_flags(r.flags, RESOURCE_FLAGS):<32} "
            f"comp={compression_name(r.compression)}"
        )
        print(
            f"       offset=0x{r.data_offset:08X}, "
            f"{format_size(r.packed_size)} -> {format_size(r.unpacked_size)} "
            f"({ratio(r.packed_size, r.unpacked_size)}), "
            f"CRC=0x{r.crc:08X}, aux0={r.aux0}, aux1={r.aux1}"
        )
        require_range(data, r.data_offset, r.packed_size, f"resource {i} payload")
        if r.compression == 2:
            print_kzb1(data, r, "       ", show_slabs)
        elif r.fourcc == "PBLK":
            print_pbk1(data, r, "       ", show_slabs)
        elif r.fourcc == "HPOL":
            print_hpl1(data, r, "       ", show_slabs)
        else:
            print_plain_resource_hint(data, r, "       ")


def warn_references(
    h: Header,
    engines: list[Engine],
    pages: list[Page],
    tracks: list[Track],
    resources: list[Resource],
) -> list[str]:
    warnings: list[str] = []
    if h.header_size != 80:
        warnings.append(f"header size is {h.header_size}, expected 80")
    if h.engine_entry_size < 64 or h.page_entry_size < 24:
        warnings.append("one or more table entry sizes are too small")
    if h.track_entry_size < 32 or h.resource_entry_size < 32:
        warnings.append("one or more table entry sizes are too small")
    if h.declared_file_size != 0 and h.default_track >= max(h.track_count, 1):
        warnings.append(f"default track {h.default_track} is outside track table")
    if h.meta_resource != 0xFFFF and h.meta_resource >= len(resources):
        warnings.append("META resource index is outside resource table")
    if h.cover_resource != 0xFFFF and h.cover_resource >= len(resources):
        warnings.append("cover resource index is outside resource table")
    for i, e in enumerate(engines):
        if e.first_page + e.page_count > len(pages):
            warnings.append(f"engine {i} page range is outside page table")
    for i, p in enumerate(pages):
        if p.engine >= len(engines):
            warnings.append(f"page {i} references invalid engine {p.engine}")
    for i, t in enumerate(tracks):
        if t.page >= len(pages):
            warnings.append(f"track {i} references invalid page {t.page}")
        if t.mwk != 0xFFFF and t.mwk >= len(resources):
            warnings.append(f"track {i} references invalid MWK resource {t.mwk}")
        if t.image != 0xFFFF and t.image >= len(resources):
            warnings.append(f"track {i} references invalid IMG5 resource {t.image}")
    hpol_count = sum(r.fourcc == "HPOL" for r in resources)
    hybrid_count = sum(p.encoding == 4 for p in pages)
    if hpol_count > 1:
        warnings.append(f"{hpol_count} HPOL resources found; KSP 1.0 permits at most one")
    if hybrid_count and hpol_count != 1:
        warnings.append(f"{hybrid_count} hybrid pages but HPOL resource count is {hpol_count}")
    return warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show structural details of a KSP 1.x music package."
    )
    parser.add_argument("pack", type=Path, help="KSP file to inspect")
    parser.add_argument(
        "--pages",
        action="store_true",
        help="print every page-table entry",
    )
    parser.add_argument(
        "--slabs",
        action="store_true",
        help="print every KZB1, PBK1, and HPL1 block/slab descriptor",
    )
    parser.add_argument(
        "--track-limit",
        type=int,
        default=25,
        metavar="N",
        help="number of tracks to print; 0 prints all (default: 25)",
    )
    parser.add_argument(
        "--no-tracks",
        action="store_true",
        help="do not print tracks",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="print all tracks, pages, and slab descriptors",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = args.pack.read_bytes()
        h = parse_header(data)
        engines = parse_engines(data, h)
        pages = parse_pages(data, h)
        tracks = parse_tracks(data, h)
        resources = parse_resources(data, h)
        require_range(data, h.string_offset, h.string_size, "string table")

        print_header(args.pack, data, h)
        print_meta_if_plain(data, h, resources)
        print_engines(data, h, engines)
        print_page_summary(pages)
        if args.pages or args.all:
            print_pages(pages)
        print_resources(data, resources, args.slabs or args.all)

        if not args.no_tracks:
            limit = None if args.all or args.track_limit == 0 else max(args.track_limit, 0)
            print_tracks(data, h, tracks, pages, limit)

        warnings = warn_references(h, engines, pages, tracks, resources)
        print("\nSTATUS")
        print("-" * 78)
        if warnings:
            for warning in warnings:
                print(f"WARNING: {warning}")
        else:
            print("Basic structure and references look consistent.")
        print(
            "Note: ZX0 streams and final reconstructed-page CRCs were not decoded "
            "or validated."
        )
        return 0

    except FileNotFoundError:
        print(f"error: file not found: {args.pack}", file=sys.stderr)
    except PermissionError:
        print(f"error: cannot read: {args.pack}", file=sys.stderr)
    except KSPError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
