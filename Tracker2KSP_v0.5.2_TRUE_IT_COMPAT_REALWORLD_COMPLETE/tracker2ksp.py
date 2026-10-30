#!/usr/bin/env python3
"""S3M/IT-S3M/IT/XM/MOD -> compact semantic KSP 1.05 for KSP1PLAY 0.48.

No KSP format extension is used. Tracker rows are compacted on the host, while
slides, portamento, vibrato, retrigger and arpeggio are executed by a resident
Z80 engine. PCM sample data is a standard MWK resource and is uploaded once to
MoonSound/OPL4 sample RAM by the existing player.
"""
from __future__ import annotations
import argparse,binascii,hashlib,json,struct
from pathlib import Path

import _s3m2opl4_backend as core
import module_formats
import compact_stream
import zx0_codec

KSP_MINOR=5
PAGE_LOAD=0x4000
PAGE_SIZE=0x4000
STREAM_BASE=0x6800
MOD_STREAM_BASE=0x6A00
IT_STREAM_BASE=0x7C00
STREAM_OFFSET=STREAM_BASE-PAGE_LOAD
STREAM_DATA_OFFSET=STREAM_OFFSET+2
STREAM_PAGE_CAPACITY=PAGE_SIZE-STREAM_DATA_OFFSET

def stream_base_for(source_format:str)->int:
    if source_format=='MOD': return MOD_STREAM_BASE
    if source_format=='IT': return IT_STREAM_BASE
    return STREAM_BASE

def stream_page_capacity_for(source_format:str)->int:
    base=stream_base_for(source_format)
    return PAGE_SIZE-((base-PAGE_LOAD)+2)
PAGE_TOTAL_CFG=0x63FC
DYNAMIC_GATEWAY_PLACEHOLDER=0x7FF0
HW_OPL4=0x40
ENGINE_DYNAMIC_PAGES=0x01
ENGINE_MWK_REQUIRED=0x04
TRACK_ONE_SHOT=0x04
NULL16=0xFFFF; NULL32=0xFFFFFFFF
COMP_NONE=0; COMP_ZX0=1; PAGE_SPARSE=0
MAX_SUPPORTED_PAGES=0xFFFF; MAX_PRELOADED_PAGES=32
OPL4_STATE_BASE=0x2FFC00  # final 1 KiB of standard 1 MiB MoonSound RAM reserved for page-state handoff

HERE=Path(__file__).resolve().parent
S3M_ENGINE_BIN=(HERE/'compact_engine_s3m.bin').read_bytes()
IT_S3M_ENGINE_BIN=(HERE/'compact_engine_it_s3m.bin').read_bytes()
IT_ENGINE_BIN=(HERE/'compact_engine_it.bin').read_bytes()
MOD_ENGINE_BIN=(HERE/'compact_engine_mod.bin').read_bytes()
XM_ENGINE_BIN=(HERE/'compact_engine_xm.bin').read_bytes()

def parse_map(path:Path):
    out={}
    for line in path.read_text().splitlines():
        if ' = 0x' in line:
            k,v=line.split(' = ',1); out[k.strip().lower()]=int(v,16)
    return out
S3M_ENGINE_SYM=parse_map(HERE/'compact_engine_s3m.map')
IT_S3M_ENGINE_SYM=parse_map(HERE/'compact_engine_it_s3m.map')
IT_ENGINE_SYM=parse_map(HERE/'compact_engine_it.map')
MOD_ENGINE_SYM=parse_map(HERE/'compact_engine_mod.map')
XM_ENGINE_SYM=parse_map(HERE/'compact_engine_xm.map')


def crc32(b): return binascii.crc32(b)&0xffffffff
def sha256(b): return hashlib.sha256(b).hexdigest()
def add_string(t:bytearray,s:str):
    o=len(t); t+=s.encode('utf-8')+b'\0'; return o

def maybe_zx0(data:bytes,mode:str):
    if mode=='none': return data,COMP_NONE
    packed=zx0_codec.compress(data)
    if len(packed)<len(data): return packed,COMP_ZX0
    return data,COMP_NONE


