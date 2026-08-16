# Third-party component: libvgm YMF278B

TinyKSP 1.9.5 uses the YMF278B wave/PCM implementation from the libvgm project:

- upstream: `ValleyBell/libvgm`
- source file: `emu/cores/ymf278b.c`
- implementation origin declared by upstream: openMSX
- upstream source license declaration: GPL-2.0

The YMF278B core models the 24-voice wave-table section. TinyKSP continues to
use its existing OPL3 implementation for the FM section and mirrors FM control
writes into libvgm to maintain YMF278B expansion/NEW2 state.

Keep the upstream license and copyright notices when distributing source or
binaries containing this integration.
