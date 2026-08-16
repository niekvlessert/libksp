#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_vm_fixture import PAGE_SIZE, LOAD, make_page  # noqa: E402

NULL16 = 0xFFFF
NULL32 = 0xFFFFFFFF
HW_PSG = 1 << 0
HW_SCC = 1 << 1
HW_SCC_PLUS = 1 << 2
HW_DUAL_SCC = 1 << 3
HW_OPL4 = 1 << 6
HW_SN76489 = 1 << 7
TRACK_HIDDEN = 1


def metadata(case: str, visible_count: int, minor: int) -> bytes:
    metadata_version = b"2" if minor >= 4 else b"1"
    lines = [
        b"metadata_version=" + metadata_version,
        b"title=Shovel Knight profile fixture",
        b"game=Shovel Knight",
        b"composer=Jake Kaufman",
        b"release_year=2014",
        b"source_format=NSF",
        b"source_sha256=596bf4746c10788731799c0b8acec063498310414b97bcc443a6a05be3649be7",
        f"track_count={visible_count}".encode(),
        f"format=KSP 1.{minor:02d} with HVAR/HVR1".encode(),
        b"unknown_future_key=accepted",
    ]
    if minor >= 4:
        lines.append(b"default_language=en")
    if case == "localized":
        lines.extend([
            "title.ja=パロディウスだ! ～神話からお笑いへ～".encode("utf-8"),
            "game.ja=パロディウスだ! ～神話からお笑いへ～".encode("utf-8"),
            b"title.pt-br=Parodius Da!",
            "title.zh-hant=鏟子騎士".encode("utf-8"),
            "future_label.ja=将来".encode("utf-8"),
        ])
    elif case == "duplicate-localized":
        lines.extend([b"title.ja=first", b"title.ja=second"])
    elif case == "bad-localized-empty":
        lines.append(b"title.=bad")
    elif case == "bad-localized-case":
        lines.append(b"title.JA=bad")
    elif case == "bad-localized-dot":
        lines.append(b"title.ja.extra=bad")
    elif case == "bad-localized-hyphen":
        lines.append(b"title.pt--br=bad")
    elif case == "bad-localized-primary":
        lines.append(b"title.x-private=bad")
    elif case == "bad-localized-long":
        lines.append(b"title.en-toolonggg=bad")
    elif case == "bad-default-language":
        lines = [b"default_language=EN" if line.startswith(b"default_language=") else line
                 for line in lines]
    elif case == "metadata-version-1":
        lines = [b"metadata_version=1" if line.startswith(b"metadata_version=") else line
                 for line in lines]
    elif case == "metadata-version-2":
        lines = [b"metadata_version=2" if line.startswith(b"metadata_version=") else line
                 for line in lines]
    if case == "missing-version":
        lines = [line for line in lines if not line.startswith(b"metadata_version=")]
    elif case == "duplicate":
        lines.append(b"title=Duplicate")
    elif case == "missing-equals":
        lines.append(b"broken_line")
    elif case == "bad-sha":
        lines = [b"source_sha256=ABC" if line.startswith(b"source_sha256=") else line for line in lines]
    elif case == "bad-track-count":
        lines = [b"track_count=fifty-one" if line.startswith(b"track_count=") else line for line in lines]
    elif case == "track-count-warning":
        lines = [b"track_count=52" if line.startswith(b"track_count=") else line for line in lines]
    payload = b"\n".join(lines) + b"\n"
    if case == "invalid-utf8":
        payload += b"notes=bad\xff\n"
    elif case == "nul":
        payload += b"notes=bad\x00value\n"
    elif case == "bom":
        payload = b"\xef\xbb\xbf" + payload
    elif case == "crlf":
        payload = payload.replace(b"\n", b"\r\n")
    return payload