def variant_payload(module:core.Module,v):
    s=module.samples[v.key.instrument]; off=max(0,v.key.offset)
    if off>=s.length:return b'\0',0,1
    if not s.looped:
        payload=s.data[off:]+b'\0'; return payload,s.length-off,len(payload)
    lb,le=s.loop_begin,s.loop_end
    # ProTracker one-shot loops: if loop start is zero, Paula first plays the
    # complete sample and only then loops 0..loop_end. Represent that exactly
    # on OPL4 by appending one copy of the loop and making the appended copy
    # the hardware loop. Offset starts still play the remaining tail first.
    if (getattr(module,'source_format','')=='MOD' and bool(getattr(module,'mod_one_shot_loops',False))
            and lb==0 and le < s.length):
        first=s.data[off:s.length] if off < s.length else b''
        loop=s.data[0:le]
        payload=(first+loop) or b'\0'
        return payload,len(first),len(payload)
    if off<=lb:
        payload=s.data[off:le] or b'\0'; return payload,lb-off,len(payload)
    if off<le:
        # Starting inside a loop can be represented without duplicating the loop:
        # rotate it to [offset..loop_end)+[loop_start..offset) and loop at zero.
        # The audible sequence is A,B,A,B... which is exactly the original
        # offset-tail followed by repeated original loop cycles.
        payload=(s.data[off:le]+s.data[lb:off]) or b'\0'
        return payload,0,len(payload)
    first=s.data[off:s.length]; loop=s.data[lb:le]; payload=first+loop or b'\0'
    return payload,len(first),len(payload)

def _shared_geometry(module:core.Module,instrument:int,off:int,base_addr:int):
    s=module.samples[instrument]; off=max(0,int(off))
    if off>=s.length:
        return base_addr,0,1
    if not s.looped:
        return base_addr+off,s.length-off,s.length-off+1
    if (getattr(module,'source_format','')=='MOD' and bool(getattr(module,'mod_one_shot_loops',False))
            and s.loop_begin==0 and off==0 and s.loop_end < s.length):
        return base_addr,s.length,s.length+s.loop_end
    # SharedPayloadWaveBank only calls this for off <= loop_begin.
    return base_addr+off,s.loop_begin-off,s.loop_end-off

def _header_prefix(start_addr:int,loop_pos:int,play_len:int)->bytes:
    comp=(-int(play_len)) & 0xFFFF
    return bytes(((start_addr>>16)&0x3F,(start_addr>>8)&0xFF,start_addr&0xFF,
                  (loop_pos>>8)&0xFF,loop_pos&0xFF,(comp>>8)&0xFF,comp&0xFF))

