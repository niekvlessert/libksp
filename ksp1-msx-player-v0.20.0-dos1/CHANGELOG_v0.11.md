# KSP1PLAY 0.11

- Performs a complete PSG reset at every track change and on exit.
- Keeps PSG register 7 I/O direction bits in the MSX-safe `10xxxxxx` state.
- Clears the entire normal SCC register area `9800h-988Fh`, including waveform
  RAM, frequencies, volumes and channel enable state, before calling INIT.
- Retains the working mapper-call stack fix and VRAM/template cache.

This addresses tracks that inherited SCC waveforms or PSG mixer/envelope state
from the previously played track and only corrected themselves after a later
music event rewrote those registers.
