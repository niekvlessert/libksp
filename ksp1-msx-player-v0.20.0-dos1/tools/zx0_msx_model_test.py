#!/usr/bin/env python3
"""Regression model for KSP1PLAY's streaming ZX0 decoder.

The model deliberately refills input in 512-byte chunks, matching the MSX COM.
It checks the Nemesis 3 engine template and every compressed sparse overlay.
It also verifies the two source-level register-corruption fixes that caused the
0.5 runtime failure.
"""
from __future__ import annotations

import argparse
import binascii
import struct
from pathlib import Path


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from('<H', b, o)[0]


def u32(b: bytes, o: int) -> int:
    return struct.unpack_from('<I', b, o)[0]


class ChunkedZX0:
    def __init__(self, packed: bytes, output_size: int, chunk_size: int = 512):
        self.packed = packed
        self.output_size = output_size
        self.chunk_size = chunk_size
        self.file_pos = 0
        self.buf = b''
        self.buf_pos = 0
        self.bit_value = 0
        self.bit_mask = 0
        self.last_byte = 0
        self.backtrack = False
        self.out = bytearray()
        self.refills = 0

    def refill(self) -> None:
        if self.file_pos >= len(self.packed):
            raise ValueError('truncated ZX0 input')
        end = min(len(self.packed), self.file_pos + self.chunk_size)
        self.buf = self.packed[self.file_pos:end]
        self.file_pos = end
        self.buf_pos = 0
        self.refills += 1

    def byte(self) -> int:
        if self.buf_pos >= len(self.buf):
            self.refill()
        value = self.buf[self.buf_pos]
        self.buf_pos += 1
        self.last_byte = value
        return value

    def bit(self) -> int:
        if self.backtrack:
            self.backtrack = False
            return self.last_byte & 1
        if self.bit_mask == 0:
            self.bit_value = self.byte()
            self.bit_mask = 0x80
        value = 1 if self.bit_value & self.bit_mask else 0
        self.bit_mask >>= 1
        return value

    def gamma(self, invert: int) -> int:
        # Mirrors the assembly BC implementation. zx_read_bit must preserve BC.
        value = 1
        while self.bit() == 0:
            value = (value << 1) | (self.bit() ^ invert)
            if value > 0xFFFF:
                raise ValueError('16-bit Elias gamma overflow')
        return value

    def literals(self, count: int) -> None:
        for _ in range(count):
            if len(self.out) >= self.output_size:
                raise ValueError('literal output overflow')
            self.out.append(self.byte())

    def match(self, offset: int, count: int) -> None:
        if not 0 < offset <= len(self.out):
            raise ValueError(f'invalid match offset {offset} at output {len(self.out)}')
        for _ in range(count):
            if len(self.out) >= self.output_size:
                raise ValueError('match output overflow')
            self.out.append(self.out[-offset])

    def decode(self) -> bytes:
        offset = 1
        self.literals(self.gamma(0))
        while True:
            if len(self.out) == self.output_size:
                return bytes(self.out)
            if self.bit() == 0:
                self.match(offset, self.gamma(0))
                if len(self.out) == self.output_size:
                    return bytes(self.out)
                if self.bit() == 0:
                    self.literals(self.gamma(0))
                    continue
            while True:
                msb = self.gamma(1)
                if msb == 256:
                    if len(self.out) != self.output_size:
                        raise ValueError('premature ZX0 end marker')
                    return bytes(self.out)
                lsb = self.byte()
                offset = msb * 128 - (lsb >> 1)
                self.backtrack = True
                self.match(offset, self.gamma(0) + 1)
                if len(self.out) == self.output_size:
                    return bytes(self.out)
                if self.bit() == 0:
                    self.literals(self.gamma(0))
                    break


def decode(packed: bytes, raw_size: int) -> tuple[bytes, int]:
    dec = ChunkedZX0(packed, raw_size)
    return dec.decode(), dec.refills


def validate_ksp(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:4] != b'KSP1':
        raise ValueError('not KSP1')
    engine_off = u32(data, 0x10)
    page_off = u32(data, 0x18)
    page_count = u16(data, 0x1C)
    e = data[engine_off:engine_off + 64]
    if len(e) != 64:
        raise ValueError('short engine entry')
    template_comp = e[0x20]
    template_off = u32(e, 0x24)
    template_packed = u32(e, 0x28)
    template_raw = u32(e, 0x2C)
    template_crc = u32(e, 0x30)
    payload = data[template_off:template_off + template_packed]
    if template_comp == 1:
        template, refills = decode(payload, template_raw)
    elif template_comp == 0:
        template, refills = payload, 0
    else:
        raise ValueError('unsupported template compression')
    if len(template) != template_raw or (binascii.crc32(template) & 0xFFFFFFFF) != template_crc:
        raise ValueError('template decode/CRC mismatch')

    compressed_pages = 0
    total_refills = refills
    for i in range(page_count):
        pe = data[page_off + i * 24:page_off + (i + 1) * 24]
        if len(pe) != 24:
            raise ValueError('short page entry')
        encoding = pe[2]
        comp = pe[3]
        po = u32(pe, 8)
        ps = u32(pe, 12)
        raw = u32(pe, 16)
        if encoding != 0:
            continue
        packed = data[po:po + ps]
        if comp == 1:
            overlay, r = decode(packed, raw)
            total_refills += r
            compressed_pages += 1
        elif comp == 0:
            overlay = packed
        else:
            raise ValueError(f'page {i}: unsupported compression')
        if len(overlay) != raw:
            raise ValueError(f'page {i}: overlay size mismatch')
        page = bytearray(template)
        pos = 0
        while pos < len(overlay):
            if pos + 4 > len(overlay):
                raise ValueError(f'page {i}: truncated sparse record')
            dst, count = struct.unpack_from('<HH', overlay, pos)
            pos += 4
            if count == 0 or pos + count > len(overlay) or dst + count > len(page):
                raise ValueError(f'page {i}: invalid sparse record')
            page[dst:dst + count] = overlay[pos:pos + count]
            pos += count
        expected_crc = u32(pe, 20)
        if expected_crc and (binascii.crc32(page) & 0xFFFFFFFF) != expected_crc:
            raise ValueError(f'page {i}: final CRC mismatch')
    return compressed_pages, total_refills


def validate_source(path: Path) -> None:
    source = path.read_text(encoding='utf-8')
    bit_start = source.index('zx_have_mask:')
    bit_end = source.index('zx_gamma_normal:', bit_start)
    bit_body = source[bit_start:bit_end]
    if 'ld b,a' in bit_body or 'ld b, a' in bit_body:
        raise ValueError('zx_read_bit still corrupts BC')
    print_start = source.index('print_u16_loop:')
    print_end = source.index('div10_u16:', print_start)
    print_body = source[print_start:print_end]
    required = ['push de', 'call div10_u16', 'pop de']
    positions = [print_body.find(item) for item in required]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise ValueError('print_u16 does not preserve its DE output pointer')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('ksp', type=Path)
    ap.add_argument('--source', type=Path, required=True)
    args = ap.parse_args()
    validate_source(args.source)
    pages, refills = validate_ksp(args.ksp)
    print(f'{args.ksp.name}: chunked ZX0 model passed; '
          f'{pages} compressed sparse pages, {refills} total 512-byte refills')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
