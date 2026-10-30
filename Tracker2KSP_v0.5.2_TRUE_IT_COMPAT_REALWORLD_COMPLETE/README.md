# Tracker2KSP v0.5.2 — native IT compatibility + real-world paging fixes

v0.5.2 continues the physically separate native Impulse Tracker runtime and finishes another high-value OpenMPT/IT compatibility layer. KSP stays at **1.05**; the ST3/S3M, IT-authored S3M, XM and MOD engines remain separate and unchanged in size.

## What v0.5.2 adds

- **Linear IT E/F/G pitch slides**. The host precomputes the IT linear factors and carries compact factors in the semantic stream, avoiding exponent/table work on the Z80.
- **S50-S53 panbrello waveforms**, including S53 sample-and-hold behaviour.
- IT **instrument/sample default panning**, with sample pan overriding instrument pan and explicit row panning overriding both.
- IT **PPS/PPC pitch-pan separation**, evaluated from the original pattern note before instrument note-map translation.
- Independent per-voice **sample global volume × instrument global volume (SV×IV)** gain, applied in the runtime before channel/global volume.
- Compatible-Gxx profile reset semantics on tone-portamento. A real G/L sample swap that changes C5/sample identity remains fail-fast rather than silently using the old sample semantics.
- Correct IT file-format filter-envelope flag handling: pitch/filter envelope flag `0x80` is recognized and filter envelopes remain explicitly unsupported rather than being mistaken for pitch envelopes.

## Real-world runtime fixes found with a high-rate IT module

A real IT 2.17-compatible module at **speed 1 / tempo 250** exposed three bugs that the synthetic fixtures did not:

- The old **48 semantic-page ceiling** was artificial. KSP 1.05 engine/page counts are 16-bit, so Tracker2KSP now permits up to **65,535 pages**. Preload eligibility is still reported separately.
- Native IT moved its dynamic stream to `$7C00` in v0.5.0, but one assembler constant still read `STREAM_DATA=$6802`. v0.5.2 fixes this to **`STREAM_PAGE+2` = `$7C02`**. Without the fix INIT could read speed/tempo from resident code/state.
- `parse_one_effect` used carry as its true stream-read-failure signal, but valid **Mxx/Vxx** comparisons could return with carry still set, and **T0x/T1x** tempo slides returned through `RET C`. These paths are now carry-safe; T0x/T1x are stored as realtime effects.

## v0.5.2 validation

- Native IT pytest suites (`v049` through `v052`): **37/37 PASS**.
- S3M: **4/4 PASS**.
- XM: **10/10 + 4/4 PASS**.
- MOD: **8/8 PASS**.
- Fresh engine build: ST3/S3M **9,054**, IT-S3M **8,926**, native IT **12,800**, MOD **10,674**, XM **6,472** bytes.
- Native IT persistent state: **929/1,024 bytes** in the reserved MoonSound state block.
- Real-world IT validation: 13,441 semantic rows / 58,393 events, **317 dynamic pages**, 0 converter warnings. TinyKSP 1.9.9 rendered the complete 140-second validation run with **316 page switches**, **8,399 PLAY calls** and **1,019,119 OPL4 PCM writes** without VM/cycle-limit failure.

## Deliberately fail-fast / remaining IT boundary

