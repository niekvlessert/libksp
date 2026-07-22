#!/usr/bin/env python3
"""Build a menu-start test disk containing several bundled KSP profiles."""
from pathlib import Path
from make_test_disk import build

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'build' / 'KSP1MENU.DSK'
files = [
    ('KSP1PLAY.COM', (ROOT / 'build' / 'KSP1PLAY.COM').read_bytes()),
    ('NEMESIS3.KSP', (ROOT / 'samples' / 'NEMESIS3.KSP').read_bytes()),
    ('NEM3P3.KSP', (ROOT / 'samples' / 'NEMESIS3_KSP101_PAGE3_TEST.KSP').read_bytes()),
    ('SOLIDSP.KSP', (ROOT / 'samples' / 'SOLIDSNK_KSP1_SPARSE_REGRESSION.ksp').read_bytes()),
    ('SOLIDHP.KSP', (ROOT / 'samples' / 'SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp').read_bytes()),
    ('README.TXT', (
        'KSP1PLAY 0.20.0 MSX-DOS1 standalone test disk\r\n'
        'Mount with an MSX-DOS1 system disk or cartridge.\r\n'
        'Run KSP1PLAY without arguments.\r\n'
        'Package menu: arrows + ENTER. Track menu: arrows, ENTER/SPACE. ESC goes back.\r\n'
    ).encode('ascii')),
    ('AUTOEXEC.BAT', b'KSP1PLAY\r\n'),
]
OUT.write_bytes(build(files))
print(f'wrote {OUT} ({OUT.stat().st_size} bytes)')
