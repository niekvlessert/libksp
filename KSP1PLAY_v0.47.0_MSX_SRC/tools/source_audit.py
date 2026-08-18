#!/usr/bin/env python3
"""Structural/readability audit for the active KSP1PLAY source tree."""
from __future__ import annotations
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'src'
failed=False

def fail(msg:str):
    global failed
    print('FAIL:',msg); failed=True

manifest=SRC/'KSPPLAYER.asm'
mt=manifest.read_text()
active=[]
for inc in re.findall(r'include\s+"([^"]+\.asm)"',mt,re.I):
    p=SRC/inc
    if p.exists() and p not in active: active.append(p)
active += [SRC/'ui/KSPMENU.asm', SRC/'runtime/RECON_RUNTIME.asm']
active += sorted((SRC/'boot').glob('*.asm'))
active=list(dict.fromkeys(active))
text='\n'.join(p.read_text(errors='ignore') for p in active)

# No address-derived placeholder labels.
generic=re.findall(r'^(?:sub_[0-9A-Fa-f]{4}h|l[0-9A-Fa-f]{4}h):',text,re.M)
if generic: fail(f'{len(generic)} generic address labels remain')

# No unexplained numeric control-flow destinations.
raw_cf=[]
pat=re.compile(r'^\s*(?:call|jp|jr)\s+(?:[A-Za-z]+\s*,\s*)?(?:0x[0-9A-Fa-f]+|0[0-9A-Fa-f]+h)\b',re.I)
for p in active:
    for n,line in enumerate(p.read_text(errors='ignore').splitlines(),1):
        if pat.search(line): raw_cf.append(f'{p.relative_to(ROOT)}:{n}: {line.strip()}')
if raw_cf: fail('numeric CALL/JP/JR targets remain:\n  '+'\n  '.join(raw_cf[:20]))

# Listing addresses do not belong on ordinary instruction lines.
listing=[]
pat_addr=re.compile(r';\s*[0-9A-Fa-f]{4}\s*$')
for p in active:
    for n,line in enumerate(p.read_text(errors='ignore').splitlines(),1):
        if pat_addr.search(line): listing.append(f'{p.relative_to(ROOT)}:{n}')
if listing: fail(f'{len(listing)} per-instruction listing-address comments remain')

# Literal NOPs are allowed only as short, deliberate instruction sequences.
nops=0; maxrun=0; maxwhere=''
for p in active:
    run=0; start=0
    for n,line in enumerate(p.read_text(errors='ignore').splitlines(),1):
        if line.strip().lower()=='nop':
            nops+=1
            if run==0:start=n
            run+=1
            if run>maxrun: maxrun=run; maxwhere=f'{p.relative_to(ROOT)}:{start}'
        else: run=0
if nops>20: fail(f'literal NOP count {nops} exceeds 20')
if maxrun>5: fail(f'longest literal NOP run {maxrun} at {maxwhere} exceeds 5')

required=['README.md','START_HERE.md','docs/ARCHITECTURE.md','docs/MEMORY_MAP.md',
          'docs/OVERLAY_ABI.md','docs/RUNTIME_FLOWS.md','docs/KSP_STRUCTURES.md',
          'docs/CHANGE_GUIDE.md','docs/ROUTINE_CONTRACTS.md','docs/TESTING.md',
          'docs/CALL_GRAPH.md','docs/SYMBOL_INDEX.md','docs/NOP_POLICY.md','docs/PROJECT_STATUS.md']
for rel in required:
    if not (ROOT/rel).exists(): fail(f'missing {rel}')
if (ROOT/'docs/history').exists(): fail('docs/history should not exist in the active project')
if len(mt.splitlines())>80: fail('KSPPLAYER.asm manifest is too large')

print(f'active ASM files: {len(active)}')
print(f'generic labels: {len(generic)}')
print(f'numeric CALL/JP/JR targets: {len(raw_cf)}')
print(f'literal NOPs: {nops}; longest run: {maxrun}')
if failed: raise SystemExit('source audit FAILED')
print('source audit: PASS')
