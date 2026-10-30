from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import struct, math
import _s3m2opl4_backend as core

# Compact semantic commands use the S3M command numbers where possible.
CMD_A=1; CMD_B=2; CMD_C=3; CMD_D=4; CMD_E=5; CMD_F=6; CMD_G=7; CMD_H=8; CMD_I=9
CMD_J=10; CMD_K=11; CMD_L=12; CMD_M=13; CMD_N=14; CMD_O=15; CMD_P=16; CMD_Q=17; CMD_R=18; CMD_S=19; CMD_T=20
CMD_U=21; CMD_V=22; CMD_W=23; CMD_X=24; CMD_Y=25; CMD_Z=26
CMD_NOTE_CUT=27
CMD_XM_PROFILE=28; CMD_VCTRL=29; CMD_GLISS=30; CMD_KEYOFF=31
CMD_ST3_COMBINED_D=32; CMD_ST3_COMBINED_H=33; CMD_ST3_COMBINED_G=34
CMD_ST3_PATTERN_DELAY=35; CMD_ST3_VIB_WAVE=36; CMD_ST3_TREM_WAVE=37
CMD_ST3_FINETUNE=38; CMD_ST3_TICK_DELAY=39
CMD_XM_TREMOLO=40; CMD_XM_VFINE_DOWN=41; CMD_XM_VFINE_UP=42; CMD_XM_VIBSPD=43; CMD_XM_VIBDEP=44
CMD_XM_PANLEFT=45; CMD_XM_PANRIGHT=46; CMD_XM_VOLPORTA=47; CMD_XM_FINE_UP=48; CMD_XM_FINE_DOWN=49
CMD_XM_FINETUNE=50; CMD_XM_PATLOOP=51; CMD_XM_TREMWAVE=52; CMD_XM_E9RETRIG=53; CMD_XM_FINEVOLUP=54; CMD_XM_FINEVOLDOWN=55
CMD_XM_PATDELAY=56; CMD_XM_GVOL=57; CMD_XM_GVOLSLIDE=58; CMD_XM_ENVPOS=59; CMD_XM_PANSLIDE=60; CMD_XM_RETRIG=61; CMD_XM_TREMOR=62; CMD_XM_XFINE_UP=63; CMD_XM_XFINE_DOWN=64; CMD_XM_STOP=65
CMD_XM_VC_VOLDN=66; CMD_XM_VC_VOLUP=67; CMD_XM_ROWINS=68; CMD_XM_ROWDELAY=69; CMD_XM_ROWNOTE=70; CMD_XM_ROWVOL=71
CMD_MOD_FILTER=72; CMD_MOD_FINE_UP=73; CMD_MOD_FINE_DOWN=74; CMD_MOD_GLISS=75; CMD_MOD_VIBWAVE=76; CMD_MOD_FINETUNE=77
CMD_MOD_PATLOOP=78; CMD_MOD_TREMWAVE=79; CMD_MOD_PAN4=80; CMD_MOD_FINEVOLUP=81; CMD_MOD_FINEVOLDOWN=82; CMD_MOD_PATDELAY=83; CMD_MOD_INVERT=84; CMD_MOD_INSTR=85
CMD_IT_PROFILE=86
CMD_IT_LINEAR_E=87; CMD_IT_LINEAR_F=88; CMD_IT_LINEAR_G=89; CMD_IT_PAN_WAVE=90; CMD_IT_GAIN=91
MOD_EFX_SPEED=(0,5,6,7,8,10,11,13,16,19,22,26,32,43,64,128)
S3M_FMTS=('S3M','IT-S3M','MODERN-S3M','IT')
S3M_FINETUNE=(7895,7941,7985,8046,8107,8169,8232,8280,8363,8413,8463,8529,8581,8651,8723,8757)

HEADER_SIZE=39
STREAM_MAGIC=b'CTR1'
STREAM_VERSION=4

@dataclass
class ResolveState:
    instrument: int = 0
    note_index: int = -1
    period_seen: bool = False
    global_mem: int = 0
    g_mem: int = 0
    o_mem: int = 0
    note_offset: int = 0
    vib_speed: int = 0
    vib_depth: int = 0
    high_offset: int = 0
    finetune_c5: int = 0
    xm_instrument_num: int = 0
    it_instrument_num: int = 0
    it_ef_mem: int = 0
    it_tremor_on: int = 1
    it_tremor_off: int = 1
    it_tremolo_speed: int = 0
    it_tremolo_depth: int = 0
    it_pan_tracker: int = 128
    it_channel_volume: int = 64
    it_panbrello_speed: int = 0
    it_panbrello_depth: int = 0
    it_tempo_mem: int = 0
    xm_volslide_mem: int = 0
    xm_fine_porta_mem: int = 0
    xm_xfine_porta_mem: int = 0
    xm_fine_vol_mem: int = 0
    xm_pan_mem: int = 0
    xm_gvol_mem: int = 0
    xm_retrig_mem: int = 0
    xm_tremolo_speed: int = 0
    xm_tremolo_depth: int = 0
    xm_channel_finetune: int = 0
    mod_finetune: int = 0
    loop_start_row: int = 0
    loop_count: int = 0
    mem: Dict[int,int] = field(default_factory=dict)

def _it_linear_factor_pair(param:int)->Tuple[int,int]:
    """OpenMPT/IT linear-slide multipliers encoded as deltas around unity.

    Returns (up_delta, down_delta). For regular parameters >= 192,
    up_delta is the excess above 2.0; the runtime infers the octave bit from
    the original parameter. Fine F0x uses the regular table; extra-fine E0x
    uses IT's 1/768-octave fine table.
    """
    param=int(param)&0xFF
    hi=param&0xF0; lo=param&0x0F
    if hi==0xE0:
        n=lo; den=768.0
        # ITTECH's fine-down table contains these historical integer values.
        fine_down=(65535,65477,65418,65359,65300,65241,65182,65123,65065,65006,64947,64888,64830,64772,64713,64645)
        fd=fine_down[n]
        fu=int(math.floor(65536.0*(2.0**(n/den))+0.5))
    elif hi==0xF0:
        n=lo; den=192.0
        fu=int(math.floor(65536.0*(2.0**(n/den))+0.5))
        fd=int(math.floor(65536.0*(2.0**(-n/den))+0.5))
    else:
        n=param; den=192.0
        fu=int(math.floor(65536.0*(2.0**(n/den))+0.5))
        fd=int(math.floor(65536.0*(2.0**(-n/den))+0.5))
    if (hi not in (0xE0,0xF0)) and n>=192:
        up_delta=max(0,min(65535,fu-131072))
    else:
        up_delta=max(0,min(65535,fu-65536))
    down_delta=max(0,min(65535,65536-fd))
    return up_delta,down_delta

@dataclass
class Action:
    ch: int
    # note_kind: None, 'normal', 'porta', 'porta_swap', 'sample_swap', 'off', 'cut', 'fade', 'delay_normal', 'delay_porta', 'delay_off'
    note_kind: Optional[str]=None
    tone: int=0
    period_q: int=0
    pitch_lo: int=0
    pitch_hi: int=0
    delayed_volume: int=0xFF
    delay_tick: int=-1
    volume: Optional[int]=None
    effects: List[Tuple[int,int,Optional[Tuple[int,int]]]] = field(default_factory=list)
    xm_instrument_present: bool=False


