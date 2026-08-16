TinyKSP standalone VM 1.9.9

This package contains a standalone KSP/KSS runtime written for this project. It
contains no libkss player layer. Selected libkss-derived chip cores and the bundled
libvgm backend retain their upstream licenses/notices.

The built-in Z80, PSG, SCC, YM2413, Y8950 and OPL4-compatible implementations
are compact project code. They are intended for portable KSP/KSS playback and are
not claimed to be cycle-exact hardware models.

KSP 1.05 shared physical payload views and localized metadata are defined by
KSP_FORMAT_SPEC_1.05.md. KSP 1.04 and KSP 1.03 remain separate strict
container/metadata grammars.

No YRW801 ROM is distributed. A user-supplied ROM is optional for standard
MoonSound ROM instruments. Embedded MWK custom samples work without it.

KSP package contents selected by the user remain subject to their own copyright
and licensing terms.

This build links libvgm's GPL-2.0 YMF278B implementation; see THIRD_PARTY_LIBVGM.md.
