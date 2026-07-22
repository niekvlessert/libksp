#!/usr/bin/env python3
"""Validate KSP 1.00/1.01 hybrid HPOL packages and the KSP1PLAY MSX profile."""
from __future__ import annotations

import argparse
import binascii
import json
import struct
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from('<H', data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from('<I', data, off)[0]


def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


class KSPError(ValueError):
    pass


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
            raise KSPError('truncated ZX0 stream')
        value = self.packed[self.ip]
        self.ip += 1
        self.last_byte = value
        return value

    def bit(self) -> int:
        if self.backtrack:
            self.backtrack = False
            return self.last_byte & 1
        if not self.bit_mask:
            self.bit_value = self.byte()
            self.bit_mask = 0x80
        value = 1 if self.bit_value & self.bit_mask else 0
        self.bit_mask >>= 1
        return value

    def gamma(self, invert: int) -> int:
        value = 1
        while not self.bit():
            value = (value << 1) | (self.bit() ^ invert)
            if value > 0x7FFFFFFF:
                raise KSPError('ZX0 gamma overflow')
        return value

    def literal(self, count: int) -> None:
        for _ in range(count):
            if len(self.out) >= self.output_size:
                raise KSPError('ZX0 output overflow')
            self.out.append(self.byte())

    def match(self, offset: int, count: int) -> None:
        if offset <= 0 or offset > len(self.out):
            raise KSPError(f'invalid ZX0 offset {offset}')
        for _ in range(count):
            if len(self.out) >= self.output_size:
                raise KSPError('ZX0 output overflow')
            self.out.append(self.out[-offset])

    def decode(self) -> bytes:
        offset = 1
        self.literal(self.gamma(0))
        while True:
            bit = self.bit()
            if not bit:
                self.match(offset, self.gamma(0))
                bit = self.bit()
                if not bit:
                    self.literal(self.gamma(0))
                    continue
            while True:
                msb = self.gamma(1)
                if msb == 256:
                    if len(self.out) != self.output_size:
                        raise KSPError(
                            f'ZX0 size mismatch: {len(self.out)} != {self.output_size}'
                        )
                    return bytes(self.out)
                lsb = self.byte()
                offset = msb * 128 - (lsb >> 1)
                self.backtrack = True
                self.match(offset, self.gamma(0) + 1)
                if not self.bit():
                    self.literal(self.gamma(0))
                    break


def zx0(data: bytes, size: int) -> bytes:
    if size == 0:
        if data:
            raise KSPError('non-empty ZX0 stream for zero-size object')
        return b''
    return ZX0Reader(data, size).decode()


@dataclass
class ProfileResult:
    file: str
    file_size: int
    tracks: int
    pages: int
    engine_load: int
    engine_size: int
    hardware_flags: int
    tick_hz: int
    block_size: int
    position_count: int
    hot_raw: int
    warm_raw: int
    cold_raw: int
    cold_slabs: int
    reconstructed_pages: int
    unique_pages: int
    profile_compatible: bool
    incompatibilities: list[str]


def bounds(data: bytes, off: int, size: int, what: str) -> bytes:
    if off < 0 or size < 0 or off + size > len(data):
        raise KSPError(f'{what} outside file: off={off} size={size}')
    return data[off:off + size]


def parse_hybrid(path: Path, reconstruct: bool = True) -> ProfileResult:
    data = path.read_bytes()
    if len(data) < 80 or data[:4] != b'KSP1':
        raise KSPError('not a KSP1 file')
    minor = u16(data, 6)
    if u16(data, 4) != 80 or minor > 1:
        raise KSPError('unsupported KSP header version')
    if u32(data, 0x0C) != len(data):
        raise KSPError('file-size field mismatch')

    engine_off, engine_count, engine_size = u32(data, 0x10), u16(data, 0x14), u16(data, 0x16)
    page_off, page_count, page_size = u32(data, 0x18), u16(data, 0x1C), u16(data, 0x1E)
    track_off, track_count, track_size = u32(data, 0x20), u16(data, 0x24), u16(data, 0x26)
    resource_off, resource_count, resource_size = u32(data, 0x28), u16(data, 0x2C), u16(data, 0x2E)
    if not engine_count or engine_size < 64 or page_size < 24 or track_size < 32 or resource_size < 32:
        raise KSPError('invalid table dimensions')
    bounds(data, engine_off, engine_count * engine_size, 'engine table')
    bounds(data, page_off, page_count * page_size, 'page table')
    bounds(data, track_off, track_count * track_size, 'track table')
    bounds(data, resource_off, resource_count * resource_size, 'resource table')

    e = bounds(data, engine_off, 64, 'engine 0')
    engine_flags = u32(e, 0)
    hardware_flags = u32(e, 4)
    tick_hz = u16(e, 10)
    load_address, runtime_size = u16(e, 12), u16(e, 14)
    template_compression = e[32]
    template_off, template_packed, template_raw = u32(e, 36), u32(e, 40), u32(e, 44)
    template = bounds(data, template_off, template_packed, 'engine template')
    if template_compression == 1:
        template = zx0(template, template_raw)
    elif template_compression == 0:
        if template_packed != template_raw:
            raise KSPError('raw template size mismatch')
    else:
        raise KSPError(f'unsupported template compression {template_compression}')
    if len(template) != runtime_size:
        raise KSPError('template runtime size mismatch')
    template_crc = u32(e, 48)
    if template_crc and crc32(template) != template_crc:
        raise KSPError('template CRC mismatch')

    hpol_entry: bytes | None = None
    for i in range(resource_count):
        r = bounds(data, resource_off + i * resource_size, 32, f'resource {i}')
        if r[:4] == b'HPOL':
            hpol_entry = r
            break
    if hpol_entry is None:
        raise KSPError('HPOL resource missing')
    hpol_off, hpol_size = u32(hpol_entry, 8), u32(hpol_entry, 12)
    hpol = bounds(data, hpol_off, hpol_size, 'HPOL')
    if len(hpol) < 96 or hpol[:4] != b'HPL1' or u16(hpol, 4) != 96 or u16(hpol, 6) != 1:
        raise KSPError('invalid HPL1 header')

    block_size = u16(hpol, 8)
    position_count = u16(hpol, 10)
    hpl_pages = u16(hpol, 12)
    hot_count, warm_count, cold_count, slab_count = (u16(hpol, x) for x in (14, 16, 18, 20))
    if hpl_pages != page_count:
        raise KSPError('HPL page count mismatch')
    if block_size not in (64, 128, 256, 512):
        raise KSPError('unsupported HPL block size')

    positions_off = u32(hpol, 24)
    maps_off, maps_packed, maps_raw = u32(hpol, 28), u32(hpol, 32), u32(hpol, 36)
    hot_off, hot_packed, hot_raw = u32(hpol, 40), u32(hpol, 44), u32(hpol, 48)
    warm_off, warm_packed, warm_raw = u32(hpol, 52), u32(hpol, 56), u32(hpol, 60)
    cold_table_off = u32(hpol, 64)
    if hot_raw != hot_count * block_size or warm_raw != warm_count * block_size:
        raise KSPError('hot/warm count and size mismatch')
    if maps_raw != page_count * position_count * 2:
        raise KSPError('map matrix dimensions mismatch')
    positions_data = bounds(hpol, positions_off, position_count * 2, 'positions')
    positions = list(struct.unpack_from(f'<{position_count}H', positions_data, 0))
    for pos in positions:
        if pos + block_size > runtime_size:
            raise KSPError(f'position {pos:#x} exceeds runtime page')

    maps = zx0(bounds(hpol, maps_off, maps_packed, 'maps stream'), maps_raw)
    hot = zx0(bounds(hpol, hot_off, hot_packed, 'hot stream'), hot_raw)
    warm = zx0(bounds(hpol, warm_off, warm_packed, 'warm stream'), warm_raw)

    cold_parts: list[bytes] = []
    cold_raw_total = 0
    for i in range(slab_count):
        desc = bounds(hpol, cold_table_off + i * 16, 16, f'cold descriptor {i}')
        po, ps, us, comp, reserved, expected_crc = struct.unpack_from('<IIHBBI', desc, 0)
        if reserved or comp not in (0, 1) or us > 16384:
            raise KSPError(f'invalid cold descriptor {i}')
        packed = bounds(hpol, po, ps, f'cold stream {i}')
        raw = zx0(packed, us) if comp == 1 else packed
        if len(raw) != us:
            raise KSPError(f'cold slab {i} size mismatch')
        if expected_crc and crc32(raw) != expected_crc:
            raise KSPError(f'cold slab {i} CRC mismatch')
        cold_parts.append(raw)
        cold_raw_total += us
    cold = b''.join(cold_parts)
    if len(cold) < cold_count * block_size:
        raise KSPError('cold pool shorter than block count')
    pool = hot + warm + cold

    reconstructed = 0
    page_hashes: set[int] = set()
    if reconstruct:
        for page_index in range(page_count):
            p = bounds(data, page_off + page_index * page_size, 24, f'page {page_index}')
            if u16(p, 0) != 0 or p[2] != 4:
                raise KSPError(f'page {page_index}: not engine-0 HPOL encoding')
            row = maps[page_index * position_count * 2:(page_index + 1) * position_count * 2]
            page = bytearray(template)
            for i, dest in enumerate(positions):
                block_id = u16(row, i * 2)
                source = block_id * block_size
                if source + block_size > len(pool):
                    raise KSPError(f'page {page_index}: invalid block {block_id}')
                page[dest:dest + block_size] = pool[source:source + block_size]
            expected = u32(p, 20)
            actual = crc32(page)
            if expected and actual != expected:
                raise KSPError(
                    f'page {page_index}: CRC mismatch {actual:08x} != {expected:08x}'
                )
            reconstructed += 1
            page_hashes.add(actual)

    problems: list[str] = []
    if engine_count != 1:
        problems.append('player supports exactly one engine')
    if engine_flags & ~0x1D or (engine_flags & 0x18 and minor < 1):
        problems.append(f'engine flags {engine_flags:#x} require unsupported runtime features')
    if hardware_flags & ~0x5F:
        problems.append(
            f'hardware flags {hardware_flags:#x} are outside the PSG/SCC/SCC+/dual-SCC/YM2413/OPL4 profile'
        )
    if hardware_flags & 0x08 and hardware_flags & 0x04:
        problems.append('dual-SCC currently requires two normal SCC devices, not SCC+')
    if engine_flags & 0x08 and hardware_flags & 0x0E:
        problems.append('PAGE2_RUNTIME conflicts with SCC, SCC+ and dual-SCC hardware')
    if load_address != 0x4000 or runtime_size != 0x4000:
        problems.append(f'engine must load at 0x4000 with size 0x4000, got {load_address:#x}/{runtime_size:#x}')
    if tick_hz not in (50, 60):
        problems.append(f'tick frequency {tick_hz} is unsupported')
    if hot_raw > 48 * 1024:
        problems.append(f'hot pool {hot_raw} exceeds 48 KiB')
    if warm_raw > 96 * 1024:
        problems.append(f'warm pool {warm_raw} exceeds 96 KiB')
    if maps_raw > 0x4000:
        problems.append(f'map matrix {maps_raw} exceeds the dedicated 16 KiB mapper segment')
    if position_count * 2 >= 0x200:
        problems.append('position table exceeds the page-0 position buffer')
    if template_packed >= 65536 or maps_packed >= 65536 or hot_packed >= 65536 or warm_packed >= 65536:
        problems.append('one whole-stream packed object exceeds 16-bit streaming size')

    return ProfileResult(
        file=path.name,
        file_size=len(data),
        tracks=track_count,
        pages=page_count,
        engine_load=load_address,
        engine_size=runtime_size,
        hardware_flags=hardware_flags,
        tick_hz=tick_hz,
        block_size=block_size,
        position_count=position_count,
        hot_raw=hot_raw,
        warm_raw=warm_raw,
        cold_raw=cold_raw_total,
        cold_slabs=slab_count,
        reconstructed_pages=reconstructed,
        unique_pages=len(page_hashes),
        profile_compatible=not problems,
        incompatibilities=problems,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    results: list[dict[str, Any]] = []
    failed = False
    for path in args.files:
        try:
            result = parse_hybrid(path)
            results.append(asdict(result))
            state = 'compatible' if result.profile_compatible else 'structurally valid, incompatible'
            print(f'{path.name}: {state}; {result.reconstructed_pages} pages reconstructed')
            for problem in result.incompatibilities:
                print(f'  - {problem}')
        except Exception as exc:
            failed = True
            results.append({'file': path.name, 'error': str(exc)})
            print(f'{path.name}: ERROR: {exc}')
    if args.json:
        args.json.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
