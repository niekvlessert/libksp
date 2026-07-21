# KSP1PLAY.COM for MSX-DOS2

Fresh MSX-DOS2 player for the standalone KSP 1.0 format.

Version 0.6 fixes two independent Z80 register-corruption errors found by the physical MSX test. Version 0.5 fixed register loss across DOS input refills; version 0.4 fixed uppercase quoted character literals in the bundled assembler.

## Version 0.6 decoder and console fixes

Two additional bugs remained after the refill fix:

1. `zx_read_bit` used register `B` as a temporary mask. `BC` is the active ZX0 Elias-gamma value or copy length, so every bit read could corrupt the decoder even when no input refill occurred.
2. `print_u16` kept its destination pointer in `DE`, but its division routine also used `DE`. It therefore wrote the track number near address `0009h` and asked DOS to print thousands of bytes from low memory, producing the screen garbage and potentially corrupting system state.

Version 0.6 preserves both register sets. The build also runs a chunked 512-byte ZX0 model against the exact Nemesis 3 template and all 24 compressed overlays (79 refills total), plus source-level regression checks for both bugs.

## Build

```bash
python3 build.py
```

No external assembler is required. The bundled Python assembler generates:

```text
build/KSP1PLAY.COM
build/KSP1SPRS.DSK
build/KSP1HYBR.DSK
build/KSP1NEM3.DSK
build/KSP_PROFILE_REPORT.json
build/SPARSE_PROFILE_REPORT.json
```

`GENERATE_KSP1PLAY.py` and `BUILD.command` run the same build.

## Run

```text
KSP1PLAY NEMESIS3.KSP 0 2
```

Arguments:

```text
KSP1PLAY file.ksp [public-track] [SCC-primary-slot]
```

Controls:

```text
SPACE   next track
ESC     stop and return to DOS2
```

The input must be a **standalone KSP 1.0 file beginning with `KSP1`**. Old KSSX/KCPZ files beginning with `KSSX` remain unsupported.

## Supported page encodings

- `0` — `KSP_PAGE_SPARSE_OVERLAY`
- `1` — `KSP_PAGE_COMPLETE`
- `4` — `KSP_PAGE_HYBRID_POOL` using `HPOL/HPL1`

Sparse and complete payloads may use `NONE` or forward `ZX0` compression. Independently decoded payloads must fit within 16 KiB.

Nemesis 3 uses 24 sparse-overlay pages, a ZX0 template, PSG+SCC hardware, and a `4000h–7FFFh` engine page, so it matches this profile.

## Memory model

```text
0100h–1628h   resident COM code and variables
17E0h–17FFh   reserved future page-0 gateway
1800h–36FFh   descriptors, title/I/O buffers and HPOL maps
3700h–3FEFh   stack
4000h–7FFFh   active engine page
8000h–BFFFh   scratch while stopped, SCC while playing
C000h–FFFFh   MSX-DOS2 page 3; untouched
```

For sparse pages, the player:

1. stops playback and restores mapper RAM in page 2;
2. decodes the common template into page 1;
3. decodes the sparse payload into page-2 scratch;
4. applies its ordered records to page 1;
5. restores the SCC cartridge in page 2;
6. calls INIT and resumes PLAY.

Page 2 is therefore never scratch and SCC simultaneously.

## Test disks

- `KSP1SPRS.DSK`: sparse-overlay Solid Snake regression package
- `KSP1HYBR.DSK`: HPOL hybrid Solid Snake regression package
- `KSP1NEM3.DSK`: the exact uploaded Nemesis 3 KSP renamed to `NEMESIS3.KSP`

Both are FAT12 data disks, not boot disks. Mount one beside an MSX-DOS2 system disk or DOS2 cartridge.

## Current limitations

- one engine per package;
- PSG and normal SCC only;
- SCC must be in a non-expanded primary slot;
- engine page must be exactly `4000h–7FFFh`;
- no dynamic mid-song page requests yet;
- page encodings 2 (`PBLK`) and 3 (`RESOURCE_MAP`) are not yet implemented in the COM;
- no runtime CRC calculation on Z80;
- no SCREEN 5 or Japanese bitmap-font UI yet.

Actual audible execution still requires testing in openMSX or on physical MSX hardware.
