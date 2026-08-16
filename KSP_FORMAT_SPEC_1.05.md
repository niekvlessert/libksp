# KSP Format and Player Implementation Specification

**Version:** 1.05  
**Extension:** `.KSP`  
**Byte order:** little-endian  
**Status:** backward-compatible minor revision of KSP 1.04

KSP 1.05 retains every KSP 1.04 engine, page, track, resource, compression,
`HVAR`, `HVR1`, and metadata structure unchanged. Version 1.05 formalizes safe
physical sharing of compressed payload ranges, including identical `KZB1` blocks
referenced by several ordinary resources.

This revision was designed for compact, track-selected MoonSound sample kits. It
does **not** introduce `MWS1`, a shared-MWK playback type, or any new player-side
sample-dictionary format. Each track still selects a normal `MWK ` resource.

This document is normative for the differences introduced by KSP 1.05. Every
KSP 1.04 rule not explicitly changed here remains mandatory.

## 1. Revision summary

```text
KSP 1.00  generic page reconstruction and shared-storage resources
KSP 1.01  declarative PAGE2_RUNTIME and PAGE3_WORKRAM engine profiles
KSP 1.02  HVAR/HVR1 hardware-dependent track implementations
KSP 1.03  standardized UTF-8 META key/value resource
KSP 1.04  localized META values and default-language declaration
KSP 1.05  shared physical payload views and cross-resource KZB1 block aliasing
```

KSP 1.05 does **not** replace or rename `HVAR`, `HVR1`, `META`, or `MWK `.

A strict KSP 1.05 file declares header minor version `5`.

A KSP 1.05 reader must accept minor versions `0`, `1`, `2`, `3`, `4`, and `5`,
subject to the rules of those versions. A strict KSP 1.04 reader may reject
minor version `5` before inspecting resources.

KSP 1.05 retains `metadata_version=2`; the metadata grammar is unchanged from
KSP 1.04.

A packer may emit a minor-version-4 compatibility copy when playback on
unmodified 1.04 readers is required. Such a copy must materialize every resource
that depends on KSP 1.05 overlapping payload views as an independent,
self-contained packed payload.

## 2. Container layout

The package layout is unchanged:

```text
80-byte KSP1 header
engine table
page table
track table
resource table
string table
compressed and uncompressed payloads
```

All offsets are absolute file offsets. Integers are unsigned little-endian
unless explicitly stated otherwise.

## 3. KSP header

The header remains 80 bytes.

```text
Offset Size Type Description
00     4         "KSP1"
04     2    u16  header size, 0x0050
06     2    u16  minor version: 0, 1, 2, 3, 4, or 5
08     4    u32  file flags, zero through KSP 1.05
0C     4    u32  complete file size

10     4    u32  engine-table offset
14     2    u16  engine count
16     2    u16  engine-entry size, at least 64

18     4    u32  page-table offset
1C     2    u16  page count
1E     2    u16  page-entry size, at least 24

20     4    u32  track-table offset
24     2    u16  physical track-table entry count
26     2    u16  track-entry size, at least 32

28     4    u32  resource-table offset
2C     2    u16  resource count
2E     2    u16  resource-entry size, at least 32

30     4    u32  string-table offset
34     4    u32  string-table size

38     2    u16  default logical/public track
3A     2    u16  package META resource index, or 0xFFFF
3C     2    u16  cover IMG5 resource index, or 0xFFFF
3E     2         reserved, zero

40     4    u32  header CRC32
44     4    u32  index CRC32
48     8         reserved, zero
```

CRC32 uses the IEEE polynomial `0xEDB88320`.

`header_crc32` covers the complete 80-byte header with the field at offset
`0x40` temporarily set to zero.

`index_crc32` covers the engine, page, track, resource, and string tables
concatenated in that order.

## 4. Resource entry

The resource entry remains unchanged from KSP 1.02.

```text
Offset Size Type Description
00     4         resource FourCC
04     2    u16  resource flags
06     1    u8   compression ID
07     1         reserved, zero
08     4    u32  payload offset
0C     4    u32  packed size
10     4    u32  logical unpacked size
14     4    u32  CRC32 of logical unpacked bytes
18     4    u32  auxiliary value 0
1C     4    u32  auxiliary value 1
```

The package-wide metadata resource has FourCC `META`. When the header field at
`0x3A` is not `0xFFFF`, it must reference a valid `META` entry. Resource entries
may participate in the shared physical payload rules in section 5.

