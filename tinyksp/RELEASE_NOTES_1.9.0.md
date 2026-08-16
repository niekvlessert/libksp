# TinyKSP 1.9.0 release notes

This tree is based on `TinyKSP-Standalone-CrossPlatform-v1.8.1_KSP104_MoonSound_source`.

## Applied FM-PAC rhythm patch

- Adds independent procedural YM2413 bass drum, snare, tom, cymbal and hi-hat voices.
- Uses rising edges in register `$0E` to trigger simultaneous rhythm bits.
- Preserves MoonSound/OPL4 and MWK support from 1.8.1.
- Verified with the Sonic 3 & Knuckles v2.2 dual-SCC + FM-PAC KSP:
  20 seconds, 1,200 PLAY calls, four dynamic page switches and 1,251 FM-PAC writes.

## KSP 1.05 reader support

- Accepts minor versions 0 through 5.
- Retains metadata grammar 2 and localized META behavior from KSP 1.04.
- Validates physical resource views using 64-bit range arithmetic.
- Accepts overlapping enclosing resource spans.
- Accepts exact compatible whole-resource and KZB1 block aliases.
- Follows KZB1 descriptor order even when physical block offsets are non-monotonic.
- Rejects partial leaf overlap, incompatible exact aliases, control/leaf overlap and
  STREAMABLE resources that require a backward seek.
- Does not decompress in place and does not cache shared data by offset alone.

## Regression coverage

- 29 ordinary MWK resources sharing one exact compressed sample block.
- First and last shared MWKs decoded by the OPL4 loader.
- Exact NONE aliases.
- Valid non-monotonic KZB1 descriptor ordering.
- Invalid partial overlap, incompatible alias, control/leaf overlap and
  backward-seeking STREAMABLE cases.
- GCC and Clang release builds.
- ASan/UBSan core parser, Z80, Yamaha and VM smoke tests.
- Windows frontend syntax check.
