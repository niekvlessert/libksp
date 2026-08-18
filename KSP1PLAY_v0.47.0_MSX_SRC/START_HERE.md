# Start here — KSP1PLAY v0.47.0

This is the quickest orientation for a human or a fresh AI context.

## What this project builds

KSP1PLAY runs KSP packages on MSX under KSPOS. The build produces:

- `KSPPLAYER.BIN`: fixed player image at `0100h..77FFh`.
- `KSPMENU.BIN`: reloadable 2 KiB UI module at `8000h..87FFh`.
- `KSPBOOT.BIN`: player plus KSPOS resident/finalizer payload.
- `RECON_RUNTIME.BIN`: page-materialization runtime assembled for `C400h`.
- a bootable source-base DSK containing KSPBOOT, KSPMENU and an empty index.

## Read in this order

1. `START_HERE.md` — this page.
2. `docs/ARCHITECTURE.md` — subsystem responsibilities.
3. `docs/MEMORY_MAP.md` — CPU/RAM/VRAM ownership and address reuse.
4. `docs/OVERLAY_ABI.md` — host images, runtime destinations and jump tables.
5. `docs/RUNTIME_FLOWS.md` — startup, package load, track install and playback.
6. `docs/CHANGE_GUIDE.md` — which file to edit for a particular change.
7. Relevant `.asm` module and matching `.inc` ABI/structure definitions.

For a compact handoff, generate/read `build/KSP1PLAY_AI_CONTEXT.md`.

## Non-negotiable invariants

1. **Exact-build gate.** Until a binary change is intentional, `python3 verify_source.py`
   must reproduce the four hashes in `README.md`.
2. **Fixed player layout.** `KSPPLAYER.BIN` occupies `0100h..77FFh`.
3. **Fixed menu ABI.** The KSPMENU jump table at `8000h` is a public interface.
4. **Address ownership changes with mapping.** The same CPU address can refer to
   different objects under different mapper/overlay states. Never infer ownership
   from the number alone.
5. **Playback hot path must remain disk-free.** Normal PLAY execution must not
   introduce FAT/BDOS/disk work.
6. **Track changes are transactional.** Stop/mute, mapper state, engine pages and
   interrupt state must be restored consistently on success and failure.
7. **Runtime-image targets are ABI.** Host storage addresses and runtime execution
   addresses are different concepts; keep them separate in names/comments.
8. **Generated runtime bytes are not edited by hand.** Edit
   `src/runtime/RECON_RUNTIME.asm`; `build.py` regenerates its stored image.

## Main control flow

```text
start
  -> init_application_defaults
  -> get_mapper_api
  -> capture_original_pages
  -> kspos_detect_and_prepare
  -> ui_application
       -> ui_menu / ui_load_pack
       -> ui_prepare_selected_engine
       -> ui_install_selected_track
       -> ui_play_screen
            -> wait_vblank_without_keyclick
            -> call_play
            -> UI action dispatch
```

See `docs/RUNTIME_FLOWS.md` for the expanded flows.

## If you want to change…

| Goal | Start here |
|---|---|
| KSP parsing / table validation | `src/format/ksp_format.asm` |
| track selection / page preparation | `src/runtime/track_engine.asm` |
| INIT/PLAY/STOP or audio writes | `src/runtime/engine_calls_audio.asm`, `src/platform/runtime_audio.asm` |
| ZX0/stream decode | `src/runtime/stream_decode.asm` |
| mapper/KSPOS behavior | `src/core/mapper_kspos.asm` |
| game/package browser | `src/ui/KSPMENU.asm`, `src/ui/menu_backend.asm` |
| track screen / actions | `src/ui/application.asm`, `src/ui/track_browser.asm` |
| metadata / elapsed time | `src/ui/metadata_playback.asm`, HVAR runtime image |
| logo / image gallery | `src/ui/overlay_loader.asm`, `src/ui/game_intro.asm`, service tail |
| SCC/SCC+/FM-PAC/OPL4 detection | `src/platform/hardware.asm` |
| VDP helpers | `src/platform/vdp.asm` |
| boot/KSPOS resident | `src/boot/` |
| ABI address or fixed region | `src/include/` first; do not scatter a new raw address |

## Before handing work to another context

Run:

```sh
python3 verify_source.py
```

Then provide `build/KSP1PLAY_AI_CONTEXT.md` plus only the source modules relevant
to the requested change. That keeps context small while preserving architecture,
ABI and test invariants.
