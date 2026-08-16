#!/usr/bin/env python3
import argparse, struct, zlib
from pathlib import Path

PAGE_SIZE=0x4000
LOAD=0x4000

def put16(buf, off, value): struct.pack_into('<H',buf,off,value)
def emit(buf, addr, data):
    off=addr-LOAD
    buf[off:off+len(data)]=bytes(data)

def make_page(dual: bool, plus: bool, variant: int):
    p=bytearray(PAGE_SIZE)
    # INIT at 4000: PSG tone A and SCC waveform/frequency/volume/enable.
    code=[]
    def ld_a(n): code.extend([0x3e,n])
    def out(n): code.extend([0xd3,n])
    # PSG mixer, period and volume
    for reg,val in [(7,0x3e),(0,0x40),(1,0),(8,15)]:
        ld_a(reg); out(0xa0); ld_a(val); out(0xa1)
    # Select/enable the requested SCC family.  The normal single-SCC fixture
    # intentionally uses the same D900/D908 slot-wrapper ABI as the Shovel
    # Knight fallback engine.  Older TinyKSP versions only intercepted these
    # callbacks for HW_DUAL_SCC and returned from INIT before any chip writes.
    if dual or not plus: code.extend([0xcd,0x00,0xd9])
    if plus: code.extend([0x3e,0x20,0x32,0xfe,0xbf])  # LD (BFFE),20h
    wave_base = 0xb800 if plus else 0x9800
    code.extend([0x21,wave_base&255,wave_base>>8, 0x06,0x20, 0x3e,0xc0])
    loop=len(code)
    code.extend([0x77,0x23,0x3c,0x10,0xfb]) # LD(HL),A;INC HL;INC A;DJNZ -5
    # SCC A frequency, volume, enable
    regs = [(0xb8a0,0x80),(0xb8a1,0x00),(0xb8aa,0x0f),(0xb8af,0x01)] if plus else [(0x9880,0x80),(0x9881,0x00),(0x988a,0x0f),(0x988f,0x01)]
    for addr,val in regs:
        code.extend([0x3e,val,0x32,addr&255,addr>>8])
    if dual:
        # SCC B selection and a different waveform/frequency.
        code.extend([0xcd,0x04,0xd9, 0x21,0x00,0x98, 0x06,0x20, 0x3e,0x40])
        code.extend([0x77,0x23,0x3d,0x10,0xfb])
        for addr,val in [(0x9880,0x50),(0x9881,0x01),(0x988a,0x0c),(0x988f,0x01)]:
            code.extend([0x3e,val,0x32,addr&255,addr>>8])
    if dual or not plus:
        code.extend([0xcd,0x08,0xd9])
    code.append(0xc9)
    emit(p,0x4000,code)

    # PLAY at 4100: change PSG period and request page 1 at second tick.
    play=[
      0x21,0x80,0x41,       # LD HL,4180 counter
      0x34,                 # INC (HL)
      0x7e,                 # LD A,(HL)
      0xd3,0xa1,            # OUT (A1),A (selected PSG reg remains 8 initially; harmless)
      0xfe,0x02,            # CP 2
      0x20,0x06,            # JR NZ,+6
      0x21,0x01,0x00,       # LD HL,1
      0xcd,0xa0,0xd8,       # CALL D8A0
      0xc9,
    ]
    emit(p,0x4100,play)
    p[0x180]=0
    p[0x200]=variant
    return bytes(p)

