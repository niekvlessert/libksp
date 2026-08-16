# TinyKSP 1.9.6

- Accepts compact MWK revisions 0E and 0F used by Nitro/DS ADPCM packs.
- Revision 0F decodes Nitro IMA ADPCM directly to packed 12-bit YMF278B PCM.
- Preserves the YMF278B stereo output.
- Uses DS-style sample-hold playback only for MWK 0E/0F, restoring the high-frequency character lost through OPL4 linear interpolation.
- Bypasses libvgm's internal approximately -15 dB PCM balancing attenuation only for MWK 0E/0F. Standard MWK 0C/0D and YRW801 playback remain unchanged.
