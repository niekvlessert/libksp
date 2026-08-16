# KSP Format and Player Implementation Specification

**Version:** 1.06  
**Extension:** `.KSP`  
**Byte order:** little-endian  
**Status:** backward-compatible minor revision of KSP 1.05

KSP 1.06 retains every KSP 1.05 container, engine, page, track, resource,
compression, `HVAR`, `HVR1`, `META`, localization, and shared-payload rule unless
this document explicitly changes it.

KSP 1.06 adds a declared **MSX-safe runtime profile**. Its purpose is to let a
packer state that a selected implementation can be installed completely before
`INIT` and can execute normal `PLAY` callbacks without disk access,
decompression, allocation, or unbounded full-page restoration.

This revision does not replace ordinary KSP engines. The selected engine remains
part of the package. A pack is not made MSX-safe merely by changing the header
minor version.

This document is normative for the differences introduced by KSP 1.06. Every
KSP 1.05 rule not explicitly changed here remains mandatory.

## 1. Revision summary

```text
KSP 1.00  generic page reconstruction and shared-storage resources
KSP 1.01  declarative PAGE2_RUNTIME and PAGE3_WORKRAM engine profiles
KSP 1.02  HVAR/HVR1 hardware-dependent track implementations
KSP 1.03  standardized UTF-8 META key/value resource
KSP 1.04  localized META values and default-language declaration
KSP 1.05  shared physical payload views and cross-resource KZB1 aliasing
KSP 1.06  declared bounded MSX runtime profiles and preinstalled working sets
```

A strict KSP 1.06 file declares header minor version `6`.

A KSP 1.06 reader must accept minor versions `0` through `6`, subject to the
rules of those versions. A strict KSP 1.05 reader may reject minor version `6`
before inspecting resources.

KSP 1.06 retains `metadata_version=2`; the META grammar is unchanged.

## 2. Header changes

The 80-byte KSP header remains unchanged in size and layout. Header field
`file_flags` at offset `0x08` is no longer required to be zero.

```text
Bit  Name                         Meaning
0    KSP_FILE_MSX_SAFE_PROFILE    At least one declared baseline implementation
                                  satisfies the KSP 1.06 MSX-safe profile.
1-31 reserved                     Must be zero in strict KSP 1.06 files.
```

A reader that does not understand a set file-flag bit must reject the file. It
must not silently ignore an unknown runtime guarantee.

A minor-version-6 file may leave bit 0 clear. Such a file gains KSP 1.06 reader
compatibility but makes no MSX-safe claim.

## 3. MSX-safe profile metadata

When `KSP_FILE_MSX_SAFE_PROFILE` is set, the package must contain a valid `META`
resource with `metadata_version=2` and the following unlocalized keys:

```text
msx_runtime_profile=<positive decimal profile number>
msx_min_ram_kib=<minimum mapper RAM in KiB>
msx_working_set_preinstalled=1
msx_vram_cache_base=<decimal byte address>
msx_cache_slot_bytes=<decimal bytes per physical slot>
msx_max_track_pages=<decimal maximum selected-track page count>
msx_max_vram_read_per_tick=<decimal bytes>
msx_no_disk_during_play=1
msx_no_decompression_during_play=1
```

The structural engine, page, and track tables remain authoritative. META values
do not override those tables. The keys describe and constrain the implementation
selected for the declared baseline.

The first standardized profile is:

```text
msx_runtime_profile=1
```

Profile 1 is the **preinstalled VRAM working-set profile** described below.
Unknown positive profile numbers may be rejected by strict MSX players while
remaining readable by generic KSP tools.

### 3.1 Optional mix hint

KSP 1.06 defines this optional key:

```text
psg_trim_steps=<decimal 0..15>
```

It requests that an engine reduce PSG amplitude by the stated number of AY
volume steps at the final hardware-output stage. It is a mix-compatibility hint,
not a change to the captured or decoded source state. Players may expose a user
override. A pack must not depend on the hint for memory safety or timing.

Analog SCC/PSG balance differs among machines, cartridges, mixers, and host
emulators. Therefore this value is not an electrical calibration standard.

## 4. Profile 1: preinstalled VRAM working set

A logical/public track satisfies profile 1 only when the hardware-selection
rules choose a physical implementation that meets every requirement in this
section.

### 4.1 Baseline hardware coverage

The package must declare `msx_min_ram_kib`, and every visible logical track must
resolve to at least one implementation for the packer's declared baseline
hardware.

`HVAR`/`HVR1` may provide additional implementations. A profile-1 claim applies
only to candidates that themselves satisfy the profile. A player must not select
an implementation that exceeds its detected RAM, VRAM, chip, slot, or cache
capacity.

