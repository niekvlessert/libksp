# KSP Format and Player Implementation Specification

**Version:** 1.01  
**Extension:** `.KSP`  
**Byte order:** little-endian  
**Purpose:** compressed MSX music packages containing one or more playback engines, tracks, reconstructed 16 KiB runtime pages, slab-compressed shared page-block pools, hybrid mapper-RAM/VRAM preload pools, shared source resources, metadata, sample kits, images, and optional banked data.

KSP is a standalone format. It is not wrapped in KSS and does not contain `KCPX`, `KCPZ`, `KSSX`, `KSCC`, an EOF trailer, or game-specific variant IDs.

KSP 1.01 is a backward-compatible minor revision of KSP 1.00. It adds
declarative writable page-2 and private page-3 runtime profiles so players never
need to recognize particular games or engine byte sequences. All valid KSP 1.00 files remain
valid KSP 1.01 inputs.

KSP 1.00 made slab-compressed shared page-block pooling, generic resource-range page reconstruction, and hybrid mapper-RAM/VRAM preload pooling native KSP features. They replace experimental KCPZ-v3/v4 page-pool variants, the separate hybrid profile, and game-specific bank reconstruction formats.

**KSP 1.01 additions:** `KSP_ENGINE_PAGE2_RUNTIME` and `KSP_ENGINE_PAGE3_WORKRAM`.

**KSP 1.00 additions:** `KSP_PAGE_RESOURCE_MAP`, `RMP1`, `KSP_RESOURCE_PAGE_SOURCE`, generic `DATA` resources, slab-based `PBK1` storage, `KSP_PAGE_HYBRID_POOL`, `HPOL`, and `HPL1`.

---

## 1. Design principles

A KSP file contains:

```text
KSP header
Engine table
Page table
Track table
Resource table
String table
Compressed payloads
```

Each engine has:

- one common runtime-page template;
- one or more reconstructed runtime pages;
- INIT, PLAY, and optional STOP addresses;
- required sound-hardware flags;
- an optional dynamic page-switch ABI;
- optional banked data;
- an optional default MWK sample kit.

Each page is represented by one of these generic encodings:

1. the engine template plus a sparse overlay;
2. a complete replacement page;
3. the engine template or a zero page plus records that copy logical blocks from a slab-compressed shared page-block pool;
4. the engine template or a zero page plus records that copy ranges from shared source resources and apply small literal or fill patches;
5. the engine template plus a common destination-position table and per-page block-ID row backed by hot mapper-RAM, warm VRAM, and optional cold on-disk tiers.

A track maps a public track number to:

- an engine page;
- an engine-specific song ID;
- optional timing information;
- an optional MWK;
- an optional image;
- a display title.

Offsets are absolute file offsets. Public track indices, page indices, engine indices, resource indices, and engine song IDs are 16-bit.

Shared block pools, hybrid preload pools, and page-source resources are package resources. They are not tied to a game, filename, publisher, or engine type. Several pages and engines may reference the same pool or source resource.

### 1.1 Limits

```text
Maximum public tracks per KSP: 65,535
Maximum pages per KSP:         65,535
Maximum engines per KSP:       65,535
Maximum resources per KSP:     65,535
```

Valid public track indices are:

```text
0 .. track_count - 1
```

No player component may store a track, page, engine, resource, or engine song ID in an 8-bit variable.

The value `0xFFFF` is used as a null reference only in fields explicitly documented as optional.

### 1.2 Shared-data rationale

A package must not be forced to store one independently compressed copy of overlapping music data for every runtime page.

Shared page blocks are useful when:

- many pages contain identical engine, waveform, table, or music fragments;
- pages share data at arbitrary positions rather than as one continuous source range;
- independently compressed overlays lose cross-page deduplication.

Logical pool blocks remain small for deduplication, but are physically grouped into independently compressed slabs. This retains most cross-block ZX0 compression while keeping random access and a bounded MSX scratch requirement.

Resource-range maps are useful when:

- tracks select different windows or ranges from one original music bank or stream;
- several tracks reuse the same complete source bank;
- a page can be described as a common template plus a few source ranges and small relocation patches;
- storing generic fixed-size blocks would add unnecessary descriptors or destroy long-distance compression within the original source.

Hybrid preload pools are useful when:

- a large set of pages is built from the same destination positions;
- most shared blocks can remain resident across track changes;
- a target MSX2 has mapper RAM and VRAM that would otherwise be unused during audio playback;
- compressing a hot or warm tier as one long stream is materially smaller than independent slabs;
- an optional cold tier can tolerate on-demand slab decoding.

The packer should compare these representations and choose the smallest valid one that meets the declared target profile:

```text
sparse overlay
complete page
shared-block map with compressed slabs
resource-range map
hybrid RAM/VRAM preload pool
```

The format does not require every page in one engine to use the same encoding. A package may contain several `PBLK` pools, several `DATA`/bank source resources, or both. KSP 1.01 permits at most one `HPOL` resource because hybrid pages select map rows by global page index.

---

## 2. KSP header

The header is 80 bytes.

```text
Offset Size Type Description
00     4         "KSP1"
04     2    u16  header size, 0x0050
06     2    u16  minor version: 0 for KSP 1.00, 1 for KSP 1.01
08     4    u32  file flags
0C     4    u32  complete file size

10     4    u32  engine-table offset
14     2    u16  engine count
16     2    u16  engine-entry size, 64

18     4    u32  page-table offset
1C     2    u16  page count
1E     2    u16  page-entry size, 24

20     4    u32  track-table offset
24     2    u16  track count
26     2    u16  track-entry size, 32

28     4    u32  resource-table offset
2C     2    u16  resource count
2E     2    u16  resource-entry size, 32

30     4    u32  string-table offset
34     4    u32  string-table size

38     2    u16  default public track
3A     2    u16  META resource index, or 0xFFFF
3C     2    u16  cover IMG5 resource index, or 0xFFFF
3E     2         reserved, zero

40     4    u32  header CRC32
44     4    u32  index CRC32
48     8         reserved, zero
```

### 2.1 File flags

No file flags are assigned through version 1.01. The field must be zero.

Shared-block and resource-map support are identified by page encoding and resource type, not by a file flag.

### 2.2 CRC rules

CRC32 uses the IEEE polynomial `0xEDB88320`.

`header_crc32` covers the complete header with the CRC field itself temporarily set to zero.

`index_crc32` covers these byte ranges concatenated in this order:

1. engine table;
2. page table;
3. track table;
4. resource table;
5. string table.

A CRC field of zero means the CRC was not generated.

Desktop readers should validate nonzero CRCs. The constrained MSX player may omit CRC validation but must still perform complete bounds validation.

---

## 3. Engine table

Each engine entry is 64 bytes.

```text
Offset Size Type Description
00     4    u32  engine flags
04     4    u32  required hardware flags
08     2    u16  engine ABI version, 1
0A     2    u16  PLAY frequency, normally 50 or 60 Hz
0C     2    u16  page load address
0E     2    u16  page size
10     2    u16  INIT address
12     2    u16  PLAY address
14     2    u16  STOP address, or 0
16     2    u16  dynamic page-switch gateway, or 0
18     2    u16  replace-start address
1A     2    u16  first global page index
1C     2    u16  number of pages belonging to engine
1E     2    u16  default MWK resource, or 0xFFFF
20     1    u8   template compression
21     1    u8   first logical bank number
22     1    u8   bank count
23     1    u8   bank-width code
24     4    u32  template data offset
28     4    u32  template packed size
2C     4    u32  template unpacked size
30     4    u32  template CRC32
34     4    u32  engine-name string offset, or 0xFFFFFFFF
38     8         reserved, zero
```

For the MSX KSPPLAY profile:

```text
page_load_address = 0x4000
page_size         = 0x4000
```

The template must decompress to exactly `page_size` bytes.

### 3.1 Engine flags

```text
bit 0  KSP_ENGINE_DYNAMIC_PAGES
       The engine may call the page-switch gateway during playback.

bit 1  KSP_ENGINE_BANKED_DATA
       The engine uses BNK8 or BN16 resources.

bit 2  KSP_ENGINE_MWK_REQUIRED
       A valid track or engine-default MWK is required.

bit 3  KSP_ENGINE_PAGE2_RUNTIME          (KSP 1.01)
       Before INIT, the reconstructed 4000h-7FFFh engine page must also be
       present as an initially identical, writable runtime image at
       8000h-BFFFh. The player may implement this as a copy or as an initial
       mapper alias. Coherence with the page-1 image after INIT is not
       required.

bit 4  KSP_ENGINE_PAGE3_WORKRAM          (KSP 1.01)
       INIT, PLAY, and STOP require a private, persistent 16 KiB work-RAM
       page at C000h-FFFFh. A native DOS player must map this page only while
       calling the engine and restore the process/DOS page before enabling
       interrupts or invoking DOS. Hosted KSS players already provide an
       isolated 64 KiB address space and need no additional image data.

bits 5–31 reserved, zero
```

Consistency requirements:

- `DYNAMIC_PAGES` requires a nonzero gateway and valid `replace_start`.
- `BANKED_DATA` requires nonzero `bank_count`.
- `MWK_REQUIRED` requires either a default MWK or an MWK on every playable track.
- `PAGE2_RUNTIME` requires minor version 1 or later,
  `page_load_address = 0x4000`, and `page_size = 0x4000`.
- `PAGE2_RUNTIME` must not be combined with `SCC`, `SCC+`, or `DUAL_SCC`,
  because those devices require cartridge address space in page 2.
- `PAGE3_WORKRAM` requires minor version 1 or later. It may be combined with
  any sound-hardware flags because it changes only page 3.

