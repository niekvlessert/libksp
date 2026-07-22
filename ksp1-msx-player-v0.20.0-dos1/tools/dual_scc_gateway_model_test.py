#!/usr/bin/env python3
"""Model regression for generic KSP ABI-1 gateway relocation.

This does not emulate the Z80. It verifies the relocation contract and fixed
memory layout against the assembled symbol table, and prevents game-specific
call-site logic from returning to the source.
"""
from __future__ import annotations

import argparse
from pathlib import Path

TOKENS = {
    0xD900: "dual_scc_select_a",
    0xD904: "dual_scc_select_b",
    0xD908: "dual_scc_restore_ram",
}
FORBIDDEN = ("Fray", "Parodius", "split_profile", "0x4209", "0x421E", "0xCE2A")


def parse_symbols(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if " = " in line:
            name, value = line.split(" = ", 1)
            out[name] = int(value, 0)
    return out


def relocate(image: bytearray, replace_offset: int, dynamic_target: int,
             dynamic_replacement: int, replacements: dict[int, int]) -> int:
    flags = 0
    i = 0
    while i < replace_offset:
        if image[i] != 0xCD or i + 2 >= replace_offset:
            i += 1
            continue
        target = image[i + 1] | (image[i + 2] << 8)
        replacement = None
        if target == dynamic_target:
            replacement = dynamic_replacement
            flags |= 1
        elif target in replacements:
            replacement = replacements[target]
            flags |= {0xD900: 2, 0xD904: 4, 0xD908: 8}[target]
        if replacement is not None:
            image[i + 1] = replacement & 0xFF
            image[i + 2] = replacement >> 8
        i += 3
    return flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--symbols", type=Path, required=True)
    args = ap.parse_args()

    source = args.source.read_text(encoding="utf-8")
    for text in FORBIDDEN:
        if text in source:
            raise SystemExit(f"game-specific path remains: {text}")

    symbols = parse_symbols(args.symbols)
    end = symbols["dynamic_gateway_end"]
    replacements = {token: symbols[name] for token, name in TOKENS.items()}
    for name, address in ((name, replacements[token]) for token, name in TOKENS.items()):
        if not 0x2000 <= address < end <= 0x2200:
            raise SystemExit(f"invalid resident callback placement: {name}={address:04X}")

    image = bytearray([0] * 0x4000)
    dynamic_target = 0x2468
    calls = [
        (0x0010, dynamic_target),
        (0x0020, 0xD900),
        (0x0030, 0xD904),
        (0x0040, 0xD908),
        (0x0050, 0xD900),
        (0x0900, 0xD904),  # mutable region: must remain untouched
    ]
    for offset, target in calls:
        image[offset:offset + 3] = bytes((0xCD, target & 0xFF, target >> 8))

    flags = relocate(
        image,
        replace_offset=0x0800,
        dynamic_target=dynamic_target,
        dynamic_replacement=0x2000,
        replacements=replacements,
    )
    if flags != 0x0F:
        raise SystemExit(f"gateway relocation flags mismatch: {flags:02X}")
    expected = {
        0x0010: 0x2000,
        0x0020: replacements[0xD900],
        0x0030: replacements[0xD904],
        0x0040: replacements[0xD908],
        0x0050: replacements[0xD900],
        0x0900: 0xD904,
    }
    for offset, target in expected.items():
        actual = image[offset + 1] | (image[offset + 2] << 8)
        if actual != target:
            raise SystemExit(f"relocation mismatch at {offset:04X}: {actual:04X} != {target:04X}")

    print(
        "generic dynamic/dual-SCC relocation model passed; "
        f"callbacks end at {end:04X}h"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
