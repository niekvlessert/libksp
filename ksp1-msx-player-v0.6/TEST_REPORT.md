# KSP1PLAY 0.6 test report

## Physical-MSX failure diagnosed

Version 0.5 displayed a large amount of garbage and then reported that the engine-template ZX0 decode failed.

The garbage and the decode failure had separate immediate causes:

- `print_u16` stored its output pointer in `DE`, then called `div10_u16`, which overwrote `DE` with the divisor 10. The routine wrote the digit at address `0009h` and passed an invalid low-memory pointer and very large length to DOS `_WRITE`.
- `zx_read_bit` used `B` for the current bit mask. The streaming ZX0 decoder stores the current Elias-gamma value and literal/match length in `BC`, so each call could alter the value being decoded.

Both register-lifetime errors are fixed in 0.6.

## Regression validation

- Exact uploaded Nemesis 3 SHA-256: `853651dad2b3c0626623932eaed14e9e6d40aa96061ca4528af56718e3f842d3`.
- Nemesis 3: 24 sparse pages, all reconstructed page CRCs valid on the host.
- Chunked decoder model: template plus all 24 compressed overlays decoded through 512-byte input windows; 79 refills exercised.
- The model reproduces each final page byte-for-byte.
- Build-time source check rejects any `ld b,a` temporary inside `zx_read_bit`.
- Build-time source check requires `print_u16` to preserve `DE` around `div10_u16`.
- Page 3 remains untouched.

## Remaining runtime test

The physical MSX/openMSX run is still required to confirm audible SCC playback. Version 0.6 has not been claimed as hardware-tested.
