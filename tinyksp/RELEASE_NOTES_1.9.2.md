# TinyKSP 1.9.2 release notes

## MoonSound PCM correction

TinyKSP 1.9.1 corrected the YMF278B wave/F-number bits in register `20h+n`, but
its ROM PCM decoder still reversed 12-bit and 16-bit formats and unpacked
12-bit data incorrectly. This produced the hard FM-radio-like hiss in Dawn of
Sorrow tracks that use YRW801 ROM instruments.

Version 1.9.2 fixes:

- YMF278B PCM formats: `00=8-bit`, `01=12-bit`, `10=16-bit`;
- exact three-byte/two-sample 12-bit nibble packing;
- MWK RAM wave placement at `384+tone` without ROM-wave aliases;
- KSP `PAGE3_WORKRAM` initialization to `FFh` immediately before INIT.

The existing register `20h+n`, KSP 1.05 shared-resource, FM-PAC rhythm and
KSP 1.00-1.05 functionality is retained.
