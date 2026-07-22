#!/usr/bin/env python3
import sys,re,struct,json,hashlib
from pathlib import Path
sys.path[:0]=['/mnt/data/.pydeps','/mnt/data']
from z80 import Z80Machine
from build_sng_pro_ksp1 import parse_kss,zx0_decode
SRC=Path('/mnt/data/protracker-all-repacked.kss')
OLD=0xca00; SIZE=0x1000; NEW=0x4000; DELTA=NEW-OLD; SONG=0x5000
src=parse_kss(SRC)

def discover():
 lo,hi=OLD,OLD+SIZE;q=[0xca00,0xca0d,0xca66,0xcad7];seen=set();inst=[]
 while q:
  a=q.pop()
  while lo<=a<hi and a not in seen:
   seen.add(a);raw0=src.memslice(a,min(8,hi-a));s,n=Z80Machine._disasm(raw0);raw=raw0[:n];inst.append((a,raw,s));sl=s.lower();nxt=a+n
   refs=[int(x,16) for x in re.findall(r'w0x([0-9a-f]+)',sl)]
   m=re.search(r'd\$\s*([+-])\s*(\d+)',sl);rel=a+((1 if m and m.group(1)=='+' else -1)*int(m.group(2)) if m else 0) if m else None
   if sl.startswith('call') or ' call ' in sl:
    for v in refs:
     if lo<=v<hi:q.append(v)
    a=nxt;continue
   if sl.startswith('jp'):
    for v in refs:
     if lo<=v<hi:q.append(v)
    if ',' in sl:a=nxt;continue
    break
   if sl.startswith('jr') or sl.startswith('djnz'):
    if rel is not None and lo<=rel<hi:q.append(rel)
    # unconditional form exactly jr D$...
    if sl.startswith('jr d$'):break
    a=nxt;continue
   if sl.startswith('ret'):
    # Conditional RET (ret z/nz/c/nc/...) has a fall-through path.
    if sl == 'ret' or sl.startswith('reti') or sl.startswith('retn'):
     break
    a=nxt;continue
   if sl.startswith('reti') or sl.startswith('retn') or sl.startswith('halt'):
    break
   a=nxt
 return sorted(inst)
INST=discover()
SONG_REF_SITES={0xCA10,0xCA13,0xCA1D,0xCA36,0xCD65,0xCD87,0xCFA6,0xCFBE,0xCFD0,0xD0D0,0xD0E2}

def patch_operand(blob,old_addr,raw,target,newtarget):
 le=bytes([target&255,target>>8]);positions=[i for i in range(len(raw)-1) if raw[i:i+2]==le]
 if len(positions)!=1:
  raise ValueError(f'operand ambiguity {old_addr:04x} {raw.hex()} target {target:04x} positions {positions}')
 pos=old_addr-OLD+positions[0];blob[pos]=newtarget&255;blob[pos+1]=newtarget>>8

def relocate():
 b=bytearray(src.memslice(OLD,SIZE));patches=[]
 for a,raw,s in INST:
  sl=s.lower()
  refs=[int(x,16) for x in re.findall(r'w0x([0-9a-f]+)',sl)]
  for v in refs:
   nv=None;kind=None
   if OLD<=v<OLD+SIZE:nv=v+DELTA;kind='engine'
   elif a in SONG_REF_SITES:
    nv=v+SONG;kind='song'
   if nv is not None:
    patch_operand(b,a,raw,v,nv);patches.append((a,v,nv,kind,s))
 # init returns after engine initialization instead of installing H.TIMI
 b[0xca4d-OLD]=0xc9
 # Direct KSP PLAY terminates here instead of chaining the previous H.TIMI hook.
 b[0xcb2f-OLD:0xcb34-OLD]=b'\xc9'*5
 # stop: silence/reset routine then return, no H.TIMI restore
 stop=bytes([0xcd,(0xd055+DELTA)&255,(0xd055+DELTA)>>8,0xc9])
 b[0xca66-OLD:0xca66-OLD+len(stop)]=stop
 # The original page-3 engine temporarily remapped page 1 around FM access.
 # A relocated page-1 engine must never unmap itself; direct I/O needs no slot helper.
 b[0xd151-OLD]=0xc9
 b[0xd186-OLD]=0xc9
 return bytes(b),patches
ENGINE,PATCHES=relocate()

