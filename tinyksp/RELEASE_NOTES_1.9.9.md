# TinyKSP 1.9.9 release notes

## Direct KSS/KSSX playback

TinyKSP can now open ordinary MSX `KSCC` and `KSSX` files without the libkss
player layer. KSS execution uses the same Z80, PSG, SCC, YM2413 and Y8950 cores
as KSP playback. The KSS VM mirrors the standard libkss low-page PSG helper
bootstrap, read-only page-2 behavior, 8 KiB bank selection at `$9000/$B000`,
16 KiB bank selection through port `$FE`, and PAL/NTSC PLAY cadence.

Supported KSS devices in this release: PSG, SCC auto mode, FM-PAC/YM2413,
Y8950/MSX-AUDIO, and the legacy 1-bit/8-bit DAC write paths. Sega-mode KSS is
rejected explicitly.

## KSP versus KSS comparison

Use:

```text
tinyksp --compare converted.ksp reference.kss --track 1
tinyksp --compare converted.ksp reference.kss --track 1 --seconds 60
```

The comparison runs both inputs through TinyKSP's own chip cores. It compares:

1. canonical chip writes, tagged as INIT or PLAY tick N;
2. 44.1 kHz signed-16 stereo PCM, sample by sample.

Exit status is `0` for an identical comparison, `3` for a content mismatch,
`1` for a playback/open error, and `2` for invalid command-line input.

On mismatch, TinyKSP reports the first differing chip write and the first
PCM frame/time/channel that diverges, plus total differing samples and maximum
absolute sample delta. The default compare window is 10 seconds. User-facing `--track N` is 1-based; a declared KSSX first-song ID is honored.
