#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

NULL16 = 0xFFFF
NULL32 = 0xFFFFFFFF
PAGE_SIZE = 64
LOAD = 0x4000
HW_PSG = 1
RES_STREAMABLE = 2


class Zx0LiteralWriter:
    def __init__(self) -> None:
        self.out = bytearray()
        self.control_pos: int | None = None
        self.mask = 0

    def bit(self, value: int) -> None:
        if self.mask == 0:
            self.control_pos = len(self.out)
            self.out.append(0)
            self.mask = 0x80
        if value:
            assert self.control_pos is not None
            self.out[self.control_pos] |= self.mask
        self.mask >>= 1

    def byte(self, value: int) -> None:
        self.out.append(value & 0xFF)

    def gamma(self, value: int, invert: bool = False) -> None:
        if value < 1:
            raise ValueError("gamma value must be positive")
        bits = bin(value)[3:]
        for char in bits:
            self.bit(0)
            data_bit = int(char) ^ int(invert)
            self.bit(data_bit)
        self.bit(1)


def zx0_literal(data: bytes) -> bytes:
    w = Zx0LiteralWriter()
    w.gamma(len(data), False)
    for b in data:
        w.byte(b)
    w.bit(1)            # new-offset branch
    w.gamma(256, True)  # end marker
    return bytes(w.out)


def kzb1_header(blocks: list[tuple[int, bytes, bytes]], resource_offset: int) -> bytes:
    # blocks: (absolute packed offset, compressed bytes, logical bytes)
    table = bytearray()
    total_raw = 0
    for absolute, packed, raw in blocks:
        table += struct.pack('<IIII', absolute - resource_offset, len(packed), len(raw),
                             zlib.crc32(raw) & 0xFFFFFFFF)
        total_raw += len(raw)
    header = bytearray(16)
    header[:4] = b'KZB1'
    struct.pack_into('<HHII', header, 4, 16, len(blocks), total_raw, 16)
    return bytes(header + table)


