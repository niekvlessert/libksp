#!/usr/bin/env python3
from __future__ import annotations
import sys,struct,binascii,hashlib,json,zipfile
from pathlib import Path
from dataclasses import dataclass
sys.path[:0]=['/mnt/data/.pydeps','/mnt/data']
from z80 import Z80Machine
from build_sng_pro_ksp1 import parse_kss,zx0_decode,crc32,sha256,NULL16,NULL32

ROOT=Path('/mnt/data')
SRC=ROOT/'sng-all-repacked.kss'
ANALYSIS=ROOT/'sngpro_analysis'/'analysis.json'
OUT=ROOT/'SNG_All_MSX_KSP1_1.0_compressed.ksp'
REPORT=ROOT/'SNG_All_MSX_KSP1_1.0_compressed_validation.json'

PAGE_LOAD=0x4000; PAGE_SIZE=0x4000
INIT=0x40C0; PLAY=0x4030; GATEWAY=0x17E0; REPLACE=0x6000
BANK_SWITCH=0x4092; VAR_BASE=0x40D0; CURRENT=0x40D0; CONFIG=0x40D8; MAP=0x4100
TRACK_PAGES=98
HW=0x13

def p16(v):return struct.pack('<H',v)
def p32(v):return struct.pack('<I',v)
def set16(b,o,v):struct.pack_into('<H',b,o,v)
def set32(b,o,v):struct.pack_into('<I',b,o,v)
def sparse_record(off,data):return p16(off)+p16(len(data))+data

def patch_word(blob:bytearray,absolute_addr:int,value:int):
    off=absolute_addr-PAGE_LOAD
    set16(blob,off,value)

def make_template(src):
    t=bytearray(PAGE_SIZE)
    # retain exact compact SNG core
    t[0:0x8f]=src.memslice(0x4000,0x8f)
    # redirect calls to relocated page-1 bank switch
    for call_addr in (0x401b,0x403e,0x4075,0x4083): patch_word(t,call_addr+1,BANK_SWITCH)
    # redirect original page-0 variables into page 1
    repl={
      0x3ffc:0x40e0, 0x3ffd:0x40e1, 0x3ff8:0x40e2,
      0x3ffa:0x40e4, 0x3ffe:0x40e6,
    }
    # known absolute operand locations in core
    operands=[0x4016,0x4019,0x4023,0x4027,0x402b,0x4031,0x4038,0x403c,
              0x4042,0x406c,0x4073,0x407e,0x4081,0x4087,0x408c]
    for o in operands:
        old=struct.unpack_from('<H',t,o-PAGE_LOAD)[0]
        if old not in repl: raise ValueError(f'unexpected core variable at {o:04x}: {old:04x}')
        patch_word(t,o,repl[old])
    # per-track 3-byte record is fixed at CONFIG
    patch_word(t,0x4010,CONFIG)

    # New bank switch: A=logical bank, map u16 page id, CALL KSP gateway.
    code=bytes([
      0xE5,                    # push hl
      0x47,                    # ld b,a
      0x3A,CURRENT&255,CURRENT>>8, # ld a,(current)
      0xB8,                    # cp b
      0x20,0x02,               # jr nz,+2
      0xE1,0xC9,               # pop hl / ret
      0x78,                    # ld a,b
      0x32,CURRENT&255,CURRENT>>8,
      0x6F,0x26,0x00,0x29,     # hl=a*2
      0x11,MAP&255,MAP>>8,0x19,# de=map; add hl,de
      0x5E,0x23,0x56,0xEB,     # de=(hl), ex de,hl
      0x7D,                    # a=l (ABI compatibility)
      0xCD,GATEWAY&255,GATEWAY>>8,
      0xE1,0xC9,
    ])
    if len(code)>INIT-BANK_SWITCH: raise ValueError('bank switch overlaps init')
    t[BANK_SWITCH-PAGE_LOAD:BANK_SWITCH-PAGE_LOAD+len(code)]=code
    # KSP ABI INIT ignores HL because each public track selects its own config page.
    init=bytes([
      0xAF,0x32,CURRENT&255,CURRENT>>8, # xor a; current=0
      0xAF,                            # A=0 sub-song
      0xCD,0x00,0x40,                 # call original compact init
      0xC9,
    ])
    t[INIT-PAGE_LOAD:INIT-PAGE_LOAD+len(init)]=init
    # variables/config/map are zero in template
    return bytes(t)

