# TinyKSP 1.9.6 validation

- `--version` reports 1.9.6.
- Castlevania Dawn of Sorrow v1.20 MWK 0F starts and loads all 18 Fleeting Respite samples.
- All 29 pack tracks pass dry-run.
- A normal MWK 0C/0D track renders byte-for-byte identically to TinyKSP 1.9.5.
- Fleeting Respite 35-second render: 2,100 PLAY calls, 7,173 OPL4 PCM writes, 18 MWK samples.
- The existing synthetic `yamaha_smoke` OPL4 fixture still fails in the original 1.9.5 libvgm path and remains unrelated to real Dawn MWK playback.
