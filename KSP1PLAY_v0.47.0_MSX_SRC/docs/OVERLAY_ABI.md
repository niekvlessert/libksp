# Runtime-image and overlay ABI

## Host image to runtime target

| Host in KSPPLAYER | Runtime target | Maximum / copied bytes | Role |
|---|---:|---:|---|
| `4A00h` | `6800h` | `0600h` | service head / MWK services |
| `4F00h` | `C35Ch` | `00A4h` | playback-control helper |
| `5000h` | `8000h` | `0C00h` | HVAR UI/metadata runtime |
| `5C00h` | `C400h` | slot `1900h`; active image `1883h` | page materializer |
| `7500h` | `6E00h` | copied `02F0h` | service tail / split / IMG5 |
| separate `KSPMENU.BIN` | `8000h` | `0800h` | reloadable browser renderer |

## Public interfaces

Use these include files rather than runtime numbers:

- `menu_abi.inc`
- `recon_abi.inc`
- `service_abi.inc`
- `service_runtime_abi.inc`
- `hvar_abi.inc`
- `ui_p3_abi.inc`
- `kspos_abi.inc`
- `kspos_runtime_abi.inc`

### KSPMENU

The first bytes at `8000h` are a stable jump table. Player code calls the named
`KSPMENU_*` symbols. Do not move those slots casually: the player and menu are
built separately.

### Page-3 playback helper

`C35Ch`, `C35Fh` and `C362h` are public jump slots for cursor-up, cursor-down and
pause-toggle. The actual implementations start later. `ui_p3_abi.inc` names both
the call slots and implementation addresses to prevent accidental conflation.

### Page materializer

The `RECON_*` prefix is the established ABI namespace for the runtime that
materializes package pages. Its public jump table starts at `C400h`. Normal
player code should call those entries through `recon_abi.inc`.

## Shared-address warning

Runtime overlays intentionally reuse CPU ranges. A label valid while HVAR owns
`8000h` is not valid while KSPMENU owns `8000h`. Likewise, page-3 shared state and
stopped-state scratch buffers may share addresses in different phases.

When adding a call or field:

1. identify the owner/runtime phase;
2. add or reuse a symbol in that owner's ABI include;
3. use the symbol from implementation code;
4. run `python3 verify_source.py`.