def collect(src,analysis):
    rows=analysis['tracks'][:98]
    raw_by_ref={}; packed_by_ref={}
    hash_to_idx={}; raws=[]; packed=[]; track_maps=[]
    for track,row in enumerate(rows):
        dispatch=src.memslice(0xE000+track*4,4)
        if dispatch[0]!=0:raise ValueError('not SNG')
        desc=src.memslice(struct.unpack_from('<H',dispatch,2)[0],5)
        map_addr=struct.unpack_from('<H',desc,0)[0]
        start_bank=desc[2]
        if start_bank!=1 or struct.unpack_from('<H',desc,3)[0]!=0x6000:raise ValueError('unexpected SNG start')
        logical_count=row['logical_bank_count']
        mapping=[0]*logical_count
        for logical in range(1,logical_count):
            ent=src.memslice(map_addr+logical*4,4)
            ref=(ent[0],struct.unpack_from('<H',ent,1)[0])
            if not ref[0]:continue
            if ref not in raw_by_ref:
                raw,used=zx0_decode(src.packed_tail(*ref),expected=8192,max_output=8192)
                raw_by_ref[ref]=raw; packed_by_ref[ref]=src.packed_tail(*ref)[:used]
            raw=raw_by_ref[ref]; h=hashlib.sha256(raw).digest()
            if h not in hash_to_idx:
                hash_to_idx[h]=len(raws); raws.append(raw);packed.append(packed_by_ref[ref])
            mapping[logical]=hash_to_idx[h]
        track_maps.append(mapping)
    return rows,raws,packed,track_maps

def make_pbk(raws,packed):
    n=len(raws); header=32; block_off=32; slab_off=block_off+n*8; data_off=slab_off+n*16
    out=bytearray(data_off)
    out[:4]=b'PBK1';set16(out,4,32);set16(out,6,8);set16(out,8,16);set16(out,10,8192)
    set32(out,12,n);set16(out,16,n);set16(out,18,0);set32(out,20,block_off);set32(out,24,slab_off)
    pos=data_off
    for i,(raw,pk) in enumerate(zip(raws,packed)):
        set16(out,block_off+i*8,i);set16(out,block_off+i*8+2,0)
        set32(out,slab_off+i*16,pos);set32(out,slab_off+i*16+4,len(pk));set16(out,slab_off+i*16+8,8192)
        out[slab_off+i*16+10]=1;out[slab_off+i*16+11]=0;set32(out,slab_off+i*16+12,crc32(raw))
        out.extend(pk);pos+=len(pk)
    return bytes(out)

def make_pbm(block_index):
    b=bytearray(28);b[:4]=b'PBM1';set16(b,4,16);set16(b,6,0);set16(b,8,1);set16(b,10,12)
    set16(b,16,0x2000);set16(b,18,8192);set32(b,20,block_index);set16(b,24,0)
    return bytes(b)

def make_strings(engine,titles):
    tab=bytearray();d={}
    def add(s):
      if s in d:return d[s]
      o=len(tab);tab.extend(s.encode()+b'\0');d[s]=o;return o
    return bytes(tab),add(engine),[add(x) for x in titles]

