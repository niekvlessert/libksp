#!/usr/bin/env python3
"""ksp_analyse - forensic KSP/MSX compatibility analyser.

Designed for diagnosing KSP files that run in a host player but crash, hang or
stay silent in KSP1PLAY on a real MSX/openMSX.  It reconstructs KSP engine
pages, invokes z80dasm, walks reachable Z80 code from INIT/PLAY and reports
memory-page, mapper and sound-chip usage with evidence addresses.

This tool is deliberately conservative: static analysis can prove some
incompatibilities, but cannot prove every indirect jump or runtime-generated
code path safe.
"""
from __future__ import annotations

import argparse
import binascii
import csv
import dataclasses
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence

from dsk_support import (
    EXPECTED_BUILDER, EXPECTED_PLAYER_CORE, TEMPLATE_NAME,
    build_single_ksp_disk, locate_latest_template,
)

try:
    from zx0_codec import decompress as zx0_decompress, compress_best as zx0_compress_best
except Exception as exc:  # pragma: no cover
    zx0_decompress = None
    zx0_compress_best = None
    ZX0_IMPORT_ERROR = str(exc)
else:
    ZX0_IMPORT_ERROR = ""

VERSION = "0.1.4"
NULL16 = 0xFFFF
NULL32 = 0xFFFFFFFF
COMP_NONE = 0
COMP_ZX0 = 1
COMP_ZX0_BLOCKS = 2
PAGE_SPARSE = 0
PAGE_COMPLETE = 1
PAGE_PBM1 = 2
PAGE_RMP1 = 3
PAGE_HPOL = 4
PAGE_BASE_ZERO = 1
RES_REQUIRED = 1
RES_PAGE_SOURCE = 4

ENGINE_DYNAMIC_PAGES = 1 << 0
ENGINE_BANKED_DATA = 1 << 1
ENGINE_MWK_REQUIRED = 1 << 2
ENGINE_PAGE2_RUNTIME = 1 << 3
ENGINE_PAGE3_WORKRAM = 1 << 4

HW_PSG = 1 << 0
HW_SCC = 1 << 1
HW_SCC_PLUS = 1 << 2
HW_DUAL_SCC = 1 << 3
HW_FMPAC = 1 << 4
HW_Y8950 = 1 << 5
HW_OPL4 = 1 << 6
HW_SN76489 = 1 << 7
HW_GG_STEREO = 1 << 8

SEVERITY_ORDER = {"INFO": 0, "NOTICE": 1, "SUSPICIOUS": 2, "HIGH": 3, "BLOCKER": 4}
VERDICTS = {
    0: "LIKELY SAFE",
    1: "LIKELY SAFE",
    2: "SUSPICIOUS",
    3: "HIGH RISK",
    4: "BLOCKER",
}

HW_NAMES = [
    (HW_PSG, "PSG"), (HW_SCC, "SCC"), (HW_SCC_PLUS, "SCC+"),
    (HW_DUAL_SCC, "Dual SCC"), (HW_FMPAC, "FM-PAC/YM2413"),
    (HW_Y8950, "MSX-AUDIO/Y8950"), (HW_OPL4, "MoonSound/OPL4"),
    (HW_SN76489, "SN76489"), (HW_GG_STEREO, "GG stereo"),
]
FLAG_NAMES = [
    (ENGINE_DYNAMIC_PAGES, "DYNAMIC_PAGES"),
    (ENGINE_BANKED_DATA, "BANKED_DATA"),
    (ENGINE_MWK_REQUIRED, "MWK_REQUIRED"),
    (ENGINE_PAGE2_RUNTIME, "PAGE2_RUNTIME"),
    (ENGINE_PAGE3_WORKRAM, "PAGE3_WORKRAM"),
]


def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def u16(b: bytes, off: int) -> int:
    return struct.unpack_from("<H", b, off)[0]


def u32(b: bytes, off: int) -> int:
    return struct.unpack_from("<I", b, off)[0]


def check_range(total: int, off: int, size: int, what: str = "range") -> None:
    if off < 0 or size < 0 or off + size > total:
        raise ValueError(f"{what} outside file: off=0x{off:X} size=0x{size:X} file=0x{total:X}")


def mask_names(value: int, names: Sequence[tuple[int, str]]) -> list[str]:
    out = [name for bit, name in names if value & bit]
    known = 0
    for bit, _ in names:
        known |= bit
    if value & ~known:
        out.append(f"unknown(0x{value & ~known:X})")
    return out


@dataclasses.dataclass
class Engine:
    index: int
    flags: int
    hardware: int
    abi: int
    tick_hz: int
    load: int
    page_size: int
    init: int
    play: int
    stop: int
    gateway: int
    replace_start: int
    first_page: int
    page_count: int
    default_mwk: int
    template_compression: int
    first_bank: int
    bank_count: int
    bank_width: int
    template_off: int
    template_packed: int
    template_raw: int
    template_crc: int
    name_off: int
    template: bytes = b""


@dataclasses.dataclass
class Page:
    index: int
    engine: int
    encoding: int
    compression: int
    flags: int
    offset: int
    packed: int
    unpacked: int
    final_crc: int


@dataclasses.dataclass
class Track:
    index: int
    page: int
    song: int
    flags: int
    mwk: int
    image: int
    title_off: int
    duration_ms: int
    loop_start_ms: int
    loop_end_ms: int
    fade_ms: int


@dataclasses.dataclass
class Resource:
    index: int
    kind: str
    flags: int
    compression: int
    offset: int
    packed: int
    unpacked: int
    crc: int
    name_off: int


