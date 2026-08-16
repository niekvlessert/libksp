# Dawn 12-bit MWK revision 0F

Revision 0F uses the same compact source representation as revision 0E:
format bits `11` contain Nintendo Nitro IMA ADPCM. At load time the player
decodes each source sample, rounds it to signed 12-bit precision and writes it
in the YMF278B packed 12-bit layout (3 bytes per 2 samples).

The decoded A Fleeting Respite bank occupies 610,362 bytes of sample payload,
or 611,130 bytes including the 0x300-byte RAM wave-header area. It therefore
fits in a 640 KiB MoonSound RAM configuration with 44,230 bytes free.
