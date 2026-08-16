# Dawn native ADPCM MWK revision 0E

Revision 0E retains the standard 13-byte MWK tone record. In this revision only,
format bits `11` identify a Nintendo Nitro IMA ADPCM source payload. The loader
decodes it at track load time into big-endian 16-bit YMF278B RAM PCM and writes
a normal 16-bit OPL4 wave header. Revisions 0C and 0D are unchanged.

This is a generic source-storage extension: playback after loading uses the
normal OPL4 engine and incurs no per-frame ADPCM cost.
