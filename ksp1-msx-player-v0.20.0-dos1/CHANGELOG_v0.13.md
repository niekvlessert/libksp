# KSP1PLAY 0.13

## Automatic KSP tick-rate selection

- Reads the engine `tick_hz` field after KSP validation.
- Selects 50 Hz when `tick_hz` is 50 and 60 Hz when it is 60.
- Changes only bit 1 of VDP register 9.
- Keeps the VDP register and the BIOS `RG9SAV` shadow synchronized.
- Saves the complete original register 9 value and restores it during cleanup,
  including fatal-error exits after the KSP engine has been validated.
- Playback remains one `PLAY` call per VBlank, now at the rate requested by the pack.

## Validation

- Existing sparse, hybrid, CRC, mapper-stack and ZX0 model tests pass.
- Resident `program_end` is `1BEAh`, below the fixed descriptor area at `1C00h`.
