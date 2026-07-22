# KSP 1.x storage optimizer

`ksp_optimize.py` reads a standalone `KSP1` package, reconstructs every runtime
page, tests alternative storage strategies, rebuilds the smallest tested valid
package, and reparses it to verify every page byte-for-byte.

## Supported input page encodings

- `0` sparse overlay
- `1` complete page
- `2` `PBM1` / `PBLK` / `PBK1`
- `3` `RMP1`, including page-source resources using NONE, ZX0 or `KZB1`
- `4` `HPOL` / `HPL1`, including hot, warm and cold tiers

Normal non-page resources are preserved. Obsolete page-storage resources are
removed and resource indices are remapped when a new representation is chosen.

## Basic use

```bash
python3 ksp_optimize.py input.ksp output.ksp
```

A JSON report is written beside the output:

```text
output.ksp.report.json
```

## Better compression

The bundled Python ZX0 codec is dependency-free and deterministic, but
conservative. Supply the reference ZX0 executable for better size comparisons:

```bash
python3 ksp_optimize.py input.ksp output.ksp --zx0 /path/to/zx0
```

For output intended for `KSP1PLAY.COM`, use the MSX profile:

```bash
python3 ksp_optimize.py input.ksp output.ksp --msx-player-profile
```

This limits page encodings and memory use to the current MSX player and uses
the bundled reference `zx0pack` build when available. The command fails instead
of falling back to the Python encoder when no reference encoder can be found;
that fallback is suitable for round-trip tests, but its streams are not used
for native-player releases.

Some imported MSX engines call or jump directly to the BIOS `WRTPSG` entry at
`0093h`. DOS applications cannot assume that BIOS page 0 remains mapped during
playback. Such a package can be migrated to a verified free address in every
runtime page with:

```bash
python3 ksp_optimize.py input.ksp output.ksp \
  --msx-player-profile --relocate-wrtpsg 0x7FE0
```

The destination must be eight bytes of page-local free space. This is a
package migration, not a game-specific player workaround.

The same package-side approach is available for engines that call BIOS
`RDVDP`, or that return from an internal routine with interrupts enabled:

```bash
python3 ksp_optimize.py input.ksp output.ksp --msx-player-profile \
  --relocate-rdvdp 0x7FE8 --patch-ei-to-di 0x42B8
```

Use `migrate_page3_workram_ksp101.py` afterward when the engine expects
persistent private work RAM at `C000h-FFFFh`. This sets the standardized KSP
1.01 `KSP_ENGINE_PAGE3_WORKRAM` flag and updates both package CRCs.

## Search levels

```bash
python3 ksp_optimize.py input.ksp output.ksp --level quick
python3 ksp_optimize.py input.ksp output.ksp --level normal
python3 ksp_optimize.py input.ksp output.ksp --level exhaustive
```

`exhaustive` means a broader deterministic search, not every mathematically
possible packing combination.

## HPOL memory profile

Defaults:

```text
hot mapper-RAM capacity: 48 KiB
warm VRAM capacity:      96 KiB
```

Override them with:

```bash
python3 ksp_optimize.py input.ksp output.ksp \
  --hot-capacity 32KiB --warm-capacity 64KiB
```

Skip HPOL candidates with `--no-hpol`.

## Safety behavior

By default, the original file is copied unchanged when none of the tested
rebuilds is smaller. Use `--force-rebuild` to emit the smallest rebuilt
candidate anyway.

Every emitted rebuild is reparsed and all reconstructed pages are compared
byte-for-byte with the source package. The JSON report contains all tested
candidate sizes and the selected page encodings.

Some older converters emitted sparse records out of address order. Strict
validation rejects those packages by default. To migrate one, use:

```bash
python3 ksp_optimize.py input.ksp output.ksp --repair-legacy-sparse
```

The source is materialized using its existing record order and the output is
always rebuilt with canonical sparse records; the malformed source is never
copied unchanged.

## Scope

This handles standardized standalone KSP 1.00 and 1.01 files beginning with
`KSP1`.
Legacy KSSX/KCPZ wrappers are intentionally outside this optimizer.
