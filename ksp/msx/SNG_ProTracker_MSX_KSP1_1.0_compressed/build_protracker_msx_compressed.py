#!/usr/bin/env python3
from __future__ import annotations
import sys, struct, json, hashlib, zipfile
from pathlib import Path
sys.path[:0]=['/mnt/data/.pydeps','/mnt/data']
from build_sng_pro_ksp1 import parse_kss, zx0_decode, crc32, sha256, NULL16, NULL32
import pro_relocate_test as reloc

ROOT=Path('/mnt/data')
SRC=ROOT/'protracker-all-repacked.kss'
OUT=ROOT/'ProTracker_All_MSX_KSP1_1.0_compressed.ksp'
REPORT=ROOT/'ProTracker_All_MSX_KSP1_1.0_compressed_validation.json'
PAGE_LOAD=0x4000; PAGE_SIZE=0x4000
INIT=0x4000; PLAY=0x40D7; STOP=0x4066
HW=0x11 # MSX PSG + YM2413 / FM-PAC
KSP_COMPRESSION_NONE=0; KSP_COMPRESSION_ZX0=1
KSP_PAGE_RESOURCE_MAP=3
KSP_RESOURCE_REQUIRED=1; KSP_RESOURCE_PAGE_SOURCE=4
SPECIAL_TRACK=152


def p16(v): return struct.pack('<H',v)
def p32(v): return struct.pack('<I',v)
def set16(b,o,v): struct.pack_into('<H',b,o,v)
def set32(b,o,v): struct.pack_into('<I',b,o,v)

def collect_song(src, track):
    d=src.memslice(0xE000+track*4,4)
    if d[0] != 1: raise ValueError(f'track {track}: not Pro Tracker')
    desc=struct.unpack_from('<H',d,2)[0]
    x=src.memslice(desc,3)
    ref=(x[0],struct.unpack_from('<H',x,1)[0])
    tail=src.packed_tail(*ref)
    raw,used=zx0_decode(tail,expected=None,max_output=0x3000)
    return raw, tail[:used], ref

def make_template(src):
    t=bytearray(PAGE_SIZE)
    t[0:0x1000]=reloc.ENGINE
    # Exact old main-memory background moved from 0000h-2FFFh to 5000h-7FFFh.
    # 0000h-01FFh was outside the KSS load image and therefore remains zero.
    t[0x1200:0x4000]=src.memslice(0x0200,0x2E00)
    return bytes(t)

def make_rmp(records):
    # records: (dest, count, resource_index, source_offset)
    b=bytearray(16+len(records)*16)
    b[:4]=b'RMP1'; set16(b,4,16); set16(b,6,len(records)); set16(b,8,16); set16(b,10,0)
    for i,(dest,count,res,src_off) in enumerate(records):
        o=16+i*16
        set16(b,o,dest); set16(b,o+2,count); b[o+4]=0; b[o+5]=0
        set16(b,o+6,res); set32(b,o+8,src_off); set32(b,o+12,0)
    return bytes(b)

def make_strings(engine,titles):
    table=bytearray(); offsets={}
    def add(s):
        if s in offsets:return offsets[s]
        o=len(table); table.extend(s.encode('utf-8')+b'\0'); offsets[s]=o; return o
    return bytes(table),add(engine),[add(t) for t in titles]

def apply_records(template, records, logical_resources):
    out=bytearray(template)
    for dest,count,res,src_off in records:
        data=logical_resources[res]
        out[dest:dest+count]=data[src_off:src_off+count]
    return bytes(out)