@dataclasses.dataclass
class Finding:
    severity: str
    code: str
    message: str
    evidence: list[str] = dataclasses.field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class KspPackage:
    def __init__(self, path: Path, data: bytes|None = None):
        self.path = path
        self.data = path.read_bytes() if data is None else bytes(data)
        self.header: dict[str, Any] = {}
        self.engines: list[Engine] = []
        self.pages: list[Page] = []
        self.tracks: list[Track] = []
        self.resources: list[Resource] = []
        self.strings = b""
        self.meta: dict[str, str] = {}
        self._resource_cache: dict[int, bytes] = {}
        self._pblk_cache: dict[int, tuple[int, list[bytes]]] = {}
        self._hpol_cache: dict[str, Any] | None = None
        self.parse()

    def parse(self) -> None:
        b = self.data
        if len(b) < 80 or b[:4] != b"KSP1":
            raise ValueError("not a KSP1 file or header shorter than 80 bytes")
        header_size, minor = struct.unpack_from("<HH", b, 4)
        flags, file_size = struct.unpack_from("<II", b, 8)
        if header_size < 80 or header_size > len(b):
            raise ValueError(f"invalid header size {header_size}")
        if file_size != len(b):
            raise ValueError(f"header file_size {file_size} != actual {len(b)}")
        engine_off, engine_count, engine_stride = struct.unpack_from("<IHH", b, 16)
        page_off, page_count, page_stride = struct.unpack_from("<IHH", b, 24)
        track_off, track_count, track_stride = struct.unpack_from("<IHH", b, 32)
        res_off, res_count, res_stride = struct.unpack_from("<IHH", b, 40)
        string_off, string_size = struct.unpack_from("<II", b, 48)
        default_track, meta_resource, cover_resource, reserved = struct.unpack_from("<HHHH", b, 56)
        header_crc, index_crc = struct.unpack_from("<II", b, 64)
        self.header = dict(header_size=header_size, minor=minor, flags=flags, file_size=file_size,
                           engine_off=engine_off, engine_count=engine_count, engine_stride=engine_stride,
                           page_off=page_off, page_count=page_count, page_stride=page_stride,
                           track_off=track_off, track_count=track_count, track_stride=track_stride,
                           resource_off=res_off, resource_count=res_count, resource_stride=res_stride,
                           string_off=string_off, string_size=string_size,
                           default_track=default_track, meta_resource=meta_resource,
                           cover_resource=cover_resource, reserved=reserved,
                           header_crc=header_crc, index_crc=index_crc,
                           header_crc_ok=None, index_crc_ok=None)
        if engine_stride < 64 or page_stride < 24 or track_stride < 32 or res_stride < 32:
            raise ValueError("descriptor stride smaller than KSP 1.x minimum")
        check_range(len(b), engine_off, engine_count * engine_stride, "engine table")
        check_range(len(b), page_off, page_count * page_stride, "page table")
        check_range(len(b), track_off, track_count * track_stride, "track table")
        check_range(len(b), res_off, res_count * res_stride, "resource table")
        check_range(len(b), string_off, string_size, "string table")
        self.strings = b[string_off:string_off + string_size]
        if header_crc:
            hc=bytearray(b[:header_size]); hc[64:68]=b"\0\0\0\0"
            self.header["header_crc_ok"]=(crc32(hc)==header_crc)
        if index_crc:
            index_bytes=(b[engine_off:engine_off+engine_count*engine_stride] +
                         b[page_off:page_off+page_count*page_stride] +
                         b[track_off:track_off+track_count*track_stride] +
                         b[res_off:res_off+res_count*res_stride] + self.strings)
            self.header["index_crc_ok"]=(crc32(index_bytes)==index_crc)

        for i in range(engine_count):
            o = engine_off + i * engine_stride
            e = Engine(
                i, u32(b,o), u32(b,o+4), u16(b,o+8), u16(b,o+10),
                u16(b,o+12), u16(b,o+14), u16(b,o+16), u16(b,o+18),
                u16(b,o+20), u16(b,o+22), u16(b,o+24), u16(b,o+26),
                u16(b,o+28), u16(b,o+30), b[o+32], b[o+33], b[o+34], b[o+35],
                u32(b,o+36), u32(b,o+40), u32(b,o+44), u32(b,o+48), u32(b,o+52)
            )
            check_range(len(b), e.template_off, e.template_packed, f"engine {i} template")
            packed = b[e.template_off:e.template_off+e.template_packed]
            e.template = self.decode_object(packed, e.template_compression, e.template_raw)
            if len(e.template) != e.page_size:
                raise ValueError(f"engine {i} template raw size {len(e.template)} != page_size {e.page_size}")
            if e.template_crc and crc32(e.template) != e.template_crc:
                raise ValueError(f"engine {i} template CRC mismatch")
            self.engines.append(e)
        for i in range(page_count):
            o = page_off + i * page_stride
            p = Page(i, u16(b,o), b[o+2], b[o+3], u16(b,o+4), u32(b,o+8), u32(b,o+12), u32(b,o+16), u32(b,o+20))
            if p.engine >= len(self.engines):
                raise ValueError(f"page {i} references engine {p.engine}")
            if p.encoding != PAGE_HPOL:
                check_range(len(b), p.offset, p.packed, f"page {i} payload")
            self.pages.append(p)
        for i in range(track_count):
            o = track_off + i * track_stride
            t = Track(i, u16(b,o), u16(b,o+2), u16(b,o+4), u16(b,o+6), u16(b,o+8),
                      u32(b,o+12), u32(b,o+16), u32(b,o+20), u32(b,o+24), u32(b,o+28))
            if t.page >= len(self.pages):
                raise ValueError(f"track {i} references page {t.page}")
            self.tracks.append(t)
        for i in range(res_count):
            o = res_off + i * res_stride
            kind = b[o:o+4].decode("ascii", "replace")
            r = Resource(i, kind, u16(b,o+4), b[o+6], u32(b,o+8), u32(b,o+12), u32(b,o+16), u32(b,o+20), u32(b,o+24))
            check_range(len(b), r.offset, r.packed, f"resource {i} {kind}")
            self.resources.append(r)
        for r in self.resources:
            if r.kind == "META":
                try:
                    raw = self.logical_resource(r.index).decode("utf-8", "replace")
                    for line in raw.splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            self.meta[k.strip()] = v.strip()
                except Exception:
                    pass

    def string(self, offset: int) -> str:
        if offset in (NULL32,):
            return ""
        if offset < 0 or offset >= len(self.strings):
            return ""
        end = self.strings.find(b"\0", offset)
        if end < 0:
            end = len(self.strings)
        return self.strings[offset:end].decode("utf-8", "replace")

    def decode_object(self, packed: bytes, comp: int, raw_size: int) -> bytes:
        if comp == COMP_NONE:
            if len(packed) != raw_size:
                raise ValueError(f"uncompressed object size {len(packed)} != declared {raw_size}")
            return packed
        if comp == COMP_ZX0:
            if zx0_decompress is None:
                raise ValueError("ZX0 decompressor unavailable: " + ZX0_IMPORT_ERROR)
            return zx0_decompress(packed, raw_size)
        raise ValueError(f"unsupported object compression id {comp}")

    def logical_resource(self, index: int) -> bytes:
        if index in self._resource_cache:
            return self._resource_cache[index]
        if not 0 <= index < len(self.resources):
            raise ValueError("resource index outside table")
        r = self.resources[index]
        packed = self.data[r.offset:r.offset+r.packed]
        if r.compression in (COMP_NONE, COMP_ZX0):
            out = self.decode_object(packed, r.compression, r.unpacked)
        elif r.compression == COMP_ZX0_BLOCKS:
            if len(packed) < 16 or packed[:4] != b"KZB1" or u16(packed,4) != 16 or u32(packed,8) != r.unpacked:
                raise ValueError("invalid KZB1 header")
            block_count = u16(packed,6); table_off = u32(packed,12)
            check_range(len(packed), table_off, block_count*16, "KZB1 table")
            chunks = []
            for i in range(block_count):
                d = table_off + i*16
                off, size, raw_size, expect = struct.unpack_from("<IIII", packed, d)
                check_range(len(packed), off, size, "KZB1 block")
                block = self.decode_object(packed[off:off+size], COMP_ZX0, raw_size)
                if expect and crc32(block) != expect:
                    raise ValueError("KZB1 block CRC mismatch")
                chunks.append(block)
            out = b"".join(chunks)
            if len(out) != r.unpacked:
                raise ValueError("KZB1 total size mismatch")
        else:
            raise ValueError(f"unsupported resource compression {r.compression}")
        if r.crc and crc32(out) != r.crc:
            raise ValueError(f"resource {index} CRC mismatch")
        self._resource_cache[index] = out
        return out

    def pblk_pool(self, index: int) -> tuple[int, list[bytes]]:
        if index in self._pblk_cache:
            return self._pblk_cache[index]
        if not 0 <= index < len(self.resources):
            raise ValueError("PBLK resource outside table")
        r = self.resources[index]
        if r.kind != "PBLK" or r.compression != COMP_NONE or (r.flags & RES_PAGE_SOURCE):
            raise ValueError("page does not reference a valid PBLK resource")
        raw = self.data[r.offset:r.offset+r.packed]
        if len(raw) < 32 or raw[:4] != b"PBK1":
            raise ValueError("invalid PBK1 header")
        header_size, block_desc_size, slab_desc_size, block_size = struct.unpack_from("<HHHH", raw, 4)
        block_count = u32(raw,12); slab_count = u16(raw,16); flags = u16(raw,18)
        block_table = u32(raw,20); slab_table = u32(raw,24); reserved = u32(raw,28)
        if header_size != 32 or block_desc_size < 8 or slab_desc_size < 16 or not block_size or flags or reserved:
            raise ValueError("invalid PBK1 dimensions")
        check_range(len(raw), block_table, block_count*block_desc_size, "PBK1 block table")
        check_range(len(raw), slab_table, slab_count*slab_desc_size, "PBK1 slab table")
        slabs: list[bytes] = []
        for i in range(slab_count):
            d = slab_table + i*slab_desc_size
            off, packed_size = u32(raw,d), u32(raw,d+4)
            unpacked, comp, slab_flags, expect = u16(raw,d+8), raw[d+10], raw[d+11], u32(raw,d+12)
            if not unpacked or unpacked > 16384 or comp > COMP_ZX0 or slab_flags:
                raise ValueError("invalid PBK1 slab")
            check_range(len(raw), off, packed_size, "PBK1 slab")
            slab = self.decode_object(raw[off:off+packed_size], comp, unpacked)
            if expect and crc32(slab) != expect:
                raise ValueError("PBK1 slab CRC mismatch")
            slabs.append(slab)
        blocks: list[bytes] = []
        canonical = bytearray()
        for i in range(block_count):
            d = block_table + i*block_desc_size
            slab_i, source = u16(raw,d), u16(raw,d+2)
            if u32(raw,d+4) or slab_i >= len(slabs) or source + block_size > len(slabs[slab_i]):
                raise ValueError("invalid PBK1 block descriptor")
            block = slabs[slab_i][source:source+block_size]
            blocks.append(block); canonical += block
        if r.crc and crc32(canonical) != r.crc:
            raise ValueError("PBLK logical CRC mismatch")
        self._pblk_cache[index] = (block_size, blocks)
        return block_size, blocks

    def hpol_pool(self) -> dict[str, Any]:
        if self._hpol_cache is not None:
            return self._hpol_cache
        matches = [r for r in self.resources if r.kind == "HPOL"]
        if len(matches) != 1:
            raise ValueError("hybrid page requires exactly one HPOL resource")
        r = matches[0]
        if r.compression != COMP_NONE or (r.flags & (RES_REQUIRED|RES_PAGE_SOURCE)) != (RES_REQUIRED|RES_PAGE_SOURCE):
            raise ValueError("invalid HPOL resource flags")
        raw = self.data[r.offset:r.offset+r.packed]
        if len(raw) < 96 or raw[:4] != b"HPL1" or u16(raw,4) != 96 or u16(raw,6) != 1:
            raise ValueError("invalid HPL1 header")
        block_size=u16(raw,8); pos_count=u16(raw,10); page_count=u16(raw,12)
        hot_count=u16(raw,14); warm_count=u16(raw,16); cold_count=u16(raw,18); slab_count=u16(raw,20)
        if not block_size or page_count != len(self.pages) or (u16(raw,22) & ~1):
            raise ValueError("invalid HPL1 dimensions")
        pos_off=u32(raw,24); map_off=u32(raw,28); map_packed=u32(raw,32); map_raw=u32(raw,36)
        hot_off=u32(raw,40); hot_packed=u32(raw,44); hot_raw=u32(raw,48)
        warm_off=u32(raw,52); warm_packed=u32(raw,56); warm_raw=u32(raw,60)
        cold_table=u32(raw,64); cold_packed_total=u32(raw,72); cold_raw=u32(raw,76)
        hot_crc=u32(raw,80); warm_crc=u32(raw,84); cold_crc=u32(raw,88); map_crc=u32(raw,92)
        if hot_raw != hot_count*block_size or warm_raw != warm_count*block_size or cold_raw != cold_count*block_size or map_raw != page_count*pos_count*2:
            raise ValueError("HPL1 size mismatch")
        check_range(len(raw), pos_off, pos_count*2, "HPL1 positions")
        check_range(len(raw), map_off, map_packed, "HPL1 map")
        check_range(len(raw), hot_off, hot_packed, "HPL1 hot")
        check_range(len(raw), warm_off, warm_packed, "HPL1 warm")
        check_range(len(raw), cold_table, slab_count*16, "HPL1 cold table")
        positions=[u16(raw,pos_off+i*2) for i in range(pos_count)]
        for i in range(1,len(positions)):
            if positions[i-1]+block_size > positions[i]:
                raise ValueError("HPL1 positions overlap")
        decoded_map=self.decode_object(raw[map_off:map_off+map_packed], COMP_ZX0, map_raw)
        if map_crc and crc32(decoded_map)!=map_crc: raise ValueError("HPL1 map CRC mismatch")
        matrix=[u16(decoded_map,i) for i in range(0,len(decoded_map),2)]
        all_blocks=bytearray()
        def tier(off:int, packed_size:int, raw_size:int, expect:int)->None:
            if raw_size:
                dec=self.decode_object(raw[off:off+packed_size], COMP_ZX0, raw_size)
                if expect and crc32(dec)!=expect: raise ValueError("HPL1 tier CRC mismatch")
                all_blocks.extend(dec)
        tier(hot_off,hot_packed,hot_raw,hot_crc); tier(warm_off,warm_packed,warm_raw,warm_crc)
        cold=bytearray(); packed_sum=0
        for i in range(slab_count):
            d=cold_table+i*16; off=u32(raw,d); psz=u32(raw,d+4); usz=u16(raw,d+8); comp=raw[d+10]; fl=raw[d+11]; expect=u32(raw,d+12)
            if not usz or usz>16384 or usz%block_size or comp>COMP_ZX0 or fl: raise ValueError("invalid HPL1 cold slab")
            check_range(len(raw),off,psz,"HPL1 cold slab")
            dec=self.decode_object(raw[off:off+psz],comp,usz)
            if expect and crc32(dec)!=expect: raise ValueError("HPL1 cold slab CRC mismatch")
            packed_sum+=psz; cold.extend(dec)
        if len(cold)!=cold_raw or packed_sum!=cold_packed_total or (cold_crc and crc32(cold)!=cold_crc):
            raise ValueError("HPL1 cold totals mismatch")
        all_blocks.extend(cold)
        total=hot_count+warm_count+cold_count
        if len(all_blocks)!=total*block_size: raise ValueError("HPL1 block data size mismatch")
        blocks=[bytes(all_blocks[i*block_size:(i+1)*block_size]) for i in range(total)]
        if any(x>=len(blocks) for x in matrix): raise ValueError("HPL1 map block outside pool")
        self._hpol_cache={"block_size":block_size,"positions":positions,"matrix":matrix,"blocks":blocks}
        return self._hpol_cache

    def materialize_page(self, page_index: int) -> bytes:
        if not 0 <= page_index < len(self.pages):
            raise ValueError("page index outside table")
        p = self.pages[page_index]; e = self.engines[p.engine]
        if p.encoding == PAGE_HPOL:
            pool=self.hpol_pool(); out=bytearray(e.template); row=page_index*len(pool["positions"])
            for j,pos in enumerate(pool["positions"]):
                ident=pool["matrix"][row+j]; block=pool["blocks"][ident]
                if pos+len(block)>len(out): raise ValueError("invalid HPL1 page copy")
                out[pos:pos+len(block)]=block
        else:
            raw=self.decode_object(self.data[p.offset:p.offset+p.packed], p.compression, p.unpacked)
            if p.encoding == PAGE_SPARSE:
                out=bytearray(e.template); cur=0; prev=0
                while cur < len(raw):
                    if cur+4>len(raw): raise ValueError("truncated sparse page record")
                    dest,count=u16(raw,cur),u16(raw,cur+2); cur+=4
                    if not count or dest<prev or dest+count>len(out) or cur+count>len(raw): raise ValueError("invalid sparse page record")
                    out[dest:dest+count]=raw[cur:cur+count]; cur+=count; prev=dest+count
            elif p.encoding == PAGE_COMPLETE:
                if len(raw)!=e.page_size: raise ValueError("complete page size mismatch")
                out=bytearray(raw)
            elif p.encoding == PAGE_PBM1:
                out=bytearray(e.page_size) if p.flags&PAGE_BASE_ZERO else bytearray(e.template)
                if len(raw)<16 or raw[:4]!=b"PBM1" or u16(raw,4)!=16 or u16(raw,10)!=12 or u32(raw,12): raise ValueError("invalid PBM1 header")
                resource,count=u16(raw,6),u16(raw,8); check_range(len(raw),16,count*12,"PBM1 records")
                _,blocks=self.pblk_pool(resource); prev=0
                for i in range(count):
                    d=16+i*12; dest,bytes_n=u16(raw,d),u16(raw,d+2); block=u32(raw,d+4); source=u16(raw,d+8)
                    if u16(raw,d+10) or not bytes_n or dest<prev or block>=len(blocks) or dest+bytes_n>len(out) or source+bytes_n>len(blocks[block]): raise ValueError("invalid PBM1 copy record")
                    out[dest:dest+bytes_n]=blocks[block][source:source+bytes_n]; prev=dest+bytes_n
            elif p.encoding == PAGE_RMP1:
                out=bytearray(e.page_size) if p.flags&PAGE_BASE_ZERO else bytearray(e.template)
                if len(raw)<16 or raw[:4]!=b"RMP1" or u16(raw,4)!=16 or u16(raw,8)!=16 or u16(raw,10) or u32(raw,12): raise ValueError("invalid RMP1 header")
                count=u16(raw,6); check_range(len(raw),16,count*16,"RMP1 records"); prev=0
                for i in range(count):
                    d=16+i*16; dest,bytes_n=u16(raw,d),u16(raw,d+2); typ=raw[d+4]; reserved=raw[d+5]; resource=u16(raw,d+6); source=u32(raw,d+8); tail=u32(raw,d+12)
                    if reserved or tail or not bytes_n or dest<prev or dest+bytes_n>len(out): raise ValueError("invalid RMP1 record")
                    if typ==0:
                        if resource>=len(self.resources) or not(self.resources[resource].flags&RES_PAGE_SOURCE): raise ValueError("RMP1 copy references non-page-source resource")
                        src=self.logical_resource(resource)
                        if source+bytes_n>len(src): raise ValueError("RMP1 source outside resource")
                        out[dest:dest+bytes_n]=src[source:source+bytes_n]
                    elif typ==1:
                        if resource!=NULL16 or source+bytes_n>len(raw): raise ValueError("invalid RMP1 inline record")
                        out[dest:dest+bytes_n]=raw[source:source+bytes_n]
                    elif typ==2:
                        if resource!=NULL16 or source&0xFFFFFF00: raise ValueError("invalid RMP1 fill record")
                        out[dest:dest+bytes_n]=bytes([source&0xFF])*bytes_n
                    else: raise ValueError("unknown RMP1 record type")
                    prev=dest+bytes_n
            else:
                raise ValueError(f"unknown page encoding {p.encoding}")
        result=bytes(out)
        if len(result)!=e.page_size: raise ValueError("materialized page size mismatch")
        if p.final_crc and crc32(result)!=p.final_crc: raise ValueError(f"page {page_index} CRC mismatch")
        return result

    def engine_for_track(self, track_index: int) -> Engine:
        t=self.tracks[track_index]; return self.engines[self.pages[t.page].engine]


# Z80 instruction lengths and recursive control flow.  Based on the decoder in
# the v0.10 converter, but used here only for forensic analysis.
_Z80_LEN=[1]*256
for _op in (0x01,0x11,0x21,0x22,0x2A,0x31,0x32,0x3A,0xC2,0xC3,0xC4,0xCA,0xCC,0xCD,0xD2,0xD4,0xDA,0xDC,0xE2,0xE4,0xEA,0xEC,0xF2,0xF4,0xFA,0xFC): _Z80_LEN[_op]=3
for _op in (0x06,0x0E,0x10,0x16,0x18,0x1E,0x20,0x26,0x28,0x2E,0x30,0x36,0x38,0x3E,0xC6,0xCE,0xD3,0xD6,0xDB,0xDE,0xE6,0xEE,0xF6,0xFE): _Z80_LEN[_op]=2
_Z80_LEN[0xCB]=2
_Z80_ED_WORD={0x43,0x4B,0x53,0x5B,0x63,0x6B,0x73,0x7B}
_Z80_IX_DISP={0x34,0x35,0x36,0x46,0x4E,0x56,0x5E,0x66,0x6E,0x70,0x71,0x72,0x73,0x74,0x75,0x77,0x7E,0x86,0x8E,0x96,0x9E,0xA6,0xAE,0xB6,0xBE}


