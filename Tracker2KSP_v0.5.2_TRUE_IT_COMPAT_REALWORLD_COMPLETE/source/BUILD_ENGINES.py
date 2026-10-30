#!/usr/bin/env python3
from pathlib import Path
import shutil, subprocess, sys
here=Path(__file__).resolve().parent
root=here.parent
asm=here/'tools'/'z80asm.py'
for stem in ('compact_engine_s3m','compact_engine_it_s3m','compact_engine_it','compact_engine_mod','compact_engine_xm'):
    src=here/f'{stem}.asm'; out=here/f'{stem}.bin'; mp=here/f'{stem}.map'; lst=here/f'{stem}.lst'
    subprocess.check_call([sys.executable,str(asm),str(src),str(out),str(mp),str(lst)])
    # The release intentionally carries root + source copies because the root
    # wrappers import their local generated engine/map files. Keep generated
    # artifacts synchronized so a source patch + rebuild cannot leave a stale
    # root engine behind.
    for generated in (out,mp,lst):
        shutil.copy2(generated,root/generated.name)
    print(f'{stem}: {out.stat().st_size} bytes')
