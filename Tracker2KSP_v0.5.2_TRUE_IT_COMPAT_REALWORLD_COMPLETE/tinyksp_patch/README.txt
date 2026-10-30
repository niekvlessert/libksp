TinyKSP 1.9.9 OPL4 RAM-header cache fix
========================================

Tracker2KSP v0.4.0 can share one PCM payload between several custom OPL4 wave
headers. The KSP engine patches those RAM wave headers once during INIT.
Real MoonSound/OPL4 hardware reads the RAM headers normally and KSP1PLAY v0.48
needs no change.

TinyKSP 1.9.9 cached MWK headers when loading the resource, so runtime writes to
0x200000..0x2002FF were not reflected in its decoded header cache. Apply the
included patch to TinyKSP 1.9.9. A Linux x86_64 test binary built from that
single patch is included for convenience.
