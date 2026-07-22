#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path


def parse_symbols(path: Path) -> dict[str, int]:
    out = {}
    for line in path.read_text().splitlines():
        if ' = ' in line:
            k, v = line.split(' = ', 1)
            out[k] = int(v, 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--symbols', type=Path, required=True)
    ns = ap.parse_args()
    src = ns.source.read_text()
    sym = parse_symbols(ns.symbols)
    expected = {
        'ui_module': 0x2200,
        'hpol_position_cache': 0x3500,
        'hpol_map_row_cache': 0x3700,
        'ui_module_end': 0x3900,
    }
    for name, value in expected.items():
        if sym.get(name) != value:
            raise SystemExit(f'{name} expected {value:04X}h, got {sym.get(name)}')
    if sym.get('ui_code_end', 0x3501) > 0x3500:
        raise SystemExit('Screen 5 UI code/data overlaps HPOL row caches')
    markers = (
        'DOS_SFIRST', 'DOS_SNEXT', 'ui_scan_wild_name:',
        'ui_screen5_init:', 'ui_restore_screen0:', 'ui_draw_player_screen:',
        'ui_draw_cached_tracks:', 'ui_track_menu:', 'ui_draw_track_menu:', 'ui_back_to_menu:', 'call free_hpol_map_segment',
        'ld de,MAP_ROW_BUFFER', 'ld hl,MAP_ROW_BUFFER',
        'ld a,(hpol_map_segment)', 'call map_p2',
    )
    for marker in markers:
        if marker not in src:
            raise SystemExit(f'missing GUI/HPOL marker: {marker}')

    if 'ui_clear_vram_loop:\n    xor a\n    out (PORT_VDP_DATA),a' not in src:
        raise SystemExit('Screen 5 clear loop does not force every VRAM byte to zero')
    for marker in ('UI_TEXT_COLS    equ 64', 'ui_write_small_glyph_row:', 'ui_expand_table:'):
        if marker not in src:
            raise SystemExit(f'missing compact-font marker: {marker}')
    for legacy in ('ld de,MAP_BUFFER\n', 'ld hl,MAP_BUFFER\n'):
        if legacy in src:
            raise SystemExit('legacy page-0 HPOL map matrix is still used')
    print('Screen 5 menu/HPOL cache layout model passed')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
