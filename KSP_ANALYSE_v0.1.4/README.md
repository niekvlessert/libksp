# ksp_analyse v0.1.4

Forensic analyser for KSP files intended for **KSP1PLAY on MSX**.

Requires Python 3.10 or newer.

The tool is not a converter and does not merely dump KSP headers. It reconstructs
KSP engine/track pages, disassembles the materialized Z80 image with **z80dasm
1.1.6**, performs recursive INIT/PLAY control-flow analysis and explains why a
KSP is likely safe, suspicious, high-risk or structurally incompatible with the
native MSX player.

## What it checks

- KSP1 header/tables, file size, header/index CRC, template/page CRC.
- Engine geometry: load address, image size, INIT/PLAY, tick rate and ABI flags.
- Declared P0/P1/P2/P3 use, including `PAGE2_RUNTIME`, `PAGE3_WORKRAM` and
  `DYNAMIC_PAGES`.
- Materialization of sparse, complete, PBM1/PBLK, RMP1 and HPOL pages.
- Reachable Z80 instructions from INIT and PLAY rather than blind byte scans.
- Direct control flow outside the resident engine, low-memory dependencies and
  unresolved `JP (HL/IX/IY)` paths.
- Reachable memory-mapper I/O (`$FC-$FF`), slot register `$A8`, PPI `$AA/$AB`,
  VDP `$98/$99`, interrupt-vector writes and scheduler-style EI epilogues.
- Declared versus statically proven PSG, SCC/SCC+, FM-PAC/YM2413,
  MSX-AUDIO/Y8950 and MoonSound/OPL4 usage.
- KSP SCC ABI tokens `$D900/$D904/$D908` are recognized as player ABI calls,
  not mistaken for missing page-3 code.
- `$9000/$9800` writes in a `PAGE2_RUNTIME` engine are treated as RAM unless
  the runtime mapping actually proves an SCC window. This avoids the old SCC
  false-positive class.
- Direct writes into reachable executable bytes (self-modifying code).

## Native-MSX policy used by default

The current strict diagnostic target is the KSP1PLAY native engine contract:

    engine load: $4000
    engine size: $4000 (16 KiB)

Additional state must be expressed through the KSP runtime mechanisms, rather
than by installing a hosted 48/64 KiB KSS-like address-space image.

Therefore an old KSP such as `$0000/$C000 + PAGE2_RUNTIME` is immediately a
`BLOCKER`; its PAGE2 mirror starting at `$8000` would run beyond `$FFFF`.

Use `--relaxed` only when investigating a non-standard/hosted runtime on
purpose. It should not be used to certify a KSP for KSP1PLAY/MSX.

## Basic use

Analyse one KSP. By default one representative track per physical page/engine
is examined:

```sh
./ksp_analyse game.ksp
```

Analyse a specific logical track:

```sh
./ksp_analyse game.ksp --track 3
```

Analyse every track:

```sh
./ksp_analyse game.ksp --all-tracks
```

Write the reconstructed binary, full z80dasm assembly, text report and JSON:

```sh
./ksp_analyse game.ksp --track 3 --report-dir reports
```

The report directory will contain files similar to:

```text
reports/game/
  engine00_track003.bin
  engine00_track003.asm
  report.txt
  report.json
```

If a conclusive structural blocker is already found, the tool stops before a
large disassembly. To investigate it anyway:

```sh
./ksp_analyse old_hosted.ksp --track 1 --deep-blockers --report-dir reports
```

## Corpus scan

For a directory, `--fast` deliberately performs the structural gate only. This
is useful for quickly separating native 16 KiB candidates from hosted/oversized
outputs:

```sh
./ksp_analyse ./ksps --fast --csv summary.csv
```

Recursive:

```sh
./ksp_analyse ./ksps --recursive --fast --csv summary.csv
```

Then run the interesting `LIKELY SAFE`/remaining candidates individually
without `--fast` for full Z80/chip analysis.

## Verdicts

- `LIKELY SAFE` — no static blocker found. This is **not** a runtime guarantee.
- `SUSPICIOUS` — incomplete indirect flow or an unusual construct needs review.
- `HIGH RISK` — a likely KSP1PLAY conflict or declaration/runtime mismatch.
- `BLOCKER` — violates the strict native MSX memory/runtime contract.

Every non-trivial verdict includes reason codes and evidence addresses, for
example:

```text
[BLOCKER] PAGE2_RUNTIME_COPY_OVERFLOW
[HIGH] IRQ_VECTOR_WRITE
[HIGH] SCC_PAGE2_RAM_AMBIGUITY
[SUSPICIOUS] INDIRECT_PLAY_FLOW
```

## z80dasm

A Linux x86-64 `z80dasm 1.1.6` binary is included and selected automatically.
The original GPLv2 source archive is included under `third_party/`.

On macOS/Linux where the bundled binary does not match the host, either install
`z80dasm` in `PATH` or build the included source:

```sh
./build_z80dasm.sh
```

The resulting `./z80dasm` is automatically detected. You can also select one:

```sh
./ksp_analyse game.ksp --z80dasm /path/to/z80dasm
```

## Recommended diagnostic workflow

1. Run `ksp_analyse file.ksp --track N --report-dir report`.
2. Read `Verdict` and the first `BLOCKER/HIGH` reasons.
3. Check the P0-P3 table and declared versus detected chip I/O.
4. Open the generated `.asm` at the evidence addresses.
5. If the only remaining issue is indirect flow, reproduce the failing track in
   KSP1PLAY/openMSX and trace that exact path rather than guessing from all bytes.

This tool makes a *static compatibility assessment*. Final proof remains actual
KSP1PLAY v0.47.x playback on MSX/openMSX: INIT must return, PLAY must continue at
its intended cadence, and real chip writes/music progression must continue.

## v0.1.1: KSP1PLAY interrupt-return analysis

Deep analysis now follows CALL/RET context from INIT and PLAY while tracking the abstract Z80 interrupt-enable state. This catches a class that plain disassembly misses: an engine callback that returns to KSP1PLAY with IFF1 enabled.

KSP1PLAY enters track installation with interrupts disabled and its gateway restores player mappings/stack only after the engine's outer RET. An `EI` that survives to that outer return therefore creates an interrupt window before the gateway can execute its first `DI`. The analyser reports:

- `INIT_RETURNS_INTERRUPTS_ENABLED` — `BLOCKER` when every statically resolved outer INIT return is enabled, otherwise `HIGH`;
- `PLAY_RETURNS_INTERRUPTS_ENABLED` — same rule for PLAY.

The context-sensitive walk distinguishes this from an `EI; RET` in an internal helper when the outer callback later executes `DI` before returning.


## v0.1.2: `--try-fix` in-memory repair and re-analysis

`--try-fix` adds an experimental repair phase after the normal deep analysis:

```sh
./ksp_analyse game.ksp --track 1 --try-fix
```

The input KSP is **never modified**. The analyser:

1. performs the normal forensic analysis;
2. collects repair candidates that have explicit control-flow evidence;
3. patches the affected materialized KSP page in memory;
4. rebuilds an in-memory candidate KSP, using uncompressed COMPLETE payloads for
   modified pages so the repair is deterministic;
5. updates page CRC plus KSP index/header CRCs;
6. reparses the candidate as a KSP from scratch;
7. runs the full analyser again and compares the before/after verdicts.

The first supported repair family is `irq_return_ei_to_di`. For
`INIT_RETURNS_INTERRUPTS_ENABLED` / `PLAY_RETURNS_INTERRUPTS_ENABLED`, the
callback walker tracks which specific reachable `EI` last enabled IFF1 on the
path to the *outer* callback return. Only those causal bytes are candidates.
The size-preserving patch is:

```text
$FB  EI  ->  $F3  DI
```

This deliberately does **not** blind-patch every `EI` in the engine. If the
analyser cannot prove the enabling source or cannot map it back to the selected
physical page, the candidate is skipped.

Example output:

```text
TRY-FIX (experimental; original file is unchanged):
  Status: IMPROVED | BLOCKER -> LIKELY SAFE | patches=1
  [PATCH] track 1 page 0 INIT: $4C58 $FB EI -> $F3 DI
  Cleared HIGH/BLOCKER codes: INIT_RETURNS_INTERRUPTS_ENABLED, PLAY_RETURNS_INTERRUPTS_ENABLED
```

`--try-fix` cannot be combined with `--fast`, because repair decisions require
the deep control-flow pass. A successful static repair still does not prove
correct sound or real-MSX runtime behaviour; it means that the specific detected
incompatibility disappeared and no equal/worse static regression was introduced.



## v0.1.4: profile-preserving `--try-fix`

