# KSP1PLAY 0.19.0

- Adds a complete package lifecycle reset after every cleanup.
- Keeps allocation ownership flags intact until their mapper segments are actually freed.
- Reasserts the original DOS2 page/slot mappings after the final mapper free.
- Clears stale hybrid, MoonSound, dynamic-page, cache and track state before opening another package.
- Waits for the triggering key to be physically released on package/menu transitions.
- Clears the BIOS keyboard buffer throughout the non-playing UI and before returning to DOS.
- Returns to BIOS-initialized 80-column SCREEN 0, with the standard system font and clean cursor state.