## 5. Shared physical payload views — new in KSP 1.05

KSP 1.05 formalizes physical payload deduplication among otherwise ordinary KSP
objects. It introduces no new FourCC, track field, compression ID, engine flag,
or playback type. In particular, a MoonSound track continues to reference one
normal `MWK ` resource. A resource such as `MWS1` is not part of KSP 1.05.

The decoded logical content remains authoritative. Physical sharing changes only
how packed bytes are placed in the file.

### 5.1 Terminology

For this section:

- an **enclosing resource span** is
  `[resource.payload_offset, resource.payload_offset + resource.packed_size)`;
- a **control range** contains a container header or descriptor table;
- a **leaf range** contains bytes directly consumed by one decompressor or raw
  copy operation;
- an **exact alias** is two references with identical absolute start and end
  offsets.

An enclosing resource span is a readable view, not a claim of exclusive physical
ownership. Two enclosing spans may overlap partially. Every resource must still
validate independently.

### 5.2 General aliasing rules

1. All offset additions and range checks use at least 64-bit arithmetic.
2. `NONE` and whole-object `ZX0` resources consume their complete packed spans as
   one leaf range. Such resources may share storage only by exact full-range
   aliasing.
3. `ZX0_BLOCKS` resources consume only their `KZB1` header, block table, and the
   leaf ranges named by their block descriptors. Bytes in gaps between those
   ranges are not part of the logical resource and must be ignored.
4. A control range or leaf range must lie completely inside its resource's
   enclosing span.
5. Enclosing spans may overlap freely when each resource's semantic ranges remain
   independently valid.
6. Two semantic leaf ranges may overlap only when they are exact aliases. Partial
   leaf overlap is invalid.
7. Exact aliases must use compatible interpretations. For aliased `KZB1` blocks,
   packed size, unpacked size, compression method, and unpacked CRC32 must agree.
8. Control ranges may lie inside another resource's unused gap. Two control
   ranges may share storage only as an exact alias with identical structure and
   interpretation. A control range must not partially overlap a semantic leaf
   range.
9. Resource CRC32 remains the CRC of that resource's complete decoded logical
   bytes. Sharing does not replace or weaken per-resource or per-block CRCs.
10. A reader must not reject a file merely because enclosing resource spans
    overlap. It must validate semantic ranges instead.
11. A reader must not decompress in place into packed source bytes. Shared source
    bytes remain immutable until every referencing object has finished reading
    them.
12. A reader may cache a decoded alias using the complete tuple
    `(absolute_offset, packed_size, compression, unpacked_size, crc32)`. It must
    not cache by offset alone.

### 5.3 Shared `KZB1` block profile

A `ZX0_BLOCKS` resource still begins with its own ordinary `KZB1` header and
block table. Every block descriptor's `packed-data offset` remains relative to
the beginning of that resource's `KZB1` payload.

Block descriptors are ordered by **logical output order**, not by physical file
offset. Their physical offsets may move forward or backward and may point to an
exact compressed block range also referenced by another resource. A reader must
follow descriptor-table order and seek as necessary.

For a strict KSP 1.05 writer:

```text
minimum_packed_size = max(
    end of KZB1 header,
    end of KZB1 block table,
    end of every referenced compressed block
) - resource.payload_offset
```

The writer must store this minimum value in `resource.packed_size`. A reader may
accept a larger enclosing span for alignment or trailing padding, but it must not
interpret unreferenced bytes as part of the logical resource.

A shared block may be referenced by any number of normal resources. For example,
several track-specific `MWK ` resources may each contain unique MWK headers and
instrument records while referencing the same compressed waveform block. Each
MWK is decoded independently and remains a complete standard MWK.

A resource using non-monotonic or backward physical block references must not set
`KSP_RESOURCE_STREAMABLE`. The absence of that flag permits normal random-access
reads on disk or in memory.

### 5.4 Backward compatibility

KSP 1.05 changes no decoded data structure. A KSP 1.04 implementation that
already treats offsets as independent references and does not require exclusive
resource ownership may be technically capable of decoding the file, but it may
reject header minor version 5.

A strict KSP 1.04 compatibility copy must not depend on overlapping resource
views introduced by this section. Its packer must materialize each `KZB1`
resource as a self-contained physical container. This can increase file size but
must not change any decoded resource bytes or playback behavior.

## 6. Standardized META resource — retained from KSP 1.04

