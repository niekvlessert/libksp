# NOP policy

The active source currently contains **17 literal `nop` instructions**. The
longest consecutive run is five bytes.

Long zero-filled areas are represented as data/reservations (`db`/`ds`) rather
than executable instructions. A literal `nop` is kept only where it is part of
an executing/fixed instruction sequence and changing it would require a timing
or behavior decision.

Current groups:

- 5 after SCC/SCC+ slot scanning before the next hardware probes.
- 3 in HVAR after a VDP data-word write (VDP pacing).
- 3 at the start of next-track handoff before mapper/interrupt restoration.
- 3 at the start of previous-track handoff for the same transition class.
- 2 between YM2413 address and data port writes.
- 1 fixed initialization slot.
- 1 byte inside the fixed service/IMG5 tail image.

Do not replace an executing NOP with `ds` merely to reduce the count: `ds` is
appropriate for non-executed storage/padding, while these bytes are currently
part of instruction streams. If a timing path is intentionally redesigned,
re-evaluate the corresponding group and runtime-test it on Z80-class timing.