class ProMachine:
 def __init__(self,original,track=0,song=None):
  self.m=Z80Machine();self.m.memory[:]=b'\0'*65536;self.m.memory[0xfd9f:0xfda4]=b'\xc9'*5;self.logs=[];self.tick=0;self.sel=1;self.original=original;self.preloaded_song=(song is not None)
  if original:
   self.m.memory[src.load:src.load+src.load_size]=src.memory
   if song is not None:self.m.memory[0:len(song)]=song
  else:
   self.m.memory[NEW:NEW+SIZE]=ENGINE
   self.m.memory[SONG+0x0200:SONG+0x3000]=src.memslice(0x0200,0x2e00)
   self.m.memory[SONG:SONG+len(song)]=song
   if track==152:
    # Track 152 uses bytes beyond its song as data. Keep an unmodified mirror
    # of the old CA00-D9FF image so relocated executable operands do not leak
    # into that data stream.
    self.m.memory[0x6000:0x7000]=src.memslice(OLD,SIZE)
    # Redirect the mirror's final C9/C9 relative word into a local C9 filler.
    self.m.memory[0x6c4a:0x6c4c]=bytes([0xb2,0x03])
    self.m.memory[0x7000:0x7400]=b'\xc9'*0x400
  def rd(a):
   if self.original and 0x8000<=a<0xa000:
    # In libkss BANK_8K mode, writing 9000h selects only page 4
    # (8000h-9FFFh). A000h-BFFFh remains the main-memory page unless
    # the engine explicitly writes B000h, which this Pro driver does not.
    return src.banks.get(self.sel,b'\0'*8192)[a-0x8000]
   return self.m.memory[a]
  def wr(a,v):
   if self.original and a==0x9000:self.sel=v;return
   self.m.memory[a]=v
  def out(p,v):
   lo=p&255
   if lo in (0x7c,0x7d,0xc0,0xc1,0xa0,0xa1,0xa2):self.logs.append((self.tick,lo,v,self.m.pc,self.m.sp,self.m.memory[self.m.sp]|(self.m.memory[(self.m.sp+1)&0xffff]<<8),self.m.a,self.m.bc,self.m.de,self.m.hl,self.m.ix,self.m.iy))
  self.m.set_read_callback(rd);self.m.set_write_callback(wr);self.m.set_output_callback(out);self.m.set_input_callback(lambda p:0xff)
  self.m.set_breakpoint(0xF103)
 def call(self,addr,a=0,hl=0):
  self.m.memory[0xF100:0xF104]=bytes([0xcd,addr&255,addr>>8,0]);self.m.pc=0xF100;self.m.sp=0xEF00;self.m.a=a;self.m.hl=hl
  for _ in range(2000):
   self.m.ticks_to_stop=20000000;ev=self.m.run()
   if self.m.pc==0xF103:return
  raise RuntimeError(f'call fail {addr:04x} pc {self.m.pc:04x}')
 def init(self,track=0):self.call(OLD if self.original and self.preloaded_song else (0x3000 if self.original else NEW),track,track)
 def play(self):self.tick+=1;self.call(0x307d if self.original else NEW+(0xcad7-OLD))

def get_song(track):
 d=src.memslice(0xe000+track*4,4);desc=struct.unpack_from('<H',d,2)[0];x=src.memslice(desc,3);ref=(x[0],struct.unpack_from('<H',x,1)[0]);return zx0_decode(src.packed_tail(*ref),expected=None,max_output=0x3000)[0]

def transform_song(track, raw):
 out=bytearray(raw)
 if track==152:
  need=0x457
  if len(out)<need:
   for a in range(len(out),need):
    out.append(src.memslice(a,1)[0] if a>=src.load else 0)
  # 5457h + 0FC9h = 6420h, the unmodified CE20h mirror.
  out[0x455:0x457]=bytes([0xC9,0x0F])
 return bytes(out)

def test(track=0,ticks=120):
 song=get_song(track);a=ProMachine(True,track=track,song=song);b=ProMachine(False,track=track,song=transform_song(track,song))
 a.init(track);b.init(track)
 init=(a.logs==b.logs,len(a.logs),len(b.logs))
 for _ in range(ticks):a.play();b.play()
 aa=a.logs;bb=b.logs;av=[x[:3] for x in aa];bv=[x[:3] for x in bb];n=min(len(av),len(bv));first=next((i for i in range(n) if av[i]!=bv[i]),n)
 initv=([x[:3] for x in aa[:init[1]]]==[x[:3] for x in bb[:init[2]]],init[1],init[2])
 return {'track':track,'song_size':len(song),'init':initv,'equal':av==bv,'first':first,'counts':[len(av),len(bv)],'old':aa[first:first+10],'new':bb[first:first+10],'pcs':[hex(a.m.pc),hex(b.m.pc)]}

if __name__=='__main__':
 print('instructions',len(INST),'patches',len(PATCHES),'engine',len(ENGINE))
 for p in PATCHES:
  if p[3]=='song':print('song patch',p)
 for tr in [0,1,2,10,50,100,157]:
  try:print(json.dumps(test(tr,120),indent=2))
  except Exception as e:print('ERR',tr,e)