`Zxx` MIDI/filter macros are still not faked. Random volume/pan swing, envelope carry/filter envelopes, sample sustain/ping-pong loop edge cases and sample auto-vibrato remain outside the exact runtime. Delayed notes that require non-neutral trigger-state application and G/L rows that genuinely swap to another sample/C5 domain also remain explicit failures. The exact NNA allocator continues to refuse a 25th simultaneously tracked OPL4 PCM voice rather than steal a sounding voice.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.it
python3 CONVERT_IT_TO_KSP.py song.it
```

---

# Tracker2KSP v0.5.1 — native IT extended effects

v0.5.1 continues the physically separate native Impulse Tracker runtime introduced in v0.4.9/v0.5.0. It adds the high-value remaining IT realtime effect layer without changing KSP 1.05 or KSP1PLAY. ST3/S3M, IT-authored S3M, XM and MOD keep their existing engines and layouts.

## What v0.5.1 adds

- **Jxy arpeggio** is enabled for native IT, using the native IT row/tick counter rather than borrowing ST3 semantics.
- **Mxx / Nxy channel volume**: immediate channel-volume set plus native IT regular/fine channel-volume slides with separate Nxx effect memory.
- **Pxy panning slide**: native IT direction, fine-slide priority and separate effect memory. Logical panning state follows the tracker channel and is inherited when NNA moves the foreground note to another physical OPL4 voice.
- **Uxy fine vibrato**: shares H/U speed/depth memory as IT does, while applying U's finer depth scale.
- **Vxx / Wxy global volume**: dynamic runtime global-volume set/slide. Wxx keeps its own memory and IT fine-slide ordering.
- **Txx tempo**: `T00` recalls T memory, values `>=20h` set tempo immediately, and `T0x/T1x` perform down/up slides on non-first ticks with IT clamping.
- **Yxy panbrello**: persistent speed/depth memory and a held panning offset. A real new note or direct panning command clears the held offset. The runtime keeps an 8-bit phase and uses the resident sine curve; final output is necessarily quantized to the OPL4's hardware panning positions.
- **Global-effect pre-pass**: Txx and Wxx are evaluated before per-voice mixing, so tempo/global-volume changes do not depend on which tracker channel contains the command and are never applied twice.
- Native IT channel/global volume is now fully dynamic. The OPL4 volume LUT remains neutral and M/N/V/W are applied in the IT runtime, avoiding double application of header global volume.
- NNA foreground reallocation preserves the logical IT channel's current channel volume and panning state.
- Native IT persistent state after the new effect variables is **905 bytes**, still inside the already-reserved final 1 KiB of MoonSound RAM (`$2FFC00-$2FFFFF`).
- Native IT engine size is now **12,288 bytes**. Its profile pointer table is at `$6E00`, profile payload begins at `$7000`, and semantic pages remain `$7C00-$7FFF`.

## Deliberately fail-fast / remaining IT boundary

`Zxx` is **not faked**: in IT it represents MIDI/filter macro execution, which needs a real macro/filter implementation rather than a PCM approximation. Native IT therefore still rejects Zxx explicitly. `S5x` alternate panbrello waveform selection also remains fail-fast; Yxy currently uses the default sine waveform. Other previously documented boundaries remain, including Old Effects mode, linear E/F/G slides, envelope carry/filter envelopes, pitch-pan separation/random volume/pan, several non-neutral instrument/sample global-volume/default-pan combinations, sustain/ping-pong sample-loop edge cases, sample auto-vibrato, and delayed-note + NNA/DCT runtime allocation.

OPL4 still provides 24 PCM voices. The exact allocator refuses a 25th simultaneously tracked NNA voice rather than silently stealing a sounding voice.

## v0.5.1 validation

- `tests/test_it_v049.py` + `tests/test_it_v050.py` + `tests/test_it_v051.py`: **25/25 native-IT tests PASS**.
- `tests/test_s3m_v045.py`: **4/4 PASS**.
- `tests/test_xm_v046.py`: **10/10 PASS**.
- `tests/test_xm_v047.py`: **4/4 PASS**.
- `tests/test_mod_v048.py`: **8/8 PASS**.
- Fresh instrument-mode native `.it -> .ksp` smoke with J/N/P/T plus envelopes/NNA: **18,464 bytes**, KSP 1.05, one semantic page, **0 warnings**, dedicated native-IT engine **12,288 bytes**.
- Smoke KSP SHA-256: `03b458c3a2ebe152a7b36de634654e5f9ebbebb322d276bf65913f309a141b77`.
- Engine sizes: ST3/S3M **9,054**; IT-S3M **8,926**; native IT **12,288**; MOD **10,674**; XM **6,472** bytes. Only native IT changed.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.it
python3 CONVERT_IT_TO_KSP.py song.it
```

---

# Tracker2KSP v0.5.0 — native IT envelopes + NNA/DCT/DCA

v0.5.0 builds on the real `IMPM` loader from v0.4.9 and adds the first full native Impulse Tracker **instrument runtime**. Native IT remains physically separate from ST3/S3M, IT-authored S3M, XM and MOD. KSP stays at **1.05** and no KSP1PLAY 0.48 change is required.

## What v0.5.0 adds

- Native IT **volume, panning and pitch envelopes** with interpolation, normal loops and sustain loops.
- Correct key-held sustain behaviour: reaching a held sustain endpoint does not incorrectly start instrument fadeout.
- Native IT **instrument FadeOut** with distinct Note Off, Note Cut and Note Fade runtime states.
- Native IT **NNA Cut / Continue / Note Off / Note Fade**. Old foreground notes can continue as independent background voices.
- Native IT **DCT Note / Sample / Instrument** with **DCA Cut / Off / Fade**. DCT Note compares the original pattern note before note-map translation, matching IT compatibility behaviour.
- Host-side flattening of IT logical channels/background NNAs to the MoonSound's 24 physical OPL4 PCM voices. A sounding voice is never stolen silently: conversion fails if exact playback would need a 25th simultaneous voice.
- Instrument-only rows now update IT instrument memory. Instrument keymaps remain active for later notes.
- A compact resident IT profile table stores NNA/DCT/DCA, FadeOut and envelope descriptors. Curves are precomputed on the host; pitch-envelope factors therefore do not require exponential math on the Z80.
- Native IT persistent state uses the already-reserved final 1 KiB of MoonSound RAM (`$2FFC00-$2FFFFF`). No sample-RAM reservation was added.
- Native IT semantic pages now use **`$7C00-$7FFF`**. The enlarged native IT engine is **11,776 bytes**. S3M, IT-S3M, MOD and XM retain their previous layouts and sizes.
- Added `tests/test_it_v050.py`; older native-IT tests are still run as regression coverage.

