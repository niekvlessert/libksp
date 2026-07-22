#!/usr/bin/env python3
from pathlib import Path

src = (Path(__file__).resolve().parents[1] / "src" / "KSP1PLAY.asm").read_text()
block = src.split("ui_text_copy_done:",1)[1].split("ui_text_scan_loop:",1)[0]
assert "ld a,' '" in block, "text terminator cell must remain a space"
assert "xor a\n    ld (de),a" not in block, "NUL must not be stored into fixed-width render row"
print("NUL padding UI model test: PASS")