For the SCREEN-1-preserving 128-KiB-VRAM layout standardized here:

```text
msx_vram_cache_base=16384       # 0x4000
msx_cache_slot_bytes=8192       # 0x2000
msx_max_track_pages<=14
```

This leaves VRAM `0x0000..0x3FFF` available for text/UI data and provides at most
14 cache slots through `0x1FFFF`.

### 4.2 Physical cache-slot rules

1. Every selected-track dynamic page must be fully reconstructed before engine
   `INIT` returns.
2. Each physical slot begins at
   `msx_vram_cache_base + slot * msx_cache_slot_bytes`.
3. A dynamic page's cached logical payload must fit entirely in one slot.
4. For the standardized layout, cached payload is at most `0x1C00` (7168) bytes
   in an `0x2000`-byte slot.
5. No sequential VDP transfer may cross a 16-KiB VRAM address boundary. A writer
   must align or split transfers so V9938 low-14-bit address wrap cannot corrupt
   another slot.
6. Slot tags and descriptor mappings must be published only after the payload is
   complete and its CRC or equivalent integrity check has succeeded.
7. The exact mapping from original descriptor number to physical slot must remain
   stable for the lifetime of the selected track unless the engine explicitly
   declares and safely performs a bounded replacement.

### 4.3 Normal PLAY constraints

After successful `INIT`, normal `PLAY` callbacks for a profile-1 implementation
must satisfy all of the following:

- no KSP file reads;
- no FAT or directory traversal;
- no decompression;
- no mapper-segment allocation or release;
- no reconstruction of a complete dynamic page;
- no fallback to disk after a descriptor miss;
- no dependence on package tables that may have been overwritten or unmapped;
- every direct VRAM read is bounded by `msx_max_vram_read_per_tick`;
- engine execution and all VRAM transfers are designed to complete within the
  declared 50/60-Hz callback budget on the baseline CPU.

For the strict profile-1 SCREEN-preserving layout, writers should keep:

```text
msx_max_vram_read_per_tick<=64
```

A player may reject a larger declared value when it cannot meet the callback
budget on the detected CPU.

### 4.4 Missing pages and fallback behavior

A profile-1 engine must not request an uncached page during normal playback. A
missing descriptor is a package/player error, not permission to perform a disk
read in the audio hot path.

A player must stop the track cleanly or return a recoverable playback error. It
must not resume from a partially installed page or silently substitute a stale
cache slot.

### 4.5 Loop and state entry

A deterministic event/delta engine must publish a complete hardware state at:

- the first playable frame;
- every externally addressable seek/restart point;
- every loop entry.

This prevents a loop or restart from depending on register state left by the
preceding path.

## 5. Player implementation requirements for profile 1

A player claiming KSP 1.06 profile-1 support must meet these requirements.

### 5.1 Resident code and scratch memory

- All code needed during disk installation and normal `PLAY` must remain visible
  under every mapper/slot configuration used by that code.
- Player scratch memory must be explicitly reserved. It must not overlap BIOS,
  DiskROM-private work areas, DOS work areas, stack ranges, overlays, package
  tables, or engine state.
- No address is considered free merely because one machine or one OpenMSX model
  left it unchanged.

### 5.2 Mapper and slot handling

- Detect mapper RAM and slots dynamically; do not assume a model-specific slot
  or segment number.
- Mask mapper readback bits according to detected mapper capacity.
- Allocate only existing segments and restore all page mappings on every success
  and error path.
- Preserve expanded-slot state and both SCC cartridge selections explicitly.
- Track replacement must be atomic: resolve and validate the destination before
  stopping the old engine, and never call `PLAY` on a partial installation.

### 5.3 Disk access

- Use documented MSX-DOS/BIOS interfaces only.
- Do not use private DiskROM stack or workspace addresses for player variables.
- Treat each independent disk phase as requiring valid, initialized file state;
  do not rely on undocumented FCB internals surviving another DOS call.
- Complete all required file reads before activating engine mappings that hide
  loader code or data.

### 5.4 VRAM access

- Set all V9938 address bits for every independent transfer.
- Split or align writes at 16-KiB VRAM boundaries.
- Preserve interrupt and VDP register state according to the player's calling
  contract.
- UI VRAM and cache VRAM must have non-overlapping declared ranges.

## 6. Packaging recommendations

KSP 1.06 does not impose a file-size limit. For a 720-KiB floppy distribution,
a packer should normally keep each KSP below approximately 600 KiB so the player,
index, boot code, and filesystem overhead fit on the same disk.

Large albums should be split into volumes without changing original logical
track numbers in user-visible metadata. A volume-local track table may use local
indices, but the original album index should be retained in metadata or the UI.

