#!/usr/bin/env python3
"""Build the clean KSP1PLAY v0.47.0 KSPOS source tree.

Default outputs deliberately contain no KSP1PLAY.COM.  KSPOS loads KSPBOOT.BIN
at boot; the historical COM byte stream is assembled as KSPPLAYER.BIN and is
embedded in KSPBOOT.BIN at CPU address 0100h.
"""
from __future__ import annotations
import argparse, hashlib, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'src'; BOOT_SRC=SRC/'boot'; TOOLS=ROOT/'tools'; BUILD=ROOT/'build'
ASM=TOOLS/'z80asm.py'
sys.path.insert(0,str(TOOLS))
from fat12 import build as build_fat12

EXPECTED={
 'KSPPLAYER.BIN':(30464,'1f86b9a461de240a8e9665a7d8a3a48eda257e00856876af717887fbd654c0f8'),
 'KSPMENU.BIN':(2048,'afaa2f8501830ee24b9b078647c6a9e7c976ef993886b39beb7ff665605e4304'),
 'KSPBOOT.BIN':(31043,'8b75436e579957a6dc8812b8eea4ff7ca9f3ffb72524d730774bcf1fb156ca3c'),
}

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def assemble(src:Path,out:Path)->bytes:
    sym=out.with_suffix('.sym'); lst=out.with_suffix('.lst')
    subprocess.run([sys.executable,str(ASM),str(src),str(out),str(sym),str(lst)],check=True)
    return out.read_bytes()
def assemble_text(text:str,stem:str)->bytes:
    p=BUILD/f'{stem}.generated.asm'; p.write_text(text,encoding='utf-8')
    return assemble(p,BUILD/f'{stem}.BIN')
def assert_canonical(name:str,data:bytes)->None:
    size,digest=EXPECTED[name]
    got=sha(data)
    if len(data)!=size or got!=digest:
        raise SystemExit(f'{name}: canonical mismatch: size {len(data)}/{size}, sha {got}/{digest}')
    print(f'{name}: EXACT canonical v0.47.0 ({len(data)} bytes, {got})')

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--reference-dsk',type=Path,help='optional original v0.47.1 base DSK; verifies boot-sector code too')
    ap.add_argument('--no-disk',action='store_true')
    args=ap.parse_args()
    BUILD.mkdir(exist_ok=True)

    player=assemble(SRC/'KSPPLAYER.asm',BUILD/'KSPPLAYER.BIN'); assert_canonical('KSPPLAYER.BIN',player)
    menu=assemble(SRC/'KSPMENU.asm',BUILD/'KSPMENU.BIN'); assert_canonical('KSPMENU.BIN',menu)

    gateway=assemble(BOOT_SRC/'KSPOS_GATEWAY.asm',BUILD/'KSPOS_GATEWAY.BIN')
    if len(gateway)>0xA0: raise SystemExit('KSPOS gateway exceeds 160-byte reservation')
    prefix=gateway+bytes(0xA0-len(gateway))
    resident=assemble(BOOT_SRC/'KSPOS_RESIDENT.asm',BUILD/'KSPOS_RESIDENT.BIN')
    resident_source=0x0060+len(prefix)+len(player)   # 7800h
    finalizer_source=resident_source+len(resident)  # 7971h
    finalizer=assemble_text(
        f'FINALIZER_SOURCE equ 0x{finalizer_source:X}\nRESIDENT_SOURCE equ 0x{resident_source:X}\nRESIDENT_SIZE equ 0x{len(resident):X}\n'+
        (BOOT_SRC/'KSPOS_FINALIZER.asm').read_text(encoding='utf-8'),'KSPOS_FINALIZER')
    kspboot=prefix+player+resident+finalizer
    (BUILD/'KSPBOOT.BIN').write_bytes(kspboot); assert_canonical('KSPBOOT.BIN',kspboot)

    boot_code=assemble_text(
        f'KSPBOOT_SIZE equ 0x{len(kspboot):X}\nFINALIZER_SOURCE equ 0x{finalizer_source:X}\n'+
        (BOOT_SRC/'KSPOS_BOOT.asm').read_text(encoding='utf-8'),'KSPOS_BOOT')
    if len(boot_code)>0xE2: raise SystemExit('boot-sector loader exceeds reserved area')

    if args.reference_dsk:
        ref=args.reference_dsk.read_bytes()
        expected=ref[0x1E:0x1E+len(boot_code)]
        if boot_code!=expected: raise SystemExit('boot-sector loader differs from supplied reference DSK')
        print(f'boot-sector loader: EXACT supplied DSK ({len(boot_code)} bytes)')

    if not args.no_disk:
        readme=(
            'KSP1PLAY v0.47.0 CLEAN SOURCE BASE\r\n'
            'Bootable KSPOS disk. No MSX-DOS and no KSP1PLAY.COM required.\r\n'
            'KSPBOOT.BIN contains the player; KSPMENU.BIN is loaded at runtime.\r\n'
            'Add KSP files and fixed 80-byte INDEX.TXT records with the normal disk builder.\r\n'
        ).encode('ascii')
        image=bytearray(build_fat12([
            ('KSPBOOT.BIN',kspboot),('KSPMENU.BIN',menu),('INDEX.TXT',b''),('README.TXT',readme)
        ]))
        # Preserve the FAT12 BPB, replace the executable boot-sector region.
        image[0:3]=b'\xEB\xFE\x90'; image[3:11]=b'KSPOS047'
        image[0x1E:0x1E+len(boot_code)]=boot_code; image[510:512]=b'\x55\xAA'
        dsk=BUILD/'KSP1PLAY_v0.47.0_SOURCE_BASE_NO_COM.DSK'; dsk.write_bytes(image)
        print(f'{dsk.name}: {len(image)} bytes (KSPBOOT + KSPMENU, no COM)')

    sums=[]
    for p in sorted(BUILD.glob('*.BIN'))+sorted(BUILD.glob('*.DSK')):
        sums.append(f'{sha(p.read_bytes())}  {p.name}')
    (BUILD/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='ascii')
    print(f'layout: player 0100h..77FFh; resident {resident_source:04X}h..{finalizer_source-1:04X}h; finalizer {finalizer_source:04X}h')
    return 0
if __name__=='__main__': raise SystemExit(main())
