#!/usr/bin/env python3
"""Static regression checks for package cleanup, keyboard draining and DOS exit."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def block(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def ordered(haystack: str, *needles: str) -> bool:
    pos = -1
    for needle in needles:
        pos = haystack.find(needle, pos + 1)
        if pos < 0:
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--symbols', required=True)
    args = ap.parse_args()

    source = Path(args.source).read_text(encoding='utf-8')
    symbols_text = Path(args.symbols).read_text(encoding='utf-8')
    symbols = {}
    for line in symbols_text.splitlines():
        if ' = ' in line:
            k, v = line.split(' = ', 1)
            symbols[k] = int(v, 0)

    cleanup = block(source, 'cleanup:', '; ---------------------------------------------------------------------------\n; KSP parsing')
    if not ordered(
        cleanup,
        'call free_hot_segments',
        'call free_template_segment',
        'call free_page3_workram_segment',
        'call free_mwk_segment',
        'call free_hpol_map_segment',
        'call restore_process_pages',
        'call ui_reset_package_state',
    ):
        raise SystemExit('cleanup does not free all package segments and reset state in order')

    load_pack = block(source, 'ui_load_pack:', 'ui_install_selected_track:')
    for forbidden in (
        'ld (template_segment_allocated),a',
        'ld (engine_p3_segment_allocated),a',
        'ld (hpol_map_allocated),a',
        'ld (mwk_segment_allocated),a',
    ):
        if forbidden in load_pack:
            raise SystemExit(f'ui_load_pack erases allocation ownership before cleanup: {forbidden}')

    reset = block(source, 'ui_reset_package_state:', 'opl4_module_end:')
    for required in (
        'ld (file_open),a',
        'ld (hot_segment_count),a',
        'ld (template_segment_allocated),a',
        'ld (engine_p3_segment_allocated),a',
        'ld (hpol_map_allocated),a',
        'ld (mwk_segment_allocated),a',
        'ld (dynamic_profile),a',
        'ld (page2_runtime_profile),a',
        'ld (page3_workram_profile),a',
        'ld (hot_write_mapped),a',
        'ld (hot_read_mapped),a',
        'ld (ui_track_cache_top),hl',
    ):
        if required not in reset:
            raise SystemExit(f'missing lifecycle reset marker: {required}')

    restore = block(source, 'ui_restore_screen0:', 'ui_write_vdp_register:')
    for required in (
        'ld a,80',
        'ld (LINL40),a',
        'BIOS_INITXT',
        'PUTPNT',
        'GETPNT',
        'ui_wait_keys_released:',
        'ui_clear_bios_keyboard_buffer:',
    ):
        if required not in restore:
            raise SystemExit(f'missing 80-column/keyboard-exit marker: {required}')


    clear_buf = block(source, 'ui_clear_bios_keyboard_buffer:', '; Wait for the physical key')
    if 'call ui_call_main_bios' in clear_buf or 'BIOS_KILBUF' in clear_buf:
        raise SystemExit('live keyboard flush still enters BIOS/CALSLT')
    if not ordered(clear_buf, 'ld hl,(PUTPNT)', 'ld (GETPNT),hl'):
        raise SystemExit('keyboard flush does not collapse the BIOS ring-buffer pointers')

    final_exit = block(source, 'ui_final_exit:', '; Open and prepare the filename')
    if not ordered(
        final_exit,
        'call cleanup',
        'call ui_wait_keys_released',
        'call ui_restore_screen0',
        'call ui_clear_bios_keyboard_buffer',
        'ld c,DOS_TERM0',
    ):
        raise SystemExit('final exit does not release keys, restore 80-column text and flush buffer')

    action_finish = block(source, 'ui_action_finish:', 'ui_read_keyboard:')
    if not ordered(action_finish, 'ld a,(engine_running)', 'call z,ui_clear_bios_keyboard_buffer'):
        raise SystemExit('non-playing UI actions do not drain BIOS keyboard buffering')

    if symbols.get('program_end', 0x1C01) > 0x1C00:
        raise SystemExit('resident core overlaps descriptor area')
    if symbols.get('ui_code_end', 0x3501) > 0x3500:
        raise SystemExit('UI overlaps HPOL cache')
    if symbols.get('opl4_module_end', 0x4001) > 0x4000:
        raise SystemExit('lifecycle reset overflows page 0 helper area')

    print(
        'lifecycle/exit model passed; '
        f"core={symbols.get('program_end', 0):04X}h, "
        f"ui={symbols.get('ui_code_end', 0):04X}h, "
        f"high={symbols.get('opl4_module_end', 0):04X}h"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
