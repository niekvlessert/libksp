#!/usr/bin/env python3
"""Build the standalone MSX-DOS1 KSP1PLAY.COM."""
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
    if binary.count(bytes([0xED, 0x57])) != 2:
        raise SystemExit('VDP guard and dynamic gateway must contain two LD A,I instructions')
    source_text = (ROOT / 'src/KSP1PLAY.asm').read_text(encoding='utf-8')
    for forbidden in ('EXTBIO', 'DOS_OPEN', 'DOS_CLOSE', 'DOS_READ', 'DOS_SEEK', 'DOS_TERM        equ 0x62'):
        if forbidden in source_text:
            raise SystemExit(f'DOS2 dependency remains in DOS1 build: {forbidden}')
    for required in ('DOS_FOPEN       equ 0x0F', 'DOS_RDBLK       equ 0x27',
                     'mapper_probe_loop:', 'mapper_build_pool:', 'fcb_prepare_filename:'):
        if required not in source_text:
            raise SystemExit(f'missing DOS1 backend marker: {required}')
    for required in ('call vdp_irq_begin', 'call vdp_irq_end', 'zx_decode_stream:', 'cache_written:'):
        if required not in source_text:
            raise SystemExit(f'missing VRAM-cache regression marker: {required}')
    for required in (
        'call configure_engine_refresh',
        'call restore_refresh_rate',
        'ld (RG9SAV),a',
        'and 0xFD',
        'or 0x02',
    ):
        if required not in source_text:
            raise SystemExit(f'missing automatic refresh-rate marker: {required}')
    for required in (
        'and 0xA0',
        'call validate_required_hardware',
        'call upload_current_mwk',
        'call prepare_opl4_init',
        "cp 'K'",
        "cp 'Z'",
        "cp 'B'",
        "cp '1'",
        'out (PORT_OPL4_WAVE_D),a',
        'dual_scc_select_a:',
        'dual_scc_select_b:',
        'dual_scc_restore_ram:',
        'call patch_engine_gateways',
        'and 0x08',
        'page2_runtime_profile:',
        'page3_workram_profile:',
        'allocate_page3_workram_segment:',
        'free_page3_workram_segment:',
        'and 0xE2',
    ):
        if required not in source_text:
            raise SystemExit(f'missing MoonSound/MWK regression marker: {required}')
    for required in (
        'call mute_fmpac_before_disk_io',
        'mute_fmpac_before_disk_io:',
        'write_ym2413_register:',
    ):
        if required not in source_text:
            raise SystemExit(f'missing FMPAC disk-mute regression marker: {required}')
    forbidden_game_paths = ('Fray', 'Parodius', 'split_profile', '0x4209', '0x421E', '0xCE2A')
    for forbidden in forbidden_game_paths:
        if forbidden in source_text:
            raise SystemExit(f'game-specific player path remains: {forbidden}')
    if symbols.get('start') != 0x0100:
        raise SystemExit('start symbol is not 0100h')
    program_end = symbols.get('program_end', 0x0100 + len(binary))
    if program_end > 0x1C00:
        raise SystemExit(f'resident COM overlaps fixed page-0 descriptors: end={program_end:04X}h')
    if symbols.get('dynamic_gateway_end', 0x2201) > 0x2200:
        raise SystemExit('dynamic callback exceeds the HPOL-only POS buffer')
    if symbols.get('dos1_overlay_end', 0x2201) > 0x2200:
        raise SystemExit('DOS1 FCB overlay crosses the Screen 5 UI')
    for name in ('dual_scc_select_a', 'dual_scc_select_b', 'dual_scc_restore_ram'):
        address = symbols.get(name, 0)
        if not 0x2000 <= address < symbols.get('dynamic_gateway_end', 0):
            raise SystemExit(f'{name} is outside the resident gateway area')
    if symbols.get('ui_module') != 0x2200:
        raise SystemExit('Screen 5 UI module is not at 2200h')
    if symbols.get('ui_code_end', 0x3501) > 0x3500:
        raise SystemExit('Screen 5 UI code/data overlaps HPOL caches')
    if symbols.get('hpol_position_cache') != 0x3500 or symbols.get('hpol_map_row_cache') != 0x3700:
        raise SystemExit('HPOL row caches moved from their fixed layout')
    if symbols.get('ui_module_end') != 0x3900:
        raise SystemExit('graphical/HPOL region must end exactly at the stack guard')
    if 0x3900 >= 0x39F0:
        raise SystemExit('invalid page-0 stack guard')
    if symbols.get('validate_required_hardware') != 0x3A00:
        raise SystemExit('MoonSound helper module is not at 3A00h')
    opl4_end = symbols.get('opl4_module_end', 0x4001)
    if opl4_end > 0x4000:
        raise SystemExit(f'MoonSound helper module crosses page 0: end={opl4_end:04X}h')
    if symbols.get('filename', 0) >= 0x1C00:
        raise SystemExit('resident COM variables overlap page-0 KSP buffers')

    run(
        sys.executable,
        'tools/make_ksp101_runtime_samples.py',
        '--source', 'samples/NEMESIS3.KSP',
        '--page3-output', 'samples/NEMESIS3_KSP101_PAGE3_TEST.KSP',
    )

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

    ksp101_report = BUILD / 'KSP101_PAGE3_REPORT.json'
    run(
        sys.executable,
        'tools/ksp1_validate_sparse.py',
        'samples/NEMESIS3_KSP101_PAGE3_TEST.KSP',
        '--json', str(ksp101_report),
    )
    ksp101 = json.loads(ksp101_report.read_text(encoding='utf-8'))[0]
    if not ksp101.get('profile_compatible') or not ksp101.get('all_page_crcs_valid'):
        raise SystemExit('KSP 1.01 PAGE3_WORKRAM sample validation failed')

    run(
        sys.executable,
        'tools/zx0_msx_model_test.py',
        'samples/NEMESIS3.KSP',
        '--source', 'src/KSP1PLAY.asm',
    )

    run(
        sys.executable,
        'tools/dual_scc_gateway_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--symbols', str(sym),
    )
    run(
        sys.executable,
        'tools/gui_shell_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--symbols', str(sym),
    )
    run(
        sys.executable,
        'tools/dos1_backend_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--symbols', str(sym),
    )
    run(
        sys.executable,
        'tools/ksp101_runtime_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--sample', 'samples/SOLIDSNK_KSP1_SPARSE_REGRESSION.ksp',
    )

    run(
        sys.executable,
        'tools/fmpac_disk_mute_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
    )

    run(
        sys.executable,
        'tools/track_selector_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--symbols', str(sym),
        '--sample', 'samples/NEMESIS3.KSP',
    )

    run(
        sys.executable,
        'tools/ui_polish_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--symbols', str(sym),
    )

    run(
        sys.executable,
        'tools/incremental_ui_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--symbols', str(sym),
    )

    run(
        sys.executable,
        'tools/nul_padding_ui_model_test.py',
    )

    run(
        sys.executable,
        'tools/player_track_window_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
    )

    run(
        sys.executable,
        'tools/lifecycle_exit_model_test.py',
        '--source', 'src/KSP1PLAY.asm',
        '--symbols', str(sym),
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
    run(sys.executable, 'tools/make_menu_test_disk.py')

    digest = hashlib.sha256(binary).hexdigest()
    (BUILD / 'SHA256SUMS').write_text(
        f'{digest}  KSP1PLAY.COM\n'
        f'{hashlib.sha256((BUILD / "KSP1SPRS.DSK").read_bytes()).hexdigest()}  KSP1SPRS.DSK\n'
        f'{hashlib.sha256((BUILD / "KSP1HYBR.DSK").read_bytes()).hexdigest()}  KSP1HYBR.DSK\n'
        f'{hashlib.sha256((BUILD / "KSP1NEM3.DSK").read_bytes()).hexdigest()}  KSP1NEM3.DSK\n'
        f'{hashlib.sha256((BUILD / "KSP1MENU.DSK").read_bytes()).hexdigest()}  KSP1MENU.DSK\n',
        encoding='ascii',
    )
    print(f'KSP1PLAY.COM: {len(binary)} bytes, SHA-256 {digest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
