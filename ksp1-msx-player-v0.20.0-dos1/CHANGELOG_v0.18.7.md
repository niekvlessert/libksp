# KSP1PLAY 0.18.7

- Fixed the final trailing `?` after track titles containing CR, LF, or another control byte.
- The low-level Screen 5 text renderer now treats every byte below `20h` as end-of-line in every UI path.
- Extended-byte characters (`80h` and above) still use the fallback `?` glyph until UTF-8 rendering is added.
- Retains incremental package-menu and live track-change repainting from v0.18.6.
- Added a regression check that rejects any renderer path which converts control bytes to `?`.
