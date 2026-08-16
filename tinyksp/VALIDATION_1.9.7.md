# TinyKSP 1.9.7 validation

Validated on Linux x86-64 from the bundled offline libvgm source:

- GCC/CMake release build passes.
- `tinyksp -v` reports `1.9.7`.
- Literal wildcard expansion (`'*.ksp'`) finds and sorts matching KSP files.
- Shell-expanded multiple file arguments are accepted as one playlist.
- A completed track automatically starts the next visible supported track.
- The final track automatically advances to the next KSP file.
- Manual seek, arrow-track switching, muting and quit controls retain their existing behavior.
- Windows frontend syntax check passes with the existing Windows stubs.

Regression note: the standalone synthetic `yamaha_smoke` OPL4 PCM fixture also
fails in the unmodified 1.9.6 source in this environment. The 1.9.7 changes are
confined to the command-line/live-playback frontend and do not alter the OPL4,
Z80, KSP parser or sound-device cores.
