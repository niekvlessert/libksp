# KSP1PLAY v0.33 packed full test report

## Content validation

```text
status: PASS
tracks: 51
total frames: 368680
maximum pages per track: 14
maximum changed-frame payload: 43 bytes
full package pages: 409
```

The complete machine-readable report is `ALL_51_TRACK_VALIDATION.json`.

## OpenMSX installation and switching

### Fixed two-track test

Both tracks cold-started and 20/20 alternating switches completed on:

- Panasonic FS-A1ST turboR
- Philips NMS-8250, 128-KiB class

### Full volume A

Local tracks 0 and 25 cold-started on both machines. Four internal replacement tests completed on both machines.

### Full volume B

Local tracks 0 and 24 cold-started on both machines. Four internal replacement tests completed on both machines.

## UI validation

The final Volume A VRAM trace confirms:

```text
R2=6 during cold install; normal name table contains "TRACK LADEN"
R2=14 during playback; private name table contains "AFSPELEN"
R2=14 during replacement; private name table contains "LADEN..."
```

The stable post-install page uses private SCREEN 1 tables at pattern base `3000h` and name-table base `3800h`.

## Limits

OpenMSX startup and representative switching tests do not replace physical listening. The full 51-track set has not yet been listened to end-to-end on the user's real dual-SCC MSX.
