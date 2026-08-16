#!/usr/bin/env python3
import argparse, math, struct, zlib
from pathlib import Path
PAGE_SIZE=0x4000; LOAD=0x4000

def emit(buf,addr,data):
    off=addr-LOAD; buf[off:off+len(data)]=bytes(data)

def out_pair(code, port_a, port_d, reg, value):
    code += [0x3e,reg,0xd3,port_a,0x3e,value,0xd3,port_d]

def mwk_payload():
    out=bytearray(b'MBMS\x10\x0d\x00\x00\x00\x00')
    flags=bytearray(64); flags[0]=1; out+=flags
    src=bytearray(13)
    src[2:11]=bytes([0,0,0xff,0x00,0xf0,0xf0,0x00,0xf0,0xf7])
    sample=bytes((int(math.sin(2*math.pi*i/32)*110)&0xff) for i in range(256))
    src[11]=len(sample)&255; src[12]=len(sample)>>8
    out+=src+sample
    return bytes(out)

def page_fmpac():
    p=bytearray(PAGE_SIZE); code=[]
    # Preset instrument 1, audible channel 0.
    for reg,val in [(0x30,0x10),(0x10,0x80),(0x20,0x16)]: out_pair(code,0x7c,0x7d,reg,val)
    code += [0xc9]
    emit(p,0x4000,code)
    play=[]
    # Small f-number movement each PLAY call.
    play += [0x21,0x80,0x41,0x34,0x3e,0x10,0xd3,0x7c,0x7e,0xc6,0x70,0xd3,0x7d,0xc9]
    emit(p,0x4100,play)
    return bytes(p)

def page_opl4():
    p=bytearray(PAGE_SIZE); code=[]
    # OPL4 FM bank 0 using OPL-compatible registers.
    for reg,val in [(0x20,0x01),(0x23,0x01),(0x40,0x3f),(0x43,0x00),
                    (0x60,0xf2),(0x63,0xf2),(0x80,0x77),(0x83,0x77),
                    (0xc0,0x01),(0xa0,0x98),(0xb0,0x31)]:
        out_pair(code,0xc4,0xc5,reg,val)
    # PCM slot 0: custom MWK wave 0, loud, center, key on.
    for reg,val in [(0x08,0),(0x20,0),(0x38,0),(0x50,0),(0x68,0x88)]:
        out_pair(code,0x7e,0x7f,reg,val)
    code += [0xc9]
    emit(p,0x4000,code)
    emit(p,0x4100,[0xc9])
    return bytes(p)

def build(path:Path, opl4:bool):
    strings=(b'MoonSound VM test\0OPL4 FM + MWK PCM\0' if opl4 else
             b'FM-PAC VM test\0YM2413 test track\0')
    page=page_opl4() if opl4 else page_fmpac()
    mwk=mwk_payload() if opl4 else b''
    engine_off=80; page_off=144; track_off=168
    resource_count=1 if opl4 else 0
    resource_off=200; string_off=resource_off+resource_count*32
    cursor=string_off+len(strings)
    template=bytes(PAGE_SIZE); template_off=cursor; cursor+=len(template)
    page_off_data=cursor; cursor+=len(page)
    mwk_off=cursor
    if opl4: cursor+=len(mwk)
    engine=bytearray(64)
    flags=4 if opl4 else 0
    hardware=(1<<6) if opl4 else (1<<4)
    struct.pack_into('<II',engine,0,flags,hardware)
    struct.pack_into('<HHHHHHHHHHHH',engine,8,1,60,LOAD,PAGE_SIZE,0x4000,0x4100,0,0,0,0,1,0 if opl4 else 0xffff)
    engine[32]=0
    struct.pack_into('<IIIII',engine,36,template_off,len(template),len(template),zlib.crc32(template)&0xffffffff,0)
    page_entry=struct.pack('<HBBHHIIII',0,1,0,0,0,page_off_data,len(page),len(page),zlib.crc32(page)&0xffffffff)
    title_off=len(strings.split(b'\0')[0])+1
    track=struct.pack('<HHHHHHIIIII',0,0,0,0 if opl4 else 0xffff,0xffff,0,title_off,3000,0xffffffff,0xffffffff,500)
    resources=b''
    if opl4:
        resources=b'MWK '+struct.pack('<HBBIIIIII',0,0,0,mwk_off,len(mwk),len(mwk),zlib.crc32(mwk)&0xffffffff,0,0)
    index=bytes(engine)+page_entry+track+resources+strings
    header=bytearray(80); header[:4]=b'KSP1'
    struct.pack_into('<HHII',header,4,80,3,0,cursor)
    struct.pack_into('<IHH',header,16,engine_off,1,64)
    struct.pack_into('<IHH',header,24,page_off,1,24)
    struct.pack_into('<IHH',header,32,track_off,1,32)
    struct.pack_into('<IHH',header,40,resource_off,resource_count,32)
    struct.pack_into('<II',header,48,string_off,len(strings))
    struct.pack_into('<HHHH',header,56,0,0xffff,0xffff,0)
    struct.pack_into('<I',header,68,zlib.crc32(index)&0xffffffff)
    temp=bytearray(header); struct.pack_into('<I',temp,64,0)
    struct.pack_into('<I',header,64,zlib.crc32(temp)&0xffffffff)
    path.write_bytes(bytes(header)+index+template+page+mwk)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('output',type=Path); ap.add_argument('--opl4',action='store_true')
    ns=ap.parse_args(); build(ns.output,ns.opl4)
