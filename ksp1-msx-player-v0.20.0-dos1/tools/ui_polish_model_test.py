#!/usr/bin/env python3
from __future__ import annotations
import argparse
import re
from pathlib import Path


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

    required = (
        'ui_redraw_track_selection:',
        'ui_redraw_track_page:',
        'ui_draw_track_index:',
        'Treat control bytes as the end of the display string.',
        'and 0x07',
        'cp 5',
    )
    for marker in required:
        if marker not in source:
            raise SystemExit(f'missing UI polish marker: {marker}')

    store = source[source.index('ui_track_menu_store:'):source.index('ui_track_menu_choose:')]
    if 'call ui_draw_track_menu' in store or 'call ui_clear_screen' in store:
        raise SystemExit('track movement still performs a full-screen redraw')
    if 'call ui_redraw_track_selection' not in store or 'call ui_redraw_track_page' not in store:
        raise SystemExit('incremental selector paths are not wired')

    text_copy = source[source.index('ui_text_copy:'):source.index('ui_text_copy_done:')]
    if 'cp 0x20' not in text_copy or 'jr c,ui_text_copy_done' not in text_copy:
        raise SystemExit('renderer does not terminate CR/LF/control bytes')
    if 'jr c,ui_text_question' in text_copy:
        raise SystemExit('renderer still converts control bytes to question marks')

    font = source[source.index('ui_font:'):source.index('ui_expand_table:')]
    values = [int(v, 16) for v in re.findall(r'0x([0-9A-Fa-f]{2})', font)]
    if len(values) != 64 * 5:
        raise SystemExit(f'3x5 font must contain 320 rows, got {len(values)}')
    if any(v > 7 for v in values):
        raise SystemExit('font row exceeds three pixels')

    if symbols.get('ui_code_end', 0x3501) > 0x3500:
        raise SystemExit('UI polish overlaps HPOL caches')
    print(f"UI polish model passed; 3x5 font, incremental repaint, UI end {symbols['ui_code_end']:04X}h")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
