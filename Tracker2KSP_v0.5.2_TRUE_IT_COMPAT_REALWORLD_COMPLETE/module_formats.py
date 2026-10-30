from __future__ import annotations
import struct, math, io, subprocess, shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import _s3m2opl4_backend as core


def _s8(x): return x-256 if x>127 else x

def _decode_delta8(data: bytes) -> bytes:
    out=bytearray(); acc=0
    for x in data:
        acc=(acc+_s8(x)) & 0xff; out.append(acc)
    return bytes(out)

def _decode_delta16(data: bytes) -> bytes:
    # Downconvert signed 16-bit delta PCM to signed 8-bit.
    out=bytearray(); acc=0
    for i in range(0,len(data)-1,2):
        d=int.from_bytes(data[i:i+2],'little',signed=True)
        acc=(acc+d) & 0xffff
        s=acc if acc<0x8000 else acc-0x10000
        out.append((s>>8)&0xff)
    return bytes(out)

def _limit_sample(data: bytes, loop_start: int, loop_end: int, c2spd: int, max_len: int = 65535):
    if len(data) <= max_len:
        return data, loop_start, loop_end, c2spd
    ratio = len(data) / max_len
    out = bytes(data[min(len(data)-1, int(i*ratio))] for i in range(max_len))
    return out, int(loop_start/ratio), min(max_len, int(loop_end/ratio)), max(1, int(c2spd/ratio))

