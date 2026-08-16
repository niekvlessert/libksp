# TinyKSP 1.9.1 release notes

## MoonSound / OPL4 correction

YMF278B PCM register `20h + slot` is now decoded according to the hardware
layout:

- bit 0: wave-number bit 8;
- bits 1-7: F-number bits 0-6.

TinyKSP 1.9.0 inherited the earlier incorrect interpretation (bit 7 as wave bit
and bits 0-6 as F-number). That selected unrelated or empty samples and shifted
pitch data, producing hiss/modem-like MoonSound audio.

All KSP 1.05 shared-resource and FM-PAC rhythm functionality from 1.9.0 is
retained.
