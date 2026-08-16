#!/usr/bin/env python3
import argparse, struct, zlib
from pathlib import Path

PAGE=0x4000; LOAD=0x4000
CODE=bytes([
  0x3e,0x00,0xd3,0xa0, 0x3e,0x40,0xd3,0xa1,
  0x3e,0x01,0xd3,0xa0, 0x3e,0x01,0xd3,0xa1,
  0x3e,0x07,0xd3,0xa0, 0x3e,0x3e,0xd3,0xa1,
  0x3e,0x08,0xd3,0xa0, 0x3e,0x0f,0xd3,0xa1,
  0xc9,
  0x3e,0x08,0xd3,0xa0, 0x3e,0x0f,0xd3,0xa1,0xc9
])

def make_kss(path:Path, bad=False, first_song=0):
    code=bytearray(CODE)
    if bad:
        # Change only the INIT volume; comparator should identify PSG reg 8.
        i=code.find(bytes([0x3e,0x0f,0xd3,0xa1]))
        code[i+1]=0x0e
    hdr=bytearray(b'KSSX')+struct.pack('<HHHH',LOAD,len(code),0x4000,0x4021)+bytes([0,0,0x10,0])
    extra=bytearray(16)
    struct.pack_into('<HH',extra,8,first_song,first_song)
    path.write_bytes(hdr+extra+code)

def make_ksp(path:Path):
    page=bytearray(PAGE); page[:len(CODE)]=CODE
    strings=b'Synthetic compare\0Track 1\0'
    engine_off=80; page_off=144; track_off=168; resource_off=200; string_off=200
    cursor=string_off+len(strings); template=bytes(PAGE); template_off=cursor; cursor+=PAGE
    page_data_off=cursor; cursor+=PAGE
    engine=bytearray(64)
    struct.pack_into('<II',engine,0,0,1) # PSG
    struct.pack_into('<HHHHHHHHHHHH',engine,8,1,60,LOAD,PAGE,0x4000,0x4021,0,0,0,0,1,0xffff)
    engine[32]=0
    struct.pack_into('<IIIII',engine,36,template_off,PAGE,PAGE,zlib.crc32(template)&0xffffffff,0)
    pt=struct.pack('<HBBHHIIII',0,1,0,0,0,page_data_off,PAGE,PAGE,zlib.crc32(page)&0xffffffff)
    title_off=len(b'Synthetic compare\0')
    tt=struct.pack('<HHHHHHIIIII',0,0,0,0xffff,0xffff,0,title_off,10000,0xffffffff,0xffffffff,0xffffffff)
    index=bytes(engine)+pt+tt+strings
    header=bytearray(80); header[:4]=b'KSP1'
    struct.pack_into('<HHII',header,4,80,2,0,cursor)
    struct.pack_into('<IHH',header,16,engine_off,1,64)
    struct.pack_into('<IHH',header,24,page_off,1,24)
    struct.pack_into('<IHH',header,32,track_off,1,32)
    struct.pack_into('<IHH',header,40,resource_off,0,32)
    struct.pack_into('<II',header,48,string_off,len(strings))
    struct.pack_into('<HHHH',header,56,0,0xffff,0xffff,0)
    struct.pack_into('<I',header,68,zlib.crc32(index)&0xffffffff)
    tmp=bytearray(header); struct.pack_into('<I',tmp,64,0)
    struct.pack_into('<I',header,64,zlib.crc32(tmp)&0xffffffff)
    path.write_bytes(bytes(header)+index+template+page)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('ksp',type=Path); ap.add_argument('kss',type=Path)
    ap.add_argument('--bad',action='store_true'); ap.add_argument('--first-song',type=int,default=0)
    ns=ap.parse_args(); make_ksp(ns.ksp); make_kss(ns.kss,ns.bad,ns.first_song)
