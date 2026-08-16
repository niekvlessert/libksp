#!/usr/bin/env python3
"""Minimal deterministic 720 KiB FAT12 image builder used by KSPOS."""
from __future__ import annotations
import struct

SECTOR=512
TOTAL_SECTORS=1440
SECTORS_PER_CLUSTER=2
RESERVED=1
FATS=2
SECTORS_PER_FAT=3
ROOT_ENTRIES=112
ROOT_SECTORS=(ROOT_ENTRIES*32+SECTOR-1)//SECTOR
DATA_START=RESERVED+FATS*SECTORS_PER_FAT+ROOT_SECTORS
CLUSTER_BYTES=SECTOR*SECTORS_PER_CLUSTER


def short_name(name:str)->bytes:
    stem,dot,ext=name.upper().partition('.')
    allowed="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$~!#%&-{}()@'`"
    if not stem or len(stem)>8 or len(ext)>3 or any(c not in allowed for c in stem+ext):
        raise ValueError(f'not a valid deterministic 8.3 name: {name}')
    return stem.ljust(8).encode('ascii')+ext.ljust(3).encode('ascii')


def set_fat12(fat:bytearray, cluster:int, value:int)->None:
    off=cluster+cluster//2
    if cluster&1:
        fat[off]=(fat[off]&0x0F)|((value<<4)&0xF0)
        fat[off+1]=(value>>4)&0xFF
    else:
        fat[off]=value&0xFF
        fat[off+1]=(fat[off+1]&0xF0)|((value>>8)&0x0F)


def build(files:list[tuple[str,bytes]])->bytes:
    image=bytearray(TOTAL_SECTORS*SECTOR)
    boot=memoryview(image)[:SECTOR]
    boot[0:3]=b'\xEB\x3C\x90'
    boot[3:11]=b'KSP1PLAY'
    struct.pack_into('<H',boot,11,SECTOR)
    boot[13]=SECTORS_PER_CLUSTER
    struct.pack_into('<H',boot,14,RESERVED)
    boot[16]=FATS
    struct.pack_into('<H',boot,17,ROOT_ENTRIES)
    struct.pack_into('<H',boot,19,TOTAL_SECTORS)
    boot[21]=0xF9
    struct.pack_into('<H',boot,22,SECTORS_PER_FAT)
    struct.pack_into('<H',boot,24,9)
    struct.pack_into('<H',boot,26,2)
    boot[38]=0x29
    struct.pack_into('<I',boot,39,0x4B535031)
    boot[43:54]=b'KSP1 SOURCE'
    boot[54:62]=b'FAT12   '
    boot[510:512]=b'\x55\xAA'
    fat=bytearray(SECTORS_PER_FAT*SECTOR); fat[0:3]=b'\xF9\xFF\xFF'
    root=bytearray(ROOT_SECTORS*SECTOR); next_cluster=2
    dos_date=((2026-1980)<<9)|(8<<5)|16; dos_time=(22<<11)
    for index,(name,content) in enumerate(files):
        if index>=ROOT_ENTRIES: raise ValueError('too many root entries')
        clusters=max(1,(len(content)+CLUSTER_BYTES-1)//CLUSTER_BYTES)
        first=next_cluster
        for i in range(clusters):
            cluster=next_cluster+i
            set_fat12(fat,cluster,0xFFF if i==clusters-1 else cluster+1)
            off=DATA_START*SECTOR+(cluster-2)*CLUSTER_BYTES
            chunk=content[i*CLUSTER_BYTES:(i+1)*CLUSTER_BYTES]
            image[off:off+len(chunk)]=chunk
        next_cluster+=clusters
        ent=index*32
        root[ent:ent+11]=short_name(name); root[ent+11]=0x20
        struct.pack_into('<H',root,ent+22,dos_time); struct.pack_into('<H',root,ent+24,dos_date)
        struct.pack_into('<H',root,ent+26,first); struct.pack_into('<I',root,ent+28,len(content))
    if next_cluster>=0xFF0: raise ValueError('disk content does not fit')
    fat1=RESERVED*SECTOR; fat2=fat1+SECTORS_PER_FAT*SECTOR; root_off=fat2+SECTORS_PER_FAT*SECTOR
    image[fat1:fat1+len(fat)]=fat; image[fat2:fat2+len(fat)]=fat; image[root_off:root_off+len(root)]=root
    return bytes(image)
