#!/usr/bin/env python3
import struct, zlib, sys
from pathlib import Path

out = Path(sys.argv[1])
dynamic = "--dynamic" in sys.argv[2:]
page_size = 64
template = bytes(page_size)
strings = b"Test engine\0Sparse track\0Complete track\0Resource track\0Hidden pooled track\0"
name_off = 0
title_offsets = [12, 25, 40, 55]

sparse = struct.pack('<HH', 10, 3) + b'abc'
complete = bytes((i * 3) & 0xff for i in range(page_size))
rmp = bytearray(32)
rmp[:4] = b'RMP1'
struct.pack_into('<HHHHI', rmp, 4, 16, 1, 16, 0, 0)
struct.pack_into('<HHBBHII', rmp, 16, 20, 4, 0, 0, 0, 2, 0)
pbm = bytearray(28)
pbm[:4] = b'PBM1'
struct.pack_into('<HHHHI', pbm, 4, 16, 2, 1, 12, 0)
struct.pack_into('<HHIHH', pbm, 16, 30, 3, 0, 1, 0)

data_resource = b'0123456789'
meta_resource = (
    b'title=TinyKSP Metadata Fixture\n'
    b'game=Fixture Game\n'
    b'system=MSX2\n'
    b'publisher=Test Publisher\n'
    b'developer=Test Developer\n'
    b'composer=Unit Composer\n'
    b'arranger=Unit Arranger\n'
    b'year=2026\n'
    b'copyright=Test Copyright\n'
    b'notes=All general fields are visible.\n'
    b'custom.field=custom value\n'
    b'track.0.title.ja=Japanese Track Title\n'
)
hvr = bytearray(24 + 12 + 8)
hvr[:4] = b'HVR1'
struct.pack_into('<HHHHHHII', hvr, 4, 24, 1, 1, 1, 12, 8, 24, 36)
struct.pack_into('<HHHHI', hvr, 24, 0, 0, 1, 0, 0)
struct.pack_into('<HHHH', hvr, 36, 0, 100, 0, 0)

pblk = bytearray(60)
pblk[:4] = b'PBK1'
struct.pack_into('<HHHHIHHIII', pblk, 4, 32, 8, 16, 4, 1, 1, 0, 32, 40, 0)
struct.pack_into('<HHI', pblk, 32, 0, 0, 0)
struct.pack_into('<IIHBBI', pblk, 40, 56, 4, 4, 0, 0, zlib.crc32(b'WXYZ') & 0xffffffff)
pblk[56:60] = b'WXYZ'

engine_count, page_count, track_count, resource_count = 1, 4, 4, 4
engine_off = 80
page_off = engine_off + 64
track_off = page_off + page_count * 24
resource_off = track_off + track_count * 32
string_off = resource_off + resource_count * 32
cursor = string_off + len(strings)
template_off = cursor; cursor += len(template)
payloads = [sparse, complete, bytes(rmp), bytes(pbm)]
payload_offsets = []
for payload in payloads:
    payload_offsets.append(cursor); cursor += len(payload)
resource_payloads = [data_resource, bytes(hvr), bytes(pblk), meta_resource]
resource_offsets = []
for payload in resource_payloads:
    resource_offsets.append(cursor); cursor += len(payload)

engine = bytearray(64)
struct.pack_into('<II', engine, 0, 1 if dynamic else 0, 1)
struct.pack_into('<HHHHHHHHHHHH', engine, 8, 1, 60, 0x4000, page_size, 0x4000, 0x4001, 0, 0, 0x4010, 0, page_count, 0xffff)
engine[32] = 0
struct.pack_into('<IIIII', engine, 36, template_off, len(template), len(template), zlib.crc32(template)&0xffffffff, name_off)

finals = []
p0 = bytearray(template); p0[10:13] = b'abc'; finals.append(bytes(p0))
finals.append(complete)
p2 = bytearray(page_size); p2[20:24] = data_resource[2:6]; finals.append(bytes(p2))
p3 = bytearray(page_size); p3[30:33] = b'XYZ'; finals.append(bytes(p3))
encodings = [0,1,3,2]
flags = [0,0,1,1]
page_table = bytearray()
for i, payload in enumerate(payloads):
    page_table += struct.pack('<HBBHHIIII', 0, encodings[i], 0, flags[i], 0, payload_offsets[i], len(payload), len(payload), zlib.crc32(finals[i])&0xffffffff)

track_table = bytearray()
for i in range(4):
    track_table += struct.pack('<HHHHHHIIIII', i, i, 1 if i==3 else 0, 0xffff, 0xffff, 0, title_offsets[i], 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff)

resource_table = bytearray()
for i,(kind,flags_,payload) in enumerate([(b'DATA',5,data_resource),(b'HVAR',0,bytes(hvr)),(b'PBLK',1,bytes(pblk)),(b'META',0,meta_resource)]):
    logical_crc = zlib.crc32(payload if kind != b'PBLK' else b'WXYZ') & 0xffffffff
    unpacked = len(payload) if kind != b'PBLK' else 4
    resource_table += kind + struct.pack('<HBBIIIIII', flags_, 0, 0, resource_offsets[i], len(payload), unpacked, logical_crc, 0, 0)

index = bytes(engine) + bytes(page_table) + bytes(track_table) + bytes(resource_table) + strings
header = bytearray(80)
header[:4] = b'KSP1'
struct.pack_into('<HHII', header, 4, 80, 2, 0, cursor)
struct.pack_into('<IHH', header, 16, engine_off, engine_count, 64)
struct.pack_into('<IHH', header, 24, page_off, page_count, 24)
struct.pack_into('<IHH', header, 32, track_off, track_count, 32)
struct.pack_into('<IHH', header, 40, resource_off, resource_count, 32)
struct.pack_into('<II', header, 48, string_off, len(strings))
struct.pack_into('<HHHH', header, 56, 0, 3, 0xffff, 0)
struct.pack_into('<I', header, 68, zlib.crc32(index)&0xffffffff)
copy = bytearray(header); struct.pack_into('<I', copy, 64, 0)
struct.pack_into('<I', header, 64, zlib.crc32(copy)&0xffffffff)

out.write_bytes(bytes(header)+index+template+b''.join(payloads)+b''.join(resource_payloads))