def _note_byte(note_index:int)->int:
    # Internal S3M-style note byte, C-0 = 0x00. XM note 1 is C-0.
    return ((note_index//12)<<4)|(note_index%12)

MOD_PT_PERIODS=(3424,3232,3048,2880,2712,2560,2416,2280,2152,2032,1920,1812,
    1712,1616,1524,1440,1356,1280,1208,1140,1076,1016,960,907,
    856,808,762,720,678,640,604,570,538,508,480,453,
    428,404,381,360,339,320,302,285,269,254,240,226,
    214,202,190,180,170,160,151,143,135,127,120,113,
    107,101,95,90,85,80,75,71,67,63,60,56,
    53,50,47,45,42,40,37,35,33,31,30,28)
MOD_TUNED_PERIODS=(
    1712,1616,1524,1440,1356,1280,1208,1140,1076,1016,960,907,
    1700,1604,1514,1430,1348,1274,1202,1134,1070,1010,954,900,
    1688,1592,1504,1418,1340,1264,1194,1126,1064,1004,948,894,
    1676,1582,1492,1408,1330,1256,1184,1118,1056,996,940,888,
    1664,1570,1482,1398,1320,1246,1176,1110,1048,990,934,882,
    1652,1558,1472,1388,1310,1238,1168,1102,1040,982,926,874,
    1640,1548,1460,1378,1302,1228,1160,1094,1032,974,920,868,
    1628,1536,1450,1368,1292,1220,1150,1086,1026,968,914,862,
    1814,1712,1616,1524,1440,1356,1280,1208,1140,1076,1016,960,
    1800,1700,1604,1514,1430,1350,1272,1202,1134,1070,1010,954,
    1788,1688,1592,1504,1418,1340,1264,1194,1126,1064,1004,948,
    1774,1676,1582,1492,1408,1330,1256,1184,1118,1056,996,940,
    1762,1664,1570,1482,1398,1320,1246,1176,1110,1048,988,934,
    1750,1652,1558,1472,1388,1310,1238,1168,1102,1040,982,926,
    1736,1640,1548,1460,1378,1302,1228,1160,1094,1032,974,920,
    1724,1628,1536,1450,1368,1292,1220,1150,1086,1026,968,914)


def _mod_note_index(period:int)->Optional[int]:
    if period<=0 or period==0xFFF: return None
    # Match OpenMPT ReadMODPatternEntry: nearest entry in the canonical
    # 7-octave ProTracker table. Table index 36 is C-2 in our internal domain.
    note=len(MOD_PT_PERIODS)-1
    for i,p in enumerate(MOD_PT_PERIODS):
        if period>=p:
            if period!=p and i and MOD_PT_PERIODS[i-1]-period < period-p:
                note=i-1
            else: note=i
            break
    return note+12


def _mod_effect(eff:int,param:int, vol:Optional[int]=None, *, vblank:bool=False, startrekker:bool=False, noisetracker:bool=False):
    cmd=None; p=param
    if eff==0 and param: cmd=10 # 0xy arpeggio
    elif eff==1: cmd=6          # 1xx porta up (no MOD parameter memory)
    elif eff==2: cmd=5          # 2xx porta down (no MOD parameter memory)
    elif eff==3: cmd=7          # 3xx tone porta (has its own speed memory)
    elif eff==4: cmd=8          # 4xy vibrato (nibble memory)
    elif eff==5: cmd=12         # 5xy tone porta + volume slide
    elif eff==6: cmd=11         # 6xy vibrato + volume slide
    elif eff==7: cmd=40         # private MOD tremolo
    elif eff==8: cmd=24         # 8xx panning
    elif eff==9: cmd=15         # 9xx sample offset (memory)
    elif eff==0xA: cmd=4        # Axy volume slide (no MOD parameter memory)
    elif eff==0xB: cmd=2        # Bxx position jump
    elif eff==0xC: vol=min(64,param)
    elif eff==0xD:
        cmd=3
        # NoiseTracker ignores the break-row parameter entirely.
        p=0 if noisetracker else ((param>>4)*10+(param&15))
    elif eff==0xE:
        sub=param>>4; lo=param&15
        if sub==0x0: cmd=72; p=lo          # E0x Amiga LED filter (state only / no-op on OPL4)
        elif sub==0x1: cmd=73; p=lo        # E1x fine porta up
        elif sub==0x2: cmd=74; p=lo        # E2x fine porta down
        elif sub==0x3: cmd=75; p=lo        # E3x glissando control
        elif sub==0x4: cmd=76; p=lo        # E4x vibrato waveform
        elif sub==0x5: cmd=77; p=lo        # E5x set finetune
        elif sub==0x6: cmd=78; p=lo        # E6x pattern loop (host flattened)
        elif sub==0x7: cmd=79; p=lo        # E7x tremolo waveform
        elif sub==0x8: cmd=80; p=lo        # E8x 4-bit panning
        elif sub==0x9: cmd=17; p=lo        # E9x retrigger
        elif sub==0xA: cmd=81; p=lo        # EAx fine volume up
        elif sub==0xB: cmd=82; p=lo        # EBx fine volume down
        elif sub==0xC: cmd=27; p=lo        # ECx note cut
        elif sub==0xD: cmd=19; p=0xD0|lo   # EDx note delay
        elif sub==0xE: cmd=83; p=lo        # EEx pattern delay
        elif sub==0xF: cmd=84; p=lo        # EFx invert loop / funk repeat
    elif eff==0xF and param>0:
        if vblank:
            cmd=1; p=min(param,31) if startrekker else param
        elif param<32: cmd=1
        else: cmd=20
    return cmd,p,vol


def _mod_magic(sig:bytes):
    """Return (channels, profile, flags) for OpenMPT-compatible 31-sample MOD magics."""
    flags={'vblank':False,'startrekker':False,'noisetracker':False,'generic':False,'swap_bytes':False,'delta':False,'pattern_offset':1084}
    if sig in (b'M.K.',b'M!K!',b'PATT',b'NSMS',b'LARD'):
        return 4,'PROTRACKER',flags
    if sig in (b'M&K!',b'FEST',b'N.T.'):
        flags.update(vblank=True,noisetracker=True)
        return 4,('NOISETRACKER' if sig==b'N.T.' else 'HMN'),flags
    if sig in (b'OKTA',b'OCTA'):
        flags['generic']=True; return 8,'OKTALYZER',flags
    if sig in (b'CD81',b'CD61'):
        flags['generic']=True; return sig[2]-48,'OCTALYSER',flags
    if len(sig)==4 and sig[0] in (ord('M'),ord('8')) and sig[1:]==b'\0\0\0':
        flags.update(delta=True,generic=True); return (8 if sig[0]==ord('8') else 4),'INCONEXIA',flags
    if sig[:3]==b'FA0' and sig[3:4] in b'45678':
        flags.update(generic=True,pattern_offset=1088); return sig[3]-48,'DIGITAL_TRACKER',flags
    if sig[:3] in (b'FLT',b'EXO') and sig[3:4] in (b'4',b'8'):
        flags.update(vblank=True,startrekker=True); return sig[3]-48,'STARTREKKER',flags
    if sig[:3]==b'TDZ' and 49<=sig[3]<=57:
        flags['generic']=True; return sig[3]-48,'TAKETRACKER',flags
    if sig==b'.M.K':
        flags['swap_bytes']=True; return 4,'DMF_HACK',flags
    if sig==b'WARD':
        flags['generic']=True; return 8,'WARD',flags
    try: s=sig.decode('ascii')
    except: s=''
    ch=None
    if len(s)==4 and s[0].isdigit() and s[1:]=='CHN': ch=int(s[0])
    elif len(s)==4 and s[:2].isdigit() and s[2:] in ('CH','CN'): ch=int(s[:2])
    elif s.endswith('CHN') and s[:-3].isdigit(): ch=int(s[:-3])
    elif s.endswith('CH') and s[:-2].isdigit(): ch=int(s[:-2])
    if ch:
        flags['generic']=True; return ch,'GENERIC_MOD',flags
    return None,None,flags


def _mod_swap16(blob:bytes)->bytes:
    if len(blob)%2: blob+=b'\0'
    out=bytearray(len(blob))
    for i in range(0,len(blob),2): out[i],out[i+1]=blob[i+1],blob[i]
    return bytes(out)


def _decode_mod_adpcm(raw: bytes, sample_len: int) -> bytes:
    """Decode OpenMPT-compatible MOD 4-bit ADPCM payload after the ADPCM marker."""
    if len(raw) < 16:
        return b''
    table=[_s8(x) for x in raw[:16]]
    out=bytearray(); acc=0
    for x in raw[16:16+(sample_len+1)//2]:
        acc=(acc+table[x&15]) & 0xff; out.append(acc)
        if len(out)>=sample_len: break
        acc=(acc+table[(x>>4)&15]) & 0xff; out.append(acc)
        if len(out)>=sample_len: break
    return bytes(out)


class _LSBBitReader:
    """Small LSB-first bit reader used by Impulse Tracker sample compression."""
    __slots__=("data","bitpos")
    def __init__(self,data:bytes): self.data=data; self.bitpos=0
    def read(self,n:int)->int:
        if n<=0: return 0
        end=self.bitpos+n
        if end>len(self.data)*8: raise ValueError('truncated IT compressed sample block')
        v=0; p=self.bitpos
        for i in range(n):
            v |= ((self.data[p>>3]>>(p&7))&1)<<i; p+=1
        self.bitpos=end
        return v


def _sign_extend(v:int,bits:int)->int:
    sign=1<<(bits-1)
    return (v^sign)-sign


def _decode_it214_channel(payload:bytes, samples:int, bit16:bool, it215:bool)->list[int]:
    """Decode one IT 2.14/2.15 compressed channel to signed integers.

    IT resets the adaptive bit width at every compressed block. The 2.15
    variant performs a second integration pass (double-delta coding).
    """
    result=[]; pos=0
    block_samples=0x4000 if bit16 else 0x8000
    maxbits=17 if bit16 else 9
    while len(result)<samples:
        if pos+2>len(payload): raise ValueError('truncated IT compressed sample block header')
        clen=int.from_bytes(payload[pos:pos+2],'little'); pos+=2
        if clen<=0 or pos+clen>len(payload): raise ValueError('invalid IT compressed sample block size')
        br=_LSBBitReader(payload[pos:pos+clen]); pos+=clen
        want=min(block_samples,samples-len(result)); width=maxbits; d1=0; d2=0
        produced=0
        while produced<want:
            value=br.read(width)
            # ITTECH's three adaptive-width escape forms. These are the same
            # forms used by OpenMPT / Schism for IT214 and IT215 streams.
            if width < 7:
                if value == (1 << (width-1)):
                    nw=br.read(4 if bit16 else 3)+1
                    width=nw if nw < width else nw+1
                    if width<1 or width>maxbits: raise ValueError('invalid IT compressed bit width')
                    continue
            elif width < maxbits:
                border=((0xFFFF if bit16 else 0xFF) >> (maxbits-width)) - (8 if bit16 else 4)
                span=16 if bit16 else 8
                if value > border-span and value <= border:
                    nw=value-(border-span)
                    width=nw if nw < width else nw+1
                    if width<1 or width>maxbits: raise ValueError('invalid IT compressed bit width')
                    continue
            else:
                flag=0x10000 if bit16 else 0x100
                if value & flag:
                    width=(value+1)&0xFF
                    if width<1 or width>maxbits: raise ValueError('invalid IT compressed bit width')
                    continue
            val=_sign_extend(value,width)
            mask=0xFFFF if bit16 else 0xFF
            d1=(d1+val)&mask
            d2=(d2+_sign_extend(d1,16 if bit16 else 8))&mask
            outv=d2 if it215 else d1
            result.append(_sign_extend(outv,16 if bit16 else 8)); produced+=1
    return result


def _decode_it_compressed(raw:bytes, frames:int, bit16:bool, stereo:bool, it215:bool)->bytes:
    """Decode IT compressed PCM and downmix to signed mono 8-bit.

    Stereo channels are encoded one after another. Since compressed blocks are
    variable-size, decode a channel while also returning its consumed length.
    """
    def one_channel(blob:bytes,count:int):
        vals=[]; pos=0; block_samples=0x4000 if bit16 else 0x8000; maxbits=17 if bit16 else 9
        while len(vals)<count:
            if pos+2>len(blob): raise ValueError('truncated IT compressed sample block header')
            clen=int.from_bytes(blob[pos:pos+2],'little'); pos+=2
            if clen<=0 or pos+clen>len(blob): raise ValueError('invalid IT compressed sample block size')
            br=_LSBBitReader(blob[pos:pos+clen]); pos+=clen
            want=min(block_samples,count-len(vals)); width=maxbits; d1=0; d2=0; produced=0
            while produced<want:
                value=br.read(width)
                if width<7:
                    if value==(1<<(width-1)):
                        nw=br.read(4 if bit16 else 3)+1; width=nw if nw<width else nw+1
                        if not 1<=width<=maxbits: raise ValueError('invalid IT compressed bit width')
                        continue
                elif width<maxbits:
                    border=((0xFFFF if bit16 else 0xFF)>>(maxbits-width))-(8 if bit16 else 4)
                    span=16 if bit16 else 8
                    if value>border-span and value<=border:
                        nw=value-(border-span); width=nw if nw<width else nw+1
                        if not 1<=width<=maxbits: raise ValueError('invalid IT compressed bit width')
                        continue
                else:
                    flag=0x10000 if bit16 else 0x100
                    if value&flag:
                        width=(value+1)&0xFF
                        if not 1<=width<=maxbits: raise ValueError('invalid IT compressed bit width')
                        continue
                val=_sign_extend(value,width); mask=0xFFFF if bit16 else 0xFF; sbits=16 if bit16 else 8
                d1=(d1+val)&mask; d2=(d2+_sign_extend(d1,sbits))&mask
                vals.append(_sign_extend(d2 if it215 else d1,sbits)); produced+=1
        return vals,pos
    left,used=one_channel(raw,frames)
    if stereo:
        right,used2=one_channel(raw[used:],frames); used+=used2
    else: right=None
    out=bytearray(frames)
    for i,l in enumerate(left):
        if right is not None: l=(l+right[i])//2
        if bit16: l >>= 8
        out[i]=l&0xFF
    return bytes(out)


def _decode_it_pcm(raw:bytes, frames:int, flags:int, cvt:int, cwtv:int)->bytes:
    bit16=bool(flags&0x02); stereo=bool(flags&0x04); compressed=bool(flags&0x08)
    if compressed:
        # IT 2.15 compression (introduced in 2.14p1) is double-delta coded.
        return _decode_it_compressed(raw,frames,bit16,stereo,cwtv>=0x0215)
    bps=2 if bit16 else 1; need=frames*bps*(2 if stereo else 1)
    if len(raw)<need: raw=raw+b'\0'*(need-len(raw))
    signed=bool(cvt&0x01); big=bool(cvt&0x02); delta=bool(cvt&0x04); byte_delta=bool(cvt&0x08)
    chans=[]; off=0
    for _ in range(2 if stereo else 1):
        vals=[]; acc=0
        if bit16:
            for i in range(frames):
                q=raw[off+i*2:off+i*2+2]
                v=int.from_bytes(q,'big' if big else 'little',signed=False)
                if delta:
                    acc=(acc+v)&0xFFFF; v=acc
                elif byte_delta:
                    # PTM-style byte delta: integrate each byte independently.
                    lo=q[0]; hi=q[1]
                    if i==0: alo=ahi=0
                    alo=(alo+lo)&0xFF; ahi=(ahi+hi)&0xFF
                    v=(ahi<<8)|alo if not big else (alo<<8)|ahi
                if not signed: v^=0x8000
                vals.append(_sign_extend(v,16))
            off+=frames*2
        else:
            for i in range(frames):
                v=raw[off+i]
                if delta or byte_delta: acc=(acc+v)&0xFF; v=acc
                if not signed: v^=0x80
                vals.append(_sign_extend(v,8))
            off+=frames
        chans.append(vals)
    out=bytearray(frames)
    for i in range(frames):
        v=chans[0][i]
        if len(chans)>1: v=(v+chans[1][i])//2
        if bit16: v>>=8
        out[i]=v&0xFF
    return bytes(out)


def _parse_it_envelope(buf:bytes,off:int,kind:str):
    if off+82>len(buf): return {'flags':0,'points':()}
    flg,num,lpb,lpe,slb,sle=buf[off:off+6]; num=min(25,num)
    pts=[]; p=off+6
    for _ in range(num):
        y=buf[p]; x=int.from_bytes(buf[p+1:p+3],'little'); p+=3
        if kind!='volume': y=_s8(y)
        pts.append((x,y))
    return {'flags':flg&0x8F,'points':tuple(pts),'loop_start':lpb,'loop_end':lpe,'sustain_start':slb,'sustain_end':sle}


def _parse_it_instrument(blob:bytes,cmwt:int):
    if not blob.startswith(b'IMPI'): raise ValueError('bad IT instrument signature')
    if cmwt<0x0200:
        raise ValueError('old-format IT instruments (Cmwt < 2.00) are not supported yet')
    if len(blob)<554: raise ValueError('truncated IT instrument header')
    keymap=[]
    for i in range(120): keymap.append((blob[0x40+i*2],blob[0x41+i*2]))
    return {
        'name':blob[0x20:0x20+26].split(b'\0',1)[0].decode('cp437','replace').rstrip(),
        'nna':blob[0x11], 'dct':blob[0x12], 'dca':blob[0x13],
        'fadeout':int.from_bytes(blob[0x14:0x16],'little'), 'pps':_s8(blob[0x16]), 'ppc':blob[0x17],
        'global_volume':blob[0x18], 'default_pan':blob[0x19], 'random_volume':blob[0x1A], 'random_pan':blob[0x1B],
        'keymap':tuple(keymap), 'vol_env':_parse_it_envelope(blob,0x130,'volume'),
        'pan_env':_parse_it_envelope(blob,0x182,'pan'), 'pitch_env':_parse_it_envelope(blob,0x1D4,'pitch'),
    }



def _estimate_mod_duration(patterns, orders, *, vblank: bool) -> float:
    """Small MOD timing model used only for OpenMPT-style VBlank detection.

    It follows the sequence-level effects that materially alter duration
    (Fxx, Bxx, Dxx, E6x and EEx).  The heuristic is deliberately bounded and
    is not used for actual conversion playback.
    """
    if not orders:
        return 0.0
    speed=6; tempo=125; order=0; row=0; seconds=0.0
    # Per-channel E6 loop state, matching the later channel-order walk.
    loop_start={}; loop_count={}
    visited={}
    steps=0
    while 0 <= order < len(orders) and steps < 200000 and seconds < 7200.0:
        patidx=orders[order]
        if patidx >= len(patterns):
            order += 1; row=0; continue
        pat=patterns[patidx]
        if row >= len(pat):
            order += 1; row=0; continue
        key=(order,row,speed,tempo,tuple(sorted(loop_start.items())),tuple(sorted(loop_count.items())))
        n=visited.get(key,0)
        if n>=2:
            break
        visited[key]=n+1
        evs=sorted(pat[row], key=lambda e:e.ch)
        jump=None; brk=None; loop_to=None; pat_delay=0
        row_speed=speed; row_tempo=tempo
        has_speed=False; has_tempo=False
        for e in evs:
            eff=int(getattr(e,'mod_raw_effect',-1)); param=int(getattr(e,'mod_raw_param',0))
            if eff==0xF and param:
                if vblank:
                    speed=max(1,param)
                elif param < 32:
                    speed=max(1,param); has_speed=True
                else:
                    tempo=max(32,param); has_tempo=True
            elif eff==0xB:
                jump=param
            elif eff==0xD:
                brk=((param>>4)*10 + (param&15))
            elif eff==0xE:
                sub=param>>4; lo=param&15
                if sub==0x6:
                    if lo==0:
                        loop_start[e.ch]=row
                    else:
                        cnt=loop_count.get(e.ch,0)
                        if cnt==0: cnt=lo
                        if cnt>0:
                            loop_to=loop_start.get(e.ch,0)
                            cnt-=1
                            loop_count[e.ch]=cnt
                elif sub==0xE:
                    pat_delay=max(pat_delay,lo)
        # Approximate PT's tick-1 tempo quirk with the timing state that was
        # active on entry to the row. This is sufficient for the 8-minute
        # VBlank detector and avoids circular dependence on the compiler.
        tick_tempo = 125 if vblank else max(32,row_tempo)
        seconds += max(1,row_speed) * (pat_delay+1) * (2.5/tick_tempo)
        if loop_to is not None:
            row=loop_to
        elif jump is not None or brk is not None:
            order=(jump if jump is not None else order+1)
            row=(brk or 0)
        else:
            row+=1
            if row>=len(pat): order+=1; row=0
        steps+=1
    return seconds


def _remap_mod_vblank_effects(patterns, *, startrekker: bool=False, noisetracker: bool=False):
    for pat in patterns:
        for row in pat:
            for e in row:
                if int(getattr(e,'mod_raw_effect',-1)) != 0xF:
                    continue
                raw=int(getattr(e,'mod_raw_param',0))
                cmd,p,vol=_mod_effect(0xF,raw,getattr(e,'vol',None),vblank=True,startrekker=startrekker,noisetracker=noisetracker)
                e.cmd=cmd; e.param=(p if cmd is not None else None); e.vol=vol

def parse_mod(path:Path)->core.Module:
    b=path.read_bytes()
    if len(b)<1084: raise ValueError('not a valid 31-sample MOD')
    sig=b[1080:1084]
    channels,profile,flags=_mod_magic(sig)
    if not channels: raise ValueError(f'unsupported/unknown MOD signature {sig!r}')
    # The resident OPL4 player has 24 hardware voices. Reject wider MODs cleanly
    # instead of silently overrunning the fixed channel-state arrays.
    if channels>24: raise ValueError(f'MOD has {channels} channels; OPL4 runtime supports at most 24')
    raw=b
    if flags['swap_bytes']:
        # Apocalypse Abyss .DMF-derived MODs swap byte pairs in header/pattern area.
        # Match OpenMPT sufficiently for ordinary sample/pattern decoding.
        raw=_mod_swap16(b)
        sig=raw[1080:1084]
    title=raw[:20].split(b'\0')[0].decode('cp437','replace').rstrip()
    samples:Dict[int,core.Sample]={}; sample_meta=[]
    only_amiga_notes=True; has_rep_len0=False; has_empty_sample_vol64=False; has_long_samples=False
    for i in range(31):
        o=20+i*30
        name=raw[o:o+22].split(b'\0')[0].decode('cp437','replace').rstrip()
        length=int.from_bytes(raw[o+22:o+24],'big')*2
        ft=raw[o+24]&15
        if profile=='HMN':
            # His Master's Noise writes the opposite finetune sign.
            ft=(-ft)&15
        finetune=ft-16 if ft>=8 else ft
        vol=min(64,raw[o+25])
        lb=int.from_bytes(raw[o+26:o+28],'big')*2; ll=int.from_bytes(raw[o+28:o+30],'big')*2
        has_rep_len0 |= bool(length and ll==0)
        has_long_samples |= bool(length>65535)
        has_empty_sample_vol64 |= bool(not length and vol==64)
        # Store native MOD finetune nibble for exact ProTracker period lookup.
        c2=max(1,int(round(core.PERIOD_CLOCK/428.0)))
        sample_meta.append((name,length,lb,ll,vol,c2,ft))
    songlen=raw[950]
    if songlen>128: songlen=128
    if songlen==0:
        songlen=128
        while songlen>1 and raw[952+songlen-1]==0: songlen-=1
    restart=raw[951]
    orders=list(raw[952:952+songlen])
    # Startrekker FLT8 stores a logical 8-channel pattern as an even/odd pair
    # of 4-channel physical patterns and order numbers reference those halves.
    flt8=(profile=='STARTREKKER' and channels==8)
    if flt8: orders=[x//2 for x in orders]
    pat_count=(max(orders)+1) if orders else 0
    read_channels=4 if flt8 else channels
    physical_patterns=(pat_count*2 if flt8 else pat_count)
    po=flags['pattern_offset']; patterns=[]
    max_panning=0; left_panning=False; extended_panning=False
    sample_swap_detected=False; has_tempo_commands=False; definitely_cia=has_long_samples
    if flt8: patterns=[[[] for _ in range(64)] for _ in range(pat_count)]
    for pi in range(physical_patterns):
        rows=([[] for _ in range(64)] if not flt8 else patterns[pi//2])
        base_ch=(4 if flt8 and (pi&1) else 0)
        last_instrument=[0]*read_channels
        instr_without_note=[0]*read_channels
        for r in range(64):
            has_speed_on_row=False; has_tempo_on_row=False
            for rch in range(read_channels):
                x=raw[po:po+4]
                if len(x)<4: x=x+b'\0'*(4-len(x))
                po+=4
                period=((x[0]&15)<<8)|x[1]; ins=(x[0]&0xF0)|(x[2]>>4); eff=x[2]&15; param=x[3]
                if eff==0x8:
                    max_panning=max(max_panning,param)
                    if param<0x80: left_panning=True
                    elif param>0x8F and param!=0xA4: extended_panning=True
                elif eff==0xE and (param&0xF0)==0x80:
                    max_panning=max(max_panning,(param&15)<<4)
                ni=_mod_note_index(period); note=_note_byte(ni) if ni is not None else None
                if period and not (113<=period<=856): only_amiga_notes=False
                if eff==0xF and param:
                    if param<32: has_speed_on_row=True
                    else:
                        has_tempo_on_row=True
                        if param<100: has_tempo_commands=True
                if not flt8:
                    if note is None and ins>0:
                        if last_instrument[rch]>0 and last_instrument[rch]!=ins:
                            instr_without_note[rch]+=1
                            if instr_without_note[rch]>=4: sample_swap_detected=True
                    elif note is not None:
                        instr_without_note[rch]=0
                    if ins: last_instrument[rch]=ins
                cmd,p,vol=_mod_effect(eff,param,vblank=flags['vblank'],startrekker=flags['startrekker'],noisetracker=flags['noisetracker'])
                if note is not None or ins or vol is not None or cmd is not None:
                    ev=core.Event(ch=base_ch+rch,note=note,ins=ins or None,vol=vol,cmd=cmd,param=p if cmd else None)
                    ev.mod_period=period or 0; ev.mod_raw_effect=eff; ev.mod_raw_param=param
                    rows[r].append(ev)
            if has_speed_on_row and has_tempo_on_row:
                definitely_cia=True
        if not flt8: patterns.append(rows)
    data_pos=po; any_adpcm=False
    for i,(name,length,lb,ll,vol,c2,ft) in enumerate(sample_meta,1):
        if length and not flags['delta'] and b[data_pos:data_pos+5]==b'ADPCM':
            need=16+(length+1)//2
            packed=b[data_pos+5:data_pos+5+need]
            data_pos += 5+len(packed)
            data=_decode_mod_adpcm(packed,length); any_adpcm=True
        else:
            enc=b[data_pos:data_pos+length]; data_pos+=length
            if flags['delta']:
                # Inconexia's special M\0\0\0 / 8\0\0\0 modules use signed 8-bit delta PCM.
                data=_decode_delta8(enc)
            else: data=enc
        le=min(len(data),lb+ll); looped=ll>2 and le>lb
        smp=core.Sample(i,name,len(data),lb,le,vol,1 if looped else 0,c2,0,data)
        smp.mod_finetune=ft; smp.mod_finetune_signed=(ft-16 if ft>=8 else ft)
        samples[i]=smp
    chset=[255]*32
    for ch in range(channels): chset[ch]=0 if ch%4 in (0,3) else 8
    m=core.Module(path,b,title,orders,patterns,samples,chset,6,125,64,0,1)
    m.source_format='MOD'; m.offset_quantum=256
    m.mod_signature=sig.decode('latin1','replace'); m.mod_profile=profile
    m.mod_startrekker=flags['startrekker']; m.mod_noisetracker=flags['noisetracker']
    m.mod_generic=flags['generic']; m.mod_restart=restart
    m.mod_only_amiga_notes=only_amiga_notes; m.mod_has_rep_len0=has_rep_len0
    canonical_pt=bool(profile=='PROTRACKER' and only_amiga_notes and not has_rep_len0)
    # OpenMPT treats low-valued 8xx commands in canonical 4ch ProTracker files
    # as sync markers rather than panning. Generic multichannel modules keep them.
    m.mod_ignore_panning=bool(flags['delta'] or (profile in ('NOISETRACKER','HMN','STARTREKKER')) or (canonical_pt and max_panning<0x30))
    m.mod_fix_7bit_panning=bool(flags['generic'] and left_panning and not extended_panning and max_panning>=0x30)
    m.mod_ft2_tremolo_ramp=bool(flags['generic'] or sig==b'M!K!')
    m.mod_adpcm=any_adpcm
    # OpenMPT also enables sample swapping after detecting four consecutive
    # instrument-only swaps in a pattern, even outside strict canonical PT.
    m.mod_sample_swap=bool(canonical_pt or sample_swap_detected)
    m.mod_sample_swap_detected=sample_swap_detected
    m.mod_one_shot_loops=bool(canonical_pt and max_panning<0x30 and restart!=0x7F)
    m.mod_out_of_range_delay=canonical_pt
    m.mod_pt_mode=canonical_pt
    m.mod_amiga_limits=canonical_pt
    # M.K./M!K! files are ambiguous between CIA and old VBlank timing. Match
    # OpenMPT's high-value heuristic: only suspicious low tempo commands, no
    # strong CIA evidence, and a CIA interpretation of at least eight minutes.
    detected_vblank=bool(flags['vblank'])
    if not detected_vblank and sig in (b'M.K.',b'M!K!') and has_tempo_commands and not definitely_cia:
        cia_len=_estimate_mod_duration(patterns,orders,vblank=False)
        vb_len=_estimate_mod_duration(patterns,orders,vblank=True)
        if cia_len>=480.0 and vb_len<cia_len:
            detected_vblank=True
            _remap_mod_vblank_effects(patterns)
            if profile=='PROTRACKER': profile='PROTRACKER_VBLANK'; m.mod_profile=profile
        m.mod_cia_duration_probe=cia_len; m.mod_vblank_duration_probe=vb_len
    m.mod_vblank=detected_vblank
    # Treat 0x78 and 0x7F as tracker markers rather than usable restart positions in the common PT/ST cases.
    m.mod_restart_valid=bool(restart<songlen and restart not in (0x78,0x7F))
    return m

def _decode_xm_adpcm(raw: bytes, sample_len: int) -> bytes:
    """Decode ModPlug's XM 4-bit ADPCM (16-byte signed delta table + nibbles)."""
    if len(raw) < 16:
        return b''
    table=[_s8(x) for x in raw[:16]]
    out=bytearray(); acc=0
    for x in raw[16:16+(sample_len+1)//2]:
        acc=(acc+table[x&15]) & 0xff; out.append(acc)
        if len(out)>=sample_len: break
        acc=(acc+table[(x>>4)&15]) & 0xff; out.append(acc)
        if len(out)>=sample_len: break
    return bytes(out)


def _xm_is_ogg_chunk(raw: bytes) -> bool:
    # OggMod / OXM stores a 32-bit original PCM byte count followed by one
    # complete Ogg Vorbis stream in the sample data chunk.
    return len(raw) >= 8 and raw[4:8] == b'OggS'


def _decode_xm_ogg(raw: bytes, typ: int) -> bytes:
    """Decode an OggMod/OXM sample to signed 8-bit mono PCM.

    OpenMPT treats the first dword as the original PCM byte count and uses the
    XM sample flags only for the expected 8/16-bit and mono/stereo geometry;
    the Vorbis stream's sample rate does not alter XM pitch.  We prefer the
    Python soundfile backend when available and fall back to ffmpeg.
    """
    if not _xm_is_ogg_chunk(raw):
        raise ValueError('not an OggMod/OXM sample chunk')
    original_size=struct.unpack_from('<I',raw,0)[0]
    is16=bool(typ & 0x10); stereo=bool(typ & 0x20)
    div=(2 if is16 else 1)*(2 if stereo else 1)
    expected_frames=(original_size // div) if div else 0
    ogg=raw[4:]
    pcm16=None
    try:
        import soundfile as sf
        data,_rate=sf.read(io.BytesIO(ogg),dtype='int16',always_2d=True)
        # The OPL4 path is mono. OpenMPT's OXM reader honours the declared XM
        # channel geometry; averaging decoded channels is the closest mono fold.
        if data.shape[1] > 1:
            # int32 avoids int16 overflow while averaging.
            mono=(data.astype('int32').sum(axis=1)//data.shape[1]).astype('int16')
        else:
            mono=data[:,0]
        pcm16=mono.tobytes()
    except Exception:
        ffmpeg=shutil.which('ffmpeg')
        if ffmpeg:
            proc=subprocess.run([ffmpeg,'-v','error','-i','pipe:0','-f','s16le','-ac','1','pipe:1'],
                                input=ogg,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
            if proc.returncode==0:
                pcm16=proc.stdout
    if pcm16 is None:
        raise ValueError('OXM/Ogg sample needs Python soundfile/libsndfile or ffmpeg for conversion')
    out=bytearray()
    frames=len(pcm16)//2
    limit=min(frames,expected_frames) if expected_frames else frames
    for i in range(limit):
        v=int.from_bytes(pcm16[i*2:i*2+2],'little',signed=True)
        out.append((v>>8)&0xff)
    if expected_frames and len(out)<expected_frames:
        out.extend(b'\0'*(expected_frames-len(out)))
    return bytes(out)


def _decode_xm_pcm(raw: bytes, typ: int, reserved: int, length_bytes: int):
    """Return mono signed-8 PCM plus byte->sample divisor for XM sample geometry.

    XM stereo is split-channel delta PCM, not interleaved.  The OPL4 path is
    mono, so decode L/R independently and average them after delta decoding.
    OggMod/OXM chunks are decoded before the normal XM delta path.
    """
    is16=bool(typ & 0x10); stereo=bool(typ & 0x20)
    div=(2 if is16 else 1)*(2 if stereo else 1)
    if _xm_is_ogg_chunk(raw):
        return _decode_xm_ogg(raw,typ),div
    sample_len=length_bytes//div
    if reserved==0xAD and not is16 and not stereo:
        return _decode_xm_adpcm(raw,sample_len),div
    if not stereo:
        return (_decode_delta16(raw) if is16 else _decode_delta8(raw)),div
    half=len(raw)//2
    left_raw,right_raw=raw[:half],raw[half:]
    left=_decode_delta16(left_raw) if is16 else _decode_delta8(left_raw)
    right=_decode_delta16(right_raw) if is16 else _decode_delta8(right_raw)
    n=min(len(left),len(right),sample_len)
    out=bytearray(n)
    for i in range(n):
        l=_s8(left[i]); r=_s8(right[i])
        v=max(-128,min(127,int((l+r)/2)))
        out[i]=v & 0xff
    return bytes(out),div


def _xm_pattern_at(b:bytes,pos:int,channels:int,version:int):
    min_header=8 if version==0x0102 else 9
    if pos+min_header>len(b): raise ValueError('truncated XM pattern header')
    phlen=struct.unpack_from('<I',b,pos)[0]
    if phlen<8 or pos+phlen>len(b): raise ValueError('invalid XM pattern header length')
    if version==0x0102:
        rows=b[pos+5]+1; psz=struct.unpack_from('<H',b,pos+6)[0]
    else:
        rows=struct.unpack_from('<H',b,pos+5)[0]; psz=struct.unpack_from('<H',b,pos+7)[0]
        if rows==0: rows=64
    rows=max(1,min(256,rows))
    pdata=b[pos+phlen:min(len(b),pos+phlen+psz)]
    evrows=[[None for _ in range(channels)] for _ in range(rows)]
    q=0
    for r in range(rows):
        for ch in range(channels):
            vals=[0,0,0,0,0]
            if q<len(pdata):
                c=pdata[q]; q+=1
                if c&0x80:
                    for k,mask in enumerate((1,2,4,8,16)):
                        if c&mask and q<len(pdata): vals[k]=pdata[q]; q+=1
                else:
                    vals[0]=c
                    for k in range(1,5):
                        if q<len(pdata): vals[k]=pdata[q]; q+=1
            evrows[r][ch]=vals
    return evrows,pos+phlen+psz


def parse_xm(path:Path)->core.Module:
    b=path.read_bytes()
    if not b.startswith(b'Extended Module: '): raise ValueError('not an XM file')
    if len(b)<80: raise ValueError('truncated XM header')
    title=b[17:37].split(b'\0')[0].decode('cp437','replace').rstrip()
    tracker=b[38:58].decode('cp437','replace').rstrip(' \0')
    version=struct.unpack_from('<H',b,58)[0]
    if version not in (0x0102,0x0103,0x0104):
        raise ValueError(f'unsupported XM version {version>>8}.{version&255:02d}')
    hsize=struct.unpack_from('<I',b,60)[0]
    songlen,restart,channels,npat,nins,flags,tempo,bpm=struct.unpack_from('<8H',b,64)
    if channels<1 or channels>24: raise ValueError(f'XM channel count {channels} is unsupported by the 24-channel OPL4 runtime (1..24)')
    orders=list(b[80:80+min(songlen,256)])
    # FT2 treats a zero-length order list as pattern 0. OpenMPT/modern MPT XMs
    # deliberately allow it to be truly empty.
    modern_empty = tracker.startswith('OpenMPT ') or tracker.startswith('ModPlug Tracker') or tracker.startswith('FastTracker v 2.00')
    if not orders and npat and not modern_empty: orders=[0]
    pos=60+hsize
    raw_patterns=[]
    if version>=0x0104:
        for _ in range(npat):
            pat,pos=_xm_pattern_at(b,pos,channels,version); raw_patterns.append(pat)

    samples:Dict[int,core.Sample]={}; inst_keymaps={}; inst_sample_ids={}; inst_names={}; next_sid=1
    pending_sample_data=[]

    def add_sample(ii, iname, meta, raw):
        nonlocal next_sid
        length,ls,ll,vol,ft,typ,pan,rel,reserved,sname=meta
        data,div=_decode_xm_pcm(raw,typ,reserved,length)
        ls//=div; ll//=div
        plen=len(data); le=min(plen,ls+ll); looped=(typ&3)!=0 and ll>1 and le>ls
        if (typ&3)==2 and looped:
            seg=data[ls:le]; data=data[:le]+seg[-2:0:-1]; ll=len(data)-ls; le=len(data); plen=len(data)
        c2=int(round(8363*(2**((rel+ft/128.0)/12.0))))
        prelimit_len=len(data)
        data2, ls2, le2, c22 = _limit_sample(data, ls, le, c2)
        plen2=len(data2); looped=looped and le2>ls2
        sid=next_sid; next_sid+=1
        smp=core.Sample(sid,sname,plen2,ls2,le2,min(64,vol),1 if looped else 0,max(1,c22),0,data2)
        smp.xm_relative_note=rel; smp.xm_finetune=ft
        smp.xm_period_offset=(int(round(768.0*math.log2(prelimit_len/float(plen2)))) if prelimit_len>plen2 and plen2 else 0)
        smp.xm_pan=pan; smp.xm_reserved=reserved; smp.xm_stereo=bool(typ&0x20); smp.xm_16bit=bool(typ&0x10); smp.xm_ogg=_xm_is_ogg_chunk(raw)
        samples[sid]=smp
        return sid

    # Instruments/sample headers. v1.02/1.03 defer all sample payloads until after patterns.
    sample_records=[]
    for ii in range(1,nins+1):
        if pos+29>len(b): raise ValueError(f'truncated XM instrument {ii}')
        ihsize=struct.unpack_from('<I',b,pos)[0] or 263
        if ihsize<29: raise ValueError(f'XM instrument {ii}: invalid header size {ihsize}')
        iname=b[pos+4:pos+26].split(b'\0')[0].decode('cp437','replace').rstrip()
        ns=struct.unpack_from('<H',b,pos+27)[0]
        inst_names[ii]=iname
        if ns:
            shsize=struct.unpack_from('<I',b,pos+29)[0] if pos+33<=len(b) else 40
            if shsize==0: shsize=40
            keymap=list(b[pos+33:pos+129]) if ihsize>=129 and pos+129<=len(b) else [0]*96
            if ihsize>=243 and pos+243<=len(b):
                vol_pts=[struct.unpack_from('<HH',b,pos+129+4*j) for j in range(12)]
                pan_pts=[struct.unpack_from('<HH',b,pos+177+4*j) for j in range(12)]
                vlen=min(12,b[pos+225]); plen_env=min(12,b[pos+226])
                inst_env={'vol_points':tuple(vol_pts[:vlen]),'pan_points':tuple(pan_pts[:plen_env]),
                    'vol_sustain':b[pos+227],'vol_loop_start':b[pos+228],'vol_loop_end':b[pos+229],
                    'pan_sustain':b[pos+230],'pan_loop_start':b[pos+231],'pan_loop_end':b[pos+232],
                    'vol_flags':b[pos+233]&7,'pan_flags':b[pos+234]&7,
                    'auto_vib_type':b[pos+235]&3,'auto_vib_sweep':b[pos+236],
                    'auto_vib_depth':b[pos+237],'auto_vib_rate':b[pos+238],
                    'fadeout':struct.unpack_from('<H',b,pos+239)[0]}
            else:
                inst_env={'vol_points':(),'pan_points':(),'vol_sustain':0,'vol_loop_start':0,'vol_loop_end':0,
                    'pan_sustain':0,'pan_loop_start':0,'pan_loop_end':0,'vol_flags':0,'pan_flags':0,
                    'auto_vib_type':0,'auto_vib_sweep':0,'auto_vib_depth':0,'auto_vib_rate':0,'fadeout':0}
        else:
            shsize=0; keymap=[0]*96
            inst_env={'vol_points':(),'pan_points':(),'vol_sustain':0,'vol_loop_start':0,'vol_loop_end':0,
                'pan_sustain':0,'pan_loop_start':0,'pan_loop_end':0,'vol_flags':0,'pan_flags':0,
                'auto_vib_type':0,'auto_vib_sweep':0,'auto_vib_depth':0,'auto_vib_rate':0,'fadeout':0}
        pos += ihsize
        recs=[]
        for si in range(ns):
            if pos+40>len(b): raise ValueError(f'XM instrument {ii}: truncated sample header {si}')
            o=pos
            length,loop_start,loop_len=struct.unpack_from('<III',b,o)
            vol=b[o+12]; finetune=struct.unpack_from('<b',b,o+13)[0]; typ=b[o+14]; pan=b[o+15]; rel=struct.unpack_from('<b',b,o+16)[0]; reserved=b[o+17]
            sname=b[o+18:o+40].split(b'\0')[0].decode('cp437','replace').rstrip() or iname
            recs.append((length,loop_start,loop_len,vol,finetune,typ,pan,rel,reserved,sname))
            pos += max(40,shsize)
        ids=[]
        if version>=0x0104:
            for meta in recs:
                length=meta[0]; reserved=meta[8]
                encoded_len=(16+(length+1)//2) if reserved==0xAD and not (meta[5]&0x30) else length
                raw=b[pos:pos+encoded_len]; pos+=encoded_len
                sid=add_sample(ii,iname,meta,raw); ids.append(sid)
                for k,v in inst_env.items(): setattr(samples[sid],'xm_'+k,v)
        else:
            for meta in recs:
                sid=next_sid; next_sid+=1; ids.append(sid)
                sample_records.append((sid,ii,iname,meta,inst_env))
        inst_keymaps[ii]=keymap; inst_sample_ids[ii]=ids

    if version<0x0104:
        for _ in range(npat):
            pat,pos=_xm_pattern_at(b,pos,channels,version); raw_patterns.append(pat)
        for sid,ii,iname,meta,inst_env in sample_records:
            length=meta[0]; reserved=meta[8]
            encoded_len=(16+(length+1)//2) if reserved==0xAD and not (meta[5]&0x30) else length
            raw=b[pos:pos+encoded_len]; pos+=encoded_len
            # add_sample allocates a new ID; force this old-version reserved ID by remapping.
            new_sid=add_sample(ii,iname,meta,raw)
            smp=samples.pop(new_sid); smp.number=sid; samples[sid]=smp
            for k,v in inst_env.items(): setattr(smp,'xm_'+k,v)
        next_sid=max(samples.keys(),default=0)+1

    # Resolve keymaps but preserve whether an instrument column actually existed.
    patterns=[]
    for evrows in raw_patterns:
        rows=[[] for _ in range(len(evrows))]
        for r,row in enumerate(evrows):
            for ch,(note,ins,volcol,eff,param) in enumerate(row):
                note_b=None; volume=None
                note_present=1<=note<=96
                if note==97: note_b=254
                elif 1<=note<=96: note_b=_note_byte(note-1)
                extra=[]
                if 0x10<=volcol<=0x50: volume=min(64,volcol-0x10)
                elif 0x60<=volcol<=0x6F: extra.append((66,volcol&15,False))      # FT2 vol-column slide down
                elif 0x70<=volcol<=0x7F: extra.append((67,volcol&15,False))      # FT2 vol-column slide up
                elif 0x80<=volcol<=0x8F: extra.append((41,volcol&15,False))       # FT2 fine vol down
                elif 0x90<=volcol<=0x9F: extra.append((42,volcol&15,False))       # FT2 fine vol up
                elif 0xA0<=volcol<=0xAF: extra.append((43,volcol&15,False))       # set vibrato speed only
                elif 0xB0<=volcol<=0xBF: extra.append((44,volcol&15,False))       # vibrato depth
                elif 0xC0<=volcol<=0xCF: extra.append((24,(volcol&15)*4,False))   # FT2 exact 0..60 pan
                elif 0xD0<=volcol<=0xDF: extra.append((45,volcol&15,False))       # pan left, no memory
                elif 0xE0<=volcol<=0xEF: extra.append((46,volcol&15,False))       # pan right, no memory
                elif 0xF0<=volcol<=0xFF: extra.append((47,volcol&15,False))       # volume-column tone porta

                cmd=None; p=param
                if eff==0x07: cmd,p=40,param                         # 7xy tremolo
                elif eff==0x0E:
                    sub=param>>4; lo=param&15
                    if sub==1: cmd,p=48,lo                           # E1 fine porta up
                    elif sub==2: cmd,p=49,lo                         # E2 fine porta down
                    elif sub==3: cmd,p=30,lo                         # E3 gliss
                    elif sub==4: cmd,p=29,lo                         # E4 vibrato waveform
                    elif sub==5: cmd,p=50,lo                         # E5 finetune
                    elif sub==6: cmd,p=51,lo                         # E6 pattern loop
                    elif sub==7: cmd,p=52,lo                         # E7 tremolo waveform
                    elif sub==9: cmd,p=53,lo                         # E9 ProTracker-style retrig
                    elif sub==0xA: cmd,p=54,lo                       # EA fine vol up
                    elif sub==0xB: cmd,p=55,lo                       # EB fine vol down
                    elif sub==0xC: cmd,p=27,lo                       # EC cut
                    elif sub==0xD: cmd,p=19,0xD0|lo                  # ED delay
                    elif sub==0xE: cmd,p=56,lo                       # EE pattern delay
                elif eff==0x10: cmd,p=57,param                       # G global volume
                elif eff==0x11: cmd,p=58,param                       # H global volume slide
                elif eff==0x14: cmd,p=31,param                       # K key off
                elif eff==0x15: cmd,p=59,param                       # L envelope position
                elif eff==0x19: cmd,p=60,param                       # P panning slide
                elif eff==0x1B: cmd,p=61,param                       # R multi retrig
                elif eff==0x1D: cmd,p=62,param                       # T tremor
                elif eff==0x0F and param==0: cmd,p=65,0              # F00: FT2 stop / indefinitely long row
                elif eff==0x21 and (param>>4)==1: cmd,p=63,param&15  # X1 extra-fine up
                elif eff==0x21 and (param>>4)==2: cmd,p=64,param&15  # X2 extra-fine down (semantic >63 remapped by stream below)
                else:
                    cmd,p,volume=_mod_effect(eff,param,volume)
                if note_b is not None or ins or volume is not None or cmd is not None or extra:
                    # Preserve the literal XM instrument number. Sample selection is
                    # resolved at playback-compile time from the real channel instrument
                    # state and the instrument's 96-note keymap.
                    ev=core.Event(ch=ch,note=note_b,ins=None,vol=volume,cmd=cmd,param=p if cmd is not None else None)
                    ev.xm_sample=None; ev.xm_instrument_present=bool(ins and ins!=0xFF); ev.xm_instrument_number=(ins if ins and ins!=0xFF else 0); ev.xm_note_present=note_present; ev.xm_volume_column=volcol
                    ev.extra_effects=extra
                    rows[r].append(ev)
        patterns.append(rows)

    chset=[255]*32
    for ch in range(min(channels,32)): chset[ch]=0 if ch%4 in (0,3) else 8
    m=core.Module(path,b,title,orders,patterns,samples,chset,(tempo or 6),(bpm or 125),64,0,1)
    m.source_format='XM'; m.offset_quantum=256; m.xm_flags=flags; m.xm_linear=bool(flags&1)
    m.xm_version=version; m.xm_restart=min(restart,max(0,len(orders)-1)) if orders else 0; m.xm_tracker_name=tracker
    m.xm_instrument_keymaps={k:tuple(v) for k,v in inst_keymaps.items()}
    m.xm_instrument_sample_ids={k:tuple(v) for k,v in inst_sample_ids.items()}
    m.xm_instrument_names=dict(inst_names)
    if tracker.startswith('FastTracker v2.00') or tracker.startswith('Fasttracker II clone'): profile='FT2'
    elif tracker.startswith('OpenMPT '): profile='OPENMPT'
    elif tracker.startswith('MilkyTracker '): profile='MILKYTRACKER'
    elif tracker.startswith('MadTracker 2.0'): profile='MADTRACKER'
    elif tracker.startswith('Skale Tracker') or tracker.startswith('Sk@le Tracker'): profile='SKALE'
    elif tracker.startswith('FastTracker v 2.00') or tracker.startswith('ModPlug Tracker'): profile='MODPLUG'
    else: profile='GENERIC-XM'
    m.xm_profile=profile
    # OpenMPT starts XM in FT2-compatible mode, then disables a small set of
    # quirks for known clones. Old ModPlug XMs use MPT semantics instead.
    m.xm_ft2_arpeggio = profile not in ('MADTRACKER','SKALE','MODPLUG')
    m.xm_ft2_porta_no_note = profile not in ('MADTRACKER','MODPLUG')
    m.xm_ft2_offset_oor = profile not in ('SKALE','MODPLUG')
    m.xm_ft2_envelope_escape = profile != 'MODPLUG'
    m.xm_ft2_pan_sustain_release = profile != 'MODPLUG'
    m.xm_ft2_e60_restart = profile != 'MODPLUG'
    m.xm_ft2_auto_vib_abort_sweep = profile != 'MODPLUG'
    m.xm_ft2_porta_reset_direction = profile != 'MODPLUG'
    m.xm_ft2_porta_target_no_reset = profile != 'MODPLUG'
    m.xm_oxm = any(bool(getattr(smp,'xm_ogg',False)) for smp in samples.values())

    neutral=((),(),0,0,0,0,0,0,0,0,0,0,0,0,0,128)
    profiles=[neutral]; profile_ids={neutral:0}
    for smp in samples.values():
        prof=(tuple(getattr(smp,'xm_vol_points',())),tuple(getattr(smp,'xm_pan_points',())),
              int(getattr(smp,'xm_vol_sustain',0)),int(getattr(smp,'xm_vol_loop_start',0)),int(getattr(smp,'xm_vol_loop_end',0)),
              int(getattr(smp,'xm_pan_sustain',0)),int(getattr(smp,'xm_pan_loop_start',0)),int(getattr(smp,'xm_pan_loop_end',0)),
              int(getattr(smp,'xm_vol_flags',0)),int(getattr(smp,'xm_pan_flags',0)),int(getattr(smp,'xm_fadeout',0)),
              int(getattr(smp,'xm_auto_vib_type',0)),int(getattr(smp,'xm_auto_vib_sweep',0)),
              int(getattr(smp,'xm_auto_vib_depth',0)),int(getattr(smp,'xm_auto_vib_rate',0)),int(getattr(smp,'xm_pan',128)))
        if prof not in profile_ids:
            if len(profiles)>=64: raise ValueError('XM needs more than 63 distinct realtime instrument/sample profiles')
            profile_ids[prof]=len(profiles); profiles.append(prof)
        smp.xm_profile_id=profile_ids[prof]
    m.xm_profiles=profiles
    return m


def parse_it(path:Path)->core.Module:
    """Parse a native Impulse Tracker (IMPM) module.

    Native IMPM parsing is deliberately strict: features which cannot yet be
    represented accurately by the dedicated IT/OPL4 runtime fail loudly
    instead of being silently rendered with S3M semantics.
    """
    b=path.read_bytes()
    if len(b)<0xC0 or b[:4]!=b'IMPM': raise ValueError('not an Impulse Tracker module')
    title=b[4:30].split(b'\0',1)[0].decode('cp437','replace').rstrip()
    ordn,insn,smpn,patn=struct.unpack_from('<4H',b,0x20)
    cwtv,cmwt,flags,special=struct.unpack_from('<4H',b,0x28)
    gv,mv,speed,tempo,sep,pwd=struct.unpack_from('<6B',b,0x30)
    if cmwt<0x0200:
        raise ValueError(f'IT compatible version {cmwt>>8}.{cmwt&255:02d} uses old-format instruments/samples; Cmwt >= 2.00 is required')
    if ordn>256 or insn>256 or smpn>256 or patn>240:
        raise ValueError(f'implausible IT counts: orders={ordn} instruments={insn} samples={smpn} patterns={patn}')
    table_end=0xC0+ordn+4*(insn+smpn+patn)
    if table_end>len(b): raise ValueError('truncated IT order/parapointer tables')
    pos=0xC0
    orders=list(b[pos:pos+ordn]); pos+=ordn
    iptrs=list(struct.unpack_from('<'+('I'*insn),b,pos)) if insn else []; pos+=4*insn
    sptrs=list(struct.unpack_from('<'+('I'*smpn),b,pos)) if smpn else []; pos+=4*smpn
    pptrs=list(struct.unpack_from('<'+('I'*patn),b,pos)) if patn else []

    instrument_mode=bool(flags&0x04)
    linear_slides=bool(flags&0x08)
    old_effects=bool(flags&0x10)
    compatible_gxx=bool(flags&0x20)

    if old_effects:
        raise ValueError('IT Old Effects mode needs the pending true-IT old-effects runtime')

    instruments={}
    if instrument_mode:
        for ii,ptr in enumerate(iptrs,1):
            if not ptr: continue
            if ptr+554>len(b): raise ValueError(f'IT instrument {ii}: header outside file')
            inst=_parse_it_instrument(b[ptr:ptr+554],cmwt)
            bad=[]
            if inst['nna'] not in (0,1,2,3): bad.append(f'invalid NNA={inst["nna"]}')
            if inst['dct'] not in (0,1,2,3): bad.append(f'invalid DCT={inst["dct"]}')
            if inst['dca'] not in (0,1,2): bad.append(f'invalid DCA={inst["dca"]}')
            if inst['random_volume'] or inst['random_pan']: bad.append('random volume/pan')
            if not (inst['default_pan']&0x80) and (inst['default_pan']&0x7F)>64:
                bad.append(f'invalid instrument default pan={inst["default_pan"]&0x7F}')
            if inst['global_volume']>128: bad.append(f'invalid instrument global volume={inst["global_volume"]}')
            for ename in ('vol_env','pan_env','pitch_env'):
                ef=int(inst[ename]['flags'])
                if ef & 0x08: bad.append(ename.replace('_',' ')+' carry')
                if ename=='pitch_env' and ef & 0x80: bad.append('filter envelope')
                if ef & 1:
                    pts=inst[ename]['points']
                    if not pts: bad.append(ename.replace('_',' ')+' enabled without points')
                    elif pts[-1][0] > 4095: bad.append(ename.replace('_',' ')+f' endpoint {pts[-1][0]} > 4095 ticks')
            if bad:
                raise ValueError(f'IT instrument {ii} ({inst["name"] or "unnamed"}): unsupported true-IT feature: '+', '.join(bad))
            instruments[ii]=inst

    samples:Dict[int,core.Sample]={}
    for si,ptr in enumerate(sptrs,1):
        if not ptr: continue
        if ptr+80>len(b) or b[ptr:ptr+4]!=b'IMPS': raise ValueError(f'IT sample {si}: bad/truncated IMPS header')
        gvl=b[ptr+0x11]; sflags=b[ptr+0x12]; vol=b[ptr+0x13]
        name=b[ptr+0x14:ptr+0x2E].split(b'\0',1)[0].decode('cp437','replace').rstrip()
        cvt=b[ptr+0x2E]; dfp=b[ptr+0x2F]
        length,lb,le,c5,sus_b,sus_e,data_ptr=struct.unpack_from('<7I',b,ptr+0x30)
        vib_speed,vib_depth,vib_rate,vib_type=b[ptr+0x4C:ptr+0x50]
        if gvl>64:
            raise ValueError(f'IT sample {si} ({name or "unnamed"}): invalid sample global volume {gvl}')
        if (dfp&0x80) and (dfp&0x7F)>64:
            raise ValueError(f'IT sample {si} ({name or "unnamed"}): invalid enabled sample default panning {dfp&0x7F}')
        if sflags&0x20:
            raise ValueError(f'IT sample {si} ({name or "unnamed"}): sustain loop is not yet supported')
        if sflags&0x40:
            raise ValueError(f'IT sample {si} ({name or "unnamed"}): ping-pong loop is not yet supported')
        if sflags&0x80:
            raise ValueError(f'IT sample {si} ({name or "unnamed"}): ping-pong sustain loop is not yet supported')
        if vib_depth or vib_rate:
            raise ValueError(f'IT sample {si} ({name or "unnamed"}): sample auto-vibrato is not yet supported')
        if length>0x10000000: raise ValueError(f'IT sample {si}: implausible sample length {length}')
        raw=b''
        if (sflags&1) and length:
            if not data_ptr or data_ptr>=len(b): raise ValueError(f'IT sample {si}: sample data pointer outside file')
            # Compressed payload length is implicit. Decoder stops after exactly
            # `length` frames, so passing the remaining file is safe.
            if sflags&0x08:
                raw=b[data_ptr:]
            else:
                bytes_per=(2 if sflags&0x02 else 1)*(2 if sflags&0x04 else 1)
                need=length*bytes_per
                if data_ptr+need>len(b): raise ValueError(f'IT sample {si}: truncated PCM payload')
                raw=b[data_ptr:data_ptr+need]
        data=_decode_it_pcm(raw,int(length),sflags,cvt,cwtv) if length else b''
        looped=bool(sflags&0x10) and 0<=lb<le<=length
        data2,lb2,le2,c52=_limit_sample(data,int(lb if looped else 0),int(le if looped else 0),int(c5 or 8363))
        smp=core.Sample(si,name or f'Sample {si}',len(data2),lb2,le2,min(64,int(vol)),1 if looped and le2>lb2 else 0,max(1,c52),int(data_ptr),data2)
        smp.it_flags=sflags; smp.it_convert=cvt; smp.it_default_pan=dfp; smp.it_global_volume=gvl
        smp.it_vibrato=(vib_speed,vib_depth,vib_rate,vib_type); smp.it_16bit=bool(sflags&2); smp.it_stereo=bool(sflags&4); smp.it_compressed=bool(sflags&8)
        samples[si]=smp

    # Decode the IT channel-mask pattern format using the 64-channel history
    # state mandated by ITTECH. We remap only actually used channels to the
    # OPL4 runtime's dense 0..23 voice range afterwards.
    raw_patterns=[]; used_channels=set()
    unsupported_effects={26:'Zxx MIDI macro / filter macro'}
    for pi,ptr in enumerate(pptrs):
        if not ptr:
            raw_patterns.append([[] for _ in range(64)]); continue
        if ptr+8>len(b): raise ValueError(f'IT pattern {pi}: header outside file')
        plen,rows=struct.unpack_from('<HH',b,ptr)
        if rows<1 or rows>1024: raise ValueError(f'IT pattern {pi}: invalid row count {rows}')
        start=ptr+8; end=start+plen
        if end>len(b): raise ValueError(f'IT pattern {pi}: packed data outside file')
        pdata=b[start:end]; q=0; r=0
        out=[[] for _ in range(rows)]
        masks=[0]*64; prev_note=[None]*64; prev_ins=[0]*64; prev_vol=[0]*64; prev_cmd=[0]*64; prev_param=[0]*64
        while r<rows and q<len(pdata):
            marker=pdata[q]; q+=1
            if marker==0:
                r+=1; continue
            och=(marker-1)&63; used_channels.add(och)
            if marker&0x80:
                if q>=len(pdata): raise ValueError(f'IT pattern {pi}: truncated channel mask')
                masks[och]=pdata[q]; q+=1
            mask=masks[och]; note=None; ins=0; volcol=0; cmd=0; param=0
            if mask&1:
                if q>=len(pdata): raise ValueError(f'IT pattern {pi}: truncated note')
                note=pdata[q]; q+=1; prev_note[och]=note
            elif mask&0x10: note=prev_note[och]
            if mask&2:
                if q>=len(pdata): raise ValueError(f'IT pattern {pi}: truncated instrument')
                ins=pdata[q]; q+=1; prev_ins[och]=ins
            elif mask&0x20: ins=prev_ins[och]
            if mask&4:
                if q>=len(pdata): raise ValueError(f'IT pattern {pi}: truncated volume column')
                volcol=pdata[q]; q+=1; prev_vol[och]=volcol
            elif mask&0x40: volcol=prev_vol[och]
            if mask&8:
                if q+1>=len(pdata): raise ValueError(f'IT pattern {pi}: truncated effect')
                cmd,param=pdata[q],pdata[q+1]; q+=2; prev_cmd[och]=cmd; prev_param[och]=param
            elif mask&0x80: cmd,param=prev_cmd[och],prev_param[och]

            ev_note=None; special_note=None
            if note is not None:
                if 0<=note<=119: ev_note=_note_byte(note)
                elif note==255: ev_note=254; special_note='off'
                elif note==254: ev_note=254; special_note='cut'
                else: special_note='fade'
            volume=None; volume_pan=None
            if mask&(4|0x40):
                if 0<=volcol<=64: volume=volcol
                elif 128<=volcol<=192: volume_pan=volcol-128
                elif volcol!=255:
                    raise ValueError(f'IT pattern {pi} row {r} channel {och+1}: volume-column command {volcol} is not yet supported')
            if special_note=='fade' and not instrument_mode:
                # In IT sample mode, Note Fade has no instrument fade target.
                ev_note=None; special_note='fade_ignored'
            instrument_present=bool(mask&(2|0x20) and ins)
            if cmd in unsupported_effects:
                raise ValueError(f'IT pattern {pi} row {r} channel {och+1}: {unsupported_effects[cmd]} is not yet supported')
            if cmd==19 and (param>>4) in (0,7,9,15):
                raise ValueError(f'IT pattern {pi} row {r} channel {och+1}: S{param:02X} subcommand is not yet supported')
            if cmd>26: raise ValueError(f'IT pattern {pi} row {r} channel {och+1}: invalid effect command {cmd}')
            ev=core.Event(ch=och,note=ev_note,ins=None,vol=volume,cmd=(cmd or None),param=(param if cmd else None))
            ev.it_note_special=special_note; ev.it_instrument_present=instrument_present; ev.it_instrument_number=int(ins or 0); ev.it_volume_column=int(volcol) if mask&(4|0x40) else None
            if volume_pan is not None: ev.volume_pan=volume_pan
            if not instrument_mode and ev.it_instrument_present:
                ev.ins=ins if ins in samples else None
            out[r].append(ev)
        raw_patterns.append(out)

    # Empty patterns and orders can leave used_channels empty; keep one runtime
    # channel so the engine has a valid state block.
    used=sorted(ch for ch in used_channels if not (b[0x40+ch]&0x80))
    if len(used)>24: raise ValueError(f'IT uses {len(used)} audible tracker channels; OPL4 runtime supports at most 24')
    if not used: used=[0]
    remap={old:i for i,old in enumerate(used)}
    patterns=[]
    for pat in raw_patterns:
        rows=[]
        for row in pat:
            nr=[]
            for ev in row:
                if ev.ch not in remap: continue
                ev.ch=remap[ev.ch]; nr.append(ev)
            rows.append(nr)
        patterns.append(rows)

    pans=[]; chvol=[]; pan_track=[]
    for old in used:
        pv=b[0x40+old]; vv=b[0x80+old]
        if vv>64: raise ValueError(f'IT channel {old+1}: invalid initial channel volume {vv}')
        if (pv&0x7F)==100:
            raise ValueError(f'IT channel {old+1}: surround panning needs the pending true-IT surround runtime')
        pv=min(64,pv&0x7F)
        # IT's separation byte scales stereo distance around centre.
        pv=max(0,min(64,32+int(round((pv-32)*(int(sep)/128.0)))))
        pans.append((pv*15+32)//64); pan_track.append((pv*255+32)//64); chvol.append(vv)
    chset=[0]*len(used)+[255]*(32-len(used))
    # Keep the public Module field in the existing 0..64 scale, while the
    # native IT engine receives the exact 0..128 header global-volume value.
    gv64=max(0,min(64,(int(gv)+1)//2))
    m=core.Module(path,b,title,orders,patterns,samples,chset,max(1,int(speed or 6)),max(32,int(tempo or 125)),gv64,flags,1)
    m.source_format='IT'; m.offset_quantum=256; m.it_cwtv=cwtv; m.it_cmwt=cmwt; m.it_flags=flags; m.it_special=special
    m.it_instrument_mode=instrument_mode; m.it_linear_slides=linear_slides; m.it_old_effects=old_effects; m.it_compatible_gxx=compatible_gxx; m.it_global_volume=int(gv)
    m.it_instruments=instruments; m.it_instrument_keymaps={k:v['keymap'] for k,v in instruments.items()}
    # Deduplicate realtime instrument profiles. Profile 0 is neutral/sample-mode.
    def _env_key(env):
        return (int(env['flags'])&7, tuple((int(x),int(y)) for x,y in env['points']),
                int(env['loop_start']),int(env['loop_end']),int(env['sustain_start']),int(env['sustain_end']))
    neutral=(0,0,0,0,_env_key({'flags':0,'points':(), 'loop_start':0,'loop_end':0,'sustain_start':0,'sustain_end':0}),
             _env_key({'flags':0,'points':(), 'loop_start':0,'loop_end':0,'sustain_start':0,'sustain_end':0}),
             _env_key({'flags':0,'points':(), 'loop_start':0,'loop_end':0,'sustain_start':0,'sustain_end':0}))
    profiles=[neutral]; profile_ids={neutral:0}
    for ii,inst in sorted(instruments.items()):
        prof=(int(inst['nna']),int(inst['dct']),int(inst['dca']),int(inst['fadeout']),
              _env_key(inst['vol_env']),_env_key(inst['pan_env']),_env_key(inst['pitch_env']))
        if prof not in profile_ids:
            if len(profiles)>=256: raise ValueError('IT needs more than 255 distinct realtime instrument profiles')
            profile_ids[prof]=len(profiles); profiles.append(prof)
        inst['profile_id']=profile_ids[prof]
    m.it_profiles=profiles
    m.it_channel_map=tuple(used); m.it_channel_volume=tuple(chvol); m.it_channel_pan_tracker=tuple(pan_track); m.channel_panning_nibbles=pans; m.s3m_is_stereo=True
    m.s3m_sample_swap=False; m.s3m_porta_sample_change=False; m.s3m_short_sample_retrig=True
    m.it_tracker_name=f'Impulse Tracker compatible (Cwtv {cwtv>>8}.{cwtv&255:02X})'
    return m

def parse_s3m_profile(path:Path)->Tuple[core.Module,str]:
    """Parse S3M and choose an explicit playback profile.

    This follows OpenMPT's important split: genuine ST3 (with GUS/SB driver
    quirks), Impulse Tracker S3M, and modern/non-ST3 S3M writers. cwtv alone
    is not sufficient because several trackers deliberately wrote ST3-looking
    headers.
    """
    m=core.parse_s3m(path); b=m.raw
    cwtv=int.from_bytes(b[0x28:0x2A],'little') if len(b)>=0x2A else 0
    family=cwtv & 0xF000
    m.s3m_cwtv=cwtv; m.s3m_tracker_family=family>>12; m.offset_quantum=256
    ordn=int.from_bytes(b[0x20:0x22],'little'); insn=int.from_bytes(b[0x22:0x24],'little'); patn=int.from_bytes(b[0x24:0x26],'little')
    flags=int.from_bytes(b[0x26:0x28],'little')
    master=b[0x33] if len(b)>0x33 else 0
    ultraclick=b[0x34] if len(b)>0x34 else 0
    use_pan=(len(b)>0x35 and b[0x35]==0xFC)
    special=int.from_bytes(b[0x3E:0x40],'little') if len(b)>=0x40 else 0

    # Fingerprint GUS vs SB using ST3's saved GUS addresses.
    ins_ptr_base=0x60+ordn; gus_or=0; pcm_headers=0
    sample_ptrs=[]; pattern_ptrs=[]
    for i in range(insn):
        q=ins_ptr_base+2*i
        if q+2>len(b): break
        para=int.from_bytes(b[q:q+2],'little'); sample_ptrs.append(para)
        o=para*16
        if para and o+80<=len(b) and b[o]==1:
            pcm_headers+=1; gus_or |= int.from_bytes(b[o+40:o+42],'little')
    pat_base=ins_ptr_base+2*insn
    for i in range(patn):
        q=pat_base+2*i
        if q+2>len(b): break
        pattern_ptrs.append(int.from_bytes(b[q:q+2],'little'))
    offsets_canonical=bool(pattern_ptrs and sample_ptrs and pattern_ptrs[0] > sample_ptrs[0])

    # OpenMPT fingerprints several cwtv=0x1320 files as non-ST3.
    disguised_modern=False; modern_name=None
    if cwtv==0x1320 and special==0 and ultraclick==0:
        if (ordn & 1)==0 and (flags & ~0x50)==0 and use_pan and offsets_canonical:
            if (ordn & 0x0F)==0:
                modern_name='ModPlug Tracker / OpenMPT 1.17' if (master & 0x80) else 'ModPlug Tracker 1.0 alpha'
                disguised_modern=True
            elif master & 0x80:
                modern_name='Schism Tracker'; disguised_modern=True
        elif flags==0 and not use_pan:
            modern_name='PlayerPRO' if b[0x30]==64 and (master&0x7F)==48 else 'Velvet Studio'; disguised_modern=True
        elif flags==8 and not use_pan:
            modern_name='Impulse Tracker < 1.03'; disguised_modern=True

    is_st3=(family==0x1000 and not disguised_modern)
    # ST3 3.01+ should leave GUS-address fingerprints. If all are zero, OpenMPT
    # assumes another writer/converter rather than forcing ST3 quirks.
    if is_st3 and pcm_headers and gus_or==0 and cwtv!=0x1300:
        is_st3=False; modern_name='Unknown / ST3-compatible writer'

    use_gus=bool(is_st3 and pcm_headers and gus_or>1)
    m.s3m_gus_address_or=gus_or; m.s3m_use_gus=use_gus
    m.s3m_is_st3=is_st3; m.s3m_is_stereo=bool(master & 0x80)
    m.s3m_old_vibrato=bool(flags & 0x01); m.s3m_amiga_limits=bool(flags & 0x10)

    if is_st3:
        m.source_format='S3M'
        m.s3m_profile='ST3-GUS' if use_gus else 'ST3-SB'
        m.s3m_tracker_name='Scream Tracker 3 ('+('GUS' if use_gus else 'SB')+')'
        m.s3m_sample_swap=not use_gus
        m.s3m_porta_sample_change=use_gus
        m.s3m_short_sample_retrig=not use_gus
        m.s3m_shared_effect_memory=True
    elif family==0x3000 or (modern_name and modern_name.startswith('Impulse Tracker')):
        m.source_format='IT-S3M'; m.s3m_profile='IT-S3M'; m.s3m_tracker_name=modern_name or 'Impulse Tracker'
        m.s3m_sample_swap=True; m.s3m_porta_sample_change=False; m.s3m_short_sample_retrig=True; m.s3m_shared_effect_memory=False
    else:
        m.source_format='MODERN-S3M'; m.s3m_profile='modern/non-ST3 S3M'; m.s3m_shared_effect_memory=False
        names={0x2000:'Imago Orpheus / compatible',0x4000:'Schism Tracker / compatible',0x5000:'OpenMPT / compatible',0x6000:'BeRoTracker',0x7000:'CreamTracker'}
        m.s3m_tracker_name=modern_name or names.get(family,'Modern / non-ST3 S3M writer')
        # Modern writers are closer to IT/Schism semantics than strict ST3.
        m.s3m_sample_swap=True; m.s3m_porta_sample_change=False; m.s3m_short_sample_retrig=(family in (0x3000,0x4000,0x5000));

    # Correct default speed/tempo after the creator profile is known.
    raw_speed=b[0x31]; raw_tempo=b[0x32]
    m.speed = 6 if (raw_speed==0 or (raw_speed==255 and is_st3)) else raw_speed
    m.tempo = (125 if is_st3 else 32) if raw_tempo<33 else raw_tempo

    # Optional default panning table. Mono S3M centers PCM channels when no
    # explicit pan exists; stereo files use the traditional left/right groups.
    poff=0x60+ordn+2*insn+2*patn; pans=[None]*32
    if use_pan and poff+32<=len(b):
        for ch,v in enumerate(b[poff:poff+32]):
            if v&0x20: pans[ch]=v&0x0F
    m.channel_panning_nibbles=pans; m.s3m_has_default_panning=any(v is not None for v in pans)
    return m,m.source_format


def parse_module(path:Path)->Tuple[core.Module,str]:
    b=path.read_bytes()[:1084]
    if b.startswith(b'IMPM'): return parse_it(path),'IT'
    if b.startswith(b'Extended Module: '): return parse_xm(path),'XM'
    if len(b)>=0x30 and b[0x2c:0x30]==b'SCRM': return parse_s3m_profile(path)
    if len(b)>=1084: return parse_mod(path),'MOD'
    return parse_s3m_profile(path)
