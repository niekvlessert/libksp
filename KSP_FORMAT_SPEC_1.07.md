# KSP Format and Player Implementation Specification

**Version:** 1.07  
**Extension:** `.KSP`  
**Byte order:** little-endian  
**Status:** backward-compatible minor revision of KSP 1.06

KSP 1.07 retains all playback, engine, page, track, compression, `HVAR`,
`HVR1`, `META`, and shared-payload rules from KSP 1.06. Version 1.07 adds a
formal distinction between a package's **game logo** and its **gallery
screenshots**, without changing the SCREEN 5 pixel container.

The baseline structures that were not reprinted in the 1.03-1.05 revision
documents remain normative from KSP 1.01. This 1.07 document consolidates the
1.05 rules, the two 1.06 MSX profiles, and the new 1.07 presentation-resource
rules. No playback behavior is allowed to depend on optional presentation
resources.

## 1. Revision summary

```text
KSP 1.00  generic page reconstruction and shared-storage resources
KSP 1.01  declarative PAGE2_RUNTIME and PAGE3_WORKRAM engine profiles
KSP 1.02  HVAR/HVR1 hardware-dependent track implementations
KSP 1.03  standardized UTF-8 META key/value resource
KSP 1.04  localized META values and default-language declaration
KSP 1.05  shared physical payload views and cross-resource KZB1 block aliasing
KSP 1.06  direct materialized dynamic pages + declarative PAGE3 zero-init
KSP 1.07  separate LOG5 game logo and SCR5 gallery screenshot resources
```

A strict KSP 1.07 file declares header minor version `7`. A KSP 1.07 reader
must accept minor versions `0` through `7`, subject to the rules of those
versions. Readers may reject a later minor version before inspecting resources.

KSP 1.07 retains `metadata_version=2`; the metadata grammar is unchanged from
KSP 1.04. Presentation resources are optional and have no effect on INIT, PLAY,
STOP, hardware selection, timing, or track navigation.

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
06     2    u16  minor version: 0, 1, 2, 3, 4, 5, 6, or 7
08     4    u32  file flags, zero through KSP 1.07
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
3E     2    u16  primary LOG5 game-logo resource index, or 0xFFFF

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
key=value

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
A strict minor-version-4 through minor-version-7 file with a `META` resource
that declares metadata version 1 is invalid. A minor-version-7 file without a
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

A KSP 1.07 reader should:

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
14. honor KSP 1.06 direct-materialized page flag `0x0002` and PAGE3 zero-init
    engine flag bit 5 when those profiles are used;
15. validate the optional header `logo_resource` and `LOG5` payload;
16. discover `SCR5` resources by FourCC and order them by `aux0`;
17. expose package metadata and presentation resources through information
    screens or APIs without making playback depend on optional descriptive or
    visual data.

Metadata parsing must never be required for safe playback except for validating
a resource explicitly marked required. Physical sharing must likewise remain an
implementation detail: the decoded logical bytes and CRC checks are identical to
a non-deduplicated package.

## 10. Writer algorithm

A KSP 1.07 writer should:

1. emit minor version `7` when any 1.06/1.07 feature is used;
2. preserve all earlier table, metadata, page, payload, and playback semantics;
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
    track-table entry count;
16. emit direct materialized pages and PAGE3 zero-init only when the KSP 1.06
    profile requirements are met;
17. store the primary game logo as `LOG5` and write its index at header `0x3E`;
18. store gallery screenshots as `SCR5` with unique `aux0` order values;
19. keep cover `IMG5`, track `IMG5`, logo `LOG5`, and screenshot `SCR5` roles
    semantically separate.

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
#define KSP_MINOR_106 6
#define KSP_MINOR_107 7

#define KSP_RESOURCE_HVAR 0x52415648u /* "HVAR" little-endian */
#define KSP_RESOURCE_META 0x4154454Du /* "META" little-endian */
#define KSP_RESOURCE_LOG5 0x35474F4Cu /* "LOG5" little-endian */
#define KSP_RESOURCE_SCR5 0x35524353u /* "SCR5" little-endian */

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

1. KSP 1.00 through 1.06 files still parse under a KSP 1.07 reader.
2. A strict minor-version-7 file with no `META` or presentation resources.
3. A strict minor-version-7 file with valid UTF-8 metadata version 2.
4. A minor-version-3 metadata-version-1 file still parses.
5. A minor-version-3 file with a localized dotted key is rejected.
6. A minor-version-4 through minor-version-7 file with `metadata_version=1` is
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
33. A KSP 1.06 direct-materialized dynamic page is accepted only with the exact
    size/profile constraints and reconstructs to its declared CRC.