def insn_len(mem: bytes|bytearray, pc: int) -> int:
    op=mem[pc]
    if op==0xED:
        return 4 if pc+1<0x10000 and mem[pc+1] in _Z80_ED_WORD else 2
    if op in (0xDD,0xFD):
        if pc+1>=0x10000: return 1
        op2=mem[pc+1]
        if op2==0xCB: return 4
        if op2==0xED:
            return 1+(4 if pc+2<0x10000 and mem[pc+2] in _Z80_ED_WORD else 2)
        n=1+_Z80_LEN[op2]
        if op2 in _Z80_IX_DISP: n+=1
        return n
    return _Z80_LEN[op]


def s8(x:int)->int: return x-256 if x&0x80 else x


@dataclasses.dataclass
class Reachability:
    seen: set[int]
    unresolved_indirect: list[int]
    external_targets: list[tuple[int,int,str]]


def reachable(mem: bytearray, valid: bytearray, entries: Sequence[int]) -> Reachability:
    queue=[x&0xFFFF for x in entries]; seen:set[int]=set(); unresolved:list[int]=[]; external:list[tuple[int,int,str]]=[]
    while queue:
        pc=queue.pop()
        while 0<=pc<0x10000 and valid[pc] and pc not in seen:
            seen.add(pc); op=mem[pc]; n=insn_len(mem,pc)
            if pc+n>0x10000 or any(not valid[x] for x in range(pc,min(pc+n,0x10000))): break
            if op in (0xDD,0xFD):
                op2=mem[pc+1] if pc+1<0x10000 else 0
                if op2==0xE9: unresolved.append(pc); break
                pc=(pc+n)&0xFFFF; continue
            if op==0xED:
                op2=mem[pc+1] if pc+1<0x10000 else 0
                if op2 in (0x45,0x4D,0x55,0x5D,0x65,0x6D,0x75,0x7D): break
                pc=(pc+n)&0xFFFF; continue
            if op in (0xC3,0xC2,0xCA,0xD2,0xDA,0xE2,0xEA,0xF2,0xFA,0xCD,0xC4,0xCC,0xD4,0xDC,0xE4,0xEC,0xF4,0xFC):
                t=mem[pc+1]|(mem[pc+2]<<8); kind="CALL" if op in (0xCD,0xC4,0xCC,0xD4,0xDC,0xE4,0xEC,0xF4,0xFC) else "JP"
                if valid[t]: queue.append(t)
                else: external.append((pc,t,kind))
                if op==0xC3: break
                pc=(pc+n)&0xFFFF; continue
            if op==0x18:
                t=(pc+2+s8(mem[pc+1]))&0xFFFF
                if valid[t]: queue.append(t)
                else: external.append((pc,t,"JR"))
                break
            if op in (0x10,0x20,0x28,0x30,0x38):
                t=(pc+2+s8(mem[pc+1]))&0xFFFF
                if valid[t]: queue.append(t)
                else: external.append((pc,t,"JRcc"))
                pc=(pc+n)&0xFFFF; continue
            if op in (0xC9,0x76,0xE9):
                if op==0xE9: unresolved.append(pc)
                break
            pc=(pc+n)&0xFFFF
    # Expand strong JP(HL) table patterns when table bytes themselves are valid.
    expanded=set(); pending=[]
    for _ in range(4):
        seeds=[]
        for pc in unresolved:
            if pc in expanded: continue
            expanded.add(pc); op=mem[pc]; table=pc+(2 if op in (0xDD,0xFD) else 1)
            vals=[]; j=table
            while j+2<0x10000 and all(valid[k] for k in (j,j+1,j+2)) and mem[j]==0xC3:
                t=mem[j+1]|mem[j+2]<<8
                if not valid[t]: break
                vals.append(t); j+=3
            if len(vals)>=2: seeds.extend(vals); continue
            vals=[]; j=table
            while j+1<0x10000 and valid[j] and valid[j+1] and len(vals)<128:
                t=mem[j]|mem[j+1]<<8
                if not valid[t]: break
                vals.append(t); j+=2
            if len(vals)>=4: seeds.extend(vals)
        pending=[x for x in dict.fromkeys(seeds) if x not in seen]
        if not pending: break
        r=reachable(mem,valid,pending); seen|=r.seen; external.extend(r.external_targets)
        for x in r.unresolved_indirect:
            if x not in unresolved: unresolved.append(x)
    return Reachability(seen, unresolved, external)



@dataclasses.dataclass
class EntryReturnState:
    enabled_returns: list[int]
    disabled_returns: list[int]
    unresolved: list[int]
    enabled_sources: dict[int,list[int]]
    truncated: bool = False


def entry_return_interrupt_state(mem: bytearray, valid: bytearray, entry: int,
                                 max_states: int = 160000, max_depth: int = 20) -> EntryReturnState:
    """Context-sensitive control-flow walk for the KSP callback interrupt contract.

    Besides IFF1 state, this keeps the PC of the most recent reachable EI that
    established the enabled state.  That provenance is used by --try-fix so the
    repair pass changes only EI instructions that are proven to flow into an
    outer INIT/PLAY return with interrupts enabled.
    """
    if not (0 <= entry < 0x10000) or not valid[entry]:
        return EntryReturnState([], [], [entry], {}, False)
    # state = (pc, synthetic call-stack of return PCs, iff_enabled, last_ei_pc)
    work=[(entry, tuple(), False, None)]
    seen=set(); enabled=[]; disabled=[]; unresolved=[]; states=0
    enabled_sources:dict[int,set[int]]={}
    cond_jp={0xC2,0xCA,0xD2,0xDA,0xE2,0xEA,0xF2,0xFA}
    cond_call={0xC4,0xCC,0xD4,0xDC,0xE4,0xEC,0xF4,0xFC}
    cond_ret={0xC0,0xC8,0xD0,0xD8,0xE0,0xE8,0xF0,0xF8}
    rst_ops={0xC7:0x00,0xCF:0x08,0xD7:0x10,0xDF:0x18,0xE7:0x20,0xEF:0x28,0xF7:0x30,0xFF:0x38}

    def do_return(pc:int, stack:tuple[int,...], iff:bool, source:int|None):
        if stack:
            work.append((stack[-1],stack[:-1],iff,source))
        else:
            if iff:
                enabled.append(pc)
                if source is not None: enabled_sources.setdefault(pc,set()).add(source)
            else:
                disabled.append(pc)

    while work and states < max_states:
        pc,stack,iff,source=work.pop(); key=(pc,stack,iff,source)
        if key in seen: continue
        seen.add(key); states += 1
        if not (0 <= pc < 0x10000) or not valid[pc]:
            unresolved.append(pc & 0xFFFF); continue
        op=mem[pc]; n=insn_len(mem,pc)
        if pc+n>0x10000 or any(not valid[x] for x in range(pc,min(pc+n,0x10000))):
            unresolved.append(pc); continue
        nxt=(pc+n)&0xFFFF

        if op==0xF3:  # DI
            work.append((nxt,stack,False,None)); continue
        if op==0xFB:  # EI; recognition delayed one instruction, but IFF1 becomes enabled
            work.append((nxt,stack,True,pc)); continue
        if op in (0xDD,0xFD):
            op2=mem[pc+1] if pc+1<0x10000 else 0
            if op2==0xE9:
                unresolved.append(pc); continue
            work.append((nxt,stack,iff,source)); continue
        if op==0xED:
            op2=mem[pc+1] if pc+1<0x10000 else 0
            if op2 in (0x45,0x4D,0x55,0x5D,0x65,0x6D,0x75,0x7D):
                do_return(pc,stack,iff,source); continue
            work.append((nxt,stack,iff,source)); continue
        if op==0xC9:
            do_return(pc,stack,iff,source); continue
        if op in cond_ret:
            do_return(pc,stack,iff,source)
            work.append((nxt,stack,iff,source)); continue
        if op==0x76:
            continue
        if op==0xE9:
            unresolved.append(pc); continue
        if op==0xC3 or op in cond_jp:
            t=mem[pc+1]|(mem[pc+2]<<8)
            if valid[t]: work.append((t,stack,iff,source))
            else: unresolved.append(pc)
            if op in cond_jp: work.append((nxt,stack,iff,source))
            continue
        if op==0x18 or op in (0x10,0x20,0x28,0x30,0x38):
            t=(pc+2+s8(mem[pc+1]))&0xFFFF
            if valid[t]: work.append((t,stack,iff,source))
            else: unresolved.append(pc)
            if op!=0x18: work.append((nxt,stack,iff,source))
            continue
        if op==0xCD or op in cond_call:
            t=mem[pc+1]|(mem[pc+2]<<8)
            if valid[t] and len(stack)<max_depth:
                work.append((t,stack+(nxt,),iff,source))
            else:
                unresolved.append(pc); work.append((nxt,stack,iff,source))
            if op in cond_call: work.append((nxt,stack,iff,source))
            continue
        if op in rst_ops:
            t=rst_ops[op]
            if valid[t] and len(stack)<max_depth:
                work.append((t,stack+(nxt,),iff,source))
            else:
                unresolved.append(pc); work.append((nxt,stack,iff,source))
            continue
        work.append((nxt,stack,iff,source))

    return EntryReturnState(sorted(set(enabled)),sorted(set(disabled)),sorted(set(unresolved)),
                            {k:sorted(v) for k,v in sorted(enabled_sources.items())},bool(work))


def find_z80dasm(explicit: str|None) -> Path|None:
    if explicit:
        p=Path(explicit).expanduser()
        return p if p.is_file() else None
    found=shutil.which("z80dasm")
    if found: return Path(found)
    here=Path(__file__).resolve().parent
    system=platform.system().lower(); machine=platform.machine().lower()
    candidates=[]
    if system=="linux" and machine in ("x86_64","amd64"):
        candidates.append(here/"bin/linux-x86_64/z80dasm")
    candidates += [here/"z80dasm", here/"bin/z80dasm"]
    for p in candidates:
        if p.is_file() and os.access(p,os.X_OK): return p
    return None


def run_z80dasm(z80: Path, binary: Path, origin: int, asm_out: Path) -> tuple[bool,str]:
    cmd=[str(z80),"-a","-l","-t","-g",hex(origin),"-o",str(asm_out),str(binary)]
    try:
        cp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    except Exception as exc:
        return False,str(exc)
    return cp.returncode==0,(cp.stderr or cp.stdout).strip()


def direct_memory_refs(mem: bytearray, pcs: Iterable[int]) -> list[tuple[int,int,str]]:
    refs=[]
    for pc in sorted(pcs):
        op=mem[pc]
        try:
            if op in (0x22,0x32): refs.append((pc,mem[pc+1]|mem[pc+2]<<8,"write"))
            elif op in (0x2A,0x3A): refs.append((pc,mem[pc+1]|mem[pc+2]<<8,"read"))
            elif op==0xED and pc+3<0x10000:
                op2=mem[pc+1]
                if op2 in (0x43,0x53,0x63,0x73): refs.append((pc,mem[pc+2]|mem[pc+3]<<8,"write"))
                elif op2 in (0x4B,0x5B,0x6B,0x7B): refs.append((pc,mem[pc+2]|mem[pc+3]<<8,"read"))
            elif op in (0xDD,0xFD) and pc+3<0x10000:
                op2=mem[pc+1]
                if op2==0x22: refs.append((pc,mem[pc+2]|mem[pc+3]<<8,"write"))
                elif op2==0x2A: refs.append((pc,mem[pc+2]|mem[pc+3]<<8,"read"))
        except IndexError: pass
    return refs


def port_refs(mem: bytearray, pcs: set[int]) -> list[tuple[int,int,str]]:
    refs=[]
    for pc in sorted(pcs):
        op=mem[pc]
        if op==0xD3 and pc+1<0x10000:
            refs.append((pc,mem[pc+1],"OUT"))
        elif op==0xDB and pc+1<0x10000:
            refs.append((pc,mem[pc+1],"IN"))
        # Strong constant-C pattern: LD C,n immediately followed by OUT(C),A/IN A,(C).
        elif op==0x0E and pc+3<0x10000 and (pc+2) in pcs and mem[pc+2]==0xED and mem[pc+3] in (0x79,0x78):
            refs.append((pc+2,mem[pc+1],"OUT(C)" if mem[pc+3]==0x79 else "IN(C)"))
        # LD BC,nn followed immediately by OUT(C),A/IN A,(C).
        elif op==0x01 and pc+4<0x10000 and (pc+3) in pcs and mem[pc+3]==0xED and mem[pc+4] in (0x79,0x78):
            refs.append((pc+3,mem[pc+1],"OUT(C)" if mem[pc+4]==0x79 else "IN(C)"))
    return refs


