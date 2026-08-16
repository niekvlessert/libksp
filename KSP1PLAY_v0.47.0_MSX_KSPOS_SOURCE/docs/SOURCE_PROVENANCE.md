# Source provenance and confidence

The final v0.47 binary is authoritative. A single untouched original v0.47 assembler tree was not available.

The recovery used three classes of evidence:

1. **Canonical final binaries** — exact `KSPBOOT.BIN`, `KSPMENU.BIN`, player payload and boot-sector loader from the supplied v0.47.1 base disk.
2. **Complete earlier source** — the v0.44 Stage-6 package builds its own binaries byte-for-byte and provides readable sources for the Stage 2/3/4/5 UI lineage plus KSPOS boot/resident code.
3. **Earlier monolithic readable assembler** — used only to restore names where the machine-code region is demonstrably unchanged in the final binary.

## Player-core 

The final 30,464-byte player was decoded to real Z80 instructions. The included assembler was corrected to emit genuine relative `JR` encodings and extended for the small IX/IY subset present in the final image.

The result round-trips exactly:

```text
src/KSPPLAYER.asm
       |
       v
 tools/z80asm.py
       |
       v
KSPPLAYER.BIN == canonical v0.47 player payload
```

Semantic labels from earlier source were accepted only when their address lies in a sufficiently long byte-identical ancestry block. `docs/RECOVERED_SYMBOLS.md` records those mappings. Unknown code is intentionally left under neutral generated labels.

## Menu 

`KSPMENU.BIN` was independently decoded and also round-trips exactly. Its stable jump table and clear browser/VDP/string behavior allowed additional descriptive names and comments to be added without changing bytes.

## Boot/runtime 

The gateway, resident runtime and finalizer generated combination produces canonical `KSPBOOT.BIN` exactly.

The boot-sector loader also reproduces the original 215 executable bytes when `--reference-dsk` is supplied.

## Confidence rule

There are two separate questions:

- **Is this the exact final program?** Yes: the generated binaries are byte-identical.
- **Are all source labels/comments the names used by the original author at v0.47?** No. Where the original final name cannot be proved, the source says so and retains a neutral generated label.

That distinction is deliberate. Binary correctness is proven; source-level semantics are documented at their actual confidence level.
