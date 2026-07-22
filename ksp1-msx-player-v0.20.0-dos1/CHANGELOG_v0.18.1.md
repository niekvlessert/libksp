# KSP1PLAY 0.18.1

- Merged the local KSP 1.01 player changes into the graphical v0.18 codebase.
- Accepts KSP minor versions 0 and 1 and rejects unsupported higher revisions.
- Added declarative `KSP_ENGINE_PAGE2_RUNTIME` support using a writable page-1/page-2 mapper alias.
- Added generic `KSP_ENGINE_PAGE3_WORKRAM` support using one optional persistent mapper segment.
- Maps private page 3 only around INIT, PLAY and STOP and restores DOS2 page 3 before DOS, BIOS or UI activity.
- Preserves the caller's private page-3 mapping across dynamic page callbacks.
- Rejects PAGE2_RUNTIME combined with SCC, SCC+ or dual-SCC hardware.
- Retains automatic 50/60 Hz switching, Screen 5 menu, dual SCC, MoonSound/MWK, HPOL and disk-backed loading.
- Retains the local HPOL 256/512-byte block fix and the strict 512-byte cache-bound check already present in v0.18.
- Updated validators and added a generated KSP 1.01 runtime-profile regression model.
- Added the KSP 1.01 specification while keeping the legacy 1.00 document.
- No game-specific runtime paths were added.