KSP 1.05 retains the KSP 1.04 `META` resource and metadata grammar
version 2 unchanged. Localization remains exactly as standardized in KSP 1.04.
Structural package and track fields remain authoritative.

### 6.1 Encoding

The logical uncompressed `META` payload is line-oriented UTF-8 text:

```text
key=value\n
```

Rules:

1. No UTF-8 byte-order mark is stored.
2. Lines use LF (`0x0A`). A writer must not emit CRLF.
3. The first `=` byte separates key and value.
4. An unlocalized key uses lowercase ASCII letters, digits, and underscores and
   must begin with a letter.
5. A localized key has the form `base.language-tag`, as specified in section
   6.3. A dot is otherwise forbidden in a key.
6. Values are UTF-8 and must not contain NUL, CR, or LF.
7. `=` is permitted inside a value after the first delimiter.
8. Empty lines are permitted and ignored.
9. Duplicate complete keys are not permitted. A base key and its localized
   forms are distinct complete keys.
10. Unknown syntactically valid keys must be ignored without rejecting the
    package.
11. Writers should terminate the final line with LF.

When a strict KSP 1.05 file contains a `META` resource, its payload must contain:

```text
metadata_version=2
```

A strict KSP 1.03 `META` payload continues to require
`metadata_version=1`; localized dotted keys are invalid in minor version 3.
A strict minor-version-4 or minor-version-5 file with a `META` resource
that declares metadata version 1 is invalid. A minor-version-5 file without a
`META` resource remains valid.

`META` may use `NONE` or one whole-object `ZX0` stream. `ZX0_BLOCKS` is not
recommended for package metadata because a conforming player needs the complete
small object to parse it. The recommended logical size is at most 16 KiB.

The resource entry's CRC covers the complete decoded UTF-8 payload.

### 6.2 Standard keys

All keys are optional except `metadata_version`. Header and table fields remain
authoritative when metadata duplicates structural information.

```text
metadata_version       metadata grammar version; "2" in KSP 1.04 and 1.05
default_language       language tag of unlocalized human-readable values

title                  package display title
game                   source game or work
composer               principal composer
additional_composer    additional composer credit
developer              original game/software developer
publisher              original publisher
release_year            four-digit original release year
original_release_date  ISO 8601 calendar date when known

source_platform        source platform description
source_format          source file/module format
source_hardware        original sound hardware
source_file            source filename without a path
source_sha256          lowercase 64-digit SHA-256 of the source file

target_platform        target playback platform
target_hardware        supported target hardware descriptions
hardware_variants      human-readable HVAR/HVR1 profile summary

track_count            number of visible logical tracks in decimal
track_metadata         statement identifying authoritative per-track fields

format                 human-readable KSP format/profile label
engine                 engine architecture
conversion             conversion method and important processing details
storage                shared-storage/compression description
converter              converter or packer name
converter_version      converter version
pack_version           package revision
conversion_date        ISO 8601 conversion date
conversion_notes       technical caveats or corrections

attribution            human-readable original-credit statement
copyright              human-readable rights notice
```

Recommended interpretation of `track_count`:

- without `HVAR`, it is the number of non-hidden public tracks;
- with `HVAR`, it is the number of visible logical tracks, not the number of
  hidden implementation records in the physical track table.

### 6.3 Localized values — retained from KSP 1.04

A localized key appends one dot and one lowercase language tag to a normal base
key:

```text
base.language-tag=value
```

The language tag uses this restricted lowercase ASCII profile:

```text
language-tag = primary *("-" subtag)
primary      = 2*8 lowercase-letter
subtag       = 1*8 (lowercase-letter / digit)
```

Examples:

```text
default_language=en
title=Parodius Da! From Myth to Laughter
title.ja=パロディウスだ! ～神話からお笑いへ～
game=Parodius Da!
game.ja=パロディウスだ!
title.pt-br=Parodius Da!
```

Normative rules:

1. The base part must independently be a valid unlocalized key.
2. Exactly one dot separates the base and language tag.
3. The complete key, including its language tag, participates in duplicate-key
   detection.
4. Language tags are stored lowercase. Readers compare them case-sensitively
   after callers normalize requested tags to lowercase.
5. `default_language`, when present, must itself contain a valid language tag.
6. Writers should include an unlocalized base value as the language-neutral or
   default fallback whenever a localized form is emitted.