Engine templates and sparse dynamic overlays may use KSP's existing ZX0
compression during installation. Profile 1 forbids decompression only during
normal `PLAY`, not during track installation.

## 7. Standard MSD1 deterministic dual-SCC profile

`MSD1` is the first reference engine/data layout built for profile 1. It is
intended for deterministic SCC/PSG timelines whose complete selected-track
working set can be preinstalled.

`MSD1` is not mandatory for every KSP 1.06 pack. Other engines may claim profile
1 when they meet all general requirements.

### 7.1 Hardware and timing

The current `MSD1` implementation targets:

```text
dual normal SCC cartridges
PSG
60-Hz captured state timeline
minimum 128 KiB mapper RAM
128 KiB VRAM
```

A pack may provide other hardware variants through ordinary `HVAR`/`HVR1` rules.

### 7.2 Engine header page

The selected physical track's first dynamic descriptor begins with:

```text
Offset Size Description
00     4    "MSD1"
04     1    MSD1 revision, currently 1
05     1    flags; bit 0 = loop enabled
06     1    tick rate in Hz
07     1    reserved, zero
08     2    first data-page descriptor
0A     2    loop data-page descriptor, or 0xFFFF
0C     2    loop record offset within reconstructed page
0E     2    selected track's first physical descriptor/base
10     4    reserved for future use, zero in revision 1
```

### 7.3 Data page

Every following data descriptor begins with:

```text
Offset Size Description
00     4    "MSP1"
04     2    next physical descriptor, or 0xFFFF
06     2    first byte after the final record in this page
08     ...  record stream
```

The dynamic replacement window is `0x6400..0x7FFF`, giving `0x1C00` bytes per
cached page. The eight-byte page header is included in that window.

### 7.4 Record stream

```text
First byte  Meaning
00          one valid no-change tick
01..FE      changed-frame payload length in bytes
FF,count    no-change run of count ticks; count must be 2..255
```

A `00` record is not end-of-track. End/continuation is determined by the data
page header and selected-track flags.

A changed-frame payload contains entity commands:

```text
bits 7..4   entity: 0..7 dual-SCC voice, 8 PSG noise/rhythm entity
bits 2..0   field mask: bit0 period, bit1 volume, bit2 wave/rhythm
bit 3       for voice period: signed 8-bit delta instead of absolute u16
```

Fields are stored in period, volume, wave/rhythm order when present.

For a voice period:

- bit 3 clear: unsigned little-endian absolute 12-bit period in a u16 field;
- bit 3 set: signed 8-bit delta from the resident previous period.

Special command `F0` is a compact volume block:

```text
F0
u16 entity bitmap, bits 0..8
packed 4-bit volume values in ascending entity order,
low nibble first, then high nibble
```

A writer may use ordinary per-entity volume fields instead when they are no
larger. Payload length must remain at most 254 bytes and must also obey the
package's `msx_max_vram_read_per_tick` declaration including the length byte.

### 7.5 Wave dictionary

The reference engine may embed a deduplicated dictionary of 32-byte SCC
waveforms in its resident template. Revision 1 supports up to 64 dictionary
entries. Track records reference dictionary indices, not raw 32-byte waveforms.

A complete state must be forced at first frame and loop entry.

## 8. Validation requirements

A strict profile-1 packer should produce a machine-readable validation report
covering at least:

- all visible tracks resolve on the declared baseline;
- reconstructed page CRCs;
- maximum pages per track;
- maximum direct VRAM bytes per tick;
- no record crosses its reconstructed page end;
- loops resolve to a complete-state record;
- deterministic decoded state matches the source timeline when such a source is
  available;
- compressed blocks decode to their declared sizes and CRCs.

Emulator counters are not proof of musical correctness. Acceptance must include
semantic register/waveform comparison and physical listening on representative
MSX2 and turboR machines.

## 9. Backward compatibility

A minor-version-5 compatibility copy must:

- declare minor version `5`;
- clear `KSP_FILE_MSX_SAFE_PROFILE` and all other file flags;
- not require a reader to understand profile-1 metadata or `MSD1` behavior;
- materialize shared payloads as required by KSP 1.05 compatibility rules.

Simply changing the header from minor 6 to minor 5 is not a compatibility
conversion when the selected engine depends on KSP 1.06 player behavior.

## 10. Current reference implementation notes

The Shovel Knight reference conversion uses:

```text
msx_runtime_profile=1
msx_min_ram_kib=128
msx_working_set_preinstalled=1
msx_vram_cache_base=16384
msx_cache_slot_bytes=8192
msx_max_track_pages=14
msx_max_vram_read_per_tick=64
msx_no_disk_during_play=1
msx_no_decompression_during_play=1
psg_trim_steps=2
```

These values document one implementation and do not redefine the general KSP
container for other sound hardware.
