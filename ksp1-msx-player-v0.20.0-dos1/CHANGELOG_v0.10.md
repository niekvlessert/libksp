# KSP1PLAY 0.10D

## Mapper allocation stack fix

The v0.9 trace stopped after `DBG 21`, before `DBG 22`. This isolates the hang to `ALL_SEG` while allocating the mapper segment used for the decompressed common template.

MSX-DOS2 requires the stack to be outside page 0 and page 2 when calling `ALL_SEG` or `FRE_SEG`. Earlier versions kept the player stack at `3FF0h` in page 0, which is invalid for those mapper calls and can hang the machine.

Version 0.10D:

- temporarily moves SP to `7FF0h` in the currently mapped page-1 RAM for every `ALL_SEG` and `FRE_SEG` call;
- restores the page-0 player stack immediately afterward;
- uses the wrapper for template and HPOL hot-segment allocation/freeing;
- adds `DBG 24` immediately before allocation and `DBG 25` after successful allocation.

Expected startup sequence for Nemesis 3:

```text
DBG 20
DBG A1
DBG A2
DBG A3
DBG A4
DBG 21
DBG 24
DBG 25
DBG 22
DBG 23
DBG 50
DBG 51
DBG 52
DBG 53
```
