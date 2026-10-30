# Tracker2KSP v0.5.2 test report

## Native IT compatibility / paging pass

v0.5.2 extends only the dedicated native-IT route. KSP remains 1.05 and the other four engine sizes remain unchanged.

### Automated regressions

```text
PYTHONPATH=source:tests:. python3 -m pytest -q tests/test_it_v049.py tests/test_it_v050.py tests/test_it_v051.py tests/test_it_v052.py
PYTHONPATH=source:tests:. python3 tests/test_s3m_v045.py
PYTHONPATH=source:tests:. python3 tests/test_xm_v046.py
PYTHONPATH=source:tests:. python3 tests/test_xm_v047.py
PYTHONPATH=source:tests:. python3 tests/test_mod_v048.py
python3 source/BUILD_ENGINES.py
```

Results: **37/37 native IT**, **4/4 S3M**, **10/10 + 4/4 XM**, **8/8 MOD** PASS.

The v0.5.2 tests cover linear E/F/G factor generation and stream payloads, S50-S53 panbrello selection, IT instrument/sample default pan precedence, PPS/PPC use of the original pattern note, SV×IV per-voice gain, filter-envelope file flag `0x80`, Compatible-Gxx profile reset, explicit sample-swap porta rejection, persistent-state/profile layout, the `$7C02` native stream-data address, carry-safe M/V/T parsing, and 16-bit dynamic-page counts beyond the previous 48-page ceiling.

### Engine build

- ST3/S3M: **9,054 bytes**
- IT-authored/modern S3M: **8,926 bytes**
- native IT: **12,800 bytes**
- MOD: **10,674 bytes**
- XM: **6,472 bytes**

Native IT profile pointers are at `$7000`, profile data starts at `$7200`, and the semantic-page window is `$7C00-$7FFF` with stream data at `$7C02`. Persistent IT state is **929 bytes**, below the 1,024-byte MoonSound reserve.

### Real-world IT validation

External validation module (not redistributed in the source package):

- title: **Coral Capers**
- source SHA-256: `45cfaf2eaed915d0a3b9285fffcc6bf16cfd0e855a8de567696d61ed6591d9b1`
- IT compatibility: **2.17**, created with IT 2.00
- active channels: **16**
- samples: **40**
- initial speed / tempo: **1 / 250**
- semantic rows / events: **13,441 / 58,393**
- compiler duration to detected sequence loop: **134.41 s**
- semantic pages: **317**
- converter warnings: **0**
- KSP output: **212,703 bytes**

TinyKSP 1.9.9 accepted the generated KSP 1.05 package and completed a 140-second WAV render using the unmodified normal 5,000,000-cycle VM guard:

- PLAY calls: **8,399**
- dynamic page switches: **316**
- OPL4 PCM writes: **1,019,119**
- VM/cycle-limit failures: **0**

This validation exposed and now permanently covers the stale `$6802` stream-data constant, carry leakage from valid M/V/T effect parsing, and the artificial 48-page limit.

### Accuracy boundary

`Zxx` remains deliberately rejected because IT uses it for MIDI/filter macros. Random swing, envelope carry/filter envelopes, sample sustain/ping-pong loop edge cases, sample auto-vibrato, delayed non-neutral trigger-state application and genuine G/L sample/C5 swaps remain fail-fast. Exact 24-voice NNA allocation is retained; a sounding 25th voice is never silently stolen.

---

# Tracker2KSP v0.5.1 test report

## Native IT extended effect runtime

v0.5.1 extends only the dedicated native-IT engine. KSP remains 1.05; the ST3/S3M, IT-S3M, MOD and XM engines remain byte-size unchanged.

### Automated regressions

```text
PYTHONPATH=source python3 -m pytest -q tests/test_it_v049.py tests/test_it_v050.py tests/test_it_v051.py
PYTHONPATH=source python3 tests/test_s3m_v045.py
PYTHONPATH=source python3 tests/test_xm_v046.py
PYTHONPATH=source python3 tests/test_xm_v047.py
PYTHONPATH=source python3 tests/test_mod_v048.py
python3 source/BUILD_ENGINES.py
```

Results: **25/25 native IT**, **4/4 S3M**, **10/10 + 4/4 XM**, **8/8 MOD** PASS.