def classify_port(port:int)->str:
    if port in (0xA0,0xA1,0xA2): return "PSG"
    if port in (0x7C,0x7D): return "FM-PAC/YM2413"
    if port in (0xC0,0xC1): return "MSX-AUDIO/Y8950"
    if port in (0xC4,0xC5,0xC6,0xC7,0x7E,0x7F): return "MoonSound/OPL4"
    if port in (0xFC,0xFD,0xFE,0xFF): return "MSX memory mapper"
    if port==0xA8: return "primary slot register"
    if port in (0xAA,0xAB): return "PPI control (not automatically DAC)"
    if port in (0x98,0x99): return "VDP"
    return "other"


def page_name(addr:int)->str: return f"P{addr//0x4000} (${(addr//0x4000)*0x4000:04X}-${(addr//0x4000+1)*0x4000-1:04X})"


def declared_memory_pages(e:Engine)->list[dict[str,Any]]:
    rows=[]
    primary_lo=e.load; primary_hi=min(0x10000,e.load+e.page_size)
    for pi in range(4):
        lo=pi*0x4000; hi=lo+0x4000; roles=[]
        overlap=max(0,min(hi,primary_hi)-max(lo,primary_lo))
        if overlap: roles.append(f"engine:{overlap}B")
        if pi==2 and (e.flags&ENGINE_PAGE2_RUNTIME): roles.append("PAGE2_RUNTIME")
        if pi==3 and (e.flags&ENGINE_PAGE3_WORKRAM): roles.append("PAGE3_WORKRAM")
        if e.flags&ENGINE_DYNAMIC_PAGES and pi in (1,2): roles.append("DYNAMIC_PAGES")
        rows.append({"page":pi,"range":f"${lo:04X}-${hi-1:04X}","engine_bytes":overlap,"roles":roles})
    return rows


