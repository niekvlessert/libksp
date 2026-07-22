#!/usr/bin/env python3
"""Compare exact-frame binary snapshots from fray_page1_state_capture.tcl."""

from __future__ import annotations

import argparse
from pathlib import Path


def compare_block(left: Path, right: Path, base: int) -> bool:
    a = left.read_bytes()
    b = right.read_bytes()
    if a == b:
        print(f"{left.name}: identical ({len(a)} bytes)")
        return True
    limit = min(len(a), len(b))
    offset = next((i for i in range(limit) if a[i] != b[i]), limit)
    if offset == limit:
        print(f"{left.name}: size differs ({len(a)} versus {len(b)})")
        return False
    lo = max(0, offset - 8)
    hi = min(limit, offset + 9)
    print(
        f"{left.name}: first difference at {base + offset:04X}: "
        f"{a[offset]:02X} versus {b[offset]:02X}"
    )
    print(f"  left : {a[lo:hi].hex(' ')}")
    print(f"  right: {b[lo:hi].hex(' ')}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path, help="left capture prefix")
    parser.add_argument("right", type=Path, help="right capture prefix")
    args = parser.parse_args()

    same = True
    for frame in (1, 2, 60, 600):
        print(f"frame {frame}")
        for suffix, base in (("page1", 0x4000), ("page2", 0x8000)):
            left = Path(f"{args.left}-frame-{frame:04d}-{suffix}.bin")
            right = Path(f"{args.right}-frame-{frame:04d}-{suffix}.bin")
            same = compare_block(left, right, base) and same
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