class SharedPayloadWaveBank:
    """Allocate OPL4 custom waves while sharing PCM payloads.

    Normal XM/MOD conversions retain the original <=64-tone allocation. S3M
    may use many Oxx offsets, so its payload-owning/private waves occupy the
    MWK-loadable low half (0..63) and pure header aliases occupy 64..127.
    KSP1PLAY still uploads an unmodified 64-tone MWK; the resident engine
    installs the upper-half alias headers once during INIT.
    """
    def __init__(self,module,extended_aliases:bool=False):
        self.module=module; self.extended_aliases=extended_aliases
        self.variants={}; self.order=[]; self.owner_by_instrument={}
        self.low_next=(1 if extended_aliases else 0); self.high_next=64; self.silence_variant=None

    def _alloc_low(self)->int:
        if self.low_next>=64:
            raise ValueError('more than 64 payload-owning/private OPL4 tones are required')
        n=self.low_next; self.low_next+=1; return n

    def _alloc_high(self)->int:
        if self.high_next>=128:
            raise ValueError('more than 128 custom OPL4 wave headers are required')
        n=self.high_next; self.high_next+=1; return n

    def get(self,instrument:int,offset:int)->int:
        q=max(1,int(getattr(self.module,'offset_quantum',1)))
        off=(max(0,int(offset))//q)*q
        key=core.WaveKey(instrument,off)
        if key in self.variants: return self.variants[key].wave_number
        smp=self.module.samples.get(instrument)
        if smp is None: raise ValueError(f'instrument {instrument} is not an 8-bit PCM sample')

        # Existing XM/MOD profile: preserve encounter-order low tones exactly.
        if not self.extended_aliases:
            if len(self.order)>=64:
                raise ValueError('more than 64 custom OPL4 tones are required')
            tone=len(self.order)
            v=core.WaveVariant(key=key,wave_number=384+tone,sample_name=smp.name,source_length=smp.length)
            shareable=(off < smp.length) and ((not smp.looped) or off<=smp.loop_begin)
            if shareable:
                owner=self.owner_by_instrument.get(instrument)
                if owner is None:
                    self.owner_by_instrument[instrument]=v; v.payload_owner=True; v.alias_owner=None
                else:
                    v.payload_owner=False; v.alias_owner=owner
                v.header_offset=off
            else:
                v.payload_owner=False; v.alias_owner=None; v.header_offset=0
            self.variants[key]=v; self.order.append(v)
            return v.wave_number

        # All out-of-range offsets are the same one-byte signed silence wave.
        if off>=smp.length:
            if self.silence_variant is not None:
                self.variants[key]=self.silence_variant
                return self.silence_variant.wave_number
            tone=self._alloc_low()
            v=core.WaveVariant(key=key,wave_number=384+tone,sample_name='silence',source_length=1)
            v.payload_owner=False; v.alias_owner=None; v.header_offset=0; v.force_silence=True
            self.silence_variant=v; self.variants[key]=v; self.order.append(v)
            return v.wave_number

        shareable=(not smp.looped) or off<=smp.loop_begin
        if shareable:
            owner=self.owner_by_instrument.get(instrument)
            if owner is None:
                tone=self._alloc_low()
                v=core.WaveVariant(key=key,wave_number=384+tone,sample_name=smp.name,source_length=smp.length)
                self.owner_by_instrument[instrument]=v
                v.payload_owner=True; v.alias_owner=None; v.header_offset=off
            else:
                tone=self._alloc_high()
                v=core.WaveVariant(key=key,wave_number=384+tone,sample_name=smp.name,source_length=smp.length)
                v.payload_owner=False; v.alias_owner=owner; v.header_offset=off
        else:
            # Starting after a loop start needs a private rotated/tail payload.
            tone=self._alloc_low()
            v=core.WaveVariant(key=key,wave_number=384+tone,sample_name=smp.name,source_length=smp.length)
            v.payload_owner=False; v.alias_owner=None; v.header_offset=0
        self.variants[key]=v; self.order.append(v)
        return v.wave_number

class CompactCompiler:
    def __init__(self, module: core.Module, source_format: str, start_order=0, stop_order=None, max_seconds=1800.0):
        self.m=module; self.fmt=source_format
        self.xm_linear=(source_format=='XM' and bool(getattr(module,'xm_linear',False)))
        self.xm_ft2_arpeggio=(source_format=='XM' and bool(getattr(module,'xm_ft2_arpeggio',True)))
        self.xm_ft2_porta_no_note=(source_format=='XM' and bool(getattr(module,'xm_ft2_porta_no_note',True)))
        self.xm_ft2_offset_oor=(source_format=='XM' and bool(getattr(module,'xm_ft2_offset_oor',True)))
        self.xm_ft2_envelope_escape=(source_format=='XM' and bool(getattr(module,'xm_ft2_envelope_escape',True)))
        self.xm_ft2_pan_sustain_release=(source_format=='XM' and bool(getattr(module,'xm_ft2_pan_sustain_release',True)))
        self.xm_ft2_e60_restart=(source_format=='XM' and bool(getattr(module,'xm_ft2_e60_restart',True)))
        self.xm_ft2_auto_vib_abort_sweep=(source_format=='XM' and bool(getattr(module,'xm_ft2_auto_vib_abort_sweep',True)))
        self.xm_ft2_porta_reset_direction=(source_format=='XM' and bool(getattr(module,'xm_ft2_porta_reset_direction',True)))
        self.xm_ft2_porta_target_no_reset=(source_format=='XM' and bool(getattr(module,'xm_ft2_porta_target_no_reset',True)))
        self.start_order=start_order
        self.stop_order=stop_order if stop_order is not None else self._next_255(start_order)
        self.max_seconds=max_seconds
        self.states={ch:ResolveState() for ch in self.m.active_channels}
        self.bank=SharedPayloadWaveBank(module,extended_aliases=(source_format in S3M_FMTS))
        self.speed=max(1,module.speed); self.tempo=max(32,module.tempo)
        self.order=start_order; self.row=0; self.seconds=0.0; self.rows=0
        self.xm_next_pat_start_row=0
        self.ended_reason=''; self.warnings=[]
        self.mod_pending_oor_delay={}
        self.it_voice_map={}
        self.it_voices=[None]*24
        self.it_global_volume=int(getattr(self.m,'it_global_volume',128)) if self.fmt=='IT' else 128
        self.it_initial_global_emitted=False
        if self.fmt=='IT':
            pans=list(getattr(self.m,'it_channel_pan_tracker',()))
            chvol=list(getattr(self.m,'it_channel_volume',()))
            for ch,st in self.states.items():
                if ch < len(pans): st.it_pan_tracker=int(pans[ch])
                if ch < len(chvol): st.it_channel_volume=max(0,min(64,int(chvol[ch])))

    def _it_profile_for_instrument(self,inum:int):
        inst=getattr(self.m,'it_instruments',{}).get(int(inum))
        return inst if inst else None

    def _it_note_identity(self,e,st:ResolveState):
        """Return (instrument, mapped_note, sample, profile) for a real IT note."""
        if self.fmt!='IT' or not bool(getattr(self.m,'it_instrument_mode',False)):
            return (0,-1,None,None)
        if e.note is None or e.note>=254:
            return (0,-1,None,None)
        literal=int(getattr(e,'it_instrument_number',0)) if bool(getattr(e,'it_instrument_present',False)) else 0
        inum=literal or st.it_instrument_num
        ni=self._note_index(e.note)
        _mapped,smp=self._it_resolve_instrument(inum,ni)
        # IT DCT=Note compares the original pattern note, not the note-map
        # translation. OpenMPT tracks this as kITDCTBehaviour.
        return (inum,ni,smp,self._it_profile_for_instrument(inum))

    @staticmethod
    def _it_voice_action(phys:int,kind:str):
        return Action(int(phys),note_kind=kind)

    def _it_apply_voice_end(self,phys:int,kind:str):
        meta=self.it_voices[phys]
        if meta is None:return
        if kind=='cut':
            self.it_voices[phys]=None
            for l,p in list(self.it_voice_map.items()):
                if p==phys:self.it_voice_map.pop(l,None)
        else:
            meta['state']='background' if meta.get('state')!='foreground' else meta.get('state')
            meta['release']=kind

    def _it_duplicate_actions(self,logical:int,new_inum:int,new_note:int,new_sample:int,new_prof):
        actions=[]; handled=set()
        if not new_prof:return actions,handled
        dct=int(new_prof.get('dct',0))
        if not dct:return actions,handled
        for phys,meta in enumerate(self.it_voices):
            if not meta or meta.get('master')!=logical:continue
            match=(dct==1 and meta.get('instrument')==new_inum and meta.get('note')==new_note)
            if dct==2: match=(meta.get('instrument')==new_inum and meta.get('sample')==new_sample)
            elif dct==3: match=(meta.get('instrument')==new_inum)
            if not match:continue
            oldprof=self._it_profile_for_instrument(meta.get('instrument',0)) or {}
            dca=int(oldprof.get('dca',new_prof.get('dca',0)))
            kind=('cut','off','fade')[max(0,min(2,dca))]
            actions.append(self._it_voice_action(phys,kind)); handled.add(phys)
            if kind=='cut': self._it_apply_voice_end(phys,'cut')
            else:
                meta['state']='background'; meta['release']=kind
                if self.it_voice_map.get(logical)==phys:self.it_voice_map.pop(logical,None)
        return actions,handled

    def _it_allocate_note_voice(self,e,st:ResolveState):
        """Map an IT logical channel note to an OPL4 voice and flatten NNA/DCT/DCA.

        We never steal a sounding voice. If exact IT semantics require more than
        24 simultaneous voices, conversion fails because OPL4 cannot represent it.
        """
        logical=e.ch
        inum,mnote,smp,prof=self._it_note_identity(e,st)
        oldphys=self.it_voice_map.get(logical)
        synth,handled=self._it_duplicate_actions(logical,inum,mnote,smp,prof)
        reusable=None
        if oldphys is not None and self.it_voices[oldphys] is not None and oldphys not in handled:
            oldmeta=self.it_voices[oldphys]
            oldprof=self._it_profile_for_instrument(oldmeta.get('instrument',0)) or {}
            nna=int(oldprof.get('nna',0))
            kind=('cut',None,'off','fade')[max(0,min(3,nna))]
            if kind=='cut':
                synth.append(self._it_voice_action(oldphys,'cut'))
                self.it_voices[oldphys]=None; reusable=oldphys
            else:
                if kind: synth.append(self._it_voice_action(oldphys,kind)); oldmeta['release']=kind
                oldmeta['state']='background'
            self.it_voice_map.pop(logical,None)
        elif oldphys is not None and self.it_voices[oldphys] is None:
            reusable=oldphys; self.it_voice_map.pop(logical,None)
        if reusable is None:
            preferred=logical if 0<=logical<24 and self.it_voices[logical] is None else None
            if preferred is not None: reusable=preferred
            else:
                reusable=next((i for i,v in enumerate(self.it_voices) if v is None),None)
        if reusable is None:
            raise ValueError(f'IT NNA/DCT requires more than 24 simultaneous OPL4 voices at order {self.order} row {self.row}; exact conversion is impossible')
        self.it_voice_map[logical]=reusable
        self.it_voices[reusable]={'master':logical,'instrument':inum,'sample':smp,'note':mnote,'state':'foreground','release':None}
        return reusable,synth,inum,prof

    def _it_target_voice(self,logical:int):
        return self.it_voice_map.get(logical, logical if 0<=logical<24 else 0)

    def _next_255(self,start):
        for i in range(start,len(self.m.orders)):
            if self.m.orders[i]==255:return i
        return len(self.m.orders)

    def _letter(self,cmd):
        return chr(64+cmd) if cmd and 1<=cmd<=26 else ''

    def _resolve(self, st:ResolveState, cmd:int, p:int)->int:
        raw=p or 0
        if self.fmt=='S3M':
            # Genuine ST3 has a deliberately odd shared memory. Any *effect
            # command* with a non-zero parameter updates the value later
            # recalled by D/E/F/I/J/K/L/Q/R/S. A NONE command never does.
            if cmd in (CMD_D,CMD_E,CMD_F,CMD_I,CMD_J,CMD_K,CMD_L,CMD_Q,CMD_R,CMD_S):
                p=raw or st.global_mem
            elif cmd==CMD_G:
                p=raw or st.g_mem
                if raw: st.g_mem=raw
            elif cmd==CMD_H:
                if raw & 0xF0: st.vib_speed=(raw>>4)&15
                if raw & 0x0F: st.vib_depth=raw&15
                p=(st.vib_speed<<4)|st.vib_depth
            elif cmd==CMD_O:
                if raw:
                    st.o_mem=raw; p=raw
                elif int(getattr(self.m,'s3m_cwtv',0)) <= 0x1301:
                    p=0
                else:
                    p=st.o_mem
            else:
                p=raw
            if cmd and raw:
                st.global_mem=raw
            return p

        # Native IT has effect-local memory, with D/K/L sharing D memory.
        # E/F share a pitch-slide memory byte; G joins that memory only when
        # the IT header's compatible-Gxx flag requests it.
        if self.fmt=='IT':
            if cmd==CMD_G:
                if bool(getattr(self.m,'it_compatible_gxx',False)):
                    if raw: st.it_ef_mem=raw
                    return raw or st.it_ef_mem
                p=raw or st.g_mem
                if raw: st.g_mem=raw
                return p
            if cmd in (CMD_E,CMD_F):
                if raw: st.it_ef_mem=raw
                return raw or st.it_ef_mem
            if cmd in (CMD_H,CMD_U):
                # IT Hxy and Uxy share the same speed/depth nibble memory.
                # U merely applies the remembered depth at 1/4 H's depth scale.
                if raw & 0xF0: st.vib_speed=(raw>>4)&15
                if raw & 0x0F: st.vib_depth=raw&15
                return (st.vib_speed<<4)|st.vib_depth
            if cmd==CMD_O:
                p=raw or st.o_mem
                if raw: st.o_mem=raw
                return p
            if cmd in (CMD_D,CMD_K,CMD_L):
                if raw: st.mem[CMD_D]=raw
                return raw or st.mem.get(CMD_D,0)
            if cmd==CMD_I:
                if raw & 0xF0: st.it_tremor_on=(raw>>4)&15
                if raw & 0x0F: st.it_tremor_off=raw&15
                return (st.it_tremor_on<<4)|st.it_tremor_off
            if cmd==CMD_R:
                if raw & 0xF0: st.it_tremolo_speed=(raw>>4)&15
                if raw & 0x0F: st.it_tremolo_depth=raw&15
                return (st.it_tremolo_speed<<4)|st.it_tremolo_depth
            if cmd in (CMD_J,CMD_N,CMD_P,CMD_Q,CMD_S,CMD_W):
                if raw: st.mem[cmd]=raw
                return raw or st.mem.get(cmd,0)
            if cmd==CMD_T:
                if raw: st.it_tempo_mem=raw
                return raw or st.it_tempo_mem
            if cmd==CMD_Y:
                if raw & 0xF0: st.it_panbrello_speed=(raw>>4)&15
                if raw & 0x0F: st.it_panbrello_depth=raw&15
                return (st.it_panbrello_speed<<4)|st.it_panbrello_depth
            return raw

        # IT-authored and modern/non-ST3 S3M use effect-local memory instead
        # of ST3's global D/E/F/I/J/K/L/Q/R/S byte.
        if self.fmt in ('IT-S3M','MODERN-S3M'):
            if cmd==CMD_G:
                p=raw or st.g_mem
                if raw: st.g_mem=raw
                return p
            if cmd==CMD_H:
                if raw & 0xF0: st.vib_speed=(raw>>4)&15
                if raw & 0x0F: st.vib_depth=raw&15
                return (st.vib_speed<<4)|st.vib_depth
            if cmd==CMD_O:
                p=raw or st.o_mem
                if raw: st.o_mem=raw
                return p
            if cmd in (CMD_D,CMD_K,CMD_L):
                if raw: st.mem[CMD_D]=raw
                return raw or st.mem.get(CMD_D,0)
            if cmd in (CMD_E,CMD_F,CMD_I,CMD_J,CMD_Q,CMD_R,CMD_S):
                if raw: st.mem[cmd]=raw
                return raw or st.mem.get(cmd,0)
            return raw
        if self.fmt=='MOD':
            # ProTracker memory is deliberately sparse. 1xx/2xx/Axy and the
            # volume half of 5xy/6xy do NOT recall parameter 00. Tone-porta,
            # vibrato nibbles and 9xx do have memory.
            if cmd==CMD_G:
                p=raw or st.g_mem
                if raw: st.g_mem=raw
                return p
            if cmd==CMD_H:
                if raw & 0xF0: st.vib_speed=(raw>>4)&15
                if raw & 0x0F: st.vib_depth=raw&15
                return (st.vib_speed<<4)|st.vib_depth
            if cmd==CMD_O:
                p=raw or st.o_mem
                if raw: st.o_mem=raw
                return p
            return raw
        # XM. FT2 has several deliberately unlinked memories.
        if cmd==CMD_G:
            p=raw or st.g_mem
            if raw: st.g_mem=raw
            return p
        if cmd==CMD_H:
            if raw & 0xF0: st.vib_speed=(raw>>4)&15
            if raw & 0x0F: st.vib_depth=raw&15
            return (st.vib_speed<<4)|st.vib_depth
        if cmd==CMD_XM_TREMOLO:
            if raw & 0xF0: st.xm_tremolo_speed=(raw>>4)&15
            if raw & 0x0F: st.xm_tremolo_depth=raw&15
            return (st.xm_tremolo_speed<<4)|st.xm_tremolo_depth
        if cmd==CMD_O:
            # FT2 only updates 9xx memory when a note is present; caller can
            # suppress the write by setting xm_offset_no_store on the event.
            p=raw or st.o_mem
            if raw: st.o_mem=raw
            return p
        if cmd==CMD_J and raw==0: return 0
        if self.fmt=='XM':
            if cmd in (CMD_D,CMD_K,CMD_L):
                if raw: st.xm_volslide_mem=raw
                return raw or st.xm_volslide_mem
            if cmd==CMD_XM_FINE_UP:
                if raw: st.xm_fine_porta_mem=(st.xm_fine_porta_mem&0x0F)|(raw<<4)
                return raw or ((st.xm_fine_porta_mem>>4)&15)
            if cmd==CMD_XM_FINE_DOWN:
                if raw: st.xm_fine_porta_mem=(st.xm_fine_porta_mem&0xF0)|raw
                return raw or (st.xm_fine_porta_mem&15)
            if cmd==CMD_XM_XFINE_UP:
                if raw: st.xm_xfine_porta_mem=(st.xm_xfine_porta_mem&0x0F)|(raw<<4)
                return raw or ((st.xm_xfine_porta_mem>>4)&15)
            if cmd==CMD_XM_XFINE_DOWN:
                if raw: st.xm_xfine_porta_mem=(st.xm_xfine_porta_mem&0xF0)|raw
                return raw or (st.xm_xfine_porta_mem&15)
            if cmd==CMD_XM_FINEVOLUP:
                if raw: st.xm_fine_vol_mem=(st.xm_fine_vol_mem&0x0F)|(raw<<4)
                return raw or ((st.xm_fine_vol_mem>>4)&15)
            if cmd==CMD_XM_FINEVOLDOWN:
                if raw: st.xm_fine_vol_mem=(st.xm_fine_vol_mem&0xF0)|raw
                return raw or (st.xm_fine_vol_mem&15)
            if cmd==CMD_XM_PANSLIDE:
                if raw: st.xm_pan_mem=raw
                return raw or st.xm_pan_mem
            if cmd==CMD_XM_GVOLSLIDE:
                if raw: st.xm_gvol_mem=raw
                return raw or st.xm_gvol_mem
            if cmd==CMD_XM_RETRIG:
                hi=raw&0xF0; lo=raw&0x0F
                if hi: st.xm_retrig_mem=(st.xm_retrig_mem&0x0F)|hi
                if lo: st.xm_retrig_mem=(st.xm_retrig_mem&0xF0)|lo
                return st.xm_retrig_mem
            if cmd in (CMD_E,CMD_F,CMD_Q):
                if raw: st.mem[cmd]=raw
                return raw or st.mem.get(cmd,0)
            return raw
        if cmd in (CMD_D,CMD_E,CMD_F,CMD_K,CMD_L,CMD_Q):
            if raw: st.mem[cmd]=raw
            return raw or st.mem.get(cmd,0)
        return raw

    @staticmethod
    def _tracker_pan_to_opl4(value:int)->int:
        # Match the Z80 runtime's 0..255 tracker-pan conversion.
        value=max(0,min(255,int(value)))
        if value<128:
            q=(value>>4)&7
            x=7-q
            return 0 if x==0 else x+8
        q=((value-128)>>4)&7
        return 0 if q==0 else q

    def _pan_nibble(self,ch:int)->int:
        pans=getattr(self.m,'channel_panning_nibbles',None)
        if pans is not None and ch<len(pans) and pans[ch] is not None:
            # S3M's 0..15 table spans the complete stereo field.
            tracker_pan=(int(pans[ch])*256+7)//15
            return self._tracker_pan_to_opl4(min(255,tracker_pan))
        if self.fmt in S3M_FMTS and not bool(getattr(self.m,'s3m_is_stereo',True)):
            return 0
        setting=self.m.channel_settings[ch] if ch < len(self.m.channel_settings) else 0
        return 11 if setting < 8 else 5

    def _xm_resolve_sample(self,instrument_num:int,noteidx:int):
        if self.fmt!='XM' or instrument_num<=0 or noteidx<0:
            return None
        ids=getattr(self.m,'xm_instrument_sample_ids',{}).get(int(instrument_num),())
        if not ids:
            return None
        km=getattr(self.m,'xm_instrument_keymaps',{}).get(int(instrument_num),())
        key=max(0,min(95,int(noteidx)))
        si=(int(km[key]) if key<len(km) else 0)
        return ids[si] if 0<=si<len(ids) and ids[si] in self.m.samples else None

    def _it_resolve_instrument(self,instrument_num:int,noteidx:int):
        if self.fmt!='IT' or not bool(getattr(self.m,'it_instrument_mode',False)) or instrument_num<=0 or noteidx<0:
            return noteidx,None
        km=getattr(self.m,'it_instrument_keymaps',{}).get(int(instrument_num),())
        key=max(0,min(119,int(noteidx)))
        if key>=len(km):
            raise ValueError(f'IT instrument {instrument_num}: note-map key {key} is missing')
        mapped_note,sample_num=km[key]
        mapped_note=int(mapped_note)
        if not 0<=mapped_note<=119: mapped_note=noteidx
        sample_num=int(sample_num)
        if sample_num not in self.m.samples:
            raise ValueError(f'IT instrument {instrument_num}: note-map key {key} selects empty/invalid sample {sample_num}; this semantic is not yet supported')
        return mapped_note,sample_num

    @staticmethod
    def _trunc_div2(v:int)->int:
        return (v//2) if v>=0 else -((-v)//2)

    def _it_note_pan_gain(self,instrument_num:int,sample_num:int,original_note_idx:int,base_tracker_pan:int):
        """Return (tracker_pan, pan_was_reset, SVxIV gain 0..64) for an IT note.

        IT applies instrument panning first, then sample panning (sample wins),
        then pitch/pan separation from the *original pattern note*.  Sample and
        instrument global volume form an independent per-voice multiplier.
        """
        smp=self.m.samples.get(int(sample_num)) if sample_num else None
        inst=(getattr(self.m,'it_instruments',{}).get(int(instrument_num))
              if bool(getattr(self.m,'it_instrument_mode',False)) and instrument_num else None)
        pan256=max(0,min(256,(max(0,min(255,int(base_tracker_pan)))*256+127)//255))
        reset=False
        if inst is not None:
            dfp=int(inst.get('default_pan',0x80))
            if not (dfp & 0x80):
                pan256=max(0,min(64,dfp&0x7F))*4; reset=True
        if smp is not None:
            dfp=int(getattr(smp,'it_default_pan',0))
            if dfp & 0x80:
                pan256=max(0,min(64,dfp&0x7F))*4; reset=True
        if inst is not None and int(inst.get('pps',0)) and original_note_idx>=0:
            delta=self._trunc_div2((int(original_note_idx)-int(inst.get('ppc',0)))*int(inst.get('pps',0)))
            pan256=max(0,min(256,pan256+delta)); reset=True
        pan255=max(0,min(255,(pan256*255+128)//256))
        gain=max(0,min(64,int(getattr(smp,'it_global_volume',64)))) if smp is not None else 64
        if inst is not None:
            # IT gbv is 0..128; OpenMPT converts it to 0..64 and then computes
            # sampleGlobal * instrumentGlobal / 64, i.e. raw SV*gbv/128.
            gain=max(0,min(64,(gain*max(0,min(128,int(inst.get('global_volume',128)))))//128))
        return pan255,reset,gain

    def _mod_period(self,ins,noteidx,ft_override=None):
        smp=self.m.samples[ins]
        ft=int(getattr(smp,'mod_finetune',0)) if ft_override is None else int(ft_override)&15
        # Internal note 48 is C-2 / ProTracker period 428.  The tuned table is
        # one octave above that reference and is shifted by note octave.
        octave=(int(noteidx)-24)//12; semi=int(noteidx)%12
        base=self.MOD_TUNED_PERIODS[(ft&15)*12+semi]
        if octave>=0: per=base>>octave
        else: per=base<<(-octave)
        return float(max(1,per))

    def _period(self,ins,noteidx):
        s=self.m.samples[ins]
        freq=s.c2spd*(2.0**((noteidx-48)/12.0))
        return core.PERIOD_CLOCK/max(1.0,freq)


    # Realtime S3M pitch state is four times the host reference period.
    # This makes E/F/G/H deltas integer while preserving the exact C2SPD
    # exponential note relation used by the proven Second Reality converter.
    ST3_CLOCK=core.PERIOD_CLOCK*4.0

    def _s3m_period_q(self,ins,noteidx,c5_override=0):
        smp=self.m.samples[ins]
        c5=int(c5_override) if c5_override else int(smp.c2spd)
        freq=float(c5)*(2.0**((int(noteidx)-48)/12.0))
        period=core.PERIOD_CLOCK/max(1.0,freq)
        return max(1,min(65535,int(round(period*4.0))))

    def _s3m_pitch_regs(self,period_q):
        # period_q is exactly four times the physical/reference period.
        return core.Compiler._pitch_regs(max(0.25,float(period_q)/4.0))

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

    XM_AMIGA_TABLE=(907,900,894,887,881,875,868,862,856,850,844,838,832,826,820,814,
        808,802,796,791,785,779,774,768,762,757,752,746,741,736,730,725,720,715,709,704,
        699,694,689,684,678,675,670,665,660,655,651,646,640,636,632,628,623,619,614,610,
        604,601,597,592,588,584,580,575,570,567,563,559,555,551,547,543,538,535,532,528,
        524,520,516,513,508,505,502,498,494,491,487,484,480,477,474,470,467,463,460,457,
        453,450,447,443,440,437,434,431)

    def _xm_amiga_period(self,ins,noteidx,ft_override=None):
        """FT2 Amiga-frequency-table period, in the same native period units
        used by OpenMPT/FT2. Slides use parameter*4 in this domain.
        """
        smp=self.m.samples[ins]
        note=int(noteidx)+int(getattr(smp,'xm_relative_note',0))
        # OpenMPT's note passed to this branch has already been shifted down by
        # one octave (XM C-0 -> internal table note 0 after clamp at C-0).
        note=max(0,note)
        ft=int(getattr(smp,'xm_finetune',0)) if ft_override is None else int(ft_override)
        # FT2 truncates the low 3 finetune bits before period lookup.
        ft &= ~7
        rnote=(note%12)<<3; roct=note//12; rfine=int(ft/16)
        i=max(0,min(103,rnote+rfine+8)); p1=self.XM_AMIGA_TABLE[i]
        if ft<0:
            rfine-=1; af=-ft
        else:
            rfine+=1; af=ft
        i=max(0,min(103,rnote+rfine+8)); p2=self.XM_AMIGA_TABLE[i]
        frac=af&15
        per=((p1*(16-frac)+p2*frac)<<1)>>roct
        # Oversize-sample decimation is a frequency multiplier. Apply it to
        # Amiga periods as a reciprocal scale.
        off=int(getattr(smp,'xm_period_offset',0))
        if off: per=int(round(per*(2.0**(off/768.0))))
        return max(1,min(65535,per))

    def _xm_linear_period(self,ins,noteidx,ft_override=None):
        """Return the bit-exact FT2 linear-period state for a note/sample.

        FT2's table is linearPeriodLUT[i] = (1936-i)*4. For a zero-based
        XM note index this reduces to 7680 - note*64 - (finetune>>3)*4.
        Relative-note is applied before the lookup. A constant compensation is
        added if an oversized sample had to be decimated for the OPL4.
        """
        smp=self.m.samples[ins]
        rel=int(getattr(smp,'xm_relative_note',0))
        ft=int(getattr(smp,'xm_finetune',0)) if ft_override is None else int(ft_override)
        # Python's right shift is arithmetic for negative integers, matching
        # FT2's ((int8_t)finetune >> 3).
        period=7680 - (noteidx+rel)*64 - (ft>>3)*4 + int(getattr(smp,'xm_period_offset',0))
        return max(1,min(31999,int(period)))

    @staticmethod
    def _xm_linear_pitch_regs(period):
        # FT2 linear-frequency relation. Convert only at the final hardware
        # boundary; slides/porta/vibrato remain in the linear period domain.
        freq=8363.0*(2.0**((4608.0-float(period))/768.0))
        physical_period=core.PERIOD_CLOCK/max(1.0,freq)
        return core.Compiler._pitch_regs(physical_period)

    def _note_index(self,n): return ((n>>4)&15)*12+(n&15)

    def _event_action(self,e, st:ResolveState)->Optional[Action]:
        cmd=e.cmd or 0; p=e.param or 0
        semantic_cmd=cmd
        if cmd:
            if self.fmt=='XM' and cmd==CMD_O and p and not bool(getattr(e,'xm_note_present',False)):
                p = st.o_mem  # FT2: 9xx without a note does not store new offset memory
            else:
                p=self._resolve(st,cmd,p)
        if self.fmt=='MOD' and semantic_cmd in (CMD_D,CMD_K,CMD_L):
            # ProTracker Axy / 5xy / 6xy uses high-nibble priority when both
            # nibbles are non-zero; this is not S3M fine-slide syntax.
            p=(p & 0xF0) if (p & 0xF0) else (p & 0x0F)
        if self.fmt=='MOD' and semantic_cmd==CMD_X and int(getattr(e,'mod_raw_effect',-1))==0x8 and bool(getattr(self.m,'mod_fix_7bit_panning',False)):
            if p==0xA4:
                # Paula surround has no direct OPL4 equivalent; centre it.
                p=0x80
                self.warnings.append(f'row event on channel {e.ch}: MOD surround pan 8A4 approximated as centre')
            else:
                p=min(255,p*2)
        if semantic_cmd==CMD_XM_XFINE_DOWN:
            cmd=CMD_E; p=0xE0|(p&15)
        elif semantic_cmd==CMD_XM_XFINE_UP:
            cmd=CMD_F; p=0xE0|(p&15)
        elif semantic_cmd==CMD_XM_FINE_UP:
            cmd=CMD_F; p=0xF0|(p&15)
        elif semantic_cmd==CMD_XM_FINE_DOWN:
            cmd=CMD_E; p=0xF0|(p&15)
        # Keep the resolved command for compile-time flow effects (SBx loops).
        e.resolved_param=p
        effects=[]
        delay=-1
        sx=(p>>4)&15 if cmd==CMD_S else -1
        sl=p&15 if cmd==CMD_S else 0

        # MOD extended commands. Keep ProTracker semantics separate from the
        # S3M engine: 1xx/2xx/Axy are ordinary effects, while E1/E2/EA/EB
        # are dedicated tick-0 fine effects.
        if self.fmt=='MOD' and cmd in (CMD_MOD_FILTER,CMD_MOD_FINE_UP,CMD_MOD_FINE_DOWN,CMD_MOD_GLISS,CMD_MOD_VIBWAVE,CMD_MOD_FINETUNE,CMD_MOD_PATLOOP,CMD_MOD_TREMWAVE,CMD_MOD_PAN4,CMD_MOD_FINEVOLUP,CMD_MOD_FINEVOLDOWN,CMD_MOD_PATDELAY,CMD_MOD_INVERT):
            if cmd==CMD_MOD_FILTER:
                pass  # Amiga LED filter has no OPL4 analogue.
            elif cmd in (CMD_MOD_FINE_UP,CMD_MOD_FINE_DOWN,CMD_MOD_GLISS,CMD_MOD_VIBWAVE,CMD_MOD_TREMWAVE,CMD_MOD_FINEVOLUP,CMD_MOD_FINEVOLDOWN,CMD_MOD_PATDELAY):
                effects.append((cmd,p&15,None))
            elif cmd==CMD_MOD_FINETUNE:
                st.mod_finetune=p&15
                effects.append((CMD_MOD_FINETUNE,p&15,None))
            elif cmd==CMD_MOD_PATLOOP:
                pass  # flattened in compile()
            elif cmd==CMD_MOD_PAN4:
                if not bool(getattr(self.m,'mod_ignore_panning',False)):
                    effects.append((CMD_X,((p&15)*255+7)//15,None))
            elif cmd==CMD_MOD_INVERT:
                # Store OpenMPT/PT's actual funk-delay increment rather than
                # the nibble, so the Z80 runtime needs no 16-byte speed table.
                effects.append((cmd,MOD_EFX_SPEED[p&15],None))
        # S3M extended commands. State-only commands are encoded as private
        # semantic commands and consumed by the Z80 parser; they do not waste
        # a realtime effect slot.
        elif cmd==CMD_S:
            if self.fmt=='IT':
                # Native IT leaves S1x/S2x unimplemented. S3x/S4x only accept
                # waveform values 0..3; larger values are ignored, not masked.
                if sx in (0x1,0x2):
                    pass
                elif sx==0x3:
                    if sl<=3: effects.append((CMD_ST3_VIB_WAVE,sl,None))
                elif sx==0x4:
                    if sl<=3: effects.append((CMD_ST3_TREM_WAVE,sl,None))
                elif sx==0x5:
                    if sl<=3: effects.append((CMD_IT_PAN_WAVE,sl,None))
                elif sx==0x6: effects.append((CMD_ST3_TICK_DELAY,sl,None))
                elif sx==0x8:
                    pv=(sl*255+7)//15
                    effects.append((CMD_X,pv,None)); st.it_pan_tracker=pv
                elif sx==0xA: st.high_offset=sl
                elif sx==0xB: pass  # flattened by compile() below
                elif sx==0xC: effects.append((CMD_NOTE_CUT,sl or 1,None))
                elif sx==0xD: delay=sl or 1
                elif sx==0xE: effects.append((CMD_ST3_PATTERN_DELAY,sl,None))
            else:
                if sx==0x1: effects.append((CMD_GLISS,sl,None))
                elif sx==0x2:
                    st.finetune_c5=S3M_FINETUNE[sl]
                    # Retune a currently playing note immediately. Future notes use
                    # the new channel C5 speed directly in their encoded period.
                    cur_ins=(e.ins if e.ins in self.m.samples else st.instrument)
                    has_new_note=(e.note is not None and e.note < 254)
                    curpq=self._s3m_period_q(cur_ins,st.note_index,st.finetune_c5) if (not has_new_note and cur_ins in self.m.samples and st.note_index>=0) else 0
                    effects.append((CMD_ST3_FINETUNE,sl,(curpq,0)))
                elif sx==0x3: effects.append((CMD_ST3_VIB_WAVE,sl&3,None))
                elif sx==0x4: effects.append((CMD_ST3_TREM_WAVE,sl&3,None))
                elif sx==0x6: effects.append((CMD_ST3_TICK_DELAY,sl,None))
                elif sx==0x8: effects.append((CMD_X,(sl*255+7)//15,None))
                elif sx==0xA: st.high_offset=sl
                elif sx==0xB: pass  # flattened by compile() below
                elif sx==0xC:
                    # ST3 explicitly ignores SC0. IT-authored S3M treats SC0 as SC1.
                    if sl or self.fmt!='S3M': effects.append((CMD_NOTE_CUT,sl or 1,None))
                elif sx==0xD: delay=sl
                elif sx==0xE:
                    if sl or self.fmt!='S3M': effects.append((CMD_ST3_PATTERN_DELAY,sl,None))
        elif cmd==CMD_K:
            if self.fmt=='S3M':
                effects=[(CMD_ST3_COMBINED_H,0,None),(CMD_ST3_COMBINED_D,p,None)]
            else:
                effects=[(CMD_H,(st.vib_speed<<4)|st.vib_depth,None),(CMD_D,p,None)]
        elif cmd==CMD_L:
            if self.fmt=='S3M':
                effects=[(CMD_ST3_COMBINED_G,st.g_mem,None),(CMD_ST3_COMBINED_D,p,None)]
            else:
                effects=[(CMD_G,st.g_mem,None),(CMD_D,p,None)]
        elif self.fmt=='XM' and cmd in (CMD_XM_FINETUNE,CMD_XM_PATLOOP,CMD_XM_STOP):
            pass  # E5/E6/F00 are handled by the host compiler.
        elif cmd not in (0,CMD_B,CMD_C,CMD_O):
            effects.append((cmd,p,None))

        if self.fmt=='MOD' and bool(getattr(self.m,'mod_ignore_panning',False)):
            effects=[fx for fx in effects if fx[0] != CMD_X]

        # S3M volume-column 128..192 is panning 0..64.
        vpan=getattr(e,'volume_pan',None)
        if vpan is not None and self.fmt in S3M_FMTS:
            effects.insert(0,(CMD_X,(max(0,min(64,int(vpan)))*255+32)//64,None))
            if self.fmt=='IT': st.it_pan_tracker=(max(0,min(64,int(vpan)))*255+32)//64

        # Extra semantic effects from XM volume column etc.
        for ex in getattr(e,'extra_effects',[]):
            if len(ex)>=3: vc,vp,usemem=ex[:3]
            else: vc,vp=ex; usemem=True
            # FT2 PanOff.xm quirk: volume-column Cx is ignored next to a
            # delayed Note Off. Effect-column panning on the same row survives.
            volcol=int(getattr(e,'xm_volume_column',0) or 0)
            if self.fmt=='XM' and e.note==254 and delay>0 and 0xC0<=volcol<=0xCF and vc==CMD_X:
                continue
            rp=self._resolve(st,vc,vp) if usemem else vp
            effects.append((vc,rp,None))
        if len(effects)>6:
            self.warnings.append(f'row event on channel {e.ch}: more than six semantic effects; extras dropped')
            effects=effects[:6]

        # FT2 row semantics that affect note/instrument handling have to be
        # known before default-volume/profile actions are generated.
        row_wants_porta=(cmd in (CMD_G,CMD_L) or any(ec==CMD_XM_VOLPORTA for ec,_,_ in effects))
        k00_suppresses_note=(self.fmt=='XM' and cmd==CMD_KEYOFF and p==0)
        xm_out_of_range_delay=(self.fmt=='XM' and delay>=0 and delay>=self.speed)
        if self.fmt=='XM' and delay>0:
            # FT2: note + tone-portamento + EDx becomes a delayed normal note.
            row_wants_porta=False

        if self.fmt=='IT' and cmd==CMD_X:
            st.it_pan_tracker=max(0,min(255,int(p)))
        if self.fmt=='IT' and cmd==CMD_M and 0<=p<=64:
            st.it_channel_volume=int(p)
        a=Action(e.ch)
        a.delay_tick=delay
        old_ins=st.instrument
        xm_ins_present = bool(getattr(e,'xm_instrument_present',False)) if self.fmt=='XM' else False
        it_ins_present = bool(getattr(e,'it_instrument_present',False)) if self.fmt=='IT' else False
        it_note_idx = (self._note_index(e.note) if self.fmt=='IT' and e.note is not None and e.note<254 else st.note_index)
        it_pattern_note_idx = it_note_idx
        if self.fmt=='XM':
            literal_inum=int(getattr(e,'xm_instrument_number',0)) if xm_ins_present else 0
            effective_inum=literal_inum or st.xm_instrument_num
            map_note=(self._note_index(e.note) if e.note is not None and e.note<254 else st.note_index)
            mapped_sample=self._xm_resolve_sample(effective_inum,map_note)
            # FT2 ignores notes whose pattern note + sample RelativeTone leaves
            # its real-note range. OpenMPT checks the internal note against
            # NOTE_MIN+11..NOTE_MIN+130; XM file note 1 maps to internal +12.
            xm_note_limit_bad=False
            if e.note is not None and e.note < 254 and mapped_sample in self.m.samples:
                ni_lim=self._note_index(e.note)
                rel_lim=int(getattr(self.m.samples[mapped_sample],'xm_relative_note',0))
                computed_internal=ni_lim + 13 + rel_lim
                xm_note_limit_bad=not (12 <= computed_internal <= 131)
            literal_ins=(mapped_sample if xm_ins_present else None)
            valid_ins=literal_ins
            # A tone-portamento target always belongs to the currently playing
            # sample; a normal note is re-keymapped through the current XM instrument.
            note_sample=(old_ins if row_wants_porta and st.period_seen else mapped_sample)
            use_ins=note_sample
        elif self.fmt=='IT' and bool(getattr(self.m,'it_instrument_mode',False)):
            xm_note_limit_bad=False
            literal_inum=int(getattr(e,'it_instrument_number',0)) if it_ins_present else 0
            effective_inum=literal_inum or st.it_instrument_num
            it_note_idx,mapped_sample=self._it_resolve_instrument(effective_inum,it_note_idx)
            literal_ins=(mapped_sample if it_ins_present and e.note is not None and e.note<254 else None)
            valid_ins=literal_ins
            note_sample=(old_ins if row_wants_porta and st.period_seen and old_ins else mapped_sample)
            use_ins=note_sample or old_ins
            xm_ins_present=False
        else:
            xm_note_limit_bad=False
            literal_inum=0
            literal_ins=e.ins if e.ins in self.m.samples else None
            valid_ins=literal_ins
            note_sample=valid_ins or old_ins
            use_ins=note_sample or old_ins
            xm_ins_present=bool(valid_ins)
        a.xm_instrument_present=xm_ins_present
        # Runtime needs this literal-instrument marker for FT2's bizarre
        # volume-column + EDx timing. It is parser-immediate and consumes no
        # realtime effect slot.
        if self.fmt=='XM' and delay>0 and getattr(e,'extra_effects',[]):
            effects.insert(0,(CMD_XM_ROWDELAY,delay&15,None))
            if xm_ins_present:
                effects.insert(1,(CMD_XM_ROWINS,1,None))
        if self.fmt=='XM' and any(ec==CMD_XM_RETRIG for ec,_,_ in effects):
            # FT2 Rxy tick-0 logic depends on the literal row fields, not only
            # on playback state. Carry the relevant bits as parser-immediate
            # semantic markers; they consume no realtime effect slot.
            if e.note is not None and e.note < 254:
                effects.insert(0,(CMD_XM_ROWNOTE,1,None))
            if xm_ins_present and e.note != 254 and not any(ec==CMD_XM_ROWINS for ec,_,_ in effects):
                effects.insert(0,(CMD_XM_ROWINS,1,None))
            vc=int(getattr(e,'xm_volume_column',0) or 0)
            if 0x11 <= vc <= 0x50:
                effects.insert(0,(CMD_XM_ROWVOL,1,None))
        if self.fmt=='IT' and bool(getattr(self.m,'it_instrument_mode',False)) and it_ins_present:
            st.it_instrument_num=literal_inum
        if valid_ins and not (cmd==CMD_S and sx==0x2):
            # Loading an instrument/sample restores its native tuning.
            st.finetune_c5=0
            if self.fmt=='MOD':
                st.mod_finetune=int(getattr(self.m.samples[valid_ins],'mod_finetune',0)) & 15
                # Runtime marker: PT changes the channel finetune on every
                # literal instrument and resets the EFx byte offset there.
                effects.insert(0,(CMD_MOD_INSTR,st.mod_finetune,None))

        # Immediate volume semantics. FT2 new-instrument + tone-portamento
        # ignores the new instrument but reloads the OLD instrument settings.
        # K00 ignores note+instrument on the row altogether.
        if delay < 0 and valid_ins and (self.fmt!='XM' or xm_ins_present) and not k00_suppresses_note:
            vol_ins=(old_ins if self.fmt=='XM' and old_ins and (row_wants_porta or xm_note_limit_bad or e.note==254) else valid_ins)
            if vol_ins in self.m.samples:
                a.volume=self.m.samples[vol_ins].volume
        if e.vol is not None and e.vol<=64:
            a.volume=e.vol
        # S3M/ST3 volume is a true 0..64 range.  Do not fold 64 to 63:
        # ST3's own fine/regular slides clamp at 64, and sample defaults and
        # pattern volume cells are allowed to contain 64.
        if self.fmt in S3M_FMTS and a.volume is not None:
            a.volume=min(64,a.volume)

        xm_ft_override=(((p & 15)-8)*16 if self.fmt=='XM' and cmd==CMD_XM_FINETUNE and e.note is not None and e.note<254 else None)
        mod_ft_override=((p&15) if self.fmt=='MOD' and cmd==CMD_MOD_FINETUNE else None)
        it_special=(getattr(e,'it_note_special',None) if self.fmt=='IT' else None)
        if self.fmt=='IT' and it_special in ('off','cut','fade') and not k00_suppresses_note:
            a.note_kind=it_special
        elif e.note is not None and not k00_suppresses_note and not xm_out_of_range_delay and not xm_note_limit_bad:
            if e.note==254:
                a.note_kind='delay_off' if delay>=0 else 'off'
                # FT2 key-off releases the volume envelope/fadeout; it does not
                # force volume to zero when an envelope is active.
                if self.fmt not in ('XM','IT') and delay<0:
                    a.volume=0
                if self.fmt=='XM' and delay>=0 and xm_ins_present and old_ins in self.m.samples:
                    a.delayed_volume=self.m.samples[old_ins].volume
                else:
                    a.delayed_volume=(0 if (delay>=0 and self.fmt not in ('XM','IT')) else 0xFF)
            elif e.note<254 and use_ins in self.m.samples:
                ni=(it_note_idx if self.fmt=='IT' else self._note_index(e.note))
                if self.fmt=='XM':
                    pitch_ft=(xm_ft_override if xm_ft_override is not None else (st.xm_channel_finetune if row_wants_porta and st.period_seen else None))
                    if self.xm_linear:
                        pq=self._xm_linear_period(use_ins,ni,pitch_ft); lo,hi=self._xm_linear_pitch_regs(pq)
                    else:
                        pq=self._xm_amiga_period(use_ins,ni,pitch_ft); lo,hi=core.Compiler._pitch_regs(max(0.25,float(pq)/4.0))
                elif self.fmt in S3M_FMTS:
                    # S3M profiles use their own integer period/C5-speed domain and C4-speed domain.
                    # Keep that exact period as runtime state so slides/porta/vibrato
                    # cannot inherit MOD/Paula rounding or clock assumptions.
                    pq=self._s3m_period_q(use_ins,ni,st.finetune_c5)
                    c5=st.finetune_c5 or self.m.samples[use_ins].c2spd
                    freq=float(c5)*(2.0**((ni-48)/12.0))
                    lo,hi=core.Compiler._pitch_regs(core.PERIOD_CLOCK/max(1.0,freq))
                else:
                    if self.fmt=='MOD':
                        period=self._mod_period(use_ins,ni,mod_ft_override if mod_ft_override is not None else st.mod_finetune)
                    else:
                        period=self._period(use_ins,ni)
                    pq=max(1,min(65535,int(round(period*4.0))))
                    lo,hi=core.Compiler._pitch_regs(period)
                wants_porta=row_wants_porta
                porta=wants_porta and st.period_seen
                suppress_new_note=(self.fmt=='XM' and self.xm_ft2_porta_no_note and wants_porta and not st.period_seen)
                if self.fmt=='XM' and porta and xm_ins_present and old_ins:
                    # FT2 ignores the new instrument number on tone-portamento rows.
                    use_ins=old_ins
                    if self.xm_linear: pq=self._xm_linear_period(use_ins,ni,pitch_ft)
                    else: pq=self._xm_amiga_period(use_ins,ni,pitch_ft)
                if suppress_new_note:
                    # 3xx / volume-column Fx with no active note has no note trigger.
                    # Effects on the row still execute, but no period/sample state is created.
                    pass
                elif porta:
                    if self.fmt in S3M_FMTS and bool(getattr(self.m,'s3m_porta_sample_change',False)) and delay<0 and valid_ins and old_ins and valid_ins!=old_ins:
                        # IT's S3M profile swaps/restarts the new sample while
                        # keeping the old pitch and sliding towards the new note.
                        wave=self.bank.get(valid_ins,0)
                        a.note_kind='porta_swap'
                        a.tone=(wave-384)
                    elif (self.fmt=='MOD' and bool(getattr(self.m,'mod_sample_swap',False)) and delay<0
                          and valid_ins and old_ins and valid_ins!=old_ins):
                        # OPL4 has no per-voice sample-end interrupt. Preserve
                        # PT's sample selection and porta target and switch the
                        # wave at the row boundary (documented approximation).
                        wave=self.bank.get(valid_ins,0)
                        a.note_kind='porta_swap'
                        a.tone=(wave-384) | (0x80 if self.m.samples[valid_ins].looped else 0)
                        if not getattr(self,'_warned_mod_swap_boundary',False):
                            self.warnings.append('ProTracker sample swaps are applied at the tracker row boundary; OPL4 exposes no sample-end callback')
                            self._warned_mod_swap_boundary=True
                    else:
                        a.note_kind='delay_porta' if delay>=0 else 'porta'
                    a.period_q=pq
                else:
                    if cmd==CMD_O:
                        off=(st.high_offset<<16) + p*256
                    elif self.fmt=='S3M' and not valid_ins:
                        # ST3 recalls the previous note's sample offset when a
                        # new note omits the instrument number.
                        off=st.note_offset
                    else:
                        off=0
                    smp=self.m.samples[use_ins]
                    if self.fmt=='IT' and cmd==CMD_O and off>=smp.length:
                        # Native IT (new-effects mode) ignores an out-of-range
                        # Oxx rather than selecting a silent/end-of-sample wave.
                        off=0
                    if self.fmt=='XM' and cmd==CMD_O and off>=smp.length and self.xm_ft2_offset_oor:
                        # FT2 9xx past sample end zeros the active period instead of
                        # starting a one-byte/silent offset variant. Skale explicitly
                        # disables this quirk, in which case the silent variant below
                        # preserves period state for later effects.
                        a.note_kind='off'
                        st.period_seen=False
                    if self.fmt=='S3M' and cmd==CMD_O and smp.looped and off>=smp.loop_end:
                        if bool(getattr(self.m,'s3m_use_gus',False)):
                            span=max(1,smp.loop_end-smp.loop_begin)
                            off=((off-smp.loop_begin)%span)+smp.loop_begin
                        else:
                            # ST3/SB stops the sample instead of GUS-style loop wrap.
                            off=smp.length
                    if a.note_kind!='off':
                        wave=self.bank.get(use_ins,off)
                        a.tone=wave-384
                        a.period_q=pq; a.pitch_lo=lo|1; a.pitch_hi=hi
                        a.note_kind='delay_normal' if delay>=0 else 'normal'
                    if self.fmt=='S3M':
                        st.note_offset=off
                if delay>=0 and valid_ins and e.vol is None and (self.fmt!='XM' or xm_ins_present):
                    a.delayed_volume=min(64,self.m.samples[valid_ins].volume) if self.fmt in S3M_FMTS else self.m.samples[valid_ins].volume
                if not suppress_new_note and a.note_kind!='off':
                    st.note_index=ni
                    st.period_seen=True
                    if self.fmt=='XM' and not porta:
                        st.xm_channel_finetune=(int(xm_ft_override) if xm_ft_override is not None else int(getattr(self.m.samples[use_ins],'xm_finetune',0)))
        elif valid_ins and delay>=0:
            # Delayed instrument without a note is unusual; preserve its eventual default volume.
            a.delayed_volume=self.m.samples[valid_ins].volume

        # FT2 EDx (x>0) with no note retriggers the previous note at tick x.
        # It behaves as a bare note: envelopes retrigger, existing panning stays.
        if (self.fmt=='XM' and delay>0 and delay<self.speed and e.note is None
                and st.period_seen and old_ins in self.m.samples and a.note_kind is None):
            ni=st.note_index; use_ins=old_ins
            if self.xm_linear:
                pq=self._xm_linear_period(use_ins,ni); lo,hi=self._xm_linear_pitch_regs(pq)
            else:
                pq=self._xm_amiga_period(use_ins,ni); lo,hi=core.Compiler._pitch_regs(max(0.25,float(pq)/4.0))
            wave=self.bank.get(use_ins,0)
            a.note_kind='delay_normal'; a.tone=wave-384; a.period_q=pq; a.pitch_lo=lo|1; a.pitch_hi=hi
            a.delay_tick=delay; a.delayed_volume=0xFF; a.xm_instrument_present=False

        # ST3 switches the active sample on an instrument-only cell without
        # retriggering the voice or converting the current period. The default
        # volume was already applied above. Avoid redundant writes when the
        # selected sample is unchanged (as in Purple Motion's repeated #24).
        if (self.fmt in S3M_FMTS and getattr(self.m,'s3m_sample_swap',self.fmt!='S3M')
                and valid_ins and old_ins and valid_ins!=old_ins
                and (e.note is None or e.note==255) and delay<0):
            wave=self.bank.get(valid_ins,0)
            a.note_kind='sample_swap'
            a.tone=(wave-384)

        if (self.fmt=='MOD' and bool(getattr(self.m,'mod_sample_swap',False))
                and valid_ins and old_ins and valid_ins!=old_ins
                and e.note is None and delay<0):
            wave=self.bank.get(valid_ins,0)
            a.note_kind='sample_swap'; a.tone=(wave-384) | (0x80 if self.m.samples[valid_ins].looped else 0)
            if not getattr(self,'_warned_mod_swap_boundary',False):
                self.warnings.append('ProTracker sample swaps are applied at the tracker row boundary; OPL4 exposes no sample-end callback')
                self._warned_mod_swap_boundary=True

        # Native IT sample/instrument panning and SV*IV are note-trigger state,
        # not ordinary volume/pan effects. Parser-immediate markers make them
        # follow NNA physical-voice remapping while keeping same-row panning
        # commands later in the stream able to override the default panning.
        # A tone-portamento still constitutes a note change for IT's default
        # pan / PPS rules; it targets the already allocated physical voice.
        if self.fmt=='IT' and a.note_kind in ('normal','delay_normal','porta','delay_porta') and use_ins in self.m.samples:
            it_ins_mode=bool(getattr(self.m,'it_instrument_mode',False))
            selected_sample=(mapped_sample if it_ins_mode else (valid_ins or use_ins))
            if a.note_kind in ('porta','delay_porta') and old_ins and selected_sample in self.m.samples and selected_sample!=old_ins:
                raise ValueError(f'IT tone-portamento with sample change at order {self.order} row {self.row} channel {e.ch+1} needs exact IT sample/C5 swap semantics')
            pan_reset,gain_pan_reset,it_gain = self._it_note_pan_gain(
                effective_inum if it_ins_mode else 0,
                use_ins,it_pattern_note_idx,st.it_pan_tracker)
            row_has_pan=any(ec==CMD_X for ec,_,_ in effects)
            if a.note_kind in ('delay_normal','delay_porta') and (gain_pan_reset or it_gain!=64):
                raise ValueError(f'IT delayed note with sample/instrument default pan, PPS or non-neutral SV*IV at order {self.order} row {self.row} channel {e.ch+1} needs delayed trigger-state support')
            effects.insert(0,(CMD_IT_GAIN,it_gain,None))
            if gain_pan_reset:
                effects.insert(0,(CMD_X,pan_reset,None))
                if not row_has_pan:
                    st.it_pan_tracker=pan_reset

        # Native IT resets the selected instrument envelope/fade state on a
        # newly triggered note. With the IT header's Compatible-Gxx bit set,
        # an instrument number beside G/L also retriggers the envelopes.
        if self.fmt=='IT' and bool(getattr(self.m,'it_instrument_mode',False)):
            profile_reset=(a.note_kind in ('normal','delay_normal') or
                           (a.note_kind in ('porta','delay_porta') and it_ins_present
                            and bool(getattr(self.m,'it_compatible_gxx',False))))
            if profile_reset:
                inum=(int(getattr(e,'it_instrument_number',0)) if it_ins_present else 0) or st.it_instrument_num
                inst=getattr(self.m,'it_instruments',{}).get(inum)
                if inst:
                    effects.insert(0,(CMD_IT_PROFILE,int(inst.get('profile_id',0))&0xFF,None))

        # FT2 resets instrument envelope/fadeout/auto-vibrato state on an
        # instrument-only row and on instrument+tone-portamento. Normal notes
        # derive the profile directly from the custom-tone table at trigger time.
        if (self.fmt=='XM' and xm_ins_present and not xm_out_of_range_delay and (valid_ins or old_ins)
                and (a.note_kind in ('porta','delay_porta') or a.note_kind is None)):
            prof_ins=(old_ins if old_ins and (a.note_kind in ('porta','delay_porta') or xm_note_limit_bad) else valid_ins)
            pid=int(getattr(self.m.samples[prof_ins],'xm_profile_id',0)) & 0x3F
            effects.insert(0,(CMD_XM_PROFILE,pid,None))
            if len(effects)>6:
                self.warnings.append(f'row event on channel {e.ch}: FT2 profile reset plus >5 simultaneous effects; extras dropped')
                effects=effects[:6]

        # J/arpeggio needs two alternate absolute periods; encode them as command-specific payload.
        outfx=[]
        arp_ins=(note_sample if note_sample in self.m.samples else valid_ins or st.instrument)
        for ec,ep,_ in effects:
            extra=None
            if self.fmt=='IT' and bool(getattr(self.m,'it_linear_slides',False)) and ec in (CMD_E,CMD_F,CMD_G):
                extra=_it_linear_factor_pair(ep)
                ec={CMD_E:CMD_IT_LINEAR_E,CMD_F:CMD_IT_LINEAR_F,CMD_G:CMD_IT_LINEAR_G}[ec]
            if ec==CMD_J and ep and arp_ins in self.m.samples and st.note_index>=0:
                if self.fmt=='XM':
                    n1=st.note_index+((ep>>4)&15); n2=st.note_index+(ep&15)
                    if self.xm_ft2_arpeggio:
                        n1=min(108,n1); n2=min(108,n2)
                    if self.xm_linear:
                        p1=self._xm_linear_period(arp_ins,n1); p2=self._xm_linear_period(arp_ins,n2)
                    else:
                        p1=self._xm_amiga_period(arp_ins,n1); p2=self._xm_amiga_period(arp_ins,n2)
                    extra=(p1,p2)
                elif self.fmt in S3M_FMTS:
                    p1=self._s3m_period_q(arp_ins,st.note_index+((ep>>4)&15),st.finetune_c5)
                    p2=self._s3m_period_q(arp_ins,st.note_index+(ep&15),st.finetune_c5)
                    extra=(p1,p2)
                else:
                    if self.fmt=='MOD':
                        p1=self._mod_period(arp_ins,st.note_index+((ep>>4)&15),st.mod_finetune)
                        p2=self._mod_period(arp_ins,st.note_index+(ep&15),st.mod_finetune)
                    else:
                        p1=self._period(arp_ins,st.note_index+((ep>>4)&15))
                        p2=self._period(arp_ins,st.note_index+(ep&15))
                    extra=(max(1,min(65535,int(round(p1*4)))),max(1,min(65535,int(round(p2*4)))))
            outfx.append((ec,ep,extra))
        a.effects=outfx

        if self.fmt=='XM':
            if k00_suppresses_note or xm_out_of_range_delay or xm_note_limit_bad:
                pass
            elif a.note_kind in ('porta','delay_porta') and old_ins:
                st.instrument=old_ins
            elif note_sample in self.m.samples and e.note is not None and e.note<254:
                st.instrument=note_sample
            elif valid_ins:
                st.instrument=valid_ins
            if (xm_ins_present and not k00_suppresses_note and not xm_out_of_range_delay and not xm_note_limit_bad
                    and not (row_wants_porta and old_ins and st.period_seen)):
                st.xm_instrument_num=literal_inum
        elif valid_ins:
            st.instrument=valid_ins
        if self.fmt=='IT' and it_ins_present and not bool(getattr(self.m,'it_instrument_mode',False)):
            st.it_instrument_num=int(getattr(e,'it_instrument_number',0))
        if self.fmt=='MOD' and cmd==CMD_MOD_FINETUNE:
            st.mod_finetune=p&15
        # No runtime-relevant action? B/C/O only can disappear completely.
        if a.note_kind is None and a.volume is None and not a.effects:
            return None
        return a

    def _encode_action(self,a:Action)->bytes:
        flags=0
        if a.note_kind is not None: flags|=0x20
        if a.volume is not None: flags|=0x40
        if a.effects: flags|=0x80
        out=bytearray(((a.ch&31)|flags,))
        if a.note_kind is not None:
            kinds={'normal':0,'delay_normal':0x40,'porta':0x80,'delay_porta':0x81,'porta_swap':0x82,'sample_swap':0x83,'cut':0xFC,'fade':0xFD,'off':0xFE,'delay_off':0xFF}
            d=kinds[a.note_kind]
            if a.note_kind in ('normal','delay_normal'):
                # Stream v4: bit 1 marks an XM note without a literal instrument
                # column. FT2 retriggers envelopes but preserves sample panning.
                if not a.xm_instrument_present: d |= 0x02
                out += bytes((d,a.tone & 0x7F))
                out += struct.pack('<HBB',a.period_q,a.pitch_lo,a.pitch_hi)
                if a.note_kind=='delay_normal': out += bytes((a.delayed_volume&0xFF,a.delay_tick&0x0F))
            elif a.note_kind in ('porta','delay_porta'):
                out.append(d); out += struct.pack('<H',a.period_q)
                if a.note_kind=='delay_porta': out += bytes((a.delayed_volume&0xFF,a.delay_tick&0x0F))
            elif a.note_kind=='porta_swap':
                out += bytes((d,a.tone&0xFF))
                out += struct.pack('<H',a.period_q)
            elif a.note_kind=='sample_swap':
                out += bytes((d,a.tone&0xFF))
            else:
                out.append(d)
                if a.note_kind=='delay_off': out += bytes((a.delayed_volume&0xFF,a.delay_tick&0x0F))
        if a.volume is not None: out.append(max(0,min(64,a.volume)))
        if a.effects:
            for i,(cmd,param,extra) in enumerate(a.effects):
                c=cmd | (0x80 if i < len(a.effects)-1 else 0)
                out += bytes((c&0xFF,param&0xFF))
                if cmd==CMD_J or cmd in (CMD_IT_LINEAR_E,CMD_IT_LINEAR_F,CMD_IT_LINEAR_G):
                    p1,p2=extra or (0,0); out += struct.pack('<HH',p1,p2)
                elif cmd==CMD_ST3_FINETUNE:
                    pq=(extra or (0,0))[0]; out += struct.pack('<H',pq)
        return bytes(out)

    def compile(self):
        rows_encoded=[]
        max_events=0; total_events=0
        # Tracker duration is conventionally one intro plus one complete loop.
        # Stop when playback reaches an already processed order/row with the
        # same global timing state; this matches libopenmpt's reported duration
        # for looping S3M/XM/MOD songs without expanding the loop to max-seconds.
        visited_positions=set()
        while self.order < self.stop_order and self.seconds < self.max_seconds:
            if self.order>=len(self.m.orders): self.ended_reason='end of order list'; break
            pos_key=(self.order,self.row,self.speed,self.tempo,tuple((ch,self.states[ch].loop_start_row,self.states[ch].loop_count) for ch in sorted(self.states)))
            if pos_key in visited_positions:
                self.ended_reason='sequence loop detected'; break
            visited_positions.add(pos_key)
            patidx=self.m.orders[self.order]
            if patidx==254: self.order+=1; self.row=0; continue
            if patidx==255: self.ended_reason='order 255'; break
            if patidx>=len(self.m.patterns): self.ended_reason='invalid pattern'; break
            pat=self.m.patterns[patidx]
            if self.row>=len(pat): self.order+=1; self.row=0; continue
            evs=pat[self.row]
            # later channel wins for B/C, matching the backend's channel-order walk.
            pending_jump=None; pending_break=None; pending_loop_row=None; pending_stop=False; xm_row_delay=0
            actions=[]
            if self.fmt=='IT' and not self.it_initial_global_emitted:
                # IT header global volume is 0..128. V is parser-immediate and
                # does not consume either realtime effect slot.
                actions.append(Action(0,effects=[(CMD_V,max(0,min(128,self.it_global_volume)),None)]))
                self.it_initial_global_emitted=True
            row_events=sorted((e for e in evs if e.ch in self.states),key=lambda x:x.ch)
            # ProTracker quirk: EDx with x>=speed can trigger at the beginning of
            # the following row, but only if that row has no new note on the channel.
            if self.fmt=='MOD' and bool(getattr(self.m,'mod_out_of_range_delay',False)) and self.mod_pending_oor_delay:
                has_note={e.ch for e in row_events if e.note is not None}
                injected=[]
                for ch,pe in sorted(self.mod_pending_oor_delay.items()):
                    if ch not in has_note:
                        injected.append(core.Event(ch=ch,note=pe.note,ins=pe.ins,vol=pe.vol))
                self.mod_pending_oor_delay.clear()
                row_events=sorted(injected+row_events,key=lambda x:x.ch)
            for e in row_events:
                # Resolve B/C parameters directly (no memory in supported profiles).
                if e.cmd==CMD_B:
                    pending_jump=e.param or 0
                    if self.fmt=='XM': self.xm_next_pat_start_row=0
                elif e.cmd==CMD_C:
                    if self.fmt=='XM': self.xm_next_pat_start_row=0
                    raw_break=e.param or 0
                    # Genuine ST3 stores Cxx as packed decimal. IT-authored
                    # S3M writes/interprets the parameter as a raw row number.
                    pending_break=((raw_break>>4)*10+(raw_break&15)) if self.fmt=='S3M' else raw_break
                elif self.fmt=='XM' and e.cmd==CMD_XM_STOP:
                    pending_stop=True
                if self.fmt=='XM' and e.cmd==CMD_XM_PATDELAY:
                    xm_row_delay=(e.param or 0)&15  # last channel wins in FT2/XM
                event_for_action=e
                if (self.fmt=='MOD' and bool(getattr(self.m,'mod_out_of_range_delay',False))
                        and e.cmd==CMD_S and ((e.param or 0)&0xF0)==0xD0
                        and ((e.param or 0)&15)>=self.speed and e.note is not None):
                    self.mod_pending_oor_delay[e.ch]=core.Event(ch=e.ch,note=e.note,ins=e.ins,vol=e.vol)
                    event_for_action=core.Event(ch=e.ch,cmd=e.cmd,param=e.param)
                state=self.states[e.ch]
                it_had_foreground=(self.fmt=='IT' and e.ch in self.it_voice_map)
                phys=self._it_target_voice(e.ch) if self.fmt=='IT' else e.ch
                synth=[]
                if (self.fmt=='IT' and bool(getattr(self.m,'it_instrument_mode',False))
                        and e.note is not None and e.note<254 and e.cmd not in (CMD_G,CMD_L)):
                    # SDx note delay + NNA would need runtime voice allocation at
                    # the delayed tick. Keep that rare combination explicit.
                    if e.cmd==CMD_S and (((e.param or 0)>>4)&15)==0xD and ((e.param or 0)&15)>0:
                        inum,_,_,prof=self._it_note_identity(e,state)
                        if prof and (int(prof.get('nna',0)) or int(prof.get('dct',0))):
                            raise ValueError(f'IT delayed note with NNA/DCT at order {self.order} row {self.row} channel {e.ch+1} is not representable by the current runtime allocator')
                    phys,synth,_,_=self._it_allocate_note_voice(e,state)
                a=self._event_action(event_for_action,state)
                if self.fmt=='IT':
                    for sa in synth: actions.append(sa)
                    if (a and bool(getattr(self.m,'it_instrument_mode',False)) and not it_had_foreground
                            and not (e.note is not None and e.note<254)
                            and e.cmd not in (CMD_A,CMD_T,CMD_V,CMD_W)
                            and not (e.cmd==CMD_S and (((int(getattr(e,'resolved_param',e.param or 0))>>4)&15) in (0x6,0xE)))):
                        # IT effect memory is already resolved on the logical
                        # channel by the host. Do not accidentally mutate an
                        # unrelated NNA background voice at the same physical index.
                        a=None
                    if a:
                        a.ch=phys
                        # A newly allocated NNA-capable physical voice must inherit
                        # the logical IT channel's current base pan and channel volume.
                        if e.note is not None and e.note<254 and e.cmd not in (CMD_G,CMD_L):
                            a.effects.insert(0,(CMD_M,max(0,min(64,state.it_channel_volume)),None))
                            a.effects.insert(0,(CMD_X,max(0,min(255,state.it_pan_tracker)),None))
                        actions.append(a)
                    sp=getattr(e,'it_note_special',None)
                    if sp in ('cut','off','fade'):
                        pv=self.it_voice_map.get(e.ch)
                        if pv is not None:
                            if sp=='cut': self._it_apply_voice_end(pv,'cut')
                            elif self.it_voices[pv] is not None: self.it_voices[pv]['release']=sp
                elif a:
                    actions.append(a)
                # SBx pattern loop is flattened at conversion time. ST3 uses
                # channel 0's loop memory globally; IT/modern S3M keep per-channel state.
                if e.cmd==CMD_S and (((getattr(e,'resolved_param',0)>>4)&15)==0xB):
                    lp=getattr(e,'resolved_param',0)&15
                    lst=self.states[min(self.states)] if self.fmt=='S3M' else self.states[e.ch]
                    if lp==0:
                        lst.loop_start_row=self.row
                    elif lst.loop_count:
                        lst.loop_count-=1
                        if lst.loop_count:
                            pending_loop_row=lst.loop_start_row
                        elif self.fmt=='S3M':
                            lst.loop_start_row=self.row+1
                    else:
                        lst.loop_count=lp
                        pending_loop_row=lst.loop_start_row
                # FT2 E6x is a per-channel pattern loop. Flatten it so the Z80
                # stream needs no pattern/order state at runtime.
                if self.fmt=='XM' and e.cmd==CMD_XM_PATLOOP:
                    lp=(e.param or 0)&15; lst=self.states[e.ch]
                    if lp==0:
                        lst.loop_start_row=self.row
                    elif lst.loop_count:
                        lst.loop_count-=1
                        if lst.loop_count:
                            pending_loop_row=lst.loop_start_row
                            if self.xm_ft2_e60_restart: self.xm_next_pat_start_row=lst.loop_start_row
                    else:
                        lst.loop_count=lp
                        pending_loop_row=lst.loop_start_row
                        if self.xm_ft2_e60_restart: self.xm_next_pat_start_row=lst.loop_start_row
                if self.fmt=='MOD' and e.cmd==CMD_MOD_PATLOOP:
                    lp=(e.param or 0)&15; lst=self.states[e.ch]
                    if lp==0:
                        lst.loop_start_row=self.row
                    elif lst.loop_count:
                        lst.loop_count-=1
                        if lst.loop_count:
                            pending_loop_row=lst.loop_start_row
                    else:
                        lst.loop_count=lp
                        pending_loop_row=lst.loop_start_row

                # Global tempo/speed commands are effective on this row.
                if e.cmd==CMD_A and (e.param or 0): self.speed=max(1,e.param or 0)
                if e.cmd==CMD_T:
                    tp=int(getattr(e,'resolved_param',e.param or 0))
                    if tp>=32: self.tempo=max(32,min(255,tp))
                if self.fmt=='IT' and e.cmd==CMD_V and 0 <= int(e.param or 0) <= 128:
                    self.it_global_volume=int(e.param or 0)
            if len(actions)>255: raise ValueError('too many compact row actions')
            rb=bytearray((len(actions),))
            for a in actions: rb+=self._encode_action(a)
            rows_encoded.append(bytes(rb)); max_events=max(max_events,len(actions)); total_events+=len(actions)
            self.rows+=1
            mod_row_delay=max(((e.param or 0)&15 for e in row_events if self.fmt=='MOD' and e.cmd==CMD_MOD_PATDELAY),default=0)
            if self.fmt=='IT':
                # Simulate global IT tempo slides and logical channel M/N/P/W
                # state across every tracker tick. Pattern delay repeats the
                # already-parsed row, so tick-0 fine slides re-apply but M/V/T>=20h
                # parser-immediate commands do not.
                it_pat_delay=0; it_tick_delay=0
                for e in row_events:
                    rp=int(getattr(e,'resolved_param',e.param or 0))
                    if e.cmd==CMD_S and ((rp>>4)&15)==0xE: it_pat_delay=rp&15
                    if e.cmd==CMD_S and ((rp>>4)&15)==0x6: it_tick_delay=rp&15
                ticks=max(1,self.speed+it_tick_delay)
                repeats=1+it_pat_delay
                tfx=[int(getattr(e,'resolved_param',e.param or 0)) for e in row_events if e.cmd==CMD_T and int(getattr(e,'resolved_param',e.param or 0))<32]
                nfx=[(e.ch,int(getattr(e,'resolved_param',e.param or 0))) for e in row_events if e.cmd==CMD_N]
                pfx=[(e.ch,int(getattr(e,'resolved_param',e.param or 0))) for e in row_events if e.cmd==CMD_P]
                wfx=[int(getattr(e,'resolved_param',e.param or 0)) for e in row_events if e.cmd==CMD_W]
                for rep in range(repeats):
                    for tick in range(ticks):
                        # Fine N/P/W forms run on tick 0, including delayed repeats.
                        for ch,np in nfx:
                            st=self.states[ch]; hi=(np>>4)&15; lo=np&15
                            delta=0
                            if tick==0:
                                if lo==15 and hi: delta=hi
                                elif hi==15 and lo: delta=-lo
                            elif lo==0 and hi: delta=hi
                            elif hi==0 and lo: delta=-lo
                            st.it_channel_volume=max(0,min(64,st.it_channel_volume+delta))
                        for ch,pp in pfx:
                            st=self.states[ch]; hi=(pp>>4)&15; lo=pp&15
                            delta=0
                            if tick==0:
                                if lo==15 and hi: delta=-(hi*4)
                                elif hi==15 and lo: delta=lo*4
                            elif lo==0 and hi: delta=-(hi*4)
                            elif hi==0 and lo: delta=lo*4
                            st.it_pan_tracker=max(0,min(255,st.it_pan_tracker+delta))
                        for wp in wfx:
                            hi=(wp>>4)&15; lo=wp&15; delta=0
                            if tick==0:
                                if lo==15 and hi: delta=hi
                                elif hi==15 and lo: delta=-lo
                            elif lo==0 and hi: delta=hi
                            elif hi==0 and lo: delta=-lo
                            self.it_global_volume=max(0,min(128,self.it_global_volume+delta))
                        if tick>0:
                            for tp in tfx:
                                lo=tp&15
                                if (tp&0xF0)==0x10: self.tempo=min(255,self.tempo+lo)
                                else: self.tempo=max(32,self.tempo-lo)
                        self.seconds += 2.5/max(32,self.tempo)
            else:
                self.seconds += self.speed*(1+xm_row_delay+mod_row_delay)*2.5/self.tempo
            if pending_stop:
                self.ended_reason='FT2 F00 stop'; break
            # advance flattened playback order
            if pending_loop_row is not None:
                self.row=pending_loop_row
            elif pending_jump is not None:
                if pending_jump<self.start_order or pending_jump>=self.stop_order:
                    self.ended_reason=f'position jump leaves subsong (B{pending_jump:02X})'; break
                self.order=pending_jump; self.row=pending_break or 0
            elif pending_break is not None:
                self.order+=1; self.row=pending_break
            else:
                self.row+=1
                if self.row>=len(pat):
                    self.order+=1
                    if self.fmt=='XM' and self.xm_ft2_e60_restart:
                        self.row=self.xm_next_pat_start_row
                        self.xm_next_pat_start_row=0
                    else:
                        self.row=0
            while self.order<self.stop_order and self.order<len(self.m.orders) and self.m.orders[self.order]==254:
                self.order+=1
            if self.fmt=='XM' and self.order>=self.stop_order and self.stop_order==len(self.m.orders):
                restart=int(getattr(self.m,'xm_restart',0))
                if self.start_order<=restart<self.stop_order:
                    self.order=restart; self.row=0
                    continue
            if self.fmt=='MOD' and self.order>=self.stop_order and self.stop_order==len(self.m.orders) and bool(getattr(self.m,'mod_restart_valid',False)):
                restart=int(getattr(self.m,'mod_restart',0))
                if self.start_order<=restart<self.stop_order:
                    self.order=restart; self.row=0
                    continue
            if self.order>=self.stop_order or self.order>=len(self.m.orders) or self.m.orders[self.order]==255:
                self.ended_reason='end of subsong/order list'; break
        if not self.ended_reason:
            self.ended_reason='max-seconds reached' if self.seconds>=self.max_seconds else 'ended'
        pans=bytes(self._pan_nibble(ch) if ch in self.states else 0 for ch in range(24))
        header=bytearray(STREAM_MAGIC)
        # ST3.00 and older always use fast volume slides, even when the
        # header flag is absent. Later S3M/IT profiles use the explicit flag.
        # S3M header flags: bit 6 (0x40) is the ST3.00 fast-volume-slide flag.
        # Bit 3 (0x08) is *zero-volume optimisation* and must not alter slide timing.
        # ST3.00 (cwtv 0x1300) implicitly uses fast volume slides.
        st3_fast = (self.fmt=='S3M' and int(getattr(self.m,'s3m_cwtv',0))==0x1300)
        stream_flags = 1 if (self.fmt in ('S3M','IT-S3M','MODERN-S3M') and (bool(self.m.flags & 0x40) or st3_fast)) else 0
        if self.fmt in ('S3M','IT-S3M','MODERN-S3M') and bool(getattr(self.m,'s3m_old_vibrato',False)): stream_flags |= 0x04
        if self.fmt=='MOD' and bool(getattr(self.m,'mod_pt_mode',False)): stream_flags |= 0x01
        if self.fmt=='MOD' and bool(getattr(self.m,'mod_ft2_tremolo_ramp',False)): stream_flags |= 0x02
        if self.xm_linear: stream_flags |= 0x02
        if self.fmt=='XM':
            if self.xm_ft2_arpeggio: stream_flags |= 0x04
            if self.xm_ft2_envelope_escape: stream_flags |= 0x08
            if self.xm_ft2_pan_sustain_release: stream_flags |= 0x10
            if self.xm_ft2_auto_vib_abort_sweep: stream_flags |= 0x20
            if self.xm_ft2_porta_reset_direction: stream_flags |= 0x40
            if self.xm_ft2_porta_target_no_reset: stream_flags |= 0x80
        header += bytes((STREAM_VERSION,min(24,len(self.m.active_channels)),(self.m.speed or (6 if self.fmt=='XM' else 1)),stream_flags))
        header += struct.pack('<H',(self.m.tempo or (125 if self.fmt=='XM' else 32)))
        header += struct.pack('<I',self.rows)
        header += pans
        header.append(0)          # alias-patch count; tracker2ksp fills this after MWK layout
        assert len(header)==HEADER_SIZE
        stream=bytes(header)+b''.join(rows_encoded)+b'\xff'
        return stream, rows_encoded, {
            'semantic_rows':self.rows,'semantic_events':total_events,'max_events_per_row':max_events,
            'semantic_stream_bytes':len(stream),'duration_seconds':self.seconds,'end_reason':self.ended_reason,
            'xm_linear_periods':self.xm_linear,'xm_tracker_profile':getattr(self.m,'xm_profile',None),
            'xm_oxm':bool(getattr(self.m,'xm_oxm',False)),
            'mod_profile':getattr(self.m,'mod_profile',None),'mod_signature':getattr(self.m,'mod_signature',None),
            'xm_ft2_arpeggio':self.xm_ft2_arpeggio if self.fmt=='XM' else None,
            'xm_ft2_offset_oor':self.xm_ft2_offset_oor if self.fmt=='XM' else None,
            'xm_ft2_envelope_escape':self.xm_ft2_envelope_escape if self.fmt=='XM' else None,
            'xm_ft2_pan_sustain_release':self.xm_ft2_pan_sustain_release if self.fmt=='XM' else None,
            'xm_ft2_e60_restart':self.xm_ft2_e60_restart if self.fmt=='XM' else None,
            'xm_ft2_auto_vib_abort_sweep':self.xm_ft2_auto_vib_abort_sweep if self.fmt=='XM' else None,
            'xm_ft2_porta_reset_direction':self.xm_ft2_porta_reset_direction if self.fmt=='XM' else None,
            'xm_ft2_porta_target_no_reset':self.xm_ft2_porta_target_no_reset if self.fmt=='XM' else None,
            'warnings':self.warnings,
        }


def attach_alias_patches(stream:bytes, rows:list[bytes], patches:list[bytes])->bytes:
    if len(patches)>64: raise ValueError('more than 64 OPL4 header alias patches')
    if len(stream)<HEADER_SIZE: raise ValueError('compact stream header truncated')
    header=bytearray(stream[:HEADER_SIZE]); header[38]=len(patches)
    for rec in patches:
        if len(rec)!=8: raise ValueError('alias patch records must be tone+7 header bytes')
        header += rec
    return bytes(header)+b''.join(rows)+b'\xff'
