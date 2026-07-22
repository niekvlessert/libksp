# KSP1PLAY v0.18.5

- Replaced the touching 4x6 font with a compact 3x5 font in a 4x8 cell.
- Added one blank pixel between characters and three blank scanlines between text baselines.
- Control bytes in KSP strings now terminate display text, fixing trailing `?` characters caused by CRLF-derived metadata.
- Track movement within the current window redraws only the old and new rows plus the selection counter.
- Track-window scrolling redraws only the title pane instead of clearing the complete Screen 5 page.
- Retains all v0.18.4 KSP 1.01, HPOL, MoonSound, dual-SCC, disk loading and FMPAC disk-mute behavior.