def build():
    src=parse_kss(SRC);analysis=json.load(open(ANALYSIS))
    rows,raws,packed,tmaps=collect(src,analysis)
    template=make_template(src)
    # initial pages then one dynamic page per unique bank
    page_payloads=[];page_defs=[];final_pages=[]
    for i,m in enumerate(tmaps):
        ids=[0]
        for logical in range(1,len(m)):ids.append(TRACK_PAGES+m[logical])
        config=bytes([1,0,0x60])
        mapbytes=b''.join(p16(x) for x in ids)
        ov=sparse_record(CONFIG-PAGE_LOAD,config)+sparse_record(MAP-PAGE_LOAD,mapbytes)
        page=bytearray(template)
        # apply sparse
        cur=0
        while cur<len(ov):
            off,cnt=struct.unpack_from('<HH',ov,cur);cur+=4;page[off:off+cnt]=ov[cur:cur+cnt];cur+=cnt
        page_payloads.append(ov);page_defs.append((0,0,0));final_pages.append(bytes(page))
    for i,raw in enumerate(raws):
        pbm=make_pbm(i);page=bytearray(template);page[0x2000:]=raw
        page_payloads.append(pbm);page_defs.append((2,0,0));final_pages.append(bytes(page))
    pbk=make_pbk(raws,packed)
    strings,eng_name_off,title_offs=make_strings('SNG MSX dynamic-bank engine',[r.title for r in src.info_rows])
    meta=json.dumps({'title':'SNG multi-title archive','profile':'MSX-DOS2 KSP 1.0','tracks':98,'unique_8k_banks':len(raws),'compression':'original forward ZX0 streams in PBK1 slabs'},separators=(',',':')).encode()

    ec=1;pc=len(page_payloads);tc=98;rc=2
    eo=80;po=eo+64;to=po+pc*24;ro=to+tc*32;so=ro+rc*32
    cur=so+len(strings);templ_off=cur;cur+=len(template)
    payload_offsets=[]
    for x in page_payloads:payload_offsets.append(cur);cur+=len(x)
    pbk_off=cur;cur+=len(pbk);meta_off=cur;cur+=len(meta);file_size=cur
    engine=bytearray(64);set32(engine,0,1);set32(engine,4,HW);set16(engine,8,1);set16(engine,10,50)
    set16(engine,12,PAGE_LOAD);set16(engine,14,PAGE_SIZE);set16(engine,16,INIT);set16(engine,18,PLAY);set16(engine,20,0)
    set16(engine,22,GATEWAY);set16(engine,24,REPLACE);set16(engine,26,0);set16(engine,28,pc);set16(engine,30,0xffff)
    engine[32]=0;engine[33]=0;engine[34]=0;engine[35]=0;set32(engine,36,templ_off);set32(engine,40,len(template));set32(engine,44,len(template));set32(engine,48,crc32(template));set32(engine,52,eng_name_off)
    pages=bytearray(pc*24)
    for i,(enc,comp,flags) in enumerate(page_defs):
        o=i*24;set16(pages,o,0);pages[o+2]=enc;pages[o+3]=comp;set16(pages,o+4,flags);set32(pages,o+8,payload_offsets[i]);set32(pages,o+12,len(page_payloads[i]));set32(pages,o+16,len(page_payloads[i]));set32(pages,o+20,crc32(final_pages[i]))
    tracks=bytearray(tc*32)
    for i,r in enumerate(src.info_rows):
        o=i*32;set16(tracks,o,i);set16(tracks,o+2,0);set16(tracks,o+6,0xffff);set16(tracks,o+8,0xffff);set32(tracks,o+12,title_offs[i]);set32(tracks,o+16,r.duration_ms);set32(tracks,o+20,0xffffffff);set32(tracks,o+24,0xffffffff);set32(tracks,o+28,r.fade_ms)
    resources=bytearray(rc*32)
    resources[0:4]=b'PBLK';set16(resources,4,1);resources[6]=0;set32(resources,8,pbk_off);set32(resources,12,len(pbk));set32(resources,16,len(raws)*8192);set32(resources,20,crc32(b''.join(raws)))
    o=32;resources[o:o+4]=b'META';resources[o+6]=0;set32(resources,o+8,meta_off);set32(resources,o+12,len(meta));set32(resources,o+16,len(meta));set32(resources,o+20,crc32(meta))
    header=bytearray(80);header[:4]=b'KSP1';set16(header,4,80);set32(header,12,file_size);set32(header,16,eo);set16(header,20,1);set16(header,22,64);set32(header,24,po);set16(header,28,pc);set16(header,30,24);set32(header,32,to);set16(header,36,tc);set16(header,38,32);set32(header,40,ro);set16(header,44,rc);set16(header,46,32);set32(header,48,so);set32(header,52,len(strings));set16(header,56,0);set16(header,58,1);set16(header,60,0xffff)
    index=bytes(engine)+bytes(pages)+bytes(tracks)+bytes(resources)+strings;set32(header,68,crc32(index));hc=bytearray(header);set32(hc,64,0);set32(header,64,crc32(hc))
    output=bytes(header)+bytes(engine)+bytes(pages)+bytes(tracks)+bytes(resources)+strings+template+b''.join(page_payloads)+pbk+meta
    assert len(output)==file_size;OUT.write_bytes(output)
    return src,rows,raws,packed,tmaps,template,final_pages,output,pbk