7. Localized values are intended for human-readable text. Localized copies of
   structural or numeric fields such as `track_count.ja` do not override or
   participate in structural validation.
8. Unknown localized base keys are handled like other unknown keys: readers
   validate the syntax and may otherwise ignore them.

When a reader needs one display value for a requested language, it should use:

1. an exact localized key match;
2. progressively less-specific tags by removing the rightmost subtag;
3. the unlocalized base key;
4. another localized value in file order only when no base value exists.

For example, a request for `pt-br` tries `title.pt-br`, then `title.pt`, then
`title`.

A metadata information screen or API may expose all localized values rather
than selecting only one.

### 6.4 Per-track metadata

KSP 1.05 does not duplicate normal track metadata inside `META`.

The track table remains authoritative for:

```text
title
duration_ms
loop_start_ms
loop_end_ms
fade_ms
KSP_TRACK_SOUND_EFFECT
KSP_TRACK_ONE_SHOT
KSP_TRACK_NO_AUTO_ADVANCE
KSP_TRACK_HIDDEN
```

For an `HVAR` logical track, the KSP 1.02 logical/implementation inheritance
rules remain unchanged. The logical track provides presentation and navigation;
the chosen implementation provides playback page, engine song ID, and MWK.
Known implementation timing fields override the corresponding logical values.

KSP 1.05 does not define localized per-track titles. A future revision may add
that capability without changing the package-level localized-key grammar.

A package may use this metadata hint:

```text
track_metadata=track table: UTF-8 title, duration_ms, loop_start_ms, loop_end_ms, fade_ms, one-shot/hidden flags
```

## 7. HVAR/HVR1 — retained unchanged from KSP 1.02

`HVAR` is an optional package-wide resource. Its logical decoded payload uses
`HVR1` version 1.

Only one package-wide `HVAR` resource is permitted. Its resource entry may use
`NONE`, `ZX0`, or `ZX0_BLOCKS`, subject to the normal resource-decoding rules.

### 7.1 HVR1 header

The fixed header is 24 bytes.

```text
Offset Size Type Description
00     4         "HVR1"
04     2    u16  header size, 24
06     2    u16  HVR1 version, 1
08     2    u16  logical-record count
0A     2    u16  candidate count
0C     2    u16  logical-record size, 12
0E     2    u16  candidate-record size, 8
10     4    u32  logical-record table offset
14     4    u32  candidate table offset
```

Offsets are relative to the start of the decoded `HVR1` payload.

### 7.2 Logical record

Each logical record is 12 bytes.

```text
Offset Size Type Description
00     2    u16  logical/public track-table index
02     2    u16  first candidate-table index
04     2    u16  candidate count for this logical track
06     2    u16  flags, zero
08     4         reserved, zero
```

The logical track index must be in range and must not occur in more than one
logical record. Candidate ranges must be in bounds and must not overlap unless
a later specification explicitly permits it.

### 7.3 Candidate record

Each candidate is 8 bytes.

```text
Offset Size Type Description
00     2    u16  implementation track-table index
02     2    u16  quality rank; larger is preferred
04     2    u16  flags, zero
06     2         reserved, zero
```

The implementation track determines the page and therefore the engine and its
conjunctive required-hardware mask.

### 7.4 Candidate eligibility and selection

For each candidate:

```text
eligible =
    (engine.required_hardware & available_hardware)
    == engine.required_hardware
```

The player selects the eligible candidate with the highest quality rank. Equal
ranks are resolved by candidate-table order.

The player must not infer that SCC, SCC+, and dual SCC are interchangeable.
Each capability bit is set only when that interface is actually usable.

The logical track must occur exactly once in its own candidate list. This is the
fallback implementation and should normally be the lowest-common-denominator
hardware version. Higher-quality implementation tracks should normally use
`KSP_TRACK_HIDDEN`.

Selection is one level only. The selected implementation is not recursively
resolved through another `HVAR` logical record.

Structural corruption, CRC failure, or an invalid selected implementation is a
package error. A player must not hide corruption by silently trying a lower-rank
candidate.

### 7.5 Presentation versus implementation

The logical track supplies:

- public track number and menu identity;
- title;
- image;
- sound-effect, one-shot, and auto-advance behavior.

The selected implementation supplies:

- page and owning engine;
- engine-specific song ID;
- track MWK selection;
- known timing fields, with field-by-field fallback to the logical track.

Normal next/previous navigation skips hidden implementation tracks.