`PAGE2_RUNTIME` and `PAGE3_WORKRAM` are engine memory-layout requirements, not
sound-hardware flags or game identifiers. A player must select these behaviors
only from the flags; examining INIT/PLAY code or matching known byte signatures is not a
conforming substitute. On a native MSX mapper implementation, mapping the same
segment into pages 1 and 2 before INIT satisfies the requirement. On a desktop
bridge, copying the reconstructed image into writable page-2 RAM satisfies it.

KSP 1.00 readers are not required to accept bit 3. Therefore, a file using
`PAGE2_RUNTIME` must declare minor version 1. A KSP 1.01 reader must accept
minor versions 0 and 1 and must reject unsupported higher minor versions or
unknown engine flags.

### 3.2 Hardware flags

```text
bit 0  MSX PSG
bit 1  SCC
bit 2  SCC+
bit 3  dual SCC
bit 4  YM2413 / FMPAC
bit 5  Y8950 / MSX-AUDIO
bit 6  OPL4 / MoonSound
bit 7  SN76489
bit 8  Game Gear stereo
bits 9–31 reserved, zero
```

Flags may be combined.

`DUAL_SCC` means two SCC-capable devices are required. Cartridge slot selection is runtime configuration and is not stored in the KSP.

`OPL4` assumes the standard MoonSound YRW801 ROM. A KSP must not contain a YRW801 filename or ROM requirement field.

### 3.3 Compression IDs

Compression IDs are shared by templates, page payloads, and normal resources.

```text
0  KSP_COMPRESSION_NONE
   Data is stored uncompressed.

1  KSP_COMPRESSION_ZX0
   One forward ZX0 stream representing the entire object.

2  KSP_COMPRESSION_ZX0_BLOCKS
   The object is divided into independently compressed sequential ZX0 blocks.
```

`ZX0_BLOCKS` is intended for sequential resources that cannot safely be decoded as one object under the declared target profile, especially large MWK sample kits and page-source resources.

#### 3.3.1 Compression-method selection

Compression is selected per independently decoded object, not from the size of the complete `.KSP` file.

For the baseline MSX2 target with 128 KiB mapper RAM and 128 KiB VRAM, the packer must use one `ZX0` stream when the complete uncompressed object can be decoded safely using its final destination or the available decode buffer while all required player, engine, bank, cache, display, and hardware allocations remain valid.

The packer must use `ZX0_BLOCKS` when a normal sequential resource cannot satisfy that condition. Every independent `KZB1` block must fit the available scratch area after decompression; the baseline MSX-DOS2 limit is 16 KiB per block.

In practical terms:

```text
Use NONE or one ZX0 stream:
    the complete object fits its bounded decode buffer; or
    the decoder writes it directly to its complete final mapper-RAM or VRAM destination.

Use ZX0_BLOCKS:
    decoding the complete object would exceed the available scratch buffer;
    retaining the complete decoded object would displace required runtime allocations;
    only ranges or sequential portions are needed during playback; or
    bounded loading is required to avoid exhausting the baseline target.
```

A packer may choose `ZX0_BLOCKS` even when one stream technically fits when blockwise access materially reduces track-change latency, dynamic-page-switch latency, or resident-memory pressure. It must not choose one whole-object `ZX0` stream merely because the total physical RAM and VRAM capacity is numerically larger than the object; the required memory layout and simultaneous allocations must also be feasible.

The following container-specific rules take precedence:

- templates and normal page payloads use `NONE` or `ZX0` and must fit the ordinary decode limit;
- `PBLK` data is divided into independently decoded slabs;
- the hybrid cold tier is divided into independently decoded slabs;
- `HPL1` map, hot, and warm streams may exceed 16 KiB because their decoders explicitly span mapper RAM or write to VRAM;
- bank resources remain `NONE` or `ZX0` because each defined bank is at most 16 KiB;
- MWK and page-source resources use `ZX0_BLOCKS` whenever whole-object decoding is not feasible under the target profile.

Templates and normal page payloads use `NONE` or `ZX0`.

A `PBLK` resource has its own indexed slab container and therefore uses `KSP_COMPRESSION_NONE` in the resource entry. Each slab independently uses `NONE` or `ZX0`; logical blocks reference byte ranges inside the uncompressed slabs.

An `HPOL` resource also uses `KSP_COMPRESSION_NONE` in the resource entry. Its `HPL1` container defines one ZX0 map stream, one optional whole-stream hot pool, one optional whole-stream warm pool, and independently compressed cold slabs. The hot and warm output sizes may exceed 16 KiB only under the hybrid MSX profile defined in sections 7.5 and 10.

Unknown compression IDs must be rejected when the corresponding object is required.

### 3.4 Bank-width codes

```text
0  no banks
1  8 KiB banks
2  16 KiB banks
```

The logical bank range is:

```text
bank_base .. bank_base + bank_count - 1
```

Each logical bank must have one matching `BNK8` or `BN16` resource.

---

## 4. Engine ABI version 1

### 4.1 INIT

Before calling INIT, the player sets:

```text
HL = 16-bit engine song ID
A  = low byte of engine song ID
BC = 0
DE = 0
```

Providing both `HL` and `A` allows existing 8-bit drivers and newer 16-bit drivers to use the same ABI.

INIT may destroy all normal registers. The stack pointer must remain valid.

### 4.2 PLAY

PLAY is called at `tick_hz`.

PLAY receives no parameters and may destroy all normal registers. The player must preserve its own state around the call.

### 4.3 STOP

When `stop_address != 0`, STOP must be called:

- before changing to another public track;
- before replacing the current engine;
- before exiting to DOS;
- before disabling an engine’s hardware.

STOP receives no parameters.

### 4.4 Dynamic page-switch gateway

KSP ABI 1 reserves:

```text
gateway address     0xD8A0
desktop mailbox     0xD89E–0xD89F
```

An engine requests another engine-local page with:

```text
HL = engine-local page index
A  = low byte of page index
CALL 0xD8A0
```

The valid range is:

```text
0 <= HL < engine.page_count
```

The corresponding global page is:

```text
engine.first_page + HL
```

On return:

```text
carry clear  page successfully installed
carry set    invalid page or materialization failure
```

The gateway preserves:

- BC;
- DE;
- HL;
- IX;
- IY;
- alternate registers;
- SP;
- the original interrupt-enable state.

AF is undefined except for the returned carry flag.

For desktop emulation, the player installs this four-byte gateway:

```text
22 9E D8 C9    LD (0xD89E),HL / RET
```

The memory-write handler collects the low and high mailbox writes and performs the page switch after the high byte is written.

A native MSX player that cannot safely keep executable code at `0xD8A0` may
relocate `CALL 0xD8A0` operands found in the immutable engine prefix below
`replace_start` to an implementation-owned resident gateway. The resulting
callback must preserve the same ABI, including page-3 mapping when
`KSP_ENGINE_PAGE3_WORKRAM` is active.

### 4.5 Replace-start rule

Initial track loading installs the complete reconstructed runtime page.

A dynamic page switch replaces only:

```text
replace_start .. page_load_address + page_size - 1
```

Bytes below `replace_start` remain unchanged. This preserves running engine code, variables, and the return path.

The gateway call and its return address must reside below `replace_start`.

### 4.6 MSX dual-SCC relocation callbacks

For ABI-1 engines declaring `DUAL_SCC`, cartridge slots remain runtime
configuration. The portable engine image uses the following `CALL` operands as
relocation tokens inside the immutable region below `replace_start`:

```text
CALL 0xD900   select and enable SCC device A
CALL 0xD904   select and enable SCC device B
CALL 0xD908   restore the player's page-2 RAM mapping
```

These token addresses are not fixed runtime entry points. A native MSX player
must rewrite every required operand before INIT. A pack declaring `DUAL_SCC`
must contain all three tokens in the immutable engine prefix.

The relocated callbacks preserve AF, BC, DE, HL, IX and IY, do not change the
interrupt-enable state, and preserve the current page-3 mapper segment. SCC
selection enables the normal SCC register window. The two runtime-selected
devices must be distinct.

This ABI currently describes two normal SCC devices. A package requiring two
SCC+ devices needs a future explicitly defined ABI and must not combine
`DUAL_SCC` with `SCC+`.

---

## 5. Page table

Each page entry is 24 bytes.

```text
Offset Size Type Description
00     2    u16  owning engine index
02     1    u8   page encoding
03     1    u8   page-payload compression ID
04     2    u16  page flags
06     2         reserved, zero
08     4    u32  page-payload offset
0C     4    u32  packed page-payload size
10     4    u32  unpacked page-payload size
14     4    u32  CRC32 of final reconstructed runtime page
```

The final reconstructed page must always be exactly `engine.page_size` bytes.

### 5.1 Page encodings

```text
0  KSP_PAGE_SPARSE_OVERLAY
1  KSP_PAGE_COMPLETE
2  KSP_PAGE_SHARED_BLOCK_MAP
3  KSP_PAGE_RESOURCE_MAP
4  KSP_PAGE_HYBRID_POOL
```

#### Encoding 0: sparse overlay

The player copies the engine template and then applies records:

```text
u16 page_offset
u16 byte_count
u8  data[byte_count]
```

Records continue until `unpacked_size` bytes have been consumed. There is no terminator.

Every record must satisfy:

```text
byte_count != 0
page_offset + byte_count <= engine.page_size
```

Records must be ordered by increasing `page_offset` and must not overlap.

#### Encoding 1: complete page

The page payload decompresses to exactly `engine.page_size` bytes and replaces the template completely.

Page flags must be zero.

#### Encoding 2: shared-block map

The page payload decompresses to a `PBM1` block-map structure.

By default, the player first copies the engine template. It then applies block-copy records from one `PBLK` resource.

When `KSP_PAGE_BASE_ZERO` is set, the player starts with an all-zero page instead of the engine template.