def build_mwk(module:core.Module,variants):
    """Build standard MWK 0x0C plus INIT-time headers for waves 384..511.

    KSP1PLAY 0.48 still uploads at most the normal 64 MWK tones. Header-only
    aliases may use OPL4 custom-wave indices 64..127 because their PCM payload
    already belongs to a low-half owner. The resident engine installs those
    seven-byte header prefixes once during INIT.
    """
    ordered=sorted(variants,key=lambda v:v.wave_number)
    if ordered and (ordered[-1].wave_number-384)>=128:
        raise ValueError('OPL4 supports at most 128 custom wave headers')
    flags=bytearray(64); blobs=[]; manifest=[]; patches=[]; addr=0x200300
    owner_addr={}
    # Extended S3M/IT-S3M uses RAM wave headers 384..511 (128 * 12 = 0x600 bytes).
    # Standard MWK 0C loaders start PCM at 0x200300 because they know only 64 headers.
    # Reserve an unreferenced tone 0 with a 0x300-byte silent payload so all real PCM
    # begins at 0x200600. Runtime header aliases 448..511 can then occupy 0x200300..
    # without corrupting the first real sample.
    if ordered and min(v.wave_number for v in ordered) >= 385:
        flags[0]=1
        pad_len=0x300
        hdr=bytearray(13)
        hdr[2]=0; hdr[3]=0
        hdr[4]=0xFF; hdr[5]=0xFF   # one-sample wave; payload is only address padding
        hdr[6:11]=bytes((0,0xF0,0,7,0))
        hdr[11]=pad_len & 0xFF; hdr[12]=(pad_len>>8)&0xFF
        # This padding occupies the physical RAM range used by OPL4 custom
        # wave headers 448..511. The Z80 alias installer overwrites only the
        # 7-byte geometry prefix, so preseed the remaining five envelope bytes
        # exactly like ordinary MWK/custom headers.
        pad=bytearray(pad_len)
        for ho in range(0,pad_len,12):
            pad[ho+7:ho+12]=bytes((0,0xF0,0,7,0))
        blobs.append(bytes(16)+bytes(hdr)+bytes(pad))
        manifest.append({'tone':0,'opl4_wave':384,'instrument':0,'sample_name':'<header-reserve>',
                         'sample_offset':0,'payload_bytes':pad_len,'sample_ram_address':addr,
                         'payload_ram_address':addr,'loop_position':0,'play_length':1,
                         'shared_payload':False,'alias_owner_tone':None,'init_header_patch':False,
                         'reserved_header_padding':True})
        addr += pad_len
    for v in ordered:
        tone=v.wave_number-384
        s=module.samples[v.key.instrument]
        alias_owner=getattr(v,'alias_owner',None)
        is_owner=bool(getattr(v,'payload_owner',False))
        header_off=int(getattr(v,'header_offset',0))
        shared=(is_owner or alias_owner is not None)

        if tone>=64:
            # Upper-half custom waves are header aliases only. Their payload was
            # already uploaded by a low-half owner through ordinary MWK 0x0C.
            if not shared or is_owner or alias_owner is None:
                raise ValueError(f'custom tone {tone} above 63 requires a shared low-half payload owner')
            if id(alias_owner) not in owner_addr:
                raise ValueError('upper-half alias encountered before its payload owner')
            base_addr=owner_addr[id(alias_owner)]
            start,lp,plen=_shared_geometry(module,v.key.instrument,header_off,base_addr)
            patches.append(bytes((tone,))+_header_prefix(start,lp,plen))
            manifest.append({'tone':tone,'opl4_wave':384+tone,'instrument':v.key.instrument,'sample_name':s.name,
                             'sample_offset':v.key.offset,'payload_bytes':0,'sample_ram_address':start,
                             'payload_ram_address':base_addr,'loop_position':lp,'play_length':plen,
                             'shared_payload':True,'alias_owner_tone':alias_owner.wave_number-384,
                             'init_header_patch':True})
            continue

        # Low-half tones are represented by the unchanged 64-flag MWK loader.
        if shared:
            if is_owner:
                base_v=core.WaveVariant(key=core.WaveKey(v.key.instrument,0),wave_number=v.wave_number,
                                        sample_name=v.sample_name,source_length=v.source_length)
                payload,base_lp,base_plen=variant_payload(module,base_v)
                owner_addr[id(v)]=addr; base_addr=addr
            else:
                payload=b''
                if id(alias_owner) not in owner_addr:
                    raise ValueError('shared MWK alias encountered before its payload owner')
                base_addr=owner_addr[id(alias_owner)]
            start,lp,plen=_shared_geometry(module,v.key.instrument,header_off,base_addr)
            if (not is_owner) or header_off:
                patches.append(bytes((tone,))+_header_prefix(start,lp,plen))
        else:
            payload,lp,plen=variant_payload(module,v)
            start=addr; base_addr=addr
        if len(payload)>65535:
            raise ValueError(f'sample variant {v.key.instrument}/{v.key.offset} exceeds 65535 bytes')
        if addr+len(payload)>OPL4_STATE_BASE:
            raise ValueError('MoonSound sample data collides with the realtime state reserve')
        flags[tone]=1
        comp=(-plen)&0xffff
        hdr=bytearray(13); hdr[2]=lp>>8; hdr[3]=lp&255; hdr[4]=comp>>8; hdr[5]=comp&255
        hdr[6:11]=bytes((0,0xF0,0,7,0)); hdr[11]=len(payload)&255; hdr[12]=len(payload)>>8
        blobs.append(bytes(16)+bytes(hdr)+payload)
        manifest.append({'tone':tone,'opl4_wave':384+tone,'instrument':v.key.instrument,'sample_name':s.name,
                         'sample_offset':v.key.offset,'payload_bytes':len(payload),'sample_ram_address':start,
                         'payload_ram_address':addr if len(payload) else base_addr,
                         'loop_position':lp,'play_length':plen,'shared_payload':shared,
                         'alias_owner_tone':(alias_owner.wave_number-384 if alias_owner is not None else None),
                         'init_header_patch':((not is_owner) or header_off) if shared else False})
        addr+=len(payload)
    if len(patches)>64:
        raise ValueError(f'engine INIT header patch table supports 64 aliases; module needs {len(patches)}')
    return b'MBMS\x10\x0c\0\0\0\0'+bytes(flags)+b''.join(blobs),manifest,patches

def volume_lut(module:core.Module):
    # Use the exact host-side logarithmic mapping from the original compiler.
    return bytes(core.Compiler._level_reg(v,module.global_volume) for v in range(65))

