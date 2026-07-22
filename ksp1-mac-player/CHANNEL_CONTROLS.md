# Playback clock and SCC channel controls

Version 1.0.3 adds interactive channel isolation to the command-line player.

## Keys

| Key | SCC | Channel |
|---|---|---:|
| `1` | A | 1 |
| `2` | A | 2 |
| `3` | A | 3 |
| `4` | A | 4 |
| `5` | A | 5 |
| `6` | B | 1 |
| `7` | B | 2 |
| `8` | B | 3 |
| `9` | B | 4 |
| `0` | B | 5 |

Pressing a key toggles the corresponding channel. The status line uses `-` for
a muted channel. SCC B keys are ignored for a single-SCC track.

## Implementation

The primary SCC uses `KSSPLAY_set_channel_mask`. The independently emulated
secondary SCC uses `SCC_setMask`. Both masks are changed while the SDL audio
device is locked, avoiding concurrent mutation during sample generation.

Only audio output is muted. The emulators continue to receive all waveform,
frequency, volume, and enable-register writes, so a channel can be restored
without restarting the track.

## Clock

Elapsed time is calculated from `rendered_frames / sample_rate`, not wall-clock
time. This keeps the display aligned with audio actually submitted by the SDL
callback. The display refreshes when the rendered whole-second value changes.