def make_y8950_page(data_page: bool):
    p=bytearray(PAGE_SIZE)
    if data_page:
        pairs=[
            (0x01,0x20),
            (0x20,0x01),(0x23,0x01),
            (0x40,0x3f),(0x43,0x00),
            (0x60,0xf2),(0x63,0xf2),
            (0x80,0x77),(0x83,0x77),
            (0xc0,0x01),(0xa0,0x98),(0xb0,0x31),
        ]
        raw=bytes(x for pair in pairs for x in pair)
        emit(p,0x6800,raw)
        return bytes(p)

    # INIT: request local page 1, copy its register pairs into writable page 2,
    # then program the Y8950 via Philips Music Module ports C0h/C1h.
    pairs=12
    code=[
        0x21,0x01,0x00,       # LD HL,1
        0xcd,0xa0,0xd8,       # CALL D8A0
        0x21,0x00,0x68,       # LD HL,6800
        0x11,0x00,0x80,       # LD DE,8000
        0x01,pairs*2,0x00,    # LD BC,byte count
        0xed,0xb0,            # LDIR
        0x21,0x00,0x80,       # LD HL,8000
        0x06,pairs,           # LD B,pair count
        0x7e,0x23,0xd3,0xc0,  # register -> C0
        0x7e,0x23,0xd3,0xc1,  # value -> C1
        0x10,0xf6,            # DJNZ loop
        0xc9,
    ]
    emit(p,0x4000,code)
    # PLAY: move F-number slightly every tick, preserving the selected voice.
    play=[
        0x21,0x80,0x41,       # counter
        0x34,                 # INC (HL)
        0x3e,0xa0,0xd3,0xc0, # select FNUM low
        0x7e,0xc6,0x78,0xd3,0xc1,
        0xc9,
    ]
    emit(p,0x4100,play)
    p[0x180]=0
    return bytes(p)

def build(path:Path,dual:bool,plus:bool,y8950:bool):
    strings=b'Direct VM test\0Synthetic direct-runtime track\0'
    if y8950:
        pages=[make_y8950_page(False),make_y8950_page(True)]
    else:
        pages=[make_page(dual,plus,0x11),make_page(dual,plus,0x77)]
    engine_off=80; page_off=engine_off+64; track_off=page_off+2*24
    resource_off=track_off+32; string_off=resource_off
    cursor=string_off+len(strings)
    template=bytes(PAGE_SIZE); template_off=cursor; cursor+=PAGE_SIZE
    page_offsets=[]
    for p in pages: page_offsets.append(cursor); cursor+=len(p)

    engine=bytearray(64)
    hardware=(1<<5) if y8950 else ((1<<0)|((1<<3) if dual else ((1<<2) if plus else (1<<1))))
    flags=9 if y8950 else 1
    tick_hz=70 if y8950 else 60
    replace_start=0x6800 if y8950 else 0x4200
    struct.pack_into('<II',engine,0,flags,hardware)
    struct.pack_into('<HHHHHHHHHHHH',engine,8,1,tick_hz,LOAD,PAGE_SIZE,0x4000,0x4100,0,0xd8a0,replace_start,0,2,0xffff)
    engine[32]=0
    struct.pack_into('<IIIII',engine,36,template_off,len(template),len(template),zlib.crc32(template)&0xffffffff,0)

    pt=bytearray()
    for i,p in enumerate(pages):
        pt+=struct.pack('<HBBHHIIII',0,1,0,0,0,page_offsets[i],len(p),len(p),zlib.crc32(p)&0xffffffff)
    tt=struct.pack('<HHHHHHIIIII',0,0,0,0xffff,0xffff,0,len(b'Direct VM test\0'),1000,0xffffffff,0xffffffff,0xffffffff)
    index=bytes(engine)+bytes(pt)+tt+strings
    header=bytearray(80); header[:4]=b'KSP1'
    struct.pack_into('<HHII',header,4,80,2,0,cursor)
    struct.pack_into('<IHH',header,16,engine_off,1,64)
    struct.pack_into('<IHH',header,24,page_off,2,24)
    struct.pack_into('<IHH',header,32,track_off,1,32)
    struct.pack_into('<IHH',header,40,resource_off,0,32)
    struct.pack_into('<II',header,48,string_off,len(strings))
    struct.pack_into('<HHHH',header,56,0,0xffff,0xffff,0)
    struct.pack_into('<I',header,68,zlib.crc32(index)&0xffffffff)
    temp=bytearray(header); struct.pack_into('<I',temp,64,0)
    struct.pack_into('<I',header,64,zlib.crc32(temp)&0xffffffff)
    path.write_bytes(bytes(header)+index+template+b''.join(pages))