This encoding covers both:

- template plus pooled overlays;
- complete pages assembled from pooled blocks over a zero base.

Logical pool blocks are fixed-size deduplication units. They are physically stored inside compressed slabs as defined by `PBK1`; a page record never contains or depends on a physical slab offset.

##### `PBM1` header

```text
Offset Size Type Description
00     4         "PBM1"
04     2    u16  header size, 16
06     2    u16  PBLK resource-table index
08     2    u16  record count
0A     2    u16  record size, 12
0C     4         reserved, zero
```

The referenced resource must have FourCC `PBLK`.

##### `PBM1` copy record

Each record is 12 bytes.

```text
Offset Size Type Description
00     2    u16  destination offset in reconstructed page
02     2    u16  byte count
04     4    u32  logical pool-block index
08     2    u16  source offset inside logical pool block
0A     2         reserved, zero
```

Every record must satisfy:

```text
byte_count != 0
destination_offset + byte_count <= engine.page_size
block_index < pool.block_count
source_offset + byte_count <= pool.block_size
```

Records must be ordered by increasing destination offset and must not overlap.

Several records may reference the same logical pool block. Several logical blocks may reside in one slab. Several pages and engines may reference the same `PBLK` resource.

The page-payload compression field applies only to the `PBM1` map itself and must be `NONE` or `ZX0`.

#### Encoding 3: resource-range map

The page payload decompresses to an `RMP1` resource-map structure.

By default, the player first copies the engine template. When `KSP_PAGE_BASE_ZERO` is set, it starts with an all-zero page.

This encoding reconstructs a page from shared resources without converting those resources into fixed-size logical pool blocks. It is intended for original music banks, continuous data streams, waveform sets, tables, and other source material that compresses better as one continuous object.

##### `RMP1` header

```text
Offset Size Type Description
00     4         "RMP1"
04     2    u16  header size, 16
06     2    u16  record count
08     2    u16  record size, 16
0A     2    u16  map flags, zero
0C     4         reserved, zero
```

##### `RMP1` record

Each record is 16 bytes.

```text
Offset Size Type Description
00     2    u16  destination offset in reconstructed page
02     2    u16  byte count
04     1    u8   record type
05     1    u8   record flags, zero
06     2    u16  resource index, or 0xFFFF for non-resource records
08     4    u32  source offset, inline-data offset, or fill value
0C     4         reserved, zero
```

Record types:

```text
0  KSP_RMAP_COPY_RESOURCE
   Copy byte_count bytes from the logical uncompressed resource beginning at source_offset.
   The referenced resource must have KSP_RESOURCE_PAGE_SOURCE set.

1  KSP_RMAP_COPY_INLINE
   Copy byte_count literal bytes from the RMP1 payload beginning at source_offset.
   resource_index must be 0xFFFF.

2  KSP_RMAP_FILL
   Fill byte_count destination bytes with the low byte of source_offset.
   resource_index must be 0xFFFF and the upper 24 bits of source_offset must be zero.
```

For `COPY_INLINE`, `source_offset` is relative to the beginning of the uncompressed `RMP1` payload. Inline bytes must lie after the fixed header and record table.

Every record must satisfy:

```text
byte_count != 0
destination_offset + byte_count <= engine.page_size
```

For `COPY_RESOURCE`:

```text
resource_index < resource_count
resource has KSP_RESOURCE_PAGE_SOURCE
source_offset + byte_count <= resource.unpacked_size
```

Records must be ordered by increasing destination offset and must not overlap. Several records may reference the same resource or overlapping source ranges. A source range may cross `KZB1` block boundaries.

The page-payload compression field applies to the complete `RMP1` payload, including inline bytes, and must be `NONE` or `ZX0`.

The final reconstructed-page CRC is calculated after all records have been applied for every encoding.


#### Encoding 4: hybrid RAM/VRAM preload pool

A hybrid page has no individual page payload. The page table entry selects its row implicitly by the page's **global page index** from the package-wide `HPOL` resource.

The player:

1. copies the owning engine template into the reconstruction page;
2. reads the destination-position table from `HPL1`;
3. reads the page's row of 16-bit global block IDs;
4. resolves each block ID to the hot, warm, or cold tier;
5. copies one complete fixed-size block to the corresponding destination position.

For an encoding-4 page:

```text
page_payload_compression = KSP_COMPRESSION_NONE
page_flags               = 0
page_payload_offset      = 0
packed_page_payload_size = 0
unpacked_payload_size    = 0
```

The package must contain exactly one `HPOL` resource. Its `HPL1.page_count` must equal the KSP header's global `page_count`. Rows corresponding to pages with another encoding are ignored, which permits mixed-format packages.

Hybrid pages always use the engine template as their base. Zero-based hybrid reconstruction is not defined in KSP 1.01.

The final reconstructed-page CRC is calculated after every destination block has been copied.

### 5.2 Page flags

```text
bit 0  KSP_PAGE_BASE_ZERO
       Valid with KSP_PAGE_SHARED_BLOCK_MAP and KSP_PAGE_RESOURCE_MAP.
       Start reconstruction from an all-zero page rather than the engine template.

bits 1–15 reserved, zero
```

For sparse-overlay, complete-page, and hybrid-pool encodings, page flags must be zero.

### 5.3 Engine ownership

The pages belonging to an engine must occupy one contiguous range beginning at `first_page`.

Every page in that range must contain the same engine index.

---

## 6. Track table

Each public track entry is 32 bytes.

```text
Offset Size Type Description
00     2    u16  global page index
02     2    u16  engine-specific song ID
04     2    u16  track flags
06     2    u16  MWK resource index, or 0xFFFF
08     2    u16  IMG5 resource index, or 0xFFFF
0A     2         reserved, zero
0C     4    u32  title offset in string table, or 0xFFFFFFFF
10     4    u32  duration in milliseconds
14     4    u32  loop-start time in milliseconds
18     4    u32  loop-end time in milliseconds
1C     4    u32  fade time in milliseconds
```

The owning engine is obtained from the referenced page entry.

### 6.1 Timing values

```text
duration_ms    0xFFFFFFFF = unknown
loop_start_ms  0xFFFFFFFF = no known loop
loop_end_ms    0xFFFFFFFF = no known loop
fade_ms        0xFFFFFFFF = use player default
fade_ms        0          = do not fade
```

A loop is valid only when both loop fields are known and:

```text
loop_start_ms < loop_end_ms
```

### 6.2 Track flags

```text
bit 0  KSP_TRACK_HIDDEN
       Do not show in the normal menu or next/previous sequence.

bit 1  KSP_TRACK_SOUND_EFFECT
       Entry represents a sound effect rather than normal music.

bit 2  KSP_TRACK_ONE_SHOT
       Do not repeat the track automatically.

bit 3  KSP_TRACK_NO_AUTO_ADVANCE
       Do not automatically continue to the following public track.

bits 4–15 reserved, zero
```

A hidden track remains directly addressable by its public index.

---

## 7. Resource table

Each resource entry is 32 bytes.

```text
Offset Size Type Description
00     4         resource FourCC
04     2    u16  resource flags
06     1    u8   compression ID
07     1         reserved, zero
08     4    u32  data offset
0C     4    u32  packed size
10     4    u32  logical unpacked size
14     4    u32  CRC32 of logical unpacked data
18     4    u32  auxiliary value 0
1C     4    u32  auxiliary value 1
```

Resource references are resource-table indices. `0xFFFF` means no resource.

### 7.1 Resource flags

```text
bit 0  KSP_RESOURCE_REQUIRED
       Playback must fail if this resource cannot be used.

bit 1  KSP_RESOURCE_STREAMABLE
       The resource may be processed sequentially without loading it fully.

bit 2  KSP_RESOURCE_PAGE_SOURCE
       The logical uncompressed bytes participate directly in page construction.
       This is required for resources referenced by KSP_PAGE_RESOURCE_MAP and for HPOL.

bits 3–15 reserved, zero
```

Unknown optional resource types must be skipped. Unknown required resource types must cause an unsupported-format error.

### 7.2 Sequential block-compressed resource format

When a normal resource entry uses:

```text
compression = KSP_COMPRESSION_ZX0_BLOCKS
```

its packed payload uses the `KZB1` sequential container.

#### `KZB1` header

```text
Offset Size Type Description
00     4         "KZB1"
04     2    u16  header size, 16
06     2    u16  block count
08     4    u32  total unpacked size
0C     4    u32  block-table offset
```

The block-table offset is relative to the beginning of the `KZB1` payload.

#### `KZB1` block descriptor

Each descriptor is 16 bytes.

```text
Offset Size Type Description
00     4    u32  packed-data offset
04     4    u32  packed size
08     4    u32  unpacked size
0C     4    u32  CRC32 of unpacked block
```

Blocks represent consecutive portions of the uncompressed resource. Their uncompressed sizes must add up exactly to `resource.unpacked_size`.

Each block is an independent forward ZX0 stream. ZX0 history must not cross a block boundary.

Recommended unpacked block size for the MSX player:

```text
16,384 bytes
```

The final block may be smaller.

### 7.3 Slab-compressed indexed page-block pool

A `PBLK` resource stores deduplicated, fixed-size logical blocks that may be fetched independently and in arbitrary order while reconstructing runtime pages.

Logical blocks are not compressed independently by default. They are placed inside one or more independently compressed slabs. This preserves compression matches between nearby blocks while keeping the maximum decode size bounded for MSX.

A `PBLK` resource entry must use:

```text
resource.type        = "PBLK"
resource.compression = KSP_COMPRESSION_NONE
resource.flags       may include KSP_RESOURCE_REQUIRED
resource.aux0        = 0
resource.aux1        = 0
```

For `PBLK`, the resource table fields have these meanings:

