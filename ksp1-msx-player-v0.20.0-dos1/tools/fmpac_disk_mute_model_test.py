#!/usr/bin/env python3
"""Static regression checks for YM2413 mute before blocking DOS I/O."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def block(source: str, label: str, next_label: str) -> str:
    pattern = rf"(?ms)^{re.escape(label)}:\n(.*?)(?=^{re.escape(next_label)}:)"
    match = re.search(pattern, source)
    if not match:
        raise SystemExit(f"missing block {label}..{next_label}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    source = Path(args.source).read_text(encoding='utf-8')

    read_disk = block(source, 'read_at_disk', 'preload_file_cache')
    if 'call mute_fmpac_before_disk_io' not in read_disk:
        raise SystemExit('read_at_disk does not mute FMPAC')

    stream_disk = block(source, 'stream_begin_disk', 'stream_begin_bad')
    if 'call mute_fmpac_before_disk_io' not in stream_disk:
        raise SystemExit('stream_begin_disk does not mute FMPAC')

    cache_path = block(source, 'read_at_vram_loop', 'read_at_vram_done')
    if 'mute_fmpac_before_disk_io' in cache_path:
        raise SystemExit('VRAM cache path must not mute FMPAC')

    helper = block(source, 'mute_fmpac_before_disk_io', 'write_ym2413_register')
    required = (
        'ld a,(engine_running)',
        'ld a,(engine_ready)',
        'ld a,(ENGINE_ENTRY+4)',
        'and 0x10',
        'ld d,0x0E',
        'ld d,0x20',
        'ld b,9',
        'call write_ym2413_register',
    )
    for marker in required:
        if marker not in helper:
            raise SystemExit(f'missing FMPAC mute marker: {marker}')

    if '0x30' in helper or '0x38' in helper:
        raise SystemExit('live disk mute must not overwrite YM2413 volume registers')

    print('FMPAC disk-I/O key-off model passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
