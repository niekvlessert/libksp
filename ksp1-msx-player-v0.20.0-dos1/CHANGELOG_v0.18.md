# KSP1PLAY 0.18

- Added full-screen Screen 5 startup menu using MSX-DOS2 Find First/Find Next.
- Running `KSP1PLAY` without arguments lists KSP files in the current directory.
- Added graphical playback screen with engine, hardware, refresh rate, package size, track/page counts and track titles.
- Added previous/next track controls and Escape-to-menu lifecycle.
- Retained direct command-line package launch.
- Moved the complete HPOL map matrix from page 0 into a dedicated mapper segment.
- Added 512-byte HPOL position and current-map-row caches below the stack.
- Kept dynamic-page and dual-SCC callback code resident and no longer overwritten by HPOL position tables.
- Restores a usable 40-column Screen 0 before returning to MSX-DOS2.
- Added GUI/HPOL memory-layout regression test and a multi-package menu test disk.
