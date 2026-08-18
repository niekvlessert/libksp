# KSP1PLAY v0.47.0 MSX source

KSP1PLAY is the MSX-side KSP music player used by KSPOS. The project builds the
player, reloadable menu, boot payload and a bootable source-base disk.

Start with **[START_HERE.md](START_HERE.md)**. It gives the read order, core
invariants, source map and the shortest route to each subsystem.

## Build

```sh
python3 verify_source.py
python3 build.py
```

`verify_source.py` rebuilds the project, refreshes generated documentation and
runs structural checks. `build.py` also creates the bootable source-base DSK.

The fixed v0.47.0 outputs are:

| Output | Size | SHA-256 |
|---|---:|---|
| `KSPPLAYER.BIN` | 30,464 | `1f86b9a461de240a8e9665a7d8a3a48eda257e00856876af717887fbd654c0f8` |
| `KSPMENU.BIN` | 2,048 | `afaa2f8501830ee24b9b078647c6a9e7c976ef993886b39beb7ff665605e4304` |
| `KSPBOOT.BIN` | 31,043 | `8b75436e579957a6dc8812b8eea4ff7ca9f3ffb72524d730774bcf1fb156ca3c` |
| `RECON_RUNTIME.BIN` | 6,275 | `12d165a53d042af169101eb3423a50aabcd06a3e33a98f7dbeaefef487683c3f` |

## Source layout

- `src/KSPPLAYER.asm` — binary-order manifest for the main player.
- `src/core/` — startup, DOS/FCB I/O, mapper and KSPOS integration.
- `src/format/` — KSP header/table validation and package-format helpers.
- `src/runtime/` — track install, engine calls, stream decode, runtime images.
- `src/platform/` — VDP, audio-hardware and slot detection.
- `src/ui/` — application loop, package browser, tracks, metadata and images.
- `src/data/` — fixed workspaces and runtime state.
- `src/include/` — memory map, format constants and cross-runtime ABIs.
- `src/boot/` — KSPOS gateway, resident service, finalizer and boot loader.
- `tools/` — assembler, disk builder helpers, audits and doc generators.
- `docs/` — architecture, memory/ABI maps, runtime flows and change guide.

## Design rule

Code outside a runtime image should call named ABI symbols, not unexplained
numeric addresses. Shared addresses may represent different objects in different
mapper/overlay states, so use the ABI or structure name appropriate to that
state.
