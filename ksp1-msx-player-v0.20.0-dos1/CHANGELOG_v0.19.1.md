# KSP1PLAY 0.19.1

- Fixes the v0.19.0 menu/startup crash triggered by the first keyboard action.
- The live Screen 5/menu path no longer calls BIOS `KILBUF` through `CALSLT`.
- Keyboard buffering is cleared safely by setting BIOS `GETPNT` equal to `PUTPNT`.
- Retains the v0.19.0 package cleanup, mapper-segment release, key-release wait and 80-column Screen 0 exit behavior.
- Adds a regression check that forbids BIOS/slot calls from the live keyboard-flush routine.
