# KSP1PLAY v0.18.8

- Fixed a trailing `?` on every Screen 5 text line.
- The common renderer previously inserted a NUL after copied text, but the fixed-width 64-cell glyph pass rendered that NUL through the fallback question-mark glyph.
- The destination row is already space-padded, so the first cell after the string now remains a space.
- This fixes static UI labels, package filenames, track titles, metadata, controls, and empty-list rows without changing KSP data.