34. PAGE3 zero-init is rejected unless PAGE3_WORKRAM is also set.
35. A valid `logo_resource` at `0x3E` points to `LOG5` and decodes as `I5V1`.
36. `logo_resource` pointing to `IMG5`, `SCR5`, or an out-of-range index is
    rejected by a strict 1.07 validator.
37. Multiple `SCR5` resources with unique `aux0` values sort deterministically.
38. Duplicate `SCR5.aux0` values are rejected.
39. A package may contain a white-background `LOG5` and black-background `SCR5`
    or `IMG5` resources without any palette/background coupling.
40. Removing all optional `LOG5`/`SCR5` resources leaves playback behavior and
    reconstructed music pages unchanged.

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


## 15. KSP 1.06 MSX profiles retained by KSP 1.07

### 15.1 Direct materialized dynamic page

KSP 1.06 assigned page flag bit 1 (`0x0002`) to a direct materialized 16 KiB
dynamic page. The normal 24-byte page descriptor is retained and uses:

```text
encoding       = 0
page flags     |= 0x0002
compression    = 0
packed_size    = 0x4000
unpacked_size  = 0x4000
payload        = complete materialized runtime page
page_crc32     = CRC32 of that complete materialized page
```

For the constrained native MSX profile, `page_load_address=0x4000`,
`page_size=0x4000`, and `0x4000 < replace_start < 0x8000`. The bytes below
`replace_start` form the persistent engine prefix; the remaining bytes are the
replaceable dynamic region. Selected direct pages used by one physical track
should be stored contiguously so an MSX player can preload them into mapper
segments and switch mapper pages instead of decompressing during PLAY.

A packer must only set this flag after reconstructing and CRC-validating the
canonical page. The direct representation changes storage and callback latency,
not the logical music data or engine ABI.

### 15.2 PAGE3 zero initialization

KSP 1.06 assigned engine flag bit 5:

```text
bit 5  KSP_ENGINE_PAGE3_ZERO_INIT
```

The flag requires `KSP_ENGINE_PAGE3_WORKRAM` (bit 4). Before INIT, a native MSX
player allocates the private persistent page-3 mapper segment and initializes
`C000h-FFFEh` to `00h`; `FFFFh` is not overwritten. When bit 5 is clear, the
legacy PAGE3_WORKRAM initialization remains `FFh`. The private page persists
through INIT/PLAY/STOP and DOS/BIOS/UI code runs with the normal process page 3
restored.

## 16. KSP 1.07 presentation resources

### 16.1 Design goal

KSP versions through 1.06 had one generic `IMG5` image type, a package `cover`
pointer, and a per-track `IMG5` pointer. That was sufficient to store pictures
but did not tell a player whether an otherwise package-level image was the
**game logo** or a **gallery screenshot**. KSP 1.07 makes those roles explicit.

The roles are represented by FourCC, not inferred from filename, dimensions,
resource-table order, colors, or image contents:

```text
LOG5  primary game/logo presentation image
SCR5  gallery screenshot
IMG5  legacy generic image, cover image, or track presentation image
```

`LOG5`, `SCR5`, and `IMG5` all use the exact same decoded `I5V1` payload. This
keeps one SCREEN 5 decoder and one palette model.

### 16.2 Header logo pointer

Header bytes `0x3E-0x3F`, reserved through KSP 1.06, are assigned in KSP 1.07:

```text
0x3E  u16  primary LOG5 resource index, or 0xFFFF when absent
```

When not `0xFFFF`, the index must be within the resource table and must identify
a `LOG5` resource. A strict KSP 1.07 writer must write `0xFFFF` when no logo is
present.

The existing `cover_resource` field at `0x3C` remains unchanged and continues
to reference `IMG5`. A logo and a cover are therefore separate concepts. A
writer must not silently use the logo pointer as a cover pointer or vice versa.

### 16.3 `I5V1` decoded payload

All three SCREEN 5 presentation FourCCs decode to:

```text
Offset Size Description
00     4    "I5V1"
04     2    width in pixels
06     2    height in pixels
08     2    stride in bytes
0A     1    palette entries: 0 or 16
0B     1    image flags, currently zero
0C     4    pixel-data size
10     n    SCREEN 5 pixels, two pixels per byte
...         optional 16 x (3-byte) V9938 palette
```