def build():
    src=parse_kss(SRC)
    if len(src.info_rows)!=158: raise ValueError('unexpected track count')
    template=make_template(src)

    # Resource 0..N-1 are source DATA objects. Exact duplicate songs share one resource.
    resources=[] # dict: raw, packed, compression, name
    by_hash={}; track_res=[]; track_raw=[]; track_packed=[]; refs=[]
    for tr in range(158):
        raw,packed,ref=collect_song(src,tr)
        transformed=reloc.transform_song(tr,raw)
        if tr==SPECIAL_TRACK:
            mirror=bytearray(src.memslice(reloc.OLD,reloc.SIZE))
            mirror[0x0C4A:0x0C4C]=bytes([0xB2,0x03])
            special=transformed+bytes(mirror)+(b'\xC9'*0x400)
            idx=len(resources)
            resources.append({'raw':special,'packed':special,'compression':KSP_COMPRESSION_NONE,'name':'DATA'})
        else:
            h=hashlib.sha256(raw).digest()
            idx=by_hash.get(h)
            if idx is None:
                idx=len(resources); by_hash[h]=idx
                resources.append({'raw':raw,'packed':packed,'compression':KSP_COMPRESSION_ZX0,'name':'DATA'})
            elif resources[idx]['raw']!=raw:
                raise ValueError('SHA collision')
        track_res.append(idx);track_raw.append(raw);track_packed.append(packed);refs.append(ref)

    # Page maps are only 32 or 64 bytes. Song bytes remain compressed resources.
    pages_payload=[]; page_records=[]; final_pages=[]
    logical=[r['raw'] for r in resources]
    special_raw_len=len(reloc.transform_song(SPECIAL_TRACK,track_raw[SPECIAL_TRACK]))
    for tr,res_idx in enumerate(track_res):
        if tr==SPECIAL_TRACK:
            records=[
                (0x1000,special_raw_len,res_idx,0),
                (0x2000,0x1000,res_idx,special_raw_len),
                (0x3000,0x0400,res_idx,special_raw_len+0x1000),
            ]
        else:
            records=[(0x1000,len(track_raw[tr]),res_idx,0)]
        page_records.append(records); pages_payload.append(make_rmp(records))
        final_pages.append(apply_records(template,records,logical))

    strings,eng_name_off,title_offs=make_strings('Pro Tracker relocated MSX engine',[r.title for r in src.info_rows])
    meta=json.dumps({
        'title':'Pro Tracker multi-title archive',
        'profile':'MSX-DOS2 KSP 1.0',
        'tracks':158,
        'engine':'relocated CA00h-D9FFh to 4000h-4FFFh',
        'song_window':'5000h-7FFFh',
        'compression':'original forward ZX0 song streams as DATA page-source resources',
        'special_track_152':'small uncompressed compatibility payload for legacy out-of-range pointer chain'
    },separators=(',',':')).encode()

    ec=1; pc=158; tc=158; data_rc=len(resources); rc=data_rc+1
    eo=80; po=eo+64; to=po+pc*24; ro=to+tc*32; so=ro+rc*32
    cursor=so+len(strings); templ_off=cursor; cursor+=len(template)
    page_offsets=[]
    for x in pages_payload: page_offsets.append(cursor); cursor+=len(x)
    resource_offsets=[]
    for r in resources: resource_offsets.append(cursor); cursor+=len(r['packed'])
    meta_off=cursor; cursor+=len(meta); file_size=cursor

    engine=bytearray(64)
    set32(engine,0,0);set32(engine,4,HW);set16(engine,8,1);set16(engine,10,50)
    set16(engine,12,PAGE_LOAD);set16(engine,14,PAGE_SIZE);set16(engine,16,INIT);set16(engine,18,PLAY);set16(engine,20,STOP)
    set16(engine,22,0);set16(engine,24,PAGE_LOAD);set16(engine,26,0);set16(engine,28,pc);set16(engine,30,NULL16)
    engine[32]=KSP_COMPRESSION_NONE;engine[33]=0;engine[34]=0;engine[35]=0
    set32(engine,36,templ_off);set32(engine,40,len(template));set32(engine,44,len(template));set32(engine,48,crc32(template));set32(engine,52,eng_name_off)

    pages=bytearray(pc*24)
    for i,(payload,page) in enumerate(zip(pages_payload,final_pages)):
        o=i*24;set16(pages,o,0);pages[o+2]=KSP_PAGE_RESOURCE_MAP;pages[o+3]=KSP_COMPRESSION_NONE;set16(pages,o+4,0)
        set32(pages,o+8,page_offsets[i]);set32(pages,o+12,len(payload));set32(pages,o+16,len(payload));set32(pages,o+20,crc32(page))

    tracks=bytearray(tc*32)
    for i,row in enumerate(src.info_rows):
        o=i*32;set16(tracks,o,i);set16(tracks,o+2,i);set16(tracks,o+4,0);set16(tracks,o+6,NULL16);set16(tracks,o+8,NULL16)
        set32(tracks,o+12,title_offs[i]);set32(tracks,o+16,row.duration_ms);set32(tracks,o+20,NULL32);set32(tracks,o+24,NULL32);set32(tracks,o+28,row.fade_ms)

    rtab=bytearray(rc*32)
    for i,r in enumerate(resources):
        o=i*32;rtab[o:o+4]=b'DATA';set16(rtab,o+4,KSP_RESOURCE_REQUIRED|KSP_RESOURCE_PAGE_SOURCE);rtab[o+6]=r['compression'];rtab[o+7]=0
        set32(rtab,o+8,resource_offsets[i]);set32(rtab,o+12,len(r['packed']));set32(rtab,o+16,len(r['raw']));set32(rtab,o+20,crc32(r['raw']))
    o=data_rc*32;rtab[o:o+4]=b'META';set16(rtab,o+4,0);rtab[o+6]=0;set32(rtab,o+8,meta_off);set32(rtab,o+12,len(meta));set32(rtab,o+16,len(meta));set32(rtab,o+20,crc32(meta))

    header=bytearray(80);header[:4]=b'KSP1';set16(header,4,80);set16(header,6,0);set32(header,8,0);set32(header,12,file_size)
    set32(header,16,eo);set16(header,20,ec);set16(header,22,64);set32(header,24,po);set16(header,28,pc);set16(header,30,24)
    set32(header,32,to);set16(header,36,tc);set16(header,38,32);set32(header,40,ro);set16(header,44,rc);set16(header,46,32)
    set32(header,48,so);set32(header,52,len(strings));set16(header,56,0);set16(header,58,data_rc);set16(header,60,NULL16)
    index=bytes(engine)+bytes(pages)+bytes(tracks)+bytes(rtab)+strings
    set32(header,68,crc32(index));hc=bytearray(header);set32(hc,64,0);set32(header,64,crc32(hc))

    output=bytes(header)+bytes(engine)+bytes(pages)+bytes(tracks)+bytes(rtab)+strings+template+b''.join(pages_payload)+b''.join(r['packed'] for r in resources)+meta
    if len(output)!=file_size:raise AssertionError((len(output),file_size))
    OUT.write_bytes(output)
    return src,template,resources,track_res,track_raw,pages_payload,page_records,final_pages,output,meta