The v0.5.1 native tests cover J/M/N/P/T/U/V/W/Y parser acceptance, Zxx fail-fast behaviour, IT-local effect memories, shared H/U memory, N/P/W fine-slide tick-zero ordering, T slide semantics, dynamic header/channel/global volume, NNA logical-state inheritance, the T/W global pre-pass, physical engine separation, and the complete dynamic-page persistent-state footprint. The persisted state totals **905 bytes**, below the 1,024-byte MoonSound reserve.

### Engine build

Fresh `python3 source/BUILD_ENGINES.py` output:

- ST3/S3M: **9,054 bytes**
- IT-authored/modern S3M: **8,926 bytes**
- native IT: **12,288 bytes**
- MOD: **10,674 bytes**
- XM: **6,472 bytes**

Native IT uses profile pointers at `$6E00`, profile data from `$7000`, and semantic pages at `$7C00-$7FFF`. The other four engine sizes are unchanged from v0.5.0.

### End-to-end native IT effect smoke

A fresh synthetic instrument-mode IT fixture combines instrument envelopes/NNA with J37, N20, P03 and T11 and is converted through the actual v0.5.1 CLI:

- format: **KSP 1.05**
- converter: **0.5.1**
- output: **18,464 bytes**
- engine: **12,288 bytes**
- IT profiles: **2**, resident profile payload **116 bytes**
- semantic rows/events: **4 / 5**
- semantic stream: **76 bytes**, one page
- warnings: **0**
- KSP SHA-256: `03b458c3a2ebe152a7b36de634654e5f9ebbebb322d276bf65913f309a141b77`

### Accuracy boundary

`Zxx` remains deliberately rejected because IT's Z command is MIDI/filter-macro execution, not a generic PCM effect. `S5x` non-default panbrello waveform selection is also still rejected, so Yxy currently uses the default sine path. Panbrello uses an 8-bit phase but is ultimately quantized to OPL4 hardware pan positions. The converter continues to fail rather than steal a 25th simultaneous OPL4 PCM voice.

---

# Tracker2KSP v0.5.0 test report

## Native IT envelopes / voice allocation

v0.5.0 starts from the source-backed v0.4.9 native `IMPM` implementation. It adds IT instrument envelopes, fadeout and NNA/DCT/DCA while retaining a physically separate native-IT Z80 engine and KSP 1.05 framing.

### Automated regressions

```text
PYTHONPATH=source:tests:. python3 -m pytest -q tests/test_it_v049.py tests/test_it_v050.py
PYTHONPATH=source:tests:. python3 tests/test_s3m_v045.py
PYTHONPATH=source:tests:. python3 tests/test_xm_v046.py
PYTHONPATH=source:tests:. python3 tests/test_xm_v047.py
PYTHONPATH=source:tests:. python3 tests/test_mod_v048.py
python3 source/BUILD_ENGINES.py
```

Results: **19/19 native IT**, **4/4 S3M**, **10/10 + 4/4 XM**, **8/8 MOD** PASS.

The native-IT tests cover profile/envelope patching, volume/pan/pitch envelope representation, FadeOut, Note Off/Cut/Fade separation, NNA Continue/Off/Fade, DCT Note/Sample/Instrument, DCA Cut/Off/Fade, original-pattern-note DCT matching, 24-voice exact-limit handling, held sustain endpoint behaviour, and the `$7C00` IT stream layout.

### Engine build

`python3 source/BUILD_ENGINES.py` builds five independent binaries:

- ST3/S3M: **9,054 bytes**
- IT-authored/modern S3M: **8,926 bytes**
- native IT: **11,776 bytes**
- MOD: **10,674 bytes**
- XM: **6,472 bytes**

Only the native IT engine grew. Native IT semantic pages use `$7C00-$7FFF`; its profile/state data remains resident below that boundary and in the already-reserved `$2FFC00-$2FFFFF` MoonSound RAM block.

### End-to-end native IT smoke

Fresh conversion of the synthetic instrument-mode envelope/NNA fixture builds a **KSP 1.05** file through the dedicated native-IT engine:

- output: **18,456 bytes**
- engine: **11,776 bytes**
- IT profiles: **2**, resident profile payload **120 bytes**
- semantic stream: **68 bytes**, one page
- converter warnings: **0**
- KSP SHA-256: `9e908b9762dd86addba61e18e24a27caa411b0411f51e53fb221b0f96f0102ba`

### Accuracy boundary

Exact playback is preferred over silent approximation. The allocator never steals a currently tracked sounding OPL4 voice; if NNA/DCT needs more than 24 simultaneous physical voices it fails explicitly. It currently does not predict natural sample ends or all release-envelope completion at conversion time, so some very NNA-heavy files may hit this conservative limit sooner than the real instantaneous voice count would require.

Still intentionally rejected: envelope carry/filter envelopes, pitch-pan separation, random volume/pan, non-neutral instrument/sample global-volume/default-pan combinations, sustain/ping-pong sample loops, sample auto-vibrato, Old Effects, linear E/F/G, exact Jxx arpeggio timing, tempo slides below `20h`, unsupported M/N/P/U/V/W/Y/Z effects, and delayed-note + NNA/DCT runtime allocation.

---

# Tracker2KSP v0.4.8 test report

## Scope

v0.4.8 is the generic MOD / ProTracker compatibility pass. It adds the remaining high-value OpenMPT MOD semantics after the initial v0.4.8 audit, while preserving the v0.4.7 XM and v0.4.5 S3M runtimes.

## Automated regressions

```text
PYTHONPATH=. python3 tests/test_mod_v048.py
PYTHONPATH=. python3 tests/test_xm_v046.py
PYTHONPATH=. python3 tests/test_xm_v047.py
PYTHONPATH=. python3 tests/test_s3m_v045.py
```

Results:

- **8/8 MOD v0.4.8 groups PASS**
- **10/10 XM v0.4.6 groups PASS**
- **4/4 XM v0.4.7 groups PASS**
- **4/4 S3M v0.4.5 groups PASS**

The MOD groups cover ProTracker effect-memory and extended effects, exact tuned periods, signature/FLT8 handling, MOD ADPCM, sample-swap detection, one-shot-loop payload geometry, CIA/VBlank profiling, exact finetune-dependent Amiga bounds, EFx runtime presence and variable-length sample-swap stream records.

## OpenMPT supplied test.mod

Final smoke conversion of `openmpt-master/test/test.mod`:

- profile: `PROTRACKER`
- converter: `0.4.8`
- warnings: 0
- output: `tests/openmpt_test_mod_v048.ksp`
- report: `tests/openmpt_test_mod_v048_result.json`
- MOD engine: 10,674 bytes
- engine resident range: `$4000-$69FF` descriptor window; actual binary ends at `$69B1`
- semantic stream window: `$6A00-$7FFF`

## Engine layout

`python3 source/BUILD_ENGINES.py`:

- ST3/S3M: **9,054 bytes**
- IT/modern-S3M: **8,926 bytes**
- MOD: **10,674 bytes**
- XM: **6,472 bytes**

Legacy MOD LUT addresses remain unchanged:

```text
SINE_TABLE    $4A6C
VOL_LUT       $4AB0
PITCH_LUT     $4B11
PITCH_LUT_END $5F63
MOD_FINETUNE  $5F64
```

The ST3/S3M, IT/modern-S3M and XM binaries are byte-identical to v0.4.7.

## Python/source validation

Root and `source/` copies of `tracker2ksp.py`, `module_formats.py` and `compact_stream.py` are byte-identical. Python compilation and all regression suites pass.

## Accuracy boundary

EFx now performs live OPL4 RAM mutation instead of being ignored, one-shot loop geometry is reproduced, and the loader/classifier follows the major OpenMPT ProTracker heuristics. Exact Paula sample-end sample-swap timing remains an OPL4 hardware limitation and is approximated at the tracker row boundary. Amiga analogue filtering/surround and sample-for-sample Paula mixer identity are not claimed.

## Cross-format end-to-end smoke

The final release files were also used for fresh end-to-end KSP builds of OpenMPT's supplied fixtures:

- `test.mod`: `PROTRACKER`, 0 warnings, `$6A00` MOD stream window.
- `test.xm`: `OPENMPT`, 0 warnings, `$6800` XM stream window.
- `test.s3m`: `MODERN-S3M`, 0 warnings, `$6800` S3M stream window.
