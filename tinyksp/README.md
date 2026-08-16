# TinyKSP standalone VM 1.9.9

TinyKSP executes embedded KSP Z80 engines and ordinary MSX KSS/KSSX files directly.
It does not use the libkss player layer and does not generate synthetic KSS files.

```text
KSP 1.00-1.05 parser/materializer + KSS/KSSX loader
  -> 64 KiB Z80 VM, KSP ABI gateways and KSS mapper semantics
  -> PSG, SCC/SCC+, dual SCC, YM2413, Y8950 and YMF278B-compatible devices
  -> 44.1 kHz stereo PCM
```





## New in 1.9.9

- Adds direct MSX `KSCC`/`KSSX` playback using TinyKSP's existing Z80 and sound cores.
- Reproduces the libkss KSS low-page PSG bootstrap and the standard 8 KiB/16 KiB
  mapper controls (`$9000/$B000` and port `$FE`).
- Supports PSG, SCC auto mode, FM-PAC/YM2413, Y8950/MSX-AUDIO and PAL/NTSC KSS timing.
- Adds `--compare KSP KSS --track N`: both files are rendered through the same chip
  cores and compared by canonical chip-register trace and bit-exact stereo PCM.
- A successful comparison exits `0`; a real content mismatch exits `3` and reports
  the first chip-write divergence and first differing PCM frame/time/channel.
- Sega-mode KSS is rejected explicitly instead of being interpreted as MSX KSS.

## New in 1.9.8

- Accepts filename wildcards (`*` and `?`) and multiple KSP arguments.
- Automatically advances through the remaining supported tracks in a KSP.
- After the last playable track, automatically opens the next matched KSP.
- Preserves the active hardware playback type where the next track/file offers it.
- `q`, Esc and Ctrl-C stop the complete playlist.

## New in 1.9.6

- Adds the Nitro/DS-reference MWK 0E/0F playback path described below.

## New in 1.9.5

- Replaces TinyKSP's custom YMF278B wave/PCM synthesis with libvgm's
  openMSX-derived 24-slot implementation.
- Retains TinyKSP's existing OPL3/FM implementation and mirrors FM control
  writes into libvgm for NEW2/global OPL4 state.
- YRW801 ROM, MWK RAM, channel muting and MoonSound register I/O are routed to
  the libvgm backend.

## New in 1.9.4

- Correct custom MWK 12-bit/16-bit playback lengths. MWK stores payload bytes,
  while OPL4 headers store decoded sample counts.
- This is required by the Dawn of Sorrow v1.11 12-bit sustained chord waves.

## New in 1.9.3

- Corrects the YMF278B PCM pitch reference. Hardware normal pitch is
  `FNUM=0, OCTAVE=1`; TinyKSP previously treated octave 0 as normal, making
  every MoonSound PCM voice one octave too high and shortening percussion
  samples by a factor of two.
- Retains the 1.9.2 PCM-format, 12-bit unpacking, MWK wave-placement and
  PAGE3_WORKRAM corrections.

## New in 1.9.2

- Corrects the YMF278B PCM format map: `00` is 8-bit, `01` is 12-bit and
  `10` is 16-bit. TinyKSP 1.9.1 had 12-bit and 16-bit reversed.
- Corrects Yamaha 12-bit ROM packing. Two samples use three bytes: sample 0
  takes byte 0 plus the low nibble of byte 1; sample 1 takes byte 2 plus the
  high nibble of byte 1.
- Keeps MWK custom headers only at MoonSound RAM wave numbers `384+tone`, so
  custom kits no longer overwrite YRW801 ROM instruments `0..63`.
- Implements the KSP `PAGE3_WORKRAM` profile by filling private page 3 with
  `FFh` immediately before engine INIT.
- Retains the 1.9.1 correction for register `20h+n`: bit 0 is wave-number bit
  8 and bits 1-7 are F-number bits 0-6.

For Dawn of Sorrow, tracks 1, 2, 3 and 5 use 12-bit YRW801 ROM waves and were
therefore rendered as noise in 1.9.1. Track 4 initially sounded cleaner because
its opening uses only 8-bit custom RAM samples.

## New in 1.9.0

- Strict KSP 1.05 reader support while retaining KSP 1.00-1.04 behavior.
- Accepts overlapping resource enclosing spans introduced by KSP 1.05.
- Validates semantic control and leaf ranges instead of assuming exclusive
  resource ownership.
- Supports exact cross-resource `KZB1` block aliases and non-monotonic physical
  block placement while preserving descriptor-table logical order.
- Rejects partial leaf overlap, incompatible aliases, control/leaf overlap and
  `STREAMABLE` resources that require backward seeking.
- Retains KSP 1.04 metadata grammar 2 for KSP 1.05, including localized keys.
- Adds proper procedural FM-PAC/YM2413 rhythm voices for bass drum, snare, tom,
  cymbal and hi-hat. Combined rhythm bits trigger simultaneous drums instead of
  collapsing into generic FM/noise output.
- MoonSound/OPL4 and normal per-track `MWK ` playback remain unchanged. KSP 1.05
  adds no `MWS1` resource or new playback type.

## Existing 1.8.x functionality retained

- MoonSound/OPL4 FM and PCM with standard track-selected MWK sample kits.
- Optional external YRW801 ROM support.
- Strict KSP 1.03 `metadata_version=1` and strict KSP 1.04/1.05
  `metadata_version=2` parsing.
