# Memory map

## Fixed file / CPU layout

| Range / address | Owner | Notes |
|---|---|---|
| `0100h..77FFh` | KSPPLAYER | 30,464-byte fixed player image |
| `4A00h` host | service head image | copied to service runtime area |
| `4F00h` host | page-3 UI helper image | copied to `C35Ch` |
| `5000h` host | HVAR image | copied to `8000h` when active |
| `5C00h` host | page-materializer image | copied to `C400h` |
| `7500h` host | service / IMG5 tail | copied to service runtime area |
| `7800h..7970h` | KSPOS resident payload | placed directly after player in KSPBOOT |
| `7971h` | KSPOS finalizer | fixed post-resident entry |
| `8000h..87FFh` | KSPMENU runtime | reloadable 2 KiB module |

The host-image addresses above are locations *inside* KSPPLAYER. They must not be
confused with the runtime target addresses in the next table.

## Runtime targets

| Runtime address | Role |
|---|---|
| `6800h` | service head / MWK-related service code |
| `6E00h` | service tail / split-screen and IMG5 support |
| `8000h` | HVAR runtime or KSPMENU, depending on current phase |
| `C300h` | shared page-3 state / stopped-state scratch according to owner |
| `C35Ch` | page-3 playback-control jump table |
| `C400h` | page-materialization runtime |

`8000h` is intentionally phase-dependent. Code must use the correct ABI for the
currently loaded object.

## Important RAM workspaces

| Address | Symbol / role |
|---|---|
| `1A16h` | package filename workspace |
| `1C80h` | KSP header workspace |
| `1D00h` | engine descriptor workspace |
| `1E00h..1FFFh` | 512-byte shared I/O/scratch buffer |
| `2F71h` | UI line buffer |
| `35E0h` | HPOL position cache during package preparation |
| `37E0h` | HPOL map-row cache during package preparation |
| `BF80h` | HVAR metadata line buffer |
| `C300h+` | HVAR/KSPOS shared state fields |

`35E0h` and `37E0h` are deliberately reused during stopped-state preparation.
Do not assume those locations retain UI contents while package preparation owns
the workspace.

## Important VRAM regions

Named constants live in `include/memory_map.inc` and `include/image_format.inc`.
Notable examples:

- `META_CACHE_VRAM_BASE = 1900h`
- `UI_GAME_TITLE_VRAM = 1800h`
- `MENU_OVERLAY_VRAM_IMAGE = 6A00h`
- `IMG5_INDICATOR_VRAM = 789Ah`

Prefer these symbols over literal VRAM addresses.

## Mapper pages

The player captures the process mapper pages at startup and restores them around
track transitions and dynamic page work. Page-2 and page-3 ownership can change
while an engine/runtime is active. `core/mapper_kspos.asm` is the source of truth
for page ownership and restoration rules.