## Deliberately fail-fast / accuracy boundary

The converter still refuses native IT features that are not implemented accurately: envelope carry, filter envelopes, pitch-pan separation, random volume/pan, non-neutral instrument/sample global-volume/default-pan cases, sustain/ping-pong sample loops, sample auto-vibrato, Old Effects, linear E/F/G slides, exact Jxx arpeggio timing, tempo slides below `20h`, and unsupported M/N/P/U/V/W/Y/Z runtime effects. Delayed notes combined with NNA/DCT also remain fail-fast because they would need tick-time voice allocation.

OPL4 has only 24 PCM voices. v0.5.0 therefore refuses a 25th simultaneously tracked NNA voice instead of using OpenMPT-style voice stealing. Background voices are conservatively retained by the conversion-time allocator; natural sample-end/release lifetime prediction is not yet used to recycle them. This can reject some NNA-heavy modules earlier than strictly necessary, but it cannot silently delete an audible voice.

## v0.5.0 validation

- `tests/test_it_v049.py` + `tests/test_it_v050.py`: **19/19 native-IT tests PASS**.
- `tests/test_mod_v048.py`: **8/8 PASS**.
- `tests/test_xm_v046.py`: **10/10 PASS**.
- `tests/test_xm_v047.py`: **4/4 PASS**.
- `tests/test_s3m_v045.py`: **4/4 PASS**.
- Fresh native instrument-mode `.it -> .ksp` smoke: **18,456 bytes**, no warnings, KSP 1.05, native IT engine 11,776 bytes.
- Engine sizes: ST3/S3M 9,054; IT-S3M 8,926; native IT 11,776; MOD 10,674; XM 6,472 bytes.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.it
python3 CONVERT_IT_TO_KSP.py song.it
```

---

# Tracker2KSP v0.4.8 — generic MOD / ProTracker compatibility pass

Tracker2KSP converts MOD, XM, S3M and IT-authored/modern S3M modules to compact realtime MoonSound/OPL4 KSP 1.05. v0.4.8 is a focused MOD/ProTracker pass on top of v0.4.7. The four tracker runtimes remain physically separate; no KSP format or KSP1PLAY change is required.

The MOD engine now owns `$4000-$69B1` and MOD semantic pages begin at **`$6A00`**. XM/S3M/IT-S3M retain their `$6800` semantic window and their engine binaries are byte-identical to v0.4.7.

## v0.4.8 MOD fixes

- **True ProTracker 1xx/2xx slides.** Values such as `1E1` are ordinary speed `$E1`, not S3M-style fine/extra-fine slides.
- **Correct MOD effect memory.** 3xx, 4xy and 9xx retain the appropriate ProTracker state; `100`, `200`, `A00`, `500` and `600` do not incorrectly inherit S3M/XM-style slide memory. 5xy/6xy retain their combined tone-porta/vibrato + Axy behaviour.
- **ProTracker A/5/6 nibble priority** replaces S3M fine-slide interpretation.
- **Exact 16-finetune ProTracker period tables** are used for notes and arpeggio. Amiga slide limits are now finetune-dependent rather than a fixed finetune-0 clamp.
- Added/expanded ProTracker effects: `7xy` tremolo; E1/E2 fine porta; E3 glissando; E4/E7 waveform selection and phase-reset rules; E5 finetune; E6 pattern loop; E8 pan; E9 retrigger; EA/EB fine volume; EC cut; ED note delay; EE pattern delay; and **EFx invert/funk loop**.
- **EFx is no longer a no-op.** The Z80 runtime keeps the ProTracker funk-delay counter and byte offset per channel and complements the active loop byte directly in MoonSound sample RAM at tracker tick cadence using OpenMPT's `0,5,6,7,8,10,11,13,16,19,22,26,32,43,64,128` delay table.
- **One-shot loops** are represented explicitly. For canonical ProTracker samples with loop start 0, OPL4 first plays the full one-shot tail and then loops an appended copy of the original loop region.
- **Sample-swap profiling** follows OpenMPT's important detector: four consecutive instrument-only sample changes enable the sample-swap quirk even outside the narrow canonical profile. Tone-portamento + sample change and instrument-only sample change have dedicated semantic note kinds.
- **Stopped looping sample replacement** can re-key a stopped OPL4 voice while preserving pitch state. Exact Paula sample-end swap timing cannot be observed by OPL4, so the actual wave change is performed at the tracker row boundary and reported as an approximation.
- **M.K./M!K! CIA-vs-VBlank detection** now probes both timing interpretations for ambiguous long modules. Suspicious low tempo commands only switch to `PROTRACKER_VBLANK` when the CIA interpretation is at least eight minutes and the VBlank interpretation is shorter, unless stronger CIA evidence exists.
- Canonical ProTracker tempo changes keep the tick-1 quirk; VBlank-classified Fxx commands are remapped to speed semantics.
- EDx out-of-range delay, restart markers and canonical ProTracker/Amiga period behaviour are profile-aware.
- Loader support is broadened for classic MOD families including NoiseTracker/HMN, Startrekker FLT4/FLT8/EXO, Oktalyzer/Octalyser, TakeTracker, Digital Tracker, Inconexia delta-MOD and generic multichannel signatures. FLT8 uses its paired 4-channel physical-pattern layout rather than being treated as a flat 8-channel pattern.
- MOD ADPCM and Inconexia signed delta PCM are decoded at conversion time. Generic 7-bit panning is recognised; unsupported Paula surround is centred deliberately.
- MOD files above 24 channels are rejected cleanly instead of overrunning the 24 OPL4 voice states.
- Chained semantic effects are now parser-safe: MOD instrument/finetune state markers do not consume either of the two continuing realtime effect slots, so instrument + 5xy/6xy cannot desynchronise the stream.

## Validation

- `tests/test_mod_v048.py`: **8/8 MOD v0.4.8 regression groups PASS**.
- `tests/test_xm_v046.py`: **10/10 XM v0.4.6 groups PASS**.
- `tests/test_xm_v047.py`: **4/4 XM v0.4.7 edge groups PASS**.
- `tests/test_s3m_v045.py`: **4/4 S3M groups PASS**.
- OpenMPT supplied `test/test.mod`: converts as `PROTRACKER`, no warnings.
- Final MOD Z80 engine: **10,674 bytes**, ending at `$69B1`; MOD stream starts at `$6A00`.
- Historical LUT/state boundary is preserved exactly: `SINE=$4A6C`, `VOL=$4AB0`, `PITCH=$4B11`, `PITCH_END=$5F63`, with new MOD finetune state beginning at `$5F64`.
- ST3/S3M (9,054 bytes), IT/modern-S3M (8,926 bytes) and XM (6,472 bytes) engines are byte-identical to v0.4.7.
- Root and `source/` Python converter files are synchronized; `source/BUILD_ENGINES.py` rebuilds all four engines.

## Remaining MOD differences

v0.4.8 aims at tracker semantics, not sample-for-sample Paula mixer identity. Remaining deliberate differences are:

- ProTracker sample swapping normally takes effect at the exact Paula sample-end boundary. OPL4 exposes no equivalent per-voice sample-end callback, so Tracker2KSP changes the selected wave at the row boundary. The converter emits a warning when this quirk is used.
- `E0x` controls the Amiga LED analogue low-pass filter. OPL4 has no hardware-equivalent filter, so this remains non-emulated.
- `8A4` Paula surround has no direct OPL4 equivalent and is centred.
- EFx itself mutates OPL4 RAM at the correct tracker tick cadence. The extremely rare combination of EFx with a transformed one-shot loop can differ during the initial one-shot pass because the OPL4 representation uses an appended hardware-loop copy.
- Paula DMA/mixer interpolation, analogue filtering and exact channel panning/gain laws are not claimed to be bit-identical to OpenMPT's Paula emulation; the target is the OPL4 hardware mixer.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.mod
python3 CONVERT_MOD_TO_KSP.py song.mod
python3 CONVERT_TRACKER_TO_KSP.py song.xm
python3 CONVERT_TRACKER_TO_KSP.py song.s3m
```