## 8. Hardware flags relevant to HVR1

The existing hardware flags remain unchanged:

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
```

Engine hardware flags are conjunctive. Alternatives belong in `HVAR/HVR1`, not
in a combined engine mask.

## 9. Reader algorithm

A KSP 1.05 reader should:

1. validate `KSP1`, header size, minor version, table sizes, bounds, and CRCs;
2. build semantic-range records for every payload-bearing entry and descriptor;
3. permit overlapping enclosing resource views, while rejecting invalid partial
   overlap between semantic control or leaf ranges according to section 5;
4. read the requested logical track;
5. detect/configure the actual available-hardware mask;
6. locate and decode the optional `HVAR` resource;
7. resolve one `HVR1` candidate when a logical record exists;
8. load only the selected implementation's engine, pages, banks, and resources;
9. for `ZX0_BLOCKS`, process descriptors in logical table order and seek to each
   referenced physical block range rather than assuming packed-offset order;
10. parse the package `META` resource when present using the grammar selected by
    the container minor version;
11. validate localized-key syntax and `default_language` for metadata version 2;
12. ignore unknown metadata keys;
13. use track-table timing and flags as authoritative;
14. expose package metadata through information screens or APIs without making
    playback depend on optional descriptive keys.

Metadata parsing must never be required for safe playback except for validating
a resource explicitly marked required. Physical sharing must likewise remain an
implementation detail: the decoded logical bytes and CRC checks are identical to
a non-deduplicated package.

## 10. Writer algorithm

A KSP 1.05 writer should:

1. emit minor version `5`;
2. preserve all KSP 1.04 table, metadata, page, and payload rules;
3. emit at most one package `HVAR` resource;
4. emit deterministic logical and candidate ordering;
5. include the logical fallback exactly once per candidate list;
6. emit a package `META` resource referenced by header field `meta_resource`;
7. begin metadata with `metadata_version=2`;
8. emit localized keys only according to section 6.3 and include an
   unlocalized fallback where practical;
9. avoid duplicating per-track timing and flags in `META`;
10. deduplicate eligible physical payloads by complete semantic leaf range, not
    by partially overlapping byte substrings;
11. for shared `KZB1` blocks, emit one canonical compressed stream and reference
    its absolute range from every applicable block descriptor;
12. set each `ZX0_BLOCKS` resource's `packed_size` to the minimum enclosing span
    required by its control structures and furthest referenced block;
13. keep the `STREAMABLE` flag clear when physical block order requires seeking;
14. recompute resource, index, header, block, and logical-object CRCs;
15. report the visible logical-track count separately from the physical
    track-table entry count.

A writer producing a KSP 1.04 compatibility copy must materialize every
`ZX0_BLOCKS` resource as a self-contained container that does not rely on
overlapping resource views. It may still use the ordinary KSP 1.04 metadata
grammar version 2.

## 11. C definitions

```c
#define KSP_MINOR_100 0
#define KSP_MINOR_101 1
#define KSP_MINOR_102 2
#define KSP_MINOR_103 3
#define KSP_MINOR_104 4
#define KSP_MINOR_105 5

#define KSP_RESOURCE_HVAR 0x52415648u /* "HVAR" little-endian */
#define KSP_RESOURCE_META 0x4154454Du /* "META" little-endian */

#pragma pack(push, 1)
typedef struct KSPHVR1Header {
    char     magic[4];
    uint16_t header_size;
    uint16_t version;
    uint16_t logical_count;
    uint16_t candidate_count;
    uint16_t logical_record_size;
    uint16_t candidate_record_size;
    uint32_t logical_table_offset;
    uint32_t candidate_table_offset;
} KSPHVR1Header;

typedef struct KSPHVR1Logical {
    uint16_t logical_track;
    uint16_t first_candidate;
    uint16_t candidate_count;
    uint16_t flags;
    uint32_t reserved;
} KSPHVR1Logical;