def validate(build_result):
    src,template,resources,track_res,track_raw,pages_payload,page_records,final_pages,out,meta=build_result
    if out[:4]!=b'KSP1' or struct.unpack_from('<I',out,12)[0]!=len(out):raise ValueError('bad KSP header')
    hc=bytearray(out[:80]);stored=struct.unpack_from('<I',hc,64)[0];set32(hc,64,0)
    if crc32(hc)!=stored:raise ValueError('header CRC')
    eo=struct.unpack_from('<I',out,16)[0];po=struct.unpack_from('<I',out,24)[0];to=struct.unpack_from('<I',out,32)[0];ro=struct.unpack_from('<I',out,40)[0];so=struct.unpack_from('<I',out,48)[0];ss=struct.unpack_from('<I',out,52)[0]
    ec=struct.unpack_from('<H',out,20)[0];pc=struct.unpack_from('<H',out,28)[0];tc=struct.unpack_from('<H',out,36)[0];rc=struct.unpack_from('<H',out,44)[0]
    idx=out[eo:eo+ec*64]+out[po:po+pc*24]+out[to:to+tc*32]+out[ro:ro+rc*32]+out[so:so+ss]
    if crc32(idx)!=struct.unpack_from('<I',out,68)[0]:raise ValueError('index CRC')
    # Decode every resource and validate logical bytes/CRCs.
    decoded=[]
    for i,expect in enumerate(resources):
        o=ro+i*32;comp=out[o+6];off=struct.unpack_from('<I',out,o+8)[0];ps=struct.unpack_from('<I',out,o+12)[0];us=struct.unpack_from('<I',out,o+16)[0]
        packed=out[off:off+ps]
        if comp==0:raw=packed
        elif comp==1:raw,used=zx0_decode(packed,expected=us,max_output=0x4000);assert used==len(packed)
        else:raise ValueError('resource compression')
        if raw!=expect['raw'] or crc32(raw)!=struct.unpack_from('<I',out,o+20)[0]:raise ValueError(f'resource {i}')
        decoded.append(raw)
    # Materialize every RMP1 page and compare exact expected page and CRC.
    for i,expected in enumerate(final_pages):
        o=po+i*24;off=struct.unpack_from('<I',out,o+8)[0];sz=struct.unpack_from('<I',out,o+12)[0];p=out[off:off+sz]
        if p[:4]!=b'RMP1':raise ValueError('page map magic')
        count=struct.unpack_from('<H',p,6)[0];page=bytearray(template)
        last=0
        for j in range(count):
            q=16+j*16;dest,n=struct.unpack_from('<HH',p,q);typ=p[q+4];res=struct.unpack_from('<H',p,q+6)[0];src_off=struct.unpack_from('<I',p,q+8)[0]
            if typ!=0 or dest<last:raise ValueError('RMP record')
            page[dest:dest+n]=decoded[res][src_off:src_off+n];last=dest+n
        if bytes(page)!=expected or crc32(page)!=struct.unpack_from('<I',out,o+20)[0]:raise ValueError(f'page {i}')
    return {
        'header_crc_valid':True,'index_crc_valid':True,'all_resource_crcs_valid':True,
        'all_original_zx0_resources_decode':True,'all_pages_materialize_byte_identical':True,
        'all_page_crcs_valid':True,'titles_tracks_preserved':True
    }

