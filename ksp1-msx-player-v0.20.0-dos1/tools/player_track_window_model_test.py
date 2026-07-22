#!/usr/bin/env python3
"""Model the playback track-window policy used by KSP1PLAY."""
from __future__ import annotations

import argparse
from pathlib import Path

PLAYER_ROWS = 13
SCROLL_THRESHOLD = PLAYER_ROWS - 1  # selected offset 12 triggers scrolling
TARGET_OFFSET = PLAYER_ROWS - 2     # selected settles at row 11


def adjust(selected: int, top: int) -> int:
    if selected < top:
        return selected
    if selected - top < SCROLL_THRESHOLD:
        return top
    return selected - TARGET_OFFSET


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    source = Path(args.source).read_text(encoding='utf-8')

    for marker in (
        'ld de,UI_PLAYER_TRACK_ROWS-1',
        'ld de,UI_PLAYER_TRACK_ROWS-2',
    ):
        if marker not in source:
            raise SystemExit(f'missing playback viewport marker: {marker}')

    # Screenshot regression: selected track 22 with old top 8 must display
    # tracks 11..23, keeping track 23 visible as the following track.
    top = adjust(22, 8)
    assert top == 11, top
    visible = list(range(top, top + PLAYER_ROWS))
    assert visible[11] == 22
    assert visible[12] == 23

    # Normal movement inside the window should not scroll unnecessarily.
    assert adjust(19, 9) == 9
    # Moving above the viewport should put the selected track at its top.
    assert adjust(7, 9) == 7

    print('player track-window model passed; track 22 shows 11..23')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
