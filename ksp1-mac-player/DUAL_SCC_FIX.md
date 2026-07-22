# Dual-SCC player fix

Version 1.0.2 adds the ESCHATOS page-gateway compatibility fix on top of the desktop dual-SCC runtime.

## Native KSP1 packs

For engines marked with `KSP1_HW_DUAL_SCC`, the player installs and handles:

- `D900`: select SCC A
- `D904`: select SCC B
- `D908`: deselect the SCC register window
- the engine-declared dynamic page gateway, normally `D8A0`

libkss's SCC is used as cartridge A. A second emu2212 SCC is used as cartridge
B. Register writes are routed to only the selected SCC, while both oscillators
continue running and are mixed into the SDL output.

## Early compatibility packs

Early dual-SCC conversions that omitted the dual-SCC hardware flag are detected
from their callback ABI:

- `D900`: submit an 8-bit local page number
- `D903`: select SCC A/B using register A

The temporary KSCC image receives compatibility stubs before INIT is executed.
The package itself is not rewritten.

## Regression fixtures

- `ESCHATOS_N163_Dual_SCC_KSP1_1.0.ksp`: native ABI
- `Megami_Tensei_II_Dual_SCC_KSP1_1.0.ksp`: early compatibility ABI

Every track in both fixtures is tested for ABI detection and exact callback
injection.

## ESCHATOS page gateway correction

The ESCHATOS converter requests local pages in register `A` but leaves `HL` as
a working pointer. Version 1.0.1 used the generic `HL` mailbox and therefore
interpreted `HL=$67CD` as page 26573. Version 1.0.2 uses the ABI-required `A`
low-byte mirror for engines with at most 256 pages and writes a zero high byte.
For engines with more than 256 pages, the full 16-bit `HL` gateway remains in
use. This removes the invalid request and installs ESCHATOS page 1 correctly.