The high nibble is the left pixel and the low nibble is the right pixel. Each
palette entry is three bytes `red, green, blue`, each in the range `0..7`.
`pixel-data size` must equal `stride * height`; stride must be large enough for
`width` pixels. Image flags remain zero in KSP 1.07. There is no transparency:
black, white, or any other logo background is stored as ordinary pixels. This
allows, for example, a white-backed publisher logo and a black-backed game logo
to coexist without a player-specific background rule.

The resource-table compression may be `NONE`, `ZX0`, or `ZX0_BLOCKS` according
to the ordinary resource rules. CRC32 is always over the complete decoded
`I5V1` payload.

### 16.4 `LOG5`

`LOG5` is package presentation data and is not tied to a track. Requirements:

```text
resource.type = "LOG5"
resource.aux0 = 0
resource.aux1 = 0
```

A package may contain at most one authoritative game logo, referenced by the
header `logo_resource` field. A player may display it on a game-information
screen, above a track list, or in another non-playback UI. Failure to decode an
optional logo must not change music playback.

Logo dimensions are intentionally not fixed. A compact crop such as roughly
150 pixels wide is recommended for the native MSX text/split-screen UI, while
desktop players may scale as appropriate.

### 16.5 `SCR5`

`SCR5` resources form an optional package-level screenshot gallery. They are
not per-track images. Requirements:

```text
resource.type = "SCR5"
resource.aux0 = zero-based gallery order
resource.aux1 = 0
```

Within one KSP 1.07 package, `SCR5.aux0` values must be unique. A reader sorts
screenshots by ascending `aux0`; resource-table order is not presentation order.
There is no format-level screenshot-count limit. A constrained MSX UI may expose
only the first ten screenshots, but must ignore additional screenshots safely.

Typical screenshots are 256x192 or 256x212, but other legal `I5V1` dimensions
are allowed. Each screenshot may carry its own 16-color palette.

### 16.6 Relationship to existing `IMG5` fields

The following older semantics remain valid:

- header `cover_resource` at `0x3C` references a generic/cover `IMG5`;
- track entry offset `0x08` references a track presentation `IMG5`;
- the logical track remains the source of the per-track image under HVAR/HVR1.

A 1.07 player must not treat `SCR5` resources as per-track images and must not
treat arbitrary `IMG5` resources as gallery screenshots. This removes the
ambiguity that existed when all pictures used only `IMG5`.

### 16.7 Reader behavior

A conforming KSP 1.07 reader that implements presentation data should:

1. validate the header `logo_resource` index;
2. if present, validate that it points to `LOG5`;
3. scan optional `SCR5` resources and validate unique `aux0` order values;
4. decode `LOG5`, `SCR5`, and `IMG5` through the same `I5V1` decoder;
5. keep presentation failures isolated from INIT/PLAY/STOP unless a resource is
   explicitly marked `REQUIRED`;
6. never infer a logo or screenshot role from filenames or pixels.

A reader that does not implement 1.07 presentation UI may ignore optional
`LOG5` and `SCR5` resources after normal structural validation.

### 16.8 Writer behavior

A strict KSP 1.07 writer should:

1. set header minor version to `7` when it emits `LOG5`, `SCR5`, or a non-FFFF
   `logo_resource`;
2. store the primary logo as `LOG5` and write its resource index at `0x3E`;
3. store gallery screenshots as `SCR5`, with consecutive `aux0` values starting
   at zero when practical;
4. leave the older cover field independent;
5. recompute resource, index, and header CRC32 values after adding images;
6. keep all image resources optional unless playback truly cannot proceed
   without them, which is strongly discouraged.

### 16.9 Nemesis 3 reference package

The first KSP 1.07 reference package uses the title-screen capture from
*Gofer no Yabou Episode 2 / Nemesis 3: The Eve of Destruction*. The publisher
Konami splash is not stored as the game logo. The following title screen is used
as the source; the `1 PLAYER / 2 PLAYERS` menu is excluded and only the title
logo plus subtitle are encoded. The resulting reference `LOG5` image is
150x69 pixels with its own 16-entry palette.

The reference package deliberately contains no `SCR5` entries yet. Gameplay
captures can therefore be added later without changing or reinterpreting the
logo resource.
