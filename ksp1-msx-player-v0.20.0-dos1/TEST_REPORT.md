# KSP1PLAY v0.20.0 test report

## Build

- COM size: 16,121 bytes
- SHA-256: `d99bb7ec2ad5a3aea70453d049f68e67980cc697fd934ed58d3b009eb3ac93c0`

## Memory boundaries

```text
resident core end       1BFAh
DOS1 FCB overlay end    21F3h
graphical UI end        34FDh
MoonSound module end    3FF9h
```

All remain below their fixed boundaries.

## Passed tests

- KSP sparse and HPOL profile validation
- KSP 1.01 PAGE2_RUNTIME/PAGE3_WORKRAM model
- ZX0 chunked-stream model
- dual-SCC gateway/relocation model
- MoonSound/MWK model checks
- FMPAC disk-I/O mute model
- package menu and track selector model
- compact-font and incremental-repaint models
- playback track-window model
- package lifecycle, keyboard drain and Screen 0 exit model
- DOS1 FCB/direct-mapper backend model
- deterministic sparse, hybrid, PAGE3 and menu disk generation

## DOS1 backend checks

- No EXTBIO mapper API dependency.
- No DOS2 file-handle OPEN/READ/SEEK/CLOSE dependency.
- Uses FCB functions 0Fh, 10h, 11h, 12h, 1Ah and 27h.
- Uses FCB record size 1 for byte-offset random reads.
- Converts command-line and directory names to DOS 8.3 FCB format.
- Detects 4-256 mapper segments without writing candidate segments.
- Excludes the startup page-0, page-1, page-2 and page-3 segments from its pool.

## Not performed

No openMSX executable or physical MSX was available. Runtime validation on an
MSX-DOS1 system remains required, especially repeated package switching and
mapper compatibility with the selected DOS1 environment.
