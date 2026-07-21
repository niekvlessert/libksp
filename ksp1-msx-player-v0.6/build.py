#!/usr/bin/env python3
"""Build KSP1PLAY.COM using the bundled two-pass Z80 assembler."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / 'build'


def run(*args: str) -> None:
    print('+', ' '.join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def parse_symbols(path: Path) -> dict[str, int]:
    symbols: dict[str, int] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if ' = ' in line:
            name, value = line.split(' = ', 1)
            symbols[name] = int(value, 0)
    return symbols


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    com = BUILD / 'KSP1PLAY.COM'
    sym = BUILD / 'KSP1PLAY.sym'
    listing = BUILD / 'KSP1PLAY.lst'
    run(sys.executable, 'tools/z80asm.py', 'src/KSP1PLAY.asm', str(com), str(sym), str(listing))

    symbols = parse_symbols(sym)
    binary = com.read_bytes()
    # Regression for the bundled assembler: quoted character literals must
    # preserve case. Earlier releases accidentally assembled 'KSP1' as 'ksp1'.
    magic_compare = bytes([0xFE, ord('K'), 0xC2])
    if magic_compare not in binary or bytes([0xFE, ord('S'), 0xC2]) not in binary or bytes([0xFE, ord('P'), 0xC2]) not in binary:
        raise SystemExit('assembler character-literal case regression')
    if bytes([0xFE, ord('k'), 0xC2]) in binary[:0x600]:
        raise SystemExit('lowercase KSP magic comparison found in COM')
    if symbols.get('start') != 0x0100:
        raise SystemExit('start symbol is not 0100h')
    program_end = symbols.get('program_end', 0x0100 + len(binary))
    if program_end > 0x17E0:
        raise SystemExit(f'resident COM overlaps reserved page-0 gateway: end={program_end:04X}h')
    if 0x1F00 + 0x1800 > 0x3700:
        raise SystemExit('page-0 map buffer exceeds its allocation')
    if 0x3700 >= 0x3FF0:
        raise SystemExit('invalid page-0 stack guard')
    if symbols.get('filename', 0) >= 0x1800:
        raise SystemExit('resident COM variables overlap page-0 KSP buffers')

    report_path = BUILD / 'KSP_PROFILE_REPORT.json'
    run(
        sys.executable,
        'tools/ksp1_validate.py',
        'samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp',
        'samples/XAK_GAZELL_KSP1_HYBRID_RAM_VRAM.ksp',
        '--json', str(report_path),
    )
    reports = json.loads(report_path.read_text(encoding='utf-8'))
    solid = next(item for item in reports if item['file'].startswith('SOLIDSNK'))
    gazell = next(item for item in reports if item['file'].startswith('XAK_GAZELL'))
    if not solid.get('profile_compatible') or solid.get('reconstructed_pages') != 43:
        raise SystemExit('Solid Snake regression validation failed')
    if gazell.get('profile_compatible'):
        raise SystemExit('Gazell must remain rejected until engine relocation/Y8950 support')

    sparse_report = BUILD / 'SPARSE_PROFILE_REPORT.json'
    run(
        sys.executable,
        'tools/ksp1_validate_sparse.py',
        'samples/SOLIDSNK_KSP1_SPARSE_REGRESSION.ksp',
        '--json', str(sparse_report),
    )
    sparse = json.loads(sparse_report.read_text(encoding='utf-8'))[0]
    if sparse.get('page_encodings') != {'sparse overlay': 43} or not sparse.get('all_page_crcs_valid'):
        raise SystemExit('sparse-overlay regression validation failed')

    nemesis_report = BUILD / 'NEMESIS3_PROFILE_REPORT.json'
    run(
        sys.executable,
        'tools/ksp1_validate_sparse.py',
        'samples/NEMESIS3.KSP',
        '--json', str(nemesis_report),
    )
    nemesis = json.loads(nemesis_report.read_text(encoding='utf-8'))[0]
    if nemesis.get('page_encodings') != {'sparse overlay': 24} or not nemesis.get('all_page_crcs_valid'):
        raise SystemExit('Nemesis 3 sparse-overlay validation failed')

    run(
        sys.executable,
        'tools/zx0_msx_model_test.py',
        'samples/NEMESIS3.KSP',
        '--source', 'src/KSP1PLAY.asm',
    )

    run(
        sys.executable,
        'tools/make_test_disk.py',
        'build/KSP1SPRS.DSK',
        '--com', str(com),
        '--ksp', 'samples/SOLIDSNK_KSP1_SPARSE_REGRESSION.ksp',
        '--ksp-name', 'SOLIDSNK.KSP',
    )
    run(
        sys.executable,
        'tools/make_test_disk.py',
        'build/KSP1HYBR.DSK',
        '--com', str(com),
        '--ksp', 'samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp',
        '--ksp-name', 'SOLIDSNK.KSP',
    )

    run(
        sys.executable,
        'tools/make_test_disk.py',
        'build/KSP1NEM3.DSK',
        '--com', str(com),
        '--ksp', 'samples/NEMESIS3.KSP',
        '--ksp-name', 'NEMESIS3.KSP',
        '--track', '0',
        '--slot', '2',
    )

    digest = hashlib.sha256(binary).hexdigest()
    (BUILD / 'SHA256SUMS').write_text(
        f'{digest}  KSP1PLAY.COM\n'
        f'{hashlib.sha256((BUILD / "KSP1SPRS.DSK").read_bytes()).hexdigest()}  KSP1SPRS.DSK\n'
        f'{hashlib.sha256((BUILD / "KSP1HYBR.DSK").read_bytes()).hexdigest()}  KSP1HYBR.DSK\n'
        f'{hashlib.sha256((BUILD / "KSP1NEM3.DSK").read_bytes()).hexdigest()}  KSP1NEM3.DSK\n',
        encoding='ascii',
    )
    print(f'KSP1PLAY.COM: {len(binary)} bytes, SHA-256 {digest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
