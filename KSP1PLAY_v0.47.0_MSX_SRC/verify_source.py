#!/usr/bin/env python3
"""Build, refresh generated guidance and audit KSP1PLAY v0.47.0."""
from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parent
for rel,args in [
    ('build.py',['--no-disk']),
    ('tools/generate_docs.py',[]),
    ('tools/make_ai_context.py',[]),
    ('tools/source_audit.py',[]),
]:
    subprocess.run([sys.executable,str(ROOT/rel),*args],cwd=ROOT,check=True)
print('KSP1PLAY v0.47.0 source verification: PASS')
