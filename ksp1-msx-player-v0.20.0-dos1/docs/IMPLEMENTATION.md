# KSP1PLAY 0.18.1 MSX implementation

## Design rule

The player has no game-specific or title-specific branches. Runtime decisions
come from KSP engine flags, hardware flags, addresses, page entries and resource
descriptors.

## DOS2-safe address space

```text
0100h-1B31h   resident code, variables and messages
1C00h-1FFFh   fixed KSP descriptors and I/O buffers
2000h-2142h   generic dynamic-page and dual-SCC callbacks
2200h-3254h   Screen 5 UI code/data
3500h-36FFh   HPOL position cache
3700h-38FFh   active HPOL map-row cache
3900h-39EFh   stack
3A00h-3FA0h   MoonSound/MWK module
4000h-7FFFh   active engine page
8000h-BFFFh   mapper scratch/runtime alias or audio cartridge
C000h-FFFFh   DOS2 page 3, except during declared PAGE3_WORKRAM calls
```

## KSP 1.01 memory profiles

### PAGE2_RUNTIME

For an engine with flag bit 3, the active page-1 mapper segment is selected in
page 2 before INIT and PLAY. This provides an initially identical writable
`8000h-BFFFh` image without an additional segment. The validator rejects this
flag with SCC, SCC+ or dual-SCC hardware.

### PAGE3_WORKRAM

For flag bit 4, the player allocates one additional user mapper segment and
clears `C000h-FFFEh` once when the package opens. The segment remains allocated
for the package lifetime. INIT, PLAY and STOP temporarily select it through
mapper port `FFh`; the original process page is restored immediately after the
call and by every general process-page restoration path.

A dynamic gateway records the caller's current page-3 segment before doing disk
or reconstruction work and reinstalls it before returning to the engine.

## Page materialization

Sparse, complete and HPOL/hybrid page paths are unchanged from v0.18. Large
packages remain open and use absolute DOS2 reads or the upper-VRAM file cache.
The complete HPOL map lives in a dedicated mapper segment; only one position
list and one page row remain in page 0.

## Generic dynamic and dual-SCC gateways

The player scans the immutable engine prefix and rewrites declared gateway CALL
operands into resident page-0 handlers. Dynamic page requests preserve normal
registers, interrupt state and now the caller's page-3 mapper segment. Dual SCC
continues to use the generic D900h/D904h/D908h relocation tokens implemented by
v0.17/v0.18.

## Supported profile gates

- exactly one engine;
- ABI version 1;
- KSP minor version 0 or 1;
- engine flags: dynamic pages, MWK-required, PAGE2_RUNTIME and PAGE3_WORKRAM;
- banked-data runtime remains unsupported;
- hardware: PSG, SCC, SCC+, dual normal SCC, YM2413 and OPL4;
- no dual-SCC plus SCC+ combination;
- no PAGE2_RUNTIME plus SCC/SCC+/dual-SCC combination;
- 50 or 60 Hz PLAY rate;
- load address and size `4000h/4000h`;
- raw or ZX0 template expanding to 16 KiB;
- initial page encodings 0, 1 or 4;
- dynamic page encoding 0 with a bounded sparse payload.
