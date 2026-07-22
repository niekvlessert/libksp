# KSP1 Mac Player 1.0.3

## Added

- live `MM:SS / MM:SS` playback position based on rendered audio frames;
- keys `1`-`5` toggle SCC A channels 1-5;
- keys `6`, `7`, `8`, `9`, `0` toggle SCC B channels 1-5;
- live status display with muted channels represented by `-`;
- unit tests for key mapping, SCC mute masks, and status rendering.

## Behavior

Channel muting affects only the generated audio. Both SCC emulators continue to
receive register updates, so re-enabling a channel resumes its current state.
SCC B keys have no effect when the current package uses only one SCC.

`--seconds 0` now follows the documented behavior and uses the track-duration
metadata rather than disabling the duration limit.
