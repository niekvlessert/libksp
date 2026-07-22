# KSP1PLAY 0.18.4

- Fixed Screen 5 clearing. The old loop wrote the changing BC loop-counter value after the first byte instead of writing zero for every VRAM byte, which produced the multicoloured horizontal bars visible in menus and during track changes.
- Replaced the 32-column 8x8 UI renderer with a compact 64-column 4x6 font.
- Each text row uses an 8-pixel pitch: six glyph pixels followed by two clean blank scanlines, providing more space between rows.
- Lowercase ASCII is rendered with the matching compact uppercase glyph; punctuation and digits remain supported.
- Expanded UI line/string buffers to 64 characters.
- Expanded cached track-title rows from 32 to 48 visible characters while retaining all 15 selector rows.
- The playback screen now reuses the selector title cache instead of rereading and rebuilding the complete title pane after INIT.
- The selected track is shown prominently above the playback track list and remains visible after Enter.
- The playback list shows 13 nearby cached tracks and refreshes the cache only when the selection leaves the current 15-track window.
- Rebuilds a readable 8x8 Screen 0 font from the compact UI font before returning to MSX-DOS2.
- Retains KSP 1.01, PAGE2_RUNTIME, PAGE3_WORKRAM, sparse/HPOL, disk-backed loading, FMPAC disk mute, dual SCC, MoonSound and automatic 50/60 Hz functionality.
