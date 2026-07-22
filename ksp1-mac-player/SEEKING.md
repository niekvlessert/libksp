# Safe seeking

Version 1.0.4 adds deterministic seeking to the command-line player.

## Controls

| Key | Action |
|---|---|
| Up arrow or `]` | Forward 10 seconds |
| Down arrow or `[` | Backward 10 seconds |
| `}` | Forward 60 seconds |
| `{` | Backward 60 seconds |

The target is clamped between `00:00` and the configured track duration.

## Why seeking restarts the emulator

KSP engines can hold state in Z80 RAM, chip registers, SCC waveform RAM,
dynamic KSP pages, loop counters, and two independent SCC oscillators. Jumping
only a driver pointer would leave those states inconsistent.

The player therefore:

1. locks the SDL audio callback;
2. resets the selected track through `KSSPLAY_reset`;
3. resets SCC B and dual-SCC routing state;
4. restores the current channel masks;
5. renders and discards every PCM frame up to the target;
6. resumes normal audio at the reconstructed timestamp.

This is deterministic and preserves dynamic-page requests, register timing,
oscillator phase, and libkss filter history. Long seeks in dual-SCC tracks can
take a moment because both SCC outputs must be advanced sample by sample.