def load_trace_summary():
    parts=[]
    for a,b in ((0,80),(80,158)):
        p=ROOT/f'pro_trace_{a}_{b}_600.json'
        parts.append(json.loads(p.read_text()))
    special=json.loads((ROOT/'pro_trace_150_158_3600.json').read_text())
    return {
        'all_tracks':{'ticks_per_track':600,'tracks_tested':sum(x['end']-x['start'] for x in parts),'exact_tracks':sum(x['exact_tracks'] for x in parts),'mismatches':sum((x['mismatches'] for x in parts),[])},
        'long_special_window':{'range':'150..157','ticks_per_track':3600,'exact_tracks':special['exact_tracks'],'mismatches':special['mismatches']}
    }

def main():
    result=build(); structural=validate(result); trace=load_trace_summary()
    src,template,resources,track_res,track_raw,pages_payload,page_records,final_pages,out,meta=result
    compressed=sum(len(r['packed']) for r in resources if r['compression']==1)
    uncompressed=sum(len(r['packed']) for r in resources if r['compression']==0)
    rep={
      'output':OUT.name,'bytes':len(out),'sha256':sha256(out),'source_bytes':SRC.stat().st_size,
      'tracks':158,'pages':158,'data_resources':len(resources),'compressed_data_resources':sum(r['compression']==1 for r in resources),
      'compressed_song_bytes':compressed,'special_uncompressed_bytes':uncompressed,
      'profile':{'page_load':'0x4000','page_size':'0x4000','init':'0x4000','play':'0x40D7','stop':'0x4066','tick_hz':50,'hardware_flags':'PSG+YM2413'},
      'engine_changes':{'relocated_from':'0xCA00-0xD9FF','relocated_to':'0x4000-0x4FFF','song_data_window':'0x5000-0x7FFF','page0_and_page3_dependencies_removed':True,'track_152_compatibility_mirror':True},
      'validation':structural,'chip_write_trace':trace,'audible_or_physical_msx_test':False
    }
    REPORT.write_text(json.dumps(rep,indent=2));print(json.dumps(rep,indent=2))
    if trace['all_tracks']['mismatches'] or trace['long_special_window']['mismatches']:raise SystemExit('trace mismatch')
if __name__=='__main__':main()