def make_hvr(logical_count: int, candidates: list[tuple[int, int]], logical_ranges: list[tuple[int, int, int]],
             case: str) -> bytes:
    raw = bytearray(24 + logical_count * 12 + len(candidates) * 8)
    raw[:4] = b"HVR1"
    logical_off = 24
    candidate_off = logical_off + logical_count * 12
    struct.pack_into("<HHHHHHII", raw, 4, 24, 1, logical_count, len(candidates), 12, 8,
                     logical_off, candidate_off)
    for i, (logical, first, count) in enumerate(logical_ranges):
        struct.pack_into("<HHHHI", raw, logical_off + i * 12, logical, first, count, 0, 0)
    for i, (track, rank) in enumerate(candidates):
        struct.pack_into("<HHHH", raw, candidate_off + i * 8, track, rank, 0, 0)
    if case == "bad-fallback":
        struct.pack_into("<H", raw, candidate_off + 2 * 8, candidates[0][0])
    elif case == "overlap" and logical_count > 1:
        struct.pack_into("<H", raw, logical_off + 12 + 2, 0)
    elif case == "bad-magic":
        raw[:4] = b"BAD!"
    return bytes(raw)


def build(path: Path, *, minor: int, meta_case: str, no_meta: bool,
          hvr_case: str, high_index: bool, no_eligible: bool) -> None:
    visible_count = 1 if high_index else 51
    if high_index:
        track_count = 260
        plus_base = 258
        dual_base = 259
    else:
        track_count = visible_count * 3
        plus_base = visible_count
        dual_base = visible_count * 2

    pages = [
        make_page(False, False, 0x11), make_page(False, False, 0x77),
        make_page(False, True, 0x22), make_page(False, True, 0x88),
        make_page(True, False, 0x33), make_page(True, False, 0x99),
    ]
    hardware = [HW_PSG | HW_SCC, HW_PSG | HW_SCC_PLUS, HW_PSG | HW_DUAL_SCC]
    if no_eligible:
        hardware = [HW_SN76489, HW_SN76489, HW_SN76489]

    strings = bytearray()
    engine_names = []
    for name in ("Normal SCC engine", "SCC+ engine", "Dual SCC engine"):
        engine_names.append(len(strings)); strings.extend(name.encode() + b"\0")
    title_offsets = []
    for i in range(visible_count):
        title_offsets.append(len(strings)); strings.extend(f"Track {i+1}".encode() + b"\0")

    engine_count = 3
    page_count = 6
    resource_count = 1 + (0 if no_meta else 1)
    engine_off = 80
    page_off = engine_off + engine_count * 64
    track_off = page_off + page_count * 24
    resource_off = track_off + track_count * 32
    string_off = resource_off + resource_count * 32
    cursor = string_off + len(strings)
    template = bytes(PAGE_SIZE)
    template_off = cursor
    cursor += len(template)
    page_offsets = []
    for page in pages:
        page_offsets.append(cursor); cursor += len(page)

    candidates: list[tuple[int, int]] = []
    ranges: list[tuple[int, int, int]] = []
    for logical in range(visible_count):
        first = len(candidates)
        if hvr_case == "equal-rank":
            candidates.extend([(plus_base + logical, 300), (dual_base + logical, 300), (logical, 100)])
        else:
            candidates.extend([(dual_base + logical, 300), (plus_base + logical, 200), (logical, 100)])
        ranges.append((logical, first, 3))
    hvr = make_hvr(visible_count, candidates, ranges, hvr_case)
    hvr_off = cursor; cursor += len(hvr)
    meta = b"" if no_meta else metadata(meta_case, visible_count, minor)
    meta_off = cursor
    cursor += len(meta)

    engines = bytearray(engine_count * 64)
    for i in range(engine_count):
        base = i * 64
        struct.pack_into("<II", engines, base, 1, hardware[i])
        struct.pack_into("<HHHHHHHHHHHH", engines, base + 8, 1, 60, LOAD, PAGE_SIZE,
                         0x4000, 0x4100, 0, 0xD8A0, 0x4200, i * 2, 2, NULL16)
        engines[base + 32] = 0
        struct.pack_into("<IIIII", engines, base + 36, template_off, len(template), len(template),
                         zlib.crc32(template) & 0xFFFFFFFF, engine_names[i])

    page_table = bytearray()
    for i, page in enumerate(pages):
        page_table += struct.pack("<HBBHHIIII", i // 2, 1, 0, 0, 0, page_offsets[i], len(page), len(page),
                                  zlib.crc32(page) & 0xFFFFFFFF)

    tracks = bytearray()
    for i in range(track_count):
        if i < visible_count:
            page, song, flags = 0, i, 0
            title = title_offsets[i]
            duration, loop_start, loop_end, fade = 3000 + i, 1000, 2500, 500
        elif high_index and i not in (plus_base, dual_base):
            page, song, flags = 0, i, TRACK_HIDDEN
            title = title_offsets[0]
            duration = loop_start = loop_end = fade = NULL32
        elif i < dual_base:
            logical = i - plus_base
            page, song, flags = 2, logical, TRACK_HIDDEN
            title = title_offsets[logical]
            duration = loop_start = loop_end = fade = NULL32
        else:
            logical = i - dual_base
            page, song, flags = 4, logical, TRACK_HIDDEN
            title = title_offsets[logical]
            duration, loop_start, loop_end, fade = 5000 + logical, NULL32, NULL32, 750
        tracks += struct.pack("<HHHHHHIIIII", page, song, flags, NULL16, NULL16, 0, title,
                              duration, loop_start, loop_end, fade)

    resources = bytearray()
    resources += b"HVAR" + struct.pack("<HBBIIIIII", 0, 0, 0, hvr_off, len(hvr), len(hvr),
                                        zlib.crc32(hvr) & 0xFFFFFFFF, 0, 0)
    meta_index = NULL16
    if not no_meta:
        meta_index = 1
        resources += b"META" + struct.pack("<HBBIIIIII", 0, 0, 0, meta_off, len(meta), len(meta),
                                            zlib.crc32(meta) & 0xFFFFFFFF, 0, 0)

    index = bytes(engines) + bytes(page_table) + bytes(tracks) + bytes(resources) + bytes(strings)
    header = bytearray(80)
    header[:4] = b"KSP1"
    struct.pack_into("<HHII", header, 4, 80, minor, 0, cursor)
    struct.pack_into("<IHH", header, 16, engine_off, engine_count, 64)
    struct.pack_into("<IHH", header, 24, page_off, page_count, 24)
    struct.pack_into("<IHH", header, 32, track_off, track_count, 32)
    struct.pack_into("<IHH", header, 40, resource_off, resource_count, 32)
    struct.pack_into("<II", header, 48, string_off, len(strings))
    struct.pack_into("<HHHH", header, 56, 0, meta_index, NULL16, 0)
    struct.pack_into("<I", header, 68, zlib.crc32(index) & 0xFFFFFFFF)
    header_copy = bytearray(header); struct.pack_into("<I", header_copy, 64, 0)
    struct.pack_into("<I", header, 64, zlib.crc32(header_copy) & 0xFFFFFFFF)

    path.write_bytes(bytes(header) + index + template + b"".join(pages) + hvr + meta)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--minor", type=int, default=3)
    parser.add_argument("--meta-case", default="valid")
    parser.add_argument("--no-meta", action="store_true")
    parser.add_argument("--hvr-case", default="valid")
    parser.add_argument("--high-index", action="store_true")
    parser.add_argument("--no-eligible", action="store_true")
    args = parser.parse_args()
    build(args.output, minor=args.minor, meta_case=args.meta_case, no_meta=args.no_meta,
          hvr_case=args.hvr_case, high_index=args.high_index, no_eligible=args.no_eligible)


if __name__ == "__main__":
    main()
