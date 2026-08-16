# TinyKSP 1.9.8 Gazzel `$D84F` fix

## Problem

`KspVm::memWrite()` treated every write to RAM address `$D84F` as a legacy
SCC cartridge selector. This happened even when the active engine declared
only PSG + FM-PAC.

The original Gazzel music driver uses `$D84F` as ordinary private work RAM.
Discarding the zero written there left the rest of the driver state at `FFh`.
As a result, note changes omitted the YM2413 key-off writes and most envelopes
were only triggered once, then decayed to silence.

## Fix

The `$D84F` interception is now enabled only when the engine hardware mask
contains SCC, SCC+ or dual SCC. Existing SCC behavior is unchanged; non-SCC
engines receive normal RAM semantics.

## Validation

With GAZZEL KSP v0.5, track 7 produced 1,555 YM2413 register writes over the
first 200 PLAY calls. The entire sequence matched the same portable driver
running in openMSX byte-for-byte, including all key-off/key-on retriggers.
All 32 Gazzel tracks completed two-second renders with both PSG and FM-PAC
writes. The engine is scheduled at the original 50 Hz.
