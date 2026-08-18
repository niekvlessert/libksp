# Change guide

Use this as the entry point for modifications.

| Change | Primary files | Also check |
|---|---|---|
| startup / DOS1 file I/O | `core/startup_io.asm` | `platform.inc`, KSPOS boot behavior |
| mapper allocation / page ownership | `core/mapper_kspos.asm` | `memory_map.inc`, cleanup paths |
| KSP header/table rules | `format/ksp_format.asm` | `ksp_format.inc`, package workspaces |
| logical track selection | `runtime/track_engine.asm` | HVAR ABI, track browser |
| INIT/PLAY/STOP | `runtime/engine_calls_audio.asm` | KSPOS gateway, audio mute/cleanup |
| dynamic/page materialization | `runtime/RECON_RUNTIME.asm`, `track_engine.asm` | `recon_abi.inc`, generated image |
| ZX0/stream behavior | `runtime/stream_decode.asm` | mapper history/output state |
| SCC/SCC+ slot detection | `platform/hardware.asm` | hardware flags and startup screen |
| FM-PAC/OPL4 runtime setup | `platform/runtime_audio.asm`, engine calls | hardware requirements |
| VDP access/timing | `platform/vdp.asm` | page-3 helper and UI callers |
| package/game browser | `ui/KSPMENU.asm`, `ui/menu_backend.asm` | `menu_abi.inc` fixed jump table |
| playback key behavior | `ui/application.asm`, `ui/input.asm` | `ui_constants.inc` |
| track paging | `ui/track_browser.asm` | HVAR visible-track helpers |
| metadata/time display | `ui/metadata_playback.asm` | HVAR runtime/state |
| logo / startup presentation | `ui/overlay_loader.asm`, `ui/startup_splash.asm` | VDP/VRAM constants |
| IMG5 gallery | `ui/game_intro.asm`, service tail | `image_format.inc`, service ABI |
| KSPOS boot/resident | `src/boot/` | fixed payload layout |
| fixed address / ABI | relevant `src/include/*.inc` | all users; avoid local literals |

## Safe workflow

1. Read the relevant ABI/memory docs before editing a runtime image or shared
   address.
2. Make the smallest coherent source change.
3. Run `python3 verify_source.py`.
4. If the binary is intentionally changing, update expected hashes only after
   runtime testing establishes the new build as the desired baseline.
5. For changes to timing-sensitive PLAY/VDP/audio paths, test on Z80-class MSX
   timing, not only on a fast host player.

## Source-style rules

- Use semantic labels and named constants.
- Keep a routine wholly inside one logical module when possible.
- Use local/control-flow names such as `*_loop`, `*_done`, `*_bad` rather than
  address-derived names.
- Put cross-runtime addresses in an ABI include.
- Represent data/padding as `db`, `dw` or `ds`; keep `nop` only where it is an
  actual instruction or fixed executable spacing.
- Add a brief contract for non-obvious public/hot-path routines.