`source/BUILD_ENGINES.py` rebuilds all tracker engines.

---

# Historical v0.4.7 notes

# Tracker2KSP v0.4.7 — XM edge compatibility pass

Tracker2KSP converts XM, S3M, IT-authored/modern S3M and MOD modules to compact realtime MoonSound/OPL4 KSP 1.05 files. v0.4.7 is a focused second XM/OpenMPT compatibility pass on top of v0.4.6. The KSP format and the `$6800` semantic-stream window are unchanged; KSP1PLAY does not need a format change.

The tracker runtimes remain physically separate:

- `compact_engine_xm.bin` — XM / FT2 and recognised XM-clone semantics
- `compact_engine_s3m.bin` — genuine Scream Tracker 3
- `compact_engine_it_s3m.bin` — IT-authored / modern S3M
- `compact_engine_mod.bin` — ProTracker / MOD

## v0.4.7 XM additions

- **OXM / OggMod sample payloads** are accepted. The converter recognises the OXM layout (`original PCM byte count` + Ogg Vorbis stream), decodes the audio at conversion time, honours the XM 8/16-bit and mono/stereo geometry, and downmixes to the signed mono PCM used by the OPL4 wave bank. It first tries Python `soundfile`/libsndfile and falls back to `ffmpeg`.
- **FT2 E60 next-pattern-row behaviour** is reproduced: the E6 loop start can survive the completed loop and become the natural start row of the next pattern; Bxx/Dxx clear that retained row. Old-ModPlug profile can disable the FT2 quirk.
- **FT2 envelope escape** is implemented: after key-off, an envelope loop whose loop-end coincides with sustain no longer traps the released volume/pan envelope.
- **FT2 panning-envelope sustain release** is modelled: a panning envelope that reached sustain while the key was held remains pinned there after key-off in the FT2-compatible profile.
- **FT2 auto-vibrato sweep abort** is modelled. A key-off before full sweep depth resets the active sweep depth to the one-step FT2 state; a sweep that already reached full depth remains full.
- **FT2 tone-portamento target pickup** is preserved across ordinary new notes (`Porta-Pickup` behaviour), rather than replacing the old target unconditionally.
- **FT2 porta direction state** is carried separately from E3 glissando state. Reaching the target through the FT2-specific branch records the direction state used by subsequent tone-portamento processing.
- **FT2 arpeggio timing** now uses the FT2 backwards speed/tick index, including its unusual >=16-speed behaviour. MadTracker and Skale profiles use the non-FT2 cycle because OpenMPT disables the FT2 arpeggio quirk for those creators.
- **9xx offset past sample end** is creator-profile aware. FT2/OpenMPT-compatible playback clears/stops the period state; Skale keeps the pitch state instead.
- **Creator-profile refinement**: MadTracker disables FT2 porta-without-old-note and FT2 arpeggio quirks; Skale disables FT2 arpeggio and FT2 out-of-range-offset semantics; the old-ModPlug route disables the set of newly modelled strict-FT2 edge flags.
- The compact XM stream now exports dedicated runtime bits for FT2 arpeggio, envelope escape, pan-sustain release, auto-vibrato sweep abort, porta direction and porta-target preservation. This does not change KSP 1.05 framing.