typedef struct KSPHVR1Candidate {
    uint16_t implementation_track;
    uint16_t quality_rank;
    uint16_t flags;
    uint16_t reserved;
} KSPHVR1Candidate;
#pragma pack(pop)
```

Readers must not cast untrusted file bytes directly to these structures without
bounds checks and little-endian conversion on non-little-endian hosts.

## 12. Required validation cases

A conforming implementation should test at least:

1. KSP 1.00, 1.01, 1.02, 1.03, and 1.04 files still parse under a 1.05 reader.
2. A strict minor-version-5 file with no `META` resource.
3. A strict minor-version-5 file with valid UTF-8 metadata version 2.
4. A minor-version-3 metadata-version-1 file still parses.
5. A minor-version-3 file with a localized dotted key is rejected.
6. A minor-version-4 or minor-version-5 file with `metadata_version=1` is
   rejected.
7. Exact, language-only, script, and region tags such as `ja`, `zh-hant`, and
   `pt-br` parse correctly.
8. Empty tags, uppercase tags, repeated dots, repeated hyphens, one-letter
   primary tags, and subtags longer than eight characters are rejected.
9. Duplicate base keys and duplicate complete localized keys are rejected, while
   a base key and distinct localized forms may coexist.
10. Invalid UTF-8, missing `=`, embedded NUL, BOM, and CRLF are rejected.
11. Unknown metadata keys and unknown localized base keys are ignored.
12. `default_language`, `source_sha256`, and decimal numeric fields are
    validated when interpreted.
13. `track_count` is compared with visible logical tracks as a warning, not a
    playback requirement.
14. Normal SCC, SCC+, and dual-SCC candidates select correctly.
15. Equal HVR1 ranks use candidate-table order.
16. No eligible candidate fails cleanly.
17. Hidden implementation tracks do not appear in normal navigation.
18. Direct selection of a hidden implementation plays it directly.
19. HVR1 logical/candidate indices above 255 work.
20. Header, index, resource, template, page, and block CRC failures are reported.
21. Metadata changes do not alter reconstructed engine or music pages.
22. Two complete `NONE` or `ZX0` resources may reference one exact physical
    range when their compression interpretation, logical size, and CRC agree.
23. Two `KZB1` descriptors in different resources may reference one identical
    physical ZX0 block range when packed size, unpacked size, and CRC agree.
24. Shared `KZB1` block descriptors may occur in different logical orders and
    at non-monotonic packed offsets.
25. Partially overlapping semantic leaf ranges are rejected.
26. Exact aliased block ranges with differing unpacked sizes or CRCs are
    rejected.
27. A KZB1 block outside its resource's enclosing packed span is rejected.
28. Overlapping resource spans containing only valid independent control ranges,
    gaps, and exact shared leaf ranges are accepted.
29. A reader does not decompress in place or overwrite bytes needed by another
    aliased resource.
30. A `STREAMABLE` resource whose descriptors require backward seeking is
    rejected or treated as non-streamable before playback.
31. Twenty-nine standard MoonSound `MWK ` resources can share compressed sample
    blocks without introducing another resource FourCC or track playback type.
32. Materializing every shared block into self-contained resource containers
    produces byte-identical logical MWKs and identical playback.

## 13. Shovel Knight KSP 1.04 profile under a 1.05 reader

The accompanying Shovel Knight package uses:

```text
51 visible logical tracks
153 physical track records
3 HVR1 candidates per logical track
priority 300: PSG + dual SCC
priority 200: PSG + SCC+
priority 100: PSG + normal SCC fallback
one shared compressed music payload
one package-wide META resource using metadata_version=2
optional package-title and game-title translations using localized keys
```

The localization addition does not modify the engine, pages, track timing, loop
points, DPCM data, or `HVR1` payload.

## 14. Castlevania: Dawn of Sorrow KSP 1.05 profile

The one-disk MoonSound package that motivated the KSP 1.05 clarification uses:

```text
29 visible sequenced tracks
Cross of the Blue Moon omitted because it is streamed audio
one shared native SSEQ-derived Z80 playback engine
29 ordinary track-selected MWK resources
58 retained custom DS sample waveforms
12 kHz, 8-bit custom PCM samples
maximum selected-track sample RAM below 128 KiB
standard YRW801 MoonSound ROM instruments for substituted sounds
KZB1 block compression for every MWK
shared physical KZB1 sample blocks across the 29 MWKs
no MWS1 resource and no nonstandard playback type
one package-wide META resource using metadata_version=2
```

Each track continues to reference a normal `MWK ` resource. The resource's
logical decoded bytes, parser behavior, sample ordering, CRC, and MoonSound RAM
image are exactly the same as in a fully materialized MWK. Only the physical
compressed block storage is deduplicated.

The standard YRW801 ROM is assumed by MoonSound hardware and is not embedded in
the package. Software players may require an external legally obtained
`yrw801.rom` image to emulate the built-in instrument ROM.