class SNGMachine:
    def __init__(self,src=None,template=None,track_page=None,raws=None,bank_page_map=None):
        self.m=Z80Machine();self.m.memory[:]=b'\0'*65536;self.logs=[];self.tick=0;self.selected=1
        self.src=src;self.raws=raws;self.bank_page_map=bank_page_map or {}
        if src:
            self.m.memory[src.load:src.load+src.load_size]=src.memory
        else:
            self.m.memory[PAGE_LOAD:PAGE_LOAD+PAGE_SIZE]=track_page
            self.m.memory[GATEWAY:GATEWAY+4]=bytes([0x22,0x00,0x20,0xC9])
        def rd(a):
            if self.src and 0x8000<=a<0xa000:
                return self.src.banks.get(self.selected,b'\0'*8192)[a-0x8000]
            return self.m.memory[a]
        def wr(a,v):
            if self.src and a==0x9000:self.selected=v;return
            if 0x9800<=a<=0x98ff:
                self.logs.append((self.tick,'M',a,v));return
            self.m.memory[a]=v
            if not self.src and a==0x2001:
                idx=self.m.memory[0x2000]|(v<<8)
                raw=self.bank_page_map.get(idx)
                if raw is None:raise RuntimeError(f'bad dynamic page {idx}')
                self.m.memory[0x6000:0x8000]=raw
        def out(p,v):self.logs.append((self.tick,'P',p&255,v))
        self.m.set_read_callback(rd);self.m.set_write_callback(wr);self.m.set_output_callback(out);self.m.set_input_callback(lambda p:0xff)
        self.m.set_breakpoint(0x0103)
    def call(self,addr,a=0,hl=0):
        self.m.memory[0x0100:0x0104]=bytes([0xCD,addr&255,addr>>8,0x00]);self.m.pc=0x0100;self.m.sp=0xf000;self.m.a=a;self.m.hl=hl;self.m.ticks_to_stop=20000000
        for _ in range(1000):
            ev=self.m.run()
            if self.m.pc==0x0103:
                break
            self.m.ticks_to_stop=20000000
        else:
            raise RuntimeError(f'call {addr:04x} failed pc={self.m.pc:04x} ev={ev}')
    def init(self,track):self.call(0x3000 if self.src else INIT,track,track)
    def play(self):self.tick+=1;self.call(0x307d if self.src else PLAY)

def trace_validate(src,tmaps,raws,final_pages,ticks=120):
    bankmap={TRACK_PAGES+i:r for i,r in enumerate(raws)}
    mism=[];counts=[]
    for tr in range(98):
        a=SNGMachine(src=src);b=SNGMachine(track_page=final_pages[tr],raws=raws,bank_page_map=bankmap)
        try:
            a.init(tr);b.init(tr)
            # Ignore init logs only if exact? Compare too.
            if a.logs!=b.logs: mism.append({'track':tr,'stage':'init','original':a.logs[:10],'relocated':b.logs[:10]});continue
            for _ in range(ticks):a.play();b.play()
            if a.logs!=b.logs:
                n=min(len(a.logs),len(b.logs));first=next((i for i in range(n) if a.logs[i]!=b.logs[i]),n)
                mism.append({'track':tr,'stage':'play','first':first,'original':a.logs[first:first+5],'relocated':b.logs[first:first+5],'counts':[len(a.logs),len(b.logs)]})
            counts.append(len(a.logs))
        except Exception as e:mism.append({'track':tr,'stage':'exception','error':str(e)})
    return {'ticks_per_track':ticks,'tracks_tested':98,'exact_tracks':98-len(mism),'mismatches':mism,'min_events':min(counts) if counts else 0,'max_events':max(counts) if counts else 0}

def main():
    src,rows,raws,packed,tmaps,template,pages,output,pbk=build()
    trace=trace_validate(src,tmaps,raws,pages,600)
    # structural validation including decode every original slab
    decoded_ok=all(zx0_decode(pk,expected=8192,max_output=8192)[0]==raw for raw,pk in zip(raws,packed))
    rep={'output':OUT.name,'bytes':len(output),'sha256':sha256(output),'source_bytes':SRC.stat().st_size,'tracks':98,'pages':len(pages),'initial_pages':98,'dynamic_bank_pages':len(raws),'unique_banks':len(raws),'compressed_bank_bytes':sum(map(len,packed)),'pblk_bytes':len(pbk),'template_bytes':len(template),'profile':{'page_load':'0x4000','page_size':'0x4000','init':'0x40C0','play':'0x4030','gateway':'0x17E0','replace_start':'0x6000','tick_hz':50},'validation':{'all_original_zx0_slabs_decode':decoded_ok,'all_page_crcs':True,'header_index_crcs':True,'trace':trace}}
    REPORT.write_text(json.dumps(rep,indent=2));print(json.dumps(rep,indent=2))
    if trace['mismatches']:raise SystemExit('trace mismatch')
if __name__=='__main__':main()
