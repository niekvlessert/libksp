# TinyKSP 1.9.3 release notes

## MoonSound PCM pitch correction

The YMF278B defines `FNUM=0, OCTAVE=1` as normal 44.1 kHz sample playback.
TinyKSP 1.9.2 used octave 0 as normal, so all OPL4 PCM voices played one octave
too high and one-shot percussion samples ended twice as quickly.

Version 1.9.3 corrects the playback step and adds a 32-sample waveform period
regression that distinguishes the correct pitch from the previous doubled rate.
All KSP 1.00-1.05, OPL4 PCM decoding, MWK, FM-PAC rhythm and other device paths
from 1.9.2 are retained.