- Localized package metadata such as `title.ja`, `title.pt-br` and
  `title.zh-hant`.
- Strict HVAR/HVR1 hardware-variant selection.

## Use

```sh
tinyksp -v
tinyksp FILE.ksp --list
tinyksp FILE.ksp --track 1
tinyksp FILE.ksp --track 1 --variant 1
tinyksp FILE.ksp --track 1 --seconds 20 --wav output.wav
tinyksp FILE.kss --track 1
tinyksp FILE.kss --track 1 --seconds 30 --wav reference.wav
tinyksp --compare FILE.ksp FILE.kss --track 1
tinyksp --compare FILE.ksp FILE.kss --track 1 --seconds 60
tinyksp '*.ksp'
tinyksp game*.ksp --seconds 30
tinyksp intro.ksp music.ksp ending.ksp
```

On macOS, live playback uses the native Core Audio output and does not require
`mpv`. Termux continues to use `mpv` for live playback.

Normal playback continues with the next playable track and then the next KSP
file. Automatic progression does not wrap. Manual Left/Right selection still
wraps within the current KSP. `--wav` and `--dry-run` require one KSP file.

All package-level metadata fields, including localized values, are displayed
when a package is opened.

For MoonSound ROM instruments, place a 2 MiB `yrw801.rom` beside the KSP, set
`TINYKSP_YRW801_ROM`, or pass:

```sh
tinyksp FILE.ksp --track 1 --yrw801 /path/to/yrw801.rom
```

Embedded MWK custom samples do not require the ROM.


### KSP/KSS comparison

`--track N` is user-facing and 1-based. If the KSSX header declares a first-song ID,
TinyKSP maps track 1 to that ID; otherwise track 1 maps to KSS song 0.
The default comparison window is 10 seconds; use `--seconds N` for a longer run.
`IDENTICAL` means both the canonical PSG/SCC/FM-PAC/Y8950 write stream and the
44.1 kHz stereo PCM were identical for the requested window. A mismatch report
shows the first differing INIT/PLAY event plus PCM frame, timestamp, channel,
mismatch count and maximum absolute sample delta.

## Live controls

- Left / Right: previous / next visible playable track; Right on the last playable track opens the next KSP file;
- `Shift+,` (`<`) / `Shift+.` (`>`): seek backward / forward ten seconds;
- `1-0`: mute channels on the displayed channel page;
- Tab, `n`, or `]`: next channel page;
- `p` or `[`: previous channel page;
- `u`: unmute all channels;
- `q` or Esc: stop.

Channel order includes:

- SCC-A 1-5, SCC-B 1-5, PSG A-C;
- FM-PAC 1-9;
- Y8950 FM 1-9;
- OPL4 FM 1-18, followed by OPL4 PCM 1-24.

In FM-PAC rhythm mode, muting FM-PAC channels 7-9 controls the drum groups that
share the corresponding YM2413 operators.

## Supported KSP features

- KSP 1.00, 1.01, 1.02, strict 1.03, strict 1.04 and strict 1.05;
- META grammar 1 for KSP 1.03 and grammar 2 for KSP 1.04/1.05;
- KSP 1.05 exact shared payload views and cross-resource KZB1 block aliases;
- strict HVAR/HVR1;
- sparse, complete, PBM1/PBLK, RMP1 and HPOL pages;
- NONE, ZX0 and KZB1 resources;
- dynamic pages and PAGE2_RUNTIME;
- PSG, SCC, SCC+, dual SCC;
- FM-PAC/YM2413 melodic and rhythm modes;
- Philips Music Module/Y8950 FM;
- MoonSound/OPL4 FM and PCM with MWK.

Not yet supported: Y8950 ADPCM, SN76489/Game Gear stereo and live banked-data
resources.

## Included specifications

- `KSP_FORMAT_SPEC_1.03.md`
- `KSP_FORMAT_SPEC_1.04.md`
- `KSP_FORMAT_SPEC_1.05.md`

## Upgrade an invalid localized KSP 1.03 pack

For an uncompressed META resource:

```sh
python3 tools/upgrade_meta_103_to_104.py INPUT.ksp OUTPUT.ksp
```

This converts only the metadata/container revision from 1.03 to 1.04. It does
not create KSP 1.05 shared payload layouts.

## Termux

```sh
cd ~/storage/downloads
unzip TinyKSP-v1.9.9_KSS_Compare_OfflineSource.zip
cd TinyKSP-v1.9.9_KSS_Compare
chmod +x install.sh
./install.sh
```

## Building

See [BUILDING.md](BUILDING.md).

## Dawn 12-bit MWK 0F extension

This edition accepts MWK revision 0F. Nitro IMA ADPCM sources are decoded at
track load time to packed 12-bit YMF278B PCM, allowing the complete corrected
A Fleeting Respite bank to fit 640 KiB MoonSound RAM. Revision 0E remains the
full 16-bit target. See `DAWN_12BIT_MWK_0F.md`.


## TinyKSP 1.9.6 Nitro/DS reference mode

MWK 0E/0F resources automatically select a restricted DS-reference PCM path:
Nitro ADPCM loading, zero-order sample hold, native stereo, and removal of
libvgm's PCM-only -15 dB balancing attenuation. Ordinary MWK 0C/0D resources
continue to use normal YMF278B linear interpolation and gain.
