# KSP1PLAY 0.18.6

- Package-menu movement now redraws only the previous/new rows while the selection remains visible.
- Scrolling the package list redraws only its 18-row pane, without clearing the title and footer.
- Live track changes no longer call the full player-screen renderer.
- Live movement within the current track window redraws only the prominent title and previous/new track rows.
- Crossing a playback window boundary redraws only the 13-row track pane.
- Added a regression model that rejects full-screen redraw calls in package navigation and live next/previous-track paths.
- Retains all KSP 1.01, HPOL, disk-backed, FMPAC mute, dual-SCC, MoonSound and 50/60 Hz functionality.
