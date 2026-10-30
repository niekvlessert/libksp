#!/usr/bin/env python3
"""Offline S3M -> MoonSound/YMF278B PCM event compiler.

This is intentionally a compiler, not a realtime S3M interpreter.  It resolves
all tracker rows/ticks on the host and emits absolute YMF278B PCM register
writes.  The MSX runtime only clocks the precompiled tick stream.

The S3M parser is intentionally generic: it accepts mono/stereo and 8/16-bit PCM,
merges duplicate packed channel tokens field-by-field, tolerates broken packed-length
fields like ST3/OpenMPT, and leaves tracker-specific effect quirks to compact_stream.py.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

PERIOD_CLOCK = 3546895.0
HEADER_BASE = 0x200000
HEADER_COUNT = 128
HEADER_BYTES = HEADER_COUNT * 12
SAMPLE_BASE = HEADER_BASE + HEADER_BYTES  # 0x200600
MAX_WAVES = 128
MAX_SAMPLE_RAM = 1024 * 1024  # standard 1 MiB MoonSound RAM window used here

# Exact 64-step ST3 / ProTracker vibrato sine table used by OpenMPT.
MOD_SINUS_TABLE = (
    0,12,25,37,49,60,71,81,90,98,106,112,117,122,125,126,
    127,126,125,122,117,112,106,98,90,81,71,60,49,37,25,12,
    0,-12,-25,-37,-49,-60,-71,-81,-90,-98,-106,-112,-117,-122,-125,-126,
    -127,-126,-125,-122,-117,-112,-106,-98,-90,-81,-71,-60,-49,-37,-25,-12,
)


def u16(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o+2], "little")


def u32(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o+4], "little")


@dataclass
class Event:
    ch: int
    note: Optional[int] = None
    ins: Optional[int] = None
    vol: Optional[int] = None
    cmd: Optional[int] = None
    param: Optional[int] = None


@dataclass
class Sample:
    number: int
    name: str
    length: int
    loop_begin: int
    loop_end: int
    volume: int
    flags: int
    c2spd: int
    data_offset: int
    data: bytes

    @property
    def looped(self) -> bool:
        return bool(self.flags & 1) and self.loop_end > self.loop_begin and self.loop_end <= self.length


@dataclass
class Module:
    path: Path
    raw: bytes
    title: str
    orders: List[int]
    patterns: List[List[List[Event]]]
    samples: Dict[int, Sample]
    channel_settings: List[int]
    speed: int
    tempo: int
    global_volume: int
    flags: int
    ffi: int

    @property
    def active_channels(self) -> List[int]:
        return [i for i, v in enumerate(self.channel_settings) if v < 16]


def _s16_to_s8(v: int) -> int:
    v = max(-32768, min(32767, int(v)))
    return (v >> 8) & 0xFF


def _decode_s3m_pcm(raw: bytes, length: int, flags: int, ffi: int) -> bytes:
    """Decode S3M PCM to the converter's signed mono 8-bit internal format.

    S3M stereo PCM is stored split (all left samples followed by all right
    samples), not interleaved. OPL4 custom waves are mono, so stereo samples
    are downmixed with a signed arithmetic average while preserving the S3M
    frame count, loop points and C5 speed.
    """
    stereo = bool(flags & 0x02)
    bit16 = bool(flags & 0x04)
    chans = 2 if stereo else 1
    bps = 2 if bit16 else 1
    need = int(length) * chans * bps
    if len(raw) < need:
        raise ValueError('S3M sample data extends past file')
    raw = raw[:need]

    def decode_plane(buf: bytes) -> list[int]:
        vals=[]
        if bit16:
            for i in range(0, len(buf), 2):
                u=int.from_bytes(buf[i:i+2], 'little', signed=False)
                if ffi == 2:  # unsigned 16-bit -> signed
                    v=u-32768
                elif ffi == 1:
                    v=u if u < 0x8000 else u-0x10000
                else:
                    raise ValueError(f'unsupported S3M sample format info {ffi}')
                vals.append(v)
        else:
            for u in buf:
                if ffi == 2:
                    vals.append(u-128)
                elif ffi == 1:
                    vals.append(u if u < 128 else u-256)
                else:
                    raise ValueError(f'unsupported S3M sample format info {ffi}')
        return vals

    plane_bytes = int(length) * bps
    left = decode_plane(raw[:plane_bytes])
    if stereo:
        right = decode_plane(raw[plane_bytes:plane_bytes*2])
        if bit16:
            return bytes(_s16_to_s8((l+r)//2) for l,r in zip(left,right))
        return bytes((((l+r)//2) & 0xFF) for l,r in zip(left,right))
    if bit16:
        return bytes(_s16_to_s8(v) for v in left)
    return bytes(v & 0xFF for v in left)


def parse_s3m(path: Path) -> Module:
    b = path.read_bytes()
    if len(b) < 0x60 or b[0x2c:0x30] != b"SCRM":
        raise ValueError(f"{path}: not an S3M file")
    ordn, insn, patn = u16(b, 0x20), u16(b, 0x22), u16(b, 0x24)
    title = b[:28].split(b"\0")[0].decode("cp437", "replace").rstrip()
    orders = list(b[0x60:0x60+ordn])
    pos = 0x60 + ordn
    ins_ptrs = [u16(b, pos + 2*i) * 16 for i in range(insn)]
    pos += 2 * insn
    pat_ptrs = [u16(b, pos + 2*i) * 16 for i in range(patn)]

    patterns: List[List[List[Event]]] = []
    for off in pat_ptrs:
        rows: List[List[Event]] = [[] for _ in range(64)]
        if not off or off + 2 > len(b):
            patterns.append(rows)
            continue
        # OpenMPT deliberately ignores the packed-length field. A number of
        # real S3Ms contain a broken value but valid row terminators.
        p = off + 2
        row = 0
        row_events: Dict[int, Event] = {}
        while p < len(b) and row < 64:
            token = b[p]; p += 1
            if token == 0:
                rows[row] = [row_events[ch] for ch in sorted(row_events)]
                row_events = {}
                row += 1
                continue
            ch = token & 31
            e = row_events.get(ch)
            if e is None:
                e = Event(ch=ch)
                row_events[ch]=e
            if token & 0x20:
                if p + 2 > len(b): break
                e.note, e.ins = b[p], b[p+1]; p += 2
            if token & 0x40:
                if p >= len(b): break
                v=b[p]; p += 1
                if 128 <= v <= 192:
                    # S3M volume-column panning: 128..192 -> 0..64.
                    e.volume_pan=v-128
                else:
                    e.vol=min(64,v)
            if token & 0x80:
                if p + 2 > len(b): break
                e.cmd, e.param = b[p], b[p+1]; p += 2
        if row < 64 and row_events:
            rows[row] = [row_events[ch] for ch in sorted(row_events)]
        patterns.append(rows)

    samples: Dict[int, Sample] = {}
    ffi = u16(b, 0x2a)
    for number, off in enumerate(ins_ptrs, 1):
        if not off or off + 0x50 > len(b) or b[off] != 1:
            continue
        memseg = (b[off+0x0d] << 16) | (b[off+0x0f] << 8) | b[off+0x0e]
        data_off = memseg * 16
        length = u32(b, off+0x10)
        flags = b[off+0x1f]
        pack = b[off+0x1e]
        if pack not in (0,):
            raise ValueError(f"sample {number}: packed/ADPCM S3M sample type {pack} is not supported yet")
        chans=2 if (flags & 0x02) else 1
        bps=2 if (flags & 0x04) else 1
        raw_len=length*chans*bps
        if data_off + raw_len > len(b):
            raise ValueError(f"sample {number}: sample data extends past file")
        data = _decode_s3m_pcm(bytes(b[data_off:data_off+raw_len]), length, flags, ffi)
        name = b[off+0x30:off+0x30+28].split(b"\0")[0].decode("cp437", "replace").rstrip()
        c5=u32(b,off+0x20)
        if c5==0: c5=8363
        elif c5<1024: c5=1024
        c5=min(65535,c5)
        samples[number] = Sample(
            number=number, name=name, length=length,
            loop_begin=min(length,u32(b, off+0x14)), loop_end=min(length,u32(b, off+0x18)),
            volume=min(64, b[off+0x1c]), flags=(flags & 1),
            c2spd=c5, data_offset=data_off, data=data,
        )
        samples[number].s3m_source_stereo=bool(flags & 0x02)
        samples[number].s3m_source_16bit=bool(flags & 0x04)

    return Module(
        path=path, raw=b, title=title, orders=orders, patterns=patterns,
        samples=samples, channel_settings=list(b[0x40:0x60]),
        speed=b[0x31], tempo=b[0x32],
        global_volume=min(64, b[0x30]), flags=u16(b, 0x26), ffi=ffi,
    )


@dataclass(frozen=True)
class WaveKey:
    instrument: int
    offset: int


@dataclass
class WaveVariant:
    key: WaveKey
    wave_number: int
    sample_name: str
    source_length: int
    start_addr: int = 0
    loop_pos: int = 0
    play_length: int = 0
    payload: bytes = b""
    shared_source: bool = True
    silence: bool = False


class WaveBank:
    def __init__(self, module: Module):
        self.module = module
        self.variants: Dict[WaveKey, WaveVariant] = {}
        self.order: List[WaveVariant] = []

    def get(self, instrument: int, offset: int) -> int:
        q = max(1, int(getattr(self.module, 'offset_quantum', 1)))
        offset = (max(0, offset) // q) * q
        key = WaveKey(instrument, offset)
        if key not in self.variants:
            if len(self.order) >= min(MAX_WAVES, 64):
                raise ValueError("more than 64 custom OPL4 wave variants are required; reduce sample-offset diversity")
            s = self.module.samples.get(instrument)
            if s is None:
                raise ValueError(f"instrument {instrument} is not an 8-bit PCM sample")
            v = WaveVariant(key=key, wave_number=384 + len(self.order), sample_name=s.name,
                            source_length=s.length)
            self.variants[key] = v
            self.order.append(v)
        return self.variants[key].wave_number

    def build(self) -> Tuple[bytes, List[dict]]:
        # Put each original sample once in RAM.  Header variants can point into it.
        used_instruments = sorted({v.key.instrument for v in self.order})
        cursor = SAMPLE_BASE
        source_addr: Dict[int, int] = {}
        source_payloads: List[Tuple[int, bytes]] = []
        for ins in used_instruments:
            s = self.module.samples[ins]
            source_addr[ins] = cursor
            # OPL4 always loops.  For S3M one-shots keep one signed-zero byte
            # directly after the source sample so every offset variant can share
            # the same payload and loop on that single silent byte.
            source_data = s.data if s.looped else (s.data + b"\0")
            source_payloads.append((cursor, source_data))
            cursor += len(source_data)

        # Variant that starts inside the loop needs a short private payload so its
        # loop target can still precede the post-offset tail.
        for v in self.order:
            s = self.module.samples[v.key.instrument]
            off = v.key.offset
            if off >= s.length:
                v.silence = True
                v.shared_source = False
                v.start_addr = cursor
                v.loop_pos = 0
                v.play_length = 1
                v.payload = b"\0"
                cursor += 1
                continue
            if not s.looped:
                # YMF278B has no one-shot bit: play through the original sample,
                # then loop forever on the single signed-zero sentinel appended
                # during source allocation.  Offset variants can share it too.
                remaining = s.length - off
                if remaining + 1 > 65536:
                    raise ValueError(
                        f"one-shot wave variant {s.number}/O{off//256:02X} exceeds "
                        "OPL4 65536-sample header limit including silent sentinel"
                    )
                v.start_addr = source_addr[s.number] + off
                v.loop_pos = remaining
                v.play_length = remaining + 1
                continue
            loop_b, loop_e = s.loop_begin, s.loop_end
            if off <= loop_b:
                v.start_addr = source_addr[s.number] + off
                v.loop_pos = loop_b - off
                v.play_length = loop_e - off
                continue
            # Offset is after loop start.  Rebuild a private sequence:
            # offset..end-of-reachable-sample, followed by original loop body.
            tail_end = s.length if off >= loop_e else loop_e
            first = s.data[off:tail_end]
            loop = s.data[loop_b:loop_e]
            payload = first + loop
            if not payload:
                payload = b"\0"
            if len(payload) > 65536:
                raise ValueError(f"wave variant {s.number}/O{off//256:02X} exceeds OPL4 65536-sample header limit")
            v.shared_source = False
            v.start_addr = cursor
            v.loop_pos = len(first)
            v.play_length = len(payload)
            v.payload = payload
            cursor += len(payload)

        if cursor - HEADER_BASE > MAX_SAMPLE_RAM:
            raise ValueError(f"MoonSound RAM image needs {cursor-HEADER_BASE} bytes (>1 MiB)")

        image = bytearray(cursor - HEADER_BASE)
        for addr, data in source_payloads:
            image[addr-HEADER_BASE:addr-HEADER_BASE+len(data)] = data
        for v in self.order:
            if v.payload:
                image[v.start_addr-HEADER_BASE:v.start_addr-HEADER_BASE+len(v.payload)] = v.payload

        manifest: List[dict] = []
        for idx, v in enumerate(self.order):
            s = self.module.samples[v.key.instrument]
            if not (1 <= v.play_length <= 65536):
                raise ValueError(f"invalid wave length {v.play_length}")
            complement = (-v.play_length) & 0xffff
            h = bytearray(12)
            h[0] = (v.start_addr >> 16) & 0x3f   # format 00 = signed 8-bit
            h[1] = (v.start_addr >> 8) & 0xff
            h[2] = v.start_addr & 0xff
            h[3] = (v.loop_pos >> 8) & 0xff
            h[4] = v.loop_pos & 0xff
            h[5] = (complement >> 8) & 0xff
            h[6] = complement & 0xff
            # LFO/VIB=0, instant attack, no decay, release 7, AM=0.
            h[7] = 0x00
            h[8] = 0xF0
            h[9] = 0x00
            h[10] = 0x07
            h[11] = 0x00
            hoff = idx * 12
            image[hoff:hoff+12] = h
            manifest.append({
                "wave": v.wave_number, "instrument": v.key.instrument,
                "sample_name": v.sample_name, "offset_samples": v.key.offset,
                "start_address": v.start_addr, "loop_position": v.loop_pos,
                "play_length": v.play_length, "source_length": v.source_length,
                "shared_source_payload": v.shared_source, "silence": v.silence,
            })
        return bytes(image), manifest


@dataclass
class Channel:
    instrument: int = 0
    period: float = 0.0
    target_period: float = 0.0
    base_period: float = 0.0
    note_index: int = -1
    volume: int = 0
    offset_mem: int = 0
    g_mem: int = 0
    h_mem: int = 0
    global_mem: int = 0
    # ST3 Hxy memory is nibble-wise: x=0 retains speed and y=0 retains depth.
    vibrato_speed: int = 0
    vibrato_depth: int = 0
    vibrato_phase: int = 0
    wave: int = 0
    key: bool = False
    # row-local
    cmd: str = ""
    param: int = 0
    row_note: Optional[int] = None
    row_ins: Optional[int] = None
    row_vol: Optional[int] = None
    delayed_tick: int = -1
    delayed_done: bool = False
    retrig_count: int = 0
    # OPL4 shadow
    reg_wave_lo: int = -1
    reg_wave_fnum_lo: int = -1
    reg_fnum_hi_oct: int = -1
    reg_level: int = -1
    reg_pan_key: int = -1


class Compiler:
    def __init__(self, module: Module, start_order: int, stop_order: Optional[int], max_seconds: float):
        self.m = module
        self.start_order = start_order
        self.stop_order = stop_order if stop_order is not None else self._next_255(start_order)
        self.max_seconds = max_seconds
        self.channels: Dict[int, Channel] = {ch: Channel() for ch in self.m.active_channels}
        self.bank = WaveBank(module)
        self.speed = module.speed
        self.tempo = module.tempo
        self.order = start_order
        self.row = 0
        self.tick_count = 0
        self.records: List[List[Tuple[int, int]]] = []
        self.row_count = 0
        self.jumps = 0
        self.fast_volume_slides = bool(module.flags & 0x40)
        self.pending_jump: Optional[int] = None
        self.pending_break: Optional[int] = None
        self.ended_reason = ""
        self.max_tick_limit = int(max_seconds * max(32, module.tempo) / 2.5) + 100 if max_seconds > 0 else 10_000_000

    def _next_255(self, start: int) -> int:
        for i in range(start, len(self.m.orders)):
            if self.m.orders[i] == 255:
                return i
        return len(self.m.orders)

    @staticmethod
    def _cmd_letter(cmd: Optional[int]) -> str:
        if not cmd: return ""
        if 1 <= cmd <= 26: return chr(ord('A') + cmd - 1)
        return ""

    def _resolve_param(self, c: Channel, cmd: str, p: int) -> int:
        # Genuine ST3 has one shared effect-parameter byte. D/E/F/I/J/K/L/Q/R/S
        # recall it on xx=00, but *any real command* with xx!=00 updates it.
        # A token with command=NONE never updates memory. G/H/O additionally keep
        # their command-specific state used by their own zero-parameter forms.
        raw = p
        if cmd in "DEFIJKLQRS":
            p = raw or c.global_mem
        elif cmd == "G":
            p = raw or c.g_mem
            if raw: c.g_mem = raw
        elif cmd == "H":
            # H has nibble-wise vibrato memory, even though Hxx also updates the
            # shared ST3 parameter byte for later D/E/F/... 00 commands.
            if raw & 0xF0:
                c.vibrato_speed = (raw >> 4) & 0x0F
            if raw & 0x0F:
                c.vibrato_depth = raw & 0x0F
            c.h_mem = (c.vibrato_speed << 4) | c.vibrato_depth
            p = c.h_mem
        elif cmd == "O":
            p = raw or c.offset_mem
            if raw: c.offset_mem = raw
        if cmd and raw:
            c.global_mem = raw
        return p

    @staticmethod
    def _note_index(note: int) -> int:
        return ((note >> 4) & 0x0f) * 12 + (note & 0x0f)

    def _period_for(self, instrument: int, note_index: int) -> float:
        s = self.m.samples[instrument]
        freq = s.c2spd * (2.0 ** ((note_index - 48) / 12.0))
        return PERIOD_CLOCK / max(1.0, freq)

    @staticmethod
    def _pitch_regs(period: float) -> Tuple[int, int]:
        if period <= 0:
            return 0, 0x80
        freq = PERIOD_CLOCK / period
        ratio = max(1e-9, freq / 44100.0)
        octave = math.floor(math.log2(ratio)) + 1
        octave = max(-8, min(7, octave))
        base = 2.0 ** (octave - 1)
        fnum = int(round((ratio / base - 1.0) * 1024.0))
        while fnum < 0 and octave > -8:
            octave -= 1; base *= 0.5
            fnum = int(round((ratio / base - 1.0) * 1024.0))
        while fnum > 1023 and octave < 7:
            octave += 1; base *= 2.0
            fnum = int(round((ratio / base - 1.0) * 1024.0))
        fnum = max(0, min(1023, fnum))
        reg20_bits = (fnum & 0x7f) << 1
        reg38 = ((octave & 0x0f) << 4) | ((fnum >> 7) & 7)
        return reg20_bits, reg38

    @staticmethod
    def _level_reg(volume: int, global_volume: int) -> int:
        amp = max(0.0, min(1.0, (volume / 64.0) * (global_volume / 64.0)))
        if amp <= 0.000001:
            tl = 127
        else:
            tl = int(round((-20.0 * math.log10(amp)) / 0.375))
            tl = max(0, min(126, tl))
        return (tl << 1) | 1  # LD=1: immediate TL update

    def _pan_nibble(self, ch: int) -> int:
        setting = self.m.channel_settings[ch]
        # ST3's default left/right groups are not hard-panned.  OPL4 values 11/5
        # provide a strong ~15 dB stereo bias while retaining the opposite side.
        return 11 if setting < 8 else 5

    def _write(self, writes: List[Tuple[int, int]], c: Channel, reg: int, value: int, attr: str, force=False):
        value &= 0xff
        if force or getattr(c, attr) != value:
            writes.append((reg, value))
            setattr(c, attr, value)

    def _emit_pitch(self, ch: int, c: Channel, period: float, writes: List[Tuple[int, int]], force=False):
        lo_bits, hi_oct = self._pitch_regs(period)
        wave_hi = ((c.wave >> 8) & 1) if c.wave else 0
        self._write(writes, c, 0x20 + ch, lo_bits | wave_hi, "reg_wave_fnum_lo", force)
        self._write(writes, c, 0x38 + ch, hi_oct, "reg_fnum_hi_oct", force)

    def _emit_volume(self, ch: int, c: Channel, writes: List[Tuple[int, int]], force=False):
        self._write(writes, c, 0x50 + ch, self._level_reg(c.volume, self.m.global_volume), "reg_level", force)

    def _keyoff(self, ch: int, c: Channel, writes: List[Tuple[int, int]], force=True):
        pan = self._pan_nibble(ch)
        self._write(writes, c, 0x68 + ch, pan, "reg_pan_key", force)
        c.key = False

    def _keyon(self, ch: int, c: Channel, writes: List[Tuple[int, int]], force=True):
        pan = self._pan_nibble(ch)
        self._write(writes, c, 0x68 + ch, 0x80 | pan, "reg_pan_key", force)
        c.key = True

    def _trigger(self, ch: int, c: Channel, note: Optional[int], ins: Optional[int], vol: Optional[int], writes: List[Tuple[int, int]], porta=False, sample_offset=0):
        if ins and ins in self.m.samples:
            c.instrument = ins
            if vol is None:
                c.volume = self.m.samples[ins].volume
        if vol is not None and vol <= 64:
            c.volume = vol
        if note is None:
            self._emit_volume(ch, c, writes)
            return
        if note == 254:
            self._keyoff(ch, c, writes)
            c.volume = 0
            self._emit_volume(ch, c, writes)
            return
        if note >= 254 or c.instrument not in self.m.samples:
            return
        ni = self._note_index(note)
        target = self._period_for(c.instrument, ni)
        if porta and c.period > 0:
            c.target_period = target
            c.note_index = ni
            self._emit_volume(ch, c, writes)
            return
        c.note_index = ni
        c.period = target
        c.base_period = target
        c.target_period = target
        c.wave = self.bank.get(c.instrument, sample_offset)
        self._keyoff(ch, c, writes, force=True)
        lo_bits, hi_oct = self._pitch_regs(c.period)
        # YMF278B: set wave-number N8 (reg 20h+n bit 0) first. Writing
        # N0..N7 (reg 08h+n) completes the wave-table-number update and
        # starts loading the selected 12-byte header. Real hardware/openMSX
        # requires this ordering even though simpler host cores may tolerate
        # the reverse order.
        self._write(writes, c, 0x20 + ch, lo_bits | ((c.wave >> 8) & 1), "reg_wave_fnum_lo", True)
        self._write(writes, c, 0x08 + ch, c.wave & 0xff, "reg_wave_lo", True)
        self._write(writes, c, 0x38 + ch, hi_oct, "reg_fnum_hi_oct", True)
        self._emit_volume(ch, c, writes, force=True)
        self._keyon(ch, c, writes, force=True)
        c.vibrato_phase = 0
        c.retrig_count = 0

    @staticmethod
    def _slide_volume(v: int, p: int, tick: int, fast: bool) -> int:
        x, y = p >> 4, p & 0x0f
        if x == 0 and y == 0: return v
        # Fine slides: DFy down / DxF up, first tick only.
        if x == 0x0f and y not in (0, 0x0f):
            return max(0, v - y) if tick == 0 else v
        if y == 0x0f and x not in (0, 0x0f):
            return min(64, v + x) if tick == 0 else v
        # Fast-volume-slide compatibility special cases D0F / DF0.
        if fast and x == 0 and y == 0x0f:
            return max(0, v - y)
        if fast and x == 0x0f and y == 0:
            return min(64, v + x)
        if tick == 0: return v
        if x and not y: return min(64, v + x)
        if y and not x: return max(0, v - y)
        # ST3 effectively prefers slide down for ambiguous non-zero nibbles.
        return max(0, v - y) if y else v

    @staticmethod
    def _retrig_volume(v: int, x: int) -> int:
        if x in (0, 8): return v
        if x == 1: return max(0, v-1)
        if x == 2: return max(0, v-2)
        if x == 3: return max(0, v-4)
        if x == 4: return max(0, v-8)
        if x == 5: return max(0, v-16)
        if x == 6: return max(0, (v*2)//3)
        if x == 7: return max(0, v//2)
        if x == 9: return min(64, v+1)
        if x == 10: return min(64, v+2)
        if x == 11: return min(64, v+4)
        if x == 12: return min(64, v+8)
        if x == 13: return min(64, v+16)
        if x == 14: return min(64, int(v*1.5))
        if x == 15: return min(64, v*2)
        return v

    def _apply_pitch_slide(self, c: Channel, cmd: str, p: int, tick: int):
        if c.period <= 0: return
        hi, lo = p >> 4, p & 0x0f
        delta = float(p)
        if hi == 0x0f:
            if tick != 0: return
            delta = float(lo)
        elif hi == 0x0e:
            if tick != 0: return
            delta = float(lo) / 4.0
        elif tick == 0:
            return
        if cmd == "E": c.period += delta
        else: c.period = max(1.0, c.period - delta)
        c.base_period = c.period

    def _apply_porta(self, c: Channel, p: int, tick: int):
        if tick == 0 or c.period <= 0 or c.target_period <= 0: return
        step = float(p)
        if c.period < c.target_period:
            c.period = min(c.target_period, c.period + step)
        elif c.period > c.target_period:
            c.period = max(c.target_period, c.period - step)
        c.base_period = c.period

    def _vibrato_period(self, c: Channel, advance: bool = True) -> float:
        if c.period <= 0 or c.vibrato_depth <= 0:
            if advance:
                c.vibrato_phase = (c.vibrato_phase + c.vibrato_speed) & 63
            return c.period
        phase = c.vibrato_phase & 63
        table_delta = MOD_SINUS_TABLE[phase]
        # OpenMPT/ST3: depth nibble is stored as depth*4, then
        # (-table*depth*4)/64 is truncated in the classic 4x period domain.
        # This compiler uses quarter-sized periods, hence divide the truncated
        # ST3 delta by four. Keep the quarter-period precision as a float.
        st3_delta = math.trunc((table_delta * c.vibrato_depth) / 16.0)
        out = max(1.0, c.period + st3_delta / 4.0)
        if advance:
            c.vibrato_phase = (c.vibrato_phase + c.vibrato_speed) & 63
        return out

    def _arpeggio_period(self, c: Channel, p: int, tick: int) -> float:
        if c.period <= 0 or c.note_index < 0 or c.instrument not in self.m.samples: return c.period
        semis = (0, p >> 4, p & 0x0f)[tick % 3]
        return self._period_for(c.instrument, c.note_index + semis)

    def _prepare_row(self, evs: Iterable[Event]):
        self.pending_jump = None
        self.pending_break = None
        by_ch = {e.ch: e for e in evs if e.ch in self.channels}
        for ch, c in self.channels.items():
            e = by_ch.get(ch)
            c.cmd = ""; c.param = 0; c.row_note = None; c.row_ins = None; c.row_vol = None
            c.delayed_tick = -1; c.delayed_done = False
            if e is None: continue
            c.row_note, c.row_ins, c.row_vol = e.note, e.ins, e.vol
            cmd = self._cmd_letter(e.cmd)
            p = e.param or 0
            if cmd:
                p = self._resolve_param(c, cmd, p)
            c.cmd, c.param = cmd, p
            if cmd == "A" and p:
                self.speed = max(1, p)
            elif cmd == "B":
                self.pending_jump = p
            elif cmd == "C" and p <= 0x3f:
                self.pending_break = p
            elif cmd == "S" and (p >> 4) == 0x0d:
                c.delayed_tick = p & 0x0f

    def _tick_channel(self, ch: int, c: Channel, tick: int, writes: List[Tuple[int, int]]):
        cmd, p = c.cmd, c.param
        delayed = c.delayed_tick >= 0
        if tick == 0:
            if not delayed:
                self._trigger(ch, c, c.row_note, c.row_ins, c.row_vol, writes, porta=(cmd == "G"), sample_offset=(c.offset_mem * 256 if cmd == "O" else 0))
            elif c.row_vol is not None and c.row_vol <= 64:
                # Note/instrument is delayed; explicit volume column is still a row command.
                c.volume = c.row_vol
                self._emit_volume(ch, c, writes)
            # Fine pitch/volume slides happen on tick zero. ST3 vibrato is
            # evaluated on tick zero as well, but its phase is not advanced.
            if cmd == "D":
                nv = self._slide_volume(c.volume, p, tick, self.fast_volume_slides)
                if nv != c.volume: c.volume = nv; self._emit_volume(ch, c, writes)
            elif cmd in ("E", "F"):
                self._apply_pitch_slide(c, cmd, p, tick); self._emit_pitch(ch, c, c.period, writes)
            elif cmd == "H":
                self._emit_pitch(ch, c, self._vibrato_period(c, advance=False), writes)
            elif cmd == "K":
                nv = self._slide_volume(c.volume, p, tick, self.fast_volume_slides)
                if nv != c.volume: c.volume = nv; self._emit_volume(ch, c, writes)
                self._emit_pitch(ch, c, self._vibrato_period(c, advance=False), writes)
            return

        if delayed and not c.delayed_done and tick == c.delayed_tick:
            if c.delayed_tick != 0 and c.delayed_tick < self.speed:
                self._trigger(ch, c, c.row_note, c.row_ins, c.row_vol, writes, porta=False, sample_offset=(c.offset_mem * 256 if cmd == "O" else 0))
            c.delayed_done = True

        out_period = c.period
        if cmd == "D":
            nv = self._slide_volume(c.volume, p, tick, self.fast_volume_slides)
            if nv != c.volume:
                c.volume = nv; self._emit_volume(ch, c, writes)
        elif cmd in ("E", "F"):
            self._apply_pitch_slide(c, cmd, p, tick); out_period = c.period
        elif cmd == "G":
            self._apply_porta(c, p, tick); out_period = c.period
        elif cmd == "H":
            out_period = self._vibrato_period(c, advance=True)
        elif cmd == "J":
            out_period = self._arpeggio_period(c, p, tick)
        elif cmd == "K":
            nv = self._slide_volume(c.volume, p, tick, self.fast_volume_slides)
            if nv != c.volume:
                c.volume = nv; self._emit_volume(ch, c, writes)
            out_period = self._vibrato_period(c, advance=True) if c.vibrato_depth else c.period
        elif cmd == "Q":
            x, y = p >> 4, p & 0x0f
            if y and tick % y == 0 and c.instrument:
                c.volume = self._retrig_volume(c.volume, x)
                self._emit_volume(ch, c, writes, force=True)
                self._keyoff(ch, c, writes, force=True)
                self._keyon(ch, c, writes, force=True)
        if out_period > 0 and cmd in "EFGHJK":
            self._emit_pitch(ch, c, out_period, writes)

    def _advance_position(self):
        if self.pending_jump is not None:
            target = self.pending_jump
            if target < self.start_order or target >= self.stop_order:
                self.ended_reason = f"position jump leaves subsong (B{target:02X})"
                return False
            self.order = target
            self.row = self.pending_break or 0
            self.jumps += 1
            return True
        if self.pending_break is not None:
            self.order += 1
            while self.order < self.stop_order and self.m.orders[self.order] == 254:
                self.order += 1
            self.row = self.pending_break
        else:
            self.row += 1
            current_pat = self.m.orders[self.order] if self.order < len(self.m.orders) else 0
            row_limit = len(self.m.patterns[current_pat]) if current_pat < len(self.m.patterns) else 64
            if self.row >= row_limit:
                self.row = 0
                self.order += 1
                while self.order < self.stop_order and self.m.orders[self.order] == 254:
                    self.order += 1
        if self.order >= self.stop_order or self.order >= len(self.m.orders) or self.m.orders[self.order] == 255:
            self.ended_reason = "end of subsong/order list"
            return False
        return True

    def compile(self):
        # Startup: select RAM wave header bank (wave 384+ -> 0x200000) and a sane mix level.
        startup = [(0x02, 0x10), (0xF8, 0x00), (0xF9, 0x00)]
        seconds = 0.0
        while self.order < self.stop_order and self.tick_count < self.max_tick_limit:
            pat = self.m.orders[self.order]
            if pat == 254:
                self.order += 1; continue
            if pat == 255 or pat >= len(self.m.patterns):
                self.ended_reason = "invalid/end order"; break
            evs = self.m.patterns[pat][self.row]
            self._prepare_row(evs)
            row_speed = self.speed
            for tick in range(row_speed):
                writes: List[Tuple[int, int]] = []
                for ch in self.m.active_channels:
                    self._tick_channel(ch, self.channels[ch], tick, writes)
                self.records.append(writes)
                self.tick_count += 1
                seconds += 2.5 / self.tempo
                if seconds >= self.max_seconds:
                    self.ended_reason = f"max-seconds {self.max_seconds:.3f} reached"
                    break
            self.row_count += 1
            if seconds >= self.max_seconds:
                break
            if not self._advance_position():
                break
        if self.records:
            self.records[0] = startup + self.records[0]
        else:
            self.records.append(startup)
        if not self.ended_reason:
            self.ended_reason = "tick limit reached" if self.tick_count >= self.max_tick_limit else "ended"
        return seconds


def pack_stream(records: List[List[Tuple[int,int]]], tempo: int, frame_hz: int = 60) -> Tuple[bytes, dict]:
    # Header: SRM1, version, frame_hz, tempo, reserved, tick_count u32,
    # data_size u32, then compact records.
    data = bytearray()
    zero_run = 0
    write_count = 0
    max_writes = 0
    nonempty = 0

    def flush_zero():
        nonlocal zero_run
        while zero_run:
            n = min(128, zero_run)
            data.append(0x80 | (n - 1))
            zero_run -= n

    for writes in records:
        if not writes:
            zero_run += 1
            continue
        flush_zero()
        nonempty += 1
        max_writes = max(max_writes, len(writes))
        write_count += len(writes)
        pos = 0
        # A single tick may very occasionally need >127 writes; split into
        # continuation chunks.  Runtime consumes all chunks before advancing tick.
        while pos < len(writes):
            n = min(127, len(writes)-pos)
            data.append(n)
            for reg, val in writes[pos:pos+n]:
                data += bytes((reg & 0xff, val & 0xff))
            pos += n
            if pos < len(writes):
                data += b"\x7f"  # impossible marker? replaced below; safeguard
                raise ValueError("tick has >127 OPL4 writes; v0.1 stream format cannot encode continuation")
    flush_zero()
    data.append(0)  # end
    h = bytearray(16)
    h[:4] = b"SRM1"
    h[4] = 1
    h[5] = frame_hz
    h[6:8] = struct.pack("<H", tempo)
    h[8:12] = struct.pack("<I", len(records))
    h[12:16] = struct.pack("<I", len(data))
    stats = {
        "ticks": len(records), "opl4_register_writes": write_count,
        "nonempty_ticks": nonempty, "max_writes_per_tick": max_writes,
        "stream_payload_bytes": len(data), "stream_total_bytes": len(h)+len(data),
        "average_writes_per_tick": write_count / max(1, len(records)),
        "tick_hz": tempo / 2.5,
    }
    return bytes(h + data), stats


def estimate_z80(stats: dict, cpu_hz: int = 3579545) -> dict:
    # Runtime implementation below uses OUT (C),r / pointer/count bookkeeping.
    # We give a conservative accounting budget, not an exact instruction trace:
    # ~70 T-states per register pair plus ~100 T-states tick-record overhead.
    avg = stats["average_writes_per_tick"]
    peak = stats["max_writes_per_tick"]
    tick_hz = stats["tick_hz"]
    avg_cycles_tick = 100 + avg * 70
    peak_cycles_tick = 100 + peak * 70
    return {
        "assumed_z80_hz": cpu_hz,
        "model_cycles_per_opl4_write_pair": 70,
        "model_fixed_cycles_per_tracker_tick": 100,
        "estimated_average_cycles_per_tracker_tick": avg_cycles_tick,
        "estimated_peak_cycles_per_tracker_tick": peak_cycles_tick,
        "estimated_average_cpu_percent": 100.0 * avg_cycles_tick * tick_hz / cpu_hz,
        "estimated_peak_single_tick_ms": 1000.0 * peak_cycles_tick / cpu_hz,
        "note": "Conservative static model; verify with openMSX instruction timing after ROM integration.",
    }


def next_stop_order(orders: List[int], start: int) -> int:
    for i in range(start, len(orders)):
        if orders[i] == 255:
            return i
    return len(orders)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, required=True)
    ap.add_argument("--start-order", type=int, default=0)
    ap.add_argument("--stop-order", type=int)
    ap.add_argument("--max-seconds", type=float, default=600.0)
    ap.add_argument("--frame-hz", type=int, default=60)
    args = ap.parse_args()

    m = parse_s3m(args.input)
    stop = args.stop_order if args.stop_order is not None else next_stop_order(m.orders, args.start_order)
    c = Compiler(m, args.start_order, stop, args.max_seconds)
    duration = c.compile()
    ram, waves = c.bank.build()
    stream, stats = pack_stream(c.records, c.tempo, args.frame_hz)
    cpu = estimate_z80(stats)

    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "moonsound_ram.bin").write_bytes(ram)
    (args.outdir / "music.srm").write_bytes(stream)
    manifest = {
        "format": "Second Reality MoonSound stream v0.1",
        "source": args.input.name,
        "title": m.title,
        "start_order": args.start_order,
        "stop_order_exclusive": stop,
        "compiled_seconds": duration,
        "end_reason": c.ended_reason,
        "initial_speed": m.speed,
        "initial_tempo": m.tempo,
        "compiled_tempo": c.tempo,
        "frame_hz": args.frame_hz,
        "active_pcm_channels": m.active_channels,
        "s3m_flags": m.flags,
        "fast_volume_slides": c.fast_volume_slides,
        "sample_ram_bytes": len(ram),
        "sample_ram_free_of_1MiB": MAX_SAMPLE_RAM - len(ram),
        "wave_variant_count": len(waves),
        "stream": stats,
        "cpu_model": cpu,
        "waves": waves,
    }
    (args.outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in manifest.items() if k != "waves"}, indent=2))


if __name__ == "__main__":
    main()
