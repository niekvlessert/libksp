#!/usr/bin/env python3
"""Validate KSP 1.0 sparse-overlay and complete-page packages."""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path
from ksp1_validate import KSPError, bounds, crc32, u16, u32, zx0


def decode_object(data: bytes, off: int, packed: int, raw: int, comp: int, label: str) -> bytes:
    payload = bounds(data, off, packed, label)
    if comp == 0:
        if packed != raw:
            raise KSPError(f'{label}: raw packed/unpacked sizes differ')
        return payload
    if comp == 1:
        return zx0(payload, raw)
    raise KSPError(f'{label}: unsupported compression {comp}')


def apply_sparse(template: bytes, raw: bytes, page_index: int) -> bytes:
    page = bytearray(template)
    cursor = 0
    previous_end = 0
    while cursor < len(raw):
        if len(raw) - cursor < 4:
            raise KSPError(f'page {page_index}: truncated sparse record')
        destination, count = struct.unpack_from('<HH', raw, cursor)
        cursor += 4
        if count == 0 or destination < previous_end or destination + count > len(page):
            raise KSPError(f'page {page_index}: invalid sparse record')
        if cursor + count > len(raw):
            raise KSPError(f'page {page_index}: sparse data outside payload')
        page[destination:destination + count] = raw[cursor:cursor + count]
        cursor += count
        previous_end = destination + count
    return bytes(page)


def validate(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 80 or data[:4] != b'KSP1' or u16(data, 4) != 80 or u16(data, 6) != 0:
        raise KSPError('not supported KSP 1.0')
    if u32(data, 12) != len(data):
        raise KSPError('file-size mismatch')
    eo, ec, es = u32(data,16), u16(data,20), u16(data,22)
    po, pc, ps = u32(data,24), u16(data,28), u16(data,30)
    to, tc, ts = u32(data,32), u16(data,36), u16(data,38)
    if ec != 1 or es < 64 or ps < 24 or ts < 32:
        raise KSPError('unsupported table dimensions')
    engine = bounds(data, eo, 64, 'engine')
    template = decode_object(data, u32(engine,36), u32(engine,40), u32(engine,44), engine[32], 'template')
    if len(template) != 0x4000 or u16(engine,12) != 0x4000 or u16(engine,14) != 0x4000:
        raise KSPError('unsupported engine page')
    if u32(engine,48) and crc32(template) != u32(engine,48):
        raise KSPError('template CRC mismatch')
    encodings = {}
    pages = []
    for i in range(pc):
        p = bounds(data, po + i*ps, 24, f'page {i}')
        if u16(p,0) != 0 or u16(p,4) != 0:
            raise KSPError(f'page {i}: unsupported owner/flags')
        enc, comp = p[2], p[3]
        raw = decode_object(data, u32(p,8), u32(p,12), u32(p,16), comp, f'page {i} payload')
        if enc == 0:
            page = apply_sparse(template, raw, i)
            name = 'sparse overlay'
        elif enc == 1:
            if len(raw) != 0x4000:
                raise KSPError(f'page {i}: complete page size mismatch')
            page = raw
            name = 'complete page'
        else:
            raise KSPError(f'page {i}: unsupported encoding {enc}')
        expected = u32(p,20)
        if expected and crc32(page) != expected:
            raise KSPError(f'page {i}: CRC mismatch')
        pages.append(page)
        encodings[name] = encodings.get(name, 0) + 1
    for i in range(tc):
        t = bounds(data, to + i*ts, 32, f'track {i}')
        if u16(t,0) >= pc:
            raise KSPError(f'track {i}: page out of range')
    return {
        'file': path.name,
        'bytes': len(data),
        'tracks': tc,
        'pages': pc,
        'page_encodings': encodings,
        'maximum_page_payload_raw': max((u32(data, po+i*ps+16) for i in range(pc)), default=0),
        'all_page_crcs_valid': True,
        'profile_compatible': True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+', type=Path)
    ap.add_argument('--json', type=Path)
    args = ap.parse_args()
    reports=[]
    for path in args.files:
        report=validate(path); reports.append(report)
        print(f"{path.name}: {report['pages']} pages, {report['page_encodings']}")
    if args.json:
        args.json.write_text(json.dumps(reports,indent=2),encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
