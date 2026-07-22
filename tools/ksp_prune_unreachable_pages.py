#!/usr/bin/env python3
"""Prune dynamic KSP pages that no public track can reach.

Split-track converters may retain the complete source page table so that page
indices stay compatible with the original multi-track package.  This tool
creates a standalone package with only the DSC0 page chains reachable from
the public tracks.  It rewrites page links and verifies reconstructed pages.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

try:
    from tools.ksp_optimize import KSPError, crc32, parse_ksp, sparse_payload
except ModuleNotFoundError:  # direct invocation as ``python3 tools/...py``
    from ksp_optimize import KSPError, crc32, parse_ksp, sparse_payload


HEADER_SIZE = 80
ENGINE_SIZE = 64
PAGE_SIZE = 24
TRACK_SIZE = 32
RESOURCE_SIZE = 32
DSC0_OFFSET = 0x0800
DSC0_NEXT_PAGE_OFFSET = DSC0_OFFSET + 10


def u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<H", data, offset, value)


def put_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value)


def reachable_pages(package) -> list[int]:
    reachable: set[int] = set()
    for track_index, track in enumerate(package.tracks):
        page_index = track.page
        chain_seen: set[int] = set()
        while page_index != 0xFFFF and page_index != 0xFF:
            if page_index in chain_seen:
                raise KSPError(f"track {track_index} page chain cycles at page {page_index}")
            if not 0 <= page_index < len(package.pages):
                raise KSPError(f"track {track_index} page {page_index} is outside the page table")
            chain_seen.add(page_index)
            reachable.add(page_index)
            page = package.pages[page_index]
            if page[DSC0_OFFSET:DSC0_OFFSET + 4] != b"DSC0":
                raise KSPError(f"page {page_index} is not a DSC0 dynamic page")
            page_index = page[DSC0_NEXT_PAGE_OFFSET]
    return sorted(reachable)


def prune(source: Path, output: Path) -> dict:
    package = parse_ksp(source, allow_legacy_sparse=True)
    raw = package.raw
    if len(package.engines) != 1:
        raise KSPError("this pruner currently requires exactly one engine")
    if any(entry.encoding != 0 or entry.compression != 0 for entry in package.page_entries):
        raise KSPError("this pruner currently requires uncompressed sparse pages")

    engine_offset = u32(raw, 16)
    engine_count = u16(raw, 20)
    engine_entry_size = u16(raw, 22)
    page_offset = u32(raw, 24)
    page_entry_size = u16(raw, 30)
    track_offset = u32(raw, 32)
    track_count = u16(raw, 36)
    track_entry_size = u16(raw, 38)
    resource_offset = u32(raw, 40)
    resource_count = u16(raw, 44)
    resource_entry_size = u16(raw, 46)
    string_offset = u32(raw, 48)
    string_size = u32(raw, 52)
    if (engine_entry_size, page_entry_size, track_entry_size, resource_entry_size) != (
        ENGINE_SIZE, PAGE_SIZE, TRACK_SIZE, RESOURCE_SIZE
    ):
        raise KSPError("unsupported KSP table entry size")

    old_pages = reachable_pages(package)
    if not old_pages:
        raise KSPError("no pages are reachable from public tracks")
    page_map = {old: new for new, old in enumerate(old_pages)}

    engines = bytearray(raw[engine_offset:engine_offset + engine_count * engine_entry_size])
    engine = engines[:ENGINE_SIZE]
    template_offset = u32(engine, 36)
    template_packed = u32(engine, 40)
    template_payload = raw[template_offset:template_offset + template_packed]
    if len(template_payload) != template_packed:
        raise KSPError("engine template is outside the source file")
    put_u16(engine, 26, 0)
    put_u16(engine, 28, len(old_pages))
    engines[:ENGINE_SIZE] = engine

    templates = [engine_state.template for engine_state in package.engines]
    page_payloads: list[bytes] = []
    page_table = bytearray(PAGE_SIZE * len(old_pages))
    for new_index, old_index in enumerate(old_pages):
        page = bytearray(package.pages[old_index])
        next_page = page[DSC0_NEXT_PAGE_OFFSET]
        if next_page == 0xFF:
            remapped_next = 0xFF
        else:
            if next_page not in page_map:
                raise KSPError(f"page {old_index} points to unreachable page {next_page}")
            remapped_next = page_map[next_page]
        page[DSC0_NEXT_PAGE_OFFSET] = remapped_next
        payload = sparse_payload(templates[0], bytes(page), 4)
        page_payloads.append(payload)
        struct.pack_into(
            "<HBBHHIIII",
            page_table,
            new_index * PAGE_SIZE,
            0, 0, 0, 0, 0, 0, len(payload), len(payload), crc32(page),
        )

    tracks = bytearray(raw[track_offset:track_offset + track_count * track_entry_size])
    for index in range(track_count):
        entry_offset = index * track_entry_size
        old_start = u16(tracks, entry_offset)
        if old_start not in page_map:
            raise KSPError(f"track {index} starts at an unreachable page {old_start}")
        put_u16(tracks, entry_offset, page_map[old_start])

    resources = bytearray(raw[resource_offset:resource_offset + resource_count * resource_entry_size])
    strings = raw[string_offset:string_offset + string_size]
    if len(strings) != string_size:
        raise KSPError("string table is outside the source file")

    new_page_offset = HEADER_SIZE + len(engines)
    new_track_offset = new_page_offset + len(page_table)
    new_resource_offset = new_track_offset + len(tracks)
    new_string_offset = new_resource_offset + len(resources)
    cursor = new_string_offset + len(strings)

    put_u32(engine, 36, cursor)
    engines[:ENGINE_SIZE] = engine
    cursor += len(template_payload)
    for index, payload in enumerate(page_payloads):
        put_u32(page_table, index * PAGE_SIZE + 8, cursor)
        cursor += len(payload)

    resource_payloads: list[bytes] = []
    for index in range(resource_count):
        entry_offset = index * resource_entry_size
        old_offset = u32(resources, entry_offset + 8)
        packed = u32(resources, entry_offset + 12)
        payload = raw[old_offset:old_offset + packed]
        if len(payload) != packed:
            raise KSPError(f"resource {index} is outside the source file")
        put_u32(resources, entry_offset + 8, cursor)
        resource_payloads.append(payload)
        cursor += len(payload)

    header = bytearray(raw[:HEADER_SIZE])
    put_u32(header, 12, cursor)
    put_u32(header, 24, new_page_offset)
    put_u16(header, 28, len(old_pages))
    put_u32(header, 32, new_track_offset)
    put_u32(header, 40, new_resource_offset)
    put_u32(header, 48, new_string_offset)
    put_u32(header, 64, 0)
    index = bytes(engines + page_table + tracks + resources + strings)
    put_u32(header, 68, crc32(index))
    put_u32(header, 64, crc32(header))

    result = bytes(
        header + engines + page_table + tracks + resources + strings +
        template_payload + b"".join(page_payloads) + b"".join(resource_payloads)
    )
    if len(result) != cursor:
        raise KSPError("pruned file-size mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    verified = parse_ksp(output)
    if len(verified.pages) != len(old_pages):
        raise KSPError("pruned page count mismatch")
    return {
        "input": str(source),
        "output": str(output),
        "input_bytes": len(raw),
        "output_bytes": len(result),
        "input_pages": len(package.pages),
        "output_pages": len(verified.pages),
        "reachable_pages": old_pages,
        "page_bytes_removed": sum(entry.packed_size for index, entry in enumerate(package.page_entries) if index not in page_map),
        "sha256": __import__("hashlib").sha256(result).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = prune(args.input, args.output)
    except (KSPError, OSError) as exc:
        parser.error(str(exc))
    print(f"Pages: {report['input_pages']} -> {report['output_pages']}")
    print(f"Size:  {report['input_bytes']} -> {report['output_bytes']} bytes")
    print(f"KSP:   {report['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