def build_adaptive(path:Path):
    strings=b'Adaptive VM test\0Synthetic adaptive track\0'
    single_pages=[make_page(False,False,0x11),make_page(False,False,0x77)]
    dual_pages=[make_page(True,False,0x22),make_page(True,False,0x88)]
    pages=single_pages+dual_pages
    engine_count=2; page_count=4; track_count=2; resource_count=1
    engine_off=80; page_off=engine_off+engine_count*64
    track_off=page_off+page_count*24; resource_off=track_off+track_count*32
    string_off=resource_off+resource_count*32; cursor=string_off+len(strings)
    template=bytes(PAGE_SIZE); template_off=cursor; cursor+=PAGE_SIZE
    page_offsets=[]
    for page in pages:
        page_offsets.append(cursor); cursor+=len(page)

    hvr=bytearray(24+12+16)
    hvr[:4]=b'HVR1'
    struct.pack_into('<HHHHHHII',hvr,4,24,1,1,2,12,8,24,36)
    struct.pack_into('<HHHHI',hvr,24,0,0,2,0,0)
    struct.pack_into('<HHHH',hvr,36,1,300,0,0)
    struct.pack_into('<HHHH',hvr,44,0,100,0,0)
    hvar_off=cursor; cursor+=len(hvr)

    engines=bytearray(engine_count*64)
    def put_engine(index, hardware, first_page):
        base=index*64
        struct.pack_into('<II',engines,base,1,hardware)
        struct.pack_into('<HHHHHHHHHHHH',engines,base+8,1,60,LOAD,PAGE_SIZE,
                         0x4000,0x4100,0,0xd8a0,0x4200,first_page,2,0xffff)
        engines[base+32]=0
        struct.pack_into('<IIIII',engines,base+36,template_off,len(template),len(template),
                         zlib.crc32(template)&0xffffffff,0)
    put_engine(0,(1<<0)|(1<<1),0)
    put_engine(1,(1<<0)|(1<<3),2)

    pt=bytearray()
    for engine_index in range(2):
        for local in range(2):
            global_page=engine_index*2+local
            page=pages[global_page]
            pt+=struct.pack('<HBBHHIIII',engine_index,1,0,0,0,page_offsets[global_page],
                            len(page),len(page),zlib.crc32(page)&0xffffffff)

    title_off=len(b'Adaptive VM test\0')
    visible=struct.pack('<HHHHHHIIIII',0,0,0,0xffff,0xffff,0,title_off,
                        3000,1000,2500,500)
    hidden=struct.pack('<HHHHHHIIIII',2,0,1,0xffff,0xffff,0,title_off,
                       5000,0xffffffff,0xffffffff,750)
    tracks=visible+hidden
    resources=b'HVAR'+struct.pack('<HBBIIIIII',0,0,0,hvar_off,len(hvr),len(hvr),
                                   zlib.crc32(hvr)&0xffffffff,0,0)
    index=bytes(engines)+bytes(pt)+tracks+resources+strings
    header=bytearray(80); header[:4]=b'KSP1'
    struct.pack_into('<HHII',header,4,80,2,0,cursor)
    struct.pack_into('<IHH',header,16,engine_off,engine_count,64)
    struct.pack_into('<IHH',header,24,page_off,page_count,24)
    struct.pack_into('<IHH',header,32,track_off,track_count,32)
    struct.pack_into('<IHH',header,40,resource_off,resource_count,32)
    struct.pack_into('<II',header,48,string_off,len(strings))
    struct.pack_into('<HHHH',header,56,0,0xffff,0xffff,0)
    struct.pack_into('<I',header,68,zlib.crc32(index)&0xffffffff)
    temp=bytearray(header); struct.pack_into('<I',temp,64,0)
    struct.pack_into('<I',header,64,zlib.crc32(temp)&0xffffffff)
    path.write_bytes(bytes(header)+index+template+b''.join(pages)+bytes(hvr))