```text
packed_size    physical size of the complete PBK1 container
unpacked_size  block_count × block_size
crc32          CRC32 of all logical blocks concatenated in block-index order
```

Unlike an ordinary uncompressed resource, `packed_size` is not required to equal `unpacked_size`.

The physical payload uses `PBK1`.

#### `PBK1` header

```text
Offset Size Type Description
00     4         "PBK1"
04     2    u16  header size, 32
06     2    u16  logical-block descriptor size, 8
08     2    u16  slab descriptor size, 16
0A     2    u16  fixed logical block size
0C     4    u32  logical block count
10     2    u16  slab count
12     2    u16  pool flags, zero
14     4    u32  logical-block table offset
18     4    u32  slab table offset
1C     4         reserved, zero
```

Offsets are relative to the beginning of the `PBK1` payload.

`block_size` must be nonzero and must not exceed the owning implementation's page size.

Recommended logical block sizes:

```text
64 bytes   aggressive deduplication; map overhead may dominate
128 bytes  high deduplication
256 bytes  balanced default
512 bytes  fewer map records and lookups
```

Packers should test several block sizes. Players must not assume one fixed block size.

#### `PBK1` logical-block descriptor

Each descriptor is 8 bytes.

```text
Offset Size Type Description
00     2    u16  slab index
02     2    u16  source offset inside uncompressed slab
04     4         reserved, zero
```

Every descriptor must satisfy:

```text
slab_index < slab_count
source_offset + block_size <= slab.unpacked_size
```

Several logical block indices may intentionally reference the same slab range. This permits both logical and physical deduplication.

#### `PBK1` slab descriptor

Each descriptor is 16 bytes.

```text
Offset Size Type Description
00     4    u32  packed-data offset relative to PBK1 start
04     4    u32  packed size
08     2    u16  unpacked size
0A     1    u8   compression: NONE or ZX0
0B     1    u8   slab flags, zero
0C     4    u32  CRC32 of uncompressed slab
```

Every slab is an independent object. ZX0 history may cross logical block boundaries inside one slab but must not cross a slab boundary.

For the MSX-DOS2 profile:

```text
1 <= slab.unpacked_size <= 16,384
```

When compression is `NONE`, packed size must equal unpacked size. When compression is `ZX0`, decoding must produce exactly the declared slab size.

Physical slab ranges may be identical. Slabs may contain bytes not referenced by any logical block when this produces a smaller compressed package or simplifies source-bank grouping.

Recommended slab sizes:

```text
4 KiB   low latency and small scratch use
8 KiB   balanced
16 KiB  best general compression on MSX with one mapper segment
```

A reader may validate the complete pool CRC incrementally in logical block-index order, but page playback does not require decoding unused slabs. The final reconstructed-page CRC detects errors in slabs actually used by a page.

#### Slab ordering and clustering

The packer should place blocks used together by the same pages into the same slab. It should also test preserving original source order when blocks originate from a continuous bank or stream.

The objective is measured complete-file size, not merely the fewest slabs or unique blocks.

A good clustering pass should consider:

- page co-occurrence;
- original source adjacency;
- repeated engine/table regions;
- dynamic page-switch locality;
- map-record count;
- packed slab size;
- the number of slab decodes needed per page.

#### Pool construction rules

A packer should:

1. reconstruct every candidate runtime page;
2. select candidate logical block sizes;
3. split reusable page regions into logical blocks;
4. deduplicate identical logical blocks globally;
5. cluster unique blocks into candidate slabs no larger than the target scratch limit;
6. compress each slab independently;
7. generate one `PBM1` map per pooled page;
8. compare total package size against sparse-overlay, complete-page, and resource-map alternatives;
9. retain the smallest representation;
10. verify every resulting runtime page byte-for-byte.

The size comparison must include:

- `PBK1` header;
- logical-block descriptors;
- slab descriptors;
- compressed slabs;
- every `PBM1` map;
- page-table and resource-table entries;
- padding and alignment actually emitted.

Do not choose pooling merely because the raw number of unique blocks is lower.

### 7.4 Page-source resources and random range access

A resource referenced by `KSP_PAGE_RESOURCE_MAP` must have `KSP_RESOURCE_PAGE_SOURCE` set.

Allowed compression modes are:

```text
NONE
    The player reads only the requested byte range directly from the file.

ZX0
    The player decodes the complete resource before copying a requested range.
    Under the MSX profile, the complete uncompressed resource must fit the available decode buffer.

ZX0_BLOCKS
    The player locates and decodes only the KZB1 blocks intersecting the requested range.
    A range may cross block boundaries.
```

For an MSX-targeted package, a page-source resource must use `ZX0_BLOCKS` when the complete uncompressed resource cannot fit the available decode buffer or cannot be retained without displacing required runtime allocations. Each block must fit the available scratch buffer and must not exceed 16 KiB under the baseline profile.

A whole-resource `ZX0` stream is valid only when the complete resource can be decoded safely before the requested range is copied. The total size of the `.KSP` file and the sum of mapper RAM plus VRAM are not sufficient tests by themselves.

The packer should preserve long continuous source ranges where possible. A complete original 8 KiB or 16 KiB music bank should normally be one `ZX0` object. A larger source stream should use 8 KiB or 16 KiB `KZB1` blocks unless it is covered by an explicitly supported direct-to-final-destination decoder.

A page-source resource may also be used as a runtime bank (`BNK8` or `BN16`). The `PAGE_SOURCE` flag does not change its bank semantics.


### 7.5 Hybrid mapper-RAM/VRAM preload pool

An `HPOL` resource stores one deduplicated fixed-size block pool divided into three physical tiers:

```text
hot    preloaded into mapper RAM
warm   preloaded into VRAM
cold   retained on disk as independently compressed slabs
```

Global block IDs are ordered as hot blocks, then warm blocks, then cold blocks.

KSP 1.01 permits at most one `HPOL` resource. It is package-wide and is addressed implicitly by `KSP_PAGE_HYBRID_POOL` pages.

An `HPOL` resource entry must use:

```text
resource.type        = "HPOL"
resource.flags       = KSP_RESOURCE_REQUIRED | KSP_RESOURCE_PAGE_SOURCE
resource.compression = KSP_COMPRESSION_NONE
resource.aux0        = declared hot-tier mapper-RAM capacity in bytes
resource.aux1        = declared warm-tier VRAM capacity in bytes
```

The resource fields have these meanings:

```text
packed_size    physical size of the complete HPL1 container
unpacked_size  canonical logical size:
               positions table + raw map matrix + hot bytes + warm bytes + cold bytes
crc32          CRC32 of that canonical logical concatenation
aux0           must be >= hot_raw_size
aux1           must be >= warm_raw_size
```

For the baseline 128 KiB mapper / 128 KiB VRAM profile, recommended capacities are:

```text
aux0 = 49,152 bytes   48 KiB mapper-RAM hot tier
aux1 = 98,304 bytes   96 KiB VRAM warm tier after one 32 KiB SCREEN 5 page
```

Smaller actual tiers are valid. A player may reject the package before playback when the declared capacities exceed available hardware.

The physical payload uses `HPL1`.

#### `HPL1` header

The header is 96 bytes.

```text
Offset Size Type Description
00     4         "HPL1"
04     2    u16  header size, 96
06     2    u16  HPL1 version, 1
08     2    u16  fixed logical block size
0A     2    u16  destination-position count
0C     2    u16  global page count
0E     2    u16  hot block count
10     2    u16  warm block count
12     2    u16  cold block count
14     2    u16  cold slab count
16     2    u16  HPL1 flags
18     4    u32  destination-position table offset
1C     4    u32  compressed map-stream offset
20     4    u32  compressed map-stream size
24     4    u32  raw map-matrix size
28     4    u32  hot ZX0 stream offset
2C     4    u32  hot packed size
30     4    u32  hot raw size
34     4    u32  warm ZX0 stream offset
38     4    u32  warm packed size
3C     4    u32  warm raw size
40     4    u32  cold-slab table offset
44     4    u32  cold-slab data-area offset
48     4    u32  total packed cold-slab bytes
4C     4    u32  total raw cold-tier size
50     4    u32  CRC32 of hot raw bytes
54     4    u32  CRC32 of warm raw bytes
58     4    u32  CRC32 of cold raw bytes in slab order
5C     4    u32  CRC32 of raw map matrix
```

All offsets are relative to the beginning of the `HPL1` payload.

The following equalities are mandatory:

```text
hot_raw_size  = hot_block_count  × block_size
warm_raw_size = warm_block_count × block_size
cold_raw_size = cold_block_count × block_size
map_raw_size  = page_count × position_count × 2
HPL1.page_count = KSP.header.page_count
```

HPL1 flags:

```text
bit 0  KSP_HPL_WARM_ZX0_QUICK_OFFSET
       The warm stream was compressed with a maximum match offset of 2,176 bytes.
       A player may use a history ring of at least 2,176 bytes instead of the standard 32,640-byte history.

bits 1–15 reserved, zero
```

When bit 0 is clear, the warm stream may use the standard ZX0 maximum offset of 32,640 bytes.

`block_size` must be nonzero. Every destination block must fit inside its owning engine's runtime page.

#### Destination-position table

The table contains `position_count` little-endian `u16` page offsets.

Positions must be strictly increasing and non-overlapping:

```text
position[i] + block_size <= position[i + 1]
position[last] + block_size <= engine.page_size
```

A hybrid package therefore uses one common destination layout for all hybrid pages. Pages belonging to engines with incompatible layouts must use another page encoding or a separately repacked KSP.

#### Compressed map matrix

The raw map matrix contains one little-endian `u16` global block ID for each destination position of each global page:

```text
row offset = global_page_index × position_count × 2
```