class Analyser:
    def __init__(self, pkg: KspPackage, z80dasm: Path|None, out_dir: Path|None, strict: bool=True, skip_z80: bool=False, deep_blockers: bool=False):
        self.pkg=pkg; self.z80=z80dasm; self.out_dir=out_dir; self.strict=strict; self.skip_z80=skip_z80; self.deep_blockers=deep_blockers

    def add(self, findings:list[Finding], severity:str, code:str, message:str, *evidence:str)->None:
        findings.append(Finding(severity,code,message,[x for x in evidence if x]))

    def virtual_memory(self, e:Engine, page:bytes)->tuple[bytearray,bytearray,list[str]]:
        mem=bytearray(0x10000); valid=bytearray(0x10000); notes=[]
        if e.load+len(page) <= 0x10000:
            mem[e.load:e.load+len(page)]=page; valid[e.load:e.load+len(page)]=b"\1"*len(page)
        else:
            n=max(0,0x10000-e.load); mem[e.load:]=page[:n]; valid[e.load:]=b"\1"*n; notes.append("primary engine image exceeds $FFFF")
        # TinyKSP semantics for non-dynamic PAGE2_RUNTIME: install the same materialized page at $8000.
        if (e.flags&ENGINE_PAGE2_RUNTIME) and not(e.flags&ENGINE_DYNAMIC_PAGES):
            if 0x8000+len(page)<=0x10000:
                mem[0x8000:0x8000+len(page)]=page; valid[0x8000:0x8000+len(page)]=b"\1"*len(page)
                notes.append(f"PAGE2_RUNTIME mirror: {len(page)//1024} KiB copied at $8000")
            else:
                notes.append("PAGE2_RUNTIME mirror would exceed Z80 address space")
        return mem,valid,notes

    def analyse_track(self, track_index:int, write_artifacts:bool=True)->dict[str,Any]:
        p=self.pkg; t=p.tracks[track_index]; pg=p.pages[t.page]; e=p.engines[pg.engine]; findings:list[Finding]=[]
        native_geom=(e.load==0x4000 and e.page_size==0x4000)
        if p.header.get("header_crc_ok") is False:
            self.add(findings,"BLOCKER","HEADER_CRC_MISMATCH","KSP header CRC does not match the file contents.")
        if p.header.get("index_crc_ok") is False:
            self.add(findings,"BLOCKER","INDEX_CRC_MISMATCH","KSP descriptor/string index CRC does not match the file contents.")
        if self.strict and not native_geom:
            self.add(findings,"BLOCKER","NON_NATIVE_ENGINE_GEOMETRY",
                     f"Engine uses load=${e.load:04X}, size=${e.page_size:04X}; strict KSP1PLAY native target expects $4000/$4000.",
                     "Hosted/oversized layouts can work in TinyKSP while colliding with the MSX player's own pages.")
        if e.load+e.page_size>0x10000:
            self.add(findings,"BLOCKER","ENGINE_OUTSIDE_Z80",f"Engine image ends at ${e.load+e.page_size:05X}, beyond $FFFF.")
        if e.flags&ENGINE_PAGE2_RUNTIME:
            if e.page_size!=0x4000:
                sev="BLOCKER" if e.page_size>0x4000 else "HIGH"
                self.add(findings,sev,"PAGE2_RUNTIME_BAD_GEOMETRY",
                         f"PAGE2_RUNTIME is paired with a {e.page_size//1024} KiB engine instead of 16 KiB.",
                         f"Runtime mirror range would be $8000-${0x8000+e.page_size-1:05X}.")
            if 0x8000+e.page_size>0x10000:
                self.add(findings,"BLOCKER","PAGE2_RUNTIME_COPY_OVERFLOW","PAGE2_RUNTIME copy at $8000 lies outside 64 KiB Z80 memory.")
        if e.hardware&(HW_SN76489|HW_GG_STEREO):
            self.add(findings,"BLOCKER","NON_MSX_SOUND_MODE","Engine declares SEGA/SN76489 hardware, not a native MSX sound target.")
        if e.init==NULL16 or e.play==NULL16:
            self.add(findings,"BLOCKER","MISSING_ENTRYPOINT",f"INIT=${e.init:04X} PLAY=${e.play:04X} is not a usable INIT/PLAY pair.")
        if self.skip_z80:
            if not findings:
                self.add(findings,"INFO","STRUCTURAL_NATIVE_OK","Fast structural pass found no native-MS​​X geometry blocker; run without --fast for code/chip analysis.")
            evidence={"analysis_mode":"structural-fast","z80dasm":{"available":bool(self.z80),"path":str(self.z80) if self.z80 else None,"ok":False,"skipped":True}}
            return self._result(track_index,e,t,pg,findings,None,None,evidence,[],[])
        if any(f.severity=="BLOCKER" for f in findings) and not self.deep_blockers:
            evidence={"analysis_mode":"structural-conclusive","z80dasm":{"available":bool(self.z80),"path":str(self.z80) if self.z80 else None,"ok":False,"skipped":True,"message":"skipped because a conclusive structural blocker was already found; use --deep-blockers to continue"}}
            return self._result(track_index,e,t,pg,findings,None,None,evidence,[],[])

        try: page=p.materialize_page(t.page)
        except Exception as exc:
            self.add(findings,"BLOCKER","PAGE_RECONSTRUCTION_FAILED",f"Track page cannot be reconstructed: {exc}")
            return self._result(track_index,e,t,pg,findings,None,None,None,{},[])
        mem,valid,notes=self.virtual_memory(e,page)
        init_r=reachable(mem,valid,[e.init]) if e.init!=NULL16 and valid[e.init] else Reachability(set(),[],[(e.init,e.init,"ENTRY")])
        play_r=reachable(mem,valid,[e.play]) if e.play!=NULL16 and valid[e.play] else Reachability(set(),[],[(e.play,e.play,"ENTRY")])
        if e.init!=NULL16 and not valid[e.init]: self.add(findings,"BLOCKER","INIT_NOT_RESIDENT",f"INIT ${e.init:04X} is outside the reconstructed resident image.")
        if e.play!=NULL16 and not valid[e.play]: self.add(findings,"BLOCKER","PLAY_NOT_RESIDENT",f"PLAY ${e.play:04X} is outside the reconstructed resident image.")

        def external_findings(label:str,r:Reachability)->None:
            low=[]; p3=[]; others=[]; abi=[]
            for pc,target,kind in r.external_targets:
                ev=f"${pc:04X}: {kind} -> ${target:04X}"
                # KSP ABI call tokens are deliberately outside the engine image.
                # D900/D904/D908 are the SCC slot-select A/B/restore tokens and
                # are relocated by KSP1PLAY before INIT. The per-engine gateway
                # is likewise a player-owned entrypoint, not missing engine code.
                if (target in (0xD900,0xD904,0xD908) and (e.hardware&(HW_SCC|HW_SCC_PLUS|HW_DUAL_SCC))) or (e.gateway not in (0,NULL16) and target==e.gateway):
                    abi.append(ev); continue
                if target<0x4000: low.append(ev)
                elif target>=0xC000 and (e.flags&ENGINE_PAGE3_WORKRAM): p3.append(ev)
                else: others.append(ev)
            if abi:
                self.add(findings,"INFO","KSP_ABI_CALLS",f"{label} uses recognized KSP player ABI token(s); these are expected external calls.",*abi[:8])
            if low:
                self.add(findings,"BLOCKER" if label=="PLAY" else "HIGH","LOW_MEMORY_DEPENDENCY",
                         f"{label} reaches code/calls below $4000, outside the native engine page.",*low[:8])
            if p3:
                self.add(findings,"SUSPICIOUS","PAGE3_RUNTIME_TARGET",
                         f"{label} targets PAGE3_WORKRAM code that static reconstruction cannot prove; verify INIT materializes it before use.",*p3[:8])
            if others:
                self.add(findings,"HIGH","EXTERNAL_CODE_TARGET",
                         f"{label} has direct control-flow targets outside reconstructed code.",*others[:8])
        external_findings("INIT",init_r); external_findings("PLAY",play_r)
        external_all=init_r.external_targets+play_r.external_targets
        abi_targets={target for _pc,target,_kind in external_all if target in (0xD900,0xD904,0xD908)}
        scc_slot_abi=bool(abi_targets & {0xD900,0xD904})
        if play_r.unresolved_indirect:
            self.add(findings,"SUSPICIOUS","INDIRECT_PLAY_FLOW",
                     f"PLAY contains {len(play_r.unresolved_indirect)} unresolved JP (HL/IX/IY) path(s); coverage is incomplete.",
                     *[f"${x:04X}" for x in play_r.unresolved_indirect[:8]])
        if init_r.unresolved_indirect:
            self.add(findings,"NOTICE","INDIRECT_INIT_FLOW",f"INIT contains {len(init_r.unresolved_indirect)} unresolved indirect jump(s).")

        all_reach=init_r.seen|play_r.seen
        refs=direct_memory_refs(mem,all_reach); prefs=port_refs(mem,all_reach)
        play_refs=direct_memory_refs(mem,play_r.seen); play_ports=port_refs(mem,play_r.seen)

        # IRQ/scheduler ownership signals.
        irq_writes=[(pc,a) for pc,a,k in refs if k=="write" and 0x0038<=a<=0x003A]
        if irq_writes:
            self.add(findings,"HIGH","IRQ_VECTOR_WRITE","Reachable code writes the Z80 interrupt vector around $0038; KSP1PLAY normally owns scheduling.",
                     *[f"${pc:04X} writes ${a:04X}" for pc,a in irq_writes[:8]])
        eis=[pc for pc in all_reach if mem[pc]==0xFB]
        epilogue=[]
        for pc in eis:
            if pc+1<0x10000 and mem[pc+1] in (0xC9,0xD9): epilogue.append(pc)
            elif pc+2<0x10000 and mem[pc+1]==0xD9 and mem[pc+2]==0xC9: epilogue.append(pc)
        # KSP1PLAY callback ABI: install_current_track enters with DI and the
        # gateway's first instruction after the engine returns is DI.  If the
        # *outer* INIT/PLAY callback itself returns with IFF1 set, a Z80 IRQ can
        # be accepted in the return window before KSP1PLAY restores its own
        # mapping/stack context.  Track CALL/RET context so EI in an internal
        # helper is not confused with the callback's real return state.
        init_ret=entry_return_interrupt_state(mem,valid,e.init) if e.init!=NULL16 and valid[e.init] else EntryReturnState([],[],[e.init],{})
        play_ret=entry_return_interrupt_state(mem,valid,e.play) if e.play!=NULL16 and valid[e.play] else EntryReturnState([],[],[e.play],{})
        fix_candidates=[]
        def report_return_irq(label:str, rs:EntryReturnState)->None:
            if not rs.enabled_returns: return
            only_enabled=bool(rs.enabled_returns) and not rs.disabled_returns and not rs.unresolved and not rs.truncated
            sev="BLOCKER" if only_enabled else "HIGH"
            code=f"{label}_RETURNS_INTERRUPTS_ENABLED"
            msg=(f"{label} can return to KSP1PLAY with interrupts enabled. "
                 "The MSX gateway restores player state only after the engine RET, so a VBlank IRQ may run in the engine mapping before the gateway's DI.")
            if only_enabled:
                msg += " Every statically resolved outer return path is interrupt-enabled."
            ev=[]
            causal=set()
            for pc in rs.enabled_returns[:8]:
                srcs=rs.enabled_sources.get(pc,[])
                causal.update(srcs)
                if srcs:
                    src_text=", ".join(f"${x:04X}" for x in srcs[:6])
                    ev.append(f"outer RET at ${pc:04X}; IFF1 enabled by reachable EI source(s) {src_text}")
                elif pc>0 and mem[pc-1]==0xFB:
                    ev.append(f"EI at ${pc-1:04X} -> outer RET at ${pc:04X}; IFF1 enabled on callback return")
                else:
                    ev.append(f"outer RET at ${pc:04X} with IFF1=enabled; enabling source unresolved")
            for src in sorted(causal):
                if 0 <= src < 0x10000 and valid[src] and mem[src]==0xFB:
                    fix_candidates.append({"kind":"irq_return_ei_to_di","callback":label,"pc":src,
                                           "reason":code,"confidence":"high" if only_enabled else "medium"})
            self.add(findings,sev,code,msg,*ev)
        report_return_irq("INIT",init_ret); report_return_irq("PLAY",play_ret)

        if epilogue and irq_writes:
            self.add(findings,"HIGH","SCHEDULER_EI_RISK","EI epilogue(s) coexist with interrupt-vector modification; this resembles a KSS-owned scheduler.",
                     *[f"EI at ${pc:04X}" for pc in epilogue[:8]])
        elif epilogue and not (init_ret.enabled_returns or play_ret.enabled_returns):
            self.add(findings,"NOTICE","EI_EPILOGUE_PRESENT","Reachable EI-before-return patterns exist only in internal/DI-restored paths; outer callback return-state analysis did not prove an enabled return.",
                     *[f"${pc:04X}" for pc in epilogue[:6]])

        # Mapper / slot / PPI / VDP activity from reachable code.
        mapper=[x for x in prefs if x[1] in (0xFC,0xFD,0xFE,0xFF)]
        if mapper:
            sev="HIGH" if not(e.flags&ENGINE_DYNAMIC_PAGES) else "NOTICE"
            self.add(findings,sev,"MAPPER_IO_REACHABLE",
                     "Reachable code writes/reads MSX mapper ports $FC-$FF." if sev=="HIGH" else "Mapper I/O is reachable and DYNAMIC_PAGES is declared; verify it goes through the KSP native gateway.",
                     *[f"${pc:04X}: {kind} ${port:02X}" for pc,port,kind in mapper[:8]])
        slot=[x for x in play_ports if x[1]==0xA8]
        if slot: self.add(findings,"HIGH","PLAY_SLOT_SWITCH","PLAY accesses primary slot register $A8; this can invalidate KSP1PLAY's mapped engine/player pages.",*[f"${pc:04X}: {kind}" for pc,_,kind in slot[:8]])
        ppi=[x for x in play_ports if x[1] in (0xAA,0xAB)]
        if ppi: self.add(findings,"SUSPICIOUS","PLAY_PPI_ACCESS","PLAY accesses PPI $AA/$AB. This may be keyboard/control logic; it is NOT classified as 1-bit DAC without timing proof.",*[f"${pc:04X}: {kind} ${port:02X}" for pc,port,kind in ppi[:8]])
        vdp=[x for x in play_ports if x[1] in (0x98,0x99)]
        if vdp: self.add(findings,"SUSPICIOUS","PLAY_VDP_ACCESS","PLAY accesses VDP ports $98/$99; this may conflict with the player UI/timing.",*[f"${pc:04X}: {kind} ${port:02X}" for pc,port,kind in vdp[:8]])

        # Direct SCC/bank-window stores. $9000 is ambiguous when page2 is RAM.
        direct_writes=[(pc,a) for pc,a,k in refs if k=="write"]
        scc_regs=[(pc,a) for pc,a in direct_writes if 0x9800<=a<=0x98FF]
        sccplus_regs=[(pc,a) for pc,a in direct_writes if 0xB800<=a<=0xB8FF]
        selectors=[(pc,a) for pc,a in direct_writes if a in (0x9000,0xB000,0xBFFE)]
        if selectors:
            if (e.flags&ENGINE_PAGE2_RUNTIME) and not(e.hardware&(HW_SCC|HW_SCC_PLUS|HW_DUAL_SCC)):
                self.add(findings,"NOTICE","PAGE2_9000_AMBIGUOUS","Writes to $9000/$B000 exist but PAGE2_RUNTIME is RAM and no SCC hardware is declared; do not treat this alone as SCC proof.",*[f"${pc:04X} -> ${a:04X}" for pc,a in selectors[:8]])
            elif not(e.flags&ENGINE_DYNAMIC_PAGES) and any(a in (0x9000,0xB000) for _,a in selectors) and not(scc_regs or sccplus_regs):
                self.add(findings,"HIGH","BANK_SELECTOR_REACHABLE","Reachable writes to common KSS/Konami bank selectors remain without clear SCC register use or DYNAMIC_PAGES proof.",*[f"${pc:04X} -> ${a:04X}" for pc,a in selectors[:8]])

        detected=set()
        for _,port,kind in prefs:
            if not kind.startswith("OUT"): continue
            if port in (0xA0,0xA1): detected.add("PSG")
            elif port in (0x7C,0x7D): detected.add("FM-PAC/YM2413")
            elif port in (0xC0,0xC1): detected.add("MSX-AUDIO/Y8950")
            elif port in (0xC4,0xC5,0xC6,0xC7,0x7E,0x7F): detected.add("MoonSound/OPL4")
        page2_is_ram=bool(e.flags&ENGINE_PAGE2_RUNTIME)
        if scc_regs and (not page2_is_ram or scc_slot_abi): detected.add("SCC")
        if sccplus_regs and (not page2_is_ram or scc_slot_abi): detected.add("SCC+")
        if page2_is_ram and (scc_regs or sccplus_regs) and not scc_slot_abi:
            if e.hardware&(HW_SCC|HW_SCC_PLUS|HW_DUAL_SCC):
                self.add(findings,"HIGH","SCC_PAGE2_RAM_AMBIGUITY",
                         "SCC is declared and writes exist in the SCC address range, but PAGE2_RUNTIME maps that range as RAM and no D900/D904 SCC-slot ABI call is reachable. The SCC declaration is likely a false positive.",
                         *[f"${pc:04X} writes ${a:04X}" for pc,a in (scc_regs+sccplus_regs)[:8]])
            else:
                self.add(findings,"NOTICE","PAGE2_SCC_RANGE_IS_RAM",
                         "Writes in $9800/$B800 ranges occur while PAGE2_RUNTIME is RAM; they are not counted as SCC proof.")
        declared=set(mask_names(e.hardware,HW_NAMES))
        needed={
            "PSG":HW_PSG,"FM-PAC/YM2413":HW_FMPAC,"MSX-AUDIO/Y8950":HW_Y8950,"MoonSound/OPL4":HW_OPL4,"SCC":HW_SCC|HW_DUAL_SCC|HW_SCC_PLUS,"SCC+":HW_SCC_PLUS
        }
        for name in sorted(detected):
            if not(e.hardware&needed[name]):
                self.add(findings,"HIGH","UNDECLARED_SOUND_HARDWARE",f"Reachable code appears to use {name}, but the engine hardware mask does not declare it.")
        for bit,name in HW_NAMES:
            if e.hardware&bit and name in ("PSG","FM-PAC/YM2413","MSX-AUDIO/Y8950","MoonSound/OPL4") and name not in detected:
                self.add(findings,"NOTICE","DECLARED_CHIP_NOT_PROVEN",f"{name} is declared, but no direct reachable register-write signature was proven statically (indirect writes may hide it).")
        if e.hardware&(HW_SCC|HW_SCC_PLUS|HW_DUAL_SCC) and not ({"SCC","SCC+"}&detected):
            sev="HIGH" if page2_is_ram and not scc_slot_abi else "NOTICE"
            self.add(findings,sev,"DECLARED_SCC_NOT_PROVEN",
                     "SCC-family hardware is declared, but the reachable code does not prove a valid SCC register window in the reconstructed runtime mapping.")

        # Direct self-modifying code evidence.
        code_bytes=set()
        for pc in all_reach:
            n=insn_len(mem,pc)
            code_bytes.update(range(pc,min(pc+n,0x10000)))
        sm=[(pc,a) for pc,a,k in refs if k=="write" and a in code_bytes]
        if sm: self.add(findings,"HIGH","SELF_MODIFYING_CODE","Reachable code directly writes into bytes classified as executable; static disassembly may become stale at runtime.",*[f"${pc:04X} -> ${a:04X}" for pc,a in sm[:8]])

        # z80dasm is a required evidence layer for deep analysis.
        artifacts=[]; z80_info={"available":bool(self.z80),"path":str(self.z80) if self.z80 else None,"ok":False,"skipped":self.skip_z80}
        if self.skip_z80:
            z80_info["message"]="external disassembly skipped by --fast; internal CFG analysis still ran"
        elif not self.z80:
            self.add(findings,"SUSPICIOUS","Z80DASM_UNAVAILABLE","z80dasm was not found; recursive decoder ran, but deep external disassembly evidence is missing.")
        elif write_artifacts and self.out_dir:
            base=self.out_dir/f"engine{e.index:02d}_track{track_index+1:03d}"
            self.out_dir.mkdir(parents=True,exist_ok=True)
            binpath=base.with_suffix(".bin"); asmpath=base.with_suffix(".asm")
            binpath.write_bytes(page); ok,msg=run_z80dasm(self.z80,binpath,e.load,asmpath); z80_info.update(ok=ok,message=msg,asm=str(asmpath),binary=str(binpath)); artifacts += [str(binpath),str(asmpath)] if ok else [str(binpath)]
            if not ok: self.add(findings,"SUSPICIOUS","Z80DASM_FAILED",f"z80dasm failed: {msg}")
        elif self.z80:
            with tempfile.TemporaryDirectory(prefix="ksp_analyse_") as td:
                bp=Path(td)/"page.bin"; ap=Path(td)/"page.asm"; bp.write_bytes(page); ok,msg=run_z80dasm(self.z80,bp,e.load,ap); z80_info.update(ok=ok,message=msg)
                if not ok: self.add(findings,"SUSPICIOUS","Z80DASM_FAILED",f"z80dasm failed: {msg}")

        page_stats=[]
        for pi in range(4):
            lo=pi*0x4000; hi=lo+0x4000
            installed=sum(1 for a in range(lo,hi) if valid[a])
            init_ins=sum(1 for a in init_r.seen if lo<=a<hi); play_ins=sum(1 for a in play_r.seen if lo<=a<hi)
            reads=sum(1 for _,a,k in refs if k=="read" and lo<=a<hi); writes=sum(1 for _,a,k in refs if k=="write" and lo<=a<hi)
            page_stats.append({"page":pi,"range":f"${lo:04X}-${hi-1:04X}","installed_bytes":installed,"init_instructions":init_ins,"play_instructions":play_ins,"direct_reads":reads,"direct_writes":writes})

        chip_usage:dict[str,list[str]]={}
        for pc,port,kind in prefs:
            if not kind.startswith("OUT"): continue
            cls=classify_port(port)
            if cls in ("PSG","FM-PAC/YM2413","MSX-AUDIO/Y8950","MoonSound/OPL4"):
                chip_usage.setdefault(cls,[]).append(f"${pc:04X} {kind} ${port:02X}")
        if "SCC" in detected:
            chip_usage["SCC"]=[f"${pc:04X} write ${a:04X}" for pc,a in scc_regs[:12]]
        if "SCC+" in detected:
            chip_usage["SCC+"]=[f"${pc:04X} write ${a:04X}" for pc,a in sccplus_regs[:12]]
        evidence={
            "analysis_mode":"deep",
            "init_reachable_instructions":len(init_r.seen),"play_reachable_instructions":len(play_r.seen),
            "unresolved_init_indirect":len(init_r.unresolved_indirect),"unresolved_play_indirect":len(play_r.unresolved_indirect),
            "init_outer_returns_irq_enabled":[f"${pc:04X}" for pc in init_ret.enabled_returns],
            "init_outer_returns_irq_disabled":[f"${pc:04X}" for pc in init_ret.disabled_returns],
            "play_outer_returns_irq_enabled":[f"${pc:04X}" for pc in play_ret.enabled_returns],
            "play_outer_returns_irq_disabled":[f"${pc:04X}" for pc in play_ret.disabled_returns],
            "init_irq_enable_sources":{f"${ret:04X}":[f"${src:04X}" for src in srcs] for ret,srcs in init_ret.enabled_sources.items()},
            "play_irq_enable_sources":{f"${ret:04X}":[f"${src:04X}" for src in srcs] for ret,srcs in play_ret.enabled_sources.items()},
            "fix_candidates":fix_candidates,
            "external_init_targets":[f"${pc:04X}->{target:04X} {kind}" for pc,target,kind in init_r.external_targets[:20]],
            "external_play_targets":[f"${pc:04X}->{target:04X} {kind}" for pc,target,kind in play_r.external_targets[:20]],
            "scc_slot_abi":scc_slot_abi,
            "scc_abi_targets":[f"${x:04X}" for x in sorted(abi_targets)],
            "ports":[{"pc":f"${pc:04X}","port":f"${port:02X}","op":kind,"class":classify_port(port)} for pc,port,kind in prefs[:200]],
            "memory_refs":[{"pc":f"${pc:04X}","address":f"${a:04X}","op":kind} for pc,a,kind in refs[:300]],
            "detected_hardware":sorted(detected),"chip_usage":chip_usage,"page_stats":page_stats,"mapping_notes":notes,"z80dasm":z80_info
        }
        if not findings: self.add(findings,"INFO","NO_STATIC_BLOCKER","No static KSP1PLAY blocker was found on the selected track. Runtime validation is still required.")
        return self._result(track_index,e,t,pg,findings,init_r,play_r,evidence,detected,artifacts)

    def _result(self,track_index:int,e:Engine,t:Track,pg:Page,findings:list[Finding],init_r:Reachability|None,play_r:Reachability|None,evidence:dict|None,detected:Iterable[str]|None,artifacts:list[str])->dict[str,Any]:
        maxsev=max((SEVERITY_ORDER.get(f.severity,0) for f in findings),default=0); confidence="high"
        if evidence and (evidence.get("unresolved_play_indirect",0) or (not evidence.get("z80dasm",{}).get("ok") and not evidence.get("z80dasm",{}).get("skipped"))): confidence="medium"
        return {
            "file":str(self.pkg.path),"title":self.pkg.meta.get("title") or self.pkg.meta.get("game") or self.pkg.path.stem,
            "track_index":track_index,"track_number":track_index+1,"track_title":self.pkg.string(t.title_off),"song_id":t.song,
            "engine":e.index,"page":t.page,"verdict":VERDICTS[maxsev],"severity_score":maxsev,"confidence":confidence,
            "engine_geometry":{"load":e.load,"page_size":e.page_size,"init":e.init,"play":e.play,"tick_hz":e.tick_hz},
            "declared_memory_pages":declared_memory_pages(e),
            "engine_flags":mask_names(e.flags,FLAG_NAMES),"engine_flags_raw":e.flags,
            "declared_hardware":mask_names(e.hardware,HW_NAMES),"hardware_raw":e.hardware,
            "page_encoding":pg.encoding,"page_compression":pg.compression,
            "detected_hardware":sorted(detected or []),"findings":[f.as_dict() for f in findings],"evidence":evidence or {},"artifacts":artifacts
        }



