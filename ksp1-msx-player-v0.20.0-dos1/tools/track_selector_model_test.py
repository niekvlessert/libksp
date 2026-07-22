#!/usr/bin/env python3
from __future__ import annotations
import argparse
import struct
from pathlib import Path


def parse_symbols(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if ' = ' in line:
            key, value = line.split(' = ', 1)
            out[key] = int(value, 0)
    return out


def selected_after(action: str, selected: int, count: int, rows: int = 15) -> int:
    if count <= 0:
        return 0
    if action == 'up':
        return count - 1 if selected == 0 else selected - 1
    if action == 'down':
        return 0 if selected + 1 >= count else selected + 1
    if action == 'page_up':
        return max(0, selected - rows)
    if action == 'page_down':
        return min(count - 1, selected + rows)
    raise ValueError(action)


def top_for(selected: int, top: int, rows: int = 15) -> int:
    if selected < top:
        return selected
    if selected >= top + rows:
        return selected - (rows - 1)
    return top


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--symbols', type=Path, required=True)
    ap.add_argument('--sample', type=Path, required=True)
    ns = ap.parse_args()
    src = ns.source.read_text(encoding='utf-8')
    sym = parse_symbols(ns.symbols)
    markers = (
        'UI_TRACK_ROWS   equ 15',
        'call ui_track_menu',
        'call ui_install_selected_track',
        'ui_track_menu:',
        'ui_draw_track_menu:',
        'ui_ensure_track_cache:',
        'ui_track_cache_pointer:',
        'ui_draw_cached_tracks:',
        'UI_TEXT_COLS    equ 64',
        "ui_track_select_help:    db 'UP/DOWN: TRACK   LEFT/RIGHT: PAGE',0",
        "ui_track_select_escape:  db 'ENTER/SPACE: PLAY   ESC: PACKAGE MENU',0",
    )
    for marker in markers:
        if marker not in src:
            raise SystemExit(f'missing track-selector marker: {marker}')
    if src.index('call ui_track_menu') > src.index('call ui_install_selected_track', src.index('call ui_track_menu')):
        raise SystemExit('track selector must run before track installation')
    if sym.get('ui_code_end', 0x3501) > 0x3500:
        raise SystemExit('track selector overflowed the Screen 5 UI region')

    data = ns.sample.read_bytes()
    if data[:4] != b'KSP1':
        raise SystemExit('sample is not KSP1')
    track_off = struct.unpack_from('<I', data, 0x20)[0]
    track_count = struct.unpack_from('<H', data, 0x24)[0]
    track_size = struct.unpack_from('<H', data, 0x26)[0]
    string_off = struct.unpack_from('<I', data, 0x30)[0]
    string_size = struct.unpack_from('<I', data, 0x34)[0]
    if track_count <= 15 or track_size < 32:
        raise SystemExit('sample does not exercise selector scrolling')
    titled = 0
    for index in range(track_count):
        title = struct.unpack_from('<I', data, track_off + index * track_size + 12)[0]
        if title == 0xFFFFFFFF:
            continue
        if title >= string_size:
            raise SystemExit(f'track {index} title is outside string table')
        end = data.find(b'\0', string_off + title, string_off + string_size)
        if end < 0:
            raise SystemExit(f'track {index} title is unterminated')
        titled += 1
    if titled != track_count:
        raise SystemExit('sample must expose a name for every selectable track')

    for count in (1, 15, 16, 255, 65535):
        assert selected_after('up', 0, count) == count - 1
        assert selected_after('down', count - 1, count) == 0
        assert selected_after('page_up', count - 1, count) >= 0
        assert selected_after('page_down', 0, count) <= count - 1
    assert top_for(15, 0) == 1
    assert top_for(14, 0) == 0
    assert top_for(3, 10) == 3
    print(f'track selector model passed; {track_count} titled tracks, UI end {sym["ui_code_end"]:04X}h')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