Rows are stored in global page-index order. The complete matrix is one forward ZX0 stream. When `map_raw_size` is zero, packed size must also be zero; otherwise the stream must decode to exactly `map_raw_size` bytes.

Every block ID must be smaller than:

```text
hot_block_count + warm_block_count + cold_block_count
```

A player may decode the complete map matrix into mapper RAM or may implement a mapper-spanning decoder. The baseline packs keep this matrix small enough to reside outside the active engine page.

#### Hot tier

The hot tier is one forward ZX0 stream containing all hot blocks concatenated in global block-ID order.

It is decompressed once into mapper RAM and remains resident while the package is open. Its output may span several 16 KiB mapper segments. The decoder must switch destination segments without resetting ZX0 history. It may resolve backreferences through mapped output segments or use a separate history ring large enough for the compressor's maximum encoded offset.

When `hot_raw_size` is zero, hot offset and packed size may be zero.

#### Warm tier

The warm tier is one forward ZX0 stream containing all warm blocks concatenated in global block-ID order.

It is decompressed once into VRAM and remains resident while the package is open. Because normal ZX0 backreferences require previously produced bytes, a VRAM-output decoder must keep sufficient decoded history in addressable RAM and write each output byte both to that history and to VRAM.

When `KSP_HPL_WARM_ZX0_QUICK_OFFSET` is clear, the history must retain at least 32,640 bytes; a 32 KiB circular buffer is sufficient. When the flag is set, a history of at least 2,176 bytes is sufficient.

The warm stream must not require reading prior bytes back from VRAM during decompression. A packer setting the quick-offset flag must enforce the 2,176-byte maximum during compression.

When `warm_raw_size` is zero, warm offset and packed size may be zero.

#### Cold-slab descriptor

Each cold-slab descriptor is 16 bytes.

```text
Offset Size Type Description
00     4    u32  packed-data offset relative to HPL1 start
04     4    u32  packed size
08     2    u16  unpacked size
0A     1    u8   compression: NONE or ZX0
0B     1    u8   slab flags, zero
0C     4    u32  CRC32 of uncompressed slab
```

Cold slabs contain consecutive cold blocks in global block-ID order. Each slab must satisfy:

```text
1 <= unpacked_size <= 16,384
unpacked_size mod block_size = 0
```

The sum of cold-slab unpacked sizes must equal `cold_raw_size`. The sum of packed sizes must equal `cold_packed_total`.

Cold slabs are decoded on demand into one normal RAM scratch segment. ZX0 history must not cross a cold-slab boundary.

#### Global block resolution

For a global block ID `b`:

```text
0 <= b < hot_count
    mapper-RAM offset = b × block_size

hot_count <= b < hot_count + warm_count
    VRAM offset = (b - hot_count) × block_size

otherwise
    cold ordinal = b - hot_count - warm_count
    locate the cold slab containing that ordinal by cumulative slab block counts
```

The physical placement of hot and warm tiers is chosen by the player. `HPL1` offsets are file offsets inside the resource, not runtime RAM or VRAM addresses.

#### Hybrid packer rules

A packer should:

1. reconstruct all candidate pages byte-for-byte;
2. determine one common set of destination positions and fixed block size;
3. deduplicate block values globally;
4. rank or cluster blocks using measured usage frequency, page co-occurrence, and original source locality;
5. select hot and warm tiers within the declared target capacities;
6. place remaining blocks in source-local cold slabs no larger than 16 KiB;
7. rewrite every page row to global hot/warm/cold block IDs;
8. compress the map matrix, hot stream, warm stream, and cold slabs;
9. compare complete-file size and expected page-load cost against PBLK and resource-map alternatives;
10. validate every reconstructed page and every nonzero CRC.

Frequency ranking is useful for a fully resident pool such as Solid Snake. Preserving source locality may produce much smaller hot, warm, and cold streams for large sequential material such as Xak: The Tower of the Gazell.

For engines that request pages during playback, the packer should keep all latency-critical blocks in hot or warm tiers or provide a prefetch plan. A cold-slab read during a synchronous page request may introduce an audible pause.

### 7.6 Defined resource types

#### `MWK `

MoonSound sample kit. The FourCC includes a trailing space.

```text
resource.type          = "MWK "
resource.compression   = NONE, ZX0, or ZX0_BLOCKS
resource.unpacked_size = complete original MWK size
resource.crc32         = CRC32 of the complete uncompressed MWK
```

The standard MoonSound YRW801 ROM is assumed and is not included or referenced.

For `ZX0_BLOCKS`, the MSX player decodes one `KZB1` block at a time and preserves MWK parser state across block boundaries.

#### `META`

UTF-8 metadata using LF-separated:

```text
key=value
```

Recommended keys:

```text
title
title.ja
game
game.ja
system
publisher
developer
composer
arranger
year
copyright
notes
track.<n>.title.<language>
```

`album` and `disc_number` are not defined KSP metadata keys.

#### `IMG5`

MSX SCREEN 5 image.

After resource decompression, the payload is:

```text
Offset Size Description
00     4    "I5V1"
04     2    width in pixels
06     2    height in pixels
08     2    stride in bytes
0A     1    palette entries: 0 or 16
0B     1    image flags, currently zero
0C     4    pixel-data size
10     n    packed SCREEN 5 pixels
...         optional palette
```

Pixel format:

- two pixels per byte;
- high nibble is the left pixel;
- low nibble is the right pixel;
- `pixel_size = stride × height`.

When present, the palette contains 16 entries of:

```text
u8 red    0–7
u8 green  0–7
u8 blue   0–7
```

A 128×106 image is the normal quarter-area presentation image. A 256×212 image may be used as a full-screen cover.

The initial MSX UI may support at most ten `IMG5` resources, although the file format itself has no ten-image limit.

#### `BNK8`

One 8 KiB engine bank.

```text
aux0 = engine index
aux1 = logical bank number
unpacked_size = 8192
```

#### `BN16`

One 16 KiB engine bank.

```text
aux0 = engine index
aux1 = logical bank number
unpacked_size = 16384
```

#### `DATA`

Generic shared source data.

```text
resource.type          = "DATA"
resource.compression   = NONE, ZX0, or ZX0_BLOCKS
resource.flags         may include REQUIRED, STREAMABLE, and PAGE_SOURCE
aux0                   = application-defined hint, normally zero
aux1                   = application-defined hint, normally zero
```

`DATA` has no game-specific interpretation. Typical contents are original music banks, continuous song-data streams, relocation tables, waveform collections, or other immutable bytes used by `KSP_PAGE_RESOURCE_MAP`.

A player that only needs the resource for page reconstruction treats it as an opaque logical byte array.

#### `PBLK`

Slab-compressed indexed page-block pool as defined in section 7.3.

It is consumed only through `KSP_PAGE_SHARED_BLOCK_MAP` pages. It is not an engine bank, must not have `KSP_RESOURCE_PAGE_SOURCE`, and must not be installed into the engine's logical bank table.

#### `HPOL`

Hybrid mapper-RAM/VRAM preload pool as defined in section 7.5.

It is consumed only through `KSP_PAGE_HYBRID_POOL` pages. It is package-wide, must be marked `REQUIRED | PAGE_SOURCE`, and must not be installed into the engine's logical bank table.

---

## 8. String table

The string table contains NUL-terminated UTF-8 strings.

All string offsets are relative to the start of the string table.

```text
0xFFFFFFFF = no string
```

A reader must verify that:

- the offset is smaller than `string_table_size`;
- a terminating NUL exists before the end of the string table.

The MSX player may initially display printable ASCII and replace unsupported UTF-8 characters. UTF-8 decoding is not required for playback.

---

## 9. File validation

A reader must reject a file when:

- the magic or major format is unsupported;
- a fixed entry size is smaller than the version 1 size;
- a reserved field or unknown mandatory flag is nonzero;
- `file_size` differs from the actual file size;
- any table, string, map, descriptor, block, or payload range exceeds the file;
- a count multiplication or offset addition overflows;
- a track references an invalid page;
- a page references an invalid engine;
- an engine page range is invalid;
- a page's engine does not match its declared owner;
- a string is unterminated;
- decompression does not produce the declared output size;
- a sparse-overlay record is zero-length, unordered, overlapping, or outside its page;
- a template does not produce exactly one engine page;
- a complete page does not produce exactly one engine page;
- a shared-block map has invalid magic, dimensions, resource index, records, or reserved fields;
- a shared-block page references a resource that is not `PBLK`;
- a `PBM1` record is zero-length, unordered, overlapping, outside its page, or outside its logical source block;
- a `PBLK` resource uses a nonzero resource compression ID or has `PAGE_SOURCE` set;
- a `PBK1` header, logical-block table, slab table, slab range, compression ID, or logical size is invalid;
- a logical block lies outside its referenced uncompressed slab;
- a slab does not decode to exactly its declared unpacked size;
- an MSX-profile slab exceeds 16 KiB;
- `PBLK.unpacked_size != block_count × block_size`;
- a resource map has invalid magic, dimensions, records, inline-data ranges, or reserved fields;
- an `RMP1` record is zero-length, unordered, overlapping, outside its page, or has an unknown record type;
- an `RMP1` resource copy references an invalid resource, a resource without `PAGE_SOURCE`, or a source range outside the logical resource;
- an `RMP1` inline copy lies outside the uncompressed map payload;
- an `RMP1` fill record has nonzero upper fill-value bytes;
- a page-source resource cannot provide the requested range using its declared compression/container;
- more than one `HPOL` resource exists;
- a hybrid page exists without exactly one valid `HPOL` resource;
- a hybrid page has nonzero flags, payload compression, payload offset, or payload sizes;
- an `HPOL` resource is not marked `REQUIRED | PAGE_SOURCE`, uses a nonzero resource compression ID, or has invalid auxiliary capacities;
- an `HPL1` header, version, flags, offset, count, size, or CRC is invalid;
- `HPL1.page_count` differs from the KSP global page count;
- the map-matrix size differs from `page_count × position_count × 2`;
- a destination position is unordered, overlapping, or outside an owning engine page;
- a map row contains an out-of-range global block ID;
- hot, warm, or cold raw size differs from its block count times block size;
- a hot or warm ZX0 stream does not decode to its declared raw size;
- a cold slab is empty, exceeds 16 KiB, is not block-aligned, has an invalid range or compression ID, or fails CRC;
- cold-slab raw and packed totals do not match the HPL1 header;
- required MWK or bank resources are missing;
- a `KZB1` descriptor is invalid;
- block unpacked sizes do not add up to the resource size;
- a nonzero final-page, resource, template, pool, or block CRC does not match.

