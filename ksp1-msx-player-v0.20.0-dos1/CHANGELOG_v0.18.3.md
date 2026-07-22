# KSP1PLAY 0.18.3

- Added a dedicated full-screen track selector after choosing a KSP package.
- Shows package filename, engine name, required hardware and `selected / total` track position above the list.
- Displays 15 track names at once with a highlighted `>` cursor.
- Up/Down select one track; Left/Right jump 15 tracks; Enter or Space starts playback.
- Escape closes the package and returns to the KSP package menu without starting audio.
- Reuses the package-menu filename buffer as a 15-row title cache while a KSP is open, avoiding repeated floppy reads when the cursor moves within the visible page.
- The playback screen keeps the nearby track list and now marks the active track with `>`.
- Retains the v0.18.2 FMPAC disk-I/O mute and all KSP 1.01, HPOL, dual-SCC and MoonSound functionality.
