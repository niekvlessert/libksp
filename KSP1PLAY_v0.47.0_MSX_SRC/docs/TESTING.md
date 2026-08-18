# Build and testing

## One-command source verification

```sh
python3 verify_source.py
```

This performs:

1. full no-disk build;
2. exact hash/size checks for KSPPLAYER, KSPMENU, KSPBOOT and the `C400h` runtime;
3. generated symbol/call documentation refresh;
4. AI-context refresh;
5. structural source audit.

## Build bootable disk

```sh
python3 build.py
```

Output:

`build/KSP1PLAY_v0.47.0_SOURCE_BASE_NO_COM.DSK`

The disk contains KSPBOOT, KSPMENU, an empty INDEX.TXT and README.TXT. Add KSP
packages/index records with the normal disk builder.

## Exact fixed outputs

The expected sizes and SHA-256 hashes are declared in `build.py` and documented
in `README.md`. A mismatch aborts the build.

## Runtime smoke tests for behavior changes

For changes that intentionally alter code, exercise at least:

- boot to game browser;
- load a normal package;
- load a package requiring the changed hardware/runtime path;
- next/previous track;
- metadata and track-page switching;
- pause/mute/loop controls;
- return to browser and load another package;
- IMG5/logo path when relevant;
- cleanup after a failed package/hardware requirement.

Timing/audio changes should be checked on Z80-class timing. Disk/page changes
should include a package that forces dynamic materialization/cache activity.
