# KSP structures used by KSP1PLAY

The exact constants are in `src/include/ksp_format.inc`; the RAM workspaces are
laid out in `src/data/package_workspaces.asm`.

## Fixed record sizes

| Record | Size |
|---|---:|
| KSP header | `80h` bytes |
| engine record | `40h` bytes |
| track record | `20h` bytes |
| page record | `20h` bytes |
| resource record | `20h` bytes |

The player reads one record into its matching workspace, then interprets fields
through named labels/constants rather than open-coded offsets.

## Package tables

The KSP header supplies offsets/counts/entry sizes for engine, page, track,
resource and string tables. Table access uses the file helpers in
`core/startup_io.asm` and validation in `format/ksp_format.asm`.

## Page materialization

Track/engine records can refer to page resources and HPL/RMP/PBM/KZB data. The
main player prepares descriptors; the `C400h` runtime handles page
materialization and associated cache/disk-buffer work.

## HVAR

HVAR defines visible/logical track handling, implementation selection and
metadata-related state. Its format constants are in `include/hvar_format.inc`;
its runtime/shared-state ABI is in `include/hvar_abi.inc`.

## IMG5

IMG5 image constants and working addresses are in `include/image_format.inc`.
The service runtime validates and preloads image payload/palette data into VRAM.

## Shared scratch space

Some structures exist only during package preparation and deliberately reuse RAM
that belongs to another subsystem during playback. `docs/MEMORY_MAP.md` lists the
known ownership changes. Never keep a pointer into a preparation-only workspace
across a transition into playback unless the code explicitly copies it first.
