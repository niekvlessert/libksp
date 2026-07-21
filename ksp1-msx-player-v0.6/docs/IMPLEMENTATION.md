# KSP1PLAY MSX implementation

## DOS2-safe address space

The COM and permanent buffers stay in page 0. Page 3 remains owned by MSX-DOS2.

```text
0100h–14FEh   resident code, variables and messages
14FFh–17DFh   growth space
17E0h–17FFh   reserved dynamic-page gateway
1800h–36FFh   fixed parser, I/O and HPOL buffers
3700h–3FEFh   stack
4000h–7FFFh   active engine page
8000h–BFFFh   mapper scratch/history while stopped, SCC while playing
C000h–FFFFh   DOS2 page 3
```

## Page dispatch

### Encoding 0: sparse overlay

1. Restore original mapper RAM in pages 1 and 2.
2. Decode/read the 16 KiB engine template into page 1.
3. Decode/read the page payload into page 2.
4. Validate and apply `[offset:u16, size:u16, bytes...]` records.
5. Expose the configured SCC slot in page 2.
6. Call INIT and start PLAY.

The decoded sparse payload must be at most 16 KiB. Records must be nonzero, ordered, non-overlapping and within the runtime page.

### Encoding 1: complete page

The raw or ZX0 payload must reconstruct to exactly 16 KiB and is installed directly in page 1.

### Encoding 4: hybrid pool

The existing `HPOL/HPL1` path preloads hot blocks into mapper segments and warm blocks into VRAM, then applies the selected map row to the template. Cold slabs use page-2 scratch on demand while stopped.

## SCC/scratch exclusion

Page 2 is RAM only during materialization. Before INIT, PLAY or interrupts, the player maps the selected SCC cartridge back into page 2. No DOS call or decode occurs while the SCC mapping is assumed to be RAM.

## Current profile gates

- one engine;
- ABI version 1;
- no dynamic/banked/MWK-required engine flags;
- PSG/SCC hardware flags only;
- 50 or 60 Hz PLAY rate;
- load address and size `4000h/4000h`;
- raw or ZX0 template;
- page encodings 0, 1 or 4.