C implementations must use at least 64-bit arithmetic for bounds calculations.

Readers must not map packed C structures directly onto file bytes. Use explicit little-endian read functions.

Payload ranges may be identical to permit deduplication. Readers must not assume every table entry or descriptor owns a unique physical range.

---

## 10. MSX-DOS2 implementation profile

The initial MSX-DOS2 implementation supports:

```text
maximum public tracks   65,535
maximum pages           65,535
maximum engines         65,535
maximum resources       65,535
track indices           16-bit
page indices            16-bit
engine song IDs         16-bit
file offsets            24-bit internally
maximum KSP file size   less than 16 MiB
engine page address     0x4000
engine page size        0x4000
```

Supported compression and page construction:

```text
Engine template             NONE or ZX0
Sparse page overlay         NONE or ZX0
Complete page               NONE or ZX0
Shared PBM1 page map        NONE or ZX0
Resource RMP1 page map      NONE or ZX0
Hybrid HPL1 map matrix      one whole ZX0 stream
Hybrid hot pool             one mapper-spanning ZX0 stream
Hybrid warm pool            one VRAM-output ZX0 stream with RAM history
Hybrid cold slab            NONE or ZX0, independently per slab
PBLK slab                   NONE or ZX0, independently per slab
Page-source resource        NONE, ZX0, or ZX0_BLOCKS
MWK resource                NONE, ZX0, or ZX0_BLOCKS
Metadata                    NONE or ZX0
SCREEN 5 image              NONE or ZX0
Bank resource               NONE or ZX0
```

A `ZX0_BLOCKS` block, `PBLK` slab, hybrid cold slab, resource-map payload, page payload, or template stream must fit in the available scratch area after decompression. Under the initial MSX profile, no ordinary independently decoded object may exceed 16 KiB.

For the baseline 128 KiB mapper-RAM / 128 KiB VRAM target, one whole-object `ZX0` stream is permitted only when its complete output either fits the available bounded decode buffer or is decoded directly into a fully allocated final destination while all simultaneous player, engine, bank, display, cache, and hardware allocations remain valid. Otherwise the resource must use `ZX0_BLOCKS` or a format-defined slab container.

The only size-limit exceptions are the `HPL1` map, hot, and warm whole streams. They are explicitly designed for mapper-spanning or VRAM-output decoding and must never be decoded into one ordinary 16 KiB buffer. Their feasibility is determined from the complete staged memory layout, not merely from total installed RAM and VRAM.

Recommended runtime memory:

```text
page 0   DOS/BIOS and file I/O helper
page 1   active engine page
page 2   SCC hardware during playback;
         temporary scratch RAM during materialization
page 3   resident KSP player, state, and stack
```

Minimum mapper allocation:

- one segment for the active engine page;
- one segment for page reconstruction or the VRAM ZX0 history ring;
- cache/staging segments required by DOS file access;
- declared BNK8/BN16 segments;
- any engine-specific work segment already required by its driver.

For the baseline hybrid profile on a machine with a 128 KiB mapper and 128 KiB VRAM, the recommended resident allocation is:

```text
48 KiB  hot pool in three mapper segments
96 KiB  warm pool in VRAM when one 32 KiB SCREEN 5 page is reserved
16 KiB  active engine page
32 KiB  temporary ZX0 history in two segments during hot/warm preload
16 KiB  active engine page after preload
16 KiB  reconstruction scratch after preload
```

The two 16 KiB history segments are temporary: after hot and warm preload completes, they may be reused for the active engine page and reconstruction scratch. This staged allocation keeps the baseline profile feasible on a 128 KiB mapper.

A package may declare smaller hot and warm requirements. Screenshots beyond the active SCREEN 5 page remain compressed in the KSP and are loaded into the same display page on demand.

A pooled or resource-mapped page can be reconstructed with:

- one complete page buffer;
- one slab or sequential-resource-block decode buffer;
- one small `PBM1`/`RMP1` map buffer or streamed map reader.

The player does not need to load the complete `PBLK` pool or complete large page-source resource.

For `HPOL`, the player preloads the complete hot and warm tiers once. The cold tier remains on disk and is decoded by slab only when referenced. The player must preserve the hot mapper segments and warm VRAM allocation while the package remains open.

For faster dynamic page switching, the implementation may cache recently used uncompressed slabs or source-resource blocks in extra mapper segments. Cache contents are an optimization and must not affect correctness.

Page 2 must be restored to the selected SCC cartridge slot before interrupts are enabled or PLAY is called.

---

## 11. Required changes to `src/kspplayer.c`

### 11.1 Remove old formats

Delete the runtime distinction between:

- compact `KSP1`;
- `KCPX`;
- `KCPZ`;
- normal KSS fallback inside the KSP parser.

A `.KSP` file is recognized only by `KSP1` at file offset zero.

There must be no KCPZ-v3, KCPZ-v4, or separate hybrid-profile runtime branch. Shared and hybrid pools are ordinary KSP 1.01 resources and page encodings.

### 11.2 Unified runtime structure

Replace old KCP-specific structures with one unified runtime structure containing:

```c
typedef struct KSPRuntime {
    uint8_t *file_data;
    size_t file_size;

    KSPHeader header;
    KSPEngine *engines;
    KSPPage *pages;
    KSPTrack *tracks;
    KSPResource *resources;

    uint16_t current_track;
    uint16_t current_engine;
    uint16_t current_page;

    uint8_t *template_buffer;
    uint8_t *page_buffer;
    uint8_t *decode_buffer;
    uint8_t *page_map_buffer;

    KSPSlabCacheEntry *slab_cache;
    size_t slab_cache_count;

    KSPResourceBlockCacheEntry *resource_cache;
    size_t resource_cache_count;

    KSPHybridPool hybrid_pool;
    uint8_t *hybrid_map_matrix;
    KSPSlabCacheEntry hybrid_cold_cache;

    uint16_t mailbox_page;
    uint8_t mailbox_low_valid;
    int applying_page;
    int failed;

    KSSPLAY *player;
} KSPRuntime;
```

Do not store all reconstructed pages as `page_count × page_size`.

Materialize pages on demand into preallocated buffers.

The memory-write callback must not perform file I/O or allocate memory. A desktop implementation may queue the request and service it at the existing safe audio-slice boundary.

### 11.3 Parser and decoder API

Use one parser API:

```c
int ksp_parse_file(...);
int ksp_validate(...);
int ksp_decode_object(...);
int ksp_decode_block_resource(...);
int ksp_open_page_pool(...);
int ksp_decode_pool_slab(...);
int ksp_get_pool_block(...);
int ksp_apply_pool_map(...);
int ksp_read_resource_range(...);
int ksp_apply_resource_map(...);
int ksp_open_hybrid_pool(...);
int ksp_preload_hybrid_hot(...);
int ksp_preload_hybrid_warm(...);
int ksp_get_hybrid_block(...);
int ksp_apply_hybrid_page(...);
int ksp_materialize_page(...);
int ksp_install_track(...);
int ksp_install_dynamic_page(...);
const char *ksp_get_string(...);
const KSPResource *ksp_get_resource(...);
```

`ksp_open_page_pool()` must validate `PBLK` and `PBK1` metadata without decompressing every slab.

`ksp_decode_pool_slab()` must:

1. validate the slab index;
2. locate and validate its descriptor and physical range;
3. decode `NONE` or ZX0 into the slab buffer;
4. require exactly the declared slab output size;
5. validate a nonzero slab CRC;
6. optionally cache the result.

`ksp_get_pool_block()` must:

1. validate the logical block index;
2. resolve its slab and source offset;
3. decode or retrieve the slab;
4. return a pointer/range of exactly `block_size` logical bytes.

`ksp_read_resource_range()` must support `NONE`, whole-object `ZX0`, and `ZX0_BLOCKS`, including ranges crossing sequential block boundaries.

`ksp_open_hybrid_pool()` must locate the single `HPOL` resource, validate `HPL1`, decode or map the complete map matrix, and prepare hot/warm/cold block resolution. Desktop implementations may keep hot and warm bytes in normal host memory while preserving the same logical tier behavior.

### 11.4 Page materialization

`ksp_materialize_page()` must:

1. find the owning engine;
2. select the page encoding;
3. create the correct base page;
4. decode and apply the page payload;
5. validate the final-page CRC when present;
6. leave exactly one reconstructed runtime page in `page_buffer`.

Encoding-specific behavior:

```text
SPARSE_OVERLAY:
    Decode the engine template.
    Decode and apply sparse records.

COMPLETE:
    Decode the page payload directly into page_buffer.

SHARED_BLOCK_MAP:
    Decode the engine template, or clear page_buffer when BASE_ZERO is set.
    Decode the PBM1 map.
    Open the referenced PBLK resource.
    For each PBM1 record:
        resolve the logical block to a slab;
        decode or retrieve that slab;
        copy the requested logical-block slice to the page destination.

RESOURCE_MAP:
    Decode the engine template, or clear page_buffer when BASE_ZERO is set.
    Decode the RMP1 map.
    For each record:
        copy the requested resource range, inline bytes, or fill value.
        Decode only the source-resource blocks intersecting the range when possible.

HYBRID_POOL:
    Decode the engine template.
    Select the map row by global page index.
    For each common destination position:
        resolve the global block ID to hot RAM, warm VRAM, or a cold slab;
        copy exactly one complete block to the page.
```

