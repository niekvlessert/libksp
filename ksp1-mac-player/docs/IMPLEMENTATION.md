# Implementation architecture

## Clean separation

`ksp1_runtime` owns all container concerns:

1. reads the complete KSP file into bounded host memory;
2. validates the header, table dimensions, file ranges and CRCs;
3. parses engines, pages, tracks, resources and UTF-8 strings;
4. decodes ZX0 and block containers;
5. reconstructs exactly one requested runtime page;
6. checks the final page CRC;
7. creates a temporary KSCC image for libkss.

`ksp1player` owns only desktop playback:

1. selects a public 16-bit track;
2. asks `ksp1_runtime` for its reconstructed KSCC image;
3. converts that image through `KSS_bin2kss`;
4. runs it through `KSSPLAY`;
5. sends signed 16-bit PCM to SDL2;
6. handles public next/previous navigation;
7. handles ABI-1 dynamic page requests.

No game name, filename, legacy KCP variant or private pack identifier appears in the playback decisions.

## Page encodings

### Sparse overlay

The engine template is decoded once and copied. Ordered sparse records replace byte ranges.

### Complete page

The page payload directly decodes to the complete engine page.

### Shared block map

A `PBM1` map references fixed-size logical blocks from a `PBK1` resource. Slabs are independently decoded and the requested block slice is copied into the page.

### Resource map

An `RMP1` map copies arbitrary ranges from decoded package resources and supports inline literals and fills.

### Hybrid pool

`HPL1` is decoded into a unified desktop block pool. The RAM/VRAM/cold tier declarations remain available for the future MSX implementation but do not constrain host memory placement. A page row maps every destination position to one pooled block.

## Dynamic page switching

For engines carrying `KSP_ENGINE_DYNAMIC_PAGES`, the player installs the ABI-1 gateway:

```text
LD (0xD89E),HL
RET
```

The libkss memory-write hook collects the 16-bit engine-local page index, materializes the corresponding global page, and replaces only `replace_start..page_end`.

The current implementation performs materialization synchronously in that callback. It is functionally correct for testing. A production low-latency revision should enqueue the page number and perform allocation/decompression at a safe audio boundary.

## KSCC bridge

libkss consumes KSS/KSCC rather than KSP directly. The bridge uses the selected page as one KSCC load image and copies the engine's load, INIT and PLAY addresses. PSG/SCC use the normal MSX baseline; YM2413 and Y8950 are represented by their KSCC device flags.

This bridge is regenerated when changing public tracks, allowing tracks to select another engine or page without extending libkss's file parser.

## Deliberate future work

The KSP parser already exposes all resources, but these playback integrations remain separate work:

- MWK upload and MoonSound backend creation;
- mapper callbacks for live BNK8/BN16 engines;
- SCREEN 5 images and UTF-8/Japanese UI rendering;
- asynchronous dynamic-page request queue;
- a native macOS graphical front end.
