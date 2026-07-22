# Debug build 0.9D

- Adds deterministic two-digit startup checkpoints.
- Adds one checkpoint after every 8 KiB of the VRAM file preload.
- Moves fixed page-0 descriptors upward to make room for trace code.
- Leaves page 3 untouched.
- Does not claim to fix the v0.8 hang; it is intended to locate it precisely.
