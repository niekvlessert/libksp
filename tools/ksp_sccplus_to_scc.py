#!/usr/bin/env python3
"""Convert an HSC1 SCC+ KSP 1.0 package to a normal-SCC HSC0 package.

The converter keeps all five source frequencies and volumes, dynamically maps
five source voices to five normal-SCC oscillators, and assigns the two voices
with the closest phase-aligned, volume-weighted waveforms to SCC channels 4/5,
which share one physical waveform RAM. By default the louder member of the
closest pair is retained exactly; an optional aligned, volume-weighted blend
is available. Pair and channel mapping hysteresis avoids rapid remapping when
candidates are nearly equal. Extremely close duplicate waveforms are merged
only when a page would otherwise exceed the normal-SCC MSX payload window.

The input profile is the standalone KSP 1.0 HSC1 event-replayer profile used by
the HuC6280-to-SCC+ packs. The output uses a compact normal-SCC Z80 HSC0 replay
engine and preserves track ordering, IDs, titles, page chains, loops and timing.
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import itertools
import json
import math
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

NULL16 = 0xFFFF
NULL32 = 0xFFFFFFFF
PAGE_SIZE = 0x4000
PAGE_LOAD = 0x4000
TRACK_ADDRESS = 0x4800
TRACK_OFFSET = TRACK_ADDRESS - PAGE_LOAD
MAX_BLOCK = PAGE_SIZE - TRACK_OFFSET
KSP_ENGINE_DYNAMIC_PAGES = 1
KSP_HARDWARE_PSG = 1 << 0
KSP_HARDWARE_SCC = 1 << 1
KSP_HARDWARE_SCCPLUS = 1 << 2
KSP_PAGE_SPARSE_OVERLAY = 0
KSP_COMPRESSION_NONE = 0
KSP_COMPRESSION_ZX0 = 1

Waveform = Tuple[int, ...]
SCCPlusState = Tuple[
    Tuple[int, ...], Tuple[int, ...], Tuple[Waveform, ...], int, int, int, int
]
NormalSCCState = Tuple[
    Tuple[int, ...], Tuple[int, ...], Tuple[Waveform, ...], int, int, int, int
]


def u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def crc32(data: bytes | bytearray) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Forward ZX0 codec (decoder plus a deterministic, conservative compressor)
# ---------------------------------------------------------------------------

def zx0_decompress(inp: bytes, outsize: int) -> bytes:
    idx = 0
    bit_mask = 0
    bit_value = 0
    last_byte = 0
    backtrack = False
    out = bytearray()

    def read_byte() -> int:
        nonlocal idx, last_byte
        if idx >= len(inp):
            raise ValueError("truncated ZX0 stream")
        last_byte = inp[idx]
        idx += 1
        return last_byte

    def read_bit() -> int:
        nonlocal backtrack, bit_mask, bit_value
        if backtrack:
            backtrack = False
            return last_byte & 1
        if bit_mask == 0:
            bit_value = read_byte()
            bit_mask = 0x80
        value = 1 if bit_value & bit_mask else 0
        bit_mask >>= 1
        return value

    def gamma(invert: int) -> int:
        value = 1
        while not read_bit():
            value = (value << 1) | (read_bit() ^ invert)
        return value

    def literals(count: int) -> None:
        for _ in range(count):
            out.append(read_byte())

    def copy(offset: int, count: int) -> None:
        if offset <= 0 or offset > len(out):
            raise ValueError(f"invalid ZX0 offset {offset}")
        for _ in range(count):
            out.append(out[-offset])

    offset = 1
    literals(gamma(0))
    while True:
        branch = read_bit()
        if not branch:
            copy(offset, gamma(0))
            branch = read_bit()
            if not branch:
                literals(gamma(0))
                continue
        while True:
            msb = gamma(1)
            if msb == 256:
                if len(out) != outsize:
                    raise ValueError(f"ZX0 size mismatch {len(out)} != {outsize}")
                return bytes(out)
            lsb = read_byte()
            offset = msb * 128 - (lsb >> 1)
            backtrack = True
            copy(offset, gamma(0) + 1)
            branch = read_bit()
            if not branch:
                literals(gamma(0))
                break


def gamma_bits(value: int, invert: int) -> List[int]:
    result: List[int] = []
    for digit in bin(value)[3:]:
        result.extend((0, (ord(digit) - 48) ^ invert))
    result.append(1)
    return result


class ZX0Writer:
    def __init__(self) -> None:
        self.output = bytearray()
        self.control_position = -1
        self.control_bit = 8

    def bit(self, value: int) -> None:
        if self.control_bit == 8:
            self.control_position = len(self.output)
            self.output.append(0)
            self.control_bit = 0
        if value:
            self.output[self.control_position] |= 1 << (7 - self.control_bit)
        self.control_bit += 1

    def bits(self, values: Iterable[int]) -> None:
        for value in values:
            self.bit(value)

    def byte(self, value: int) -> None:
        self.output.append(value & 0xFF)

    def data(self, values: bytes) -> None:
        self.output.extend(values)


def zx0_tokens(raw: bytes, minimum_match: int = 4, maximum_candidates: int = 96):
    table: Dict[bytes, List[int]] = defaultdict(list)
    tokens = []
    literal_start = 0
    position = 0
    size = len(raw)

    def add(index: int) -> None:
        if index + 2 >= size:
            return
        key = raw[index:index + 3]
        candidates = table[key]
        candidates.append(index)
        if len(candidates) > maximum_candidates * 4:
            cutoff = index - 32640
            candidates[:] = [x for x in candidates if x >= cutoff][-maximum_candidates * 2:]

    while position < size:
        best_length = 0
        best_offset = 0
        if position + 2 < size:
            for candidate in reversed(table.get(raw[position:position + 3], ())[-maximum_candidates:]):
                offset = position - candidate
                if not 1 <= offset <= 32640:
                    continue
                limit = min(size - position, 0xFFFF)
                length = 3
                while length < limit and raw[candidate + length] == raw[position + length]:
                    length += 1
                if length > best_length:
                    best_length = length
                    best_offset = offset
                    if length >= 1024:
                        break
        if best_length >= minimum_match:
            if literal_start < position:
                tokens.append(("literal", raw[literal_start:position]))
            tokens.append(("match", best_offset, best_length))
            for index in range(position, min(size, position + best_length)):
                add(index)
            position += best_length
            literal_start = position
        else:
            add(position)
            position += 1
    if literal_start < size:
        tokens.append(("literal", raw[literal_start:]))
    if not tokens:
        tokens = [("literal", b"\0")]
    if tokens[0][0] != "literal":
        # In practice position zero cannot have a match; keep this defensive.
        tokens.insert(0, ("literal", raw[:1]))
    return tokens


_compress_cache: Dict[bytes, bytes] = {}


def zx0_compress(raw: bytes) -> bytes:
    if not raw:
        return b""
    key = hashlib.sha256(raw).digest()
    cached = _compress_cache.get(key)
    if cached is not None:
        return cached
    tokens = zx0_tokens(raw)
    writer = ZX0Writer()
    first = tokens[0][1]
    writer.bits(gamma_bits(len(first), 0))
    writer.data(first)
    previous = "literal"
    for token in tokens[1:]:
        if token[0] == "literal":
            if previous != "match":
                raise ValueError("adjacent ZX0 literal tokens")
            literal = token[1]
            writer.bit(0)
            writer.bits(gamma_bits(len(literal), 0))
            writer.data(literal)
            previous = "literal"
            continue
        writer.bit(1)
        _, offset, length = token
        msb = (offset + 127) // 128
        remainder = msb * 128 - offset
        length_bits = gamma_bits(length - 1, 0)
        writer.bits(gamma_bits(msb, 1))
        writer.byte((remainder << 1) | length_bits[0])
        writer.bits(length_bits[1:])
        previous = "match"
    writer.bit(1)
    writer.bits(gamma_bits(256, 1))
    packed = bytes(writer.output)
    if zx0_decompress(packed, len(raw)) != raw:
        raise ValueError("ZX0 compressor round-trip failed")
    _compress_cache[key] = packed
    return packed


def compress_object(raw: bytes, enabled: bool = True) -> Tuple[int, bytes]:
    if not enabled:
        return KSP_COMPRESSION_NONE, raw
    packed = zx0_compress(raw)
    if len(packed) < len(raw):
        return KSP_COMPRESSION_ZX0, packed
    return KSP_COMPRESSION_NONE, raw


# ---------------------------------------------------------------------------
# KSP 1.0 parser
# ---------------------------------------------------------------------------
@dataclass
class EngineEntry:
    flags: int
    hardware: int
    abi: int
    tick_rate: int
    load_address: int
    page_size: int
    init_address: int
    play_address: int
    stop_address: int
    gateway: int
    replace_start: int
    first_page: int
    page_count: int
    default_mwk: int
    compression: int
    first_bank: int
    bank_count: int
    bank_width: int
    template_offset: int
    template_packed: int
    template_unpacked: int
    template_crc: int
    name_offset: int


@dataclass
class PageEntry:
    engine: int
    encoding: int
    compression: int
    flags: int
    offset: int
    packed: int
    unpacked: int
    final_crc: int


@dataclass
class TrackEntry:
    page: int
    song: int
    flags: int
    mwk: int
    image: int
    title: str
    duration: int
    loop_start: int
    loop_end: int
    fade: int


@dataclass
class ResourceEntry:
    kind: bytes
    flags: int
    compression: int
    offset: int
    packed: int
    unpacked: int
    crc: int
    aux0: int
    aux1: int
    payload: bytes


@dataclass
class KSPPackage:
    raw: bytes
    engines: List[EngineEntry]
    page_entries: List[PageEntry]
    pages: List[bytes]
    tracks: List[TrackEntry]
    resources: List[ResourceEntry]
    strings: bytes
    default_track: int
    meta_index: int
    cover_index: int


def decode_object(data: bytes, offset: int, packed: int, unpacked: int, compression: int) -> bytes:
    if offset > len(data) or packed > len(data) - offset:
        raise ValueError("KSP payload outside file")
    payload = data[offset:offset + packed]
    if compression == KSP_COMPRESSION_NONE:
        if packed != unpacked:
            raise ValueError("uncompressed KSP object size mismatch")
        return payload
    if compression == KSP_COMPRESSION_ZX0:
        return zx0_decompress(payload, unpacked)
    raise ValueError(f"unsupported KSP compression {compression}")


def apply_sparse_overlay(template: bytes, overlay: bytes) -> bytes:
    page = bytearray(template)
    cursor = 0
    while cursor < len(overlay):
        if cursor + 4 > len(overlay):
            raise ValueError("truncated sparse overlay")
        offset, length = struct.unpack_from("<HH", overlay, cursor)
        cursor += 4
        if cursor + length > len(overlay) or offset + length > len(page):
            raise ValueError("invalid sparse overlay record")
        page[offset:offset + length] = overlay[cursor:cursor + length]
        cursor += length
    return bytes(page)


def parse_ksp(path: Path) -> KSPPackage:
    data = path.read_bytes()
    if len(data) < 80 or data[:4] != b"KSP1":
        raise ValueError("input is not standalone KSP 1.0")
    if u16(data, 4) != 80 or u16(data, 6) != 0 or u32(data, 8) != 0:
        raise ValueError("unsupported KSP header")
    if u32(data, 12) != len(data):
        raise ValueError("KSP file-size field mismatch")
    header_copy = bytearray(data[:80])
    stored_header_crc = u32(header_copy, 64)
    struct.pack_into("<I", header_copy, 64, 0)
    if stored_header_crc and crc32(header_copy) != stored_header_crc:
        raise ValueError("KSP header CRC mismatch")

    engine_offset, engine_count, engine_size = u32(data, 16), u16(data, 20), u16(data, 22)
    page_offset, page_count, page_size = u32(data, 24), u16(data, 28), u16(data, 30)
    track_offset, track_count, track_size = u32(data, 32), u16(data, 36), u16(data, 38)
    resource_offset, resource_count, resource_size = u32(data, 40), u16(data, 44), u16(data, 46)
    string_offset, string_size = u32(data, 48), u32(data, 52)
    if (engine_size, page_size, track_size, resource_size) != (64, 24, 32, 32):
        raise ValueError("unsupported KSP table entry size")

    def take(offset: int, size: int, label: str) -> bytes:
        if offset > len(data) or size > len(data) - offset:
            raise ValueError(f"{label} outside file")
        return data[offset:offset + size]

    engine_table = take(engine_offset, engine_count * 64, "engine table")
    page_table = take(page_offset, page_count * 24, "page table")
    track_table = take(track_offset, track_count * 32, "track table")
    resource_table = take(resource_offset, resource_count * 32, "resource table")
    strings = take(string_offset, string_size, "string table")
    stored_index_crc = u32(data, 68)
    if stored_index_crc and crc32(engine_table + page_table + track_table + resource_table + strings) != stored_index_crc:
        raise ValueError("KSP index CRC mismatch")

    def string_at(offset: int) -> str:
        if offset == NULL32:
            return ""
        if offset >= len(strings):
            raise ValueError("KSP string offset outside table")
        end = strings.find(b"\0", offset)
        if end < 0:
            raise ValueError("unterminated KSP string")
        return strings[offset:end].decode("utf-8")

    engines: List[EngineEntry] = []
    templates: List[bytes] = []
    for index in range(engine_count):
        entry = engine_table[index * 64:(index + 1) * 64]
        values = struct.unpack_from("<IIHHHHHHHHHHHHBBBBIIIII", entry, 0)
        engine = EngineEntry(*values)
        if engine.page_size != PAGE_SIZE or engine.load_address != PAGE_LOAD:
            raise ValueError("converter requires a 0x4000-0x7FFF engine page")
        template = decode_object(data, engine.template_offset, engine.template_packed,
                                 engine.template_unpacked, engine.compression)
        if len(template) != engine.page_size:
            raise ValueError("engine template size mismatch")
        if engine.template_crc and crc32(template) != engine.template_crc:
            raise ValueError("engine template CRC mismatch")
        engines.append(engine)
        templates.append(template)

    page_entries: List[PageEntry] = []
    pages: List[bytes] = []
    for index in range(page_count):
        entry = page_table[index * 24:(index + 1) * 24]
        owner, encoding, compression, flags, reserved, offset, packed, unpacked, final_crc = struct.unpack("<HBBHHIIII", entry)
        if reserved != 0 or owner >= len(engines):
            raise ValueError("invalid page entry")
        page_entry = PageEntry(owner, encoding, compression, flags, offset, packed, unpacked, final_crc)
        payload = decode_object(data, offset, packed, unpacked, compression)
        if encoding == KSP_PAGE_SPARSE_OVERLAY:
            page = apply_sparse_overlay(templates[owner], payload)
        elif encoding == 1:
            page = payload
        else:
            raise ValueError(f"input page {index} uses unsupported encoding {encoding}")
        if len(page) != engines[owner].page_size:
            raise ValueError("reconstructed page size mismatch")
        if final_crc and crc32(page) != final_crc:
            raise ValueError(f"page {index} CRC mismatch")
        page_entries.append(page_entry)
        pages.append(page)

    tracks: List[TrackEntry] = []
    for index in range(track_count):
        entry = track_table[index * 32:(index + 1) * 32]
        page, song, flags, mwk, image, reserved, title, duration, loop_start, loop_end, fade = struct.unpack("<HHHHHHIIIII", entry)
        if reserved or page >= len(pages):
            raise ValueError("invalid track entry")
        tracks.append(TrackEntry(page, song, flags, mwk, image, string_at(title),
                                 duration, loop_start, loop_end, fade))

    resources: List[ResourceEntry] = []
    for index in range(resource_count):
        entry = resource_table[index * 32:(index + 1) * 32]
        kind = entry[:4]
        flags, compression, reserved, offset, packed, unpacked, expected_crc, aux0, aux1 = struct.unpack_from("<HBBIIIIII", entry, 4)
        if reserved:
            raise ValueError("invalid resource entry")
        payload = decode_object(data, offset, packed, unpacked, compression)
        if expected_crc and crc32(payload) != expected_crc:
            raise ValueError(f"resource {index} CRC mismatch")
        resources.append(ResourceEntry(kind, flags, compression, offset, packed, unpacked,
                                       expected_crc, aux0, aux1, payload))

    return KSPPackage(data, engines, page_entries, pages, tracks, resources, strings,
                      u16(data, 56), u16(data, 58), u16(data, 60))


# ---------------------------------------------------------------------------
# HSC1 event decoding
# ---------------------------------------------------------------------------
@dataclass
class HSCEvent:
    frame: int
    event_pointer: int
    state: SCCPlusState


@dataclass
class HSC1Block:
    flags: int
    wave_count: int
    total_frames: int
    loop_pointer: int
    stream_offset: int
    next_page: int
    events: List[HSCEvent]
    loop_frame: Optional[int]
    local_frames: int


def zero_sccplus_state() -> SCCPlusState:
    zero_wave: Waveform = tuple([0] * 32)
    return ((0,) * 5, (0,) * 5, (zero_wave,) * 5, 1, 0, 8, 0)


def zero_normal_state() -> NormalSCCState:
    zero_wave: Waveform = tuple([0] * 32)
    return ((0,) * 5, (0,) * 5, (zero_wave,) * 4, 1, 0, 8, 0)


def parse_hsc1(block: bytes) -> HSC1Block:
    if len(block) < 17 or block[:4] != b"HSC1":
        raise ValueError("runtime page does not contain HSC1")
    flags = block[4]
    wave_count = block[5]
    total_frames = u16(block, 6)
    loop_pointer = u16(block, 8)
    stream_offset = u16(block, 10)
    next_page = block[12]
    if block[13] != ord("C") or block[14:16] != b"\0\0":
        raise ValueError("unsupported HSC1 header")
    if stream_offset != 16 + wave_count * 32 or stream_offset >= len(block):
        raise ValueError("invalid HSC1 waveform dictionary")
    dictionary: List[Waveform] = [
        tuple(block[16 + index * 32:16 + (index + 1) * 32])
        for index in range(wave_count)
    ]
    cursor = stream_offset
    previous_frame = -1
    periods = [0] * 5
    volumes = [0] * 5
    wave_ids = [0] * 5
    psg_period = 1
    psg_volume = 0
    noise_period = 8
    noise_volume = 0
    events: List[HSCEvent] = []
    while True:
        if cursor >= len(block):
            raise ValueError("unterminated HSC1 stream")
        delay = block[cursor]
        cursor += 1
        if delay == 0xFF:
            break
        event_pointer = cursor
        frame = previous_frame + delay + 1
        if cursor + 3 > len(block):
            raise ValueError("truncated HSC1 masks")
        frequency_mask, volume_mask, wave_mask = block[cursor:cursor + 3]
        cursor += 3
        if wave_mask & 0xE0:
            raise ValueError("invalid HSC1 wave mask")
        for index in range(5):
            if wave_mask & (1 << index):
                if cursor >= len(block):
                    raise ValueError("truncated HSC1 waveform ID")
                wave_ids[index] = block[cursor]
                cursor += 1
                if wave_ids[index] >= wave_count:
                    raise ValueError("HSC1 waveform ID out of range")
        for index in range(5):
            if frequency_mask & (1 << index):
                if cursor + 2 > len(block):
                    raise ValueError("truncated HSC1 frequency")
                periods[index] = u16(block, cursor) & 0x0FFF
                cursor += 2
        if frequency_mask & 0x20:
            psg_period = u16(block, cursor)
            cursor += 2
        if frequency_mask & 0x40:
            noise_period = block[cursor] & 31
            cursor += 1
        for index in range(5):
            if volume_mask & (1 << index):
                volumes[index] = block[cursor] & 15
                cursor += 1
        if volume_mask & 0x20:
            psg_volume = block[cursor] & 15
            cursor += 1
        if volume_mask & 0x40:
            noise_volume = block[cursor] & 15
            cursor += 1
        state: SCCPlusState = (
            tuple(periods), tuple(volumes), tuple(dictionary[value] for value in wave_ids),
            psg_period, psg_volume, noise_period, noise_volume,
        )
        events.append(HSCEvent(frame, event_pointer, state))
        previous_frame = frame
    if cursor != len(block):
        raise ValueError("trailing bytes after HSC1 stream")
    if not events:
        raise ValueError("empty HSC1 stream")
    loop_event = next((event for event in events if event.event_pointer == loop_pointer), None)
    return HSC1Block(flags, wave_count, total_frames, loop_pointer, stream_offset,
                     next_page, events, loop_event.frame if loop_event else None,
                     events[-1].frame + 1)


def extract_hsc1_page(page: bytes) -> Tuple[bytes, HSC1Block]:
    if page[TRACK_OFFSET:TRACK_OFFSET + 4] != b"HSC1":
        raise ValueError("page has no HSC1 block at 0x4800")
    # HSC streams consume the rest of the sparse record, not the zero padding.
    # Find the terminator by parsing progressively from the known stream layout.
    # The caller supplies reconstructed pages; use the first zero-filled tail only
    # after a structurally valid 0xFF stream terminator.
    header = page[TRACK_OFFSET:]
    stream_offset = u16(header, 10)
    cursor = stream_offset
    wave_count = header[5]
    if stream_offset != 16 + 32 * wave_count:
        raise ValueError("invalid HSC1 stream offset")
    while True:
        if cursor >= len(header):
            raise ValueError("HSC1 stream exceeds page")
        delay = header[cursor]
        cursor += 1
        if delay == 0xFF:
            break
        if cursor + 3 > len(header):
            raise ValueError("truncated HSC1 event")
        fm, vm, wm = header[cursor:cursor + 3]
        cursor += 3
        cursor += sum((wm >> index) & 1 for index in range(5))
        cursor += 2 * sum((fm >> index) & 1 for index in range(6))
        cursor += (fm >> 6) & 1
        cursor += sum((vm >> index) & 1 for index in range(7))
    block = bytes(header[:cursor])
    return block, parse_hsc1(block)


# ---------------------------------------------------------------------------
# Dynamic SCC+ -> normal SCC allocator
# ---------------------------------------------------------------------------
SCC_VOLUME_AMPLITUDE = tuple(index / 15.0 for index in range(16))
PAIR_HYSTERESIS_ABSOLUTE = 0.0125
PAIR_HYSTERESIS_RELATIVE = 0.16
OUTPUT_SWITCH_PENALTY = 0.018
PAIR_ORDER_SWITCH_PENALTY = 0.008


def signed_wave(wave: Sequence[int]) -> List[float]:
    return [float(value - 256 if value >= 128 else value) for value in wave]


def byte_wave(values: Sequence[float]) -> Waveform:
    result = []
    for value in values:
        rounded = int(round(value))
        rounded = max(-128, min(127, rounded))
        result.append(rounded & 0xFF)
    return tuple(result)


def normalise_shape(values: Sequence[float]) -> List[float]:
    mean = sum(values) / len(values)
    centred = [value - mean for value in values]
    rms = math.sqrt(sum(value * value for value in centred) / len(centred))
    if rms < 1e-9:
        return [0.0] * len(values)
    return [value / rms for value in centred]


@dataclass(frozen=True)
class WaveAlignment:
    shift: int
    distance: float
    correlation: float


def phase_aligned_distance(first: Waveform, second: Waveform) -> WaveAlignment:
    first_shape = normalise_shape(signed_wave(first))
    second_shape = normalise_shape(signed_wave(second))
    first_nonzero = any(abs(value) > 1e-12 for value in first_shape)
    second_nonzero = any(abs(value) > 1e-12 for value in second_shape)
    if not first_nonzero and not second_nonzero:
        return WaveAlignment(0, 0.0, 1.0)
    if not first_nonzero or not second_nonzero:
        return WaveAlignment(0, 1.0, -1.0)
    best = WaveAlignment(0, float("inf"), -1.0)
    for shift in range(32):
        shifted = second_shape[-shift:] + second_shape[:-shift] if shift else second_shape
        correlation = sum(a * b for a, b in zip(first_shape, shifted)) / 32.0
        distance = max(0.0, min(1.0, (1.0 - correlation) * 0.5))
        if distance < best.distance:
            best = WaveAlignment(shift, distance, correlation)
    return best


def voice_amplitude(volume: int) -> float:
    return SCC_VOLUME_AMPLITUDE[max(0, min(15, int(volume)))]


def pair_distortion(first_wave: Waveform, second_wave: Waveform,
                    first_volume: int, second_volume: int,
                    alignment: Optional[WaveAlignment] = None) -> Tuple[float, WaveAlignment]:
    first_amplitude = voice_amplitude(first_volume)
    second_amplitude = voice_amplitude(second_volume)
    if first_amplitude <= 0.0 or second_amplitude <= 0.0:
        return 0.0, WaveAlignment(0, 0.0, 1.0)
    if alignment is None:
        alignment = phase_aligned_distance(first_wave, second_wave)
    audibility = 2.0 * min(first_amplitude, second_amplitude) / (first_amplitude + second_amplitude)
    return alignment.distance * audibility, alignment


def blend_shared_waveform(first_wave: Waveform, second_wave: Waveform,
                          first_volume: int, second_volume: int,
                          alignment: WaveAlignment,
                          previous_wave: Waveform) -> Waveform:
    first_amplitude = voice_amplitude(first_volume)
    second_amplitude = voice_amplitude(second_volume)
    if first_amplitude <= 0.0 and second_amplitude <= 0.0:
        return previous_wave
    if second_amplitude <= 0.0:
        return first_wave
    if first_amplitude <= 0.0:
        return second_wave
    first_values = signed_wave(first_wave)
    second_values = signed_wave(second_wave)
    shift = alignment.shift
    if shift:
        second_values = second_values[-shift:] + second_values[:-shift]
    shared = [
        (a * first_amplitude + b * second_amplitude) / (first_amplitude + second_amplitude)
        for a, b in zip(first_values, second_values)
    ]
    return byte_wave(shared)


@dataclass
class PairingDecision:
    mapping: Tuple[int, int, int, int, int]
    pair: Tuple[int, int]
    pair_cost: float
    fixed_pair_cost: float
    retained_by_hysteresis: bool


class DynamicSCCAllocator:
    def __init__(self, shared_wave_strategy: str = "louder") -> None:
        if shared_wave_strategy not in ("louder", "blend"):
            raise ValueError("shared-wave strategy must be louder or blend")
        self.shared_wave_strategy = shared_wave_strategy
        self.previous_mapping = (0, 1, 2, 3, 4)
        self.previous_shared_wave: Waveform = tuple([0] * 32)
        self.alignment_cache: Dict[Tuple[Waveform, Waveform], WaveAlignment] = {}
        self.frames = 0
        self.mapping_changes = 0
        self.pair_changes = 0
        self.hysteresis_retentions = 0
        self.exact_pair_frames = 0
        self.distortion_sum = 0.0
        self.fixed_distortion_sum = 0.0
        self.pair_usage: Dict[Tuple[int, int], int] = defaultdict(int)

    def _alignment(self, first: Waveform, second: Waveform) -> WaveAlignment:
        key = (first, second)
        result = self.alignment_cache.get(key)
        if result is None:
            result = phase_aligned_distance(first, second)
            self.alignment_cache[key] = result
        return result

    def _pair_costs(self, volumes: Sequence[int], waves: Sequence[Waveform]):
        result = {}
        for first, second in itertools.combinations(range(5), 2):
            alignment = self._alignment(waves[first], waves[second])
            cost, _ = pair_distortion(waves[first], waves[second], volumes[first], volumes[second], alignment)
            result[(first, second)] = (cost, alignment)
        return result

    def _choose_pair(self, costs):
        best_pair, (best_cost, best_alignment) = min(costs.items(), key=lambda item: (item[1][0], item[0]))
        current_pair = tuple(sorted(self.previous_mapping[3:5]))
        current_cost, current_alignment = costs[current_pair]
        margin = max(PAIR_HYSTERESIS_ABSOLUTE, best_cost * PAIR_HYSTERESIS_RELATIVE)
        if current_cost <= best_cost + margin:
            return current_pair, current_cost, best_cost, True, current_alignment
        return best_pair, best_cost, best_cost, False, best_alignment

    def _mapping_cost(self, mapping: Tuple[int, int, int, int, int], volumes: Sequence[int]) -> float:
        cost = 0.0
        for output, source in enumerate(mapping):
            previous_source = self.previous_mapping[output]
            if source != previous_source:
                cost += OUTPUT_SWITCH_PENALTY * max(
                    voice_amplitude(volumes[source]), voice_amplitude(volumes[previous_source])
                )
        if mapping[3:5] != self.previous_mapping[3:5]:
            cost += PAIR_ORDER_SWITCH_PENALTY
        return cost

    def _choose_mapping(self, pair: Tuple[int, int], volumes: Sequence[int]):
        remaining = [source for source in range(5) if source not in pair]
        candidates = []
        for independent in itertools.permutations(remaining):
            for shared_order in (pair, (pair[1], pair[0])):
                mapping = tuple(independent + shared_order)
                candidates.append((self._mapping_cost(mapping, volumes), mapping))
        return min(candidates, key=lambda item: (item[0], item[1]))[1]

    def allocate(self, state: SCCPlusState) -> Tuple[NormalSCCState, PairingDecision]:
        periods, volumes, waves, psg_period, psg_volume, noise_period, noise_volume = state
        costs = self._pair_costs(volumes, waves)
        pair, pair_cost, best_cost, retained, _ = self._choose_pair(costs)
        mapping = self._choose_mapping(pair, volumes)
        shared_first, shared_second = mapping[3], mapping[4]
        alignment = self._alignment(waves[shared_first], waves[shared_second])
        if self.shared_wave_strategy == "blend":
            shared_wave = blend_shared_waveform(
                waves[shared_first], waves[shared_second], volumes[shared_first], volumes[shared_second],
                alignment, self.previous_shared_wave,
            )
        else:
            # Keep the louder member exactly. The pair has already been selected
            # for closest phase-aligned shape, so the quieter voice incurs the
            # smallest available timbral error without creating new dictionary waves.
            if volumes[shared_second] > volumes[shared_first]:
                shared_wave = waves[shared_second]
            else:
                shared_wave = waves[shared_first]
        output: NormalSCCState = (
            tuple(periods[source] for source in mapping),
            tuple(volumes[source] for source in mapping),
            (waves[mapping[0]], waves[mapping[1]], waves[mapping[2]], shared_wave),
            psg_period, psg_volume, noise_period, noise_volume,
        )
        if mapping != self.previous_mapping:
            self.mapping_changes += 1
        if set(mapping[3:5]) != set(self.previous_mapping[3:5]):
            self.pair_changes += 1
        instantaneous_best = min(costs, key=lambda candidate: (costs[candidate][0], candidate))
        if retained and tuple(sorted(mapping[3:5])) != instantaneous_best:
            self.hysteresis_retentions += 1
        if pair_cost <= 1e-12:
            self.exact_pair_frames += 1
        fixed_cost, _ = pair_distortion(waves[3], waves[4], volumes[3], volumes[4],
                                        self._alignment(waves[3], waves[4]))
        self.distortion_sum += pair_cost
        self.fixed_distortion_sum += fixed_cost
        self.frames += 1
        normalized_pair = tuple(sorted(mapping[3:5]))
        self.pair_usage[normalized_pair] += 1
        self.previous_mapping = mapping
        self.previous_shared_wave = shared_wave
        return output, PairingDecision(mapping, normalized_pair, pair_cost, fixed_cost, retained)

    def statistics(self) -> dict:
        frames = max(1, self.frames)
        return {
            "frames": self.frames,
            "mapping_changes": self.mapping_changes,
            "pair_changes": self.pair_changes,
            "hysteresis_retentions": self.hysteresis_retentions,
            "exact_pair_frames": self.exact_pair_frames,
            "exact_pair_fraction": self.exact_pair_frames / frames,
            "mean_pair_distortion": self.distortion_sum / frames,
            "mean_fixed_source_4_5_distortion": self.fixed_distortion_sum / frames,
            "distortion_reduction_vs_fixed": (
                0.0 if self.fixed_distortion_sum <= 1e-12
                else 1.0 - self.distortion_sum / self.fixed_distortion_sum
            ),
            "pair_usage_frames": {f"{a}+{b}": count for (a, b), count in sorted(self.pair_usage.items())},
        }


# ---------------------------------------------------------------------------
# HSC0 encoder
# ---------------------------------------------------------------------------
def state_delta(previous: NormalSCCState, current: NormalSCCState,
                hardware_waves: Sequence[Optional[Waveform]],
                force_full: bool = False):
    periods, volumes, waves, psg_period, psg_volume, noise_period, noise_volume = current
    old_periods, old_volumes, _old_waves, old_psg_period, old_psg_volume, old_noise_period, old_noise_volume = previous
    if force_full:
        return 0x7F, 0x7F, 0x0F
    frequency_mask = 0
    volume_mask = 0
    wave_mask = 0
    for index in range(5):
        audible = volumes[index] > 0
        if audible and (periods[index] != old_periods[index] or old_volumes[index] == 0):
            frequency_mask |= 1 << index
        if volumes[index] != old_volumes[index]:
            volume_mask |= 1 << index
    for index in range(4):
        audible = volumes[index] > 0 if index < 3 else (volumes[3] > 0 or volumes[4] > 0)
        # Compare against what is known to be in physical SCC waveform RAM,
        # not against the preceding logical state. A source can select an
        # instrument while muted; no write was emitted then, so the waveform
        # must still be installed when that oscillator becomes audible.
        if audible and waves[index] != hardware_waves[index]:
            wave_mask |= 1 << index
    if psg_volume > 0 and (psg_period != old_psg_period or old_psg_volume == 0):
        frequency_mask |= 0x20
    if psg_volume != old_psg_volume:
        volume_mask |= 0x20
    if noise_volume > 0 and (noise_period != old_noise_period or old_noise_volume == 0):
        frequency_mask |= 0x40
    if noise_volume != old_noise_volume:
        volume_mask |= 0x40
    return frequency_mask, volume_mask, wave_mask


def encode_hsc0(states: Sequence[NormalSCCState], initial_state: NormalSCCState,
                total_frames: int, flags: int, next_page: int,
                force_full_frames: Iterable[int], force_event_frame0: bool,
                initial_hardware_waves: Optional[Sequence[Optional[Waveform]]] = None,
                _merge_near_duplicates: bool = False) -> Tuple[bytes, dict, Tuple[Optional[Waveform], ...]]:
    if not states:
        raise ValueError("cannot encode empty HSC0 page")
    forced = set(force_full_frames)
    events = []
    previous = initial_state
    hardware_waves: List[Optional[Waveform]] = list(initial_hardware_waves or (None, None, None, None))
    if len(hardware_waves) != 4:
        raise ValueError("initial_hardware_waves must contain four entries")
    for frame, state in enumerate(states):
        force_full = frame in forced
        frequency_mask, volume_mask, wave_mask = state_delta(previous, state, hardware_waves, force_full)
        if frequency_mask or volume_mask or wave_mask or force_full or (force_event_frame0 and frame == 0):
            events.append([frame, frequency_mask, volume_mask, wave_mask, state, force_full])
            for index in range(4):
                if wave_mask & (1 << index):
                    hardware_waves[index] = state[2][index]
        previous = state
    # Preserve the exact chunk boundary even when conversion removes the source's final delta.
    end_frame = len(states) - 1
    if not events or events[-1][0] != end_frame:
        events.append([end_frame, 0, 0, 0, states[-1], False])

    # A delay byte is limited to 0..254. Insert zero-mask timing anchors.
    expanded = []
    previous_frame = -1
    for event in events:
        frame = event[0]
        while frame - previous_frame - 1 > 254:
            previous_frame += 255
            expanded.append([previous_frame, 0, 0, 0, states[previous_frame], False])
        expanded.append(event)
        previous_frame = frame
    events = expanded

    wave_ids: Dict[Waveform, int] = {}
    wave_dictionary: List[Waveform] = []
    wave_alias_merges = 0
    # HSC0 stores a page-local waveform dictionary.  Coalesce only extremely
    # close, phase-identical shapes.  This is deliberately conservative: it
    # avoids spending 32 bytes on practically duplicate source instruments,
    # while never merging a cyclically shifted waveform.
    for _, _, _, wave_mask, state, _ in events:
        for index in range(4):
            if wave_mask & (1 << index):
                wave = state[2][index]
                if wave not in wave_ids:
                    alias = None
                    if _merge_near_duplicates:
                        for candidate_id, candidate in enumerate(wave_dictionary):
                            alignment = phase_aligned_distance(candidate, wave)
                            if alignment.shift == 0 and alignment.distance <= 0.004:
                                alias = candidate_id
                                break
                    if alias is not None:
                        wave_ids[wave] = alias
                        wave_alias_merges += 1
                    else:
                        if len(wave_dictionary) >= 255:
                            raise ValueError("HSC0 page needs more than 255 waveform dictionary entries")
                        wave_ids[wave] = len(wave_dictionary)
                        wave_dictionary.append(wave)

    stream_offset = 16 + 32 * len(wave_dictionary)
    stream = bytearray()
    previous_frame = -1
    event_pointer_by_frame: Dict[int, int] = {}
    for frame, frequency_mask, volume_mask, wave_mask, state, _ in events:
        stream.append(frame - previous_frame - 1)
        event_pointer_by_frame[frame] = stream_offset + len(stream)
        stream.extend((frequency_mask, volume_mask, wave_mask))
        periods, volumes, waves, psg_period, psg_volume, noise_period, noise_volume = state
        for index in range(4):
            if wave_mask & (1 << index):
                stream.append(wave_ids[waves[index]])
        for index in range(5):
            if frequency_mask & (1 << index):
                stream.extend(struct.pack("<H", periods[index] & 0x0FFF))
        if frequency_mask & 0x20:
            stream.extend(struct.pack("<H", psg_period))
        if frequency_mask & 0x40:
            stream.append(noise_period & 31)
        for index in range(5):
            if volume_mask & (1 << index):
                stream.append(volumes[index] & 15)
        if volume_mask & 0x20:
            stream.append(psg_volume & 15)
        if volume_mask & 0x40:
            stream.append(noise_volume & 15)
        previous_frame = frame
    stream.append(0xFF)

    loop_frame = min(forced) if forced else 0
    loop_pointer = event_pointer_by_frame.get(loop_frame, stream_offset + 1)
    block = bytearray(b"HSC0")
    block.extend((flags & 0xFF, len(wave_dictionary)))
    block.extend(struct.pack("<HHH", total_frames & 0xFFFF, loop_pointer, stream_offset))
    block.extend((next_page & 0xFF, ord("C"), 0, 0))
    for wave in wave_dictionary:
        block.extend(bytes(wave))
    block.extend(stream)
    if len(block) > MAX_BLOCK:
        if not _merge_near_duplicates:
            return encode_hsc0(
                states, initial_state, total_frames, flags, next_page,
                force_full_frames, force_event_frame0,
                initial_hardware_waves, True,
            )
        raise ValueError(f"HSC0 block is too large: {len(block)} > {MAX_BLOCK}")
    validate_hsc0(block)
    return bytes(block), {
        "local_frames": len(states),
        "total_frames": total_frames,
        "events": len(events),
        "waveforms": len(wave_dictionary),
        "near_duplicate_waveforms_merged": wave_alias_merges,
        "stream_bytes": len(stream),
        "block_bytes": len(block),
        "loop_frame": loop_frame if forced else None,
    }, tuple(hardware_waves)


def validate_hsc0(data: bytes) -> int:
    if data[:4] != b"HSC0":
        raise ValueError("not HSC0")
    wave_count = data[5]
    stream_offset = u16(data, 10)
    if stream_offset != 16 + 32 * wave_count or stream_offset >= len(data):
        raise ValueError("invalid HSC0 stream offset")
    cursor = stream_offset
    events = 0
    while True:
        if cursor >= len(data):
            raise ValueError("unterminated HSC0 stream")
        delay = data[cursor]
        cursor += 1
        if delay == 0xFF:
            break
        if cursor + 3 > len(data):
            raise ValueError("truncated HSC0 event")
        fm, vm, wm = data[cursor:cursor + 3]
        cursor += 3
        if wm & 0xF0:
            raise ValueError("invalid HSC0 wave mask")
        cursor += sum((wm >> index) & 1 for index in range(4))
        cursor += 2 * sum((fm >> index) & 1 for index in range(6))
        cursor += (fm >> 6) & 1
        cursor += sum((vm >> index) & 1 for index in range(7))
        if cursor > len(data):
            raise ValueError("HSC0 event exceeds block")
        events += 1
    if cursor != len(data):
        raise ValueError("trailing HSC0 bytes")
    return events


# ---------------------------------------------------------------------------
# Normal SCC engine builder
# ---------------------------------------------------------------------------
ORIGIN = 0x4000
TRACK = 0x4800
WAVE = 0x4810
PTR = 0x4700
WAIT = 0x4702
ENDED = 0x4703
FM = 0x4704
VM = 0x4705
WM = 0x4706
LOOPPTR = 0x4707
PAGE_GATEWAY = 0xD8A0
SCC_ENABLE = 0x9000
SCC_WAVE = 0x9800
SCC_FREQ = 0x9880
SCC_VOL = 0x988A
SCC_KEY = 0x988F


class Assembler:
    def __init__(self) -> None:
        self.data = bytearray()
        self.labels: Dict[str, int] = {}
        self.fixups = []

    @property
    def pc(self) -> int:
        return ORIGIN + len(self.data)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate label {name}")
        self.labels[name] = self.pc

    def emit(self, *values: int) -> None:
        self.data.extend(value & 0xFF for value in values)

    def word(self, value: int) -> None:
        self.emit(value, value >> 8)

    def absolute_fixup(self, opcode: int, label: str) -> None:
        self.emit(opcode)
        self.fixups.append(("absolute", len(self.data), label))
        self.emit(0, 0)

    def call(self, target: int | str) -> None:
        if isinstance(target, int):
            self.emit(0xCD)
            self.word(target)
        else:
            self.absolute_fixup(0xCD, target)

    def jump(self, label: str, condition: Optional[str] = None) -> None:
        opcode = {None: 0xC3, "z": 0xCA, "nz": 0xC2, "c": 0xDA, "nc": 0xD2}[condition]
        self.absolute_fixup(opcode, label)

    def relative_jump(self, label: str, condition: Optional[str] = None) -> None:
        opcode = {None: 0x18, "z": 0x28, "nz": 0x20, "c": 0x38, "nc": 0x30}[condition]
        self.emit(opcode)
        self.fixups.append(("relative", len(self.data), label))
        self.emit(0)

    def finish(self) -> bytes:
        for kind, position, label in self.fixups:
            target = self.labels[label]
            if kind == "absolute":
                self.data[position:position + 2] = struct.pack("<H", target)
            else:
                displacement = target - (ORIGIN + position + 1)
                if not -128 <= displacement <= 127:
                    raise ValueError(f"JR {label} out of range: {displacement}")
                self.data[position] = displacement & 0xFF
        return bytes(self.data)


def load_a_absolute(asm: Assembler, address: int) -> None:
    asm.emit(0x3A); asm.word(address)


def store_a_absolute(asm: Assembler, address: int) -> None:
    asm.emit(0x32); asm.word(address)


def load_hl_absolute(asm: Assembler, address: int) -> None:
    asm.emit(0x2A); asm.word(address)


def store_hl_absolute(asm: Assembler, address: int) -> None:
    asm.emit(0x22); asm.word(address)


def load_hl(asm: Assembler, value: int) -> None:
    asm.emit(0x21); asm.word(value)


def load_de(asm: Assembler, value: int) -> None:
    asm.emit(0x11); asm.word(value)


def load_bc(asm: Assembler, value: int) -> None:
    asm.emit(0x01); asm.word(value)


def output_a(asm: Assembler, port: int) -> None:
    asm.emit(0xD3, port)


def psg_constant(asm: Assembler, register: int, value: int) -> None:
    asm.emit(0x3E, register); output_a(asm, 0xA0)
    asm.emit(0x3E, value); output_a(asm, 0xA1)


def build_normal_scc_engine() -> Tuple[bytes, Dict[str, int]]:
    asm = Assembler()
    asm.label("init")
    asm.call("silence")
    asm.emit(0xAF); store_a_absolute(asm, ENDED)
    asm.emit(0x3E, 0x3F); store_a_absolute(asm, SCC_ENABLE)
    psg_constant(asm, 7, 0x2E)
    asm.emit(0x3E, 0x1F); store_a_absolute(asm, SCC_KEY)
    asm.call("load_chunk_start")
    asm.emit(0xC9)

    asm.label("play")
    load_a_absolute(asm, ENDED); asm.emit(0xB7, 0xC0)
    load_a_absolute(asm, WAIT); asm.emit(0xB7)
    asm.relative_jump("apply_event", "z")
    asm.emit(0x3D); store_a_absolute(asm, WAIT); asm.emit(0xC9)

    asm.label("load_chunk_start")
    load_hl_absolute(asm, TRACK + 8); load_de(asm, TRACK); asm.emit(0x19)
    store_hl_absolute(asm, LOOPPTR)
    load_hl_absolute(asm, TRACK + 10); load_de(asm, TRACK); asm.emit(0x19)
    asm.emit(0x7E, 0x23); store_a_absolute(asm, WAIT); store_hl_absolute(asm, PTR)
    asm.emit(0xB7, 0xC0)
    asm.jump("apply_event")

    asm.label("apply_event")
    load_hl_absolute(asm, PTR)
    asm.emit(0x7E, 0x23); store_a_absolute(asm, FM)
    asm.emit(0x7E, 0x23); store_a_absolute(asm, VM)
    asm.emit(0x7E, 0x23); store_a_absolute(asm, WM)

    for index in range(4):
        load_a_absolute(asm, WM); asm.emit(0xE6, 1 << index)
        asm.relative_jump(f"wave_{index}_done", "z")
        asm.emit(0x7E, 0x23, 0xE5, 0x6F, 0x26, 0x00)
        for _ in range(5): asm.emit(0x29)
        load_bc(asm, WAVE); asm.emit(0x09)
        load_de(asm, SCC_WAVE + 32 * index); load_bc(asm, 32)
        asm.emit(0xED, 0xB0, 0xE1)
        asm.label(f"wave_{index}_done")

    for index in range(5):
        load_a_absolute(asm, FM); asm.emit(0xE6, 1 << index)
        asm.relative_jump(f"frequency_{index}_done", "z")
        asm.emit(0x7E, 0x23); store_a_absolute(asm, SCC_FREQ + 2 * index)
        asm.emit(0x7E, 0x23, 0xE6, 0x0F); store_a_absolute(asm, SCC_FREQ + 2 * index + 1)
        asm.label(f"frequency_{index}_done")

    load_a_absolute(asm, FM); asm.emit(0xE6, 0x20)
    asm.relative_jump("psg_frequency_done", "z")
    asm.emit(0x5E, 0x23, 0x56, 0x23)
    asm.emit(0x3E, 0); output_a(asm, 0xA0); asm.emit(0x7B); output_a(asm, 0xA1)
    asm.emit(0x3E, 1); output_a(asm, 0xA0); asm.emit(0x7A); output_a(asm, 0xA1)
    asm.label("psg_frequency_done")

    load_a_absolute(asm, FM); asm.emit(0xE6, 0x40)
    asm.relative_jump("noise_frequency_done", "z")
    asm.emit(0x5E, 0x23, 0x3E, 6); output_a(asm, 0xA0); asm.emit(0x7B); output_a(asm, 0xA1)
    asm.label("noise_frequency_done")

    for index in range(5):
        load_a_absolute(asm, VM); asm.emit(0xE6, 1 << index)
        asm.relative_jump(f"volume_{index}_done", "z")
        asm.emit(0x7E, 0x23, 0xE6, 0x0F); store_a_absolute(asm, SCC_VOL + index)
        asm.label(f"volume_{index}_done")

    load_a_absolute(asm, VM); asm.emit(0xE6, 0x20)
    asm.relative_jump("psg_volume_done", "z")
    asm.emit(0x5E, 0x23, 0x3E, 8); output_a(asm, 0xA0); asm.emit(0x7B); output_a(asm, 0xA1)
    asm.label("psg_volume_done")

    load_a_absolute(asm, VM); asm.emit(0xE6, 0x40)
    asm.relative_jump("noise_volume_done", "z")
    asm.emit(0x5E, 0x23, 0x3E, 9); output_a(asm, 0xA0); asm.emit(0x7B); output_a(asm, 0xA1)
    asm.label("noise_volume_done")

    asm.emit(0x7E, 0x23, 0xFE, 0xFF)
    asm.relative_jump("stream_end", "z")
    store_a_absolute(asm, WAIT); store_hl_absolute(asm, PTR); asm.emit(0xC9)

    asm.label("stream_end")
    load_a_absolute(asm, TRACK + 4); asm.emit(0xE6, 0x08)
    asm.relative_jump("local_end", "z")
    load_a_absolute(asm, TRACK + 4); asm.emit(0xE6, 0x10)
    asm.relative_jump("ordinary_continuation", "z")

    load_a_absolute(asm, TRACK + 12); asm.call(PAGE_GATEWAY)
    load_hl_absolute(asm, TRACK + 8); load_de(asm, TRACK); asm.emit(0x19)
    store_hl_absolute(asm, PTR); asm.emit(0xAF); store_a_absolute(asm, WAIT); asm.emit(0xC9)

    asm.label("ordinary_continuation")
    load_a_absolute(asm, TRACK + 12); asm.call(PAGE_GATEWAY)
    load_hl_absolute(asm, TRACK + 10); load_de(asm, TRACK); asm.emit(0x19)
    asm.emit(0x7E, 0x23); store_a_absolute(asm, WAIT); store_hl_absolute(asm, PTR); asm.emit(0xC9)

    asm.label("local_end")
    load_a_absolute(asm, TRACK + 4); asm.emit(0xE6, 1)
    asm.relative_jump("final_end", "z")
    load_hl_absolute(asm, LOOPPTR); store_hl_absolute(asm, PTR)
    asm.emit(0xAF); store_a_absolute(asm, WAIT); asm.emit(0xC9)

    asm.label("final_end")
    asm.call("silence"); asm.emit(0x3E, 1); store_a_absolute(asm, ENDED); asm.emit(0xC9)

    asm.label("silence")
    asm.emit(0xAF); load_hl(asm, SCC_VOL); asm.emit(0x06, 6)
    asm.label("silence_loop")
    asm.emit(0x77, 0x23, 0x10)
    asm.fixups.append(("relative", len(asm.data), "silence_loop")); asm.emit(0)
    for register in (8, 9, 10): psg_constant(asm, register, 0)
    asm.emit(0xC9)

    code = asm.finish()
    if len(code) > 0x700:
        raise ValueError(f"normal-SCC engine too large: {len(code)}")
    return code, asm.labels


# ---------------------------------------------------------------------------
# Conversion orchestration and KSP writer
# ---------------------------------------------------------------------------
def page_chain(start_page: int, blocks: Sequence[HSC1Block]) -> List[int]:
    result = []
    seen = set()
    page = start_page
    while page not in seen:
        if page >= len(blocks):
            raise ValueError("HSC1 next-page index out of range")
        seen.add(page)
        result.append(page)
        block = blocks[page]
        if not (block.flags & 0x08) or block.next_page == 0xFF:
            break
        if block.flags & 0x10:
            break
        page = block.next_page
    return result


def expand_source_states(block: HSC1Block, initial: SCCPlusState) -> List[SCCPlusState]:
    states: List[SCCPlusState] = []
    active = initial
    event_index = 0
    for frame in range(block.local_frames):
        while event_index < len(block.events) and block.events[event_index].frame == frame:
            active = block.events[event_index].state
            event_index += 1
        states.append(active)
    if event_index != len(block.events):
        raise ValueError("HSC1 event outside local frame range")
    return states


def package_string(source: KSPPackage, offset: int) -> str:
    if offset == NULL32 or offset >= len(source.strings):
        return ""
    end = source.strings.find(b"\0", offset)
    if end < 0:
        return ""
    try:
        return source.strings[offset:end].decode("utf-8")
    except UnicodeDecodeError:
        return ""


def package_title(source: KSPPackage) -> str:
    if source.meta_index != NULL16 and source.meta_index < len(source.resources):
        resource = source.resources[source.meta_index]
        if resource.kind == b"META":
            try:
                for line in resource.payload.decode("utf-8").splitlines():
                    if line.startswith("title=") and line[6:].strip():
                        return line[6:].strip()
            except UnicodeDecodeError:
                pass
    engine_name = package_string(source, source.engines[0].name_offset)
    for suffix in (" SCC+", " SCC", " conversion", " event replayer"):
        position = engine_name.lower().find(suffix.lower())
        if position > 0:
            engine_name = engine_name[:position]
            break
    if engine_name.strip():
        return engine_name.strip()
    if source.tracks:
        title = source.tracks[0].title
        marker = title.lower().find(" track ")
        return title[:marker].strip() if marker > 0 else title.strip()
    return "KSP package"


def update_meta(source: KSPPackage, input_name: str, stats: dict) -> bytes:
    lines = []
    if source.meta_index != NULL16 and source.meta_index < len(source.resources):
        meta = source.resources[source.meta_index]
        if meta.kind == b"META":
            try:
                text = meta.payload.decode("utf-8")
                lines = [line for line in text.splitlines()
                         if not line.startswith(("system=", "conversion=", "hardware=", "source_variant_removed="))]
            except UnicodeDecodeError:
                lines = []
    if not any(line.startswith("title=") for line in lines):
        lines.insert(0, f"title={package_title(source)}")
    lines.extend([
        "system=PC Engine to MSX normal SCC conversion",
        "hardware=MSX PSG + normal SCC",
        "conversion=standalone KSP 1.0 SCC+ to normal-SCC dynamic waveform pairing",
        "source_variant_removed=SCC+ independent channel-5 waveform",
        f"source_file={input_name}",
        f"pairing_mean_distortion={stats['mean_pair_distortion']:.8f}",
        f"pairing_reduction_vs_fixed_4_5={stats['distortion_reduction_vs_fixed']:.8f}",
    ])
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def make_sparse_overlay(block: bytes) -> bytes:
    return struct.pack("<HH", TRACK_OFFSET, len(block)) + block


def build_ksp(source: KSPPackage, input_name: str, output_path: Path, converted_blocks: Sequence[bytes],
              engine_code: bytes, labels: Dict[str, int], allocator_stats: dict,
              compress: bool) -> Tuple[bytes, dict]:
    if len(source.engines) != 1:
        raise ValueError("converter currently supports one engine")
    if len(converted_blocks) != len(source.pages):
        raise ValueError("converted page count mismatch")

    template = bytearray(PAGE_SIZE)
    template[:len(engine_code)] = engine_code
    template = bytes(template)
    final_pages = []
    overlays = []
    for block in converted_blocks:
        overlay = make_sparse_overlay(block)
        page = apply_sparse_overlay(template, overlay)
        final_pages.append(page)
        overlays.append(overlay)

    strings = bytearray()
    string_offsets: Dict[str, int] = {}
    def add_string(value: str) -> int:
        if value in string_offsets:
            return string_offsets[value]
        offset = len(strings)
        strings.extend(value.encode("utf-8") + b"\0")
        string_offsets[value] = offset
        return offset

    engine_name_offset = add_string(f"{package_title(source)} normal SCC dynamic-pair conversion")
    track_title_offsets = [add_string(track.title) for track in source.tracks]

    meta = update_meta(source, input_name, allocator_stats)
    template_compression, template_payload = compress_object(template, compress)
    page_objects = [compress_object(overlay, compress) for overlay in overlays]
    meta_compression, meta_payload = compress_object(meta, compress)

    engine_count = 1
    page_count = len(final_pages)
    track_count = len(source.tracks)
    resource_count = 1
    engine_offset = 80
    page_offset = engine_offset + 64 * engine_count
    track_offset = page_offset + 24 * page_count
    resource_offset = track_offset + 32 * track_count
    string_offset = resource_offset + 32 * resource_count
    payload_offset = string_offset + len(strings)

    template_offset = payload_offset
    cursor = template_offset + len(template_payload)
    page_offsets = []
    for _, payload in page_objects:
        page_offsets.append(cursor)
        cursor += len(payload)
    meta_offset = cursor
    cursor += len(meta_payload)
    file_size = cursor

    engine_table = bytearray(64)
    struct.pack_into("<II", engine_table, 0, KSP_ENGINE_DYNAMIC_PAGES,
                     KSP_HARDWARE_PSG | KSP_HARDWARE_SCC)
    struct.pack_into("<HHHHHHHHHHHH", engine_table, 8,
                     1, source.engines[0].tick_rate, PAGE_LOAD, PAGE_SIZE,
                     labels["init"], labels["play"], 0, PAGE_GATEWAY,
                     TRACK_ADDRESS, 0, page_count, NULL16)
    engine_table[32] = template_compression
    engine_table[33:36] = b"\0\0\0"
    struct.pack_into("<IIIII", engine_table, 36, template_offset, len(template_payload),
                     len(template), crc32(template), engine_name_offset)

    page_table = bytearray(24 * page_count)
    for index, ((compression, payload), offset, page) in enumerate(zip(page_objects, page_offsets, final_pages)):
        struct.pack_into("<HBBHHIIII", page_table, index * 24,
                         0, KSP_PAGE_SPARSE_OVERLAY, compression, 0, 0,
                         offset, len(payload), len(overlays[index]), crc32(page))

    track_table = bytearray(32 * track_count)
    for index, (track, title_offset_value) in enumerate(zip(source.tracks, track_title_offsets)):
        struct.pack_into("<HHHHHHIIIII", track_table, index * 32,
                         track.page, track.song, track.flags, NULL16, NULL16, 0,
                         title_offset_value, track.duration, track.loop_start,
                         track.loop_end, track.fade)

    resource_table = bytearray(32)
    resource_table[:4] = b"META"
    struct.pack_into("<HBBIIIIII", resource_table, 4,
                     0, meta_compression, 0, meta_offset, len(meta_payload), len(meta),
                     crc32(meta), 0, 0)

    header = bytearray(80)
    header[:4] = b"KSP1"
    struct.pack_into("<HHII", header, 4, 80, 0, 0, file_size)
    struct.pack_into("<IHH", header, 16, engine_offset, engine_count, 64)
    struct.pack_into("<IHH", header, 24, page_offset, page_count, 24)
    struct.pack_into("<IHH", header, 32, track_offset, track_count, 32)
    struct.pack_into("<IHH", header, 40, resource_offset, resource_count, 32)
    struct.pack_into("<II", header, 48, string_offset, len(strings))
    struct.pack_into("<HHHH", header, 56, source.default_track, 0, NULL16, 0)
    index_bytes = bytes(engine_table + page_table + track_table + resource_table + strings)
    struct.pack_into("<I", header, 68, crc32(index_bytes))
    header_copy = bytearray(header)
    struct.pack_into("<I", header_copy, 64, 0)
    struct.pack_into("<I", header, 64, crc32(header_copy))

    output = (bytes(header) + bytes(engine_table) + bytes(page_table) + bytes(track_table) +
              bytes(resource_table) + bytes(strings) + template_payload +
              b"".join(payload for _, payload in page_objects) + meta_payload)
    if len(output) != file_size:
        raise AssertionError("KSP output length mismatch")
    output_path.write_bytes(output)
    validation = validate_output(output, final_pages)
    return output, {
        "file": output_path.name,
        "bytes": len(output),
        "sha256": sha256(output),
        "template_raw": len(template),
        "template_packed": len(template_payload),
        "page_payload_raw_total": sum(map(len, overlays)),
        "page_payload_packed_total": sum(len(payload) for _, payload in page_objects),
        "compression": "ZX0 where smaller" if compress else "NONE",
        "validation": validation,
    }


def validate_output(output: bytes, expected_pages: Sequence[bytes]) -> dict:
    temporary = Path("/tmp/_validate_normal_scc.ksp")
    temporary.write_bytes(output)
    package = parse_ksp(temporary)
    temporary.unlink(missing_ok=True)
    if package.pages != list(expected_pages):
        raise ValueError("output page reconstruction mismatch")
    hsc0_events = []
    for page in package.pages:
        header = page[TRACK_OFFSET:]
        stream_offset = u16(header, 10)
        cursor = stream_offset
        while True:
            delay = header[cursor]; cursor += 1
            if delay == 0xFF: break
            fm, vm, wm = header[cursor:cursor + 3]; cursor += 3
            cursor += sum((wm >> i) & 1 for i in range(4))
            cursor += 2 * sum((fm >> i) & 1 for i in range(6))
            cursor += (fm >> 6) & 1
            cursor += sum((vm >> i) & 1 for i in range(7))
        block = bytes(header[:cursor])
        hsc0_events.append(validate_hsc0(block))
    return {
        "header_crc": "ok",
        "index_crc": "ok",
        "page_crcs": len(package.pages),
        "hsc0_pages": len(hsc0_events),
        "hsc0_events": sum(hsc0_events),
        "hardware_flags": package.engines[0].hardware,
        "init": f"0x{package.engines[0].init_address:04X}",
        "play": f"0x{package.engines[0].play_address:04X}",
    }


def convert(input_path: Path, output_path: Path, report_path: Path,
            compress: bool = True, shared_wave_strategy: str = "louder") -> dict:
    source = parse_ksp(input_path)
    if len(source.engines) != 1:
        raise ValueError("expected one HSC1 engine")
    engine = source.engines[0]
    if not (engine.hardware & KSP_HARDWARE_SCCPLUS):
        raise ValueError("source package does not declare SCC+")
    if engine.tick_rate != 60:
        raise ValueError("HSC converter currently requires 60 Hz")

    hsc_blocks: List[HSC1Block] = []
    for index, page in enumerate(source.pages):
        try:
            _, parsed = extract_hsc1_page(page)
        except Exception as exc:
            raise ValueError(f"page {index}: {exc}") from exc
        hsc_blocks.append(parsed)

    converted: List[Optional[bytes]] = [None] * len(hsc_blocks)
    page_reports: List[Optional[dict]] = [None] * len(hsc_blocks)
    global_stats = {
        "frames": 0, "mapping_changes": 0, "pair_changes": 0,
        "hysteresis_retentions": 0, "exact_pair_frames": 0,
        "distortion_sum": 0.0, "fixed_distortion_sum": 0.0,
        "pair_usage_frames": defaultdict(int),
    }
    chain_reports = []

    for track_index, track in enumerate(source.tracks):
        if converted[track.page] is not None:
            continue
        chain = page_chain(track.page, hsc_blocks)
        allocator = DynamicSCCAllocator(shared_wave_strategy)
        source_state = zero_sccplus_state()
        normal_state = zero_normal_state()
        hardware_waves: Tuple[Optional[Waveform], ...] = (None, None, None, None)
        chain_page_reports = []
        for chain_position, page_index in enumerate(chain):
            block = hsc_blocks[page_index]
            source_states = expand_source_states(block, source_state)
            normal_states = []
            for source_frame in source_states:
                transformed, _ = allocator.allocate(source_frame)
                normal_states.append(transformed)
            force_full = []
            # This page is a loop target when it contains a valid loop pointer and
            # either loops locally or another chunk wraps back to it.
            referenced_by_wrap = any(
                other.flags & 0x10 and other.next_page == page_index
                for other in hsc_blocks
            )
            if block.loop_frame is not None and ((block.flags & 1) or referenced_by_wrap):
                force_full.append(block.loop_frame)
            try:
                output_block, block_report, hardware_waves = encode_hsc0(
                    normal_states, normal_state, block.total_frames, block.flags,
                    block.next_page, force_full, force_event_frame0=(chain_position == 0),
                    initial_hardware_waves=hardware_waves,
                )
            except ValueError as exc:
                raise ValueError(f"page {page_index} in chain {chain}: {exc}") from exc
            converted[page_index] = output_block
            block_report.update({
                "page": page_index,
                "source_events": len(block.events),
                "source_waveforms": block.wave_count,
                "flags": f"0x{block.flags:02X}",
                "next_page": block.next_page,
            })
            page_reports[page_index] = block_report
            chain_page_reports.append(block_report)
            source_state = source_states[-1]
            normal_state = normal_states[-1]
        stats = allocator.statistics()
        chain_reports.append({"track": track_index, "start_page": track.page,
                              "pages": chain, "allocator": stats})
        global_stats["frames"] += stats["frames"]
        global_stats["mapping_changes"] += stats["mapping_changes"]
        global_stats["pair_changes"] += stats["pair_changes"]
        global_stats["hysteresis_retentions"] += stats["hysteresis_retentions"]
        global_stats["exact_pair_frames"] += stats["exact_pair_frames"]
        global_stats["distortion_sum"] += stats["mean_pair_distortion"] * stats["frames"]
        global_stats["fixed_distortion_sum"] += stats["mean_fixed_source_4_5_distortion"] * stats["frames"]
        for pair, count in stats["pair_usage_frames"].items():
            global_stats["pair_usage_frames"][pair] += count

    missing = [index for index, value in enumerate(converted) if value is None]
    if missing:
        raise ValueError(f"unreferenced HSC1 pages were not converted: {missing}")

    frame_count = max(1, global_stats["frames"])
    fixed_sum = global_stats["fixed_distortion_sum"]
    allocator_summary = {
        "frames": global_stats["frames"],
        "mapping_changes": global_stats["mapping_changes"],
        "pair_changes": global_stats["pair_changes"],
        "hysteresis_retentions": global_stats["hysteresis_retentions"],
        "exact_pair_frames": global_stats["exact_pair_frames"],
        "exact_pair_fraction": global_stats["exact_pair_frames"] / frame_count,
        "mean_pair_distortion": global_stats["distortion_sum"] / frame_count,
        "mean_fixed_source_4_5_distortion": fixed_sum / frame_count,
        "distortion_reduction_vs_fixed": 0.0 if fixed_sum <= 1e-12 else 1.0 - global_stats["distortion_sum"] / fixed_sum,
        "pair_usage_frames": dict(sorted(global_stats["pair_usage_frames"].items())),
    }

    engine_code, labels = build_normal_scc_engine()
    output, output_report = build_ksp(source, input_path.name, output_path, [value for value in converted if value is not None],
                                      engine_code, labels, allocator_summary, compress)
    report = {
        "input": {
            "file": input_path.name,
            "bytes": len(source.raw),
            "sha256": sha256(source.raw),
            "hardware_flags": source.engines[0].hardware,
            "pages": len(source.pages),
            "tracks": len(source.tracks),
        },
        "conversion": {
            "method": "dynamic phase-aligned, volume-weighted waveform pairing",
            "shared_channels": [4, 5],
            "shared_waveform": ("phase-aligned volume-weighted blend" if shared_wave_strategy == "blend" else "louder waveform of closest phase-aligned pair"),
            "mapping_hysteresis": True,
            "waveform_ram_tracking": "physical SCC waveform RAM state tracked independently from muted logical voices",
            "allocator": allocator_summary,
            "normal_scc_engine_bytes": len(engine_code),
            "engine_labels": {name: f"0x{address:04X}" for name, address in labels.items()},
        },
        "pages": page_reports,
        "chains": chain_reports,
        "output": output_report,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--no-compress", action="store_true",
                        help="store template, overlays and META uncompressed")
    parser.add_argument("--shared-wave", choices=("louder", "blend"), default="louder",
                        help="waveform used by normal-SCC channels 4/5 (default: louder)")
    args = parser.parse_args()
    report_path = args.report or args.output.with_suffix(".report.json")
    report = convert(args.input, args.output, report_path, not args.no_compress, args.shared_wave)
    print(f"Wrote {args.output} ({report['output']['bytes']} bytes)")
    print(f"Wrote {report_path}")
    print(f"SHA-256 {report['output']['sha256']}")
    print(f"Mean paired distortion {report['conversion']['allocator']['mean_pair_distortion']:.8f}")
    print(f"Reduction vs fixed source channels 4+5 {report['conversion']['allocator']['distortion_reduction_vs_fixed']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
