#!/usr/bin/env python3
"""Regression model for KSP 1.01 PAGE2_RUNTIME/PAGE3_WORKRAM support."""
from __future__ import annotations

import argparse
import struct
import tempfile
from pathlib import Path

from ksp1_validate_sparse import validate
from ksp1_validate import KSPError


def patch_pack(source: Path, *, minor: int, flags: int, hardware: int) -> bytes:
    data = bytearray(source.read_bytes())
    engine_off = struct.unpack_from('<I', data, 0x10)[0]
    struct.pack_into('<H', data, 0x06, minor)
    struct.pack_into('<I', data, engine_off + 0x00, flags)
    struct.pack_into('<I', data, engine_off + 0x04, hardware)
    # Header/index CRCs are optional. Clear them after mutating descriptors.
    struct.pack_into('<I', data, 0x40, 0)
    struct.pack_into('<I', data, 0x44, 0)
    return bytes(data)


def run_case(source: Path, *, minor: int, flags: int, hardware: int, accepted: bool) -> None:
    payload = patch_pack(source, minor=minor, flags=flags, hardware=hardware)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'case.ksp'
        path.write_bytes(payload)
        try:
            validate(path)
        except KSPError:
            if accepted:
                raise
        else:
            if not accepted:
                raise SystemExit(
                    f'expected rejection: minor={minor} flags={flags:#x} hardware={hardware:#x}'
                )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--sample', type=Path, required=True)
    ns = ap.parse_args()

    text = ns.source.read_text(encoding='utf-8')
    required = (
        'page2_runtime_profile:',
        'page3_workram_profile:',
        'allocate_page3_workram_segment:',
        'free_page3_workram_segment:',
        'ld a,(mapped_p1)\n    jp map_p2',
        'ld a,(engine_p3_segment)\n    out (0xFF),a',
        'ld a,(original_p3)\n    out (0xFF),a',
        'ld (dynamic_saved_p3),a',
        'ld a,(dynamic_saved_p3)\n    out (0xFF),a',
        'and 0xE2',
        'and 0x18',
        'and 0x0E',
    )
    for marker in required:
        if marker not in text:
            raise SystemExit(f'missing KSP 1.01 runtime marker: {marker}')

    # PAGE3_WORKRAM may coexist with SCC hardware.
    run_case(ns.sample, minor=1, flags=0x10, hardware=0x03, accepted=True)
    # PAGE2_RUNTIME is valid for a non-SCC engine in KSP 1.01.
    run_case(ns.sample, minor=1, flags=0x08, hardware=0x01, accepted=True)
    # Both memory flags are valid together for a non-SCC engine.
    run_case(ns.sample, minor=1, flags=0x18, hardware=0x01, accepted=True)
    # KSP 1.00 may not use either new memory-layout flag.
    run_case(ns.sample, minor=0, flags=0x08, hardware=0x01, accepted=False)
    run_case(ns.sample, minor=0, flags=0x10, hardware=0x01, accepted=False)
    # PAGE2_RUNTIME conflicts with all SCC address-space requirements.
    run_case(ns.sample, minor=1, flags=0x08, hardware=0x03, accepted=False)
    run_case(ns.sample, minor=1, flags=0x08, hardware=0x08, accepted=False)
    # Unknown future engine bits remain rejected.
    run_case(ns.sample, minor=1, flags=0x20, hardware=0x01, accepted=False)

    print('KSP 1.01 PAGE2_RUNTIME/PAGE3_WORKRAM model passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