def build_adaptive_multitrack(path:Path):
    strings=b'Adaptive multi-track test\0First track\0Second track\0'
    first_title=len(b'Adaptive multi-track test\0')
    second_title=first_title+len(b'First track\0')
    single_pages=[make_page(False,False,0x11),make_page(False,False,0x77)]
    dual_pages=[make_page(True,False,0x22),make_page(True,False,0x88)]
    pages=single_pages+dual_pages
    engine_count=2; page_count=4; track_count=4; resource_count=1
    engine_off=80; page_off=engine_off+engine_count*64
    track_off=page_off+page_count*24; resource_off=track_off+track_count*32
    string_off=resource_off+resource_count*32; cursor=string_off+len(strings)
    template=bytes(PAGE_SIZE); template_off=cursor; cursor+=PAGE_SIZE
    page_offsets=[]
    for page in pages:
        page_offsets.append(cursor); cursor+=len(page)

    hvr=bytearray(24+2*12+4*8)
    hvr[:4]=b'HVR1'
    struct.pack_into('<HHHHHHII',hvr,4,24,1,2,4,12,8,24,48)
    struct.pack_into('<HHHHI',hvr,24,0,0,2,0,0)
    struct.pack_into('<HHHHI',hvr,36,2,2,2,0,0)
    struct.pack_into('<HHHH',hvr,48,1,300,0,0)
    struct.pack_into('<HHHH',hvr,56,0,100,0,0)
    struct.pack_into('<HHHH',hvr,64,3,300,0,0)
    struct.pack_into('<HHHH',hvr,72,2,100,0,0)
    hvar_off=cursor; cursor+=len(hvr)

    engines=bytearray(engine_count*64)
    def put_engine(index, hardware, first_page):
        base=index*64
        struct.pack_into('<II',engines,base,1,hardware)
        struct.pack_into('<HHHHHHHHHHHH',engines,base+8,1,60,LOAD,PAGE_SIZE,
                         0x4000,0x4100,0,0xd8a0,0x4200,first_page,2,0xffff)
        engines[base+32]=0
        struct.pack_into('<IIIII',engines,base+36,template_off,len(template),len(template),
                         zlib.crc32(template)&0xffffffff,0)
    put_engine(0,(1<<0)|(1<<1),0)
    put_engine(1,(1<<0)|(1<<3),2)

    pt=bytearray()
    for engine_index in range(2):
        for local in range(2):
            global_page=engine_index*2+local
            page=pages[global_page]
            pt+=struct.pack('<HBBHHIIII',engine_index,1,0,0,0,page_offsets[global_page],
                            len(page),len(page),zlib.crc32(page)&0xffffffff)

    def track(page, song, flags, title, duration):
        return struct.pack('<HHHHHHIIIII',page,song,flags,0xffff,0xffff,0,title,
                           duration,0xffffffff,0xffffffff,500)
    tracks=(track(0,0,0,first_title,3000)+
            track(2,0,1,first_title,5000)+
            track(0,1,0,second_title,4000)+
            track(2,1,1,second_title,6000))
    resources=b'HVAR'+struct.pack('<HBBIIIIII',0,0,0,hvar_off,len(hvr),len(hvr),
                                   zlib.crc32(hvr)&0xffffffff,0,0)
    index=bytes(engines)+bytes(pt)+tracks+resources+strings
    header=bytearray(80); header[:4]=b'KSP1'
    struct.pack_into('<HHII',header,4,80,2,0,cursor)
    struct.pack_into('<IHH',header,16,engine_off,engine_count,64)
    struct.pack_into('<IHH',header,24,page_off,page_count,24)
    struct.pack_into('<IHH',header,32,track_off,track_count,32)
    struct.pack_into('<IHH',header,40,resource_off,resource_count,32)
    struct.pack_into('<II',header,48,string_off,len(strings))
    struct.pack_into('<HHHH',header,56,0,0xffff,0xffff,0)
    struct.pack_into('<I',header,68,zlib.crc32(index)&0xffffffff)
    temp=bytearray(header); struct.pack_into('<I',temp,64,0)
    struct.pack_into('<I',header,64,zlib.crc32(temp)&0xffffffff)
    path.write_bytes(bytes(header)+index+template+b''.join(pages)+bytes(hvr))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('output',type=Path); ap.add_argument('--dual',action='store_true'); ap.add_argument('--plus',action='store_true'); ap.add_argument('--y8950',action='store_true'); ap.add_argument('--adaptive',action='store_true'); ap.add_argument('--adaptive-multitrack',action='store_true')
    ns=ap.parse_args()
    if sum((ns.dual,ns.plus,ns.y8950,ns.adaptive,ns.adaptive_multitrack)) > 1: ap.error('hardware modes are mutually exclusive')
    if ns.adaptive: build_adaptive(ns.output)
    elif ns.adaptive_multitrack: build_adaptive_multitrack(ns.output)
    else: build(ns.output,ns.dual,ns.plus,ns.y8950)
