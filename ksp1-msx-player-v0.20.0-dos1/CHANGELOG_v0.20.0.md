# v0.20.0 — standalone MSX-DOS1 backend

- Removed all MSX-DOS2 handle calls and the DOS2 EXTBIO mapper allocator.
- Added MSX-DOS1 FCB open, close, directory search and random block reads.
- Uses one-byte FCB records, preserving byte-addressed 24-bit random KSP access.
- Added DOS1 `*.KSP` directory scanning and 8.3 filename conversion.
- Added direct primary-memory-mapper size detection through ports FC-FF.
- Added a private high-segment pool that excludes the four process segments.
- Retained disk-backed streams, sparse VRAM cache and HPOL cold-slab loading.
- Retained the graphical UI, clean package lifecycle and 80-column Screen 0 exit.
- Retained KSP 1.01, dual SCC, FMPAC disk mute and MoonSound/MWK support.
- Added a DOS1 backend regression/model test.

Compatibility notes:

- Requires MSX-DOS1, MSX2 and a 128 KiB or larger memory mapper.
- Current-directory 8.3 files only; no subdirectories.
- Do not combine this direct-mapper build with a DOS1 RAM disk or TSR that owns
  hidden mapper segments.