def build(path: Path, case: str) -> None:
    strings = b'KSP 1.05 test engine\0Shared payload test\0'
    engine_off = 80
    page_off = engine_off + 64
    track_off = page_off + 24

    if case == 'valid-shared':
        resource_count = 31
    elif case in ('valid-nonmonotonic', 'invalid-streamable-backward', 'invalid-control-leaf'):
        resource_count = 1
    else:
        resource_count = 2
    resource_off = track_off + 32
    string_off = resource_off + resource_count * 32
    cursor = string_off + len(strings)

    template = bytes(PAGE_SIZE)
    template_off = cursor; cursor += len(template)
    page = bytes(PAGE_SIZE)
    page_payload_off = cursor; cursor += len(page)

    resources: list[tuple[bytes, int, int, int, int, int, int]] = []
    payload_chunks: list[tuple[int, bytes]] = []

    if case == 'valid-shared':
        # 29 ordinary MWK resources: each has a unique MWK header block and all
        # alias one exact compressed sample block, matching the KSP 1.05 profile.
        mwk_count = 29
        control_size = 48  # KZB1 header + two descriptors
        controls_base = cursor
        unique_base = controls_base + mwk_count * control_size
        unique_headers: list[bytes] = []
        unique_packed: list[bytes] = []
        for i in range(mwk_count):
            flags = bytearray(64); flags[0] = 1
            source = bytearray(13)
            source[2] = 0; source[3] = 0
            source[4] = 0xff; source[5] = 0xc0
            source[6] = 0xf0; source[7] = 0xf0; source[8] = 0
            source[9] = 0xf0; source[10] = 0xf7
            source[11] = 64; source[12] = 0
            header = b'MBMS\x10' + b'\x0d' + bytes([i, 0, 0]) + b'\x00' + bytes(flags) + bytes(source)
            unique_headers.append(header)
            unique_packed.append(zx0_literal(header))
        unique_offsets: list[int] = []
        pos = unique_base
        for packed_header in unique_packed:
            unique_offsets.append(pos)
            pos += len(packed_header)
        sample = bytes(((i * 7) & 0xff) for i in range(64))
        sample_packed = zx0_literal(sample)
        shared_sample_off = pos
        shared_end = shared_sample_off + len(sample_packed)
        for i in range(mwk_count):
            r_off = controls_base + i * control_size
            logical = unique_headers[i] + sample
            ctl = kzb1_header([
                (unique_offsets[i], unique_packed[i], unique_headers[i]),
                (shared_sample_off, sample_packed, sample),
            ], r_off)
            payload_chunks.append((r_off, ctl))
            payload_chunks.append((unique_offsets[i], unique_packed[i]))
            resources.append((b'MWK ', 0, 2, r_off, shared_end-r_off, len(logical),
                              zlib.crc32(logical)&0xffffffff))
        payload_chunks.append((shared_sample_off, sample_packed))
        raw_alias = b'RAW-ALIAS'
        raw_alias_off = shared_end
        payload_chunks.append((raw_alias_off, raw_alias))
        resources += [
            (b'RA01', 0, 0, raw_alias_off, len(raw_alias), len(raw_alias), zlib.crc32(raw_alias)&0xffffffff),
            (b'RA02', 0, 0, raw_alias_off, len(raw_alias), len(raw_alias), zlib.crc32(raw_alias)&0xffffffff),
        ]
        cursor = raw_alias_off + len(raw_alias)
    elif case in ('valid-nonmonotonic', 'invalid-streamable-backward'):
        raw_a, raw_b = b'FIRST-', b'SECOND'
        packed_a, packed_b = zx0_literal(raw_a), zx0_literal(raw_b)
        r_off = cursor
        block_a_off = r_off + 48
        block_b_off = block_a_off + len(packed_a)
        # Descriptor order is B then A: logical output SECONDFIRST-.
        ctl = kzb1_header([(block_b_off, packed_b, raw_b), (block_a_off, packed_a, raw_a)], r_off)
        payload_chunks += [(r_off, ctl), (block_a_off, packed_a), (block_b_off, packed_b)]
        end = block_b_off + len(packed_b)
        flags = RES_STREAMABLE if case == 'invalid-streamable-backward' else 0
        logical = raw_b + raw_a
        resources.append((b'DATA', flags, 2, r_off, end-r_off, len(logical),
                          zlib.crc32(logical)&0xffffffff))
        cursor = end
    elif case == 'invalid-control-leaf':
        raw = b'BAD'
        packed = zx0_literal(raw)
        r_off = cursor
        # Deliberately point the leaf into the 16-byte KZB1 header.
        leaf_off = r_off + 8
        ctl = kzb1_header([(leaf_off, packed, raw)], r_off)
        payload_chunks.append((r_off, ctl))
        end = r_off + max(len(ctl), 8 + len(packed))
        resources.append((b'DATA', 0, 2, r_off, end-r_off, len(raw), zlib.crc32(raw)&0xffffffff))
        cursor = end
    else:
        raw = b'OVERLAP-BLOCK'
        packed = zx0_literal(raw)
        r0_off = cursor
        r1_off = r0_off + 32
        shared_off = r1_off + 32
        if case == 'invalid-partial':
            second_off = shared_off + 1
            raw2 = raw
            crc2 = zlib.crc32(raw2)&0xffffffff
            raw_size2 = len(raw2)
        elif case == 'invalid-mismatch':
            second_off = shared_off
            raw2 = raw + b'!'
            crc2 = zlib.crc32(raw2)&0xffffffff
            raw_size2 = len(raw2)
        else:
            raise ValueError(case)
        r0_ctl = kzb1_header([(shared_off, packed, raw)], r0_off)
        # Build descriptor manually so mismatch can reference identical bytes with incompatible semantics.
        r1_ctl = bytearray(32)
        r1_ctl[:4] = b'KZB1'
        struct.pack_into('<HHII', r1_ctl, 4, 16, 1, raw_size2, 16)
        struct.pack_into('<IIII', r1_ctl, 16, second_off-r1_off, len(packed), raw_size2, crc2)
        payload_chunks += [(r0_off, r0_ctl), (r1_off, bytes(r1_ctl)), (shared_off, packed)]
        end0 = shared_off + len(packed)
        end1 = second_off + len(packed)
        resources += [
            (b'DA01', 0, 2, r0_off, end0-r0_off, len(raw), zlib.crc32(raw)&0xffffffff),
            (b'DA02', 0, 2, r1_off, end1-r1_off, raw_size2, crc2),
        ]
        cursor = max(end0, end1)

    engine = bytearray(64)
    struct.pack_into('<II', engine, 0, 0, HW_PSG)
    struct.pack_into('<HHHHHHHHHHHH', engine, 8, 1, 60, LOAD, PAGE_SIZE,
                     LOAD, LOAD+1, 0, 0, 0, 0, 1, NULL16)
    engine[32] = 0
    struct.pack_into('<IIIII', engine, 36, template_off, len(template), len(template),
                     zlib.crc32(template)&0xffffffff, 0)

    page_table = struct.pack('<HBBHHIIII', 0, 1, 0, 0, 0, page_payload_off, len(page),
                             len(page), zlib.crc32(page)&0xffffffff)
    track_table = struct.pack('<HHHHHHIIIII', 0, 0, 0, NULL16, NULL16, 0,
                              len(b'KSP 1.05 test engine\0'), NULL32, NULL32, NULL32, NULL32)
    resource_table = bytearray()
    for kind, flags, compression, off, packed_size, raw_size, crc in resources:
        resource_table += kind + struct.pack('<HBBIIIIII', flags, compression, 0, off,
                                             packed_size, raw_size, crc, 0, 0)

    index = bytes(engine) + page_table + track_table + bytes(resource_table) + strings
    header = bytearray(80)
    header[:4] = b'KSP1'
    struct.pack_into('<HHII', header, 4, 80, 5, 0, cursor)
    struct.pack_into('<IHH', header, 16, engine_off, 1, 64)
    struct.pack_into('<IHH', header, 24, page_off, 1, 24)
    struct.pack_into('<IHH', header, 32, track_off, 1, 32)
    struct.pack_into('<IHH', header, 40, resource_off, len(resources), 32)
    struct.pack_into('<II', header, 48, string_off, len(strings))
    struct.pack_into('<HHHH', header, 56, 0, NULL16, NULL16, 0)
    struct.pack_into('<I', header, 68, zlib.crc32(index)&0xffffffff)
    tmp = bytearray(header); struct.pack_into('<I', tmp, 64, 0)
    struct.pack_into('<I', header, 64, zlib.crc32(tmp)&0xffffffff)

    image = bytearray(cursor)
    image[:80] = header
    image[engine_off:engine_off+64] = engine
    image[page_off:page_off+24] = page_table
    image[track_off:track_off+32] = track_table
    image[resource_off:resource_off+len(resource_table)] = resource_table
    image[string_off:string_off+len(strings)] = strings
    image[template_off:template_off+len(template)] = template
    image[page_payload_off:page_payload_off+len(page)] = page
    for off, data in payload_chunks:
        image[off:off+len(data)] = data
    path.write_bytes(image)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('output', type=Path)
    ap.add_argument('--case', default='valid-shared', choices=[
        'valid-shared', 'valid-nonmonotonic', 'invalid-partial', 'invalid-mismatch',
        'invalid-streamable-backward', 'invalid-control-leaf'])
    args = ap.parse_args()
    build(args.output, args.case)


if __name__ == '__main__':
    main()