v0.1.4 fixes a repair-writer bug found with **Yie Ar Kung-Fu (enhanced SCC)**.
Earlier versions materialised every patched page as a 16 KiB `PAGE_COMPLETE` page.
Although the reconstructed Z80 bytes were correct, changing `PAGE_SPARSE` into
`PAGE_COMPLETE` could change KSP1PLAY's structural/profile routing and produce
`UNSUPPORTED PROFILE` on the MSX player.

Repair now follows a strict profile-preservation rule:

- `PAGE_SPARSE` stays sparse. A byte inherited from the engine template is repaired
  by adding a minimal sparse overlay record.
- `PAGE_COMPLETE` stays complete.
- page compression (`NONE` or `ZX0`), page flags and engine association are preserved.
- PBM1/RMP1/HPOL pages are currently **not** flattened for an automatic code fix;
  the repair is refused until a representation-preserving writer exists.
- after rebuilding, the package is reparsed and the repaired physical page must
  reconstruct byte-for-byte to the requested image.
- `--try-fix` reports a `[PROFILE]` line showing that the runtime page profile was preserved.

This is intentionally stricter than merely producing a structurally valid KSP. A
repair that changes KSP1PLAY backend/profile semantics is not accepted as a fix.

## v0.1.3: `--build-disk`, emitted KSP and conservative hardware repair

`--build-disk` turns the analyser into a short analyse/repair/test-artifact
pipeline:

```sh
./ksp_analyse game.ksp --track 1 --build-disk
```

It implies `--try-fix` and performs these steps in order:

1. deep-analyse the original KSP;
2. apply only evidence-backed in-memory repairs and reanalyse them;
3. perform a second package-wide hardware audit over every referenced physical
   engine/page;
4. conservatively repair the emitted engine hardware mask when the static proof
   is strong enough;
5. update `target_hardware` in META when a hardware correction was made while
   preserving `source_hardware` as source provenance;
6. refresh KSP file size, descriptor data and header/index CRCs;
7. write the emitted KSP to `ksp/` next to the analyser;
8. re-open and reanalyse that on-disk KSP;
9. build a one-KSP 720 KiB test disk in `dsk/` using the canonical latest
   KSP1PLAY test template.

The input KSP is never overwritten.

### Latest-player requirement

The canonical MSX target for this release is:

```text
KSP1PLAY player core:       v0.47.0
DSK builder/package base:   v0.47.1
required template:          KSP1PLAY_v0.47.1_BASE.DSK
```

Place the template here:

```text
KSP_ANALYSE_v0.1.3/player/KSP1PLAY_v0.47.1_BASE.DSK
```

or supply either the template DSK or the complete v0.47.1 DSK-builder ZIP:

```sh
./ksp_analyse game.ksp --build-disk --player-template /path/to/KSP_DSK_BUILDER_v0.47.1_COMPLETE.zip
```

The tool checks that the template contains `KSPBOOT.BIN`, `KSP1PLAY.COM` and
`KSPMENU.BIN`, and refuses an older/unknown player. It deliberately does not
fall back to the old v0.22.x disks.

If the latest template is unavailable, `--build-disk` still writes and validates
the repaired KSP in `ksp/`, reports `DSK NOT BUILT`, and returns a failure status
for the requested disk step.

### Hardware correction policy

Hardware reporting and hardware *removal* use different confidence thresholds.
Reachable direct chip I/O can add a missing hardware bit. Removal is much more
conservative. In v0.1.3 the only automatically removable family is a false SCC
family declaration.

An SCC/SCC+/Dual-SCC declaration is removed only when all referenced physical
pages for the engine satisfy all of the following:

- deep CFG analysis completed;
- z80dasm evidence completed successfully;
- INIT and PLAY have no unresolved indirect jumps;
- no control-flow/dynamic-code finding can hide another hardware path;
- no SCC/SCC+ register window is proven;
- no `$D900/$D904` SCC slot ABI path is reachable.

If any of those conditions is missing, the SCC declaration is left intact.
The analyser never guesses SCC versus SCC+ versus Dual-SCC when SCC activity is
actually present.

Q-Bert is the regression case for this rule: the source metadata says
`SCC + PSG`, but the complete reachable engine proves PSG I/O only. Its emitted
KSP is therefore normalized to engine hardware `PSG` and
`target_hardware=PSG`, while `source_hardware=SCC + PSG` is retained as
provenance.
