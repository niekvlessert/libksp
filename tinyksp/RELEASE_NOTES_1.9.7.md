# TinyKSP 1.9.7

- Adds wildcard KSP selection with `*` and `?` in the filename.
- Accepts multiple KSP file arguments, including shell-expanded wildcards.
- Plays the next visible supported track automatically when the current track duration ends.
- After the final playable track, advances to the next matched KSP file.
- Keeps the current hardware playback type where the next track or file offers the same type; otherwise uses its first supported type.
- Manual Left/Right track selection still wraps within the current KSP. Automatic progression never wraps.
- `q`, Esc and Ctrl-C stop the complete playlist.

Examples:

```sh
tinyksp '*.ksp'
tinyksp game*.ksp --seconds 30
tinyksp intro.ksp music.ksp ending.ksp
```

`--wav` and `--dry-run` remain single-file operations.
