#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path


def block(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end, source.index(start))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--symbols', required=True)
    ns = ap.parse_args()
    source = Path(ns.source).read_text(encoding='utf-8')
    symbols = {}
    for line in Path(ns.symbols).read_text(encoding='utf-8').splitlines():
        if ' = ' in line:
            name, value = line.split(' = ', 1)
            symbols[name] = int(value, 0)

    menu_up = block(source, 'ui_menu_up_store:', 'ui_menu_down:')
    menu_down = block(source, 'ui_menu_down_store:', 'ui_menu_choose:')
    for name, section in (('up', menu_up), ('down', menu_down)):
        if 'call ui_draw_menu' in section or 'call ui_clear_screen' in section:
            raise SystemExit(f'package-menu {name} still performs a full redraw')
        if 'call ui_menu_store_selection' not in section:
            raise SystemExit(f'package-menu {name} does not use incremental selection')

    menu_store = block(source, 'ui_menu_store_selection:', 'ui_draw_menu_index:')
    for marker in ('call ui_draw_menu_index', 'jp ui_draw_menu_rows'):
        if marker not in menu_store:
            raise SystemExit(f'missing package-menu incremental marker: {marker}')
    if 'call ui_clear_screen' in menu_store:
        raise SystemExit('incremental package selection clears SCREEN 5')

    next_action = block(source, 'ui_next_action:', 'ui_previous_action:')
    previous_action = block(source, 'ui_previous_action:', 'ui_back_to_menu:')
    for name, section in (('next', next_action), ('previous', previous_action)):
        if 'call ui_draw_player_screen' in section or 'call ui_clear_screen' in section:
            raise SystemExit(f'live {name}-track path still performs a full redraw')
        for marker in ('call ui_remember_player_selection', 'call ui_update_player_selection'):
            if marker not in section:
                raise SystemExit(f'live {name}-track path missing {marker}')

    player_update = block(source, 'ui_update_player_selection:', 'program_end:')
    for marker in (
        'call ui_draw_selected_track_title',
        'call ui_draw_player_track_index',
        'call ui_draw_cached_tracks',
    ):
        if marker not in player_update:
            raise SystemExit(f'missing live incremental repaint marker: {marker}')
    for forbidden in ('call ui_clear_screen', 'call ui_draw_player_screen'):
        if forbidden in player_update:
            raise SystemExit(f'live incremental helper contains {forbidden}')

    if symbols.get('program_end', 0x1C01) > 0x1C00:
        raise SystemExit('resident incremental helpers overlap KSP descriptors')
    if symbols.get('ui_code_end', 0x3501) > 0x3500:
        raise SystemExit('incremental UI overlaps HPOL caches')
    print(
        f"incremental package/live-track repaint model passed; "
        f"core end {symbols['program_end']:04X}h, UI end {symbols['ui_code_end']:04X}h"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
