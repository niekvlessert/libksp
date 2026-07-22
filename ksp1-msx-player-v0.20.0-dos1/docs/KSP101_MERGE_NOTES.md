# KSP 1.01 merge notes for v0.18.1

The uploaded local player was based on the older v0.12/v0.13 code line. Its
portable changes were merged into v0.18 rather than replacing the newer
Screen 5, dual-SCC, MoonSound, HPOL and disk-loading implementation.

## Merged directly

- KSP minor versions 0 and 1.
- `KSP_ENGINE_PAGE2_RUNTIME`.
- `KSP_ENGINE_PAGE3_WORKRAM`.
- Rejection of new memory flags in minor version 0.
- PAGE2_RUNTIME conflict with SCC page-2 hardware.
- HPOL 256-byte block handling and strict cache bounds (already present in v0.18).
- Updated Python validators.

## Adapted to v0.18

The old source reused its Fray split-page segment for PAGE3_WORKRAM. v0.18 has
no game-specific profiles, so the merged implementation allocates a clean,
optional page-3 mapper segment solely from the declarative engine flag.

The uploaded specification describes a possible page-3-resident player with a
fixed gateway at D8A0h. v0.18 remains page-0 resident so DOS-backed loading and
the graphical shell are preserved. It relocates ABI gateway CALL operands from
the immutable engine prefix to its resident page-0 callback. The specification
now explicitly permits this native relocation and retains the dual-SCC token ABI.

## Not claimed

This merge does not implement every aspirational item in sections 11 and 12 of
the complete format/programmer specification, such as multiple engines, PBLK,
RMP1 or a wholesale split into KSPDOS2/KSPPLAYER modules.
