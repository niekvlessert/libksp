# Dawn of Sorrow v1.11 validation

Pack: `Castlevania_Dawn_of_Sorrow_MoonSound_KSP1_1.04_OneDisk_v1.11_FleetingRespite_soft12bit_chords.ksp`

Player: TinyKSP 1.9.4 with external `yrw801.rom`.

- KSP 1.04 parser, file-size field, index CRC and header CRC accepted.
- Track 1: 35-second WAV render, 44.1 kHz stereo, 1,543,500 frames.
- Track 1: exactly 2,100 PLAY calls, 7,173 OPL4 PCM writes and 17 MWK samples.
- Tracks 1-29: two-second smoke render each, exactly 120 PLAY calls per track.
- Opening sustained chord waves 10 and 11 are custom 12-bit PCM at 10 kHz.
- v1.10 timing, melodic pitch, percussion fixes and free-voice allocation are retained.