The implementation should retain the last decoded slab or page-source block and may use a larger LRU cache.

### 11.5 Desktop gateway

Install at `0xD8A0`:

```text
LD (0xD89E),HL
RET
```

The memory-write callback must:

1. save the low byte written to `0xD89E`;
2. trigger after the high byte is written to `0xD89F`;
3. form the 16-bit engine-local page;
4. validate it against the current engine;
5. materialize the requested page, including pooled and hybrid pages;
6. copy only `replace_start..page_end` into emulated memory.

Remove the current one-byte page mailbox and all `uint8_t` track/page limitations.

### 11.6 Track loading

For a public track:

1. resolve the track;
2. resolve its page and engine;
3. call the previous engine's STOP when needed;
4. configure required hardware;
5. load bank resources;
6. resolve and upload the track MWK or engine-default MWK;
7. materialize the complete initial page;
8. install the gateway;
9. call/reset INIT using the engine song ID;
10. start PLAY at the engine tick frequency.

When the selected track uses another engine, recreate or reconfigure the synthetic KSS/libkss runtime with the new INIT, PLAY, STOP, and hardware properties.

### 11.7 Packer requirements

The KSP packer must expose a deterministic optimization pass.

Before selecting a resource compression method, it must construct the declared target memory plan and record whether each normal resource is eligible for whole-object `ZX0` or requires `ZX0_BLOCKS`. The decision must account for simultaneous allocations, final destination, scratch requirements, and playback access pattern. Complete `.KSP` file size is not the deciding factor.

For every engine page, it must consider:

- sparse overlay against the selected engine template;
- complete-page ZX0;
- shared-block map using candidate logical block sizes, slab sizes, and slab clusterings;
- resource-range map using available or derived shared source resources, with inline/fill patches where useful;
- hybrid preload pool using candidate block sizes, common position sets, hot/warm capacity splits, tier orderings, and cold-slab groupings.

The packer may create:

- one package-wide `PBLK` resource;
- one `PBLK` resource per engine;
- several pools grouped by page similarity, logical block size, or slab locality;
- package-wide or engine-local `DATA` page-source resources;
- `BNK8`/`BN16` resources that are also marked as page sources;
- at most one package-wide `HPOL` resource.

It must not create a new pool when the complete file becomes larger.

The packer must emit a report containing at least:

```text
original page count
unique reconstructed page count
candidate logical pool-block sizes
candidate slab sizes and clustering methods
unique block and slab count per candidate
pool header/table bytes
pool compressed slab bytes
all PBM1 map bytes
resource-map source resources and compression
whole-object versus block-compression eligibility per resource
peak simultaneous mapper-RAM, VRAM, and scratch usage for the target profile
all RMP1 map/inline bytes
hybrid block size and common destination count
hot/warm/cold raw and packed bytes
hybrid map-matrix packed bytes
hybrid tier-selection strategy and reference-hit counts
selected encoding per page
total size for every candidate representation
byte-identical page validation result
```

### 11.8 User interface

- `--song` accepts `0..65534`, subject to `track_count`.
- Next/previous uses the track table, not KSS `trk_min/trk_max`.
- Hidden tracks are skipped during normal navigation.
- `--info` lists package metadata, engines, tracks, hardware, and page encodings.
- `--info` should report PBLK resource count, logical block size, block count, slab count/sizes, page-source resources, HPOL hot/warm/cold sizes and capacities, and cache usage.
- Track titles come directly from the string table.
- `--mwk` remains an explicit override.
- OPL4 automatically assumes the standard YRW801 ROM when required.

---

## 12. Required changes to the MSX assembly player

Relevant files:

```text
msx/KSPDOS2.asm
msx/KSPPLAYER.asm
msx/PLAYER_LAYOUT.inc
msx/KSPMWK.asm
```

Add one shared format include:

```text
msx/KSPFORMAT.inc
```

It must contain all:

- structure offsets;
- entry sizes;
- page encodings;
- page flags;
- compression IDs;
- resource FourCC constants;
- `PBM1`, `RMP1`, `PBK1`, `KZB1`, and `HPL1` constants.

Equivalent C definitions should be generated from, or tested against, the same values.

### 12.1 `KSPDOS2.asm`

Replace existing KSS/KCP/KSP probing with:

1. read the first 80 bytes;
2. require `KSP1`;
3. validate header and entry sizes;
4. validate the 24-bit MSX file-size limit;
5. read the requested 16-bit track entry;
6. read its page entry;
7. read the owning engine entry;
8. allocate required mapper segments;
9. keep the file open for direct absolute reads;
10. hand parsed descriptors to the resident player.

Remove:

- `input_format`;
- `kcp_file`;
- `probe_kcp_header`;
- `probe_compact_ksp_file`;
- KSS header parsing;
- fixed offsets such as `0x21`, `0x131`, and `0x235`;
- 8-bit song/page variables.

The command line must parse a 16-bit public track number.

Do not stage the complete KSP unless it is very small. Read templates, pages, pool descriptors, slabs, HPOL tiers, page-source ranges, banks, strings, and resources by absolute offsets.

### 12.2 `PLAYER_LAYOUT.inc`

Make this include the only source of truth for resident-player addresses.

The handoff block should contain:

- handoff magic and version;
- DOS file handle;
- 24-bit file size;
- selected 16-bit track;
- cached 80-byte KSP header;
- cached 64-byte engine entry;
- cached 24-byte page entry;
- cached 32-byte track entry;
- cached 32-byte PBLK resource entry when needed;
- cached 32-byte PBK1 header when needed;
- cached 16-byte slab descriptor when needed;
- cached 32-byte page-source resource entry when needed;
- cached 32-byte HPOL resource entry when needed;
- cached 96-byte HPL1 header when needed;
- hot mapper segment list;
- warm VRAM base and size;
- map-matrix location;
- cold-slab cache descriptor;
- mapper segment IDs;
- PUT_P0, PUT_P1, and PUT_P2 addresses;
- safe stack top;
- SCC slot configuration;
- direct file-read helper address.

Add assembler assertions proving that:

- the resident player remains within page 3;
- the gateway is exactly at `0xD8A0`;
- the mailbox area remains available;
- the stack cannot overlap static player state;
- the PBM1/RMP1/HPL1 and slab/resource-block scratch regions cannot overlap the resident code.

### 12.3 `KSPPLAYER.asm`

Initial track installation:

1. load or clear the page base;
2. decode and apply the selected page encoding;
3. copy the complete page into the active page-1 mapper segment;
4. load required banks;
5. upload the selected MWK;
6. install or update runtime addresses;
7. call INIT;
8. begin PLAY.

Shared-block page materialization:

1. read and validate the `PBM1` header;
2. read the referenced `PBLK` resource entry;
3. read and validate its `PBK1` header;
4. process each map record;
5. resolve the logical block descriptor to a slab and source offset;
6. decode or reuse the requested slab;
7. copy only the requested logical-block slice;
8. continue until every record is applied;
9. validate final page CRC when enabled.

Resource-map page materialization:

1. read and validate the `RMP1` header and record table;
2. establish the template or zero base;
3. for each `COPY_RESOURCE` record, validate `PAGE_SOURCE` and the logical range;
4. read directly for `NONE`, decode the whole object for bounded `ZX0`, or decode only intersecting `KZB1` blocks;
5. apply inline and fill records without allocating another resource;
6. support source ranges crossing sequential compression blocks;
7. validate final page CRC when enabled.


Hybrid-page initialization and materialization:

1. locate and validate the package-wide `HPOL` resource and `HPL1` header;
2. allocate the declared hot-tier mapper segments;
3. reserve the declared warm-tier VRAM range without overlapping the active SCREEN 5 page;
4. decode the complete map matrix;
5. decode the hot ZX0 stream across mapper segments without resetting history;
6. decode the warm ZX0 stream through a 32 KiB circular history buffer, or a smaller buffer when the quick-offset flag permits it, while writing output to VRAM;
7. on page materialization, copy the engine template;
8. select the global page row from the map matrix;
9. copy hot blocks directly, warm blocks through the VDP data port, and cold blocks from the on-demand slab cache;
10. validate final page CRC when enabled.

The hot and warm streams are preloaded once per opened package, not once per track. Cold slabs remain file-backed.

Dynamic page-switch gateway at `0xD8A0`:

1. receive engine-local page in `HL`;
2. preserve ABI-required registers;
3. reject an out-of-range page;
4. calculate the global page index;
5. read its page descriptor;
6. temporarily map scratch RAM into page 2;
7. materialize the requested page using any valid page encoding;
8. copy only the engine's replace range into the active page;
9. restore the SCC cartridge to page 2;
10. restore registers and interrupt state;
11. return with carry clear.

Never enable interrupts while page 2 still contains scratch RAM.

Public next/previous track changes must call STOP and perform a complete track installation. Internal engine page switches must not call STOP or INIT.

### 12.4 Slab, page-source, and hybrid-tier cache

The minimum implementation may use one 16 KiB decode buffer and retain metadata for the most recently decoded object.

Recommended pool lookup:

```text
resolve logical block -> slab index + source offset
if requested pool resource and slab index equal cached values:
    reuse decoded slab
else:
    read slab descriptor
    seek and decode slab
    replace cache entry
```

Recommended `ZX0_BLOCKS` page-source lookup:

```text
identify every sequential block intersecting the requested source range
reuse the cached resource block when possible
otherwise seek, decode, and cache the required block
copy only the intersecting bytes
```

Recommended hybrid lookup:

```text
if block ID is hot:  copy from resident mapper segment
if block ID is warm: copy from resident VRAM
if block ID is cold: locate and reuse/decode the containing cold slab
```

An enhanced implementation may allocate additional mapper segments as an LRU cache.

Cache keys are:

```text
PBLK slab:             resource table index + slab index
page-source KZB1 block: resource table index + sequential block index
whole ZX0 source:      resource table index
hybrid cold slab:       HPOL resource index + cold slab index
```

The cache must be invalidated when:

- the file closes;
- a decode error occurs;
- mapper segments are released.

Changing tracks or engines does not require invalidating immutable package-wide slabs, source blocks, or preloaded HPOL hot/warm tiers.

### 12.5 `KSPMWK.asm`

Replace old KDIR/SONG/MWK lookup with direct resource-table descriptors.

MWK selection order:

1. command-line override, when available;
2. track MWK resource;
3. engine-default MWK resource;
4. fail when `MWK_REQUIRED` is set;
5. otherwise continue without MWK.

Implement:

```text
NONE
    Read and process the resource sequentially.

ZX0
    Decode the complete resource only when the target memory plan provides a
    safe complete destination without displacing required runtime allocations.

ZX0_BLOCKS
    Decode and process one independent KZB1 block at a time when whole-resource
    decoding is not feasible or when bounded sequential processing is preferred.
```

For the baseline 128 KiB mapper-RAM / 128 KiB VRAM target, the packer must emit `ZX0_BLOCKS` for an MWK that cannot be decoded and retained safely as one object. The player must not infer feasibility from total installed memory alone.

Persistent MWK parser state must survive block boundaries.

Do not look for or declare a YRW801 ROM file.

### 12.6 Banked data

When `BANKED_DATA` is set:

1. locate every `BNK8` or `BN16` resource for the engine;
2. validate its logical bank number;
3. allocate mapper segments;
4. decode each bank into its segment;
5. populate the runtime logical-to-physical bank table;
6. reject missing or duplicate logical banks.

`PBLK` and `HPOL` resources are page-construction resources and must never be inserted into this bank table. A `BNK8` or `BN16` resource may also carry `KSP_RESOURCE_PAGE_SOURCE` and be referenced by resource maps.

### 12.7 Track navigation

The MSX player menu and command-line parser must use 16-bit decimal conversion.

Next and previous operations must perform 16-bit arithmetic and skip hidden tracks without truncating indices.

Track-title lookup must use at least 24-bit arithmetic on MSX and checked 64-bit arithmetic in C.

---

## 13. Non-negotiable implementation rules

The implementation must not:

- inspect filenames to identify an engine;
- contain game IDs or game-specific switch statements;
- use `KCPX`, `KCPZ`, or old trailer parsing;
- introduce KCPZ-v3 or KCPZ-v4 as public formats;
- assume fewer than 256 tracks or pages;
- store a track or page number in an 8-bit variable;
- load every reconstructed page into desktop memory;
- load the complete `PBLK` pool merely to play one page;
- treat `HPOL` as merely another per-page decompression method; its physical hot/warm/cold tier layout is part of the format;
- require the complete HPOL cold tier to fit in resident RAM or VRAM;
- reset ZX0 history at a mapper-segment boundary within a hot stream;
- decode a standard-offset warm ZX0 stream with less than 32,640 bytes of addressable history;
- set the quick-offset flag when the warm stream contains a match offset above 2,176 bytes;
- read ZX0 history back from VRAM while decoding a warm stream;
- compress every small logical pool block independently when slab grouping would be smaller;
- load a complete large page-source resource when it cannot fit the declared target memory plan and `ZX0_BLOCKS` permits bounded range access;
- choose whole-object `ZX0` solely because total mapper RAM plus VRAM exceeds the resource size;
- assume a particular PBLK block size;
- assume one PBLK pool per file or one pool per engine;
- permit more than one HPOL resource in a KSP 1.01 file;
- treat a PBLK logical block index as a physical file or slab offset;
- assume that one resource-map range stays within one sequential compression block;
- stage the whole file on MSX by default;
- reject block-compressed MWK resources;
- require the complete MWK in CPU RAM;
- parse file structures with native packed C structs;
- overwrite page 3 engine/player state;
- leave scratch RAM mapped over an SCC cartridge;
- reference an external YRW801 ROM from KSP metadata.

---

## 14. Acceptance tests

The implementation is complete when these packages work:

1. one uncompressed engine, one page, one track;
2. ZX0 template plus sparse ZX0 page;
3. complete-page encoding;
4. shared-block page over an engine template;
5. shared-block page over a zero base;
6. one PBLK pool shared by several pages;
7. one PBLK pool shared by two engines;
8. two PBLK resources with different logical block sizes;
9. PBLK slabs compressed with NONE;
10. PBLK slabs compressed independently with ZX0;
11. several logical blocks inside one slab;
12. one logical block referenced by several pages;
13. two logical block indices referencing the same slab range;
14. a PBM1 record copying only part of a logical block;
15. pooled-page reconstruction using only one 16 KiB slab buffer;
16. clustered slabs smaller than independently compressed logical blocks;
17. final pooled pages byte-identical to source pages;
18. resource-map page over an engine template;
19. resource-map page over a zero base;
20. RMP1 copying from a NONE page-source resource;
21. RMP1 copying from a bounded whole-object ZX0 page source;
22. RMP1 copying from a ZX0_BLOCKS page source;
23. one resource range crossing a KZB1 block boundary;
24. RMP1 inline literal patches;
25. RMP1 fill records;
26. a BNK8 or BN16 resource also used as a page source;
27. several tracks sharing one source bank with different range maps;
28. resource-map package smaller than equivalent block-pool and overlay packages;
29. packer declines pooling or resource mapping when either increases total size;
30. a package containing 256 tracks;
31. a package containing at least 1,000 tracks;
32. selection of tracks 255, 256, 511, and 999;
33. next/previous navigation across track 255/256;
34. hidden-track skipping above track 255;
35. at least 260 engine pages;
36. a dynamic request for a pooled page above 255;
37. a dynamic request for a resource-mapped page above 255;
38. two engines in one package;
39. tracks sharing one page but using different song IDs;
40. track-specific and engine-default MWKs;
41. an MWK larger than 64 KiB;
42. an MWK containing multiple independently compressed ZX0 blocks;
43. an MWK field crossing a compressed-block boundary;
44. an MWK sample crossing a compressed-block boundary;
45. successful MWK upload using only one 16 KiB scratch segment;
46. banked 8 KiB and 16 KiB engines;
47. PSG, SCC, SCC+, dual SCC, and OPL4 hardware flags;
48. one HPOL package with hot and warm tiers and no cold tier;
49. one HPOL package with hot, warm, and cold tiers;
50. an HPOL package with empty hot or warm tier;
51. mapper-spanning hot ZX0 decompression;
52. VRAM-output warm ZX0 decompression using a 32 KiB history ring for a standard-offset stream;
53. VRAM-output warm ZX0 decompression using the quick-offset flag and a reduced history ring;
54. rejection of a quick-offset stream containing an offset above 2,176 bytes;
55. hybrid map rows selected above global page 255;
56. hot, warm, and cold block references in one reconstructed page;
57. cold-slab cache reuse across tracks;
58. hybrid pages byte-identical to source pages;
59. packer chooses source locality instead of frequency when it produces a smaller HPL1;
60. player rejects an HPOL package exceeding declared/available RAM or VRAM capacity;
61. SCREEN 5 display remains active while the warm tier occupies remaining VRAM;
62. metadata with translated titles;
63. SCREEN 5 image resources;
64. unknown optional resources skipped safely;
65. unknown required resources rejected;
66. corrupt offsets, sizes, overlays, maps, slab descriptors, source ranges, HPOL tiers, blocks, and CRCs rejected;
67. Escape releases hot mapper segments and restores VRAM, mapper, SCC, OPL4, and DOS state;
68. next/previous skips hidden tracks;
69. no code path depends on a game title or variant number;
70. one sequential resource that fits the baseline target memory plan and is stored as one ZX0 stream;
71. the same logical resource enlarged beyond the safe memory plan and stored as ZX0_BLOCKS;
72. packer reports peak simultaneous mapper-RAM, VRAM, and scratch use for both cases.

---

## 15. Reference optimization targets

These are informative targets, not normative file-format requirements.

A shared-block implementation should be able to represent cases such as:

```text
Solid Snake SCC:
    current complete-page/overlay package: approximately 75 KiB
    shared full-page data pool:            approximately 55 KiB
    slab-compressed logical block pool:    target approximately 46–55 KiB
    original-bank resource mapping:        plausible target approximately 35–45 KiB
    hybrid RAM/VRAM preload pool:           measured approximately 49 KiB

Xak: Tower of the Gazell:
    independently compressed pages:        approximately 360 KiB
    unrestricted shared music pool:        approximately 160 KiB
    hybrid RAM/VRAM/cold pool:             measured approximately 172 KiB
```

Exact output depends on:

- selected engine template;
- logical block size;
- slab size and block ordering;
- source-bank/resource boundaries;
- PBM1/RMP1 map-record and inline-patch overhead;
- ZX0 optimizer;
- metadata size;
- whether physical compressed payload ranges are deduplicated;
- hybrid hot/warm capacities;
- frequency-ranked versus source-local tier ordering;
- cold-slab size and expected on-demand load count.

The packer must optimize measured complete-file size and validate reconstructed pages, rather than targeting these exact numbers. The packer should report decode cost as a secondary metric: number of slabs or source blocks required to materialize each page.