## Validation

- `tests/test_xm_v046.py`: **10/10 v0.4.6 XM regression groups PASS**.
- `tests/test_xm_v047.py`: **4/4 v0.4.7 XM edge-compatibility regression groups PASS**.
- `tests/test_s3m_v045.py`: **4/4 S3M regression groups PASS**.
- OpenMPT supplied `test/test.xm`: builds as `OPENMPT`, 96 semantic rows, no warnings.
- The same OpenMPT module with linear periods disabled: builds through the Amiga-frequency-table route with no warnings.
- OXM smoke module: one Ogg/Vorbis sample is decoded and emitted as one custom OPL4 tone, no warnings.
- Final XM Z80 engine: **6,472 bytes** at `$4000`, well below the `$6800` stream window.
- S3M, IT-S3M and MOD binaries are byte-identical to v0.4.6; only the XM engine changed.
- Root and `source/` XM source/binary/map/list copies are synchronized.
- `python3 -m py_compile *.py source/*.py tests/test_xm_v046.py tests/test_xm_v047.py tests/test_s3m_v045.py`: PASS.

## Remaining XM limitations

These are deliberately not claimed as bit-exact:

- OXM decoding is a **converter-time dependency**: `soundfile`/libsndfile or `ffmpeg` must be available. The Z80/KSP runtime does not contain a Vorbis decoder.
- OpenMPT has more defensive handling for malformed/chained Ogg streams than this converter; normal OXM/OggMod sample chunks are the target.
- FT2 arpeggio combined with deliberately pathological simultaneous realtime pitch slides can still differ because Tracker2KSP stores precomputed alternate OPL4-compatible period targets rather than reproducing OpenMPT's mixer-period arithmetic sample-for-sample.
- Old ModPlug identification from the classic 20-byte XM tracker string is necessarily approximate; OpenMPT can use additional saved-with/version information that classic XM files may not expose uniformly.
- Mixer-only FT2 details such as its exact output ramping/panning law cannot map sample-for-sample to the OPL4 hardware mixer.
- More than 24 simultaneous XM PCM channels remains deliberately unsupported because the OPL4 exposes 24 PCM voices.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.xm
python3 CONVERT_TRACKER_TO_KSP.py song.s3m
python3 CONVERT_TRACKER_TO_KSP.py song.mod
```

Format-specific wrappers are included. `source/BUILD_ENGINES.py` rebuilds all four Z80 engines.

---

# Historical v0.4.6 notes

# Tracker2KSP v0.4.6 — generic XM / FastTracker II compatibility pass

Tracker2KSP converts XM, S3M, IT-authored/modern S3M and MOD modules to compact realtime MoonSound/OPL4 KSP 1.05 files. v0.4.6 concentrates on **XM / FastTracker II correctness** while retaining the v0.4.5 S3M fixes.

The tracker engines remain physically separate:

- `compact_engine_xm.bin` — XM / FastTracker II semantics
- `compact_engine_s3m.bin` — genuine Scream Tracker 3 (`ST3-GUS` / `ST3-SB`)
- `compact_engine_it_s3m.bin` — IT-authored and modern/non-ST3 S3M compatibility route
- `compact_engine_mod.bin` — ProTracker / MOD

KSP 1.05 and KSP1PLAY do **not** need a format change for v0.4.6. The semantic stream remains at `$6800`.

## v0.4.6 XM fixes

- XM playback state is no longer tied to the `linear periods` header bit. **Amiga-frequency-table XM files now keep XM envelopes, panning envelope, fadeout, auto-vibrato, key-off and waveform state.** `XM_LINEAR` selects only the pitch domain.
- XM instrument numbers are preserved as instruments instead of being flattened to a sample during parsing. Runtime compilation resolves the active sample through the instrument's 96-note keymap and keeps current instrument, current sample and note state separate.
- FT2 tone-portamento semantics are corrected: a new instrument beside tone-portamento does not replace the currently playing sample, and tone-portamento without an old playing note does not create a note.
- FT2 effect memory is split correctly: `Axy/5xy/6xy` share normal volume-slide memory; E1/E2, X1/X2 and EA/EB use independent fine/extra-fine memories; panning/global-volume/retrigger have their own state; volume-column effects do **not** inherit effect memory.
- `9xx` offset memory is only updated when a real note occurs on the row, matching FT2.
- Added realtime FT2 effects: `7xy` tremolo, `Gxx` global volume, `Hxy` global-volume slide, `Lxx` envelope position, `Pxy` panning slide, `Rxy` multi-retrigger and `Txy` tremor.
- Added/expanded extended effects: E1/E2 fine porta, E3 glissando state, E4 vibrato waveform, E5 finetune, E6 pattern loop, E7 tremolo waveform, E9 retrigger including E90, EA/EB fine volume, EC note cut, ED note delay, EE pattern delay, X1/X2 extra-fine porta and F00 stop semantics.
- `Axy/5xy/6xy` and global-volume slide now use FT2 nibble priority rather than S3M-style fine-slide interpretation.
- FT2 delayed-note / delayed-note-off corner cases are modelled, including `3xx + EDx`, delayed Note Off without normal fade/key-off, volume-column timing beside EDx, and the PanOff rule that ignores volume-column panning beside a delayed Note Off.
- FT2 K00 suppresses the simultaneous note/instrument action and performs the key-off semantics instead.
- Rxy first-tick behaviour now carries literal row note/instrument/volume-column state to the Z80 runtime. Rxy does not reset XM envelopes, interval 0 remains valid, and retrigger volume transform `x=6` is the exact 10/16 (=5/8) integer transform.
- The XM realtime engine now has **three continuing effect slots** so legal FT2 effect-column + volume-column combinations are not silently truncated.
- Notes that become invalid after XM `RelativeTone` transposition are ignored instead of clamped/played.
- XM versions **1.02, 1.03 and 1.04** are accepted, including the old pre-1.04 instrument/sample layout and 1.02 row-count encoding. A zero pattern row count is interpreted as 64 rows where appropriate.
- Initial speed/tempo fallbacks are FT2-compatible (`0 -> 6` and `0 -> 125`). Restart position is retained.
- XM split-stereo 8/16-bit delta PCM is decoded and downmixed to mono for the OPL4 custom-wave path. ModPlug XM 4-bit ADPCM (`reserved=0xAD`) is decoded.
- Basic creator profiling is reported for FT2, OpenMPT, MilkyTracker, MadTracker, Skale, ModPlug and generic XM. OpenMPT-style truly empty order lists are kept distinct from classic FT2's implicit pattern-0 behaviour.
- XM files above 24 channels are rejected explicitly instead of overflowing the 24-voice runtime state.

## Validation

- `tests/test_xm_v046.py`: **10/10 XM regression groups PASS**.
- `tests/test_s3m_v045.py`: **4/4 S3M regression groups PASS**.
- OpenMPT's supplied `test/test.xm` builds successfully as `OPENMPT`, with no converter warnings.
- The same OpenMPT test data with the XM linear-period flag cleared also builds successfully through the Amiga-frequency-table path while retaining XM instrument/envelope semantics.
- All four Z80 engines rebuild from source. The v0.4.6 XM engine is 6,136 bytes; root and `source/` binaries are byte-identical.
- `python3 -m py_compile *.py source/*.py` passes.

## Known XM gaps after v0.4.6

These are intentionally **not** claimed as solved:

- OXM / Ogg-compressed XM samples are not decoded.
- Creator identification exists, but every historical clone-specific playback deviation (notably some MadTracker/Skale/old ModPlug arpeggio/offset/porta quirks) is not yet reproduced individually.
- Rare FT2/OpenMPT compatibility flags such as envelope escape, panning-sustain release, auto-vibrato sweep abort, porta-direction/target edge cases and E60 restart corner cases still need dedicated regression modules before claiming bit-exact behaviour.
- Amiga-period arithmetic is implemented in the FT2 period domain, but the final realtime OPL4 frequency conversion remains a hardware-oriented lookup/approximation rather than an attempt to reproduce an Amiga mixer sample-for-sample.
- More than 24 simultaneous XM channels cannot map one-to-one to the 24 OPL4 PCM voices and is therefore deliberately rejected.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.xm
python3 CONVERT_TRACKER_TO_KSP.py song.s3m
python3 CONVERT_TRACKER_TO_KSP.py song.mod
```

Format-specific wrappers are included. `source/BUILD_ENGINES.py` rebuilds all four Z80 engines.

---

# Historical v0.4.5 S3M notes

## v0.4.5 S3M generic fixes

- Explicit S3M creator profiles replace the old `family 3 => IT, everything else => ST3` rule. Genuine ST3 is split into GUS/SB behaviour; IT-authored and modern OpenMPT/Schism/Orpheus-style files no longer inherit strict ST3 quirks.
- Genuine ST3 shared effect memory now follows OpenMPT/ST3 semantics: any real non-zero effect command updates the byte recalled by D/E/F/I/J/K/L/Q/R/S; `command=NONE,param!=0` does not. G/H/O retain their command-specific state as well.
- K/L combined volume slide is completely suppressed on tick 0, including with fast volume slides.
- `Qx0` uses a one-tick retrigger interval for strict ST3.
- `Ixy` tremor and `Rxy` tremolo now execute in the S3M runtimes; vibrato/tremolo waveform state is supported.
- Important `Sxx` commands are implemented: S2 finetune, S3 vibrato waveform, S4 tremolo waveform, S6 tick delay, S8 panning, SA high sample offset, SB pattern loop, SC note cut, SD note delay and SE pattern delay. S1 glissando state is parsed, but exact semitone-quantised portamento remains a known gap (see below).
- Initial S3M speed/tempo fallback is profile-aware (`speed 0 -> 6`, strict ST3 `speed 255 -> 6`, strict invalid tempo -> 125).
- C5/C2 speed is normalised like ST3/OpenMPT (`0 -> 8363`, minimum 1024, maximum 65535).
- S3M volume-column values 128..192 are converted to panning 0..64. Mono S3M playback is centred when no explicit panning table overrides it.
- Pattern decoding ignores an unreliable packed-length field and merges duplicate channel tokens field-by-field, matching OpenMPT's row/channel model.
- S3M 16-bit and stereo PCM are accepted. Stereo planes are decoded correctly and downmixed to the converter's signed mono OPL4 custom-wave format.
- Strict GUS sample offsets past a loop end wrap within the loop; strict SB out-of-range offsets stop instead of using the previous alias behaviour.
- S3M old-vibrato header flag `0x01` is propagated to the runtime and doubles the strict-ST3 vibrato depth.

### OpenMPT regression

OpenMPT's own `test/test.s3m` (`cwtv=0x5132`) previously aborted with `stereo/16-bit S3M samples are not supported`. v0.4.5 classifies it as `MODERN-S3M / OpenMPT`, decodes its stereo 16-bit PCM and builds a KSP successfully. `tests/test_s3m_v045.py` also covers shared effect memory, NONE-command memory behaviour, profile defaults, duplicate-token merging, bad packed-length tolerance, mono panning and stereo/16-bit decoding.

## Known S3M gaps after v0.4.5

These are deliberately not claimed as solved yet:

- S1 glissando is recognised but the realtime Gxx slide is not yet quantised to exact semitone steps.
- ST3 GUS-vs-SB **short-sample end detection during Q retrigger** is not exact on the OPL4 runtime yet.
- Header flag `0x10` Amiga period limits and original ST3 master-volume/preamp gain are not yet modelled.
- S3M ADPCM-packed samples and AdLib/SCRI instruments remain unsupported.
- IT/Schism/OpenMPT-specific S3M corner cases beyond the profile split are intentionally left for the later IT audit.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.s3m
python3 CONVERT_TRACKER_TO_KSP.py song.xm
python3 CONVERT_TRACKER_TO_KSP.py song.mod
```

Format-specific wrappers are included as well.

## Source tree

The root converter files and their copies under `source/` are synchronized in this release. `source/BUILD_ENGINES.py` rebuilds all four Z80 engine binaries.

## Historical v0.4.4 notes

## v0.4.4 S3M reference-pitch fixes

- Genuine ST3/S3M note state now starts from the same C2SPD/exponential base period used by the proven Second Reality ST3-to-OPL4 converter, while keeping the 4x integer runtime domain required by E/F/G/H effects.
- Temporary H/J/K hardware pitch is tracked separately from the underlying base period and restored at the correct following tick/row boundary. This removes the large high-tone drift seen in the Purple Motion passages around 1:04-1:16.
- Tone portamento now clamps correctly on 16-bit underflow/overflow instead of wrapping to a bogus period.
- The v0.4.3 OPL4 0x200600 PCM start and complete 12-byte upper alias headers remain in place.
- These changes are confined to the genuine ST3/S3M engine. IT-authored S3M, XM and MOD retain their separate engines and pitch semantics.


Additional full-track fixes in the final v0.4.4 build:

- The S3M `PITCH_LUT` no longer overlaps mutable state at `$5F00`; the final 30 lookup bytes were previously vulnerable to runtime corruption.
- H/K vibrato explicitly returns the OPL4 pitch to base at zero crossings.
- J arpeggio explicitly restores base pitch at cycle position 0.
- K/L combined-command timing follows their primitive H/G + D behaviour while rejecting fine D forms.
- E/F pitch rows always commit their intended pitch, and a fresh note clears stale temporary H/J/K state.
- Complete Purple Motion register comparison against the proven Second Reality converter now stays within about 2.9 cents, with the 1:10 high-tone region around 1 cent.

## v0.4.4 fixes

### 128-wave OPL4 RAM header reservation

Extended S3M/IT-S3M playback uses custom OPL4 wave headers 384..511. OPL4 RAM therefore needs a full 128 × 12-byte header area (`0x200000..0x2005FF`). Earlier Tracker2KSP builds let real PCM start at `0x200300`, so runtime installation of upper-half alias headers 448..511 could overwrite the first real sample payload.

v0.4.4 reserves the missing `0x300` bytes. Real PCM now starts at `0x200600` whenever the extended alias layout is used.

### Complete upper-half alias headers

Runtime aliases for sample-offset variants write their seven variable geometry bytes during INIT. The reserved header area is now pre-seeded with the five fixed OPL4 envelope bytes (`00 F0 00 07 00`) for every upper-half header. This prevents `Oxx` sample-offset variants from playing with zero/uninitialized envelope data.

These two fixes repair the opening Purple Motion chord corruption and the large regression at the next section around 44.5 seconds.

## S3M / IT-S3M split inherited from v0.4.2

- S3M creator/version information is read from `cwtv` instead of selecting all `.s3m` files as one playback profile.
- Real ST3 files use the ST3-specific engine and shared-effect-memory semantics.
- Impulse Tracker-authored S3Ms use the separate IT-S3M engine and IT-compatible command memory/retrigger/portamento behavior.
- ST3 GUS saves are distinguished from SoundBlaster-oriented saves where relevant to sample behavior.

## Usage

```text
python3 CONVERT_TRACKER_TO_KSP.py song.s3m
python3 CONVERT_TRACKER_TO_KSP.py song.xm
python3 CONVERT_TRACKER_TO_KSP.py song.mod
```

Format-specific wrappers are included as well.

## Source tree

The root converter files and their copies under `source/` are synchronized in this release. `source/BUILD_ENGINES.py` rebuilds all four Z80 engine binaries.

## TinyKSP

The included TinyKSP 1.9.9 header-cache patch remains required for emulated playback that caches OPL4 wave headers outside the actual OPL4 RAM image. Real MoonSound hardware observes the RAM writes directly.