def _cdiv(n:int,d:int)->int:
    if d<=0:return 0
    return -(abs(n)//d) if n<0 else n//d

def _ft2_env_curve(points):
    """Precompute the upper-byte FT2 envelope value for each X tick."""
    if not points:return b''
    pts=[(int(x)&0xFFFF,max(0,min(64,int(y)))) for x,y in points]
    maxx=pts[-1][0]
    if maxx>2047:
        raise ValueError(f'XM envelope endpoint {maxx} exceeds realtime profile limit 2047 ticks')
    out=bytearray(maxx+1); seg=0
    for x in range(maxx+1):
        while seg+1<len(pts) and x>=pts[seg+1][0]: seg+=1
        x0,y0=pts[seg]
        if seg+1<len(pts):
            x1,y1=pts[seg+1]; dx=x1-x0
            delta=_cdiv((y1-y0)<<8,dx) if dx>0 else 0
            val=(y0<<8)+delta*(x-x0)
        else:
            val=y0<<8
        hi=val>>8
        out[x]=max(0,min(64,hi))
    return bytes(out)

def _profile_point_x(points,index:int)->int:
    if not points:return 0
    index=max(0,min(len(points)-1,int(index)))
    return int(points[index][0]) & 0xFFFF

def build_xm_profile_patch(module:core.Module,sym:dict,waves:list[dict]):
    profiles=list(getattr(module,'xm_profiles',[]))
    if not profiles:return None
    tone_addr=sym['xm_tone_profile']; ptr_addr=sym['xm_profile_ptrs']; data_addr=sym['xm_profile_data']; limit=sym['xm_profile_limit']
    tone_map=bytearray(64)
    for w in waves:
        tone=int(w['tone']); ins=int(w['instrument'])
        tone_map[tone]=int(getattr(module.samples[ins],'xm_profile_id',0)) & 0x3F
    curves=[]; curve_meta=[]
    record_bytes=30*len(profiles)
    cursor=data_addr+record_bytes
    records=[]
    for prof in profiles:
        vp,pp,vs,vls,vle,ps,pls,ple,vf,pf,fade,avtype,avsweep,avdepth,avrate,basepan=prof
        vcurve=_ft2_env_curve(vp) if (vf&1 and vp) else b''
        pcurve=_ft2_env_curve(pp) if (pf&1 and pp) else b''
        vaddr=cursor if vcurve else 0; cursor+=len(vcurve)
        paddr=cursor if pcurve else 0; cursor+=len(pcurve)
        flags=(vf&7)|((pf&7)<<3)|(0x40 if avdepth else 0)
        sweep_step=((int(avdepth)<<8)//int(avsweep)) if avdepth and avsweep else 0
        rec=bytearray(30)
        rec[0]=flags&0x7F; rec[1]=int(basepan)&0xFF
        struct.pack_into('<H',rec,2,int(fade)&0xFFFF)
        rec[4]=int(avtype)&3; rec[5]=int(avdepth)&0xFF; rec[6]=int(avrate)&0xFF
        struct.pack_into('<H',rec,8,sweep_step&0xFFFF)
        struct.pack_into('<HHHHH',rec,10,vaddr,len(vcurve)-1 if vcurve else 0,
                         _profile_point_x(vp,vs),_profile_point_x(vp,vls),_profile_point_x(vp,vle))
        struct.pack_into('<HHHHH',rec,20,paddr,len(pcurve)-1 if pcurve else 0,
                         _profile_point_x(pp,ps),_profile_point_x(pp,pls),_profile_point_x(pp,ple))
        records.append(bytes(rec)); curves.extend((vcurve,pcurve))
    if cursor>limit:
        raise ValueError(f'XM envelope/profile data needs {cursor-data_addr} bytes but resident profile area has {limit-data_addr}')
    ptrs=bytearray(128)
    for i in range(min(64,len(profiles))): struct.pack_into('<H',ptrs,i*2,data_addr+i*30)
    blob=b''.join(records)+b''.join(curves)
    return {'tone_addr':tone_addr,'tone_map':bytes(tone_map),'ptr_addr':ptr_addr,'ptrs':bytes(ptrs),
            'data_addr':data_addr,'blob':blob,'limit':limit,'profiles':len(profiles),'bytes':len(blob)}

def _it_env_curve(env,kind:str):
    """Precompute an IT envelope at tracker-tick resolution.

    Volume is stored as 0..64 bytes, pan as 0..64 (32 neutral), and pitch as
    a Q8 period multiplier. IT pitch envelope units are half-semitones.
    """
    flags,points,ls,le,ss,se=env
    if not (flags&1) or not points:return b''
    pts=[(int(x),int(y)) for x,y in points]
    maxx=pts[-1][0]
    if maxx>4095: raise ValueError(f'IT {kind} envelope endpoint {maxx} exceeds 4095 ticks')
    seg=0; out=bytearray()
    for x in range(maxx+1):
        while seg+1<len(pts) and x>=pts[seg+1][0]: seg+=1
        x0,y0=pts[seg]
        if seg+1<len(pts):
            x1,y1=pts[seg+1]; dx=x1-x0
            yf=(float(y0)+(float(y1-y0)*float(x-x0)/float(dx))) if dx>0 else float(y0)
        else: yf=float(y0)
        if kind=='volume': out.append(max(0,min(64,int(yf))))
        elif kind=='pan': out.append(max(0,min(64,int(round(yf+32.0)))))
        else:
            # Positive IT pitch-envelope values raise pitch, so period shrinks.
            # Store a cheap runtime representation: optional octave doubling,
            # then an 8-bit Q8 delta around unity. This keeps the Z80 to one
            # 16x8 multiply instead of an exponential/16x16 multiply.
            factor=2.0**(-yf/24.0); fl=0
            if factor>=2.0:
                factor*=0.5; fl|=0x02
            if factor<1.0:
                fl|=0x01; mag=int(round((1.0-factor)*256.0))
            else:
                mag=int(round((factor-1.0)*256.0))
            out += bytes((max(0,min(255,mag)),fl))
    return bytes(out)

def _it_env_x(env,index:int)->int:
    points=env[1]
    if not points:return 0
    index=max(0,min(len(points)-1,int(index)))
    return int(points[index][0])&0xFFFF

def build_it_profile_patch(module:core.Module,sym:dict):
    profiles=list(getattr(module,'it_profiles',[]))
    if not profiles:return None
    ptr_addr=sym['it_profile_ptrs']; data_addr=sym['it_profile_data']; limit=sym['it_profile_limit']
    rec_size=44
    cursor=data_addr+rec_size*len(profiles)
    records=[]; curves=[]
    for prof in profiles:
        nna,dct,dca,fade,ve,pe,pie=prof
        vcurve=_it_env_curve(ve,'volume'); pcurve=_it_env_curve(pe,'pan'); picurve=_it_env_curve(pie,'pitch')
        vaddr=cursor if vcurve else 0; cursor+=len(vcurve)
        paddr=cursor if pcurve else 0; cursor+=len(pcurve)
        piaddr=cursor if picurve else 0; cursor+=len(picurve)
        rec=bytearray(rec_size)
        rec[0]=int(ve[0])&7; rec[1]=int(pe[0])&7; rec[2]=int(pie[0])&7
        rec[3]=int(nna)&3; rec[4]=int(dct)&3; rec[5]=int(dca)&3
        struct.pack_into('<H',rec,6,int(fade)&0xFFFF)
        def put(off,addr,curve,env,scale=1):
            maxt=(len(curve)//scale-1) if curve else 0
            struct.pack_into('<HHHHHH',rec,off,addr,maxt,_it_env_x(env,env[2]),_it_env_x(env,env[3]),_it_env_x(env,env[4]),_it_env_x(env,env[5]))
        put(8,vaddr,vcurve,ve,1); put(20,paddr,pcurve,pe,1); put(32,piaddr,picurve,pie,2)
        records.append(bytes(rec)); curves.extend((vcurve,pcurve,picurve))
    if cursor>limit:
        raise ValueError(f'IT envelope/profile data needs {cursor-data_addr} bytes but resident profile area has {limit-data_addr}')
    ptrs=bytearray(512)
    if len(profiles)>256: raise ValueError('IT profile pointer table supports at most 256 profiles')
    for i in range(len(profiles)): struct.pack_into('<H',ptrs,i*2,data_addr+i*rec_size)
    blob=b''.join(records)+b''.join(curves)
    return {'ptr_addr':ptr_addr,'ptrs':bytes(ptrs),'data_addr':data_addr,'blob':blob,'limit':limit,
            'profiles':len(profiles),'bytes':len(blob)}

def make_engine_template(module:core.Module,page_count:int,source_format:str,waves:list[dict],stream_base:int|None=None):
    if source_format=='S3M':
        engine_bin=S3M_ENGINE_BIN; sym=S3M_ENGINE_SYM
    elif source_format in ('IT-S3M','MODERN-S3M'):
        engine_bin=IT_S3M_ENGINE_BIN; sym=IT_S3M_ENGINE_SYM
    elif source_format=='IT':
        engine_bin=IT_ENGINE_BIN; sym=IT_ENGINE_SYM
    elif source_format=='MOD':
        engine_bin=MOD_ENGINE_BIN; sym=MOD_ENGINE_SYM
    elif source_format=='XM':
        engine_bin=XM_ENGINE_BIN; sym=XM_ENGINE_SYM
    else:
        raise ValueError(f'unsupported tracker engine format {source_format}')
    use_xm_engine=(source_format=='XM')
    use_it_engine=(source_format=='IT')
    t=bytearray(PAGE_SIZE)
    if stream_base is None: stream_base=stream_base_for(source_format)
    stream_offset=stream_base-PAGE_LOAD
    if len(engine_bin)>stream_offset:
        raise ValueError(f'compact engine is {len(engine_bin)} bytes and overlaps 0x{stream_base:04X} dynamic window')
    t[:len(engine_bin)]=engine_bin
    struct.pack_into('<H',t,PAGE_TOTAL_CFG-PAGE_LOAD,page_count)
    vo=sym['vol_lut']-PAGE_LOAD
    t[vo:vo+65]=(bytes(core.Compiler._level_reg(v,64) for v in range(65)) if use_it_engine else volume_lut(module))
    pinfo=None
    if use_xm_engine:
        pinfo=build_xm_profile_patch(module,sym,waves)
        if pinfo:
            t[pinfo['tone_addr']-PAGE_LOAD:pinfo['tone_addr']-PAGE_LOAD+64]=pinfo['tone_map']
            t[pinfo['ptr_addr']-PAGE_LOAD:pinfo['ptr_addr']-PAGE_LOAD+128]=pinfo['ptrs']
            off=pinfo['data_addr']-PAGE_LOAD
            t[off:off+len(pinfo['blob'])]=pinfo['blob']
    elif use_it_engine:
        pinfo=build_it_profile_patch(module,sym)
        if pinfo:
            t[pinfo['ptr_addr']-PAGE_LOAD:pinfo['ptr_addr']-PAGE_LOAD+512]=pinfo['ptrs']
            off=pinfo['data_addr']-PAGE_LOAD
            t[off:off+len(pinfo['blob'])]=pinfo['blob']
    return t,engine_bin,sym,pinfo

def split_semantic_pages(stream:bytes,rows:list[bytes],source_format:str=None):
    if len(stream)<compact_stream.HEADER_SIZE: raise ValueError('compact stream header truncated')
    alias_count=stream[38] if stream[4]>=3 else 0
    header_len=compact_stream.HEADER_SIZE + alias_count*8
    header=stream[:header_len]
    page_capacity=stream_page_capacity_for(source_format or '')
    pages=[]; cur=bytearray(header)
    for row in rows:
        if len(row)>page_capacity:
            raise ValueError(f'a single compact row is {len(row)} bytes, larger than dynamic page capacity')
        if len(cur)+len(row)>page_capacity:
            pages.append(bytes(cur)); cur=bytearray()
        cur+=row
    if len(cur)+1>page_capacity:
        pages.append(bytes(cur)); cur=bytearray()
    cur.append(0xFF); pages.append(bytes(cur))
    if len(pages)>MAX_SUPPORTED_PAGES:
        raise ValueError(f'compact row stream needs {len(pages)} pages; KSP 1.05 page-count maximum is {MAX_SUPPORTED_PAGES}')
    return pages

def build_ksp(module,source_format,stream,rows,semantic_stats,mwk,waves,title,source_name,output,compression):
    stream_base=stream_base_for(source_format); stream_offset=stream_base-PAGE_LOAD
    page_capacity=stream_page_capacity_for(source_format)
    chunks=split_semantic_pages(stream,rows,source_format); page_count=len(chunks)
    template,engine_bin,engine_sym,profile_info=make_engine_template(module,page_count,source_format,waves,stream_base)
    records=[]; payloads=[]
    for i,ch in enumerate(chunks):
        window=struct.pack('<H',len(ch))+ch
        overlay=struct.pack('<HH',stream_offset,len(window))+window
        stored,comp=maybe_zx0(overlay,compression)
        runtime=bytearray(template); runtime[stream_offset:stream_offset+len(window)]=window
        records.append({'index':i,'stream_bytes':len(ch),'overlay_bytes':len(overlay),'stored_bytes':len(stored),
                        'compression':comp,'runtime_crc':crc32(runtime)})
        payloads.append(stored)
    strings=bytearray()
    engine_names={'S3M':'Tracker2KSP ST3/S3M MoonSound engine','IT-S3M':'Tracker2KSP Impulse Tracker S3M MoonSound engine','IT':'Tracker2KSP native Impulse Tracker MoonSound engine','MODERN-S3M':'Tracker2KSP modern S3M MoonSound engine','MOD':'Tracker2KSP ProTracker MOD MoonSound engine','XM':'Tracker2KSP FastTracker II XM MoonSound engine'}
    ename=add_string(strings,engine_names[source_format]); tname=add_string(strings,title)
    metadata='\n'.join([
        'metadata_version=2','default_language=en',f'title={title}',f'game={title}',
        'source_platform=PC tracker module',f'source_format={source_format}',f'source_tracker={getattr(module,"it_tracker_name",getattr(module,"s3m_tracker_name",source_format))}',f's3m_cwtv=0x{getattr(module,"s3m_cwtv",0):04X}' if source_format in ('S3M','IT-S3M','MODERN-S3M') else 'tracker_profile=not_applicable',f'source_file={source_name}',
        f'source_sha256={sha256(module.raw)}','target_platform=MSX2','target_hardware=MoonSound / OPL4',
        'format=KSP 1.05',f'engine=native Z80 {source_format}-specific multi-page realtime engine',
        'conversion=compact rows/effects + shared MWK PCM payloads + INIT-time OPL4 header aliases; no rendered PCM and no pre-expanded tick register stream',
        f'initial_speed={module.speed}',f'initial_tempo={module.tempo}',f'active_channels={len(module.active_channels)}',
        f'custom_opl4_waves={len(waves)}',f'event_pages={page_count}','converter=tracker2ksp.py','converter_version=0.5.2'
    ])+'\n'; meta=metadata.encode()
    mwkp,mcomp=maybe_zx0(mwk,compression)
    engine_off=80; page_off=engine_off+64; track_off=page_off+page_count*24; resource_off=track_off+32
    string_off=resource_off+64; payload_off=string_off+len(strings); cursor=payload_off
    template_off=cursor; cursor+=len(template)
    for r,p in zip(records,payloads): r['payload_offset']=cursor; cursor+=len(p)
    mwk_off=cursor; cursor+=len(mwkp); meta_off=cursor; cursor+=len(meta); file_size=cursor
    engines=bytearray(64)
    struct.pack_into('<II',engines,0,ENGINE_MWK_REQUIRED|ENGINE_DYNAMIC_PAGES,HW_OPL4)
    struct.pack_into('<HHHHHHHHHHHH',engines,8,1,60,PAGE_LOAD,PAGE_SIZE,engine_sym['init'],engine_sym['play'],engine_sym['stop'],
                     DYNAMIC_GATEWAY_PLACEHOLDER,stream_base,0,page_count,0)
    engines[32]=COMP_NONE
    struct.pack_into('<IIIII',engines,36,template_off,len(template),len(template),crc32(template),ename)
    pages=bytearray(page_count*24)
    for i,r in enumerate(records):
        struct.pack_into('<HBBHHIIII',pages,i*24,0,PAGE_SPARSE,r['compression'],0,0,r['payload_offset'],r['stored_bytes'],r['overlay_bytes'],r['runtime_crc'])
    tracks=bytearray(32)
    struct.pack_into('<HHHHHHIIIII',tracks,0,0,0,TRACK_ONE_SHOT,0,NULL16,0,tname,round(semantic_stats['duration_seconds']*1000),NULL32,NULL32,0)
    resources=bytearray(64); resources[0:4]=b'MWK '
    struct.pack_into('<HBBIIIIII',resources,4,0,mcomp,0,mwk_off,len(mwkp),len(mwk),crc32(mwk),0,0)
    resources[32:36]=b'META'
    struct.pack_into('<HBBIIIIII',resources,36,0,COMP_NONE,0,meta_off,len(meta),len(meta),crc32(meta),0,0)
    header=bytearray(80); header[:4]=b'KSP1'; struct.pack_into('<HHII',header,4,80,KSP_MINOR,0,file_size)
    struct.pack_into('<IHH',header,16,engine_off,1,64); struct.pack_into('<IHH',header,24,page_off,page_count,24)
    struct.pack_into('<IHH',header,32,track_off,1,32); struct.pack_into('<IHH',header,40,resource_off,2,32)
    struct.pack_into('<II',header,48,string_off,len(strings)); struct.pack_into('<HHHH',header,56,0,1,NULL16,0)
    index=bytes(engines)+bytes(pages)+bytes(tracks)+bytes(resources)+bytes(strings)
    struct.pack_into('<I',header,68,crc32(index)); struct.pack_into('<I',header,64,0); struct.pack_into('<I',header,64,crc32(header))
    out=bytes(header)+index+bytes(template)+b''.join(payloads)+mwkp+meta
    assert len(out)==file_size
    output.parent.mkdir(parents=True,exist_ok=True); output.write_bytes(out)
    packed_pages=sum(r['stored_bytes'] for r in records); mapper_segments=(packed_pages+PAGE_SIZE-1)//PAGE_SIZE
    return {'status':'built','format':'KSP 1.05','converter_version':'0.5.2','input':str(module.path),'output':str(output),
            'title':title,'duration_ms':round(semantic_stats['duration_seconds']*1000),'output_bytes':len(out),'output_sha256':sha256(out),
            'engine':{'init':hex(engine_sym['init']),'play':hex(engine_sym['play']),'stop':hex(engine_sym['stop']),'play_hz':60,'hardware':'OPL4',
                      'resident_range':f'0x4000-0x{stream_base-1:04X} (code/state; persistent tracker state handoff via OPL4 RAM 0x2FFC00)','dynamic_window':f'0x{stream_base:04X}-0x7FFF','binary_bytes':len(engine_bin),'xm_ft2_profiles':profile_info['profiles'] if (profile_info and source_format=='XM') else 0,'xm_profile_bytes':profile_info['bytes'] if (profile_info and source_format=='XM') else 0,'it_profiles':profile_info['profiles'] if (profile_info and source_format=='IT') else 0,'it_profile_bytes':profile_info['bytes'] if (profile_info and source_format=='IT') else 0},
            'semantic_stream':{**semantic_stats,'raw_bytes':len(stream),'page_count':page_count,'page_capacity':page_capacity,
                               'packed_page_bytes':packed_pages,'mapper_segments_for_preload':mapper_segments,
                               'ksp1play_preload_eligible':page_count<=MAX_PRELOADED_PAGES and mapper_segments<=12,
                               'pages':[{k:('ZX0' if v==1 else 'none') if k=='compression' else v for k,v in r.items() if k!='payload_offset'} for r in records]},
            'mwk':{'revision':'0x0C','custom_tones':len(waves),'pcm_payload_bytes':sum(int(w['payload_bytes']) for w in waves),'shared_alias_tones':sum(1 for w in waves if w.get('init_header_patch')),'raw_bytes':len(mwk),'stored_bytes':len(mwkp),'compression':'ZX0' if mcomp else 'none','waves':waves},
            'ksp_format_changes_required':False,'ksp1play_0_48_changes_required':False,
            'tracker_profile':{'selected':(getattr(module,'mod_profile',source_format) if source_format=='MOD' else source_format),'s3m_cwtv':(f'0x{getattr(module,"s3m_cwtv",0):04X}' if source_format in ('S3M','IT-S3M','MODERN-S3M') else None),'creator':(getattr(module,'mod_profile','MOD') if source_format=='MOD' else getattr(module,'it_tracker_name',getattr(module,'s3m_tracker_name',source_format))),'default_panning_table':bool(getattr(module,'s3m_has_default_panning',False))},
            'accuracy_notes':['strict Scream Tracker 3 S3Ms use a dedicated ST3 engine with ST3 shared-effect-memory, combined-slide and retrigger timing rules','Impulse Tracker-authored S3Ms use the IT-S3M engine with command-local effect memory','native IMPM files use a physically separate true-IT engine and IT packed-pattern/sample loader','modern/non-ST3 S3Ms (OpenMPT/Schism/Orpheus-style) are kept out of the strict ST3 quirk profile and use the compatible S3M runtime','MOD uses a separate ProTracker/Paula engine binary','XM uses a separate FastTracker II engine with XM instrument/envelope state independent of linear-vs-Amiga frequency-table selection','ordinary note pitches are converted to OPL4 registers on the host; realtime pitch effects remain in the selected tracker engine domain']}

def main():
    ap=argparse.ArgumentParser(description='Convert S3M/IT-S3M/native-IT/modern-S3M/XM/MOD to compact realtime MoonSound KSP 1.05')
    ap.add_argument('input',type=Path); ap.add_argument('-o','--output',type=Path); ap.add_argument('--title')
    ap.add_argument('--start-order',type=int,default=0); ap.add_argument('--stop-order',type=int); ap.add_argument('--max-seconds',type=float,default=1800)
    ap.add_argument('--compression',choices=('auto','zx0','none'),default='auto'); ap.add_argument('--report',type=Path)
    a=ap.parse_args(); out=a.output or a.input.with_suffix('.ksp')
    if out.exists() and out.is_dir(): out=out/a.input.with_suffix('.ksp').name
    elif out.suffix.lower()!='.ksp': out=out.with_suffix('.ksp')
    m,fmt=module_formats.parse_module(a.input)
    stop=a.stop_order if a.stop_order is not None else next((i for i in range(a.start_order,len(m.orders)) if m.orders[i]==255),len(m.orders))
    cc=compact_stream.CompactCompiler(m,fmt,a.start_order,stop,a.max_seconds)
    stream,rows,stats=cc.compile(); mwk,waves,patches=build_mwk(m,cc.bank.order)
    stream=compact_stream.attach_alias_patches(stream,rows,patches)
    stats['semantic_stream_bytes']=len(stream); stats['opl4_init_header_aliases']=len(patches)
    report=build_ksp(m,fmt,stream,rows,stats,mwk,waves,a.title or m.title or a.input.stem,a.input.name,out,a.compression)
    text=json.dumps(report,indent=2,ensure_ascii=False); print(text)
    if a.report: a.report.write_text(text+'\n',encoding='utf-8')
    return 0
if __name__=='__main__': raise SystemExit(main())