def selected_track_indices(pkg:KspPackage,args:argparse.Namespace)->list[int]:
    if args.track is not None:
        idx=args.track-1
        if idx<0 or idx>=len(pkg.tracks): raise ValueError(f"track {args.track} outside 1..{len(pkg.tracks)}")
        return [idx]
    if args.all_tracks:
        return list(range(len(pkg.tracks)))
    indices=[]; seen=set()
    for t in pkg.tracks:
        key=pkg.pages[t.page].engine if args.fast else (t.page,pkg.pages[t.page].engine)
        if key not in seen:
            seen.add(key); indices.append(t.index)
    return indices


def page_offset_for_runtime_pc(e:Engine, pc:int)->int|None:
    if e.load <= pc < e.load+e.page_size:
        return pc-e.load
    if (e.flags&ENGINE_PAGE2_RUNTIME) and not(e.flags&ENGINE_DYNAMIC_PAGES) and 0x8000 <= pc < 0x8000+e.page_size:
        return pc-0x8000
    return None


def _encode_page_payload(raw:bytes, compression:int)->tuple[bytes,int]:
    """Encode a logical page payload while preserving its compression contract."""
    if compression == COMP_NONE:
        return raw, COMP_NONE
    if compression == COMP_ZX0:
        if zx0_compress_best is None:
            raise ValueError("ZX0 compressor unavailable: " + ZX0_IMPORT_ERROR)
        packed,_mode = zx0_compress_best(raw, "auto")
        # Do not silently change the descriptor's compression kind just because
        # a tiny sparse stream happens to compress larger than its raw form.
        return packed, COMP_ZX0
    raise ValueError(f"profile-preserving repair does not support page compression id {compression}")


def _decode_sparse_records(raw:bytes, page_size:int)->list[tuple[int,bytes]]:
    records=[]; cur=0; prev=0
    while cur < len(raw):
        if cur+4 > len(raw):
            raise ValueError("truncated sparse page record")
        dest,count=u16(raw,cur),u16(raw,cur+2); cur+=4
        if not count or dest < prev or dest+count > page_size or cur+count > len(raw):
            raise ValueError("invalid sparse page record")
        records.append((dest,bytes(raw[cur:cur+count])))
        cur += count; prev=dest+count
    return records


def _serialize_sparse_records(records:list[tuple[int,bytes]], page_size:int)->bytes:
    out=bytearray(); prev=0
    for dest,data in sorted(records,key=lambda x:x[0]):
        if not data or dest < prev or dest+len(data) > page_size or len(data)>0xFFFF:
            raise ValueError("invalid sparse page record after repair")
        out += struct.pack("<HH",dest,len(data)); out += data
        prev=dest+len(data)
    return bytes(out)


def _patch_sparse_payload(raw:bytes, page_size:int, original_page:bytes, patched_page:bytes)->bytes:
    """Patch a SPARSE stream without materialising it as PAGE_COMPLETE.

    Existing records are edited in-place logically. Changed bytes that were
    previously inherited from the engine template are inserted as minimal new
    sparse records. Adjacent records are coalesced, preserving the same final
    reconstructed page while keeping the KSP page profile sparse.
    """
    if len(original_page)!=page_size or len(patched_page)!=page_size:
        raise ValueError("sparse repair page-size mismatch")
    changed=[i for i,(a,b) in enumerate(zip(original_page,patched_page)) if a!=b]
    if not changed:
        return raw
    # Build an overlay map from the original sparse records, then add exactly
    # the changed bytes. Re-serialise into contiguous runs.
    overlay={}
    for dest,data in _decode_sparse_records(raw,page_size):
        for j,val in enumerate(data): overlay[dest+j]=val
    for off in changed: overlay[off]=patched_page[off]
    items=sorted(overlay.items())
    records=[]
    if items:
        run_start=items[0][0]; run=bytearray([items[0][1]]); last=run_start
        for off,val in items[1:]:
            if off==last+1 and len(run)<0xFFFF:
                run.append(val)
            else:
                records.append((run_start,bytes(run)))
                run_start=off; run=bytearray([val])
            last=off
        records.append((run_start,bytes(run)))
    return _serialize_sparse_records(records,page_size)


def rebuild_ksp_preserving_page_profiles(pkg:KspPackage, patched_pages:dict[int,bytes])->tuple[bytes,list[dict[str,Any]]]:
    """Rebuild patched pages without changing their KSP runtime profile.

    Only SPARSE and COMPLETE page encodings are currently auto-repairable.
    PBM1/RMP1/HPOL are deliberately rejected rather than being flattened to a
    COMPLETE page, because that can alter KSP1PLAY backend/profile selection.
    Payloads are appended so existing offsets never move; only the selected
    page descriptor payload fields and CRC are updated.
    """
    b=bytearray(pkg.data); h=pkg.header; changes=[]
    for page_index,patched in sorted(patched_pages.items()):
        if not 0 <= page_index < len(pkg.pages): raise ValueError("patched page outside table")
        p=pkg.pages[page_index]; e=pkg.engines[p.engine]
        original=pkg.materialize_page(page_index)
        if len(patched)!=e.page_size: raise ValueError("patched page size differs from engine page size")
        if p.encoding == PAGE_SPARSE:
            logical=pkg.decode_object(pkg.data[p.offset:p.offset+p.packed],p.compression,p.unpacked)
            new_raw=_patch_sparse_payload(logical,e.page_size,original,patched)
        elif p.encoding == PAGE_COMPLETE:
            new_raw=bytes(patched)
        else:
            raise ValueError(f"page {page_index}: profile-preserving repair not implemented for encoding {p.encoding}; refusing PAGE_COMPLETE conversion")
        packed,comp=_encode_page_payload(new_raw,p.compression)
        if comp != p.compression:
            raise ValueError(f"page {page_index}: repair changed compression profile")
        payload_off=len(b); b.extend(packed)
        d=h["page_off"]+page_index*h["page_stride"]
        # Encoding, compression, flags and engine reference remain byte-for-byte.
        before_profile=bytes(b[d:d+8])
        struct.pack_into("<IIII",b,d+8,payload_off,len(packed),len(new_raw),crc32(bytes(patched)))
        after_profile=bytes(b[d:d+8])
        if before_profile != after_profile:
            raise ValueError(f"page {page_index}: repair mutated page profile descriptor")
        changes.append({
            "page":page_index,"encoding_before":p.encoding,"encoding_after":p.encoding,
            "compression_before":p.compression,"compression_after":p.compression,
            "flags_before":p.flags,"flags_after":p.flags,"profile_preserved":True,
            "old_packed":p.packed,"new_packed":len(packed),"old_unpacked":p.unpacked,"new_unpacked":len(new_raw),
        })
    _recalculate_ksp_crcs_and_size(b,h)
    # Hard postcondition: parsing must reconstruct exactly the requested pages
    # and all untouched engine/profile fields must still match.
    rebuilt=KspPackage(pkg.path,bytes(b))
    for page_index,patched in patched_pages.items():
        if rebuilt.materialize_page(page_index)!=bytes(patched):
            raise ValueError(f"page {page_index}: rebuilt page does not match repaired image")
        a,bp=pkg.pages[page_index],rebuilt.pages[page_index]
        if (a.engine,a.encoding,a.compression,a.flags)!=(bp.engine,bp.encoding,bp.compression,bp.flags):
            raise ValueError(f"page {page_index}: rebuilt package changed runtime profile")
    return bytes(b),changes

def _high_problem_count(summary:dict[str,Any])->int:
    return sum(1 for f in summary.get("top_findings",[]) if SEVERITY_ORDER.get(f.get("severity","INFO"),0)>=3)


def _recalculate_ksp_crcs_and_size(b:bytearray, h:dict[str,Any])->None:
    """Refresh file_size plus KSP header/index CRCs after descriptor edits."""
    struct.pack_into("<I",b,12,len(b))
    if h.get("index_crc"):
        eo,ec,es=h["engine_off"],h["engine_count"],h["engine_stride"]
        po,pc,ps=h["page_off"],h["page_count"],h["page_stride"]
        to,tc,ts=h["track_off"],h["track_count"],h["track_stride"]
        ro,rc,rs=h["resource_off"],h["resource_count"],h["resource_stride"]
        so,ss=h["string_off"],h["string_size"]
        index_bytes=(bytes(b[eo:eo+ec*es])+bytes(b[po:po+pc*ps])+bytes(b[to:to+tc*ts])+
                     bytes(b[ro:ro+rc*rs])+bytes(b[so:so+ss]))
        struct.pack_into("<I",b,68,crc32(index_bytes))
    if h.get("header_crc"):
        struct.pack_into("<I",b,64,0)
        hc=bytearray(b[:h["header_size"]]); hc[64:68]=b"\0\0\0\0"
        struct.pack_into("<I",b,64,crc32(hc))


def _hardware_text(mask:int)->str:
    names=[]
    for bit,name in HW_NAMES:
        if mask & bit:
            # META historically uses the shorter spellings.
            names.append({"FM-PAC/YM2413":"FM-PAC","MSX-AUDIO/Y8950":"Y8950",
                          "MoonSound/OPL4":"OPL4"}.get(name,name))
    known=0
    for bit,_ in HW_NAMES: known |= bit
    if mask & ~known: names.append(f"unknown(0x{mask & ~known:X})")
    return " + ".join(names) if names else "None"


def _update_meta_lines(raw:bytes, updates:dict[str,str])->bytes:
    """Update selected key=value lines while preserving all other META content."""
    text=raw.decode("utf-8","replace")
    newline="\r\n" if "\r\n" in text else "\n"
    trailing=text.endswith("\n") or text.endswith("\r")
    lines=text.replace("\r\n","\n").replace("\r","\n").split("\n")
    if lines and lines[-1]=="": lines=lines[:-1]
    remaining=dict(updates); out=[]
    for line in lines:
        if "=" in line:
            key,_=line.split("=",1); k=key.strip()
            if k in remaining:
                out.append(f"{key}={remaining.pop(k)}"); continue
        out.append(line)
    for k,v in remaining.items(): out.append(f"{k}={v}")
    result=newline.join(out)
    if trailing or out: result += newline
    return result.encode("utf-8")


def _hardware_audit_indices(pkg:KspPackage)->list[int]:
    """One representative track for every referenced physical page/engine.

    The current static CFG does not constant-propagate song ids, so re-running
    every logical track that shares an identical physical page adds no coverage.
    Hardware removal still requires every referenced physical page to be deep
    and fully resolved before it is considered safe.
    """
    result=[]; seen=set()
    for t in pkg.tracks:
        key=(t.page,pkg.pages[t.page].engine)
        if key not in seen:
            seen.add(key); result.append(t.index)
    return result


def _deep_hardware_audit(pkg:KspPackage, z80:Path|None, args:argparse.Namespace)->list[dict[str,Any]]:
    analyser=Analyser(pkg,z80,None,strict=not args.relaxed,skip_z80=False,deep_blockers=True)
    return [analyser.analyse_track(i,write_artifacts=False) for i in _hardware_audit_indices(pkg)]


def normalize_output_hardware(pkg:KspPackage, z80:Path|None, args:argparse.Namespace)->tuple[KspPackage,dict[str,Any]]:
    """Conservatively normalize engine hardware declarations for emitted KSPs.

    Directly proven chip usage is added when absent.  v0.1.3 only *removes*
    SCC-family declarations, and only when every referenced physical page for
    that engine has complete deep CFG coverage, no valid SCC ABI/register use,
    and no control-flow finding that would hide an SCC path.  This is intended
    to repair false SCC declarations such as Q-Bert without guessing on opaque
    drivers.
    """
    audit=_deep_hardware_audit(pkg,z80,args)
    by_engine:dict[int,list[dict[str,Any]]]={}
    for r in audit: by_engine.setdefault(int(r["engine"]),[]).append(r)
    masks={e.index:e.hardware for e in pkg.engines}
    corrections=[]
    detected_to_bit={
        "PSG":HW_PSG,"FM-PAC/YM2413":HW_FMPAC,"MSX-AUDIO/Y8950":HW_Y8950,
        "MoonSound/OPL4":HW_OPL4,"SCC":HW_SCC,"SCC+":HW_SCC_PLUS,
    }
    scc_bits=HW_SCC|HW_SCC_PLUS|HW_DUAL_SCC
    incomplete_codes={"INDIRECT_PLAY_FLOW","INDIRECT_INIT_FLOW","LOW_MEMORY_DEPENDENCY",
                      "EXTERNAL_CODE_TARGET","PAGE3_RUNTIME_TARGET","SELF_MODIFYING_CODE"}
    for e in pkg.engines:
        rs=by_engine.get(e.index,[]); old=e.hardware; new=old
        detected=set()
        for r in rs: detected.update(r.get("detected_hardware",[]))
        for name in detected:
            bit=detected_to_bit.get(name)
            if bit: new |= bit
        # Preserve the exact SCC-family declaration whenever SCC activity was
        # observed.  Only absence can cause a downgrade, never SCC<->SCC+ guesses.
        if old & scc_bits and not ({"SCC","SCC+"}&detected) and rs:
            complete=True; reasons=[]
            for r in rs:
                ev=r.get("evidence",{})
                codes={f.get("code") for f in r.get("findings",[])}
                if ev.get("analysis_mode")!="deep": complete=False; reasons.append("not deep")
                if not ev.get("z80dasm",{}).get("ok"):
                    complete=False; reasons.append("z80dasm evidence unavailable")
                if r.get("confidence")!="high":
                    complete=False; reasons.append("analysis confidence is not high")
                if ev.get("unresolved_init_indirect",0) or ev.get("unresolved_play_indirect",0):
                    complete=False; reasons.append("unresolved indirect flow")
                if ev.get("scc_slot_abi"):
                    complete=False; reasons.append("SCC slot ABI reachable")
                if codes & incomplete_codes:
                    complete=False; reasons.append("incomplete/dynamic control flow")
            if complete:
                new &= ~scc_bits
                reasons=["all referenced physical pages have resolved deep CFG", "no SCC/SCC+ register window proven", "no D900/D904 SCC-slot ABI reachable"]
            else:
                reasons=list(dict.fromkeys(reasons)) or ["SCC absence not proven"]
        else:
            reasons=[]
        if new != old:
            corrections.append({"engine":e.index,"old_mask":old,"new_mask":new,
                                "old":mask_names(old,HW_NAMES),"new":mask_names(new,HW_NAMES),
                                "reason":"; ".join(reasons) if reasons else "reachable chip I/O requires hardware bit(s)"})
            masks[e.index]=new

    b=bytearray(pkg.data); h=pkg.header
    for e in pkg.engines:
        d=h["engine_off"]+e.index*h["engine_stride"]
        struct.pack_into("<I",b,d+4,masks[e.index])
    union=0
    for m in masks.values(): union |= m
    meta_update=None
    meta_index=None
    if pkg.resources:
        mr=h.get("meta_resource",NULL16)
        if isinstance(mr,int) and 0 <= mr < len(pkg.resources) and pkg.resources[mr].kind=="META":
            meta_index=mr
        else:
            meta_index=next((r.index for r in pkg.resources if r.kind=="META"),None)
    if meta_index is not None and corrections:
        old_meta=pkg.logical_resource(meta_index)
        new_meta=_update_meta_lines(old_meta,{"target_hardware":_hardware_text(union)})
        if new_meta != old_meta:
            off=len(b); b.extend(new_meta)
            d=h["resource_off"]+meta_index*h["resource_stride"]
            b[d+6]=COMP_NONE
            struct.pack_into("<IIII",b,d+8,off,len(new_meta),len(new_meta),crc32(new_meta))
            meta_update={"resource":meta_index,"target_hardware":_hardware_text(union),"old_bytes":len(old_meta),"new_bytes":len(new_meta)}
    _recalculate_ksp_crcs_and_size(b,h)
    out=KspPackage(pkg.path,bytes(b))
    info={"audit_tracks":[r["track_number"] for r in audit],"corrections":corrections,
          "meta_update":meta_update,"final_union_mask":union,"final_target_hardware":_hardware_text(union)}
    return out,info


def build_test_outputs(original_path:Path, candidate_pkg:KspPackage, z80:Path|None,
                       args:argparse.Namespace)->tuple[KspPackage,list[dict[str,Any]],dict[str,Any],dict[str,Any]]:
    """Write the repaired/normalized KSP and, when possible, latest-player DSK."""
    tool_dir=Path(__file__).resolve().parent
    ksp_dir=tool_dir/"ksp"; dsk_dir=tool_dir/"dsk"
    ksp_dir.mkdir(parents=True,exist_ok=True); dsk_dir.mkdir(parents=True,exist_ok=True)

    normalized,hw_info=normalize_output_hardware(candidate_pkg,z80,args)
    ksp_path=ksp_dir/(original_path.stem+".ksp")
    ksp_path.write_bytes(normalized.data)
    # Re-open from the emitted file, not just the in-memory bytes.  This catches
    # write/truncation issues and makes the final report describe the artifact.
    emitted=KspPackage(ksp_path)
    analyser=Analyser(emitted,z80,None,strict=not args.relaxed,skip_z80=False,deep_blockers=args.deep_blockers)
    final_indices=selected_track_indices(emitted,args)
    final_results=[analyser.analyse_track(i,write_artifacts=False) for i in final_indices]
    final_summary=aggregate(final_results)
    info:dict[str,Any]={
        "requested":True,"ksp":str(ksp_path),"ksp_bytes":len(emitted.data),
        "hardware":hw_info,"final_summary":final_summary,"dsk":None,"dsk_error":None,
        "required_player_core":EXPECTED_PLAYER_CORE,"required_builder_baseline":EXPECTED_BUILDER,
    }
    try:
        explicit=Path(args.player_template).expanduser() if args.player_template else None
        template_raw,template_source=locate_latest_template(tool_dir,explicit)
        title=emitted.meta.get("title") or emitted.meta.get("game") or original_path.stem
        dsk_path=dsk_dir/(original_path.stem+".dsk")
        dsk_info=build_single_ksp_disk(template_raw,emitted.data,ksp_path.name,title,dsk_path)
        dsk_info["template_source"]=template_source
        info["dsk"]=dsk_info
    except Exception as exc:
        info["dsk_error"]=str(exc)
    return emitted,final_results,final_summary,info


def try_fix_in_memory(pkg:KspPackage, indices:list[int], original_results:list[dict[str,Any]],
                      z80:Path|None, out_dir:Path|None, args:argparse.Namespace)->tuple[dict[str,Any],KspPackage|None]:
    """Apply evidence-backed candidate repairs to an in-memory KSP and reanalyse.

    v0.1.4 deliberately has one automatic code repair family: causal EI -> DI
    for INIT/PLAY outer returns that are proven to leave IFF1 enabled. The
    framework is intentionally generic so future fixers can be added without
    conflating detection and repair.
    """
    before=aggregate(original_results)
    current_pkg=pkg; current_results=original_results; current_summary=before
    applied=[]; passes=[]; max_passes=4
    for pass_no in range(1,max_passes+1):
        patched_pages:dict[int,bytearray]={}
        proposed=[]; seen_physical=set()
        for r in current_results:
            ti=r["track_index"]; t=current_pkg.tracks[ti]; pg=current_pkg.pages[t.page]; e=current_pkg.engines[pg.engine]
            for c in r.get("evidence",{}).get("fix_candidates",[]):
                if c.get("kind")!="irq_return_ei_to_di": continue
                pc=int(c["pc"]); off=page_offset_for_runtime_pc(e,pc)
                if off is None:
                    proposed.append({**c,"track":ti+1,"page":t.page,"status":"SKIPPED","detail":"EI source is outside patchable resident/page2 image"}); continue
                key=(t.page,off)
                if key in seen_physical: continue
                seen_physical.add(key)
                if t.page not in patched_pages: patched_pages[t.page]=bytearray(current_pkg.materialize_page(t.page))
                page=patched_pages[t.page]
                if not (0 <= off < len(page)) or page[off]!=0xFB:
                    proposed.append({**c,"track":ti+1,"page":t.page,"offset":off,"status":"SKIPPED","detail":"candidate byte is no longer EI ($FB)"}); continue
                old=page[off]; page[off]=0xF3
                rec={"kind":c["kind"],"track":ti+1,"engine":e.index,"page":t.page,"callback":c.get("callback"),
                     "pc":f"${pc:04X}","page_offset":f"${off:04X}","old":f"${old:02X} EI","new":"$F3 DI",
                     "reason":c.get("reason"),"confidence":c.get("confidence","medium"),"status":"APPLIED"}
                proposed.append(rec)
        if not patched_pages:
            if proposed: passes.append({"pass":pass_no,"patches":proposed,"result":"NO_APPLICABLE_PATCH"})
            break
        try:
            candidate_bytes,profile_changes=rebuild_ksp_preserving_page_profiles(current_pkg,{k:bytes(v) for k,v in patched_pages.items()})
        except Exception as exc:
            for rec in proposed:
                if rec.get("status")=="APPLIED":
                    rec["status"]="SKIPPED"; rec["detail"]="profile-preserving writer refused repair: " + str(exc)
            passes.append({"pass":pass_no,"patches":proposed,"result":"REJECTED_PROFILE_MUTATION","detail":str(exc)})
            break
        candidate_pkg=KspPackage(pkg.path,candidate_bytes)
        candidate_out=(out_dir/"try_fix") if out_dir else None
        analyser=Analyser(candidate_pkg,z80,candidate_out,strict=not args.relaxed,skip_z80=False,deep_blockers=args.deep_blockers)
        candidate_results=[analyser.analyse_track(i,write_artifacts=bool(candidate_out)) for i in indices]
        candidate_summary=aggregate(candidate_results)
        passes.append({"pass":pass_no,"patches":proposed,"profile_changes":profile_changes,"profile_preserved":all(x.get("profile_preserved") for x in profile_changes),
                       "before_verdict":current_summary["verdict"],
                       "after_verdict":candidate_summary["verdict"],"after_summary":candidate_summary})
        applied.extend(x for x in proposed if x.get("status")=="APPLIED")
        # Never keep a repair pass that increases the global static severity.
        if candidate_summary["severity_score"] > current_summary["severity_score"]:
            passes[-1]["result"]="REJECTED_REGRESSION"; break
        passes[-1]["result"]="ACCEPTED"
        current_pkg,current_results,current_summary=candidate_pkg,candidate_results,candidate_summary
    before_codes={f["code"] for r in original_results for f in r.get("findings",[]) if SEVERITY_ORDER.get(f.get("severity","INFO"),0)>=3}
    after_codes={f["code"] for r in current_results for f in r.get("findings",[]) if SEVERITY_ORDER.get(f.get("severity","INFO"),0)>=3}
    fixed_codes=sorted(before_codes-after_codes)
    if not applied:
        status="NO_FIX_AVAILABLE"
    elif current_summary["severity_score"] < before["severity_score"]:
        status="IMPROVED"
    elif fixed_codes:
        status="PARTIAL"
    else:
        status="NO_CHANGE"
    repair={"mode":"in-memory","experimental":True,"original_file_modified":False,"status":status,
            "before":before,"after":current_summary,"fixed_high_or_blocker_codes":fixed_codes,
            "applied_patch_count":len(applied),"applied_patches":applied,"passes":passes,"tracks_after":current_results,
            "note":"Candidate is reparsed and reanalysed after each accepted pass. Static improvement is not proof of correct audio/runtime behaviour."}
    return repair,(current_pkg if applied else None)

def aggregate(results:list[dict[str,Any]])->dict[str,Any]:
    if not results: return {"verdict":"BLOCKER","confidence":"low","top_findings":[]}
    score=max(r["severity_score"] for r in results); confidence="high" if all(r["confidence"]=="high" for r in results) else "medium"
    top=[]; seen=set()
    for r in results:
        for f in r["findings"]:
            key=(f["severity"],f["code"],f["message"])
            if key not in seen and SEVERITY_ORDER[f["severity"]]>=max(2,score-1): seen.add(key); top.append(f)
    top.sort(key=lambda f:(-SEVERITY_ORDER[f["severity"]],f["code"]))
    return {"verdict":VERDICTS[score],"severity_score":score,"confidence":confidence,"top_findings":top[:12]}


def render_text(pkg:KspPackage, results:list[dict[str,Any]], summary:dict[str,Any], repair:dict[str,Any]|None=None, build:dict[str,Any]|None=None)->str:
    title=pkg.meta.get("title") or pkg.meta.get("game") or pkg.path.stem
    lines=[f"KSP ANALYSE v{VERSION}",f"File: {pkg.path.name}",f"Title: {title}",f"KSP: 1.{pkg.header['minor']:02d} | engines={len(pkg.engines)} pages={len(pkg.pages)} tracks={len(pkg.tracks)} resources={len(pkg.resources)}",
           f"Verdict: {summary['verdict']} (confidence: {summary['confidence']})"]
    meta_bits=[]
    for key in ("converter","converter_version","native_profile","source_format","source_hardware","target_hardware"):
        if pkg.meta.get(key): meta_bits.append(f"{key}={pkg.meta[key]}")
    if meta_bits: lines += ["Metadata: " + " | ".join(meta_bits)]
    lines += ["","Engine overview:"]
    for e in pkg.engines:
        lines.append(f"  E{e.index}: load=${e.load:04X} size=${e.page_size:04X} INIT=${e.init:04X} PLAY=${e.play:04X} tick={e.tick_hz}Hz")
        lines.append(f"      flags: {', '.join(mask_names(e.flags,FLAG_NAMES)) or 'none'}")
        lines.append(f"      hw:    {', '.join(mask_names(e.hardware,HW_NAMES)) or 'none'}")
        memparts=[]
        for mp in declared_memory_pages(e):
            if mp["roles"]: memparts.append(f"P{mp['page']}="+"+".join(mp["roles"]))
        lines.append(f"      mem:   {'; '.join(memparts) if memparts else 'no resident span'}")
    for r in results:
        lines += ["",f"Track {r['track_number']:03d}: {r['track_title'] or '(untitled)'} | song={r['song_id']} | E{r['engine']} P{r['page']}",
                  f"  Verdict: {r['verdict']} (confidence: {r['confidence']})"]
        ev=r.get("evidence",{})
        if ev:
            mode=ev.get("analysis_mode","deep")
            if mode.startswith("structural"):
                lines.append(f"  Analysis mode: {mode} (use --deep-blockers for code analysis of blocked layouts)")
            else:
                lines.append(f"  Reachable: INIT {ev.get('init_reachable_instructions',0)} insns, PLAY {ev.get('play_reachable_instructions',0)} insns; unresolved PLAY jumps={ev.get('unresolved_play_indirect',0)}")
                det=ev.get("detected_hardware",[]); lines.append(f"  Detected chip I/O: {', '.join(det) if det else 'none proven directly'}")
                for chip,hits in ev.get("chip_usage",{}).items():
                    if hits: lines.append(f"    {chip}: " + "; ".join(hits[:4]))
                lines.append("  Memory pages:")
                for ps in ev.get("page_stats",[]):
                    lines.append(f"    P{ps['page']} {ps['range']}: installed={ps['installed_bytes']:5d}  INIT-code={ps['init_instructions']:4d}  PLAY-code={ps['play_instructions']:4d}  refs R/W={ps['direct_reads']}/{ps['direct_writes']}")
        for f in r["findings"]:
            if f["severity"]=="INFO" and len(r["findings"])>1: continue
            lines.append(f"  [{f['severity']}] {f['code']}: {f['message']}")
            for x in f.get("evidence",[])[:8]: lines.append(f"      - {x}")
    if summary.get("top_findings"):
        lines += ["","Why this overall verdict:"]
        for f in summary["top_findings"][:8]: lines.append(f"  [{f['severity']}] {f['code']}: {f['message']}")
    if repair is not None:
        lines += ["","TRY-FIX (experimental; original file is unchanged):",
                  f"  Status: {repair['status']} | {repair['before']['verdict']} -> {repair['after']['verdict']} | patches={repair['applied_patch_count']}"]
        for x in repair.get("applied_patches",[])[:16]:
            lines.append(f"  [PATCH] track {x['track']} page {x['page']} {x.get('callback','?')}: {x['pc']} {x['old']} -> {x['new']} ({x['reason']})")
        profile_changes=[]
        for rp in repair.get("passes",[]): profile_changes.extend(rp.get("profile_changes",[]))
        if profile_changes:
            enc_names={PAGE_SPARSE:"SPARSE",PAGE_COMPLETE:"COMPLETE",PAGE_PBM1:"PBM1",PAGE_RMP1:"RMP1",PAGE_HPOL:"HPOL"}
            for pc in profile_changes[:16]:
                lines.append(f"  [PROFILE] page {pc['page']}: {enc_names.get(pc['encoding_before'],pc['encoding_before'])}/{pc['compression_before']} preserved; sparse/complete payload {pc['old_unpacked']} -> {pc['new_unpacked']} bytes")
        if repair.get("fixed_high_or_blocker_codes"):
            lines.append("  Cleared HIGH/BLOCKER codes: " + ", ".join(repair["fixed_high_or_blocker_codes"]))
        remain=[f for f in repair.get("after",{}).get("top_findings",[]) if SEVERITY_ORDER.get(f.get("severity","INFO"),0)>=2]
        if remain:
            lines.append("  Remaining candidate issues after re-analysis:")
            for f in remain[:8]: lines.append(f"    [{f['severity']}] {f['code']}: {f['message']}")
        else:
            lines.append("  Re-analysis found no SUSPICIOUS/HIGH/BLOCKER issue in the selected track set.")
        lines.append("  The original input KSP is never overwritten; --build-disk may write the accepted candidate to ksp/.")
    if build is not None:
        lines += ["","BUILD OUTPUT:",f"  KSP: {build.get('ksp')}"]
        hw=build.get("hardware",{})
        for c in hw.get("corrections",[]):
            lines.append(f"  [HW FIX] E{c['engine']}: {', '.join(c['old']) or 'none'} -> {', '.join(c['new']) or 'none'}")
            lines.append(f"           {c['reason']}")
        if hw.get("meta_update"):
            lines.append(f"  META target_hardware -> {hw.get('final_target_hardware')}")
        fs=build.get("final_summary",{})
        if fs: lines.append(f"  Final emitted-KSP verdict: {fs.get('verdict')} (confidence: {fs.get('confidence')})")
        if build.get("dsk"):
            d=build["dsk"]
            lines.append(f"  DSK: {d.get('output')}")
            lines.append(f"  Player: KSP1PLAY core {d.get('player_core')} / DSK builder baseline {d.get('builder_baseline')}")
            lines.append(f"  Template: {d.get('template_source','')}")
        else:
            lines.append(f"  DSK NOT BUILT: {build.get('dsk_error')}")
    lines += ["","Interpretation:","  LIKELY SAFE = no static native-MS​​X blocker found; not a runtime guarantee.","  SUSPICIOUS  = inspect flagged paths; static coverage is incomplete or unusual.","  HIGH RISK   = likely KSP1PLAY conflict; runtime tracing strongly recommended.","  BLOCKER     = violates the strict native KSP1PLAY/MSX memory/runtime contract."]
    return "\n".join(lines)+"\n"


def analyse_file(path:Path,args:argparse.Namespace)->tuple[KspPackage,list[dict[str,Any]],dict[str,Any],dict[str,Any]|None,KspPackage]:
    pkg=KspPackage(path); z80=find_z80dasm(args.z80dasm)
    out_dir=None
    if args.report_dir:
        out_dir=Path(args.report_dir)/safe_name(path.stem)
    analyser=Analyser(pkg,z80,out_dir,strict=not args.relaxed,skip_z80=args.fast,deep_blockers=args.deep_blockers)
    indices=selected_track_indices(pkg,args)
    results=[analyser.analyse_track(i,write_artifacts=bool(args.report_dir)) for i in indices]
    summary=aggregate(results); repair=None; candidate=pkg
    if args.try_fix:
        repair,fixed_candidate=try_fix_in_memory(pkg,indices,results,z80,out_dir,args)
        if fixed_candidate is not None: candidate=fixed_candidate
    return pkg,results,summary,repair,candidate


def safe_name(s:str)->str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s)[:120] or "ksp"


def collect_paths(targets:list[str],recursive:bool)->list[Path]:
    out=[]
    for raw in targets:
        p=Path(raw).expanduser()
        if p.is_file(): out.append(p)
        elif p.is_dir(): out.extend(sorted(p.rglob("*.ksp") if recursive else p.glob("*.ksp")))
        else: raise FileNotFoundError(raw)
    return list(dict.fromkeys(x.resolve() for x in out))


def main(argv:Sequence[str]|None=None)->int:
    ap=argparse.ArgumentParser(description="Forensic KSP/MSX compatibility analyser using z80dasm")
    ap.add_argument("targets",nargs="+",help="KSP file(s) or directory/directories")
    ap.add_argument("--track",type=int,help="analyse one 1-based logical track")
    ap.add_argument("--all-tracks",action="store_true",help="analyse every track (default: one representative per physical page/engine)")
    ap.add_argument("--recursive",action="store_true",help="scan KSP files recursively in directories")
    ap.add_argument("--z80dasm",help="explicit path to z80dasm executable")
    ap.add_argument("--report-dir",help="write reconstructed .bin, z80dasm .asm and JSON reports here")
    ap.add_argument("--json",action="store_true",help="print JSON instead of human-readable text")
    ap.add_argument("--csv",help="write one-row-per-KSP batch summary CSV")
    ap.add_argument("--relaxed",action="store_true",help="do not mark non-$4000/$4000 geometry as a strict-native blocker")
    ap.add_argument("--fast",action="store_true",help="structural corpus scan only: skip page reconstruction, z80dasm and reachable-code/chip analysis")
    ap.add_argument("--deep-blockers",action="store_true",help="continue page reconstruction/z80dasm/code analysis even after a conclusive structural blocker")
    ap.add_argument("--try-fix",action="store_true",help="experimentally patch evidence-backed problems in memory and fully reanalyse the candidate; never modifies the input file")
    ap.add_argument("--build-disk",action="store_true",help="imply --try-fix, write repaired KSP to tool ksp/ and build a latest-player test DSK in tool dsk/")
    ap.add_argument("--player-template",help=f"explicit {TEMPLATE_NAME} or KSP_DSK_BUILDER_v0.47.1 ZIP for --build-disk")
    ap.add_argument("--version",action="version",version=f"ksp_analyse {VERSION}")
    args=ap.parse_args(argv)
    if args.track is not None and args.all_tracks: ap.error("--track and --all-tracks are mutually exclusive")
    if args.build_disk: args.try_fix=True
    if args.player_template and not args.build_disk: ap.error("--player-template is only valid with --build-disk")
    if args.try_fix and args.fast: ap.error("--try-fix/--build-disk requires deep analysis and cannot be combined with --fast")
    paths=collect_paths(args.targets,args.recursive)
    if not paths: print("No .ksp files found",file=sys.stderr); return 2
    rows=[]; exit_code=0
    for n,path in enumerate(paths):
        try:
            pkg,results,summary,repair,candidate=analyse_file(path,args)
            build=None; output_pkg=None; effective_summary=summary
            if args.build_disk:
                z80=find_z80dasm(args.z80dasm)
                output_pkg,final_results,final_summary,build=build_test_outputs(path,candidate,z80,args)
                effective_summary=final_summary
                if build.get("dsk_error"):
                    exit_code=max(exit_code,2)
            report={"tool":"ksp_analyse","version":VERSION,"summary":summary,"try_fix":repair,"build":build,
                    "package":{"file":str(path),"header":pkg.header,"meta":pkg.meta,"engines":[dataclasses.asdict(e)|{"template":"<omitted>"} for e in pkg.engines],"track_count":len(pkg.tracks),"page_count":len(pkg.pages),"resource_count":len(pkg.resources)},"tracks":results}
            if output_pkg is not None:
                report["output_package"]={"file":str(output_pkg.path),"header":output_pkg.header,"meta":output_pkg.meta,
                                          "engines":[dataclasses.asdict(e)|{"template":"<omitted>"} for e in output_pkg.engines],
                                          "track_count":len(output_pkg.tracks),"page_count":len(output_pkg.pages),"resource_count":len(output_pkg.resources),
                                          "summary":effective_summary}
            text=render_text(pkg,results,summary,repair,build)
            if args.report_dir:
                rd=Path(args.report_dir)/safe_name(path.stem); rd.mkdir(parents=True,exist_ok=True)
                (rd/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
                (rd/"report.txt").write_text(text,encoding="utf-8")
            if args.json:
                print(json.dumps(report,indent=2))
            elif len(paths)==1:
                print(text,end="")
            else:
                reason=effective_summary.get("top_findings",[{}])[0].get("code","") if effective_summary.get("top_findings") else ""
                suffix=""
                if build is not None:
                    suffix=f" -> {build.get('ksp','')}" + (f"; DSK {build['dsk'].get('output')}" if build.get('dsk') else "; DSK FAILED")
                print(f"{effective_summary['verdict']:<12} {effective_summary['confidence']:<6} {path.name} {reason}{suffix}")
            row_pkg=output_pkg or pkg
            e0=row_pkg.engines[0] if row_pkg.engines else None
            top=(effective_summary.get("top_findings") or [{}])[0]
            rows.append({"file":str(path),"title":row_pkg.meta.get("title",path.stem),"verdict":effective_summary["verdict"],"confidence":effective_summary["confidence"],"top_reason":top.get("code",""),"load":f"0x{e0.load:04X}" if e0 else "","page_size":f"0x{e0.page_size:04X}" if e0 else "","flags":"|".join(mask_names(e0.flags,FLAG_NAMES)) if e0 else "","declared_hw":"|".join(mask_names(e0.hardware,HW_NAMES)) if e0 else "","tracks":len(row_pkg.tracks)})
            if effective_summary["severity_score"]>=4 and not (args.build_disk and build and build.get("dsk_error")):
                exit_code=max(exit_code,1)
        except Exception as exc:
            exit_code=max(exit_code,2); print(f"ERROR       low    {path.name}: {exc}",file=sys.stderr)
            rows.append({"file":str(path),"title":path.stem,"verdict":"ERROR","confidence":"low","top_reason":str(exc),"load":"","page_size":"","flags":"","declared_hw":"","tracks":""})
    if args.csv:
        cp=Path(args.csv); cp.parent.mkdir(parents=True,exist_ok=True)
        with cp.open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    return exit_code


if __name__=="__main__":
    raise SystemExit(main())
